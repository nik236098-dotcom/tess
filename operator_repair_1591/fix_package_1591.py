#!/usr/bin/env python3
"""Revision 2 of the beeline_integrated_io_15_91 package. Run on the EXTRACTED package.

    python3 fix_package_1591.py /path/to/extracted/package

Changes made in place (idempotent, refuses any other package):
1. test_beeline.py: the separate SUCCESS push is no longer cut to 4000 characters.
   It goes through the durable outbox (split into confirmed parts by the 15.91 sender);
   if the queue is unavailable it is sent directly, split, never truncated.
2. test_update.py: the preserved-handler hashes no longer depend on ast.dump(), whose
   text changed in Python 3.13; the installer's preflight failed on Python <= 3.12.
3. install.py: the reviewed package copies are installed after the input checksum
   matches, instead of re-applying edits.json line ranges.
4. test_beeline.py: the proxy login is removed from the code (TELEGRAM_DEFAULT_PROXY = "");
   the runtime already reads telegram_config.json "proxy" first. install.py refuses to
   run until that key exists, so Telegram traffic never silently loses the proxy.
5. test_beeline.py: autonomous SUCCESS/ERROR assist requests get a budget per page
   state (two per unchanged URL, then one per 30 minutes, none while the previous one
   is unanswered) instead of a full agent run and an identical report every 45 seconds.
6. test_beeline.py: registration/error policy. After the analysis report the runtime
   closes the error page, opens a fresh one and retries the row once; a second error on
   the same row skips it (logged, Telegram notice). A worker is never stopped by an error.
   The rule is also written into the DeepSeek system instructions and the task text.
7. manifest.json, edits.json, SHA256SUMS.txt, verification.json, test_results.txt are
   regenerated so every checksum the installer verifies is consistent again.
"""
from __future__ import annotations
import ast
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import re

MARKER = "SUCCESS_PUSH_DURABLE_1591R2"
PROXY_MARKER = "PROXY_FROM_CONFIG_1591R3"
EXPECTED_INPUT_OUTPUT_SHA = "9e216a70bb1e931c2e9568687c26564a0132bccd6b748dd42fef4eff9335fa50"
# test_beeline.py of the first build and of revision 2 are both accepted as input.
ACCEPTED_PACKAGE_SHAS = {EXPECTED_INPUT_OUTPUT_SHA,
                         "8f5fc960fc6cc44faebc19eae0709057f3c8c627d623d9219a0c85cff81d3012",
                         "437155a246d1e370a68cc29ec54850944837f0a575600c57c9f30b9849ebdf73",
                         "b835682314ab8958af4500f7176ca660608f14f09bb7bd02827eb503a23597b0"}

# Revision 5: registration/error policy. After the detailed analysis and its report the
# runtime closes the error page, opens a fresh one and retries the row once; a second
# error on the same row skips it. A worker slot is never stopped because of an error.
ERROR_MARKER = "ERROR_RECOVERY_1591R5"
MISSION_RULE_R5 = (
    "\n\nПРАВИЛО ОШИБКИ РЕГИСТРАЦИИ (ERROR_RECOVERY_1591R5): /registration/error — не успех, "
    "но и не вечное ожидание. Сначала детальный анализ страницы (DOM, текст ошибки, console/network) "
    "и мини-отчёт. После отчёта error-вкладка закрывается и открывается новая автоматически, без отдельного подтверждения: "
    "runtime делает это сразу после твоего отчёта и повторяет ту же строку один раз. "
    "При повторной ошибке на той же строке строка пропускается без нового анализа, worker берёт "
    "следующую. Ни одна ошибка не должна приводить к потере worker. Запрет close/restart/reload "
    "остаётся только для SUCCESS_GUARD.")
AGENT_ERROR_BLOCK_R5 = '''ERROR SUPERVISOR:
- /registration/error НИКОГДА не является success.
- Сначала самостоятельно изучи DOM, видимый текст, console/network и последние ответы API.
  Определи конкретную причину и, если это безопасно, попробуй исправить на текущей странице.
- Затем отправь мини-отчёт: причина, что проверил, что попробовал, результат, URL.
- После детального анализа и отчёта error-вкладка закрывается и открывается новая
  АВТОМАТИЧЕСКИ, без отдельного подтверждения: runtime делает это сразу после твоего
  отчёта и повторяет ту же строку один раз. При повторной ошибке на той же строке
  строка пропускается, worker переходит к следующей.
- Из-за error worker никогда не теряется: слот всегда получает новую вкладку.
- Запрет close/restart/reload/back/navigate действует только на SUCCESS GUARD.

'''
QUEUE_ERROR_TEXT_R5 = '''    text = (
        f"[AUTO_ERROR_ASSIST TAB {tab_id}] "
        "После mobile-id-auth открылась /registration/error. Это НЕ success. "
        "Сначала автономно проанализируй текущую physical-вкладку: DOM, видимый текст "
        "ошибки, DevTools console и network, последние запросы/ответы и состояние формы. "
        "Определи конкретную причину и, если это безопасно, попробуй исправить её на этой "
        "странице. Затем ОБЯЗАТЕЛЬНО отправь мини-отчёт: причина, что проверил, что "
        "попробовал, результат, URL. Сразу после твоего отчёта runtime автоматически, без "
        "отдельного подтверждения, закроет эту error-вкладку, откроет новую и повторит строку один раз; "
        "при повторной ошибке строка будет пропущена. Worker при этом не теряется. "
        "Сам вкладку не закрывай: это сделает runtime после отчёта. "
        f"Причина вызова: {reason}. URL: {url}"
    )
'''
TICK_ERROR_R5 = r'''# ERROR_RECOVERY_1591R5
ERROR_ASSIST_MAX_SECONDS = 300
ERROR_SKIP_DWELL_SECONDS = 15
ERROR_ROW_MAX_ATTEMPTS = 2


def _error_row_key(worker):
    row = worker.get("row")
    try:
        return _row_number_value(row) or str(row)
    except Exception:
        return str(row)


def _error_analysis_delivered(worker):
    state = (worker.get("auto_assist_state") or {}).get("ERROR") or {}
    if int(state.get("count") or 0) < 1:
        return False
    try:
        return not _auto_assist_pending("ERROR", worker.get("id") or 0)
    except Exception:
        return True


def _error_recover(base_dir, worker, reason):
    """Close the error page, open a fresh one; retry the row once, then skip it.

    Runs without user permission. A worker slot is never stopped because of an error.
    """
    key = _error_row_key(worker)
    counts = worker.setdefault("error_retry_counts", {})
    counts[key] = int(counts.get(key) or 0) + 1
    attempt = counts[key]
    try:
        capture_blackbox(worker, "error_recovery")
    except Exception:
        pass
    worker["error_guard"] = False
    worker["success_guard"] = False
    worker["error_assist_entered_at"] = None
    worker["auto_assist_state"] = {}
    worker["phase"] = "ERROR_RECOVERY"
    restart_same_row_in_new_page(worker)
    if worker.get("phase") != "RESTART_ROW_READY":
        print(f"[Вкладка {worker['id']}] ERROR RECOVERY: новая вкладка не создана ({reason}).", flush=True)
        return False
    if attempt < ERROR_ROW_MAX_ATTEMPTS:
        set_tab_status(
            worker, "♻️",
            f"registration/error: {reason}. Вкладка закрыта, открыта новая; "
            f"повторяю строку (попытка {attempt + 1}).",
        )
        external_heartbeat(worker, "error_retry_same_row")
        return True
    # Second error on the same row: skip it; the next row starts on the fresh page.
    try:
        with (Path(base_dir) / "error_skipped_rows.txt").open("a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')}\t{key}\t{reason}\n")
    except Exception:
        pass
    try:
        chat = str(load_telegram_config().get("chat_id") or "")
        if chat:
            _io1591.enqueue_notice(
                globals(), chat,
                f"⏭ Вкладка {worker['id']}: строка {key} пропущена после повторной "
                f"registration/error ({reason}). Worker продолжает со следующей строкой.",
            )
    except Exception:
        pass
    worker["row"] = None
    worker["phase"] = "IDLE"
    set_tab_status(worker, "⏭", f"Строка {key} пропущена после повторной registration/error. Беру следующую.")
    external_heartbeat(worker, "error_row_skipped")
    return True


def tick_error_assist(base_dir, worker):
    page = worker["page"]
    worker["error_guard"] = True
    now = monotonic()
    if not worker.get("error_assist_entered_at"):
        worker["error_assist_entered_at"] = now
    entered = float(worker["error_assist_entered_at"])

    if page.is_closed():
        # A closed error page never costs the worker slot: open a fresh page and go on.
        _error_recover(base_dir, worker, "error-страница закрыта извне")
        return

    # If Operator safely repaired the page and it becomes a real contract page,
    # promote it into the immutable SUCCESS GUARD.
    if _post_auth_contract_page(page) and not _post_auth_error_page(page):
        worker["error_guard"] = False
        worker["error_assist_entered_at"] = None
        enter_success_guard(
            worker,
            "DeepSeek/сайт вывел error-state на страницу договора",
        )
        return

    key = _error_row_key(worker)
    if int((worker.get("error_retry_counts") or {}).get(key) or 0) >= ERROR_ROW_MAX_ATTEMPTS - 1:
        # Repeated error on the same row: no second analysis; skip after a short dwell.
        external_heartbeat(worker, "error_repeat_skip_pending")
        if now - entered >= ERROR_SKIP_DWELL_SECONDS:
            _error_recover(base_dir, worker, "повторная ошибка регистрации на той же строке")
        return

    queue_error_assist(
        worker,
        "registration/error открыта; проанализируй DOM/console/network и отправь отчёт",
    )
    external_heartbeat(worker, "error_assist_observing")
    if _error_analysis_delivered(worker):
        _error_recover(base_dir, worker, "детальный анализ завершён")
    elif now - entered >= ERROR_ASSIST_MAX_SECONDS:
        _error_recover(base_dir, worker, "анализ не получен за отведённое время")
'''
README_NOTE_R5 = '''

РЕВИЗИЯ 5 (fix_package_1591.py)
Правило ошибки регистрации (ERROR_RECOVERY_1591R5). После детального анализа и отчёта
DeepSeek runtime автоматически, без отдельного подтверждения, закрывает error-вкладку, открывает новую и
повторяет ту же строку один раз; при повторной ошибке на той же строке строка
пропускается (без нового анализа, запись в error_skipped_rows.txt и уведомление в
Telegram), worker берёт следующую. Если анализ не пришёл за 5 минут, восстановление
выполняется всё равно. Закрытая извне error-страница тоже больше не останавливает
worker. Правило добавлено в системные инструкции (OPERATOR_MISSION_1586, блок ERROR
SUPERVISOR) и в текст задания AUTO_ERROR_ASSIST. Запрет close/restart остаётся только
для SUCCESS_GUARD. Изменён tick_error_assist; обработчики подписи/страницы не тронуты.
'''

# Revision 4: autonomous SUCCESS/ERROR assist requests get a budget per page state.
# Before: every tick in SUCCESS_ASSIST re-queued a full developer-agent run every 45 s
# while the page did not change, and each run posted an identical report.
ASSIST_MARKER = "AUTO_ASSIST_BUDGET_1591R4"
RESIGNED_HANDLERS = {"queue_success_assist", "queue_error_assist", "tick_error_assist"}
OLD_SUCCESS_THROTTLE = '''    now = monotonic()
    last = float(worker.get("success_ai_last_at") or 0)
    if not force and now - last < 45:
        return False

    worker["success_ai_last_at"] = now
    tab_id = int(worker.get("id") or 0)
'''
NEW_SUCCESS_THROTTLE = '''    if not _auto_assist_allowed(worker, "SUCCESS", force):
        return False
    tab_id = int(worker.get("id") or 0)
'''
OLD_ERROR_THROTTLE = '''    now = monotonic()
    last = float(worker.get("error_ai_last_at") or 0)
    if not force and now - last < 45:
        return False
    worker["error_ai_last_at"] = now

    tab_id = int(worker.get("id") or 0)
'''
NEW_ERROR_THROTTLE = '''    if not _auto_assist_allowed(worker, "ERROR", force):
        return False

    tab_id = int(worker.get("id") or 0)
'''
QUEUE_ERROR_DEF = "def queue_error_assist(worker, reason, force=False):\n"
ASSIST_HELPER = '''# AUTO_ASSIST_BUDGET_1591R4
AUTO_ASSIST_MIN_GAP_SECONDS = 45
AUTO_ASSIST_REPORTS_PER_STATE = 2
AUTO_ASSIST_REPEAT_SECONDS = 1800


def _auto_assist_pending(kind, tab_id):
    """True while an unanswered [AUTO_<kind>_ASSIST TAB n] job is still in the inbox."""
    conn = _ai_db_connect()
    try:
        row = conn.execute(
            "SELECT 1 FROM inbox WHERE done_at IS NULL AND body LIKE ? LIMIT 1",
            (f"[AUTO_{kind}_ASSIST TAB {int(tab_id)}]%",),
        ).fetchone()
        return row is not None
    finally:
        conn.close()


def _auto_assist_allowed(worker, kind, force=False):
    """Budget for autonomous assist requests: the page state, not the clock, decides.

    Per unchanged page URL at most AUTO_ASSIST_REPORTS_PER_STATE requests (the second
    one no sooner than AUTO_ASSIST_MIN_GAP_SECONDS after the first), then one every
    AUTO_ASSIST_REPEAT_SECONDS. A new URL starts a new budget. A request is never
    queued while the previous one for this tab has not been answered yet. `force`
    only waives the minimum gap.
    """
    now = monotonic()
    try:
        url = str(worker.get("page").url or "")
    except Exception:
        url = ""
    states = worker.setdefault("auto_assist_state", {})
    state = states.get(kind)
    if not state or state.get("url") != url:
        state = {"url": url, "count": 0, "last": 0.0}
        states[kind] = state
    try:
        if _auto_assist_pending(kind, worker.get("id") or 0):
            return False
    except Exception:
        pass
    since_last = now - float(state.get("last") or 0)
    if state["count"] >= AUTO_ASSIST_REPORTS_PER_STATE:
        if since_last < AUTO_ASSIST_REPEAT_SECONDS:
            return False
    elif state["count"] > 0 and not force and since_last < AUTO_ASSIST_MIN_GAP_SECONDS:
        return False
    state["count"] += 1
    state["last"] = now
    worker[f"{kind.lower()}_ai_last_at"] = now
    return True


'''
README_NOTE_R4 = '''

РЕВИЗИЯ 4 (fix_package_1591.py)
Бюджет автономных запросов SUCCESS_ASSIST/ERROR_ASSIST. Раньше каждый тик в фазе
SUCCESS_ASSIST ставил в очередь новый полный прогон агента каждые 45 секунд, пока
страница не менялась, и каждый прогон присылал одинаковый отчёт (8 одинаковых
сообщений за 8 минут, лишние токены). Теперь на одну неизменную страницу (URL)
не более двух запросов (второй не раньше чем через 45 с), затем один раз в 30 минут;
новый URL начинает новый бюджет; пока предыдущий запрос по этой вкладке не отвечен,
новый не ставится. Изменены только queue_success_assist и queue_error_assist;
обработчики страницы/подписи не тронуты. Маркер: AUTO_ASSIST_BUDGET_1591R4.
'''

# Revision 3: the proxy login is not embedded in the code any more. The runtime already
# prefers telegram_config.json "proxy" and the TELEGRAM_PROXY variable over this constant.
PROXY_LINE_RE = re.compile(r'^TELEGRAM_DEFAULT_PROXY = "(?:socks5h?|https?)://[^"\n]*"[ \t]*$', re.M)
NEW_PROXY_LINE = ('TELEGRAM_DEFAULT_PROXY = ""  # ' + PROXY_MARKER
                  + ': set "proxy" in telegram_config.json (or TELEGRAM_PROXY)')
OLD_MAIN_RECONSTRUCT = "    original, output = reconstruct(app, package)\n"
NEW_MAIN_RECONSTRUCT = ("    original, output = reconstruct(app, package)\n"
                        "    ensure_proxy_configured(app)\n")
PROXY_GUARD_SOURCE = '''

def ensure_proxy_configured(app):
    """r3: the code no longer embeds the Telegram proxy; it must be in telegram_config.json."""
    try:
        cfg = json.loads((app/'telegram_config.json').read_text('utf-8'))
    except (OSError, ValueError):
        cfg = {}
    if not str((cfg or {}).get('proxy') or '').strip():
        raise RuntimeError('telegram_config.json has no "proxy". Add "proxy": "socks5h://user:password@host:port" '
                           '(the value that was TELEGRAM_DEFAULT_PROXY in the old code) before installing; '
                           'this build does not embed it and would otherwise reach Telegram without the proxy.')
'''

OLD_PUSH = '''            r, err = telegram_api(
                cfg,
                "sendMessage",
                {
                    "chat_id": chat,
                    "text": str(success_text)[:4000],
                    "disable_web_page_preview": "true",
                },
            )
            if not r:
                print(f"[Telegram] ОШИБКА отдельного SUCCESS push: {err}", flush=True)
'''
NEW_PUSH = '''            # SUCCESS_PUSH_DURABLE_1591R2: the whole text is queued and delivered in
            # confirmed parts by the durable sender; it is never cut to 4000 characters.
            success_text = str(success_text)
            if not success_text.strip():
                continue
            try:
                _io1591.enqueue_notice(globals(), chat, success_text)
                continue
            except Exception as exc:
                print(
                    "[Telegram] SUCCESS push не поставлен в очередь, отправляю напрямую: "
                    f"{_io1591.redact(exc)}",
                    flush=True,
                )
            for piece in _io1591.split_text(success_text):
                r, err = telegram_api(
                    cfg,
                    "sendMessage",
                    {
                        "chat_id": chat,
                        "text": piece,
                        "disable_web_page_preview": "true",
                    },
                )
                if not r:
                    print(f"[Telegram] ОШИБКА отдельного SUCCESS push: {err}", flush=True)
'''

# Version-independent structural hash: fields that are None or [] are omitted, which is
# what ast.dump() started doing by default in Python 3.13. Attributes are never included.
SIGNATURE_SOURCE = '''
def ast_signature(node):
    if isinstance(node, ast.AST):
        fields = []
        for name, value in ast.iter_fields(node):
            if value is None or (isinstance(value, list) and not value):
                continue
            fields.append((name, ast_signature(value)))
        return (type(node).__name__, tuple(fields))
    if isinstance(node, list):
        return tuple(ast_signature(x) for x in node)
    return repr(node)


def handler_hash(node):
    return hashlib.sha256(repr(ast_signature(node)).encode()).hexdigest()
'''
_ns: dict = {"ast": ast, "hashlib": hashlib}
exec(SIGNATURE_SOURCE, _ns)
ast_signature, handler_hash = _ns["ast_signature"], _ns["handler_hash"]

OLD_TEST_HASH = "            actual=hashlib.sha256(ast.dump(function(name),include_attributes=False).encode()).hexdigest()\n"
NEW_TEST_HASH = "            actual=handler_hash(function(name))\n"

OLD_INPUT_CHECK = '''        if digest(raw) != meta['input_sha256']:
            raise RuntimeError(f'{name}: installed source is different; no code changed. Actual SHA256={digest(raw)}')
'''
NEW_INPUT_CHECK = '''        accepted = {meta['input_sha256'], *meta.get('previous_output_sha256', [])}
        if digest(raw) not in accepted:
            raise RuntimeError(f'{name}: installed source is different; no code changed. Actual SHA256={digest(raw)}')
'''
OLD_RECONSTRUCT = '''        lines = raw.decode('utf-8').splitlines(keepends=True)
        for change in reversed(edits[name]):
            lines[change['start']:change['end']] = change['replacement']
        updated = ''.join(lines).encode('utf-8')
        if digest(updated) != meta['output_sha256']:
            raise RuntimeError(f'{name}: reconstruction checksum failed')
        result[name] = updated
'''
NEW_RECONSTRUCT = '''        # r2: the reviewed package copy is installed once the input checksum matched.
        updated = (package/name).read_bytes()
        if digest(updated) != meta['output_sha256']:
            raise RuntimeError(f'{name}: package copy checksum failed')
        result[name] = updated
'''

README_NOTE_R3 = '''

РЕВИЗИЯ 3 (fix_package_1591.py)
Логин и пароль прокси убраны из кода: TELEGRAM_DEFAULT_PROXY = "". Код и раньше
брал прокси сначала из telegram_config.json ("proxy"), затем из переменной
TELEGRAM_PROXY и только потом из константы. Перед установкой добавьте в
/opt/beeline/telegram_config.json ключ "proxy" со старым значением константы;
install.py отказывается продолжать, пока ключа нет. Маркер: PROXY_FROM_CONFIG_1591R3.
Значение из старого кода на сервере:  grep -o 'socks5h://[^"]*' /opt/beeline/test_beeline.py
'''

README_NOTE = '''

РЕВИЗИЯ 2 (fix_package_1591.py)
1. Отдельный SUCCESS push больше не обрезается до 4000 символов: текст целиком
   ставится в durable-очередь и доставляется частями с подтверждением; при
   недоступной очереди отправляется напрямую частями. Маркер в коде:
   SUCCESS_PUSH_DURABLE_1591R2. Редактируемые статусные сообщения (editMessageText)
   по-прежнему ограничены 4000 символами: часть edit-сообщения разделить нельзя.
2. Хэши защищённых обработчиков в test_update.py считаются по структуре AST без
   полей None/[] и не зависят от версии Python. Прежний ast.dump() давал другой
   текст на Python <= 3.12, из-за чего preflight установщика падал.
3. install.py ставит проверенные копии из пакета после совпадения входного хэша;
   edits.json сохранён как описание изменений. Сервер с уже установленной первой
   сборкой 15.91-io обновляется тем же путём.
Проверка после установки:
grep -c SUCCESS_PUSH_DURABLE_1591R2 /opt/beeline/test_beeline.py   # ожидается 1
'''


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def node_range(source: str, node) -> tuple:
    """Character offsets of the whole lines a top-level node occupies."""
    lines = source.splitlines(keepends=True)
    return sum(map(len, lines[:node.lineno - 1])), sum(map(len, lines[:node.end_lineno]))


def only_function(source: str, name: str):
    nodes = [n for n in ast.walk(ast.parse(source)) if isinstance(n, ast.FunctionDef) and n.name == name]
    if len(nodes) != 1:
        raise SystemExit(f"Expected one {name}; found {len(nodes)}. Source unchanged.")
    return nodes[0]


def replace_once(text: str, old: str, new: str, what: str) -> str:
    if text.count(old) != 1:
        raise SystemExit(f"{what}: expected exactly one occurrence, found {text.count(old)}; nothing changed")
    return text.replace(old, new, 1)


def add_edit(edits: list, output_before: str, old_block: str, new_block: str, reflected=None) -> None:
    """Record the new change in edits.json using the ORIGINAL (input) line numbers.

    `reflected` are the edits already applied in output_before (default: all of `edits`);
    edits appended during the same run are not part of output_before and must not shift lines.
    """
    reflected = edits if reflected is None else reflected
    out_lines = output_before.splitlines(keepends=True)
    old_lines = old_block.splitlines(keepends=True)
    starts = [i for i in range(len(out_lines)) if out_lines[i:i + len(old_lines)] == old_lines]
    if len(starts) != 1:
        raise SystemExit("edits.json: SUCCESS push block not unique in the package output")
    out_start = starts[0]
    delta = 0
    for change in sorted(reflected, key=lambda c: c["start"]):
        shift = len(change["replacement"]) - (change["end"] - change["start"])
        if change["start"] + delta + shift <= out_start:
            delta += shift
    in_start = out_start - delta
    for change in edits:
        if change["start"] < in_start + len(old_lines) and in_start < change["end"]:
            raise SystemExit("edits.json: the SUCCESS push block overlaps an existing edit")
    edits.append({"start": in_start, "end": in_start + len(old_lines),
                  "replacement": new_block.splitlines(keepends=True)})
    edits.sort(key=lambda c: c["start"])


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    package = Path(argv[1]).resolve()
    app = package / "test_beeline.py"
    for name in ("test_beeline.py", "server_controller.py", "operator_runtime_io.py", "install.py",
                 "test_update.py", "manifest.json", "edits.json", "SHA256SUMS.txt", "README.txt"):
        if not (package / name).is_file():
            raise SystemExit(f"{package / name}: missing; this is not the extracted 15.91 package")
    source = app.read_text("utf-8")
    if MARKER in source and PROXY_MARKER in source and ASSIST_MARKER in source and ERROR_MARKER in source:
        print("Already revision 5; nothing changed.")
        return 0
    if sha(app) not in ACCEPTED_PACKAGE_SHAS:
        raise SystemExit(f"test_beeline.py SHA256 {sha(app)} is not a reviewed 15.91-io build; nothing changed")
    manifest = json.loads((package / "manifest.json").read_text("utf-8"))
    edits = json.loads((package / "edits.json").read_text("utf-8"))
    reflected = [dict(x) for x in edits["test_beeline.py"]]  # edits already present in `source`
    new_source = source
    test_src = (package / "test_update.py").read_text("utf-8")
    install_src = (package / "install.py").read_text("utf-8")

    if MARKER not in source:
        # 1. SUCCESS push
        new_source = replace_once(new_source, OLD_PUSH, NEW_PUSH, "test_beeline.py SUCCESS push")
        add_edit(edits["test_beeline.py"], source, OLD_PUSH, NEW_PUSH, reflected)

        # 2. Version-independent handler hashes
        test_src = replace_once(test_src, OLD_TEST_HASH, NEW_TEST_HASH, "test_update.py hash line")
        test_src = replace_once(test_src, "\nclass SourceIntegrityTests(unittest.TestCase):\n",
                                "\n" + SIGNATURE_SOURCE + "\n\nclass SourceIntegrityTests(unittest.TestCase):\n",
                                "test_update.py SourceIntegrityTests")

        # 3. Installer uses the package copies
        install_src = replace_once(install_src, OLD_INPUT_CHECK, NEW_INPUT_CHECK, "install.py input check")
        install_src = replace_once(install_src, OLD_RECONSTRUCT, NEW_RECONSTRUCT, "install.py reconstruct")

    if PROXY_MARKER not in source:
        # 4 (r3). Proxy login out of the code; installer insists on telegram_config.json "proxy".
        matches = PROXY_LINE_RE.findall(new_source)
        if len(matches) != 1:
            raise SystemExit(f"TELEGRAM_DEFAULT_PROXY literal: expected one line, found {len(matches)}; nothing changed")
        old_proxy_line = PROXY_LINE_RE.search(new_source).group(0)
        new_source = new_source.replace(old_proxy_line, NEW_PROXY_LINE, 1)
        add_edit(edits["test_beeline.py"], source, old_proxy_line + "\n", NEW_PROXY_LINE + "\n", reflected)
        install_src = replace_once(install_src, OLD_MAIN_RECONSTRUCT, NEW_MAIN_RECONSTRUCT, "install.py main")
        install_src = replace_once(install_src, "\n\ndef main():\n", PROXY_GUARD_SOURCE + "\n\ndef main():\n",
                                   "install.py proxy guard")

    # 5 (r4). Budget for autonomous assist requests.
    if ASSIST_MARKER not in source:
        new_source = replace_once(new_source, OLD_SUCCESS_THROTTLE, NEW_SUCCESS_THROTTLE, "queue_success_assist throttle")
        new_source = replace_once(new_source, OLD_ERROR_THROTTLE, NEW_ERROR_THROTTLE, "queue_error_assist throttle")
        new_source = replace_once(new_source, QUEUE_ERROR_DEF, ASSIST_HELPER + QUEUE_ERROR_DEF, "assist helper insertion")
        add_edit(edits["test_beeline.py"], source, OLD_SUCCESS_THROTTLE, NEW_SUCCESS_THROTTLE, reflected)
        add_edit(edits["test_beeline.py"], source, OLD_ERROR_THROTTLE, NEW_ERROR_THROTTLE, reflected)
        add_edit(edits["test_beeline.py"], source, QUEUE_ERROR_DEF, ASSIST_HELPER + QUEUE_ERROR_DEF, reflected)
    # 6 (r5). registration/error: analyse, report, then close/reopen, retry once, skip.
    if ERROR_MARKER not in source:
        if ASSIST_MARKER not in new_source:
            raise SystemExit("revision 5 needs the revision 4 assist budget; nothing changed")
        # a) runtime: replace tick_error_assist and add the recovery helpers before it
        fn = only_function(new_source, "tick_error_assist")
        a, b = node_range(new_source, fn)
        old_tick = new_source[a:b]
        new_source = new_source[:a] + TICK_ERROR_R5 + new_source[b:]
        add_edit(edits["test_beeline.py"], source, old_tick, TICK_ERROR_R5, reflected)
        # b) AUTO_ERROR_ASSIST task text
        fn = only_function(new_source, "queue_error_assist")
        assigns = [n for n in ast.walk(fn) if isinstance(n, ast.Assign)
                   and any(isinstance(t, ast.Name) and t.id == "text" for t in n.targets)]
        if len(assigns) != 1:
            raise SystemExit("queue_error_assist: text assignment not unambiguous")
        a, b = node_range(new_source, assigns[0])
        old_text = new_source[a:b]
        new_source = new_source[:a] + QUEUE_ERROR_TEXT_R5 + new_source[b:]
        add_edit(edits["test_beeline.py"], source, old_text, QUEUE_ERROR_TEXT_R5, reflected)
        # c) ERROR SUPERVISOR block of the agent system prompt
        a = new_source.index("ERROR SUPERVISOR:\n")
        b = new_source.index("Правила действий:\n", a)
        old_block = new_source[a:b]
        new_source = new_source[:a] + AGENT_ERROR_BLOCK_R5 + new_source[b:]
        add_edit(edits["test_beeline.py"], source, old_block, AGENT_ERROR_BLOCK_R5, reflected)
        # d) the priority mission constant
        missions = [n for n in ast.parse(new_source).body if isinstance(n, ast.Assign)
                    and any(isinstance(t, ast.Name) and t.id == "OPERATOR_MISSION_1586" for t in n.targets)]
        if len(missions) != 1:
            raise SystemExit("OPERATOR_MISSION_1586 not unambiguous")
        a, b = node_range(new_source, missions[0])
        old_mission = new_source[a:b]
        if not old_mission.rstrip("\n").endswith('"""'):
            raise SystemExit("OPERATOR_MISSION_1586 is not a triple-quoted literal")
        new_mission = old_mission.rstrip("\n")[:-3] + MISSION_RULE_R5 + '"""\n'
        new_source = new_source[:a] + new_mission + new_source[b:]
        add_edit(edits["test_beeline.py"], source, old_mission, new_mission, reflected)

    compile(new_source, "test_beeline.py", "exec")
    compile(test_src, "test_update.py", "exec")
    compile(install_src, "install.py", "exec")

    # 4. Manifest and checksums
    tree = ast.parse(new_source)
    for name in manifest["preserved_handlers"]:
        nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name]
        if len(nodes) != 1:
            raise SystemExit(f"preserved handler {name}: found {len(nodes)}")
        manifest["preserved_ast_sha256"][name] = handler_hash(nodes[0])
    old_hashes = {n: handler_hash(next(x for x in ast.parse(source).body
                                        if isinstance(x, ast.FunctionDef) and x.name == n))
                  for n in manifest["preserved_handlers"]}
    changed = {n for n in old_hashes if old_hashes[n] != manifest["preserved_ast_sha256"][n]}
    if changed - RESIGNED_HANDLERS:
        raise SystemExit(f"Preserved handlers changed unexpectedly: {sorted(changed - RESIGNED_HANDLERS)}")
    # A server that already runs the first 15.91 build is upgraded in place as well.
    manifest["files"]["test_beeline.py"]["previous_output_sha256"] = sorted(ACCEPTED_PACKAGE_SHAS)
    manifest["files"]["test_beeline.py"]["output_sha256"] = hashlib.sha256(new_source.encode("utf-8")).hexdigest()
    manifest["revision"] = 5

    app.write_text(new_source, "utf-8")
    (package / "test_update.py").write_text(test_src, "utf-8")
    (package / "install.py").write_text(install_src, "utf-8")
    (package / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), "utf-8")
    (package / "edits.json").write_text(json.dumps(edits, ensure_ascii=False, indent=2), "utf-8")
    readme = package / "README.txt"
    for heading, note in (("РЕВИЗИЯ 2", README_NOTE), ("РЕВИЗИЯ 3", README_NOTE_R3), ("РЕВИЗИЯ 4", README_NOTE_R4),
                          ("РЕВИЗИЯ 5", README_NOTE_R5)):
        if heading not in readme.read_text("utf-8"):
            readme.write_text(readme.read_text("utf-8").rstrip("\n") + note, "utf-8")

    # Prove the package's own suite passes here, then record it.
    run = subprocess.run([sys.executable, "-m", "unittest", "-v", "test_update"], cwd=package,
                         text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=300)
    (package / "test_results.txt").write_text(run.stdout, "utf-8")
    if run.returncode:
        print(run.stdout)
        raise SystemExit("Package tests failed after the fix; review test_results.txt")
    ran = next((line for line in run.stdout.splitlines() if line.startswith("Ran ")), "")
    verification = json.loads((package / "verification.json").read_text("utf-8"))
    verification.update({"python": sys.version, "revision": 5, "result": "OK",
                         "tests": int(ran.split()[1]) if ran else None,
                         "exact_input_sha256": manifest["files"]})
    (package / "verification.json").write_text(json.dumps(verification, ensure_ascii=False, indent=2), "utf-8")

    sums = [f"{sha(package / name)}  {name}" for name in
            ("test_beeline.py", "server_controller.py", "operator_runtime_io.py", "install.py", "test_update.py",
             "manifest.json", "edits.json", "README.txt", "verification.json", "test_results.txt",
             "install_preflight_results.txt") if (package / name).is_file()]
    (package / "SHA256SUMS.txt").write_text("\n".join(sums) + "\n", "utf-8")
    for line in ("__pycache__",):
        for cache in package.glob(line):
            for f in cache.iterdir():
                f.unlink()
            cache.rmdir()
    print(ran + " — OK")
    print("Revision 5 applied to", package)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

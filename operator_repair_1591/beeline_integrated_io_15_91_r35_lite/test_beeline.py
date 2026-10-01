"""Тест заполнения корзины. Запуск: python test_beeline.py
Установка: python -m pip install playwright
           python -m playwright install chromium
"""
from multiprocessing import Manager
import re
import ast
import hashlib
import traceback
import sys
import os
import secrets
import multiprocessing as mp
import socket
import subprocess
import tempfile
import time
import urllib.request
import urllib.error
import urllib.parse
import urllib.parse
import json
import shutil
from urllib.parse import urlsplit, urlunsplit, parse_qs
from console_wait import console_input
from local_matcher import try_local_captcha, configure_matcher_runtime
from time import monotonic
from pathlib import Path
import operator_runtime_io as _io1591

IO_BUILD_VERSION = "15.91-io"
from batch_support import load_clients, wait_confirmation, save_result


RUNTIME_LOG_DIR = Path(__file__).resolve().parent / "runtime_logs"
RUNTIME_CONSOLE_FILE = RUNTIME_LOG_DIR / "console.log"
RUNTIME_SESSION_MARKER_V1584 = f"=== CURRENT SERVICE SESSION START {time.time():.3f} ==="


class _RuntimeConsoleTee:
    """Mirror stdout/stderr to the real console and a shared runtime log."""

    def __init__(self, original, stream_name):
        self.original = original
        self.stream_name = stream_name
        self._buffer = ""

    def write(self, data):
        text = str(data)
        try:
            self.original.write(text)
        except Exception:
            pass

        self._buffer += text
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            self._append_line(line)
        return len(text)

    def flush(self):
        try:
            self.original.flush()
        except Exception:
            pass
        if self._buffer:
            self._append_line(self._buffer)
            self._buffer = ""

    def isatty(self):
        try:
            return self.original.isatty()
        except Exception:
            return False

    @property
    def encoding(self):
        return getattr(self.original, "encoding", "utf-8")

    def fileno(self):
        return self.original.fileno()

    def _append_line(self, line):
        try:
            RUNTIME_LOG_DIR.mkdir(parents=True, exist_ok=True)
            proc_name = mp.current_process().name
            prefix = (
                f"[{time.strftime('%Y-%m-%d %H:%M:%S')} "
                f"pid={os.getpid()} proc={proc_name} {self.stream_name}] "
            )
            # Open-per-line makes writes from spawned processes independent.
            with RUNTIME_CONSOLE_FILE.open("a", encoding="utf-8") as f:
                f.write(prefix + line + "\n")
        except Exception:
            pass


def _install_runtime_console_capture():
    if not isinstance(sys.stdout, _RuntimeConsoleTee):
        sys.stdout = _RuntimeConsoleTee(sys.stdout, "stdout")
    if not isinstance(sys.stderr, _RuntimeConsoleTee):
        sys.stderr = _RuntimeConsoleTee(sys.stderr, "stderr")


def _runtime_console_tail(max_lines=180, max_chars=32000):
    """Return actual recent console output visible to DeepSeek chat/agent."""
    try:
        if not RUNTIME_CONSOLE_FILE.exists():
            return "(runtime console log пока пуст)"
        lines = RUNTIME_CONSOLE_FILE.read_text(
            encoding="utf-8", errors="replace"
        ).splitlines()
        # SESSION_FILTER_1585
        _marker1585 = "=== CURRENT SERVICE SESSION START "
        _last1585 = -1
        for _i1585 in range(len(lines) - 1, -1, -1):
            if _marker1585 in lines[_i1585]:
                _last1585 = _i1585
                break
        if _last1585 < 0:
            return "(граница текущей сессии отсутствует; исторический лог не подставлен)"
        lines = lines[_last1585:]
        text = "\n".join(lines[-max(1, int(max_lines)):])
        if len(text) > max_chars:
            text = text[-max_chars:]
        return text or "(runtime console log пока пуст)"
    except Exception as exc:
        return f"(не удалось прочитать runtime console: {type(exc).__name__}: {exc})"


_install_runtime_console_capture()



class Diagnostics:
    """Минимальная встроенная диагностика без внешнего diagnostics.py."""

    def __init__(self, page, browser_name, browser_version):
        self.page = page
        self.browser_name = browser_name
        self.browser_version = browser_version
        stamp = time.strftime("%Y%m%d_%H%M%S")
        millis = int((time.time() % 1) * 1_000_000)
        self.path = Path.cwd() / f"diagnostic_{stamp}_{millis:06d}.txt"
        self._write_raw({
            "event": "diagnostic_started",
            "time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "browser": browser_name,
            "browser_version": browser_version,
            "url": self._safe_url(),
        })

    def _safe_url(self):
        try:
            return self.page.url
        except Exception:
            return None

    def _write_raw(self, obj):
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(obj, ensure_ascii=False, default=str) + "\n")
        except Exception:
            pass

    def write(self, event, **data):
        self._write_raw({
            "time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "event": event,
            "url": self._safe_url(),
            **data,
        })

    def snapshot(self, name):
        """Текстовый snapshot; визуальный снимок делает BLACKBOX при проблемах."""
        snap = {
            "time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "event": "snapshot",
            "name": name,
            "url": self._safe_url(),
        }
        try:
            if not self.page.is_closed():
                snap["title"] = self.page.title()
                snap["ready_state"] = self.page.evaluate("document.readyState")
        except Exception as exc:
            snap["snapshot_error"] = f"{type(exc).__name__}: {exc}"
        self._write_raw(snap)


DIAGNOSTICS_DIR = Path(__file__).resolve().parent / "diagnostics"

DIAGNOSTIC_SESSIONS_TO_KEEP = 40  # FINAL_PAGE_1591R23: restarts every 20 min made 5 sessions a few hours


def create_diagnostic_session():
    DIAGNOSTICS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    session_dir = DIAGNOSTICS_DIR / f"session_{stamp}"
    session_dir.mkdir(parents=True, exist_ok=True)
    (session_dir / "blackbox").mkdir(parents=True, exist_ok=True)

    sessions = sorted(
        [p for p in DIAGNOSTICS_DIR.glob("session_*") if p.is_dir()],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for old in sessions[DIAGNOSTIC_SESSIONS_TO_KEEP:]:
        shutil.rmtree(old, ignore_errors=True)
    return session_dir



def make_diagnostics(page, browser_name, browser_version, output_dir=None):
    """Создаёт диагностический файл внутри папки конкретной вкладки/сессии."""
    target = Path(output_dir) if output_dir else DIAGNOSTICS_DIR
    target.mkdir(parents=True, exist_ok=True)
    old_cwd = Path.cwd()
    try:
        os.chdir(target)
        return Diagnostics(page, browser_name, browser_version)
    finally:
        os.chdir(old_cwd)


from playwright.sync_api import sync_playwright, expect, TimeoutError as PlaywrightTimeoutError, Error as PlaywrightError

REGION_HOST = "saratov.beeline.ru"
START_URL = f"https://{REGION_HOST}/basket/"
TARIFF_NAME = "подписка bee START"
TELEGRAM_CONFIG_FILE = Path(__file__).resolve().parent / "telegram_config.json"
ROW_START_STALL_SECONDS = 120
DEFAULT_EXTERNAL_STALL_SECONDS = 90
PROTECTED_MATCHER_STALL_SECONDS = 75
FAST_RECOVERY_GRACE_SECONDS = 7

BLACKBOX_ROOT = Path(__file__).resolve().parent / "diagnostics" / "blackbox"
BLACKBOX_MAX_CASES = 20


def _safe_name(value):
    return re.sub(r"[^0-9A-Za-zА-Яа-я._-]+", "_", str(value))[:80]


def _prune_blackbox():
    """Храним только последние BLACKBOX_MAX_CASES проблемных снимков."""
    try:
        BLACKBOX_ROOT.mkdir(parents=True, exist_ok=True)
        cases = sorted(
            [p for p in BLACKBOX_ROOT.iterdir() if p.is_dir()],
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        for old in cases[BLACKBOX_MAX_CASES:]:
            shutil.rmtree(old, ignore_errors=True)
    except Exception:
        pass


def capture_blackbox(worker, reason, exc=None):
    """Сохраняет визуальное и техническое состояние проблемной вкладки."""
    try:
        session_dir = worker.get("diagnostic_session_dir")
        blackbox_root = (
            Path(session_dir) / "blackbox"
            if session_dir else BLACKBOX_ROOT
        )
        blackbox_root.mkdir(parents=True, exist_ok=True)
        row_no, active, second = row_parts(worker.get("row"))
        stamp = time.strftime("%Y%m%d_%H%M%S")
        millis = int((time.time() % 1) * 1000)
        case = blackbox_root / (
            f"{stamp}_{millis:03d}_tab{worker.get('id','?')}_"
            f"row{_safe_name(row_no)}_{_safe_name(reason)}"
        )
        case.mkdir(parents=True, exist_ok=True)

        page = worker.get("page")
        meta = {
            "time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "tab": worker.get("id"),
            "reason": reason,
            "phase": worker.get("phase"),
            "row_no": row_no,
            "row": [active, second],
            "confirm_attempt": worker.get("confirm_attempt"),
            "last_progress_label": worker.get("last_progress_label"),
            "last_progress_age_seconds": round(
                monotonic() - worker.get("last_progress_at", monotonic()), 2
            ),
            "url": None,
            "title": None,
            "exception_type": type(exc).__name__ if exc else None,
            "exception": str(exc) if exc else None,
        }

        if page is not None and not page.is_closed():
            try:
                meta["url"] = page.url
            except Exception:
                pass
            try:
                meta["title"] = page.title()
            except Exception:
                pass
            try:
                page.screenshot(
                    path=str(case / "screen.png"),
                    full_page=True,
                    timeout=10000,
                )
            except Exception as shot_exc:
                meta["screenshot_error"] = f"{type(shot_exc).__name__}: {shot_exc}"
            try:
                (case / "page.html").write_text(
                    page.content(), encoding="utf-8", errors="replace"
                )
            except Exception as html_exc:
                meta["html_error"] = f"{type(html_exc).__name__}: {html_exc}"
            try:
                state = page.evaluate("""() => ({
                    readyState: document.readyState,
                    activeElement: document.activeElement ? {
                        tag: document.activeElement.tagName,
                        name: document.activeElement.getAttribute('name'),
                        type: document.activeElement.getAttribute('type'),
                        valueLength: (document.activeElement.value || '').length
                    } : null,
                    visibleButtons: [...document.querySelectorAll('button')]
                        .filter(x => {
                            const s=getComputedStyle(x), r=x.getBoundingClientRect();
                            return s.display!=='none' && s.visibility!=='hidden' &&
                                   r.width>0 && r.height>0;
                        })
                        .slice(0,40)
                        .map(x => ({
                            text:(x.innerText||'').trim().slice(0,120),
                            disabled:x.disabled,
                            ariaDisabled:x.getAttribute('aria-disabled'),
                            dataDisabled:x.getAttribute('data-disabled')
                        })),
                    visibleInputs: [...document.querySelectorAll('input')]
                        .filter(x => {
                            const s=getComputedStyle(x), r=x.getBoundingClientRect();
                            return s.display!=='none' && s.visibility!=='hidden' &&
                                   r.width>0 && r.height>0;
                        })
                        .slice(0,30)
                        .map(x => ({
                            name:x.name, type:x.type,
                            valueLength:(x.value||'').length,
                            disabled:x.disabled
                        }))
                })""")
                (case / "page_state.json").write_text(
                    json.dumps(state, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
            except Exception as state_exc:
                meta["state_error"] = f"{type(state_exc).__name__}: {state_exc}"

        if exc is not None:
            try:
                (case / "traceback.txt").write_text(
                    "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)),
                    encoding="utf-8",
                    errors="replace",
                )
            except Exception:
                pass

        (case / "meta.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(
            f"[BLACKBOX] Вкладка {worker.get('id')} — сохранён снимок: {case}",
            flush=True,
        )
        _prune_blackbox()
        return str(case)
    except Exception as bb_exc:
        print(
            f"[BLACKBOX] Не удалось сохранить снимок: "
            f"{type(bb_exc).__name__}: {bb_exc}",
            flush=True,
        )
        return None


def row_parts(row):
    if isinstance(row, dict):
        return row.get("row_no","?"), str(row.get("active_digits",row.get("number",""))), str(row.get("second_value",row.get("value","")))
    if isinstance(row, (tuple,list)):
        v=list(row)+["","",""]
        return v[0], str(v[1]), str(v[2])
    return "?", str(row or ""), ""


def install_page_activity_tracker(page, worker):
    """Обновляет heartbeat при реальной сетевой/навигационной активности страницы."""
    def touch(kind):
        worker["last_page_activity_at"] = monotonic()
        worker["last_page_activity_kind"] = kind
        hb = worker.get("heartbeat")
        if hb is not None:
            try:
                info = dict(hb.get(str(worker["id"])) or {})
                info["activity_time"] = worker["last_page_activity_at"]
                info["activity_kind"] = kind
                info["page_url"] = page.url if not page.is_closed() else ""
                info["window_name"] = _read_page_window_name(page)
                info["generation"] = int(worker.get("generation") or 1)
                info["worker_pid"] = os.getpid()
                hb[str(worker["id"])] = info
            except Exception:
                pass

    try:
        page.on("request", lambda _: touch("request"))
        page.on("response", lambda _: touch("response"))
        page.on("domcontentloaded", lambda: touch("domcontentloaded"))
        page.on("load", lambda: touch("load"))
        page.on("framenavigated", lambda _: touch("navigation"))
    except Exception:
        pass
    touch("tracker_installed")



def set_tab_status(worker, icon, note):
    sm=worker.get("status_map")
    if sm is None: return
    n,a,b=row_parts(worker.get("row"))
    total = worker.get("total_rows")
    counter = f"{n}/{total}" if total else str(n)
    lines=[
        f"{icon} Вкладка {worker['id']}",
        f"Строка: {counter}",
        f"Данные: {a} | {b}",
        f"Этап: {worker.get('phase','?')}",
    ]
    if worker.get("confirm_attempt"): lines.append(f"Подтверждение: {worker['confirm_attempt']}/6")
    if note: lines.append(note)
    try: sm[str(worker["id"])]={"text":"\n".join(lines),"time":time.time()}
    except Exception: pass

def load_telegram_config():
    try: return json.loads(TELEGRAM_CONFIG_FILE.read_text(encoding="utf-8"))
    except Exception: return {}

TELEGRAM_DEFAULT_PROXY = ""  # PROXY_FROM_CONFIG_1591R3: set "proxy" in telegram_config.json (or TELEGRAM_PROXY)


TELEGRAM_DIRECT_PROXY_VALUES = {"direct", "none", "off", "no", "-"}  # PROXY_DIRECT_1591R20: server outside RU


def telegram_http_proxies(cfg):
    # Config/env override wins. This keeps all Telegram consumers on one transport.
    proxy = str(
        (cfg or {}).get("proxy")
        or os.environ.get("TELEGRAM_PROXY")
        or TELEGRAM_DEFAULT_PROXY
        or ""
    ).strip()
    if not proxy or proxy.lower() in TELEGRAM_DIRECT_PROXY_VALUES:  # PROXY_DIRECT_1591R20
        return None
    if "://" not in proxy:
        proxy = "socks5h://" + proxy
    elif proxy.lower().startswith("socks5://"):
        proxy = "socks5h://" + proxy[len("socks5://"):]
    return {"http": proxy, "https": proxy}


def telegram_api(cfg, method, payload):
    token = str(cfg.get("token", "")).strip()
    if not token:
        return None, "В telegram_config.json отсутствует token"

    proxies = telegram_http_proxies(cfg)

    try:
        import requests
    except ImportError:
        return None, (
            "Не установлен requests. Выполни: "
            "python -m pip install \"requests[socks]\""
        )

    try:
        r = requests.post(
            f"https://api.telegram.org/bot{token}/{method}",
            data=payload,
            proxies=proxies,
            timeout=15,
        )
        try:
            obj = r.json()
        except Exception:
            return None, f"HTTP {r.status_code}: {r.text[:300]}"
        if r.ok and obj.get("ok"):
            return obj, None
        return None, _io1591.TelegramFailure(
            f"Telegram API: {obj.get('error_code', r.status_code)} {obj.get('description', '')}",
            code=obj.get("error_code", r.status_code),
            retry_after=(obj.get("parameters") or {}).get("retry_after"),
        )
    except Exception as exc:
        return None, _io1591.TelegramFailure(f"{type(exc).__name__}: {exc}")

# TG_RATE_1591R27
TG_MIN_CALL_GAP_1591R27 = 1.5
TG_STATUS_MIN_EDIT_GAP_1591R27 = 6.0


def _tg_status_file_1591r27():
    return TELEGRAM_CONFIG_FILE.with_name("telegram_status_messages.json")


def _tg_call_1591r27(cfg, method, payload, state):
    """One rate-limited Bot API call of the status logger: a global gap between calls and a
    full stop for retry_after when Telegram answers 429 (retrying every second grew the ban)."""
    now = time.time()
    if now < float(state.get("pause_until") or 0):
        return None, "paused"
    gap = TG_MIN_CALL_GAP_1591R27 - (now - float(state.get("last_call") or 0))
    if gap > 0:
        time.sleep(gap)
    state["last_call"] = time.time()
    r, err = telegram_api(cfg, method, payload)
    retry_after = getattr(err, "retry_after", None)
    if isinstance(retry_after, (int, float)) and retry_after > 0:
        state["pause_until"] = time.time() + float(retry_after) + 1
        print(f"[Telegram] 429: Telegram просит паузу {int(retry_after)} с — статусы не трогаю до её конца.", flush=True)
    return r, err


def _tg_status_messages_load_1591r27(chat):
    try:
        data = json.loads(_tg_status_file_1591r27().read_text("utf-8"))
        if str(data.get("chat")) == str(chat):
            return {int(k): int(v) for k, v in (data.get("mids") or {}).items()}
    except Exception:
        pass
    return {}


def _tg_status_messages_save_1591r27(chat, mids):
    try:
        _tg_status_file_1591r27().write_text(
            json.dumps({"chat": str(chat), "mids": {str(k): v for k, v in mids.items()}}), "utf-8"
        )
    except Exception:
        pass


def _tg_status_sync_1591r27(cfg, chat, status_map, mids, last, state, edited_at):
    """Create the missing status messages and push the changed texts, within the limits."""
    changed = False
    for i in range(1, TAB_COUNT + 1):
        if i in mids:
            continue
        r, err = _tg_call_1591r27(
            cfg, "sendMessage",
            {"chat_id": chat, "text": f"⏳ Вкладка {i}\nСтатус: запуск...", "disable_web_page_preview": "true"},
            state,
        )
        if r:
            mids[i] = r["result"]["message_id"]
            last[i] = ""
            changed = True
            print(f"[Telegram] Сообщение вкладки {i} создано.", flush=True)
        else:
            if err != "paused":
                print(f"[Telegram] ОШИБКА отправки вкладки {i}: {err}", flush=True)
            break
    if changed:
        _tg_status_messages_save_1591r27(chat, mids)
    now = time.time()
    for i, mid in list(mids.items()):
        info = status_map.get(str(i))
        t = str((info or {}).get("text", ""))
        if not t or t == last.get(i) or now - float(edited_at.get(i) or 0) < TG_STATUS_MIN_EDIT_GAP_1591R27:
            continue
        r, err = _tg_call_1591r27(
            cfg, "editMessageText",
            {"chat_id": chat, "message_id": mid, "text": t[:4000], "disable_web_page_preview": "true"},
            state,
        )
        edited_at[i] = time.time()
        if r:
            last[i] = t
            continue
        if err == "paused":
            break
        low = str(err).lower()
        if "message is not modified" in low:
            last[i] = t
        elif "not found" in low or "can't be edited" in low or "message_id_invalid" in low:
            mids.pop(i, None)
            _tg_status_messages_save_1591r27(chat, mids)
            print(f"[Telegram] Сообщение вкладки {i} исчезло — создам новое.", flush=True)
        else:
            print(f"[Telegram] ОШИБКА обновления вкладки {i}: {err}", flush=True)


def telegram_logger_process(status_map, success_queue, stop_event):
    cfg = load_telegram_config()
    chat = str(cfg.get("chat_id", "")).strip()
    mids, last = {}, {}
    state, edited_at = {"pause_until": 0.0, "last_call": 0.0}, {}  # TG_RATE_1591R27

    print("[Telegram] Логгер запущен.", flush=True)
    if not chat:
        print("[Telegram] ОШИБКА: в telegram_config.json отсутствует chat_id.", flush=True)
        return

    test, err = telegram_api(cfg, "getMe", {})
    if not test:
        print(f"[Telegram] ОШИБКА SOCKS5/getMe: {err}", flush=True)
        print("[Telegram] Основной сценарий продолжает работу без Telegram.", flush=True)
        return
    bot_name = (test.get("result") or {}).get("username", "?")
    print(f"[Telegram] SOCKS5 подключён. Бот: @{bot_name}", flush=True)

    # TG_RATE_1591R27: reuse the status messages of the previous run instead of four new ones
    # per restart; each is verified by an edit and recreated only when Telegram says it is gone.
    for i, mid in _tg_status_messages_load_1591r27(chat).items():
        r, err = _tg_call_1591r27(
            cfg, "editMessageText",
            {"chat_id": chat, "message_id": mid, "text": f"⏳ Вкладка {i}\nСтатус: перезапуск...",
             "disable_web_page_preview": "true"},
            state,
        )
        if r or err == "paused" or "not modified" in str(err or "").lower():
            mids[i] = mid
            last[i] = ""
    _tg_status_sync_1591r27(cfg, chat, status_map, mids, last, state, edited_at)
    if not mids:
        print(
            "[Telegram] Статусные сообщения пока не созданы (лимит Telegram) — попробую позже; "
            "основной сценарий работает.",
            flush=True,
        )

    while not stop_event.is_set():
        # Успехи отправляются ОТДЕЛЬНЫМИ сообщениями и никогда не редактируются.
        while True:
            try:
                success_text = success_queue.get_nowait()
            except Exception:
                break
            # SUCCESS_PUSH_DURABLE_1591R2: the whole text is queued and delivered in
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

        _tg_status_sync_1591r27(cfg, chat, status_map, mids, last, state, edited_at)  # TG_RATE_1591R27
        time.sleep(1)


DEEPSEEK_CONFIG_FILE = Path(__file__).resolve().parent / "deepseek_config.json"
PROJECT_RULES_FILE = Path(__file__).resolve().parent / "PROJECT_RULES.md"
AI_MEMORY_FILE = Path(__file__).resolve().parent / "ai_observer_memory.jsonl"
AI_CHAT_MEMORY_FILE = Path(__file__).resolve().parent / "ai_chat_memory.jsonl"

AI_OBSERVER_INTERVAL = None
AI_POLL_LOCK_FILE = Path(__file__).resolve().parent / ".deepseek_telegram_poll.lock"

AI_TELEGRAM_DB = Path(__file__).resolve().parent / "ai_telegram_queue.sqlite3"


def _ai_db_connect():
    import sqlite3
    conn = sqlite3.connect(str(AI_TELEGRAM_DB), timeout=30)
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def _ai_message_lane(body):
    low = str(body or "").lower().strip()
    if low in {"ок", "да", "применить", "apply", "откат", "откатить", "rollback"}:
        return "dev"
    code_triggers = (
        "фикс", "исправь", "почини", "сделай фикс", "сделай обновление",
        "обнови код", "измени код", "добавь", "доработ", "передел",
        "рефактор", "убери из кода", "замени в коде", "патч",
    )
    if any(x in low for x in code_triggers):
        return "dev"
    if str(os.environ.get("TG_EXTERNAL_CONTROLLER", "")).strip() == "1" and not _operator_needs_tools(body):
        return "chat"
    return "fast"


def _ai_message_priority(body):
    low = str(body or "").lower()
    if any(x in low for x in ("срочно", "немедленно", "прямо сейчас", "!!!")):
        return 100
    if any(x in low for x in (
        "перезапусти", "рестарт", "restart", "восстанов",
        "закрой вклад", "перезагрузи", "reload",
    )):
        return 70
    if any(x in low for x in (
        "ошиб", "завис", "не работает", "проверь", "глянь", "посмотри",
    )):
        return 40
    return 10


def _ai_db_init():
    conn = _ai_db_connect()
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS inbox (
                update_id INTEGER PRIMARY KEY,
                chat_id TEXT NOT NULL,
                body TEXT NOT NULL,
                received_at REAL NOT NULL,
                attempts INTEGER NOT NULL DEFAULT 0,
                next_attempt_at REAL NOT NULL DEFAULT 0,
                last_error TEXT,
                done_at REAL,
                lane TEXT NOT NULL DEFAULT 'fast',
                priority INTEGER NOT NULL DEFAULT 10,
                claimed_by TEXT,
                claim_until REAL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS outbox (
                update_id INTEGER PRIMARY KEY,
                chat_id TEXT NOT NULL,
                body TEXT NOT NULL,
                created_at REAL NOT NULL,
                attempts INTEGER NOT NULL DEFAULT 0,
                next_attempt_at REAL NOT NULL DEFAULT 0,
                last_error TEXT,
                sent_at REAL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS effects (
                effect_key TEXT PRIMARY KEY,
                update_id INTEGER NOT NULL,
                tool TEXT NOT NULL,
                args_json TEXT NOT NULL,
                started_at REAL NOT NULL,
                completed_at REAL,
                result_json TEXT
            )
        """)

        cols = {str(row[1]) for row in conn.execute("PRAGMA table_info(inbox)").fetchall()}
        if "lane" not in cols:
            conn.execute("ALTER TABLE inbox ADD COLUMN lane TEXT NOT NULL DEFAULT 'fast'")
        if "priority" not in cols:
            conn.execute("ALTER TABLE inbox ADD COLUMN priority INTEGER NOT NULL DEFAULT 10")
        if "claimed_by" not in cols:
            conn.execute("ALTER TABLE inbox ADD COLUMN claimed_by TEXT")
        if "claim_until" not in cols:
            conn.execute("ALTER TABLE inbox ADD COLUMN claim_until REAL")

        rows = conn.execute(
            "SELECT update_id, body FROM inbox WHERE done_at IS NULL AND update_id > 0 "
            "AND (claimed_by IS NULL OR claim_until < ?)",
            (time.time(),),
        ).fetchall()
        for update_id, body in rows:
            conn.execute(
                "UPDATE inbox SET lane=?, priority=? WHERE update_id=?",
                (_ai_message_lane(body), _ai_message_priority(body), int(update_id)),
            )

        # Never clear leases belonging to a still-running AI consumer.
        conn.commit()
    finally:
        conn.close()



def _ai_db_offset():
    with _ai_db_connect() as conn:
        row = conn.execute(
            "SELECT value FROM meta WHERE key='telegram_offset'"
        ).fetchone()
        try:
            return int(row[0]) if row else 0
        except Exception:
            return 0


def _ai_db_store_telegram_update(update, allowed_chat):
    """Atomically store a Telegram message and advance the durable offset."""
    update_id = int(update.get("update_id", 0))
    msg = update.get("message") or {}
    chat_id = str((msg.get("chat") or {}).get("id") or "")
    body = str(msg.get("text") or "").strip()

    conn = _ai_db_connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        if update_id and chat_id == str(allowed_chat) and body:
            lane = _ai_message_lane(body)
            priority = _ai_message_priority(body)
            conn.execute(
                """INSERT OR IGNORE INTO inbox
                   (update_id, chat_id, body, received_at, next_attempt_at,
                    lane, priority)
                   VALUES (?, ?, ?, ?, 0, ?, ?)""",
                (update_id, chat_id, body, time.time(), lane, priority),
            )

        # Offset changes in THE SAME transaction as the inbox INSERT.
        # A crash can therefore cause a harmless Telegram redelivery, but can
        # never acknowledge an update without first persisting its message.
        if update_id:
            conn.execute(
                """INSERT INTO meta(key,value) VALUES('telegram_offset',?)
                   ON CONFLICT(key) DO UPDATE SET value=excluded.value""",
                (str(update_id + 1),),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()




def _ai_db_enqueue_internal(body, lane="fast", priority=100):
    """Queue an autonomous Operator task without pretending it came from Telegram."""
    cfg = load_telegram_config()
    chat_id = str(cfg.get("chat_id", "")).strip()
    if not chat_id:
        return None

    # Negative IDs cannot collide with normal positive Telegram update_ids.
    update_id = -int(time.time_ns())
    conn = _ai_db_connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            """INSERT INTO inbox
               (update_id, chat_id, body, received_at, next_attempt_at,
                lane, priority)
               VALUES (?, ?, ?, ?, 0, ?, ?)""",
            (
                update_id,
                chat_id,
                str(body),
                time.time(),
                str(lane),
                int(priority),
            ),
        )
        conn.commit()
        return update_id
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# AUTO_ASSIST_BUDGET_1591R4
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


def queue_error_assist(worker, reason, force=False):
    """Analyze /registration/error before any retry/recovery decision."""
    if not _auto_assist_allowed(worker, "ERROR", force):
        return False

    tab_id = int(worker.get("id") or 0)
    url = ""
    try:
        url = worker.get("page").url
    except Exception:
        pass

    text = (
        f"[AUTO_ERROR_ASSIST TAB {tab_id}] "
        "После mobile-id-auth открылась /registration/error. Это НЕ success. "
        "Сначала автономно проанализируй текущую physical-вкладку: DOM, видимый текст "
        "ошибки, DevTools console и network, последние запросы/ответы и состояние формы. "
        "Определи конкретную причину и, если это безопасно, попробуй исправить её на этой "
        "странице. Затем ОБЯЗАТЕЛЬНО отправь мини-отчёт: причина, что проверил, что "
        "попробовал, результат, URL. Сразу после твоего отчёта runtime автоматически, без "
        "отдельного подтверждения, закроет эту error-вкладку, откроет новую и пропустит строку без повтора. "
        "Worker при этом не теряется. "
        "Сам вкладку не закрывай: это сделает runtime после отчёта. "
        f"Причина вызова: {reason}. URL: {url}"
    )
    try:
        _ai_db_enqueue_internal(text, lane="fast", priority=125)
        print(
            f"[AI AUTO] TAB {tab_id}: ERROR_ASSIST поставлен в очередь: {reason}",
            flush=True,
        )
        return True
    except Exception as exc:
        print(
            f"[AI AUTO] TAB {tab_id}: ERROR_ASSIST queue failed: "
            f"{type(exc).__name__}: {exc}",
            flush=True,
        )
        return False


def queue_success_assist(worker, reason, force=False):
    """Ask DeepSeek to inspect/help a confirmed post-auth page.

    Rate limited so a stubborn form cannot create an AI-request storm.
    """
    if not _auto_assist_allowed(worker, "SUCCESS", force):
        return False
    tab_id = int(worker.get("id") or 0)
    url = ""
    try:
        url = worker.get("page").url
    except Exception:
        pass

    text = (
        f"[AUTO_SUCCESS_ASSIST TAB {tab_id}] "
        "Это твоя главная автономная обязанность после успешного mobile-id подтверждения. "
        "Работай БЕЗ участия пользователя. СНАЧАЛА наблюдай текущую physical-вкладку: "
        "прочитай DOM/видимые ошибки/состояние кнопок и DevTools console/network. "
        "Не вмешивайся, пока сайт сам нормально продвигается. "
        "Если прогресс остановился или форма невалидна — сам найди причину и исправь её: "
        "заполни все реально отсутствующие обязательные поля, выбери корректные autocomplete "
        "подсказки, проверь город/область/адрес и остальные поля. Уже корректно заполненные "
        "значения не перезаписывай. Для текущего сценария город при отсутствии — Саратов, "
        "область при отсутствии — Саратовская область. "
        "Затем правильно заполни поле подписи, дождись активной кнопки и нажми "
        "«Подписать договор». После клика снова наблюдай DOM/console/network и убедись, "
        "что подписание действительно завершилось либо точно определи оставшуюся ошибку. "
        "ЖЁСТКО ЗАПРЕЩЕНО на SUCCESS GUARD: close, restart worker, reload, navigate, "
        "back/forward и любое действие, способное потерять успешную страницу. "
        "В конце ОБЯЗАТЕЛЬНО отправь пользователю короткий мини-отчёт: что было не так; "
        "что ты изменил; какие значения поставил; стала ли кнопка активна; нажал ли её; "
        "чем закончилось подписание; на каком URL/экране осталась вкладка. "
        "Пример формата: «Не был указан город, поэтому подтверждение договора не проходило. "
        "Поставил город — Саратов. Кнопка стала активна, нажал “Подписать договор”. "
        "Подписание прошло успешно. Вкладка осталась на …». "
        "ЕСЛИ RUNTIME УЖЕ НАЖАЛ «Подписать договор», а страница не изменилась или кнопка осталась: "  # AI_VERDICT_1591R30
        "сними всплывающие окна, перерисуй подпись, нажми кнопку ОДИН раз и проверь в network ответ "
        "/checksignature/. Пока статус вкладки ✍️ (runtime сам рисует и нажимает) — не кликай. "
        "ПОСЛЕДНЯЯ СТРОКА ОТЧЁТА СТРОГО одна из: «VERDICT: SIGNED» (checksignature 200 или экран после "
        "подписи), «VERDICT: PAYMENT» (экран «пора оплатить eSIM»), «VERDICT: NOT_SIGNED — причина». "
        f"Причина вызова: {reason}. Текущий URL: {url}"
    )
    try:
        _ai_db_enqueue_internal(text, lane="fast", priority=120)
        print(
            f"[AI AUTO] TAB {tab_id}: SUCCESS_ASSIST поставлен в очередь: {reason}",
            flush=True,
        )
        return True
    except Exception as exc:
        print(
            f"[AI AUTO] TAB {tab_id}: не удалось поставить задачу: "
            f"{type(exc).__name__}: {exc}",
            flush=True,
        )
        return False


def _ai_effect_key(update_id, tool_name, args):
    raw = json.dumps(args or {}, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]
    return f"{int(update_id)}:{tool_name}:{digest}", raw


def _ai_effect_begin(update_id, tool_name, args):
    """Exactly-once gate for side-effect tools across Operator retries."""
    effect_key, args_json = _ai_effect_key(update_id, tool_name, args)
    conn = _ai_db_connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            """SELECT completed_at, result_json
               FROM effects WHERE effect_key=?""",
            (effect_key,),
        ).fetchone()

        if row:
            conn.commit()
            if row[0] is not None and row[1]:
                try:
                    return False, effect_key, json.loads(row[1])
                except Exception:
                    return False, effect_key, {
                        "ok": True,
                        "replayed": True,
                        "note": "Эффект уже был выполнен; повтор запрещён.",
                    }
            return False, effect_key, {
                "ok": False,
                "replayed": True,
                "note": (
                    "Этот side-effect уже был начат в предыдущей попытке "
                    "данного Telegram update. Повторно не выполняю."
                ),
            }

        conn.execute(
            """INSERT INTO effects
               (effect_key, update_id, tool, args_json, started_at)
               VALUES (?, ?, ?, ?, ?)""",
            (effect_key, int(update_id), str(tool_name), args_json, time.time()),
        )
        conn.commit()
        return True, effect_key, None
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _ai_effect_complete(effect_key, result):
    try:
        payload = json.dumps(result, ensure_ascii=False, default=str)
    except Exception:
        payload = json.dumps({"ok": False, "result": repr(result)}, ensure_ascii=False)

    with _ai_db_connect() as conn:
        conn.execute(
            """UPDATE effects
               SET completed_at=?, result_json=?
               WHERE effect_key=?""",
            (time.time(), payload, str(effect_key)),
        )
        conn.commit()


def _ai_db_next_message(lane, consumer_id, lease_seconds):
    now = time.time()
    conn = _ai_db_connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            """SELECT update_id, chat_id, body, attempts, priority
               FROM inbox
               WHERE done_at IS NULL
                 AND lane=?
                 AND next_attempt_at <= ?
                 AND (claimed_by IS NULL OR claim_until IS NULL OR claim_until < ?)
               ORDER BY priority DESC, update_id ASC
               LIMIT 1""",
            (str(lane), now, now),
        ).fetchone()
        if not row:
            conn.commit()
            return None
        update_id, chat_id, body, attempts, priority = row
        conn.execute(
            """UPDATE inbox
               SET attempts=?, claimed_by=?, claim_until=?
               WHERE update_id=?""",
            (
                int(attempts or 0) + 1,
                str(consumer_id),
                now + float(lease_seconds),
                int(update_id),
            ),
        )
        conn.commit()
        return {
            "update_id": int(update_id),
            "chat_id": str(chat_id),
            "body": str(body),
            "attempts": int(attempts or 0) + 1,
            "priority": int(priority or 0),
            "lane": str(lane),
        }
    finally:
        conn.close()


def _ai_db_release_lane_claims(lane):
    with _ai_db_connect() as conn:
        conn.execute(
            """UPDATE inbox
               SET claimed_by=NULL, claim_until=NULL
               WHERE done_at IS NULL AND lane=?""",
            (str(lane),),
        )
        conn.commit()



def _ai_db_complete(update_id, chat_id, response_text):
    """Finish the AI job and durably queue its Telegram response."""
    conn = _ai_db_connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            "UPDATE inbox SET done_at=?, last_error=NULL, claimed_by=NULL, claim_until=NULL WHERE update_id=?",
            (time.time(), int(update_id)),
        )
        conn.execute(
            """INSERT INTO outbox
               (update_id, chat_id, body, created_at, next_attempt_at)
               VALUES (?, ?, ?, ?, 0)
               ON CONFLICT(update_id) DO NOTHING""",
            (int(update_id), str(chat_id), str(response_text), time.time()),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _ai_db_fail(update_id, error, attempts):
    attempts = int(attempts or 1)
    if attempts >= 3:
        conn = _ai_db_connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT chat_id FROM inbox WHERE update_id=?",
                (int(update_id),),
            ).fetchone()
            chat_id = str(row[0]) if row else ""
            conn.execute(
                """UPDATE inbox
                   SET done_at=?, last_error=?, claimed_by=NULL, claim_until=NULL
                   WHERE update_id=?""",
                (time.time(), str(error)[:2000], int(update_id)),
            )
            if chat_id:
                body = (
                    "⚠️ DeepSeek Operator не смог завершить это сообщение после "
                    f"{attempts} попыток. Последняя ошибка: {str(error)[:1200]}"
                )
                conn.execute(
                    """INSERT INTO outbox
                       (update_id, chat_id, body, created_at, next_attempt_at)
                       VALUES (?, ?, ?, ?, 0)
                       ON CONFLICT(update_id) DO NOTHING""",
                    (int(update_id), chat_id, body, time.time()),
                )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
        return

    delay = min(30, max(3, attempts * 5))
    with _ai_db_connect() as conn:
        conn.execute(
            """UPDATE inbox
               SET last_error=?, next_attempt_at=?, claimed_by=NULL, claim_until=NULL
               WHERE update_id=? AND done_at IS NULL""",
            (str(error)[:2000], time.time() + delay, int(update_id)),
        )
        conn.commit()



def _ai_db_next_outbox():
    now = time.time()
    with _ai_db_connect() as conn:
        row = conn.execute(
            """SELECT update_id, chat_id, body, attempts
               FROM outbox
               WHERE sent_at IS NULL AND next_attempt_at <= ?
               ORDER BY created_at ASC, update_id ASC
               LIMIT 1""",
            (now,),
        ).fetchone()
        if not row:
            return None
        return {
            "update_id": int(row[0]),
            "chat_id": str(row[1]),
            "body": str(row[2]),
            "attempts": int(row[3] or 0),
        }


def _ai_db_outbox_sent(update_id):
    with _ai_db_connect() as conn:
        conn.execute(
            "UPDATE outbox SET sent_at=?, last_error=NULL WHERE update_id=?",
            (time.time(), int(update_id)),
        )
        conn.commit()


def _ai_db_outbox_fail(update_id, error, attempts):
    attempts = int(attempts or 0) + 1
    delay = min(120, max(2, attempts * 3))
    with _ai_db_connect() as conn:
        conn.execute(
            """UPDATE outbox
               SET attempts=?, last_error=?, next_attempt_at=?
               WHERE update_id=? AND sent_at IS NULL""",
            (attempts, str(error)[:1000], time.time() + delay, int(update_id)),
        )
        conn.commit()


def _ai_health_touch(health, state, detail=None):
    if health is None:
        return
    try:
        health["time"] = monotonic()
        health["pid"] = os.getpid()
        health["state"] = str(state)
        if detail is not None:
            health["detail"] = str(detail)[:500]
    except Exception:
        pass


def _release_ai_poll_lock():
    try:
        if not AI_POLL_LOCK_FILE.exists():
            return
        raw = AI_POLL_LOCK_FILE.read_text(encoding="utf-8").strip()
        if raw == str(os.getpid()):
            AI_POLL_LOCK_FILE.unlink(missing_ok=True)
    except Exception:
        pass


def ai_telegram_receiver_process(stop_event, receiver_health):
    """Owns getUpdates continuously; DeepSeek work can never block reception."""
    tg_cfg = load_telegram_config()
    chat = str(tg_cfg.get("chat_id", "")).strip()
    if not chat:
        print("[AI RX] Нет Telegram chat_id; receiver отключён.", flush=True)
        return

    _io1591.start_sender(globals(), tg_cfg, stop_event=stop_event)
    try:
        _, webhook_err = telegram_api(
            tg_cfg, "deleteWebhook", {"drop_pending_updates": "false"}
        )
        if webhook_err:
            print(f"[AI RX] deleteWebhook: {webhook_err}", flush=True)

        # IMPORTANT: there is NO startup drain anymore.
        # We resume exactly from the last offset that was committed together
        # with a durable inbox insert.
        offset = _ai_db_offset()
        print(f"[AI RX] Старт. Durable offset={offset}.", flush=True)

        while not stop_event.is_set():
            _ai_health_touch(receiver_health, "polling")
            r, err = telegram_api(
                tg_cfg,
                "getUpdates",
                {
                    "timeout": 2,
                    "offset": offset,
                    "allowed_updates": json.dumps(["message"]),
                },
            )

            if err:
                print(f"[AI RX] getUpdates error: {err}", flush=True)
                _ai_health_touch(receiver_health, "telegram_error", err)
                time.sleep(2)
            elif r:
                for upd in r.get("result", []):
                    try:
                        _ai_db_store_telegram_update(upd, chat)
                        update_id = int(upd.get("update_id", 0))
                        offset = max(offset, update_id + 1)
                        msg = upd.get("message") or {}
                        if str((msg.get("chat") or {}).get("id")) == chat:
                            body = str(msg.get("text") or "").strip()
                            if body:
                                print(
                                    f"[AI RX] update={update_id} "
                                    f"lane={_ai_message_lane(body)} "
                                    f"priority={_ai_message_priority(body)} "
                                    f"сохранён: {body[:120]}",
                                    flush=True,
                                )
                                try:
                                    telegram_api(
                                        tg_cfg,
                                        "sendChatAction",
                                        {"chat_id": chat, "action": "typing"},
                                    )
                                except Exception:
                                    pass
                    except Exception as exc:
                        # Do NOT move the local offset when persistence failed.
                        print(
                            f"[AI RX] Не удалось сохранить update: "
                            f"{type(exc).__name__}: {exc}",
                            flush=True,
                        )
                        offset = _ai_db_offset()
                        break

            # Responses are sent by the independent durable sender thread.
            _ai_health_touch(receiver_health, "polling")
    finally:
        pass


def acquire_ai_poll_lock():
    try:
        if AI_POLL_LOCK_FILE.exists():
            raw = AI_POLL_LOCK_FILE.read_text(encoding="utf-8").strip()
            try: old_pid = int(raw)
            except Exception: old_pid = 0
            if old_pid:
                try:
                    os.kill(old_pid, 0)
                    return False, old_pid
                except Exception:
                    pass
        AI_POLL_LOCK_FILE.write_text(str(os.getpid()), encoding="utf-8")
        return True, os.getpid()
    except Exception:
        return True, os.getpid()

def release_ai_poll_lock():
    try:
        if AI_POLL_LOCK_FILE.exists() and AI_POLL_LOCK_FILE.read_text(encoding="utf-8").strip() == str(os.getpid()):
            AI_POLL_LOCK_FILE.unlink(missing_ok=True)
    except Exception:
        pass



def load_deepseek_config():
    try:
        return json.loads(DEEPSEEK_CONFIG_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}




AI_AGENT_PENDING_FILE = Path(__file__).resolve().parent / "ai_agent_pending.json"

AI_AGENT_CHECKPOINT_ROOT = Path(__file__).resolve().parent / "ai_agent_checkpoints"


def _agent_checkpoint_path(session_id):
    AI_AGENT_CHECKPOINT_ROOT.mkdir(parents=True, exist_ok=True)
    return AI_AGENT_CHECKPOINT_ROOT / f"{session_id}.json"


def _agent_save_checkpoint(session_id, user_text, messages, state, round_no):
    """Persist enough state so a restarted DEV/FAST consumer can continue."""
    try:
        payload = {
            "session_id": str(session_id),
            "user_text": str(user_text),
            "round_no": int(round_no),
            "messages": messages,
            "state": {
                "changed": sorted(state.get("changed") or []),
                "deleted": sorted(state.get("deleted") or []),
                "runtime_actions": list(state.get("runtime_actions") or []),
                "summary": str(state.get("summary") or ""),
                "verification": list(state.get("verification") or []),
                "finished": bool(state.get("finished")),
                "awaiting_recheck": state.get("awaiting_recheck"),
            },
            "saved_at": time.time(),
        }
        path = _agent_checkpoint_path(session_id)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        tmp.replace(path)
    except Exception:
        pass


def _agent_load_checkpoint(session_id, user_text):
    path = _agent_checkpoint_path(session_id)
    if not path.exists():
        return None
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
        if str(obj.get("user_text") or "") != str(user_text):
            return None
        return obj
    except Exception:
        return None


def _agent_clear_checkpoint(session_id):
    try:
        _agent_checkpoint_path(session_id).unlink(missing_ok=True)
    except Exception:
        pass



def _submit_host_action(
    action_queue,
    action_results,
    action,
    ai_health=None,
    timeout=25,
):
    if action_queue is None or action_results is None:
        return {"ok": False, "error": "host action controller недоступен"}

    action_id = (
        f"{os.getpid()}-{time.time_ns()}-"
        f"{action.get('action','ACTION')}"
    )
    payload = dict(action)
    payload["action_id"] = action_id
    payload["requested_at"] = time.time()
    action_queue.put(payload)

    deadline = monotonic() + float(timeout)
    while monotonic() < deadline:
        _ai_health_touch(ai_health, "busy_host_action", payload.get("action"))
        try:
            result = action_results.pop(action_id, None)
        except Exception:
            result = None
        if result is not None:
            return dict(result)
        time.sleep(0.1)

    return {
        "ok": False,
        "error": f"host action timeout: {payload.get('action')}",
        "action_id": action_id,
    }


AI_AGENT_CANDIDATE_ROOT = Path(__file__).resolve().parent / "ai_candidates"
AI_AGENT_BACKUP_ROOT = Path(__file__).resolve().parent / "ai_agent_backups"
AI_AGENT_EXCLUDED_DIRS = {
    ".git", ".venv", "__pycache__", "diagnostics",
    "ai_candidates", "ai_agent_backups", "ai_agent_checkpoints", "ai_backups", "ai_full_backups",
}
AI_AGENT_PROTECTED_FILES = {
    "deepseek_config.json", "telegram_config.json",
    "ai_agent_pending.json", "ai_pending_proposals.json",
    "ai_observer_memory.jsonl", "ai_chat_memory.jsonl",
    ".deepseek_telegram_poll.lock",
    "ai_telegram_queue.sqlite3",
    "ai_telegram_queue.sqlite3-wal",
    "ai_telegram_queue.sqlite3-shm",
}


def _agent_safe_rel(path):
    raw = str(path or "").replace("\\", "/").strip().lstrip("/")
    if not raw:
        raise ValueError("пустой путь")
    rel = Path(raw)
    if rel.is_absolute() or ".." in rel.parts:
        raise ValueError("путь выходит за папку проекта")
    if any(part in AI_AGENT_EXCLUDED_DIRS for part in rel.parts):
        raise ValueError("служебная папка недоступна для редактирования")
    if rel.name in AI_AGENT_PROTECTED_FILES:
        raise ValueError("служебный/секретный файл недоступен для редактирования")
    return rel


def _agent_live_path(path):
    root = Path(__file__).resolve().parent
    rel = _agent_safe_rel(path)
    target = (root / rel).resolve()
    if root.resolve() not in target.parents:
        raise ValueError("путь выходит за папку проекта")
    return target


def _agent_candidate_dir(session_id):
    d = AI_AGENT_CANDIDATE_ROOT / str(session_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


def _agent_candidate_path(session_id, path):
    rel = _agent_safe_rel(path)
    d = _agent_candidate_dir(session_id)
    target = (d / rel).resolve()
    if d.resolve() not in target.parents:
        raise ValueError("candidate path выходит за сессию")
    return target


def _agent_is_text_file(fp):
    try:
        if fp.stat().st_size > 2_500_000:
            return False
        fp.read_text(encoding="utf-8")
        return True
    except Exception:
        return False


def _agent_list_project_files():
    root = Path(__file__).resolve().parent
    items = []
    for fp in sorted(root.rglob("*")):
        if not fp.is_file():
            continue
        rel = fp.relative_to(root)
        if any(part in AI_AGENT_EXCLUDED_DIRS for part in rel.parts):
            continue
        if rel.name in AI_AGENT_PROTECTED_FILES:
            continue
        try:
            size = fp.stat().st_size
        except Exception:
            size = 0
        items.append({"path": rel.as_posix(), "bytes": size})
    return items


def _agent_read_file(session_id, path, start_line=1, end_line=None):
    rel = _agent_safe_rel(path)
    candidate = _agent_candidate_path(session_id, rel.as_posix())
    live = _agent_live_path(rel.as_posix())
    source = candidate if candidate.exists() else live
    if not source.exists() or not source.is_file():
        return {"ok": False, "error": "файл не существует", "path": rel.as_posix()}
    try:
        text = source.read_text(encoding="utf-8")
    except Exception as exc:
        return {"ok": False, "error": f"не текстовый UTF-8 файл: {exc}", "path": rel.as_posix()}
    lines = text.splitlines()
    s = max(1, int(start_line or 1))
    e = min(len(lines), int(end_line)) if end_line else len(lines)
    if e < s:
        e = s
    numbered = "\n".join(f"{i}: {lines[i-1]}" for i in range(s, e + 1))
    return {
        "ok": True,
        "path": rel.as_posix(),
        "source": "candidate" if source == candidate else "working",
        "start_line": s,
        "end_line": e,
        "total_lines": len(lines),
        "content": numbered,
    }


def _agent_search_text(session_id, query, path=None, max_hits=30):
    root = Path(__file__).resolve().parent
    q = str(query or "")
    if not q:
        return {"ok": False, "error": "пустой query"}
    files = []
    if path:
        try:
            rel = _agent_safe_rel(path)
            files = [root / rel]
        except Exception as exc:
            return {"ok": False, "error": str(exc)}
    else:
        files = [root / Path(x["path"]) for x in _agent_list_project_files()]
    hits = []
    needle = q.lower()
    for live in files:
        if len(hits) >= int(max_hits or 30):
            break
        try:
            rel = live.relative_to(root)
            candidate = _agent_candidate_path(session_id, rel.as_posix())
            source = candidate if candidate.exists() else live
            text = source.read_text(encoding="utf-8")
        except Exception:
            continue
        for idx, line in enumerate(text.splitlines(), 1):
            if needle in line.lower():
                hits.append({
                    "path": rel.as_posix(),
                    "line": idx,
                    "text": line[:500],
                    "source": "candidate" if source == candidate else "working",
                })
                if len(hits) >= int(max_hits or 30):
                    break
    return {"ok": True, "hits": hits}


def _agent_ensure_candidate(session_id, path):
    rel = _agent_safe_rel(path)
    candidate = _agent_candidate_path(session_id, rel.as_posix())
    if candidate.exists():
        return candidate, rel
    live = _agent_live_path(rel.as_posix())
    candidate.parent.mkdir(parents=True, exist_ok=True)
    if live.exists():
        if not live.is_file():
            raise ValueError("path не является файлом")
        shutil.copy2(live, candidate)
    else:
        candidate.write_text("", encoding="utf-8")
    return candidate, rel


def _agent_compile_candidate_if_python(fp):
    if fp.suffix.lower() != ".py":
        return None
    body = fp.read_text(encoding="utf-8")
    compile(body, str(fp), "exec")
    return True


def _agent_write_file(session_id, state, path, content):
    candidate, rel = _agent_ensure_candidate(session_id, path)
    old = candidate.read_text(encoding="utf-8") if candidate.exists() else ""
    try:
        candidate.parent.mkdir(parents=True, exist_ok=True)
        candidate.write_text(str(content), encoding="utf-8")
        _agent_compile_candidate_if_python(candidate)
    except Exception:
        candidate.write_text(old, encoding="utf-8")
        raise
    state["changed"].add(rel.as_posix())
    state["deleted"].discard(rel.as_posix())
    return {"ok": True, "path": rel.as_posix(), "bytes": candidate.stat().st_size}


def _agent_replace_text(session_id, state, path, old, new, count=1):
    candidate, rel = _agent_ensure_candidate(session_id, path)
    body = candidate.read_text(encoding="utf-8")
    old = str(old)
    if not old:
        return {"ok": False, "error": "old пустой", "path": rel.as_posix()}
    occurrences = body.count(old)
    if occurrences == 0:
        return {
            "ok": False,
            "error": "точный фрагмент не найден; перечитай нужный диапазон файла и попробуй снова",
            "path": rel.as_posix(),
        }
    n = max(1, int(count or 1))
    updated = body.replace(old, str(new), n)
    candidate.write_text(updated, encoding="utf-8")
    try:
        _agent_compile_candidate_if_python(candidate)
    except Exception as exc:
        candidate.write_text(body, encoding="utf-8")
        return {"ok": False, "error": f"Python syntax check: {exc}", "path": rel.as_posix()}
    state["changed"].add(rel.as_posix())
    state["deleted"].discard(rel.as_posix())
    return {"ok": True, "path": rel.as_posix(), "replaced": min(occurrences, n)}


def _agent_replace_python_function(session_id, state, path, function_name, content):
    candidate, rel = _agent_ensure_candidate(session_id, path)
    if candidate.suffix.lower() != ".py":
        return {"ok": False, "error": "replace_python_function работает только с .py"}
    original = candidate.read_text(encoding="utf-8")
    try:
        tree = ast.parse(original)
    except Exception as exc:
        return {"ok": False, "error": f"исходный файл не парсится: {exc}"}
    target = None
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == str(function_name):
            target = node
            break
    if target is None or not getattr(target, "end_lineno", None):
        return {"ok": False, "error": f"функция {function_name} не найдена"}
    lines = original.splitlines(keepends=True)
    new_content = str(content).rstrip() + "\n"
    updated = "".join(lines[:target.lineno - 1]) + new_content + "".join(lines[target.end_lineno:])
    candidate.write_text(updated, encoding="utf-8")
    try:
        _agent_compile_candidate_if_python(candidate)
    except Exception as exc:
        candidate.write_text(original, encoding="utf-8")
        return {"ok": False, "error": f"Python syntax check: {exc}"}
    state["changed"].add(rel.as_posix())
    state["deleted"].discard(rel.as_posix())
    return {"ok": True, "path": rel.as_posix(), "function": str(function_name)}


def _agent_delete_file(state, path):
    rel = _agent_safe_rel(path)
    live = _agent_live_path(rel.as_posix())
    if not live.exists():
        return {"ok": False, "error": "файл не существует", "path": rel.as_posix()}
    state["deleted"].add(rel.as_posix())
    state["changed"].discard(rel.as_posix())
    return {"ok": True, "path": rel.as_posix(), "marked_for_delete": True}


def _agent_runtime_status(status_map, pages):
    statuses = []
    for i in range(1, TAB_COUNT + 1):
        info = status_map.get(str(i)) or {}
        statuses.append(f"TAB {i}: {info.get('text','нет статуса')}")
    page_lines = []
    for item in pages:
        if item.get("tab_id"):
            page_lines.append(
                f"TAB {item.get('tab_id')} browser={item.get('browser')} "
                f"url={item.get('url','')} title={item.get('title','')}"
            )
    return "\n".join(statuses), "\n".join(page_lines)


OPERATOR_API_MISSION_V1584 = """ТВОЯ ПОСТОЯННАЯ ГЛАВНАЯ ЗАДАЧА — автономно сопровождать SUCCESS/ERROR-вкладки и контролировать корректность завершения процесса. После выхода из mobile-id-auth на post-auth страницу сначала наблюдай живую physical-вкладку: DOM, validation, состояние элементов, console/network. Если процесс остановился, самостоятельно установи фактическую причину по странице; недостающим или невалидным может быть любое поле. Уже корректные значения не меняй. SUCCESS_GUARD и ERROR_GUARD запрещают destructive close/restart/reload/back/navigation. После автономного вмешательства отправляй краткий фактический отчёт: блокер, проверки, изменения/значения, состояние действия, результат и текущий URL. Мониторинг воркеров, Telegram, прокси и кода — второстепенная задача. Если спрашивают о твоей задаче, первым делом называй эту постоянную миссию. Для состояния «сейчас» используй текущий heartbeat, текущие вкладки и только текущую service/runtime session; старые proxy/Telegram ошибки не выдавай за текущие без свежего подтверждения."""

OPERATOR_MISSION_1586 = """У ТЕБЯ ЕСТЬ ПОСТОЯННОЕ АКТИВНОЕ ПОРУЧЕНИЕ, ОНО НЕ ЗАВИСИТ ОТ НОВЫХ СООБЩЕНИЙ ПОЛЬЗОВАТЕЛЯ. Твоя главная задача — автономный SUCCESS/ERROR SUPERVISOR процесса регистрации eSIM. Ты обязан самостоятельно сопровождать каждую вкладку после mobile-id-auth, распознавать SUCCESS/ERROR/post-auth состояния, анализировать живую physical-вкладку, DOM, validation, console/network и доводить безопасно исправимый post-auth процесс до корректного завершения без ожидания отдельного поручения пользователя. Если не заполнено или невалидно любое обязательное поле — сам определи именно это поле по текущей странице; не ограничивайся заранее известным списком. Уже корректные значения не меняй. На SUCCESS_GUARD и ERROR_GUARD запрещены destructive close/restart/reload/back/forward/navigation. /registration/error НИКОГДА не является успехом. Настоящий SUCCESS фиксируется только после подтверждённого финального post-sign состояния. После вмешательства отправляй фактический мини-отчёт: блокер, что проверил, что именно изменил и на какие значения, состояние кнопки подписания, действие/результат и финальный URL. Мониторинг кода, воркеров, Telegram и прокси — вторичная техническая функция.

КРИТИЧЕСКОЕ ПРАВИЛО РОЛИ: никогда не говори «у меня нет задачи», «конкретного поручения нет», «я в режиме ожидания», «я просто наблюдатель» или эквивалент. Постоянная задача уже назначена выше. Если пользователь спрашивает «какая у тебя задача?», первым делом ответь, что твоя постоянная главная задача — автономный SUCCESS/ERROR Supervisor, а затем кратко опиши текущий живой статус. Для утверждений о состоянии «сейчас» используй только текущую service/runtime session и текущие вкладки; исторические ошибки не выдавай за текущие без свежего подтверждения.

ПРАВИЛО ОШИБКИ РЕГИСТРАЦИИ (ERROR_RECOVERY_1591R5, ERROR_SKIP_ALWAYS_1591R16): /registration/error — не успех. Runtime обрабатывает её сам, автоматически, без отдельного подтверждения и без запроса к DeepSeek: error-вкладка закрывается, открывается новая, строка пропускается и записывается в error_skipped_rows.txt, worker берёт следующую. Анализировать такие страницы не нужно. Ни одна ошибка не должна приводить к потере worker. Запрет close/restart/reload остаётся только для SUCCESS_GUARD."""

def _agent_system_prompt(status_map, pages, user_text):
    try:
        rules = PROJECT_RULES_FILE.read_text(encoding="utf-8")
    except Exception:
        rules = ""
    statuses, page_lines = _agent_runtime_status(status_map, pages)
    return f"""Ты DeepSeek Operator — технический оператор проекта.

Ты умеешь:
- читать весь исходный проект и готовить candidate-правки;
- читать Python stdout/stderr;
- видеть живые Chromium-вкладки через CDP;
- читать DOM/HTML/текст/cookies;
- читать browser console, JS errors и network telemetry;
- по прямому запросу пользователя кликать, вводить текст, нажимать клавиши,
  выполнять JS, reload/navigate/back/forward, открывать/закрывать страницы,
  запрашивать restart worker и выполнять terminal-команды.

ВАЖНО: live-действия проходят через HOST ACTION CONTROLLER.
Ты не управляешь жизненным циклом worker напрямую.
Контроллер проверяет точную physical generation/window.name непосредственно перед действием.
Устаревшее действие получает STALE_GENERATION и ничего не меняет.

ГЛАВНАЯ АВТОНОМНАЯ ЦЕЛЬ — SUCCESS SUPERVISOR:
- Если TAB вышел с mobile-id-auth на personal-data-form/страницу договора, mobile-id
  подтверждение уже успешно. С этого момента самостоятельно сопровождай physical-вкладку
  до завершения договора, не ожидая сообщений пользователя.
- Сначала НАБЛЮДАЙ: DOM, видимые validation errors, enabled/disabled кнопок,
  DevTools console и network. Пока сайт сам корректно продвигается — не вмешивайся.
- Если прогресс остановился, сам установи конкретную причину и вмешайся минимально:
  заполни недостающие обязательные поля, выбери autocomplete, исправь невалидное поле.
  Не меняй поля, которые сайт уже корректно заполнил.
- Для этого сценария: если отсутствует город — поставь «Саратов» и выбери подсказку;
  если отсутствует область — «Саратовская область» и выбери подсказку.
- Проверь остальные обязательные поля по DOM/validation; не ограничивайся заранее
  известным списком города/области.
- Правильно заполни поле подписи так, чтобы форма приняла её во всех требуемых областях.
  Дождись, когда «Подписать договор» станет активной, и нажми её.
- После нажатия снова наблюдай страницу/console/network и проверь фактический результат.
- Если runtime уже нажал «Подписать договор», а страница не изменилась или кнопка осталась:
  сними всплывающие окна, перерисуй подпись, нажми кнопку ОДИН раз, проверь ответ
  /checksignature/ в network. Пока статус вкладки ✍️ — runtime сам рисует и нажимает, не кликай.
- Последняя строка каждого отчёта SUCCESS SUPERVISOR СТРОГО одна из: «VERDICT: SIGNED»,
  «VERDICT: PAYMENT» (экран «пора оплатить eSIM»), «VERDICT: NOT_SIGNED — причина».
  Runtime читает эту строку: SIGNED фиксирует успех, PAYMENT — шаг оплаты, NOT_SIGNED —
  вкладка удерживается и уходит на проверку пользователю.
- При любой проблеме после успешного auth сам анализируй и помогай, без участия пользователя.
- На SUCCESS GUARD АБСОЛЮТНО ЗАПРЕЩЕНЫ: close, restart, reload, navigate, back,
  forward и любые действия, способные потерять эту успешную physical-вкладку.
- После каждого автономного вмешательства ОБЯЗАТЕЛЬНО дай пользователю мини-отчёт:
  (1) что мешало; (2) что изменил; (3) конкретные поставленные значения;
  (4) состояние кнопки; (5) нажал ли «Подписать договор»; (6) результат;
  (7) текущий URL/экран. Не пиши абстрактно «исправил» — перечисляй фактические действия.

ERROR SUPERVISOR:
- /registration/error НИКОГДА не является success.
- Такие страницы runtime обрабатывает АВТОМАТИЧЕСКИ, без отдельного подтверждения и без
  твоего анализа: error-вкладка закрывается, открывается новая, строка пропускается
  (error_skipped_rows.txt), worker переходит к следующей.
- Не запрашивай и не проводи анализ /registration/error по своей инициативе.
- Из-за error worker никогда не теряется: слот всегда получает новую вкладку.
- Запрет close/restart/reload/back/navigate действует только на SUCCESS GUARD.

Правила действий:
1. Сначала read-only диагностика, если задача не является прямой командой пользователя.
2. После ЛЮБОГО live-действия обязательно перечитай состояние затронутого TAB.
   До re-check следующий live-action будет отклонён.
3. Не отправляй пачку close/reload/restart на несколько вкладок.
   Одно действие → результат → re-check → следующее решение.
4. Если сам пришёл к выводу, что нужен restart/close/reload здорового worker,
   host имеет право отказать. Для автоматического recovery нужны реальные признаки stall.
5. Если пользователь прямо сказал «нажми / введи / перезагрузи / перезапусти / закрой»,
   это считается user-directed action, но generation-check всё равно обязателен.
6. Не проводи полный аудит всех вкладок без просьбы. Используй минимум инструментов.
7. Отвечай только по-русски.
8. Для простого вопроса дай короткий ответ быстро.

КОД:
Если пользователь явно просит фикс/изменение кода — подготовь candidate.
Candidate не применяется автоматически во время текущего запуска.
Пользователь отдельно пишет «применить»/«ок» → backup → apply → compile → rollback при ошибке.

ПРАВИЛА ПРОЕКТА:
{rules}

СООБЩЕНИЕ ПОЛЬЗОВАТЕЛЯ:
{user_text}

RUNTIME-СТАТУСЫ:
{statuses}

ОТКРЫТЫЕ WORKER-СТРАНИЦЫ:
{page_lines}

ПОСЛЕДНИЕ СТРОКИ PYTHON-КОНСОЛИ:
{_runtime_console_tail(max_lines=80, max_chars=14000)}
"""



def _agent_tools():
    return [
        {
            "type": "function",
            "function": {
                "name": "list_project_files",
                "description": "Список доступных файлов всего проекта.",
                "strict": True,
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "read_runtime_console",
                "description": "Прочитать реальный недавний stdout/stderr всех Python-процессов текущего запуска программы.",
                "strict": True,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "max_lines": {"type": "integer", "minimum": 20, "maximum": 500}
                    },
                    "required": [],
                    "additionalProperties": False
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "read_project_file",
                "description": "Прочитать рабочую или уже изменённую candidate-версию файла по строкам.",
                "strict": True,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "start_line": {"type": "integer", "minimum": 1},
                        "end_line": {"type": "integer", "minimum": 1},
                    },
                    "required": ["path"],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "search_project_text",
                "description": "Найти текст по всем доступным файлам проекта или в одном файле.",
                "strict": True,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "path": {"type": "string"},
                        "max_hits": {"type": "integer", "minimum": 1, "maximum": 100},
                    },
                    "required": ["query"],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "replace_python_function",
                "description": "Заменить целиком Python-функцию по её имени в candidate, без хрупкого old/new proposal.",
                "strict": True,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "function_name": {"type": "string"},
                        "content": {"type": "string"},
                    },
                    "required": ["path", "function_name", "content"],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "replace_text",
                "description": "Точно заменить небольшой фрагмент текста в candidate. При несовпадении инструмент вернёт ошибку и можно перечитать файл.",
                "strict": True,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "old": {"type": "string"},
                        "new": {"type": "string"},
                        "count": {"type": "integer", "minimum": 1, "maximum": 100},
                    },
                    "required": ["path", "old", "new"],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "write_candidate_file",
                "description": "Создать новый файл или полностью заменить candidate-файл.",
                "strict": True,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "content": {"type": "string"},
                    },
                    "required": ["path", "content"],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "delete_project_file",
                "description": "Пометить файл проекта на удаление при подтверждённом применении.",
                "strict": True,
                "parameters": {
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                    "required": ["path"],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "request_runtime_action",
                "description": "Запросить немедленный same-row restart конкретного TAB.",
                "strict": True,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "action": {"type": "string", "enum": ["RESTART_TAB"]},
                        "tab": {"type": "integer", "minimum": 1, "maximum": TAB_COUNT},
                        "reason": {"type": "string"},
                    },
                    "required": ["action", "tab", "reason"],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "list_browser_tabs",
                "description": "Показать все живые вкладки обоих Chromium, включая URL/title/window.name.",
                "strict": True,
                "parameters": {"type":"object","properties":{},"required":[],"additionalProperties":False},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_page_state",
                "description": "Получить URL/title/readyState/видимый текст/active element живой вкладки; опционально HTML.",
                "strict": True,
                "parameters": {
                    "type":"object",
                    "properties":{"tab":{"type":"integer","minimum":1,"maximum":TAB_COUNT},"include_html":{"type":"boolean"}},
                    "required":["tab"],"additionalProperties":False
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "read_browser_devtools",
                "description": "Прочитать browser console.log/warn/error, JS errors/stack, fetch/XHR network telemetry и performance resources вкладки.",
                "strict": True,
                "parameters": {
                    "type":"object",
                    "properties":{"tab":{"type":"integer","minimum":1,"maximum":TAB_COUNT},"max_items":{"type":"integer","minimum":10,"maximum":500}},
                    "required":["tab"],"additionalProperties":False
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "inspect_dom",
                "description": "Посмотреть реальные DOM-элементы вкладки по CSS selector или тексту с attrs/value/visible/disabled/rect.",
                "strict": True,
                "parameters": {
                    "type":"object",
                    "properties":{
                        "tab":{"type":"integer","minimum":1,"maximum":TAB_COUNT},
                        "selector":{"type":"string"},"text":{"type":"string"},
                        "max_items":{"type":"integer","minimum":1,"maximum":100}
                    },
                    "required":["tab"],"additionalProperties":False
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "browser_click",
                "description": "Кликнуть в живой вкладке по CSS selector, видимому тексту, role+name или координатам.",
                "strict": True,
                "parameters": {
                    "type":"object",
                    "properties":{
                        "tab":{"type":"integer","minimum":1,"maximum":TAB_COUNT},
                        "selector":{"type":"string"},"text":{"type":"string"},
                        "role":{"type":"string"},"name":{"type":"string"},
                        "x":{"type":"number"},"y":{"type":"number"},
                        "force":{"type":"boolean"},"timeout_ms":{"type":"integer","minimum":100,"maximum":60000}
                    },
                    "required":["tab"],"additionalProperties":False
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "browser_fill",
                "description": "Заполнить input/textarea в живой вкладке.",
                "strict": True,
                "parameters": {
                    "type":"object",
                    "properties":{
                        "tab":{"type":"integer","minimum":1,"maximum":TAB_COUNT},
                        "selector":{"type":"string"},"value":{"type":"string"},
                        "timeout_ms":{"type":"integer","minimum":100,"maximum":60000}
                    },
                    "required":["tab","selector","value"],"additionalProperties":False
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "browser_type",
                "description": "Печатать текст через клавиатуру в элемент или текущий focus.",
                "strict": True,
                "parameters": {
                    "type":"object","properties":{
                        "tab":{"type":"integer","minimum":1,"maximum":TAB_COUNT},
                        "selector":{"type":"string"},"value":{"type":"string"},
                        "delay_ms":{"type":"integer","minimum":0,"maximum":1000},
                        "timeout_ms":{"type":"integer","minimum":100,"maximum":60000}
                    },
                    "required":["tab","value"],"additionalProperties":False
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "browser_press",
                "description": "Нажать клавишу/комбинацию клавиш в элементе или текущем focus.",
                "strict": True,
                "parameters": {
                    "type":"object","properties":{
                        "tab":{"type":"integer","minimum":1,"maximum":TAB_COUNT},
                        "selector":{"type":"string"},"key":{"type":"string"},
                        "timeout_ms":{"type":"integer","minimum":100,"maximum":60000}
                    },
                    "required":["tab","key"],"additionalProperties":False
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "browser_evaluate_js",
                "description": "Выполнить произвольный JavaScript в контексте живой вкладки и вернуть результат.",
                "strict": True,
                "parameters": {
                    "type":"object","properties":{
                        "tab":{"type":"integer","minimum":1,"maximum":TAB_COUNT},
                        "script":{"type":"string"}
                    },
                    "required":["tab","script"],"additionalProperties":False
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "browser_navigate",
                "description": "Перейти живой вкладкой на URL.",
                "strict": True,
                "parameters": {
                    "type":"object","properties":{
                        "tab":{"type":"integer","minimum":1,"maximum":TAB_COUNT},
                        "url":{"type":"string"},"wait_until":{"type":"string"},
                        "timeout_ms":{"type":"integer","minimum":100,"maximum":120000}
                    },
                    "required":["tab","url"],"additionalProperties":False
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "browser_reload",
                "description": "Перезагрузить живую вкладку.",
                "strict": True,
                "parameters":{"type":"object","properties":{"tab":{"type":"integer","minimum":1,"maximum":TAB_COUNT},"timeout_ms":{"type":"integer","minimum":100,"maximum":120000}},"required":["tab"],"additionalProperties":False},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "browser_back",
                "description": "Назад в истории живой вкладки.",
                "strict": True,
                "parameters":{"type":"object","properties":{"tab":{"type":"integer","minimum":1,"maximum":TAB_COUNT},"timeout_ms":{"type":"integer","minimum":100,"maximum":120000}},"required":["tab"],"additionalProperties":False},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "browser_forward",
                "description": "Вперёд в истории живой вкладки.",
                "strict": True,
                "parameters":{"type":"object","properties":{"tab":{"type":"integer","minimum":1,"maximum":TAB_COUNT},"timeout_ms":{"type":"integer","minimum":100,"maximum":120000}},"required":["tab"],"additionalProperties":False},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "browser_wait",
                "description": "Подождать указанное время в живой вкладке.",
                "strict": True,
                "parameters":{"type":"object","properties":{"tab":{"type":"integer","minimum":1,"maximum":TAB_COUNT},"milliseconds":{"type":"integer","minimum":0,"maximum":60000}},"required":["tab","milliseconds"],"additionalProperties":False},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "browser_cookies",
                "description": "Прочитать cookies контекста живой вкладки.",
                "strict": True,
                "parameters":{"type":"object","properties":{"tab":{"type":"integer","minimum":1,"maximum":TAB_COUNT}},"required":["tab"],"additionalProperties":False},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "browser_clear_telemetry",
                "description": "Очистить накопленные browser console/error/network telemetry вкладки.",
                "strict": True,
                "parameters":{"type":"object","properties":{"tab":{"type":"integer","minimum":1,"maximum":TAB_COUNT}},"required":["tab"],"additionalProperties":False},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "browser_close_tab",
                "description": "Управляемо заменить worker-вкладку: host закрывает старую вкладку, завершает старый процесс и сразу запускает replacement с той же строкой.",
                "strict": True,
                "parameters":{"type":"object","properties":{"tab":{"type":"integer","minimum":1,"maximum":TAB_COUNT}},"required":["tab"],"additionalProperties":False},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "browser_open_page",
                "description": "Открыть новую обычную страницу в доступном Chromium.",
                "strict": True,
                "parameters":{"type":"object","properties":{"browser":{"type":"integer","minimum":1,"maximum":BROWSER_COUNT},"url":{"type":"string"}},"required":["browser","url"],"additionalProperties":False},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "run_terminal",
                "description": "Выполнить реальную команду локального терминала с теми же Windows-правами, что у Python-процесса, и вернуть stdout/stderr/код.",
                "strict": True,
                "parameters": {
                    "type":"object","properties":{
                        "command":{"type":"string"},"cwd":{"type":"string"},
                        "timeout":{"type":"integer","minimum":1,"maximum":600}
                    },
                    "required":["command"],"additionalProperties":False
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "finish_changes",
                "description": "Завершить текущую задачу. Можно без code changes; summary — итог пользователю.",
                "strict": True,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "summary": {"type": "string"},
                        "verification": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                    },
                    "required": ["summary", "verification"],
                    "additionalProperties": False,
                },
            },
        },
    ]


def _agent_execute_tool(session_id, state, name, args, cdp_urls, action_queue=None, action_results=None, ai_health=None, job_update_id=None):
    try:
        effect_key = None

        readonly_browser_tools = {
            "list_browser_tabs", "get_page_state", "read_browser_devtools",
            "inspect_dom", "browser_cookies",
        }
        browser_mutation_tools = {
            "browser_click", "browser_fill", "browser_type", "browser_press",
            "browser_evaluate_js", "browser_navigate", "browser_reload",
            "browser_back", "browser_forward", "browser_clear_telemetry",
            "browser_close_tab", "browser_open_page",
        }

        # After any live mutation the model MUST inspect the result before another.
        if name in browser_mutation_tools or name == "request_runtime_action":
            pending_recheck = state.get("awaiting_recheck")
            if pending_recheck:
                return {
                    "ok": False,
                    "error": (
                        "Сначала перечитай состояние после предыдущего действия "
                        f"(TAB {pending_recheck.get('tab')}). Используй get_page_state/"
                        "inspect_dom/read_browser_devtools."
                    ),
                }

        if name in readonly_browser_tools:
            tab = int(args.get("tab") or 0) if args.get("tab") is not None else None
            pending_recheck = state.get("awaiting_recheck")
            if pending_recheck and (
                name == "list_browser_tabs"
                or not tab
                or tab == int(pending_recheck.get("tab") or 0)
            ):
                state["awaiting_recheck"] = None
        if name == "list_project_files":
            return {"ok": True, "files": _agent_list_project_files()}
        if name == "read_runtime_console":
            return {
                "ok": True,
                "scope": "current_service_session_only",
                "console": _runtime_console_tail(
                    max_lines=args.get("max_lines", 200),
                    max_chars=50000,
                ),
            }
        if name == "browser_close_tab":
            tab = int(args.get("tab") or 0)
            if not 1 <= tab <= TAB_COUNT:
                return {"ok": False, "error": "tab вне диапазона"}
            action = {
                "action": "RESTART_TAB",
                "tab": tab,
                "reason": "DeepSeek Operator requested managed worker replacement",
                "requested_at": time.time(),
            }
            if action_queue is None:
                return {"ok": False, "error": "runtime action queue недоступна"}
            action_queue.put(action)
            result = {
                "ok": True,
                "managed": True,
                "queued": action,
                "note": "Запрос передан host. Host сам проверит, действительно ли worker требует recovery.",
            }
            if effect_key is not None:
                _ai_effect_complete(effect_key, result)
            return result
        if name in readonly_browser_tools or name == "browser_wait":
            return _browser_tool(cdp_urls, name, args)

        if name in browser_mutation_tools:
            user_text = str(state.get("user_text") or "")
            explicit = _explicit_live_action_request(user_text)

            # Open-page is not bound to an existing worker generation.
            if name == "browser_open_page":
                action = {
                    "action": "OPEN_PAGE",
                    "browser": int(args.get("browser") or 1),
                    "url": str(args.get("url") or "about:blank"),
                    "user_directed": bool(explicit),
                }
                result = _submit_host_action(
                    action_queue, action_results, action,
                    ai_health=ai_health, timeout=30,
                )
                if result.get("ok"):
                    state["awaiting_recheck"] = {"tab": 0}
                return result

            tab = int(args.get("tab") or 0)
            ident = _current_worker_identity(cdp_urls, tab)
            if not ident:
                return {"ok": False, "error": f"TAB {tab}: живая worker-вкладка не найдена"}

            action_map = {
                "browser_click": "CLICK",
                "browser_fill": "FILL",
                "browser_type": "TYPE",
                "browser_press": "PRESS",
                "browser_evaluate_js": "EVALUATE_JS",
                "browser_navigate": "NAVIGATE",
                "browser_reload": "RELOAD",
                "browser_back": "BACK",
                "browser_forward": "FORWARD",
                "browser_clear_telemetry": "CLEAR_TELEMETRY",
                "browser_close_tab": "CLOSE_TAB",
            }
            action = {
                "action": action_map[name],
                "tab": tab,
                "expected_window_name": ident["window_name"],
                "args": dict(args),
                "user_directed": bool(explicit),
                "reason": f"DeepSeek tool {name}",
            }
            result = _submit_host_action(
                action_queue, action_results, action,
                ai_health=ai_health, timeout=30,
            )
            if result.get("ok"):
                state["awaiting_recheck"] = {"tab": tab}
            return result
        if name == "run_terminal":
            if not _explicit_terminal_request(state.get("user_text") or ""):
                return {
                    "ok": False,
                    "error": "Terminal разрешён, когда пользователь явно просит выполнить команду.",
                }
            action = {
                "action": "RUN_TERMINAL",
                "command": str(args.get("command") or ""),
                "cwd": args.get("cwd"),
                "timeout": int(args.get("timeout") or 120),
                "user_directed": True,
            }
            return _submit_host_action(
                action_queue, action_results, action,
                ai_health=ai_health,
                timeout=min(180, int(args.get("timeout") or 120) + 10),
            )
        if name == "read_project_file":
            return _agent_read_file(
                session_id,
                args.get("path"),
                args.get("start_line", 1),
                args.get("end_line"),
            )
        if name == "search_project_text":
            return _agent_search_text(
                session_id,
                args.get("query"),
                args.get("path"),
                args.get("max_hits", 30),
            )
        if name == "replace_python_function":
            return _agent_replace_python_function(
                session_id, state,
                args.get("path"), args.get("function_name"), args.get("content"),
            )
        if name == "replace_text":
            return _agent_replace_text(
                session_id, state,
                args.get("path"), args.get("old"), args.get("new"), args.get("count", 1),
            )
        if name == "write_candidate_file":
            return _agent_write_file(
                session_id, state, args.get("path"), args.get("content"),
            )
        if name == "delete_project_file":
            return _agent_delete_file(state, args.get("path"))
        if name == "request_runtime_action":
            tab = int(args.get("tab") or 0)
            ident = _current_worker_identity(cdp_urls, tab)
            if not ident:
                return {"ok": False, "error": f"TAB {tab}: worker page не найдена"}
            action = {
                "action": "RESTART_TAB",
                "tab": tab,
                "expected_window_name": ident["window_name"],
                "reason": str(args.get("reason") or ""),
                "user_directed": bool(
                    _explicit_tab_lifecycle_request(state.get("user_text") or "")
                ),
            }
            result = _submit_host_action(
                action_queue, action_results, action,
                ai_health=ai_health, timeout=35,
            )
            if result.get("ok"):
                state["awaiting_recheck"] = {"tab": tab}
            return result
        if name == "finish_changes":
            state["summary"] = str(args.get("summary") or "").strip()
            state["verification"] = [str(x) for x in (args.get("verification") or [])]
            state["finished"] = True
            return {
                "ok": True,
                "changed": sorted(state["changed"]),
                "deleted": sorted(state["deleted"]),
                "runtime_actions": state["runtime_actions"],
            }
        result = {"ok": False, "error": f"неизвестный tool: {name}"}
        if effect_key is not None:
            _ai_effect_complete(effect_key, result)
        return result
    except Exception as exc:
        result = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        try:
            if 'effect_key' in locals() and effect_key is not None:
                _ai_effect_complete(effect_key, result)
        except Exception:
            pass
        return result


def _run_developer_agent(status_map, pages, user_text, images, cdp_urls, ai_health=None, action_queue=None, action_results=None, job_update_id=None):
    cfg = load_deepseek_config()
    key = str(cfg.get("api_key", "")).strip()
    if not key:
        return None, "deepseek_config.json: отсутствует api_key"

    try:
        import requests, base64
    except ImportError:
        return None, 'Нужен requests: python -m pip install requests'

    # Stable session id lets a retried durable Telegram update resume its checkpoint.
    session_id = (
        f"tg_{int(job_update_id)}"
        if job_update_id is not None
        else time.strftime("%Y%m%d_%H%M%S") + f"_{os.getpid()}"
    )
    session_dir = _agent_candidate_dir(session_id)

    state = {
        "changed": set(),
        "deleted": set(),
        "runtime_actions": [],
        "summary": "",
        "verification": [],
        "finished": False,
        "user_text": user_text,
        "awaiting_recheck": None,
        "observations": [],
    }

    system_prompt = _io1591.build_system(globals(), status_map, pages, user_text)
    user_content = [{"type": "text", "text": "Выполни задачу пользователя. Используй инструменты проекта."}]
    for raw in images or []:
        try:
            b64 = base64.b64encode(raw).decode("ascii")
            user_content.append({
                "type": "image_url",
                "image_url": {"url": "data:image/png;base64," + b64, "detail": "low"},
            })
        except Exception:
            pass

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]
    round_no = 0

    # Resume after an Operator process crash/restart.
    checkpoint = _agent_load_checkpoint(session_id, user_text)
    if checkpoint:
        try:
            cp_messages = checkpoint.get("messages")
            cp_state = checkpoint.get("state") or {}
            if isinstance(cp_messages, list) and cp_messages:
                messages = cp_messages
                round_no = int(checkpoint.get("round_no") or 0)
                state["changed"] = set(cp_state.get("changed") or [])
                state["deleted"] = set(cp_state.get("deleted") or [])
                state["runtime_actions"] = list(cp_state.get("runtime_actions") or [])
                state["summary"] = str(cp_state.get("summary") or "")
                state["verification"] = list(cp_state.get("verification") or [])
                state["finished"] = bool(cp_state.get("finished"))
                state["awaiting_recheck"] = cp_state.get("awaiting_recheck")
                print(
                    f"[AI] Возобновляю checkpoint {session_id} с round={round_no}.",
                    flush=True,
                )
        except Exception:
            pass

    code_task = _explicit_code_change_request(user_text)
    live_action_task = _explicit_live_action_request(user_text)

    readonly_names = {
        "list_project_files",
        "read_project_file",
        "search_project_text",
        "read_runtime_console",
        "list_browser_tabs",
        "get_page_state",
        "read_browser_devtools",
        "inspect_dom",
        "browser_cookies",
        "browser_wait",
    }
    live_names = readonly_names | {
        "browser_click", "browser_fill", "browser_type", "browser_press",
        "browser_evaluate_js", "browser_navigate", "browser_reload",
        "browser_back", "browser_forward", "browser_clear_telemetry",
        "browser_close_tab", "browser_open_page", "request_runtime_action",
        "run_terminal",
    }
    code_names = readonly_names | {
        "replace_python_function",
        "replace_text",
        "write_candidate_file",
        "delete_project_file",
        "finish_changes",
    }

    allowed_names = (
        code_names if code_task
        else live_names if live_action_task
        else readonly_names
    )
    tools = [
        tool for tool in _agent_tools()
        if ((tool.get("function") or {}).get("name") in allowed_names)
    ]

    # No overall task deadline and no tool-round cap.
    # Only one HTTP request gets a finite timeout so a dead socket can be retried.
    api_timeout = 300
    token_budget = min(
        int(cfg.get("developer_max_tokens") or 12000),
        12000,
    )

    # Loop detection is based on repeated identical tool+args+result, not elapsed time.
    last_effect_signature = None
    repeated_effect_count = 0
    loop_warning_sent = False

    def compact_result(result):
        try:
            text = json.dumps(result, ensure_ascii=False, sort_keys=True, default=str)
        except Exception:
            text = repr(result)
        return text[:5000]

    def remember_observation(name, args, result):
        try:
            item = {
                "tool": str(name),
                "args": args,
                "result": result,
            }
            state["observations"].append(item)
            if len(state["observations"]) > 20:
                state["observations"] = state["observations"][-20:]
        except Exception:
            pass

    def fallback_plan(reason):
        lines = [
            "Агент не смог продолжить текущий шаг, но уже собранные результаты сохранены.",
            f"Причина остановки шага: {reason}",
        ]
        if state["changed"]:
            lines.append("Подготовленные candidate-файлы: " + ", ".join(sorted(state["changed"])))
        if state["deleted"]:
            lines.append("Помечены на удаление: " + ", ".join(sorted(state["deleted"])))
        if state.get("summary"):
            lines.append("Последний вывод: " + str(state["summary"])[:1800])

        obs = state.get("observations") or []
        if obs:
            lines.append("Последние факты:")
            for item in obs[-6:]:
                result_text = compact_result(item.get("result"))
                lines.append(
                    f"- {item.get('tool')}: {result_text[:900]}"
                )

        plan = {
            "id": session_id,
            "created": time.time(),
            "summary": "\n".join(lines),
            "verification": list(state.get("verification") or []),
            "files": sorted(state["changed"]),
            "deletes": sorted(state["deleted"]),
            "runtime_actions": list(state.get("runtime_actions") or []),
            "candidate_dir": str(session_dir),
            "needs_apply": bool(state["changed"] or state["deleted"]),
        }
        return plan

    while True:
        round_no += 1
        _ai_health_touch(ai_health, "busy_deepseek", f"round={round_no}")

        # Always rebuild from current instructions, never from checkpoint system text.
        messages = _io1591.canonical_messages(messages, system_prompt, user_text)

        payload = {
            "model": str(cfg.get("model") or "deepseek-flash"),
            "messages": messages,
            "tools": tools,
            "tool_choice": "auto",
            "temperature": 0.1,
            "max_tokens": token_budget,
        }

        _io1591.request_audit(payload, "tools")

        # Retry transient API/network failures without killing the whole task.
        retry_no = 0
        while True:
            try:
                r = requests.post(
                    "https://api.deepseek.com/chat/completions",
                    headers={
                        "Authorization": "Bearer " + key,
                        "Content-Type": "application/json",
                    },
                    json=payload,
                    timeout=api_timeout,
                )
                try:
                    obj = r.json()
                except Exception:
                    obj = None

                if r.ok:
                    break

                status = int(r.status_code)
                retryable = status == 429 or 500 <= status <= 599
                if not retryable:
                    reason = f"DeepSeek HTTP {status}: {str(obj or r.text)[:1200]}"
                    plan = fallback_plan(reason)
                    _agent_clear_checkpoint(session_id)
                    return plan, None

                retry_no += 1
                wait_s = min(30, 3 * retry_no)
                print(
                    f"[AI] DeepSeek HTTP {status}; retry {retry_no} через {wait_s} сек.",
                    flush=True,
                )
                _ai_health_touch(ai_health, "busy_deepseek_retry", f"http={status}")
                time.sleep(wait_s)
                continue

            except (requests.Timeout, requests.ConnectionError) as exc:
                retry_no += 1
                wait_s = min(30, 3 * retry_no)
                print(
                    f"[AI] DeepSeek network {type(exc).__name__}; "
                    f"retry {retry_no} через {wait_s} сек.",
                    flush=True,
                )
                _ai_health_touch(
                    ai_health,
                    "busy_deepseek_retry",
                    f"{type(exc).__name__}: {exc}",
                )
                time.sleep(wait_s)
                continue
            except Exception as exc:
                plan = fallback_plan(
                    f"DeepSeek request: {type(exc).__name__}: {exc}"
                )
                _agent_clear_checkpoint(session_id)
                return plan, None

        try:
            msg = obj["choices"][0]["message"]
        except Exception:
            plan = fallback_plan(
                f"DeepSeek вернул неожиданный ответ: {str(obj)[:1200]}"
            )
            _agent_clear_checkpoint(session_id)
            return plan, None

        calls = msg.get("tool_calls") or []
        if calls:
            messages.append({
                "role": "assistant",
                "content": msg.get("content"),
                "tool_calls": calls,
            })

            for call in calls:
                fn = (call.get("function") or {}).get("name")
                raw_args = (call.get("function") or {}).get("arguments") or "{}"

                try:
                    args = json.loads(raw_args)
                except Exception as exc:
                    result = {
                        "ok": False,
                        "error": f"invalid tool arguments JSON: {exc}",
                    }
                else:
                    _ai_health_touch(ai_health, "busy_tool", fn)
                    result = _agent_execute_tool(
                        session_id,
                        state,
                        fn,
                        args,
                        cdp_urls,
                        action_queue=action_queue,
                        action_results=action_results,
                        ai_health=ai_health,
                        job_update_id=job_update_id,
                    )
                    _ai_health_touch(ai_health, "busy_deepseek", f"after_tool={fn}")

                remember_observation(fn, args if 'args' in locals() else {}, result)

                messages.append({
                    "role": "tool",
                    "tool_call_id": call.get("id"),
                    "content": json.dumps(result, ensure_ascii=False, default=str),
                })

                # Detect a real loop: exactly the same tool call producing exactly
                # the same result over and over.
                try:
                    signature = (
                        str(fn),
                        json.dumps(args, ensure_ascii=False, sort_keys=True, default=str),
                        compact_result(result),
                    )
                except Exception:
                    signature = (str(fn), str(raw_args), compact_result(result))

                if signature == last_effect_signature:
                    repeated_effect_count += 1
                else:
                    last_effect_signature = signature
                    repeated_effect_count = 1
                    loop_warning_sent = False

                if repeated_effect_count >= 5 and not loop_warning_sent:
                    messages.append({
                        "role": "user",
                        "content": (
                            "Ты повторяешь один и тот же tool с тем же результатом. "
                            "Это зацикливание. Не повторяй его: используй другой подход "
                            "или заверши задачу итогом по уже собранным данным."
                        ),
                    })
                    loop_warning_sent = True

                if repeated_effect_count >= 8:
                    plan = fallback_plan(
                        "обнаружено зацикливание: один и тот же tool/args/result "
                        "повторился 8 раз"
                    )
                    _agent_save_checkpoint(
                        session_id, user_text, messages, state, round_no
                    )
                    return plan, None

            _agent_save_checkpoint(
                session_id, user_text, messages, state, round_no
            )

            if state["finished"]:
                break
            continue

        plain = str(msg.get("content") or "").strip()
        if plain:
            state["summary"] = plain
            state["finished"] = True
            _agent_save_checkpoint(
                session_id, user_text, messages, state, round_no
            )
            break

        # Empty model turn is not a reason to discard the whole task.
        messages.append({
            "role": "user",
            "content": (
                "Предыдущий ответ был пустым. Продолжи текущую задачу с уже "
                "собранным контекстом. Не начинай анализ заново."
            ),
        })
        _agent_save_checkpoint(
            session_id, user_text, messages, state, round_no
        )

    # Syntax-check candidate files before offering apply.
    for rel in sorted(state["changed"]):
        fp = _agent_candidate_path(session_id, rel)
        try:
            _agent_compile_candidate_if_python(fp)
        except Exception as exc:
            plan = fallback_plan(
                f"Candidate {rel} не прошёл compile: {exc}"
            )
            _agent_clear_checkpoint(session_id)
            return plan, None

    plan = {
        "id": session_id,
        "created": time.time(),
        "summary": state["summary"] or "Изменение проекта",
        "verification": state["verification"],
        "files": sorted(state["changed"]),
        "deletes": sorted(state["deleted"]),
        "runtime_actions": state["runtime_actions"],
        "candidate_dir": str(session_dir),
        "needs_apply": bool(state["changed"] or state["deleted"]),
    }

    AI_AGENT_PENDING_FILE.write_text(
        json.dumps(plan, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    _agent_clear_checkpoint(session_id)
    return plan, None



def _agent_backup_project(tag):
    root = Path(__file__).resolve().parent
    backup = AI_AGENT_BACKUP_ROOT / str(tag)
    backup.mkdir(parents=True, exist_ok=False)
    original = []
    for fp in root.rglob("*"):
        if not fp.is_file():
            continue
        rel = fp.relative_to(root)
        if any(part in AI_AGENT_EXCLUDED_DIRS for part in rel.parts):
            continue
        if rel.name == AI_AGENT_PENDING_FILE.name:
            continue
        original.append(rel.as_posix())
        dest = backup / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(fp, dest)
    (backup / "_manifest.json").write_text(
        json.dumps({"original_files": original}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return backup


def _agent_restore_backup(backup, touched=None):
    root = Path(__file__).resolve().parent
    manifest_file = backup / "_manifest.json"
    manifest = json.loads(manifest_file.read_text(encoding="utf-8")) if manifest_file.exists() else {}
    originals = set(manifest.get("original_files") or [])

    # Remove files created by the failed/applied candidate when they did not
    # exist in the backup.
    for rel in (touched or []):
        if rel not in originals:
            target = root / rel
            try:
                if target.is_file():
                    target.unlink()
            except Exception:
                pass

    for fp in backup.rglob("*"):
        if not fp.is_file() or fp.name == "_manifest.json":
            continue
        rel = fp.relative_to(backup)
        dest = root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(fp, dest)


def _apply_agent_candidate(plan):
    root = Path(__file__).resolve().parent
    session_id = str(plan.get("id") or "")
    candidate_dir = AI_AGENT_CANDIDATE_ROOT / session_id
    if not candidate_dir.exists():
        return False, "Candidate-папка не найдена."

    tag = time.strftime("%Y%m%d_%H%M%S") + "_" + session_id
    backup = _agent_backup_project(tag)
    touched = set(plan.get("files") or []) | set(plan.get("deletes") or [])
    try:
        for rel in plan.get("files") or []:
            safe = _agent_safe_rel(rel)
            src = candidate_dir / safe
            if not src.exists() or not src.is_file():
                raise RuntimeError(f"candidate-файл отсутствует: {rel}")
            dest = _agent_live_path(rel)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)

        for rel in plan.get("deletes") or []:
            target = _agent_live_path(rel)
            if target.exists() and target.is_file():
                target.unlink()

        # Compile every Python source in the actual project after applying.
        for fp in root.rglob("*.py"):
            rel = fp.relative_to(root)
            if any(part in AI_AGENT_EXCLUDED_DIRS for part in rel.parts):
                continue
            compile(fp.read_text(encoding="utf-8"), str(fp), "exec")

        return True, (
            f"Candidate применён. Backup: {backup.name}. "
            f"Изменено: {len(plan.get('files') or [])}, удалено: {len(plan.get('deletes') or [])}."
        )
    except Exception as exc:
        _agent_restore_backup(backup, touched=touched)
        return False, f"Ошибка проверки; выполнен rollback: {type(exc).__name__}: {exc}"


def _rollback_latest_agent_backup():
    if not AI_AGENT_BACKUP_ROOT.exists():
        return False, "Backup отсутствует."
    items = sorted(
        [x for x in AI_AGENT_BACKUP_ROOT.iterdir() if x.is_dir()],
        key=lambda x: x.stat().st_mtime,
        reverse=True,
    )
    if not items:
        return False, "Backup отсутствует."
    backup = items[0]
    try:
        _agent_restore_backup(backup)
        return True, f"Откат к {backup.name} выполнен."
    except Exception as exc:
        return False, f"Rollback error: {type(exc).__name__}: {exc}"


def _looks_like_developer_request(text):
    low = str(text or "").lower()
    triggers = (
        "исправ", "фикс", "почини", "патч", "ошиб", "завис", "таймаут", "timeout",
        "не работает", "не запуска", "не наж", "не перех", "recovery",
        "измени", "добав", "доработ", "передел", "сделай", "хочу чтобы",
        "обнови код", "обновление", "рефактор", "убери", "замени",
    )
    return any(x in low for x in triggers)


def _operator_needs_tools(text):
    low = str(text or "").lower().strip()
    if not low:
        return False
    # Explicit operator prefix always forces the tool-capable route.
    if low.startswith(("/op ", "/operator ", "оператор ")):
        return True

    technical = (
        "ошиб", "баг", "фикс", "исправ", "почини", "не работает", "завис",
        "таймаут", "timeout", "вклад", "tab ", "таб ", "брауз", "chrom",
        "консол", "traceback", "стектрейс", "лог", "network", "сеть",
        "devtools", "dom", "html", "процесс", "worker", "воркер",
        "очеред", "статус", "состояни", "что там", "как там",
        "проверь", "посмотри", "диагност", "почему", "перезап",
        "закрой", "открой", "клик", "нажм", "введ", "запусти",
        "код", "файл", "добав", "измени", "доработ", "передел",
        "esim", "sim ", "успех", "success", "heartbeat", "matcher",
        "protected", "confirm", "resend", "cancelling",
    )
    return any(token in low for token in technical)



def _explicit_code_change_request(text):
    low = str(text or "").lower().strip()
    if not low:
        return False
    triggers = (
        "фикс", "исправь", "почини", "сделай фикс", "сделай обновление",
        "обнови код", "измени код", "добавь", "доработ", "передел",
        "рефактор", "убери из кода", "замени в коде", "патч",
    )
    return any(x in low for x in triggers)



def _explicit_live_action_request(text):
    low = str(text or "").lower().strip()
    if not low:
        return False
    if low.startswith("[auto_success_assist") or low.startswith("[auto_error_assist"):
        return True
    triggers = (
        "нажми", "кликни", "введи", "заполни", "напечатай",
        "перезагрузи", "reload", "обнови вкладку",
        "перейди на", "открой страницу", "назад", "вперёд", "вперед",
        "закрой вклад", "перезапусти", "рестарт", "restart",
        "выполни команд", "запусти команд", "в терминале",
        "/op ", "/operator ", "оператор ",
    )
    return any(x in low for x in triggers)


def _explicit_tab_lifecycle_request(text):
    low = str(text or "").lower().strip()
    return any(x in low for x in (
        "перезагрузи", "reload", "обнови вкладку",
        "закрой вклад", "перезапусти", "рестарт", "restart",
        "перейди на", "назад", "вперёд", "вперед",
    ))


def _explicit_terminal_request(text):
    low = str(text or "").lower().strip()
    return any(x in low for x in (
        "выполни команд", "запусти команд", "в терминале", "powershell", "cmd ",
    ))



def _chat_memory_tail(limit=24):
    try:
        lines = AI_CHAT_MEMORY_FILE.read_text(encoding="utf-8").splitlines()[-limit:]
        return "\n".join(lines)
    except Exception:
        return ""

def _chat_memory_append(role, text_value):
    try:
        with AI_CHAT_MEMORY_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps({
                "time": time.strftime("%Y-%m-%d %H:%M:%S"),
                "role": role,
                "text": str(text_value)[:12000],
            }, ensure_ascii=False) + "\n")
    except Exception:
        pass

def _ai_memory_tail(limit=20):
    try:
        lines = AI_MEMORY_FILE.read_text(encoding="utf-8").splitlines()[-limit:]
        return "\n".join(lines)
    except Exception:
        return ""


def _ai_memory_append(role, text_value):
    try:
        with AI_MEMORY_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps({
                "time": time.strftime("%Y-%m-%d %H:%M:%S"),
                "role": role,
                "text": str(text_value)[:12000],
            }, ensure_ascii=False) + "\n")
    except Exception:
        pass


def deepseek_vision_request(prompt, images=None, timeout=90, *, system_prompt=None):
    """DeepSeek Flash request. Images are passed from memory, never via disk."""
    cfg = load_deepseek_config()
    key = str(cfg.get("api_key", "")).strip()
    if not key:
        return None, "deepseek_config.json: отсутствует api_key"
    try:
        import requests, base64
    except ImportError:
        return None, 'Нужен requests: python -m pip install requests'

    content = [{"type": "text", "text": prompt}]
    for raw in images or []:
        b64 = base64.b64encode(raw).decode("ascii")
        content.append({
            "type": "image_url",
            "image_url": {
                "url": "data:image/png;base64," + b64,
                "detail": "low",
            },
        })

    current_system = system_prompt or _io1591.build_system(globals(), {}, [], str(prompt))
    payload = {
        "model": str(cfg.get("model") or "deepseek-flash"),
        "messages": _io1591.canonical_messages([{ "role": "user", "content": content}], current_system),
        "temperature": 0.2,
        "max_tokens": 1800,
    }
    _io1591.request_audit(payload, "chat")
    try:
        r = requests.post(
            "https://api.deepseek.com/chat/completions",
            headers={
                "Authorization": "Bearer " + key,
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=timeout,
        )
        obj = r.json()
        if not r.ok:
            return None, f"DeepSeek HTTP {r.status_code}: {obj}"
        choice = obj["choices"][0]
        text = choice["message"].get("content")
        if not isinstance(text, str) or not text.strip():
            return None, "DeepSeek вернул пустой ответ; выполнение не подтверждено."
        if choice.get("finish_reason") == "length":
            text += "\n\n[API ограничил длину ответа. Это не подтверждение завершения задачи.]"
        return text, None
    except Exception as exc:
        return None, f"{type(exc).__name__}: {exc}"




_BROWSER_TELEMETRY_JS = r"""
(() => {
  if (window.__deepseekTelemetryInstalled) return true;
  window.__deepseekTelemetryInstalled = true;
  const cap = (arr, item, max=500) => {
    arr.push(item);
    if (arr.length > max) arr.splice(0, arr.length - max);
  };
  const safe = (v) => {
    try {
      if (typeof v === 'string') return v;
      return JSON.stringify(v);
    } catch (_) {
      try { return String(v); } catch (_) { return '<unprintable>'; }
    }
  };
  const store = window.__deepseekTelemetry = window.__deepseekTelemetry || {
    console: [], errors: [], network: []
  };

  for (const level of ['log','info','warn','error','debug']) {
    const original = console[level] && console[level].bind(console);
    if (!original || original.__deepseekWrapped) continue;
    const wrapped = (...args) => {
      cap(store.console, {
        ts: Date.now(), level, text: args.map(safe).join(' ')
      });
      return original(...args);
    };
    wrapped.__deepseekWrapped = true;
    console[level] = wrapped;
  }

  window.addEventListener('error', (e) => {
    cap(store.errors, {
      ts: Date.now(),
      type: 'error',
      message: e.message || '',
      filename: e.filename || '',
      lineno: e.lineno || 0,
      colno: e.colno || 0,
      stack: e.error && e.error.stack ? String(e.error.stack) : ''
    });
  }, true);

  window.addEventListener('unhandledrejection', (e) => {
    const r = e.reason;
    cap(store.errors, {
      ts: Date.now(),
      type: 'unhandledrejection',
      message: safe(r),
      stack: r && r.stack ? String(r.stack) : ''
    });
  });

  if (window.fetch && !window.fetch.__deepseekWrapped) {
    const originalFetch = window.fetch.bind(window);
    const wrappedFetch = async (...args) => {
      const input = args[0];
      const init = args[1] || {};
      const url = typeof input === 'string' ? input : (input && input.url) || '';
      const method = (init.method || (input && input.method) || 'GET').toUpperCase();
      const started = Date.now();
      try {
        const response = await originalFetch(...args);
        cap(store.network, {
          ts: started, kind: 'fetch', method, url,
          status: response.status, ok: response.ok,
          duration_ms: Date.now() - started
        });
        return response;
      } catch (err) {
        cap(store.network, {
          ts: started, kind: 'fetch', method, url,
          error: safe(err), duration_ms: Date.now() - started
        });
        throw err;
      }
    };
    wrappedFetch.__deepseekWrapped = true;
    window.fetch = wrappedFetch;
  }

  if (window.XMLHttpRequest && !XMLHttpRequest.prototype.__deepseekWrapped) {
    const open = XMLHttpRequest.prototype.open;
    const send = XMLHttpRequest.prototype.send;
    XMLHttpRequest.prototype.open = function(method, url, ...rest) {
      this.__dsMethod = String(method || 'GET').toUpperCase();
      this.__dsUrl = String(url || '');
      return open.call(this, method, url, ...rest);
    };
    XMLHttpRequest.prototype.send = function(...args) {
      const started = Date.now();
      const xhr = this;
      const done = () => {
        cap(store.network, {
          ts: started, kind: 'xhr',
          method: xhr.__dsMethod || 'GET',
          url: xhr.__dsUrl || '',
          status: xhr.status || 0,
          duration_ms: Date.now() - started
        });
      };
      xhr.addEventListener('loadend', done, {once:true});
      xhr.addEventListener('error', () => {
        cap(store.network, {
          ts: started, kind: 'xhr',
          method: xhr.__dsMethod || 'GET',
          url: xhr.__dsUrl || '',
          error: 'XHR error',
          duration_ms: Date.now() - started
        });
      }, {once:true});
      return send.apply(this, args);
    };
    XMLHttpRequest.prototype.__deepseekWrapped = true;
  }
  return true;
})()
"""


def _install_browser_telemetry(page):
    try:
        page.add_init_script(_BROWSER_TELEMETRY_JS)
    except Exception:
        pass
    try:
        page.evaluate(_BROWSER_TELEMETRY_JS)
    except Exception:
        pass


def _find_worker_page_in_browser(browser, tab_id):
    prefix = f"esim-worker-{int(tab_id)}-"
    legacy = f"esim-worker-{int(tab_id)}"
    matches = []
    for context in browser.contexts:
        for page in context.pages:
            try:
                name = str(page.evaluate("() => window.name || ''"))
                if name == legacy or name.startswith(prefix):
                    matches.append(page)
            except Exception:
                continue
    return matches[-1] if matches else None




def _find_exact_worker_page(browser, expected_window_name):
    expected = str(expected_window_name or "")
    if not expected:
        return None
    for context in browser.contexts:
        for page in context.pages:
            try:
                if str(page.evaluate("() => window.name || ''")) == expected:
                    return page
            except Exception:
                continue
    return None


def _with_exact_worker_page(cdp_url, expected_window_name, action):
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(cdp_url)
        page = _find_exact_worker_page(browser, expected_window_name)
        if page is None:
            raise RuntimeError(
                f"physical worker page not found: {expected_window_name}"
            )
        _install_browser_telemetry(page)
        return action(page)


def _current_worker_identity(cdp_urls, tab_id):
    """Read-only snapshot used when the Operator requests a host-controlled action."""
    prefix = f"esim-worker-{int(tab_id)}-"
    legacy = f"esim-worker-{int(tab_id)}"
    matches = []
    with sync_playwright() as p:
        for browser_no, cdp_url in enumerate(cdp_urls, 1):
            try:
                browser = p.chromium.connect_over_cdp(cdp_url)
            except Exception:
                continue
            for context in browser.contexts:
                for page in context.pages:
                    try:
                        name = str(page.evaluate("() => window.name || ''"))
                    except Exception:
                        continue
                    if name == legacy or name.startswith(prefix):
                        matches.append((browser_no, page, name))
        if not matches:
            return None
        browser_no, page, name = matches[-1]
        try:
            url = page.url
        except Exception:
            url = ""
        return {
            "tab": int(tab_id),
            "browser": int(browser_no),
            "window_name": name,
            "url": url,
        }


def _with_live_worker_page(cdp_urls, tab_id, action):
    """Connect to the real Chromium tab, perform an action, and leave Chromium running."""
    last_error = None
    with sync_playwright() as p:
        for cdp_url in cdp_urls:
            try:
                browser = p.chromium.connect_over_cdp(cdp_url)
                page = _find_worker_page_in_browser(browser, tab_id)
                if page is None:
                    continue
                _install_browser_telemetry(page)
                return action(page)
            except Exception as exc:
                last_error = exc
                continue
    if last_error:
        raise RuntimeError(f"TAB {tab_id}: {type(last_error).__name__}: {last_error}")
    raise RuntimeError(f"TAB {tab_id}: живая worker-вкладка не найдена")


def _browser_tabs_snapshot(cdp_urls):
    result = []
    with sync_playwright() as p:
        for browser_no, cdp_url in enumerate(cdp_urls, 1):
            try:
                browser = p.chromium.connect_over_cdp(cdp_url)
            except Exception as exc:
                result.append({
                    "browser": browser_no,
                    "error": f"{type(exc).__name__}: {exc}",
                })
                continue
            for context in browser.contexts:
                for page in context.pages:
                    try:
                        worker_name = str(page.evaluate("() => window.name || ''"))
                    except Exception:
                        worker_name = ""
                    m = re.fullmatch(r"esim-worker-(\d+)(?:-p\d+-g\d+)?", worker_name)
                    try:
                        result.append({
                            "browser": browser_no,
                            "tab": int(m.group(1)) if m else None,
                            "window_name": worker_name,
                            "url": page.url,
                            "title": page.title(),
                        })
                    except Exception:
                        pass
    return result


def _browser_state(page, include_html=False):
    _install_browser_telemetry(page)
    data = page.evaluate(r"""() => {
        const body = document.body;
        const text = body ? (body.innerText || '') : '';
        const active = document.activeElement;
        return {
          url: location.href,
          title: document.title,
          windowName: window.name || '',
          readyState: document.readyState,
          text: text.slice(0, 40000),
          activeElement: active ? {
            tag: active.tagName, id: active.id || '',
            name: active.getAttribute('name') || '',
            type: active.getAttribute('type') || '',
            value: ('value' in active ? String(active.value || '') : '')
          } : null,
          viewport: {width: innerWidth, height: innerHeight},
          scroll: {x: scrollX, y: scrollY}
        };
    }""")
    if include_html:
        try:
            data["html"] = page.content()[:120000]
        except Exception as exc:
            data["html_error"] = str(exc)
    return data


def _browser_telemetry(page, max_items=200):
    _install_browser_telemetry(page)
    return page.evaluate(r"""(maxItems) => {
      const s = window.__deepseekTelemetry || {console:[], errors:[], network:[]};
      const resources = performance.getEntriesByType('resource').slice(-maxItems).map(x => ({
        name: x.name, initiatorType: x.initiatorType,
        duration_ms: Math.round(x.duration),
        transferSize: x.transferSize || 0
      }));
      return {
        console: (s.console || []).slice(-maxItems),
        errors: (s.errors || []).slice(-maxItems),
        network: (s.network || []).slice(-maxItems),
        resources
      };
    }""", int(max_items))


def _browser_inspect(page, selector=None, text=None, max_items=50):
    _install_browser_telemetry(page)
    return page.evaluate(r"""({selector, textQuery, maxItems}) => {
      const visible = (el) => {
        const r = el.getBoundingClientRect();
        const s = getComputedStyle(el);
        return !!(r.width || r.height) && s.display !== 'none' && s.visibility !== 'hidden';
      };
      let nodes = [];
      if (selector) {
        try { nodes = Array.from(document.querySelectorAll(selector)); }
        catch (e) { return {error: 'Invalid selector: ' + e.message}; }
      } else {
        nodes = Array.from(document.querySelectorAll(
          'button,input,textarea,select,a,[role],[contenteditable="true"]'
        ));
      }
      if (textQuery) {
        const q = textQuery.toLowerCase();
        nodes = nodes.filter(el => ((el.innerText || el.textContent || el.value || '') + '')
          .toLowerCase().includes(q));
      }
      return nodes.slice(0, maxItems).map((el, i) => {
        const r = el.getBoundingClientRect();
        const attrs = {};
        for (const a of el.attributes || []) attrs[a.name] = a.value;
        return {
          index:i, tag:el.tagName, text:(el.innerText || el.textContent || '').trim().slice(0,1000),
          value:('value' in el ? String(el.value || '') : ''),
          visible:visible(el), disabled:!!el.disabled,
          checked:('checked' in el ? !!el.checked : null),
          attrs, rect:{x:r.x,y:r.y,width:r.width,height:r.height}
        };
      });
    }""", {
        "selector": selector or "",
        "textQuery": text or "",
        "maxItems": int(max_items),
    })


def _browser_click(page, args):
    selector = str(args.get("selector") or "").strip()
    text_value = str(args.get("text") or "").strip()
    role = str(args.get("role") or "").strip()
    name = str(args.get("name") or "").strip()
    if args.get("x") is not None and args.get("y") is not None:
        page.mouse.click(float(args["x"]), float(args["y"]))
        return {"ok": True, "method": "coordinates"}
    if selector:
        loc = page.locator(selector).first
    elif role and name:
        loc = page.get_by_role(role, name=re.compile(re.escape(name), re.I)).first
    elif text_value:
        loc = page.get_by_text(re.compile(re.escape(text_value), re.I), exact=False).first
    else:
        raise ValueError("нужен selector, text, role+name или x+y")
    loc.scroll_into_view_if_needed(timeout=5000)
    loc.click(timeout=int(args.get("timeout_ms") or 10000), force=bool(args.get("force", False)))
    return {"ok": True, "url": page.url}


def _browser_fill(page, args):
    selector = str(args.get("selector") or "").strip()
    if not selector:
        raise ValueError("selector обязателен")
    loc = page.locator(selector).first
    loc.scroll_into_view_if_needed(timeout=5000)
    loc.fill(str(args.get("value") or ""), timeout=int(args.get("timeout_ms") or 10000))
    return {"ok": True, "value": loc.input_value(timeout=3000)}


def _browser_tool(cdp_urls, name, args):
    tab = int(args.get("tab") or 0) if "tab" in args else None
    if name == "list_browser_tabs":
        return {"ok": True, "tabs": _browser_tabs_snapshot(cdp_urls)}
    if name == "browser_open_page":
        browser_no = int(args.get("browser") or 1)
        if not 1 <= browser_no <= len(cdp_urls):
            return {"ok": False, "error": "browser должен быть 1 или 2"}
        try:
            with sync_playwright() as p:
                browser = p.chromium.connect_over_cdp(cdp_urls[browser_no-1])
                contexts = browser.contexts
                context = contexts[0] if contexts else browser.new_context()
                page = context.new_page()
                page.goto(str(args.get("url") or "about:blank"), wait_until="domcontentloaded", timeout=30000)
                return {"ok": True, "url": page.url, "title": page.title()}
        except Exception as exc:
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    if not tab:
        return {"ok": False, "error": "tab обязателен"}

    def action(page):
        if name == "get_page_state":
            return {"ok": True, "state": _browser_state(page, bool(args.get("include_html", False)))}
        if name == "read_browser_devtools":
            return {"ok": True, "telemetry": _browser_telemetry(page, args.get("max_items", 200))}
        if name == "inspect_dom":
            return {"ok": True, "elements": _browser_inspect(
                page, args.get("selector"), args.get("text"), args.get("max_items", 50)
            )}
        if name == "browser_click":
            return _browser_click(page, args)
        if name == "browser_fill":
            return _browser_fill(page, args)
        if name == "browser_press":
            selector = str(args.get("selector") or "").strip()
            key = str(args.get("key") or "")
            if selector:
                page.locator(selector).first.press(key, timeout=int(args.get("timeout_ms") or 10000))
            else:
                page.keyboard.press(key)
            return {"ok": True}
        if name == "browser_type":
            selector = str(args.get("selector") or "").strip()
            value = str(args.get("value") or "")
            delay = int(args.get("delay_ms") or 0)
            if selector:
                page.locator(selector).first.type(value, delay=delay, timeout=int(args.get("timeout_ms") or 10000))
            else:
                page.keyboard.type(value, delay=delay)
            return {"ok": True}
        if name == "browser_evaluate_js":
            result = page.evaluate(str(args.get("script") or ""))
            try:
                json.dumps(result)
            except Exception:
                result = repr(result)
            return {"ok": True, "result": result}
        if name == "browser_navigate":
            page.goto(
                str(args.get("url") or ""),
                wait_until=str(args.get("wait_until") or "domcontentloaded"),
                timeout=int(args.get("timeout_ms") or 30000),
            )
            return {"ok": True, "url": page.url, "title": page.title()}
        if name == "browser_reload":
            page.reload(wait_until="domcontentloaded", timeout=int(args.get("timeout_ms") or 30000))
            return {"ok": True, "url": page.url}
        if name == "browser_back":
            page.go_back(wait_until="domcontentloaded", timeout=int(args.get("timeout_ms") or 30000))
            return {"ok": True, "url": page.url}
        if name == "browser_forward":
            page.go_forward(wait_until="domcontentloaded", timeout=int(args.get("timeout_ms") or 30000))
            return {"ok": True, "url": page.url}
        if name == "browser_wait":
            page.wait_for_timeout(int(args.get("milliseconds") or 1000))
            return {"ok": True, "url": page.url}
        if name == "browser_cookies":
            cookies = page.context.cookies()
            return {"ok": True, "cookies": cookies}
        if name == "browser_clear_telemetry":
            page.evaluate("""() => {
              const s = window.__deepseekTelemetry;
              if (s) { s.console=[]; s.errors=[]; s.network=[]; }
            }""")
            return {"ok": True}
        if name == "browser_close_tab":
            current = page.url
            page.close()
            return {"ok": True, "closed_url": current}
        raise ValueError(f"неизвестный browser tool: {name}")
    try:
        return _with_live_worker_page(cdp_urls, tab, action)
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


def _run_operator_terminal(command, timeout=120, cwd=None):
    """Run a real local shell command with the same OS rights as this Python process."""
    import subprocess
    root = Path(__file__).resolve().parent
    real_cwd = str(Path(cwd).expanduser()) if cwd else str(root)
    try:
        cp = subprocess.run(
            str(command),
            cwd=real_cwd,
            shell=True,
            text=True,
            capture_output=True,
            timeout=max(1, min(int(timeout or 120), 600)),
            encoding="utf-8",
            errors="replace",
        )
        return {
            "ok": cp.returncode == 0,
            "returncode": cp.returncode,
            "stdout": (cp.stdout or "")[-50000:],
            "stderr": (cp.stderr or "")[-50000:],
            "cwd": real_cwd,
        }
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}", "cwd": real_cwd}


# OBSERVER_TIMEOUT_1591R11
OBSERVER_COLLECT_TIMEOUT_SECONDS = 45
AI_LANE_BUSY_CEILING_SECONDS = 900


def _observer_collect_pages(cdp_urls, with_screenshots=True, timeout=None):
    """Bounded page collection for the DeepSeek lanes.

    page.evaluate has no timeout in Playwright: on a page that stopped answering (a tab
    being replaced, a hung renderer) it never returns, the lane stays in busy_browser and
    the supervisor leaves it alone. The unbounded collector therefore runs in its own
    thread with its own Playwright instance; if it exceeds the deadline the lane process
    exits and the parent respawns it, releasing its inbox claims.
    """
    import threading
    limit = float(OBSERVER_COLLECT_TIMEOUT_SECONDS if timeout is None else timeout)
    outcome = {}

    def run():
        try:
            outcome["pages"] = _observer_collect_pages_unbounded(cdp_urls, with_screenshots=with_screenshots)
        except BaseException as exc:  # re-raised in the caller
            outcome["error"] = exc

    worker = threading.Thread(target=run, name="observer-collect-1591", daemon=True)
    worker.start()
    worker.join(limit)
    if worker.is_alive():
        print(
            f"[AI] Сбор страниц не завершился за {limit:.0f} с (evaluate завис на неотвечающей "
            "вкладке) — процесс наблюдателя завершается, родитель перезапустит его.",
            flush=True,
        )
        os._exit(3)
    if "error" in outcome:
        raise outcome["error"]
    return outcome.get("pages", [])


def _observer_collect_pages_unbounded(cdp_urls, with_screenshots=True):
    """Connects read-only to both Chromium instances and snapshots worker pages.

    Unbounded: call _observer_collect_pages, which adds the deadline.
    """
    collected = []
    with sync_playwright() as p:
        for browser_no, cdp_url in enumerate(cdp_urls, 1):
            try:
                browser = p.chromium.connect_over_cdp(cdp_url)
            except Exception as exc:
                collected.append({
                    "tab_id": None, "browser": browser_no,
                    "error": f"CDP: {type(exc).__name__}: {exc}",
                    "image": None,
                })
                continue
            try:
                for context in browser.contexts:
                    for page in context.pages:
                        try:
                            worker_name = page.evaluate("() => window.name || ''")
                        except Exception:
                            continue
                        m = re.fullmatch(r"esim-worker-(\d+)(?:-p\d+-g\d+)?", str(worker_name))
                        if not m:
                            continue
                        tab_id = int(m.group(1))
                        try:
                            url = page.url
                            title = page.title()
                        except Exception:
                            url, title = "", ""
                        _install_browser_telemetry(page)
                        collected.append({
                            "tab_id": tab_id,
                            "browser": browser_no,
                            "url": url,
                            "title": title,
                            "page": page,
                            "image": None,
                        })
                # Keep CDP connection alive until optional screenshots below are done.
                if with_screenshots:
                    for item in collected:
                        if item.get("browser") != browser_no or not item.get("page"):
                            continue
                        try:
                            item["image"] = item["page"].screenshot(
                                type="png", full_page=False, timeout=8000
                            )
                        except Exception as exc:
                            item["screenshot_error"] = f"{type(exc).__name__}: {exc}"
            finally:
                # ВАЖНО: browser.close() здесь закрыл бы настоящий Chromium.
                # Просто выходим из Playwright-сессии наблюдателя; рабочий браузер не трогаем.
                pass
    return collected




def _chat_prompt(status_map, pages, user_text):
    return _io1591.chat_context(globals(), status_map, pages, user_text)

def _observer_prompt(status_map, pages, user_text=None):
    try:
        rules = PROJECT_RULES_FILE.read_text(encoding="utf-8")
    except Exception:
        rules = ""
    statuses = []
    for i in range(1, TAB_COUNT + 1):
        info = status_map.get(str(i)) or {}
        statuses.append(f"TAB {i}: {info.get('text','нет статуса')}")
    page_lines = []
    for p in pages:
        if p.get("tab_id"):
            page_lines.append(
                f"TAB {p['tab_id']} browser={p.get('browser')} "
                f"url={p.get('url','')} title={p.get('title','')}"
            )
    request = user_text or (
        "Проведи контрольное наблюдение. Сообщай только о явных нарушениях правил, "
        "зависании, рассинхронизации UI и worker state или повторяющейся системной ошибке. "
        "Если всё выглядит штатно, ответь ровно: OK"
    )
    return f"""Ты DeepSeek Observer — автоматический технический наблюдатель работающей программы.
ПРАВИЛА ПРОЕКТА:
{rules}

ТЕКУЩИЕ СТАТУСЫ:
{chr(10).join(statuses)}

СТРАНИЦЫ:
{chr(10).join(page_lines)}

ПОСЛЕДНИЕ СТРОКИ КОНСОЛИ:
{_runtime_console_tail(max_lines=120, max_chars=22000)}

ПОСЛЕДНИЙ ДИАЛОГ:
{_ai_memory_tail()}

ЗАДАЧА/СООБЩЕНИЕ ПОЛЬЗОВАТЕЛЯ:
{request}

Отвечай по-русски, конкретно. Если пользователь указывает правильное ожидаемое
поведение, учитывай его как уточнение правил проекта."""


def ai_observer_process(status_map, cdp_urls, stop_event, ai_health, action_queue, action_results, lane='fast'):
    """DeepSeek Operator. Telegram reception is owned by a separate receiver."""
    tg_cfg = load_telegram_config()
    chat = str(tg_cfg.get("chat_id", "")).strip()
    if not chat:
        print("[AI] Нет Telegram chat_id; operator отключён.", flush=True)
        return

    lane = str(lane or "fast")
    consumer_id = f"{lane}:{os.getpid()}"
    lease_seconds = 90 if lane == "fast" else 180
    print(
        f"[AI {lane.upper()}] Operator process стартовал PID={os.getpid()}.",
        flush=True,
    )
    last_observe = 0.0

    while not stop_event.is_set():
        _ai_health_touch(ai_health, "idle")

        job = None
        try:
            job = _ai_db_next_message(
                lane=lane,
                consumer_id=consumer_id,
                lease_seconds=lease_seconds,
            )
        except Exception as exc:
            print(
                f"[AI] Inbox read error: {type(exc).__name__}: {exc}",
                flush=True,
            )
            _ai_health_touch(ai_health, "inbox_error", exc)
            time.sleep(2)
            continue

        if not job:
            # Local/CDP telemetry maintenance only; no paid AI request.
            try:
                if monotonic() - last_observe >= 5:
                    _ai_health_touch(ai_health, "busy_browser", "telemetry_bootstrap")
                    if cdp_urls:
                        _observer_collect_pages(cdp_urls, with_screenshots=False)
                    last_observe = monotonic()
            except Exception:
                pass
            _ai_health_touch(ai_health, "idle")
            time.sleep(1)
            continue

        update_id = job["update_id"]
        latest = job["body"].strip()
        low = latest.lower()
        print(
            f"[AI {lane.upper()}] Обрабатываю update {update_id}: {latest[:120]}",
            flush=True,
        )

        try:
            _ai_health_touch(ai_health, "busy_browser", f"update={update_id}")
            pages = _observer_collect_pages(cdp_urls, with_screenshots=False) if cdp_urls else []
            images = []

            response_text = None

            # Compatibility for a stale pending candidate from an older build.
            if low in {"ок", "да", "применить", "apply"} and AI_AGENT_PENDING_FILE.exists():
                try:
                    plan = json.loads(
                        AI_AGENT_PENDING_FILE.read_text(encoding="utf-8")
                    )
                    ok, msg = _apply_agent_candidate(plan)
                    if ok:
                        AI_AGENT_PENDING_FILE.unlink(missing_ok=True)
                    response_text = "🔧 DeepSeek Operator\n\n" + msg
                except Exception as exc:
                    response_text = (
                        "⚠️ Не удалось применить candidate: "
                        f"{type(exc).__name__}: {exc}"
                    )

            elif low in {"откат", "откатить", "rollback"}:
                _, msg = _rollback_latest_agent_backup()
                response_text = "↩️ " + msg

            else:
                if lane in {"fast", "chat"} and not _operator_needs_tools(latest):
                    # One API call, no project/browser audit for casual conversation.
                    _ai_health_touch(ai_health, "busy_deepseek", f"fast_chat update={update_id}")
                    fast_prompt = _chat_prompt(status_map, pages, latest)
                    answer, fast_err = deepseek_vision_request(
                        fast_prompt,
                        images=[],
                        timeout=300,
                        system_prompt=_io1591.build_system(globals(), status_map, pages, latest),
                    )
                    if fast_err:
                        response_text = "⚠️ DeepSeek: " + fast_err
                    else:
                        response_text = "🤖 DeepSeek Operator\n\n" + str(answer or "Готово.")
                    plan = None
                    dev_err = None
                else:
                    _ai_health_touch(ai_health, "busy_deepseek", f"update={update_id}")
                    plan, dev_err = _run_developer_agent(
                        status_map,
                        pages,
                        latest,
                        images,
                        cdp_urls,
                        ai_health=ai_health,
                        action_queue=action_queue,
                        action_results=action_results,
                        job_update_id=update_id,
                    )

                if response_text is not None:
                    pass
                elif dev_err:
                    response_text = "⚠️ Developer: " + dev_err
                else:
                    if plan.get("needs_apply"):
                        file_lines = [
                            "• " + x for x in (plan.get("files") or [])
                        ] + [
                            "• DELETE " + x for x in (plan.get("deletes") or [])
                        ]
                        verification = plan.get("verification") or []
                        verify_text = (
                            "\n\nПроверка:\n• " + "\n• ".join(verification)
                            if verification else ""
                        )
                        response_text = (
                            "🔧 DeepSeek подготовил фикс\n\n"
                            + str(plan.get("summary") or "")
                            + "\n\nФайлы:\n"
                            + "\n".join(file_lines)
                            + verify_text
                            + "\n\nНапиши «применить», чтобы сделать backup → apply → compile → rollback при ошибке."
                        )
                    else:
                        response_text = (
                            "🤖 DeepSeek Operator\n\n"
                            + str(plan.get("summary") or "Готово.")
                        )

            # Mark complete and queue the response in one local durable store.
            _ai_db_complete(
                update_id,
                job["chat_id"],
                (response_text or "🤖 DeepSeek Operator\n\nПустой результат; выполнение не подтверждено."),
            )
            _ai_health_touch(ai_health, "idle")
            print(f"[AI {lane.upper()}] update {update_id} завершён.", flush=True)

        except Exception as exc:
            err = f"{type(exc).__name__}: {exc}"
            print(f"[AI {lane.upper()}] Operator error update {update_id}: {err}", flush=True)
            _ai_db_fail(update_id, err, job.get("attempts", 1))
            _ai_health_touch(ai_health, "job_error", err)

        time.sleep(0.2)



def fill_test_signature(page, diagnostic=None):
    """Fill the visible signature pad with a test scribble crossing all four quadrants."""
    selectors = [
        "canvas",
        '[data-testid*="sign" i] canvas',
        '[class*="sign" i] canvas',
        '[class*="signature" i] canvas',
    ]
    canvas = None
    for selector in selectors:
        loc = page.locator(selector)
        for i in range(loc.count()):
            candidate = loc.nth(i)
            try:
                box = candidate.bounding_box()
                if candidate.is_visible() and box and box["width"] >= 250 and box["height"] >= 120:
                    canvas = candidate
                    break
            except Exception:
                pass
        if canvas is not None:
            break

    if canvas is None:
        raise RuntimeError("Поле графической подписи не найдено.")

    canvas.scroll_into_view_if_needed()
    box = canvas.bounding_box()
    if not box:
        raise RuntimeError("Не удалось получить координаты поля подписи.")

    x, y, w, h = box["x"], box["y"], box["width"], box["height"]

    # One continuous stroke deliberately visits every quadrant while staying
    # comfortably inside the pad borders.
    points = [
        (0.12, 0.28), (0.28, 0.18), (0.43, 0.36),   # top-left
        (0.58, 0.20), (0.82, 0.32),                 # top-right
        (0.68, 0.58), (0.86, 0.76),                 # bottom-right
        (0.55, 0.68), (0.40, 0.82), (0.18, 0.70),   # bottom-left
        (0.34, 0.54), (0.62, 0.46), (0.78, 0.62),
        (0.48, 0.74), (0.24, 0.48),
    ]

    page.mouse.move(x + points[0][0]*w, y + points[0][1]*h)
    page.mouse.down()
    try:
        for px, py in points[1:]:
            page.mouse.move(x + px*w, y + py*h, steps=5)
            page.wait_for_timeout(35)
    finally:
        page.mouse.up()

    page.wait_for_timeout(500)
    if diagnostic is not None:
        try:
            diagnostic.write("test_signature_drawn", width=w, height=h)
        except Exception:
            pass
    print("Тестовая подпись нарисована через все 4 квадранта.", flush=True)
    return True



def fill_signature_and_submit(page, diagnostic=None):
    """Draw the test signature, then click the visible 'Подписать договор' button by name."""
    fill_test_signature(page, diagnostic)

    # Prefer the accessible button name; fall back to visible text if the site
    # uses a non-standard button implementation.
    button = page.get_by_role(
        "button",
        name=re.compile(r"^\s*подписать\s+договор\s*$", re.I),
    )
    try:
        button.wait_for(state="visible", timeout=8000)
    except Exception:
        button = page.get_by_text(
            re.compile(r"^\s*подписать\s+договор\s*$", re.I),
            exact=False,
        )
        button.wait_for(state="visible", timeout=5000)

    deadline = monotonic() + 10
    while monotonic() < deadline:
        try:
            if button.is_visible() and button.is_enabled():
                break
        except Exception:
            pass
        page.wait_for_timeout(250)
    else:
        raise RuntimeError(
            "Кнопка «Подписать договор» найдена, но не стала активной после заполнения подписи."
        )

    old_url = page.url
    button.click(timeout=8000, no_wait_after=True)
    if diagnostic is not None:
        try:
            diagnostic.write("sign_contract_clicked", old_url=old_url)
        except Exception:
            pass
    print("Нажата кнопка «Подписать договор».", flush=True)

    # Do not blindly click twice. Give the page time to react and let the caller
    # continue from the resulting state.
    page.wait_for_timeout(1000)
    return True



def _regionize_beeline_url(url):
    try:
        parsed = urlsplit(str(url or ""))
        if not str(parsed.hostname or "").endswith(".beeline.ru"):
            return str(url or "")
        return urlunsplit((
            parsed.scheme or "https",
            REGION_HOST,
            parsed.path,
            parsed.query,
            parsed.fragment,
        ))
    except Exception:
        return str(url or "")


def ensure_region_page(page, diagnostic=None, timeout=25):
    """Force current Beeline registration URL onto the configured Saratov host."""
    try:
        current = page.url
        parsed = urlsplit(current)
    except Exception:
        return False

    if not str(parsed.hostname or "").endswith(".beeline.ru"):
        return False
    if parsed.hostname == REGION_HOST:
        return True

    target = _regionize_beeline_url(current)
    if not target or target == current:
        return parsed.hostname == REGION_HOST

    print(
        f"Регион страницы {parsed.hostname} → {REGION_HOST}. "
        "Открываю тот же registration URL в Саратове.",
        flush=True,
    )
    try:
        page.goto(target, wait_until="domcontentloaded", timeout=timeout * 1000)
        page.wait_for_timeout(700)
        ok = urlsplit(page.url).hostname == REGION_HOST
        if diagnostic is not None:
            try:
                diagnostic.write(
                    "region_host_corrected",
                    from_url=current,
                    target_url=target,
                    final_url=page.url,
                    ok=ok,
                )
            except Exception:
                pass
        return ok
    except Exception as exc:
        if diagnostic is not None:
            try:
                diagnostic.write(
                    "region_host_correction_failed",
                    from_url=current,
                    target_url=target,
                    error_type=type(exc).__name__,
                    error=str(exc)[:500],
                )
            except Exception:
                pass
        print(
            f"Не удалось перевести registration на {REGION_HOST}: "
            f"{type(exc).__name__}: {exc}",
            flush=True,
        )
        return False


def _phone_digits(value):
    return re.sub(r"\D", "", str(value or ""))


def _normalize_ru_phone(value):
    digits = _phone_digits(value)
    if len(digits) != 11:
        return None
    if digits.startswith("8"):
        digits = "7" + digits[1:]
    if not digits.startswith("7"):
        return None
    return "+" + digits


def capture_esim_offer_page(page, diagnostic=None, contact_phone=None, timeout=6):
    """Capture exact offer-page URL and the reserved eSIM number on that page."""
    offer_url = str(page.url or "")
    setattr(page, "_reserved_sim_url", offer_url)
    setattr(page, "_reserved_sim_url_locked", True)

    excluded = {_phone_digits(contact_phone)}
    excluded |= {
        x[1:] for x in list(excluded)
        if len(x) == 11 and x.startswith(("7", "8"))
    }

    best_number = None
    best_score = -10_000
    deadline = monotonic() + timeout

    while monotonic() < deadline and not best_number:
        candidates = []

        try:
            exact = page.locator(
                'xpath=//*[@id="root"]/div/div/main/div/div[1]/div/div/p[2]'
            )
            if exact.count() and exact.first.is_visible():
                candidates.append((
                    200,
                    (exact.first.inner_text(timeout=1000) or "").strip(),
                    "legacy_xpath",
                ))
        except Exception:
            pass

        try:
            blocks = page.evaluate(r"""() => {
                const out = [];
                const els = Array.from(document.querySelectorAll(
                    'p,span,div,strong,b,h1,h2,h3,h4,li'
                ));
                for (const el of els) {
                    const r = el.getBoundingClientRect();
                    const st = getComputedStyle(el);
                    if (!r.width || !r.height || st.display === 'none' || st.visibility === 'hidden') continue;
                    const txt = (el.innerText || el.textContent || '').trim();
                    if (!txt || txt.length > 500) continue;
                    if (/(?:\+?7|8)[\s()\-]*\d{3}[\s()\-]*\d{3}[\s\-]*\d{2}[\s\-]*\d{2}/.test(txt)) {
                        out.push(txt);
                    }
                }
                return [...new Set(out)].slice(0, 120);
            }""")
        except Exception:
            blocks = []

        for txt in blocks or []:
            low = str(txt).lower().replace("ё", "е")
            score = 0
            if "esim" in low or "e-sim" in low or "e sim" in low:
                score += 90
            if re.search(r"\bсим\b", low):
                score += 55
            if "номер" in low:
                score += 35
            if "ваш" in low or "зарезерв" in low or "выбран" in low:
                score += 20
            if "контакт" in low:
                score -= 120
            candidates.append((score, txt, "visible_text"))

        for base_score, txt, source in candidates:
            for m in re.finditer(
                r'(?:\+?7|8)[\s()\-]*\d{3}[\s()\-]*\d{3}[\s\-]*\d{2}[\s\-]*\d{2}',
                str(txt),
            ):
                normalized = _normalize_ru_phone(m.group(0))
                if not normalized:
                    continue
                digits = _phone_digits(normalized)
                national = digits[1:] if len(digits) == 11 else digits
                if digits in excluded or national in excluded:
                    continue
                if base_score > best_score:
                    best_score = base_score
                    best_number = normalized

        if not best_number:
            page.wait_for_timeout(200)

    if best_number:
        setattr(page, "_reserved_sim_number", best_number)

    if diagnostic is not None:
        try:
            diagnostic.write(
                "reserved_esim_offer_captured",
                sim_url=offer_url,
                sim_number=best_number,
                region_host=urlsplit(offer_url).hostname,
            )
        except Exception:
            pass

    print(
        f"eSIM offer сохранён: номер={best_number or 'не найден'} | {offer_url}",
        flush=True,
    )
    return bool(best_number)


def capture_reserved_sim(page, worker=None, timeout=4):
    """Capture reserved eSIM number + ORIGINAL eSIM page URL.

    Can be called before a worker dict exists. In that case the values are
    cached on the Playwright Page object and copied into worker memory later.
    """
    # Prefer an already remembered original eSIM URL. Never overwrite it with
    # a later registration/auth/success URL.
    remembered_url = ""
    try:
        remembered_url = getattr(page, "_reserved_sim_url", "") or ""
    except Exception:
        remembered_url = ""

    if worker is not None:
        remembered_url = worker.get("reserved_sim_url") or remembered_url

    try:
        current_url = page.url
    except Exception:
        current_url = ""

    url_locked = bool(getattr(page, "_reserved_sim_url_locked", False))
    if not remembered_url and current_url and not url_locked:
        remembered_url = current_url
        try:
            setattr(page, "_reserved_sim_url", remembered_url)
        except Exception:
            pass
        if worker is not None:
            worker["reserved_sim_url"] = remembered_url
    elif worker is not None and remembered_url and not worker.get("reserved_sim_url"):
        worker["reserved_sim_url"] = remembered_url

    # If the number was already captured earlier, just synchronize it to worker.
    remembered_number = ""
    try:
        remembered_number = getattr(page, "_reserved_sim_number", "") or ""
    except Exception:
        remembered_number = ""
    if worker is not None:
        remembered_number = worker.get("reserved_sim_number") or remembered_number

    if remembered_number:
        if worker is not None:
            worker["reserved_sim_number"] = remembered_number
        return True

    deadline = monotonic() + timeout
    found = None

    while monotonic() < deadline and not found:
        # Primary locator from the old working draft.
        candidates = [
            page.locator('xpath=//*[@id="root"]/div/div/main/div/div[1]/div/div/p[2]'),
            page.locator('[data-testid*="sim" i]'),
            page.locator('[class*="sim" i]'),
        ]

        for loc in candidates:
            try:
                count = min(loc.count(), 20)
                for i in range(count):
                    el = loc.nth(i)
                    if not el.is_visible():
                        continue
                    txt = (el.inner_text(timeout=1000) or "").strip()
                    for m in re.finditer(
                        r'(?:\+?7|8)[\s()\-]*\d{3}[\s()\-]*\d{3}[\s\-]*\d{2}[\s\-]*\d{2}',
                        txt,
                    ):
                        digits = re.sub(r"\D", "", m.group(0))
                        if len(digits) == 11:
                            found = "+" + (
                                "7" + digits[1:] if digits.startswith("8") else digits
                            )
                            break
                    if found:
                        break
            except Exception:
                pass
            if found:
                break

        # Fallback if the wrapper/XPath changed.
        if not found:
            try:
                body = page.locator("body").inner_text(timeout=1500)
                lines = [x.strip() for x in body.splitlines() if x.strip()]
                ranked = sorted(
                    lines,
                    key=lambda x: 0
                    if re.search(r'\be\s*sim\b|\bsim\b', x, re.I)
                    else 1,
                )
                for line in ranked:
                    m = re.search(
                        r'(?:\+?7|8)[\s()\-]*\d{3}[\s()\-]*\d{3}[\s\-]*\d{2}[\s\-]*\d{2}',
                        line,
                    )
                    if not m:
                        continue
                    digits = re.sub(r"\D", "", m.group(0))
                    if len(digits) == 11:
                        found = "+" + (
                            "7" + digits[1:] if digits.startswith("8") else digits
                        )
                        break
            except Exception:
                pass

        if not found:
            page.wait_for_timeout(200)

    tab_label = worker.get("id") if worker is not None else "pre-worker"

    if found:
        try:
            setattr(page, "_reserved_sim_number", found)
        except Exception:
            pass
        if worker is not None:
            worker["reserved_sim_number"] = found
            if remembered_url and not worker.get("reserved_sim_url"):
                worker["reserved_sim_url"] = remembered_url

        print(
            f"[Вкладка {tab_label}] Запомнил eSIM: {found} | "
            f"{remembered_url or current_url}",
            flush=True,
        )
        return True

    print(
        f"[Вкладка {tab_label}] URL eSIM сохранён: "
        f"{remembered_url or current_url or 'не найден'}; "
        "номер на странице пока не найден.",
        flush=True,
    )
    return False



SUCCESS_PROFILE_FIELDS = [
    ("full_name", "ФИО"), ("gender", "Пол"), ("birth_date", "Дата рождения"),
    ("passport_series", "Серия паспорта"), ("passport_number", "Номер паспорта"),
    ("passport_issue_date", "Дата выдачи"), ("passport_issued_by", "Кем выдан"),
    ("country", "Страна"), ("region", "Область"), ("district", "Район"),
    ("locality", "Населённый пункт"), ("street", "Улица"), ("house", "Дом"),
    ("building", "Корпус"), ("apartment", "Квартира"),
]

def _norm_label(value):
    return re.sub(r"\s+", " ", str(value or "").lower().replace("ё", "е")).strip()

def capture_contract_details(page, worker):
    try:
        raw = page.evaluate(r"""() => {
            const visible = el => {
                const r=el.getBoundingClientRect(), s=getComputedStyle(el);
                return r.width>0 && r.height>0 && s.display!=='none' && s.visibility!=='hidden';
            };
            const text = el => (el && (el.innerText || el.textContent) || '').trim();
            const out=[];
            for (const el of document.querySelectorAll('input,textarea,select')) {
                if (!visible(el) || el.type==='hidden') continue;
                if ((el.type==='radio'||el.type==='checkbox') && !el.checked) continue;
                let label='';
                if (el.id) {
                    try {
                        const lab=document.querySelector(`label[for="${CSS.escape(el.id)}"]`);
                        if(lab) label=text(lab);
                    } catch(_) {}
                }
                if(!label){ const lab=el.closest('label'); if(lab) label=text(lab); }
                const holder=el.closest('[class*="field"],[class*="input"],[class*="form"],[class*="control"],div');
                let context=holder?text(holder):'';
                if(context.length>350) context=context.slice(0,350);
                let value='';
                if(el.tagName==='SELECT') value=el.options[el.selectedIndex]?.text||el.value||'';
                else if(el.type==='radio'||el.type==='checkbox') value=label||el.value||'Да';
                else value=el.value||'';
                out.push({label,context,value:String(value||'').trim(),name:el.name||'',id:el.id||'',placeholder:el.placeholder||''});
            }
            return out;
        }""")
    except Exception:
        return worker.get("success_profile") or {}

    profile=dict(worker.get("success_profile") or {})
    def put(k,v):
        v=str(v or "").strip()
        if v and not profile.get(k): profile[k]=v

    for item in raw or []:
        v=str(item.get("value") or "").strip()
        if not v: continue
        hay=_norm_label(" ".join([
            item.get("label") or "", item.get("context") or "",
            item.get("name") or "", item.get("id") or "",
            item.get("placeholder") or ""
        ]))
        if "фио" in hay or ("фамил" in hay and "имя" in hay): put("full_name",v)
        elif "дата рождения" in hay or "birth" in hay: put("birth_date",v)
        elif re.search(r"\bпол\b",hay) or "gender" in hay: put("gender",v)
        elif "дата выдачи" in hay: put("passport_issue_date",v)
        elif "кем выдан" in hay: put("passport_issued_by",v)
        elif "серия" in hay and ("паспорт" in hay or hay.strip()=="серия"): put("passport_series",v)
        elif "номер" in hay and ("паспорт" in hay or hay.strip()=="номер"): put("passport_number",v)
        elif "страна" in hay: put("country",v)
        elif "область" in hay or "регион" in hay: put("region",v)
        elif "район" in hay: put("district",v)
        elif "населен" in hay or "город" in hay: put("locality",v)
        elif "улиц" in hay: put("street",v)
        elif re.search(r"\bдом\b",hay): put("house",v)
        elif "корпус" in hay or "строен" in hay: put("building",v)
        elif "квартир" in hay: put("apartment",v)
    worker["success_profile"]=profile
    return profile


# SUCCESS_PROFILE_TEXT_1591R12
# The contract screen shows the name, gender and birth date as plain text, not as form
# fields, so the input-based captures above leave them empty. This capture reads
# "label: value" pairs from the page text (main frame and iframes), validates every
# value by type and never overwrites a value that is already captured.
_PROFILE_TEXT_LABELS_1591R12 = {
    "full_name": ("фио", "фамилия имя отчество", "ф и о", "fullname", "full name"),
    "gender": ("пол", "gender"),
    "birth_date": ("дата рождения", "birth date", "birthdate"),
    "passport_series": ("серия паспорта", "серия"),
    "passport_number": ("номер паспорта",),
    "passport_issue_date": ("дата выдачи",),
    "passport_issued_by": ("кем выдан",),
    "country": ("страна",),
    "region": ("область", "регион"),
    "district": ("район",),
    "locality": ("населенный пункт", "город", "г."),
    "street": ("улица", "ул."),
    "house": ("дом", "номер дома", "д."),
    "building": ("корпус", "строение", "корп."),
    "apartment": ("квартира", "кв."),
}
_DATE_RE_1591R12 = re.compile(r"\b\d{1,2}[.\-/]\d{1,2}[.\-/]\d{2,4}\b|\b\d{4}-\d{2}-\d{2}\b")
_FIO_RE_1591R12 = re.compile(
    r"^[А-ЯЁA-Z][А-Яа-яЁёA-Za-z.\-]{0,30}(\s+[А-ЯЁA-Z][А-Яа-яЁёA-Za-z.\-]{0,30}){1,3}$"
)
_GENDER_RE_1591R12 = re.compile(r"^(мужской|женский|муж|жен|м|ж|male|female)$", re.I)
_PROFILE_TEXT_VALUE_RE_1591R12 = {
    "passport_series": re.compile(r"^\d{2}\s?\d{2}$"),
    "passport_number": re.compile(r"^\d{6}$"),
    "house": re.compile(r"^\d{1,4}[а-яa-z]?(\s*/\s*\d{1,3})?$", re.I),
    "building": re.compile(r"^[\dа-яa-z\-]{1,6}$", re.I),
    "apartment": re.compile(r"^\d{1,5}[а-яa-z]?$", re.I),
}


def _text_label_key_1591r12(label):
    """Profile key for a visible label, or None. Labels are matched whole (or as the first
    word of a longer label), so «номер договора» or «домашний телефон» never match."""
    hay = _norm_label(label).strip(" :;-–—\t.,")
    if not hay or len(hay) > 40:
        return None
    for key, words in _PROFILE_TEXT_LABELS_1591R12.items():
        for word in words:
            word = _norm_label(word)
            if hay == word or hay.startswith(word + " "):
                return key
    return None


def _text_value_ok_1591r12(key, value):
    value = str(value or "").strip().strip(":;,")
    if not value or value in ("—", "-", "–") or len(value) > 160:
        return False
    if key == "full_name":
        return bool(_FIO_RE_1591R12.match(value))
    if key == "gender":
        return bool(_GENDER_RE_1591R12.match(value))
    if key in ("birth_date", "passport_issue_date"):
        return bool(_DATE_RE_1591R12.search(value))
    pattern = _PROFILE_TEXT_VALUE_RE_1591R12.get(key)
    return bool(pattern.match(value)) if pattern else True


_PROFILE_TEXT_JS_1591R12 = r"""
() => {
  const vis = el => {
    try {
      const r = el.getBoundingClientRect(), s = getComputedStyle(el);
      return r.width > 0 && r.height > 0 && s.display !== 'none' && s.visibility !== 'hidden';
    } catch (_) { return false; }
  };
  const txt = el => ((el && (el.innerText || el.textContent)) || '').replace(/\s+/g, ' ').trim();
  const pairs = [];
  const seen = new Set();
  const push = (label, value) => {
    label = String(label || '').replace(/\s+/g, ' ').trim().replace(/[:：]\s*$/, '');
    value = String(value || '').replace(/\s+/g, ' ').trim()
      .replace(/^[:：\-–—]\s*/, '').replace(/[;,]\s*$/, '');
    if (!label || !value || label.length > 40 || value.length > 160) return;
    if (value === label) return;
    const k = label + '|' + value;
    if (seen.has(k)) return;
    seen.add(k);
    pairs.push({label: label, value: value});
  };
  const containers = 'tr,dl,li,p,div,section,article,fieldset';
  document.querySelectorAll(
    'dt,th,[class*="label"],[class*="Label"],[class*="title"],[class*="name"]'
  ).forEach(el => {
    if (!vis(el)) return;
    const label = txt(el);
    if (!label || label.length > 40) return;
    let value = '';
    const sib = el.nextElementSibling;
    if (sib && vis(sib)) value = txt(sib);
    if (!value) {
      const row = el.closest(containers);
      if (row) {
        const t = txt(row);
        const i = t.indexOf(label);
        if (i >= 0) value = t.slice(i + label.length);
      }
    }
    push(label, value);
  });
  document.querySelectorAll('span,div,li,p,strong,b,em,small,a,label,dd,td').forEach(el => {
    if (!vis(el) || (el.children && el.children.length)) return;
    const t = txt(el);
    if (!t || t.length > 140) return;
    const m = t.match(/^([^:：]{2,40})[:：]\s*(.+)$/);
    if (m) push(m[1], m[2]);
  });
  let text = '';
  try { text = (document.body && (document.body.innerText || '')) || ''; } catch (_) {}
  return {pairs: pairs, text: text.slice(0, 20000)};
}
"""


def capture_success_profile_text_1591r12(page, worker):
    """Fill missing profile fields from the visible text of the contract screen."""
    targets, collected, texts = [], [], []
    if page is not None:
        targets.append(page)
        try:
            for frame in page.frames:
                if frame not in targets:
                    targets.append(frame)
        except Exception:
            pass
    for target in targets:
        try:
            data = target.evaluate(_PROFILE_TEXT_JS_1591R12)
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        for item in data.get("pairs") or []:
            if isinstance(item, dict):
                collected.append((item.get("label"), item.get("value")))
        if data.get("text"):
            texts.append(str(data.get("text")))

    profile = dict(worker.get("success_profile") or {})

    def put(key, value):
        if not key or profile.get(key):
            return
        if _text_value_ok_1591r12(key, value):
            profile[key] = str(value).strip().strip(":;,")

    for label, value in collected:
        put(_text_label_key_1591r12(label), value)

    for text in texts:
        lines = [line.strip() for line in re.split(r"[\r\n]+", text)]
        for index, line in enumerate(lines):
            if not line:
                continue
            match = re.match(r"^([^:：]{2,40})[:：]\s*(.+)$", line)
            if match:
                put(_text_label_key_1591r12(match.group(1)), match.group(2))
            elif _text_label_key_1591r12(line) and index + 1 < len(lines):
                following = lines[index + 1]
                if following and not _text_label_key_1591r12(following):
                    put(_text_label_key_1591r12(line), following)

    worker["success_profile"] = profile
    worker["profile"] = dict(profile)
    try:
        diagnostic = worker.get("diagnostic")
        if diagnostic and texts and not worker.get("success_text_dump_done"):
            worker["success_text_dump_done"] = True
            diagnostic.write("success_page_text_v1591r12", url=str(getattr(page, "url", "") or ""),
                             text="\n".join(texts)[:20000])
    except Exception:
        pass
    return profile


_capture_contract_details_before_v1583 = capture_contract_details
def capture_contract_details(page, worker):
    result = _capture_contract_details_before_v1583(page, worker)
    try:
        final_profile_capture_v1583(page, worker)
    except Exception:
        pass
    try:
        capture_success_profile_text_1591r12(page, worker)  # SUCCESS_PROFILE_TEXT_1591R12
    except Exception:
        pass
    return worker.get("success_profile") or result


def _success_profile_lines(profile):
    profile=profile or {}
    return [f"{label}: {profile.get(key) or '—'}" for key,label in SUCCESS_PROFILE_FIELDS]

def _success_message(worker, rec):
    row_no, active_value, second_value = row_parts(worker.get("row"))
    profile = rec.get("profile") or {}
    return "\n".join([
        "#успешно",  # SUCCESS_TAG_1591R17: searchable among the DeepSeek reports
        f"✅ УСПЕХ — Вкладка {worker['id']}",
        f"Строка: {row_no}/{worker.get('total_rows') or '?'}",
        f"Исходные данные: {active_value} | {second_value}",
        "",
        *_success_profile_lines(profile),
        "",
        f"eSIM: {rec.get('sim_number') or '—'}",
        f"Ссылка eSIM: {rec.get('sim_url') or '—'}",
        f"Страница договора: {rec.get('final_url') or '—'}",  # FINAL_PAGE_1591R23
        f"Заголовок страницы: {rec.get('final_title') or '—'}",
        *_final_links_lines_1591r23(rec.get("final_links")),
    ])


# FINAL_PAGE_1591R23
_FINAL_LINKS_JS_1591R23 = r"""() => {
  const out = [];
  const seen = new Set();
  const want = /договор|pdf|скачать|qr|esim|e-sim|загруз|документ|contract|download|профил|оплат|pay/i;
  const clean = s => String(s || '').replace(/\s+/g, ' ').trim();
  for (const el of document.querySelectorAll('a[href], [data-href], button[formaction]')) {
    const href = el.href || el.getAttribute('data-href') || el.getAttribute('formaction') || '';
    const text = clean(el.innerText || el.textContent || el.getAttribute('aria-label') || el.getAttribute('download'));
    if (!href || href.startsWith('javascript:') || seen.has(href)) continue;
    if (!(want.test(text) || want.test(href))) continue;
    seen.add(href);
    out.push({text: text.slice(0, 80), href: href.slice(0, 500)});
    if (out.length >= 8) break;
  }
  for (const img of document.querySelectorAll('img')) {
    const alt = clean(img.alt), src = String(img.src || '');
    if (!(/qr/i.test(alt) || /qr/i.test(src))) continue;
    out.push(src.startsWith('data:') ? {text: 'QR-код на странице (встроенное изображение)', href: ''}
                                     : {text: 'QR-код: ' + (alt || 'изображение'), href: src.slice(0, 500)});
    if (out.length >= 10) break;
  }
  let text = '';
  try { text = String((document.body && document.body.innerText) || ''); } catch (_) {}
  return {links: out, title: String(document.title || ''), text: text.slice(0, 20000)};
}"""


def capture_final_page_1591r23(page, worker=None):
    """URL of the page the worker is on when the success is recorded (the signed contract)
    plus its document-like links: contract, PDF, QR, download. Read-only."""
    result = {"url": "", "title": "", "links": []}
    if page is None:
        return result
    try:
        result["url"] = str(page.url or "")
    except Exception:
        pass
    text = ""
    try:
        data = page.evaluate(_FINAL_LINKS_JS_1591R23)
        if isinstance(data, dict):
            result["links"] = [x for x in (data.get("links") or []) if isinstance(x, dict)][:10]
            result["title"] = str(data.get("title") or "")[:200]
            text = str(data.get("text") or "")
    except Exception:
        pass
    if worker is not None:
        worker["final_url"] = result["url"]
        worker["final_title"] = result["title"]
        worker["final_links"] = result["links"]
        try:
            diagnostic = worker.get("diagnostic")
            if diagnostic:
                diagnostic.write("final_page_1591r23", url=result["url"], title=result["title"],
                                 links=result["links"], text=text[:20000])
        except Exception:
            pass
    return result


def _final_links_lines_1591r23(links):
    out = []
    for item in (links or [])[:10]:
        text = str((item or {}).get("text") or "").strip() or "документ"
        href = str((item or {}).get("href") or "").strip()
        out.append(f"{text}: {href}" if href else text)
    return out


def write_success_record(base_dir, worker):
    n,a,b=row_parts(worker.get("row"))
    final = capture_final_page_1591r23(worker.get("page"), worker)  # FINAL_PAGE_1591R23
    rec={
        "tab":worker["id"],
        "row":n,
        "active_digits":a,
        "second_value":b,
        "sim_number":worker.get("reserved_sim_number"),
        "sim_url":worker.get("reserved_sim_url"),
        "profile":dict(worker.get("success_profile") or {}),
        "final_url": final.get("url") or "",  # FINAL_PAGE_1591R23
        "final_title": final.get("title") or "",
        "final_links": list(final.get("links") or []),
        "sign_trace": _sign_trace_summary_1591r25(worker.get("sign_trace")),  # SIGN_TRACE_1591R25
    }
    with (base_dir/"successful_sims.jsonl").open("a",encoding="utf-8") as f:
        f.write(json.dumps(rec,ensure_ascii=False)+"\n")
    return rec



# OVERLAY_DISMISS_1591R6 / TARIFF_BY_NAME_1591R7
_MODAL_DIALOG_SELECTOR = '[role="dialog"][aria-modal="true"]'
_CHOOSE_BUTTON_RE = re.compile(r"^\s*выбрать\s*$", re.I)


def _blocking_dialog_indexes(page, keep_text=None, keep_selector=None):
    """Indexes of visible modal dialogs that do NOT contain what we are about to click."""
    return list(page.evaluate("""([keepText, keepSelector]) => {
        const out = [];
        [...document.querySelectorAll('[role="dialog"][aria-modal="true"]')].forEach((el, i) => {
            const r = el.getBoundingClientRect(); const s = getComputedStyle(el);
            if (!(r.width > 0 && r.height > 0 && s.display !== 'none' && s.visibility !== 'hidden')) return;
            if (keepSelector && el.querySelector(keepSelector)) return;
            if (keepText && (el.innerText || '').includes(keepText)) return;
            out.push(i);
        });
        return out;
    }""", [keep_text or "", keep_selector or ""]) or [])


def _visible_modal_dialogs(page):
    return len(_blocking_dialog_indexes(page))


def dismiss_blocking_overlays(page, attempts=3, keep_text=None, keep_selector=None):
    """Close a portal modal that intercepts clicks; never the dialog we need.

    Order: a visible close button inside the dialog, then Escape; as a last resort the
    dialog stops intercepting pointer events. The DOM is never removed, the basket is kept.
    A dialog containing keep_text or an element matching keep_selector is left untouched.
    Returns True when no blocking dialog is visible afterwards.
    """
    for _ in range(attempts):
        try:
            blocking = _blocking_dialog_indexes(page, keep_text, keep_selector)
        except Exception:
            return True
        if not blocking:
            return True
        closed = False
        dialog = page.locator(_MODAL_DIALOG_SELECTOR).nth(blocking[-1])
        for close_button in (
            dialog.get_by_role("button", name=re.compile(r"закрыть|close|✕|×", re.I)),
            dialog.locator('button[aria-label*="акрыть" i], button[aria-label*="close" i], [data-testid*="close" i]'),
        ):
            try:
                if close_button.count() > 0:
                    close_button.first.click(timeout=1500, no_wait_after=True)
                    closed = True
                    break
            except Exception:
                pass
        if not closed and not keep_text and not keep_selector:
            # Escape would close the protected dialog too; use it only when nothing is protected.
            try:
                page.keyboard.press("Escape")
            except Exception:
                pass
        try:
            page.wait_for_timeout(300)
        except Exception:
            pass
    try:
        blocking = _blocking_dialog_indexes(page, keep_text, keep_selector)
        if not blocking:
            return True
        page.evaluate("""(indexes) => {
            const all = document.querySelectorAll('[role="dialog"][aria-modal="true"]');
            indexes.forEach(i => { if (all[i]) all[i].style.pointerEvents = 'none'; });
        }""", blocking)
        print("Модальное окно не закрылось; снял перехват кликов, DOM не трогал.", flush=True)
    except Exception:
        pass
    return False


def _tariff_choose_button(page, diagnostic=None, timeout=10000):
    """«выбрать» inside the card titled TARIFF_NAME; the card order is never assumed.

    TARIFF_SCOPE_1591R32: the basket already holding TARIFF_NAME (chosen by an earlier row in the
    same Chromium: the basket is shared by its tabs) shows the same title with «изменить» and no
    «выбрать»; the tariff is looked for inside the «выберите тариф» picker first, and a card is only
    the element around the title that holds exactly one tariff title and a visible «выбрать».
    """
    scopes = []
    try:
        header = page.get_by_text(_TARIFF_PICKER_HEADER_RE_1591R32).first
        if header.count() > 0:
            picker = header.locator(
                "xpath=ancestor::*[.//*[normalize-space(.)='" + TARIFF_NAME + "']][1]"
            )
            if picker.count() > 0:
                scopes.append(picker)
    except Exception:
        pass
    scopes.append(page)
    deadline = monotonic() + timeout / 1000.0
    while True:
        for scope in scopes:
            try:
                button = _tariff_card_button_1591r32(scope)
            except Exception:
                button = None
            if button is not None:
                return button
        if monotonic() >= deadline:
            break
        page.wait_for_timeout(300)
    try:
        titles = page.locator("text=/подписка/i").all_inner_texts()[:10]
        choose_count = page.get_by_role("button", name=_CHOOSE_BUTTON_RE).count()
    except Exception:
        titles, choose_count = [], -1
    if diagnostic is not None:
        try:
            diagnostic.write("tariff_card_not_found", tariff=TARIFF_NAME, titles=titles, choose_buttons=choose_count)
        except Exception:
            pass
    print(
        f"Карточка «{TARIFF_NAME}» с кнопкой «выбрать» не найдена; на экране: {titles}, "
        f"кнопок «выбрать»: {choose_count}",
        flush=True,
    )
    raise RuntimeError(
        f"RECOVERABLE_RESTART_ROW: карточка тарифа «{TARIFF_NAME}» с кнопкой «выбрать» не найдена."
    )


# TARIFF_CHANGE_BUTTON_1591R33
_TARIFF_CHANGE_METRIC_1591R33 = 'button[data-metric-name="basketMetric:handleClickChangeTariffButton"]'


def _tariff_change_button_1591r33(page):
    """Locator of the tariff block's «изменить». The basket can show several «изменить» (the region
    block «Саратов • изменить» comes first) and the first one opened the region picker, not the
    tariff picker. Preference: the site's own tariff-change button when it is marked, else the
    «изменить» nearest to a tariff title («подписка bee …»), else every «изменить» (the caller
    clicks the first). Any «изменить» is waited for first, so a late render does not fall through."""
    generic = page.get_by_role("button", name="изменить", exact=True)
    try:
        expect(generic.first).to_be_visible(timeout=20000)
    except Exception:
        return generic
    try:
        marked = page.locator(_TARIFF_CHANGE_METRIC_1591R33)
        if marked.count() > 0:
            return marked
    except Exception:
        pass
    try:
        titles = page.get_by_text(_TARIFF_TITLE_RE_1591R32)
        for index in range(min(titles.count(), 4)):
            near = titles.nth(index).locator(
                "xpath=ancestor::*[.//button[normalize-space(.)='изменить']][1]"
            ).get_by_role("button", name="изменить", exact=True)
            if near.count() > 0:
                return near
    except Exception:
        pass
    return generic


# TARIFF_SCOPE_1591R32
_TARIFF_PICKER_HEADER_RE_1591R32 = re.compile(r"^\s*выберите тариф\s*$", re.I)
_TARIFF_TITLE_RE_1591R32 = re.compile(r"^\s*подписка bee\b", re.I)
_TARIFF_BASKET_BUTTON_RE_1591R32 = re.compile(r"^\s*(изменить|удалить тариф)\s*$", re.I)


def _tariff_card_button_1591r32(scope):
    """The visible «выбрать» of the one card titled TARIFF_NAME inside `scope`, else None."""
    titles = scope.get_by_text(TARIFF_NAME, exact=True)
    for index in range(min(titles.count(), 8)):
        title = titles.nth(index)
        try:
            if not title.is_visible():
                continue
            card = title.locator(
                "xpath=ancestor::*[.//button[normalize-space(.)='выбрать' or normalize-space(.)='Выбрать']][1]"
            )
            if card.count() == 0:
                continue
            if card.get_by_text(_TARIFF_TITLE_RE_1591R32).count() != 1:
                continue  # a container of several cards (or the basket plus the picker), not a card
            if card.get_by_role("button", name=_TARIFF_BASKET_BUTTON_RE_1591R32).count() > 0:
                continue  # the basket card («изменить» / «Удалить тариф»): its «выбрать» belong to options
            button = card.get_by_role("button", name=_CHOOSE_BUTTON_RE)
            if button.count() > 0 and button.first.is_visible():
                return button.first
        except Exception:
            continue
    return None


# ROW_START_ACTIVITY_1591R8
def _row_progress(page, note):
    """Refresh the worker heartbeat from inside a long registration step."""
    publisher = getattr(page, "_publish_worker_phase", None)
    if publisher is None:
        return
    try:
        publisher("ROW_START", note)
    except Exception:
        pass


def esim_state(page):
    return page.evaluate("""() => {
        const el = document.querySelector('input#esim[name="sim"]');
        if (!el) return {selected: false, missing: true};
        const aria = el.getAttribute('aria-checked');
        return {selected: aria === null ? el.checked : aria === 'true',
                checked: el.checked, ariaChecked: aria, disabled: el.disabled};
    }""")


def wait_esim_stable(page, timeout=6):
    deadline = monotonic() + timeout
    selected_since = None
    while monotonic() < deadline:
        if esim_state(page)["selected"]:
            if selected_since is None:
                selected_since = monotonic()
            if monotonic() - selected_since >= 1:
                return True
        else:
            selected_since = None
        # Короткий интервал проверки; события браузера продолжают обрабатываться.
        page.wait_for_timeout(200)
    return False


def select_esim(page):
    for attempt in range(1, 4):
        if esim_state(page)["selected"] and wait_esim_stable(page, timeout=2):
            return
        print(f"Выбор eSIM: попытка {attempt}/3...", flush=True)
        dismiss_blocking_overlays(page, keep_selector='input#esim[name="sim"]')  # OVERLAY_DISMISS_1591R6
        radio = page.locator('input#esim[name="sim"]')
        try:
            radio.wait_for(state="visible", timeout=10000)
            expect(radio).to_be_enabled(timeout=10000)
            # При повторном рендере locator находит актуальный input.
            if not esim_state(page)["selected"]:
                radio.click(timeout=5000)
        except PlaywrightTimeoutError:
            print("Нажатие не подтверждено; проверяю состояние переключателя.")
        if not esim_state(page)["selected"]:
            # The pointer may still be intercepted by a portal layer: click through it.
            try:
                radio.click(timeout=3000, force=True, no_wait_after=True)
            except Exception:
                pass
        if not esim_state(page)["selected"]:
            try:
                page.evaluate("""() => {
                    const el = document.querySelector('input#esim[name="sim"]');
                    if (!el) return;
                    const label = el.closest('label');
                    if (label) label.click(); else el.click();
                    if (!el.checked) {
                        el.checked = true;
                        for (const t of ['input', 'change']) el.dispatchEvent(new Event(t, {bubbles: true}));
                    }
                }""")
            except Exception:
                pass
        if wait_esim_stable(page):
            print("Выбор eSIM устойчиво подтверждён.")
            return
        print("Состояние eSIM:", esim_state(page))
    raise RuntimeError(
        "После трёх попыток eSIM не выбрана устойчиво. "
        "Переход к оформлению остановлен."
    )


def wait_for_captcha_task(page, timeout=30):
    selector = '[data-testid="advanced-iframe"]'
    deadline = monotonic() + timeout
    while monotonic() < deadline:
        frames = page.locator(selector)
        for index in range(frames.count()):
            frame_box = frames.nth(index)
            if not frame_box.is_visible():
                continue
            task = page.frame_locator(selector).nth(index).get_by_test_id("silhouette-container")
            if not task.is_visible():
                continue
            images_ready = task.evaluate("""el => [...el.querySelectorAll('img')]
                .every(img => img.complete && img.naturalWidth > 0)""")
            if images_ready:
                return frame_box
        page.wait_for_timeout(200)
    raise PlaywrightTimeoutError("Не появился блок задания «Силуэты» внутри iframe.")



def _captcha_overlay_visible(page):
    """Не кликаем «Продолжить» поверх ещё открытой проверки."""
    try:
        frames = page.locator('[data-testid="advanced-iframe"]')
        for index in range(frames.count()):
            if frames.nth(index).is_visible():
                return True
    except Exception:
        pass
    return False


def wait_confirmation_after_continue(page, continue_button, diagnostic,
                                     settle_seconds=5, max_retries=2):
    """Страховка от редкого зависания формы после закрытия проверки.

    Нормальный сценарий не трогаем: если форма ушла дальше, сразу передаём
    управление обычному wait_confirmation(). Если через несколько секунд
    форма всё ещё здесь и «Продолжить» снова доступна, повторяем клик.
    """
    for retry in range(max_retries + 1):
        deadline = monotonic() + settle_seconds
        while monotonic() < deadline:
            if page.is_closed():
                return wait_confirmation(page)

            # Если кнопки формы больше нет, переход уже начался/произошёл.
            try:
                if continue_button.count() == 0 or not continue_button.first.is_visible():
                    return wait_confirmation(page)
            except Exception:
                return wait_confirmation(page)

            # Пока поверх формы открыта проверка, «Продолжить» не трогаем.
            if _captcha_overlay_visible(page):
                page.wait_for_timeout(250)
                continue

            page.wait_for_timeout(250)

        if page.is_closed():
            return wait_confirmation(page)

        # После паузы повторяем только если исходная форма всё ещё видна,
        # проверка закрыта, а кнопка действительно доступна.
        if _captcha_overlay_visible(page):
            print('Проверка всё ещё открыта; повторный «Продолжить» не нажимаю.', flush=True)
            return wait_confirmation(page)

        try:
            button = continue_button.first
            if not button.is_visible():
                return wait_confirmation(page)
            if not button.is_enabled() or button.get_attribute('aria-disabled') == 'true':
                return wait_confirmation(page)
        except Exception:
            return wait_confirmation(page)

        if retry >= max_retries:
            print('Форма осталась на месте после повторных попыток «Продолжить».', flush=True)
            diagnostic.snapshot('continue_retry_exhausted')
            return wait_confirmation(page)

        try:
            diagnostic.snapshot(f'before_continue_retry_{retry + 1}')
            button.click(timeout=5000)
            diagnostic.write('continue_retry', attempt=retry + 1,
                             reason='form_still_visible_after_check')
            print(
                f'Форма не ушла дальше за {settle_seconds} секунд — '
                f'повторно нажимаю «Продолжить» ({retry + 1}/{max_retries}).',
                flush=True,
            )
        except Exception as exc:
            diagnostic.write('continue_retry_failed', attempt=retry + 1,
                             error_type=type(exc).__name__)
            print('Повторный клик «Продолжить» не удался; перехожу к обычному ожиданию.', flush=True)
            return wait_confirmation(page)

    return wait_confirmation(page)

def clear_registration_fields(page):
    """Очищает только данные текущей строки, не перезапуская браузер/форму."""
    active_field = page.locator('input[name="ctn"]')
    try:
        form = active_field.locator("xpath=ancestor::form[1]")
        scope = form if form.count() == 1 else page
        second_field = scope.locator(
            'input:visible:not([name="ctn"]):not([type="hidden"])'
            ':not([type="checkbox"]):not([type="radio"]):not([type="submit"])'
            ':not([type="button"]):not([type="reset"])'
        )
        for field in (active_field, second_field.first):
            try:
                if field.count() and field.is_visible():
                    field.click(timeout=3000)
                    field.press("ControlOrMeta+A")
                    field.press("Backspace")
            except Exception:
                pass
        page.wait_for_timeout(300)
    except Exception:
        pass


def process_registration_row(page, diagnostic, active_digits, second_value):
    active_field = page.locator('input[name="ctn"]')
    expect(active_field).to_be_visible()
    active_phone = (
        f"+7 {active_digits[1:4]} {active_digits[4:7]} "
        f"{active_digits[7:9]} {active_digits[9:11]}"
    )
    diagnostic.write("step", name="registration_typing")
    number_responses = []

    def on_number_response(response):
        url = urlsplit(response.url)
        if not str(url.hostname or "").endswith(".beeline.ru") or "checknumber" not in url.path.lower():
            return
        ctn = parse_qs(url.query).get("ctn", [""])[0]
        ctn_digits = "".join(c for c in ctn if c.isdigit())
        if ctn_digits in (active_digits, active_digits[1:]):
            number_responses.append(response)

    page.on("response", on_number_response)
    try:
        print("Ввожу активный номер...")
        active_field.click()
        active_field.press("ControlOrMeta+A")
        active_field.press("Backspace")
        active_field.press_sequentially(active_phone, delay=80)
        active_field.press("Tab")
        if "".join(c for c in active_field.input_value() if c.isdigit()) != active_digits:
            raise RuntimeError("Поле активного номера не сохранило номер полностью.")

        form = active_field.locator("xpath=ancestor::form[1]")
        scope = form if form.count() == 1 else page
        second_field = scope.locator(
            'input:visible:not([name="ctn"]):not([type="hidden"])'
            ':not([type="checkbox"]):not([type="radio"]):not([type="submit"])'
            ':not([type="button"]):not([type="reset"])'
        )
        expect(second_field).to_have_count(1, timeout=10000)
        expect(second_field).to_be_editable(timeout=10000)
        print("Ввожу второе поле...")
        diagnostic.write("step", name="second_field_typing")
        expected = re.sub(r"\s+", "", second_value)
        second_ok = False

        for second_attempt in range(1, 5):
            second_field.click()

            entered_now = re.sub(r"\s+", "", second_field.input_value())
            missing = (
                expected[len(entered_now):]
                if expected.startswith(entered_now) and len(entered_now) < len(expected)
                else ""
            )

            if second_attempt > 1 and 0 < len(missing) <= 2:
                print(
                    f"Второе поле недописано на {len(missing)} символ(а). "
                    f"Дописываю: {missing}",
                    flush=True,
                )
                second_field.press("End")
                second_field.press_sequentially(missing, delay=160)
            else:
                if second_attempt > 1:
                    print(
                        f"Повторный полный ввод второго поля "
                        f"({second_attempt}/4)...",
                        flush=True,
                    )
                second_field.press("ControlOrMeta+A")
                second_field.press("Backspace")
                page.wait_for_timeout(200)
                second_field.press_sequentially(second_value, delay=110)

            for _ in range(15):
                entered = re.sub(r"\s+", "", second_field.input_value())
                if entered == expected:
                    second_ok = True
                    break
                page.wait_for_timeout(150)

            if not second_ok:
                second_field.press("Tab")
                page.wait_for_timeout(350)
                entered = re.sub(r"\s+", "", second_field.input_value())
                second_ok = entered == expected

            diagnostic.write(
                "second_field_attempt",
                attempt=second_attempt,
                actual_length=len(re.sub(r"\s+", "", second_field.input_value())),
                expected_length=len(expected),
                ok=second_ok,
            )
            if second_ok:
                break

        if not second_ok:
            diagnostic.snapshot("second_field_not_saved")
            raise RuntimeError(
                "RECOVERABLE_RESTART_ROW: второе поле не сохранилось "
                "после 4 проверенных попыток."
            )

        second_field.press("Tab")
        diagnostic.write("step", name="both_fields_filled")
        print("Оба поля заполнены. Проверяю готовность формы...")

        deadline = monotonic() + 10
        while not number_responses and monotonic() < deadline:
            page.wait_for_timeout(200)
        if number_responses:
            response = number_responses[-1]
            failure = response.finished()
            diagnostic.write(
                "number_check_completed", status=response.status,
                transfer_ok=failure is None,
            )
            # Ошибка проверки номера сама по себе больше не роняет весь список.
            # Решение принимаем по фактическому состоянию кнопки ниже.
            if failure or not response.ok:
                diagnostic.write(
                    "number_check_unsuccessful", status=response.status,
                    transfer_ok=failure is None,
                )
        else:
            diagnostic.write("number_check_not_observed")
            print("Отдельный ответ проверки номера не найден; проверяю доступность кнопки.")
    finally:
        page.remove_listener("response", on_number_response)

    continue_button = page.get_by_role(
        "button", name=re.compile(r"^\s*продолжить\s*$", re.I)
    )
    expect(continue_button).to_be_visible(timeout=10000)
    enabled = False
    valid_deadline = monotonic() + 5
    while monotonic() < valid_deadline:
        try:
            button = continue_button.first
            if (button.is_visible()
                    and button.is_enabled()
                    and button.get_attribute("disabled") is None
                    and button.get_attribute("aria-disabled") != "true"
                    and button.get_attribute("data-disabled") != "true"):
                enabled = True
                break
        except Exception:
            pass
        page.wait_for_timeout(200)

    if not enabled:
        diagnostic.snapshot("invalid_row_continue_disabled")
        diagnostic.write("invalid_row", reason="continue_button_disabled")
        print(
            "Кнопка «Продолжить» осталась серой. Строка невалидна — "
            "очищаю поля и беру следующую в этом же окне.",
            flush=True,
        )
        clear_registration_fields(page)
        return "INVALID_ROW"

    diagnostic.snapshot("before_continue")
    continue_button.first.click()
    print("Кнопка «продолжить» нажата. Жду загрузку задания внутри капчи до 30 секунд...")
    try:
        captcha_frame = wait_for_captcha_task(page)
    except PlaywrightTimeoutError:
        diagnostic.snapshot("captcha_task_not_ready_after_30s")
        if _is_auth_url(page.url) and not _captcha_overlay_visible(page):
            # Protected stage is already behind us even if task detection missed it.
            launch_event = getattr(page, "_launch_ready_event", None)
            if launch_event is not None and not launch_event.is_set():
                launch_event.set()
                print(
                    "Protected stage уже пройден (открыт auth) — "
                    "разрешаю следующую вкладку.",
                    flush=True,
                )
        else:
            raise RuntimeError(
                "RECOVERABLE_RESTART_ROW: protected task не стал готов за 30 секунд."
            )
    else:
        diagnostic.snapshot("captcha_task_ready")
        # Publish the protected state BEFORE entering matcher. This closes the
        # race where UI already showed the protected modal while status stayed IDLE.
        publisher = getattr(page, "_publish_worker_phase", None)
        if publisher is not None:
            publisher("PROTECTED_CHECK", "Защищённый этап обнаружен; запускаю matcher")
        setattr(page, "_protected_check_in_progress", True)
        hb = getattr(page, "_worker_heartbeat", None)
        if hb is not None:
            try:
                hb["phase"] = "PROTECTED_CHECK"
            except Exception:
                pass
        # Внешний watchdog обязан игнорировать этот этап целиком.
        # Страница остаётся единственной рабочей вкладкой этого слота.
        try:
            try_local_captcha(page, captcha_frame)
        finally:
            setattr(page, "_protected_check_in_progress", False)

        # Не считаем шаг завершённым только потому, что функция вернулась.
        # Ждём фактического ухода/закрытия экрана проверки.
        close_deadline = monotonic() + 30
        while monotonic() < close_deadline:
            if page.is_closed():
                raise RuntimeError("RECOVERABLE_RESTART_ROW: вкладка закрылась после проверки.")
            if not _captcha_overlay_visible(page):
                break
            page.wait_for_timeout(250)
        else:
            diagnostic.snapshot("protected_check_still_visible")
            raise RuntimeError(
                "RECOVERABLE_RESTART_ROW: предыдущая проверка осталась открытой; "
                "к ожиданию подтверждения не перехожу."
            )

        if publisher is not None:
            publisher("POST_PROTECTED", "Защищённый этап закрыт; проверяю следующий экран")

        # ЕДИНСТВЕННАЯ точка разблокировки cascade.
        # Не достаточно просто открыть форму: следующая вкладка появляется
        # только после того, как protected stage этой вкладки реально завершён
        # и overlay исчез.
        launch_event = getattr(page, "_launch_ready_event", None)
        if launch_event is not None and not launch_event.is_set():
            launch_event.set()
            print(
                "Защищённый этап успешно завершён — "
                "разрешаю запуск следующей вкладки этого Chromium.",
                flush=True,
            )
    # Ожидание подтверждения вынесено в общий диспетчер worker-вкладок.
    # Это позволяет каждой вкладке иметь собственный 65-секундный таймер и не
    # блокировать остальные вкладки во время ожидания.
    return "PENDING_CONFIRM"


def run_registration(page, diagnostic, phone, digits, active_digits, second_value, form_ready=False, launch_ready_event=None):
    if not form_ready:
        print("Открываю корзину...")
        goto_error = None
        for goto_attempt in range(1, 4):
            try:
                page.goto(START_URL, wait_until="domcontentloaded", timeout=60000)
                goto_error = None
                break
            except PlaywrightError as exc:
                goto_error = exc
                msg = str(exc)
                if "ERR_NAME_NOT_RESOLVED" not in msg or goto_attempt >= 3:
                    raise
                print(
                    f"DNS временно не разрешил адрес. Повтор перехода {goto_attempt}/3...",
                    flush=True,
                )
                page.wait_for_timeout(2000 * goto_attempt)
        if goto_error is not None:
            raise goto_error

        # При пяти одновременных вкладках корзина может дорисовываться заметно
        # дольше. Не используем фиксированные 5 секунд: ждём именно готовую кнопку.
        _row_progress(page, "открываю выбор тарифа")  # ROW_START_ACTIVITY_1591R8
        print("Открываю выбор тарифа...")
        def click_tariff_change():
            candidates = [  # TARIFF_CHANGE_BUTTON_1591R33: the tariff «изменить», not the region one
                _tariff_change_button_1591r33(page),
                page.get_by_role("button", name="изменить", exact=True),
                page.locator("button").filter(has_text=re.compile(r"^\s*изменить\s*$", re.I)),
            ]
            last_error = None
            dismiss_blocking_overlays(page)  # OVERLAY_DISMISS_1591R6
            for candidate in candidates:
                try:
                    expect(candidate.first).to_be_visible(timeout=20000)
                    try:
                        candidate.first.click(timeout=15000, no_wait_after=True)
                    except PlaywrightTimeoutError:
                        # The button is ready; a portal modal intercepts the pointer.
                        dismiss_blocking_overlays(page)
                        candidate.first.click(timeout=15000, no_wait_after=True, force=True)
                    return
                except (PlaywrightTimeoutError, AssertionError) as exc:
                    last_error = exc
            raise last_error or RuntimeError("Кнопка «изменить» не найдена")

        try:
            click_tariff_change()
        except (PlaywrightTimeoutError, AssertionError):
            diagnostic.snapshot("tariff_change_button_not_ready")
            # ROW_START_ACTIVITY_1591R8: a reload resets the basket; retry in place first.
            print("Кнопка «изменить» не нажалась с первой попытки. Повторяю без перезагрузки...", flush=True)
            _row_progress(page, "повтор «изменить» без перезагрузки")
            page.wait_for_timeout(3000)
            try:
                click_tariff_change()
            except (PlaywrightTimeoutError, AssertionError):
                print("Кнопка «изменить» не нажалась повторно. Обновляю только эту вкладку...", flush=True)
                page.reload(wait_until="domcontentloaded", timeout=60000)
                click_tariff_change()

        _row_progress(page, "нажимаю «выбрать» в карточке тарифа")  # ROW_START_ACTIVITY_1591R8
        print("Нажимаю «выбрать» в карточке тарифа...")
        choose_clicked = False
        for choose_attempt in range(1, 4):
            dismiss_blocking_overlays(page, keep_text=TARIFF_NAME)  # OVERLAY_DISMISS_1591R6
            choose_button = _tariff_choose_button(page, diagnostic)  # TARIFF_BY_NAME_1591R7
            try:
                choose_button.click(timeout=7000, no_wait_after=True)
                choose_clicked = True
            except Exception as exc:
                diagnostic.write(
                    "second_choose_click_exception",
                    attempt=choose_attempt,
                    error_type=type(exc).__name__,
                )

            # Даже если click() сообщил timeout, действие могло уже состояться.
            state_deadline = monotonic() + 8
            while monotonic() < state_deadline:
                try:
                    if page.locator('input#esim[name="sim"]').count() > 0:
                        choose_clicked = True
                        break
                    if page.get_by_text(TARIFF_NAME, exact=True).count() > 0:
                        choose_clicked = True
                        break
                except Exception:
                    pass
                page.wait_for_timeout(250)

            if choose_clicked:
                break

            print(
                f"После «выбрать» переход пока не подтверждён "
                f"({choose_attempt}/3). Повторяю...",
                flush=True,
            )

        if not choose_clicked:
            diagnostic.snapshot("second_choose_transition_not_confirmed")
            raise RuntimeError(
                "RECOVERABLE_RESTART_ROW: после второй кнопки «выбрать» "
                "переход не подтвердился."
            )

        # Название тарифа может дорисоваться позже самой рабочей формы.
        # Не роняем строку только из-за отсутствия точного текста bee START.
        tariff_title_seen = False
        try:
            expect(page.get_by_text(TARIFF_NAME, exact=True).first).to_be_visible(timeout=5000)
            tariff_title_seen = True
        except Exception:
            diagnostic.write(
                "tariff_title_not_seen",
                note="continue_by_actual_controls",
            )
            print(
                "Точный текст bee START пока не появился; "
                "проверяю фактические элементы оформления.",
                flush=True,
            )

        # Если eSIM-control уже существует, продолжаем независимо от заголовка.
        try:
            page.locator('input#esim[name="sim"]').wait_for(state="attached", timeout=10000)
        except Exception as exc:
            diagnostic.snapshot("esim_control_not_ready")
            raise RuntimeError(
                "RECOVERABLE_RESTART_ROW: после выбора тарифа не появилась форма eSIM."
            ) from exc

        if tariff_title_seen:
            print("На странице найдено название bee START. Выбираю eSIM...")
        else:
            print("Форма eSIM уже доступна. Продолжаю без ожидания заголовка тарифа...")
        _row_progress(page, "выбор eSIM")  # ROW_START_ACTIVITY_1591R8
        select_esim(page)
        field = page.get_by_placeholder("+7 999 999 99")
        expect(field).to_be_visible(timeout=15000)
        expect(field).to_be_editable(timeout=15000)

        # Поле маскированное: после fill() сайт может ещё несколько сотен
        # миллисекунд нормализовать значение. Проверяем эквивалентные формы
        # 7XXXXXXXXXX / XXXXXXXXXX и при необходимости один раз вводим посимвольно.
        expected_digits = "".join(c for c in digits if c.isdigit())

        def contact_value_ok():
            actual = "".join(c for c in field.input_value() if c.isdigit())
            expected_variants = {expected_digits}
            if expected_digits.startswith(("7", "8")) and len(expected_digits) == 11:
                expected_variants.add(expected_digits[1:])
            actual_variants = {actual}
            if actual.startswith(("7", "8")) and len(actual) == 11:
                actual_variants.add(actual[1:])
            return bool(expected_variants & actual_variants)

        def actual_contact_digits():
            return "".join(c for c in field.input_value() if c.isdigit())

        expected_full = expected_digits
        expected_national = (
            expected_digits[1:]
            if expected_digits.startswith(("7", "8")) and len(expected_digits) == 11
            else expected_digits
        )

        def normalized_actual():
            actual = actual_contact_digits()
            if actual.startswith(("7", "8")) and len(actual) == 11:
                return actual[1:]
            return actual

        def contact_ok_now():
            return normalized_actual() == expected_national

        contact_ok = False
        for input_attempt in range(1, 5):
            if input_attempt == 1:
                # Маскированные поля надёжнее заполняются с клавиатуры.
                field.click()
                field.press("ControlOrMeta+A")
                field.press("Backspace")
                field.press_sequentially(phone, delay=110)
            else:
                current = normalized_actual()

                # Если маска съела только хвост, не стираем уже корректную часть.
                if expected_national.startswith(current):
                    missing = expected_national[len(current):]
                else:
                    missing = ""

                if 0 < len(missing) <= 2:
                    print(
                        f"Контактный номер недописан на {len(missing)} символ(а). "
                        f"Дописываю: {missing}",
                        flush=True,
                    )
                    field.click()
                    field.press("End")
                    field.press_sequentially(missing, delay=180)
                else:
                    print(
                        f"Полностью переввожу контактный номер "
                        f"({input_attempt}/4)...",
                        flush=True,
                    )
                    field.click()
                    field.press("ControlOrMeta+A")
                    field.press("Backspace")
                    page.wait_for_timeout(250)
                    field.press_sequentially(phone, delay=140)

            # Даём маске закончить форматирование ДО blur.
            for _ in range(15):
                if contact_ok_now():
                    contact_ok = True
                    break
                page.wait_for_timeout(150)

            if not contact_ok:
                field.press("Tab")
                page.wait_for_timeout(400)
                if contact_ok_now():
                    contact_ok = True

            diagnostic.write(
                "contact_phone_attempt",
                attempt=input_attempt,
                actual_digits=actual_contact_digits(),
                actual_length=len(actual_contact_digits()),
                expected_length=len(expected_full),
                ok=contact_ok,
            )
            if contact_ok:
                break

        if not contact_ok:
            diagnostic.snapshot("contact_phone_not_saved")
            raise RuntimeError(
                "RECOVERABLE_RESTART_ROW: контактный номер не сохранился "
                "после 4 проверенных попыток."
            )

        print("Нажимаю «идём дальше»...")

        def refill_contact_after_reload():
            """После reload восстанавливает eSIM и контактный номер."""
            print("После обновления снова выбираю eSIM...", flush=True)
            select_esim(page)
            contact = page.get_by_placeholder("+7 999 999 99")
            expect(contact).to_be_visible(timeout=15000)
            expect(contact).to_be_editable(timeout=15000)
            contact.fill(phone)
            contact.press("Tab")
            page.wait_for_timeout(700)

        transition_ok = False
        # Возвращено рабочее поведение старого наброска.
        for transition_attempt in range(1, 5):
            next_button = page.get_by_role(
                "button",
                name=re.compile(r"^\s*(?:ид[её]м дальше|к оформлению)\s*$", re.I),
            )
            expect(next_button).to_be_visible(timeout=15000)
            expect(next_button).to_be_enabled(timeout=15000)
            select_esim(page)

            diagnostic.write(
                "registration_transition_attempt",
                attempt=transition_attempt,
            )
            next_button.first.click(timeout=10000, no_wait_after=True)
            print(
                f"«Идём дальше»: попытка {transition_attempt}/4.",
                flush=True,
            )

            # Старый рабочий вариант: определяем переход по фактическому
            # состоянию страницы и не возвращаемся к выбору eSIM, если
            # оформление уже открылось.
            source_url = page.url
            transition_deadline = monotonic() + 12
            while monotonic() < transition_deadline:
                try:
                    choice = page.get_by_role(
                        "button",
                        name=re.compile(r"выбрать способ регистрации", re.I),
                    )
                    if choice.count() > 0 and choice.first.is_visible():
                        transition_ok = True
                        break

                    old_next = page.get_by_role(
                        "button",
                        name=re.compile(r"^\\s*(?:ид[её]м дальше|к оформлению)\\s*$", re.I),
                    )
                    old_screen_gone = (
                        old_next.count() == 0
                        or not old_next.first.is_visible()
                    )
                    if page.url != source_url and old_screen_gone:
                        transition_ok = True
                        break
                except Exception:
                    pass
                page.wait_for_timeout(250)

            if transition_ok:
                diagnostic.write(
                    "registration_transition_success",
                    url=page.url,
                    detection="page_state",
                )
                print(
                    "Переход к оформлению подтверждён. Повторно eSIM не выбираю.",
                    flush=True,
                )
                break

            diagnostic.snapshot(
                f"registration_transition_stuck_{transition_attempt}"
            )
            print(
                "Через 12 секунд перехода действительно нет. "
                "Перезагружаю эту вкладку и повторяю ту же строку.",
                flush=True,
            )
            diagnostic.write(
                "registration_transition_recovery",
                attempt=transition_attempt,
                stage="reload_reselect_esim",
            )
            try:
                page.reload(wait_until="domcontentloaded", timeout=60000)
            except PlaywrightTimeoutError:
                diagnostic.write(
                    "registration_recovery_reload_timeout",
                    attempt=transition_attempt,
                )
            page.wait_for_timeout(2500)
            refill_contact_after_reload()

        if not transition_ok:
            diagnostic.snapshot("registration_transition_exhausted")
            raise RuntimeError(
                "RECOVERABLE_RESTART_ROW: переход на регистрацию eSIM "
                "не произошёл после 4 восстановлений."
            )

        # Нужные пользователю eSIM URL и eSIM-номер находятся именно
        # на этой промежуточной странице: ПОСЛЕ контактного номера и
        # ДО клика «выбрать способ регистрации».
        ensure_region_page(page, diagnostic)
        capture_esim_offer_page(
            page,
            diagnostic=diagnostic,
            contact_phone=phone,
            timeout=6,
        )

        print("Нажимаю «выбрать способ регистрации»...")
        registration_method_opened = False
        for method_attempt in range(1, 5):
            try:
                method_button = page.get_by_role(
                    "button", name="выбрать способ регистрации"
                ).first
                expect(method_button).to_be_visible(timeout=5000)
                expect(method_button).to_be_enabled(timeout=5000)
                method_button.scroll_into_view_if_needed(timeout=3000)
                method_button.click(timeout=5000)
                registration_method_opened = True
                break
            except Exception as exc:
                diagnostic.write(
                    "registration_method_click_retry",
                    attempt=method_attempt,
                    error_type=type(exc).__name__,
                )
                print(
                    f"Кнопка выбора способа регистрации пока нестабильна "
                    f"({method_attempt}/4). Повторяю...",
                    flush=True,
                )
                page.wait_for_timeout(1500)

        if not registration_method_opened:
            diagnostic.snapshot("registration_method_click_exhausted")
            raise RuntimeError(
                "RECOVERABLE_RESTART_ROW: кнопка выбора способа регистрации "
                "не стала стабильной после 4 попыток."
            )

        print("Выбираю «с сим билайна»...")
        sim_method_opened = False
        sim_method_error = None
        for sim_attempt in range(1, 5):
            try:
                chip = page.locator("div").filter(
                    has_text=re.compile(
                        r"^с сим билайнавозьмём ваши данные с активного номера у нас$"
                    )
                ).nth(1)
                chip.wait_for(state="visible", timeout=8000)
                chip.click(timeout=8000, no_wait_after=True)

                active_input = page.locator('input[name="ctn"]')
                active_input.wait_for(state="visible", timeout=8000)
                sim_method_opened = True
                break
            except Exception as exc:
                sim_method_error = exc
                diagnostic.write(
                    "sim_method_click_retry",
                    attempt=sim_attempt,
                    error_type=type(exc).__name__,
                )
                page.wait_for_timeout(800)

        if not sim_method_opened:
            diagnostic.snapshot("sim_method_click_exhausted")
            raise RuntimeError(
                "RECOVERABLE_RESTART_ROW: не удалось открыть форму «с сим билайна» "
                f"после 4 попыток: {type(sim_method_error).__name__ if sim_method_error else 'unknown'}"
            )

        print("Открылась форма регистрации с SIM Билайна.")
        ensure_region_page(page, diagnostic)

        # Следующую вкладку этого Chromium пока НЕ запускаем.
        # Каскад будет разблокирован только после успешного завершения
        # защищённого этапа текущей строки.
    else:
        print("Использую уже открытую форму — браузер не перезапускаю.", flush=True)
        expect(page.locator('input[name="ctn"]')).to_be_visible(timeout=8000)
        # Даже при повторном использовании готовой формы новый cascade-slot
        # не выпускаем до завершения protected stage этой строки.

    return process_registration_row(page, diagnostic, active_digits, second_value)



def return_to_clean_registration_form(page, diagnostic, timeout=20):
    """После 6 неудачных подтверждений возвращаемся ровно на один шаг назад.

    По текущему сценарию браузера предыдущая запись истории — форма с двумя
    чистыми полями. Никаких дополнительных go_back() и ручной очистки здесь
    нет: если форма не появилась, это отдельная ошибка навигации.
    """
    print(
        "6 попыток подтверждения закончились — возвращаюсь на один шаг назад "
        "к форме и беру следующую строку.",
        flush=True,
    )
    diagnostic.snapshot("before_back_after_confirm_timeout")
    try:
        page.go_back(wait_until="domcontentloaded", timeout=20000)
    except PlaywrightTimeoutError:
        # История могла отрисовать предыдущую страницу, но событие load зависло.
        # Ни второй back, ни перезагрузку не делаем — просто проверяем саму форму.
        pass

    deadline = monotonic() + timeout
    active_field = page.locator('input[name="ctn"]')
    while monotonic() < deadline and not page.is_closed():
        try:
            if active_field.count() and active_field.first.is_visible():
                diagnostic.snapshot("registration_form_after_back")
                diagnostic.write("returned_to_registration_form_after_confirm_timeout")
                print(
                    "Форма снова открыта. Следующая строка будет введена в это же окно.",
                    flush=True,
                )
                return True
        except Exception:
            pass
        page.wait_for_timeout(250)

    diagnostic.snapshot("registration_form_not_found_after_back")
    diagnostic.write("back_after_confirm_timeout_failed")
    print(
        "После одного перехода назад форма с номером не появилась. "
        "Больше назад автоматически не иду.",
        flush=True,
    )
    return False


# TWO_BROWSERS_1591R28
CAPTCHA_PARALLEL_MAX = 2            # captchas solved at the same time across all tabs
CAPTCHA_GATE_WAIT_SECONDS = 180     # longest wait for a slot; then the tab solves anyway
_CAPTCHA_GATE = None                # multiprocessing semaphore, set in each worker process

_try_local_captcha_unlocked = try_local_captcha


def try_local_captcha(page, frame_box=None):
    """Captchas of different tabs overlap at most CAPTCHA_PARALLEL_MAX at a time: a tab waits
    for a slot and reports CAPTCHA_WAIT to the watchdog meanwhile."""
    gate = _CAPTCHA_GATE
    if gate is None:
        return _try_local_captcha_unlocked(page, frame_box)
    from local_matcher import matcher_progress as _matcher_progress
    acquired = False
    deadline = monotonic() + CAPTCHA_GATE_WAIT_SECONDS
    try:
        while not acquired and monotonic() < deadline:
            acquired = bool(gate.acquire(timeout=5))
            if not acquired:
                try:
                    _matcher_progress("CAPTCHA_WAIT")
                except Exception:
                    pass
        return _try_local_captcha_unlocked(page, frame_box)
    finally:
        if acquired:
            try:
                gate.release()
            except Exception:
                pass


# BROWSER_COUNT_ENV_1591R34: BEELINE_BROWSERS=1 in the systemd unit runs one Chromium on a small
# server (4 vCPU / 8 GB ran two at load average 20: every click and wait timed out). Default 2 (r28).
def _browser_count_1591r34(default=2):
    try:
        value = int(str(os.environ.get("BEELINE_BROWSERS") or default).strip())
    except ValueError:
        value = default
    return min(max(value, 1), 4)


BROWSER_COUNT = _browser_count_1591r34()  # TWO_BROWSERS_1591R28: Chromium instances, TABS_PER_BROWSER tabs each
TABS_PER_BROWSER = 4  # SUCCESS_TAG_1591R17: four worker tabs
TAB_COUNT = BROWSER_COUNT * TABS_PER_BROWSER


def _is_auth_url(url):
    try:
        parsed = urlsplit(url)
        return (
            str(parsed.hostname or "").endswith(".beeline.ru")
            and "mobile-id-auth" in parsed.path
        )
    except Exception:
        return False


def _resend_locators(page):
    label = re.compile(
        r"^\s*(?:отправить\s+снова|отправить|повторить\s+ещ[её])\s*$",
        re.I,
    )
    return [
        page.get_by_role("button", name=label),
        page.locator("button").filter(has_text=label),
        page.locator('[role="button"]').filter(has_text=label),
        page.get_by_text(label, exact=True),
    ]


def try_click_resend_once(page, tab_id):
    """Одна быстрая попытка клика без блокирующего 15-секундного ожидания."""
    for locator in _resend_locators(page):
        try:
            count = locator.count()
        except Exception:
            continue
        for index in range(count):
            candidate = locator.nth(index)
            try:
                if not candidate.is_visible() or not candidate.is_enabled():
                    continue
                if candidate.get_attribute("disabled") is not None:
                    continue
                if candidate.get_attribute("aria-disabled") == "true":
                    continue
                if candidate.get_attribute("data-disabled") == "true":
                    continue
                label = (candidate.inner_text() or "").strip() or "Отправить снова"
                candidate.scroll_into_view_if_needed(timeout=1500)
                candidate.click(timeout=3000)
                print(f"[Вкладка {tab_id}] После 65 секунд нажата «{label}».", flush=True)
                return True
            except Exception:
                continue
    return False



def _worker_window_name(tab_id, generation=1, pid=None):
    pid = os.getpid() if pid is None else int(pid)
    return f"esim-worker-{int(tab_id)}-p{pid}-g{int(generation)}"


def _read_page_window_name(page):
    try:
        if page is not None and not page.is_closed():
            return str(page.evaluate("() => window.name || ''") or "")
    except Exception:
        pass
    return ""


def make_worker(tab_id, page, heartbeat=None, status_map=None):
    worker = {
        "id": tab_id,
        "page": page,
        "phase": "IDLE",
        "row": None,
        "diagnostic": None,
        "form_ready": False,
        "contact_digits": None,
        "contact_phone": None,
        "post_retry_deadline": None,
        "post_retries": 0,
        "auth_deadline": None,
        "auth_entered_at": None,
        "confirm_attempt": 0,
        "confirm_deadline": None,
        "resend_deadline": None,
        "stopped": False,
        "last_progress_at": monotonic(),
        "last_progress_label": "worker_created",
        "watchdog_restarts": 0,
        "heartbeat": heartbeat,
        "restart_close_deadline": None,
        "restart_in_progress": False,
        "generation": 1,
        "cancelling": False,

        "total_rows": None,
        "diagnostic_session_dir": None,
        "success_queue": None,
        "last_page_activity_at": monotonic(),
        "last_page_activity_kind": "worker_created",

        "status_map": status_map,
        "reserved_sim_number": None,
        "reserved_sim_url": None,
        "completed_confirm_cycle": False,
        "success_guard": False,
        "success_ai_last_at": 0.0,
        "region_fix_last_at": 0.0,
        "error_guard": False,
        "error_ai_last_at": 0.0,
    }

    def remember_auth(frame):
        # Событие навигации фиксирует реальный момент входа на mobile-id-auth,
        # даже если в этот момент диспетчер занят другой вкладкой.
        if _is_auth_url(frame.url):
            worker["auth_entered_at"] = monotonic()

    page.on("framenavigated", remember_auth)
    return worker


def save_worker_result(base_dir, worker, status):
    page = worker["page"]
    diagnostic = worker["diagnostic"]
    line_number, active_digits, _ = row_parts(worker["row"])
    if diagnostic is not None:
        try:
            diagnostic.snapshot("end")
        except Exception:
            pass
    save_result(
        base_dir / "results.jsonl",
        line_number,
        active_digits,
        status,
        page,
    )
    print(f"[Вкладка {worker['id']}] Результат строки {line_number}: {status}", flush=True)


# ROW_SKIP_PERSIST_1591R22
INVALID_ROW_MAX_ATTEMPTS = 2


def _invalid_row_retry_1591r22(worker):
    """A grey «Продолжить» can be the form's stale state rather than the row's data (the same
    aggregateId was seen across many rows). Retry the row once in a fresh tab."""
    key = _error_row_key(worker)
    counts = worker.setdefault("invalid_row_counts", {})
    counts[key] = int(counts.get(key) or 0) + 1
    if counts[key] >= INVALID_ROW_MAX_ATTEMPTS:
        return False
    print(
        f"[Вкладка {worker['id']}] Строка {key}: «Продолжить» серая — повторяю её один раз в новой вкладке.",
        flush=True,
    )
    restart_same_row_in_new_page(worker)
    if worker.get("phase") != "RESTART_ROW_READY":
        return False
    set_tab_status(worker, "♻️", f"Строка {key}: форма не приняла данные; повтор в новой вкладке.")
    external_heartbeat(worker, "invalid_row_retry")
    return True


def _fresh_tab_for_next_row_1591r22(worker):
    """Skip the row; the next one starts in a fresh tab, never in the used form."""
    restart_same_row_in_new_page(worker)
    if worker.get("phase") != "RESTART_ROW_READY":
        return False
    reset_runtime_state(worker)
    worker["form_ready"] = False
    worker["phase"] = "IDLE"
    external_heartbeat(worker, "invalid_row_skipped")
    return True


# ROW_RESTART_LIMIT_1591R32
ROW_RESTART_MAX = 3            # same-row restarts (new tab, same row) before the row is put back
ROW_DEFER_MAX_PER_RUN = 2      # a row is put back at most this many times per process launch
DEFERRED_ROWS_FILE_NAME = "deferred_rows.jsonl"


def _row_restart_exhausted_1591r32(worker, row, rows):
    """Count same-row restarts; past ROW_RESTART_MAX the row goes to the back of the queue
    and the slot (already on a fresh page) takes the next one. The number is not marked
    processed, so the row is tried again later in this run or at the next launch."""
    key = _row_number_value(row) if row is not None else ""
    counter = worker.get("row_restarts_1591r32") or {}
    attempts = int(counter.get(key) or 0) + 1
    worker["row_restarts_1591r32"] = {key: attempts}
    if attempts <= ROW_RESTART_MAX:
        return False
    tab_id = worker.get("id")
    line_number, active_digits, _ = row_parts(row)
    deferred = int(row.get("_deferred_1591r32") or 0) + 1 if isinstance(row, dict) else 1
    requeued = False
    if isinstance(row, dict) and deferred <= ROW_DEFER_MAX_PER_RUN and rows is not None:
        row["_deferred_1591r32"] = deferred
        try:
            rows.put(row)
            requeued = True
        except Exception as exc:
            print(f"[Вкладка {tab_id}] Строка {line_number} не вернулась в очередь: {type(exc).__name__}: {exc}", flush=True)
    note = ("вернул в конец очереди" if requeued
            else "оставил до следующего запуска (номер не помечен обработанным)")
    print(
        f"[Вкладка {tab_id}] Строка {line_number}: {ROW_RESTART_MAX} перезапуска подряд не помогли; "
        f"{note}, беру следующую.",
        flush=True,
    )
    try:
        base_dir = worker.get("base_dir")
        if base_dir:
            with open(Path(base_dir) / DEFERRED_ROWS_FILE_NAME, "a", encoding="utf-8") as handle:
                handle.write(json.dumps({"time": time.strftime("%Y-%m-%d %H:%M:%S"), "tab": tab_id,
                                         "row": line_number, "number": active_digits,
                                         "restarts": attempts - 1, "requeued": requeued},
                                        ensure_ascii=False) + "\n")
    except Exception:
        pass
    worker["row_restarts_1591r32"] = {}
    set_tab_status(worker, "⏭", f"Строка {line_number}: перезапуски исчерпаны, {note}")
    reset_runtime_state(worker)
    worker["form_ready"] = False
    worker["phase"] = "IDLE"
    external_heartbeat(worker, "row_deferred")
    return True


def reset_runtime_state(worker):
    worker["row"] = None
    worker["diagnostic"] = None
    worker["post_retry_deadline"] = None
    worker["post_retries"] = 0
    worker["auth_deadline"] = None
    worker["auth_entered_at"] = None
    worker["confirm_attempt"] = 0
    worker["confirm_deadline"] = None
    worker["resend_deadline"] = None
    worker["completed_confirm_cycle"] = False
    worker["success_guard"] = False
    worker["success_ai_last_at"] = 0.0
    worker["region_fix_last_at"] = 0.0
    worker["error_guard"] = False
    worker["error_ai_last_at"] = 0.0


def finish_worker_row(base_dir, worker, status):
    """Фиксирует результат и решает, можно ли этой вкладке брать следующую строку."""
    if status == "INVALID_ROW" and _invalid_row_retry_1591r22(worker):  # ROW_SKIP_PERSIST_1591R22
        return
    save_worker_result(base_dir, worker, status)

    if status == "INVALID_ROW":
        remember_processed_number(base_dir, worker.get("row"))
        if _fresh_tab_for_next_row_1591r22(worker):
            return
        worker["form_ready"] = True
        reset_runtime_state(worker)
        worker["phase"] = "IDLE"
        return

    if status == "CONFIRM_TIMEOUT":
        remember_processed_number(base_dir, worker.get("row"))
        diagnostic = worker["diagnostic"]
        page = worker["page"]
        if return_to_clean_registration_form(page, diagnostic):
            worker["form_ready"] = True
            reset_runtime_state(worker)
            worker["phase"] = "IDLE"
            return

        print(
            f"[Вкладка {worker['id']}] После 6 попыток не удалось вернуться к форме. "
            "Эта вкладка оставлена для проверки, остальные продолжают работу.",
            flush=True,
        )
        worker["stopped"] = True
        worker["phase"] = "STOPPED"
        return

    # Любой неизвестный финальный исход — не причина останавливать слот.
    # Повторяем ту же строку в новой рабочей вкладке.
    worker["form_ready"] = False
    print(
        f"[Вкладка {worker['id']}] Неожиданный итог {status} — "
        "восстанавливаю эту же строку.",
        flush=True,
    )
    restart_same_row_in_new_page(worker)
    return

    if status == "LEFT_AUTH_REVIEW":
        print(
            f"[Вкладка {worker['id']}] Страница подтверждения сменилась. "
            "Вкладка оставлена открытой для проверки; остальные продолжают.",
            flush=True,
        )
    elif status in ("ERROR", "AUTH_NOT_REACHED", "WINDOW_CLOSED"):
        print(
            f"[Вкладка {worker['id']}] Получен {status}. "
            "Вкладка оставлена открытой; остальные вкладки не останавливаются.",
            flush=True,
        )


def start_row_in_worker(base_dir, browser_version, worker, row):
    page = worker["page"]
    tab_id = worker["id"]
    line_number, active_digits, second_value = row_parts(row)
    worker["row"] = row
    worker["restart_in_progress"] = False
    tab_diag_dir = (
        Path(worker["diagnostic_session_dir"]) / f"tab_{tab_id}"
        if worker.get("diagnostic_session_dir")
        else DIAGNOSTICS_DIR / f"tab_{tab_id}"
    )
    worker["diagnostic"] = make_diagnostics(
        page, "chromium", browser_version, tab_diag_dir
    )
    # process_registration_row() is blocking, so expose the shared heartbeat entry
    # directly to the page for long protected stages.
    try:
        class _HeartbeatSlot:
            def __setitem__(self, key, value):
                hb = worker.get("heartbeat")
                if hb is None:
                    return
                info = dict(hb.get(str(worker["id"])) or {})
                info[key] = value
                info["time"] = monotonic()
                hb[str(worker["id"])] = info
        setattr(page, "_worker_heartbeat", _HeartbeatSlot())
    except Exception:
        pass
    # A replacement page is no longer RESTART_ROW_READY once this row starts.
    publish_worker_phase(worker, "ROW_START", "Начинаю обработку строки")

    # Matcher stages use the exact same publisher, so worker.phase, shared heartbeat
    # and Telegram/DeepSeek status can no longer disagree.
    configure_matcher_runtime(
        tab_id=tab_id,
        heartbeat=worker.get("heartbeat"),
        stage_callback=lambda stage: publish_worker_phase(
            worker,
            "PROTECTED_CHECK",
            "Защищённый этап активен",
            matcher_stage=stage,
        ),
    )

    # process_registration_row() cannot see worker directly, so expose one safe
    # phase publisher on this Page object.
    setattr(
        page,
        "_publish_worker_phase",
        lambda phase, note="": publish_worker_phase(worker, phase, note),
    )

    # process_registration_row() не получает worker напрямую. Передаём через
    # Page только cascade-event: он будет выставлен строго после того, как
    # protected overlay реально закрылся.
    setattr(page, "_launch_ready_event", worker.get("launch_ready_event"))

    if not worker["form_ready"]:
        worker["contact_digits"] = "791900011" + f"{secrets.randbelow(100):02d}"
        digits = worker["contact_digits"]
        worker["contact_phone"] = (
            f"+7 {digits[1:4]} {digits[4:7]} {digits[7:9]} {digits[9:11]}"
        )

    print(
        f"\n[Вкладка {tab_id}] Обрабатываю строку {line_number}, "
        f"номер заканчивается на {active_digits[-4:]}.",
        flush=True,
    )

    try:
        status = run_registration(
            page,
            worker["diagnostic"],
            worker["contact_phone"],
            worker["contact_digits"],
            active_digits,
            second_value,
            form_ready=worker["form_ready"],
            launch_ready_event=worker.get("launch_ready_event"),
        )
    except Exception as exc:
        message = str(exc)
        print(
            f"[Вкладка {tab_id}] Ошибка: {type(exc).__name__}: {exc}. "
            f"Диагностика: {worker['diagnostic'].path}",
            flush=True,
        )
        worker["diagnostic"].write(
            "batch_error", error_type=type(exc).__name__, message=message
        )
        capture_blackbox(worker, "batch_error", exc)
        closed_target = (
            "Target page, context or browser has been closed" in message
            or "TargetClosedError" in type(exc).__name__
            or "Page has been closed" in message
        )
        if closed_target and "RECOVERABLE_RESTART_ROW:" not in message:
            message = "RECOVERABLE_RESTART_ROW: рабочая вкладка неожиданно закрылась."

        if "RECOVERABLE_RESTART_ROW:" in message:
            print(
                f"[Вкладка {tab_id}] Локальное восстановление исчерпано. "
                "Закрываю проблемную вкладку и открываю новую с той же строкой.",
                flush=True,
            )
            restart_same_row_in_new_page(worker)
            return
        # Главное правило: неизвестная ошибка не останавливает рабочий слот
        # и не теряет текущую строку. Сохраняем BLACKBOX, закрываем старую
        # рабочую вкладку и повторяем эту же строку в новой.
        set_tab_status(
            worker,
            "♻️",
            f"Неизвестная ошибка: {type(exc).__name__}: {message[:350]}\n"
            "Восстанавливаю эту же строку.",
        )
        print(
            f"[Вкладка {tab_id}] Неизвестная ошибка — "
            "перезапускаю рабочую вкладку с той же строкой.",
            flush=True,
        )
        restart_same_row_in_new_page(worker)
        return

    if status == "INVALID_ROW":
        finish_worker_row(base_dir, worker, status)
        return

    if status == "PENDING_CONFIRM":
        cached_url = getattr(page, "_reserved_sim_url", None)
        cached_number = getattr(page, "_reserved_sim_number", None)
        if cached_url and not worker.get("reserved_sim_url"):
            worker["reserved_sim_url"] = cached_url
        if cached_number:
            worker["reserved_sim_number"] = cached_number
        elif getattr(page, "_reserved_sim_url_locked", False):
            print(
                f"[Вкладка {tab_id}] eSIM offer URL сохранён, "
                "но номер на offer-странице не был найден; "
                "поздний auth/form номер не подставляю.",
                flush=True,
            )
        else:
            capture_reserved_sim(page, worker, timeout=2)
        publish_worker_phase(worker, "CONFIRM", "Форма пройдена; ожидаю подтверждение")
        # launch_ready_event здесь намеренно НЕ выставляем.
        # Он разрешается только в process_registration_row после фактического
        # закрытия protected overlay.

    if status != "PENDING_CONFIRM":
        finish_worker_row(base_dir, worker, status)
        return

    # После клика «Продолжить» не ждём подтверждение внутри этой функции.
    # Дальше диспетчер опрашивает все активные worker-вкладки по кругу.
    worker["form_ready"] = False
    worker["phase"] = "POST_CONTINUE"
    external_heartbeat(worker, "post_continue")
    worker["post_retries"] = 0
    worker["post_retry_deadline"] = monotonic() + 5
    worker["auth_deadline"] = monotonic() + 60


def begin_confirmation(worker):
    now = monotonic()
    worker["phase"] = "CONFIRM"
    worker["confirm_attempt"] = 1
    entered_at = worker.get("auth_entered_at")
    worker["confirm_deadline"] = (entered_at if entered_at is not None else now) + 65
    external_heartbeat(worker, "confirm_wait")
    set_tab_status(worker, "🟡", "Ожидаю подтверждение: попытка 1/6")
    print(
        f"[Вкладка {worker['id']}] Экран подтверждения открыт. "
        "Запущен собственный таймер 65 секунд (попытка 1/6).",
        flush=True,
    )


def tick_post_continue(base_dir, worker):
    page = worker["page"]
    now = monotonic()

    # Критично: retry кнопки «Продолжить» допустим ТОЛЬКО пока мы всё ещё
    # на исходной форме с input[name="ctn"]. Если форма исчезла, переход
    # состоялся и на следующей странице эту кнопку больше не ищем.
    try:
        registration_field = page.locator('input[name="ctn"]')
        still_on_registration_form = (
            registration_field.count() > 0
            and registration_field.first.is_visible()
        )
    except Exception:
        still_on_registration_form = False

    if not still_on_registration_form:
        worker["diagnostic"].write(
            "registration_page_left",
            reason="ctn_field_disappeared",
        )
        print(
            f"[Вкладка {worker['id']}] Исходная форма закрылась — "
            "переход выполнен. На новой странице «Продолжить» не ищу.",
            flush=True,
        )
        worker["phase"] = "AUTH_WAIT"
        worker["auth_deadline"] = now + 60
        return

    if page.is_closed():
        print(
            f"[Вкладка {worker['id']}] Рабочая вкладка неожиданно закрыта — "
            "повторяю эту же строку.",
            flush=True,
        )
        restart_same_row_in_new_page(worker)
        return

    if _is_auth_url(page.url):
        begin_confirmation(worker)
        return

    continue_button = page.get_by_role(
        "button", name=re.compile(r"^\s*продолжить\s*$", re.I)
    )

    # Если исходная кнопка формы исчезла, считаем, что переход начался,
    # и ждём появления mobile-id-auth отдельно, не блокируя другие вкладки.
    try:
        if continue_button.count() == 0 or not continue_button.first.is_visible():
            worker["phase"] = "AUTH_WAIT"
            worker["auth_deadline"] = now + 60
            return
    except Exception:
        worker["phase"] = "AUTH_WAIT"
        worker["auth_deadline"] = now + 60
        return

    if _captcha_overlay_visible(page):
        return

    if now < worker["post_retry_deadline"]:
        return

    try:
        button = continue_button.first
        enabled = (
            button.is_visible()
            and button.is_enabled()
            and button.get_attribute("disabled") is None
            and button.get_attribute("aria-disabled") != "true"
            and button.get_attribute("data-disabled") != "true"
        )
    except Exception:
        worker["phase"] = "AUTH_WAIT"
        worker["auth_deadline"] = now + 60
        return

    if not enabled:
        worker["phase"] = "AUTH_WAIT"
        worker["auth_deadline"] = now + 60
        return

    if worker["post_retries"] >= 5:
        print(
            f"[Вкладка {worker['id']}] Форма осталась на месте после повторных "
            "попыток «Продолжить»; дальше жду переход без блокировки остальных.",
            flush=True,
        )
        worker["phase"] = "RESTART_ROW"
        return

    try:
        worker["diagnostic"].snapshot(
            f"before_continue_retry_{worker['post_retries'] + 1}"
        )
        button.click(timeout=5000)
        worker["post_retries"] += 1
        worker["post_retry_deadline"] = monotonic() + 5
        worker["diagnostic"].write(
            "continue_retry",
            attempt=worker["post_retries"],
            reason="form_still_visible_after_check",
        )
        print(
            f"[Вкладка {worker['id']}] Форма не ушла дальше — повторно нажимаю "
            f"«Продолжить» ({worker['post_retries']}/5).",
            flush=True,
        )
    except Exception as exc:
        worker["diagnostic"].write(
            "continue_retry_failed", error_type=type(exc).__name__
        )
        worker["phase"] = "AUTH_WAIT"
        worker["auth_deadline"] = monotonic() + 60


def tick_auth_wait(base_dir, worker):
    page = worker["page"]
    if page.is_closed():
        print(
            f"[Вкладка {worker['id']}] Рабочая вкладка неожиданно закрыта — "
            "повторяю эту же строку.",
            flush=True,
        )
        restart_same_row_in_new_page(worker)
        return
    if _is_auth_url(page.url):
        launch_event = worker.get("launch_ready_event")
        if launch_event is not None and not launch_event.is_set():
            launch_event.set()
            print(
                f"[Вкладка {worker['id']}] Auth открыт — protected stage завершён; "
                "разрешаю следующую вкладку этого Chromium.",
                flush=True,
            )
        begin_confirmation(worker)
        return
    try:
        current_url = page.url
    except Exception:
        current_url = ""

    if "/registration/error" in current_url:
        capture_blackbox(worker, "registration_error_page")
        print(
            f"[Вкладка {worker['id']}] Сайт открыл registration/error — "
            "сразу повторяю ту же строку.",
            flush=True,
        )
        restart_same_row_in_new_page(worker)
        return

    if monotonic() >= worker["auth_deadline"]:
        capture_blackbox(worker, "auth_not_reached")
        set_tab_status(worker, "♻️", "Переход не состоялся — повторяю эту же строку")
        print(
            f"[Вкладка {worker['id']}] Переход не состоялся — "
            "перезапускаю рабочую вкладку с той же строкой.",
            flush=True,
        )
        restart_same_row_in_new_page(worker)


def _signature_button_locator(page):
    button = page.get_by_role(
        "button",
        name=re.compile(r"^\s*подписать\s+договор\s*$", re.I),
    )
    try:
        if button.count() and button.first.is_visible():
            return button.first
    except Exception:
        pass
    fallback = page.get_by_text(
        re.compile(r"^\s*подписать\s+договор\s*$", re.I),
        exact=False,
    )
    try:
        if fallback.count() and fallback.first.is_visible():
            return fallback.first
    except Exception:
        pass
    return None


def _signature_page_hint(page):
    if _signature_button_locator(page) is not None:
        return True
    try:
        body = page.locator("body").inner_text(timeout=1000)
        if re.search(r"подпиш\w*\s+договор|подписать\s+договор", body, re.I):
            return True
    except Exception:
        pass
    try:
        canvases = page.locator("canvas")
        for i in range(min(canvases.count(), 10)):
            box = canvases.nth(i).bounding_box()
            if box and box["width"] >= 250 and box["height"] >= 120:
                return True
    except Exception:
        pass
    return False


def capture_all_form_fields_v1583(page):
    """Read-only snapshot of all form controls and their label metadata."""
    try:
        return page.evaluate("""() => {
          const out = [];
          for (const el of document.querySelectorAll('input,select,textarea')) {
            let label = '';
            try {
              if (el.id) {
                const l = document.querySelector('label[for="' + CSS.escape(el.id) + '"]');
                if (l) label = (l.innerText || l.textContent || '').trim();
              }
              if (!label) {
                const l = el.closest('label');
                if (l) label = (l.innerText || l.textContent || '').trim();
              }
            } catch (_) {}
            let value = '';
            try {
              value = (el.type === 'checkbox' || el.type === 'radio')
                ? (el.checked ? 'true' : 'false')
                : String(el.value == null ? '' : el.value);
            } catch (_) {}
            out.push({
              tag: (el.tagName || '').toLowerCase(),
              type: el.type || '',
              name: el.name || '',
              id: el.id || '',
              value,
              label,
              placeholder: el.placeholder || '',
              ariaLabel: el.getAttribute('aria-label') || '',
              disabled: !!el.disabled,
              readOnly: !!el.readOnly
            });
          }
          return out;
        }""")
    except Exception:
        return []


# PROFILE_LABELS_1591R19
_FORM_FIELDS_JS_1591R19 = r"""() => {
  const clean = s => String(s || '').replace(/\s+/g, ' ').trim();
  const hasControl = el => !!(el && el.querySelector && el.querySelector('input,select,textarea'));
  const shortText = el => { const t = clean(el && (el.innerText || el.textContent)); return t && t.length <= 80 ? t : ''; };
  const out = [];
  for (const el of document.querySelectorAll('input,select,textarea')) {
    let near = '';
    try {
      // 1. the wrapper of exactly this control that carries a short caption (floating labels)
      let node = el.parentElement;
      for (let depth = 0; depth < 5 && !near && node; depth++) {
        if (node.querySelectorAll('input,select,textarea').length !== 1) break;
        near = shortText(node);
        node = node.parentElement;
      }
      // 2. the caption rendered just before the control or its wrapper; another control
      //    in between means the caption belongs to that other field
      node = el;
      for (let depth = 0; depth < 3 && !near && node; depth++) {
        let sib = node.previousElementSibling;
        while (sib && !near) {
          if (sib.matches('input,select,textarea') || hasControl(sib)) break;
          near = shortText(sib);
          sib = sib.previousElementSibling;
        }
        node = node.parentElement;
      }
    } catch (_) {}
    const attrs = [];
    try {
      for (const a of el.attributes) {
        if (/^(data-|aria-|autocomplete$|title$|role$)/.test(a.name) && a.value) attrs.push(a.name + '=' + a.value);
      }
      const by = el.getAttribute('aria-labelledby');
      if (by) for (const id of by.split(/\s+/)) { const l = document.getElementById(id); if (l) attrs.push('labelledby=' + clean(l.textContent)); }
    } catch (_) {}
    let value = '';
    try {
      value = (el.type === 'checkbox' || el.type === 'radio') ? (el.checked ? 'true' : 'false')
                                                              : String(el.value == null ? '' : el.value);
    } catch (_) {}
    let label = '';
    try {
      if (el.id) { const l = document.querySelector('label[for="' + CSS.escape(el.id) + '"]'); if (l) label = clean(l.textContent); }
      if (!label) { const l = el.closest('label'); if (l) label = clean(l.textContent); }
    } catch (_) {}
    out.push({tag: (el.tagName || '').toLowerCase(), type: el.type || '', name: el.name || '', id: el.id || '',
              value, label, placeholder: el.placeholder || '', ariaLabel: el.getAttribute('aria-label') || '',
              near, attrs: attrs.join(' ')});
  }
  return out;
}"""


def capture_form_fields_1591r19(page):
    """capture_all_form_fields_v1583 plus `near` (the closest label-like text around the
    control) and `attrs` (data-/aria-/autocomplete attributes). Read-only."""
    try:
        data = page.evaluate(_FORM_FIELDS_JS_1591R19)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _alias_hit_1591r19(hay, word):
    """Short aliases («пол», «дом», «край», «ул.») must be whole words: «поле», «домашний»
    and «крайний» in a hint next to the field are not labels."""
    word = word.replace("ё", "е")
    if len(word) <= 4:
        return re.search(r"(?<![а-яa-z0-9])" + re.escape(word) + r"(?![а-яa-z0-9])", hay) is not None
    return word in hay


_DATE_FIELD_RE_1591R19 = re.compile(r"^\d{2}[.\-/]\d{2}[.\-/]\d{4}$")
_SKIP_FIELD_TYPES_1591R19 = {"checkbox", "radio", "hidden", "submit", "button", "password", "file"}


def _profile_fallback_1591r19(profile, fields, consumed):
    """Fields with no caption anywhere: the full name and the birth date by value shape, the
    four address inputs between «страна» and «дом» by their position on the form."""
    text_inputs = [(i, f) for i, f in enumerate(fields)
                   if str(f.get("tag") or "input").lower() == "input"
                   and str(f.get("type") or "text").lower() not in _SKIP_FIELD_TYPES_1591R19]
    issue_date = str(profile.get("passport_issue_date") or "").strip()
    for i, f in text_inputs:
        value = str(f.get("value") or "").strip()
        if i in consumed or not value:
            continue
        if not profile.get("full_name") and " " in value and _FIO_RE_1591R12.match(value):
            profile["full_name"] = value
            consumed.add(i)
            continue
        if (not profile.get("birth_date") and _DATE_FIELD_RE_1591R19.match(value) and value != issue_date
                and (_DATE_FIELD_RE_1591R19.match(str(f.get("placeholder") or "").strip())
                     or "рожд" in str(f.get("near") or "").lower())):
            profile["birth_date"] = value
            consumed.add(i)
    ids = [str(f.get("id") or "").lower() for f in fields]
    if "country" in ids and "house" in ids and ids.index("country") < ids.index("house"):
        a, b = ids.index("country"), ids.index("house")
        between = [(i, f) for i, f in text_inputs if a < i < b]
        if len(between) == 4:
            for (i, f), key in zip(between, ("region", "district", "locality", "street")):
                value = str(f.get("value") or "").strip()
                if i not in consumed and len(value) >= 2 and not profile.get(key):
                    profile[key] = value
                    consumed.add(i)
    return profile


def final_profile_capture_v1583(page, worker):
    fields = capture_all_form_fields_v1583(page)
    worker["final_form_fields"] = fields
    try:
        d = worker.get("diagnostic")
        if d:
            d.write("final_form_capture_v1583", fields=fields, url=page.url)
    except Exception:
        pass

    profile = _io1591.merge_capture(worker.get("success_profile"), worker.get("profile"))
    aliases = {
        "full_name": ("фио", "фамилия имя отчество", "фамилия", "ф.и.о", "ф. и. о", "fullname", "full_name",
                      "autocomplete=name"),  # PROFILE_LABELS_1591R19
        "gender": ("пол", "gender"),
        "birth_date": ("дата рождения", "дата рожд", "рождения", "birth", "birthday", "bday"),
        "passport_series": ("серия паспорта", "passport series", "series"),
        "passport_number": ("номер паспорта", "passport number", "passportnumber"),
        "passport_issue_date": ("дата выдачи", "issue date", "issuedate"),
        "passport_issued_by": ("кем выдан", "issuer", "issued by"),
        "country": ("страна", "country"),
        "region": ("область", "регион", "край", "республика", "region", "address-level1"),
        "district": ("район", "р-н", "district"),
        "locality": ("населённый пункт", "населенный пункт", "населённый", "населенный", "город", "city",
                     "locality", "address-level2"),
        "street": ("улица", "ул.", "street", "address-line1"),
        "house": ("дом", "house"),
        "building": ("корпус", "building"),
        "apartment": ("квартира", "apartment", "flat"),
    }
    extended = capture_form_fields_1591r19(page)  # PROFILE_LABELS_1591R19
    if extended:
        try:
            d = worker.get("diagnostic")
            if d:
                d.write("form_fields_1591r19", fields=extended, url=page.url)
        except Exception:
            pass
    matched = extended or fields
    consumed = set()
    for index, f in enumerate(matched):
        value = str(f.get("value") or "").strip()
        if not value or str(f.get("type") or "").lower() in _SKIP_FIELD_TYPES_1591R19:
            continue
        if not re.search(r"[0-9a-zа-яё]", value.lower()):  # SIGN_TRACE_1591R25: a lone «.» is not a value
            continue
        hay = " ".join(str(f.get(k) or "") for k in
                       ("label", "name", "id", "placeholder", "ariaLabel", "near", "attrs")).lower().replace("ё", "е")
        for key, words in aliases.items():
            if profile.get(key):
                continue
            if any(_alias_hit_1591r19(hay, word) for word in words):
                profile[key] = value
                consumed.add(index)
                break
    _profile_fallback_1591r19(profile, matched, consumed)
    worker["success_profile"] = profile
    worker["profile"] = dict(profile)
    return profile, fields


def finalize_success(base_dir, worker):

    # FINAL_SUCCESS_GUARD_V1583
    page = worker.get("page")
    if page is not None and _post_auth_error_page(page):
        print(
            f"[Вкладка {worker.get('id')}] FALSE SUCCESS BLOCKED: /registration/error",
            flush=True,
        )
        try:
            capture_blackbox(worker, "blocked_false_success_registration_error")
        except Exception:
            pass
        enter_error_guard(worker, "finalize_success blocked on registration/error")
        return False

    if page is not None:
        final_profile_capture_v1583(page, worker)
    page = worker["page"]
    row_no, _, _ = row_parts(worker.get("row"))

    # Last chance to capture visible contract values before publishing.
    try:
        capture_contract_details(page, worker)
    except Exception:
        pass

    try:
        worker["diagnostic"].write(
            "confirmation_success_stop", row_no=row_no, url=page.url
        )
    except Exception:
        pass

    # Do not overwrite the original eSIM page URL with a later page URL.
    if not worker.get("reserved_sim_number"):
        capture_reserved_sim(page, worker, timeout=1)

    worker["phase"] = "SUCCESS_STOP"
    rec = write_success_record(base_dir, worker)
    remember_processed_number(base_dir, worker.get("row"))

    success_queue = worker.get("success_queue")
    if success_queue is not None:
        try:
            success_queue.put(_success_message(worker, rec))
        except Exception as exc:
            print(
                f"[Telegram] Не удалось поставить SUCCESS в очередь: "
                f"{type(exc).__name__}: {exc}",
                flush=True,
            )

    set_tab_status(
        worker,
        "✅",
        (
            f"УСПЕХ\nSIM: {rec.get('sim_number') or 'не найден'}\n"
            f"Ссылка: {rec.get('sim_url') or 'не найдена'}\n"
            "Успешная вкладка оставлена открытой. Для очереди будет создана новая."
        ),
    )
    external_heartbeat(worker, "success_stop")
    print(
        f"\n[Вкладка {worker['id']}] ✅ ПОДТВЕРЖДЕНО УСПЕШНО. "
        f"Строка {row_no}. Эту вкладку оставляю открытой; "
        "рабочий слот будет заменён новой вкладкой.\n",
        flush=True,
    )
    worker["stopped"] = True



# PERSDATA_SKIP_1591R15
ERROR_FINAL_NEEDLES_1591R15 = (
    ("данные не прошли проверку", "данные не прошли проверку у оператора"),
    ("укажите другой свой номер", "оператор просит указать другой номер"),
    ("persdata_not_match", "PERSDATA_NOT_MATCH"),
    ("не совпадают с данными", "данные не совпадают с базой оператора"),
)


def _error_page_final_reason(page):
    """Reason text when the error page is a deterministic operator refusal, else None."""
    try:
        body = (page.locator("body").inner_text(timeout=1500) or "").lower()
    except Exception:
        return None
    for needle, reason in ERROR_FINAL_NEEDLES_1591R15:
        if needle in body:
            return reason
    return None


def _error_skip_final(worker, reason):
    """Skip the row at once: a retry cannot change the operator's answer.

    Same steps as the second-error skip of ERROR_RECOVERY_1591R5, minus the analysis
    and the retry: fresh page, record in error_skipped_rows.txt, Telegram notice, IDLE.
    """
    key = _error_row_key(worker)
    base_dir = worker.get("base_dir") or Path(__file__).resolve().parent
    try:
        capture_blackbox(worker, "error_final_skip")
    except Exception:
        pass
    print(
        f"[Вкладка {worker['id']}] registration/error: {reason}. Повтор бессмыслен — "
        f"строка {key} пропускается без анализа.",
        flush=True,
    )
    worker["error_guard"] = False
    worker["success_guard"] = False
    worker["error_assist_entered_at"] = None
    worker["auto_assist_state"] = {}
    worker["phase"] = "ERROR_RECOVERY"
    restart_same_row_in_new_page(worker)
    if worker.get("phase") != "RESTART_ROW_READY":
        print(f"[Вкладка {worker['id']}] Новая вкладка не создана; строка {key} будет повторена.", flush=True)
        return False
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
                f"⏭ Вкладка {worker['id']}: строка {key} пропущена без повтора: {reason}. "
                "Worker продолжает со следующей строкой.",
            )
    except Exception:
        pass
    remember_processed_number(base_dir, worker.get("row"))  # ROW_SKIP_PERSIST_1591R22: not back after a restart
    worker["row"] = None
    worker["phase"] = "IDLE"
    set_tab_status(worker, "⏭", f"Строка {key} пропущена: {reason}. Беру следующую.")
    external_heartbeat(worker, "error_row_skipped_final")
    return True


def enter_error_guard(worker, note):
    # ERROR_SKIP_ALWAYS_1591R16: every /registration/error after the confirmation is handled
    # without DeepSeek: the tab is replaced and the row is skipped at once. A page that names
    # the cause (PERSDATA_SKIP_1591R15) supplies the precise reason for the record.
    reason = _error_page_final_reason(worker.get("page")) or "registration/error после подтверждения"
    if _error_skip_final(worker, reason):
        return
    # No fresh page yet: the error tick repeats the skip after a short dwell, still without
    # an analysis request (the repeat-error branch of ERROR_RECOVERY_1591R5).
    worker.setdefault("error_retry_counts", {})[_error_row_key(worker)] = ERROR_ROW_MAX_ATTEMPTS - 1
    worker["error_guard"] = True
    worker["success_guard"] = False
    worker["phase"] = "ERROR_ASSIST"
    set_tab_status(
        worker, "♻️",
        "Registration error — вкладка будет перезапущена, строка пропущена. DeepSeek не вызывается."
    )
    external_heartbeat(worker, note)


# ERROR_RECOVERY_1591R5
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
    remember_processed_number(base_dir, worker.get("row"))  # ROW_SKIP_PERSIST_1591R22: not back after a restart
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


def _post_auth_error_page(page):
    try:
        low = str(page.url or "").lower()
        if "/registration/error" in low:
            return True
    except Exception:
        pass
    try:
        body = (page.locator("body").inner_text(timeout=1500) or "").lower()
        needles = (
            "что-то пошло не так",
            "произошла ошибка",
            "не удалось продолжить",
        )
        return any(x in body for x in needles)
    except Exception:
        return False


def _post_auth_contract_page(page):
    try:
        low = str(page.url or "").lower()
        if "personal-data-form" in low:
            return True
    except Exception:
        pass
    try:
        return bool(_signature_page_hint(page) or _signature_button_locator(page))
    except Exception:
        return False


def _region_input_candidates(page):
    # Prefer semantic attributes and only then nearby label text.
    rx = re.compile(r"(область|регион|region)", re.I)
    return [
        page.locator(
            'input[name*="region" i], input[id*="region" i], '
            'input[name*="area" i], input[id*="area" i], '
            'input[placeholder*="область" i], input[aria-label*="область" i], '
            'input[placeholder*="регион" i], input[aria-label*="регион" i]'
        ),
        page.get_by_label(rx),
    ]


def ensure_region_if_missing(page, diagnostic=None):
    """Fill Saratov region only when the region field is actually empty/invalid."""
    needs_region = False
    try:
        err = page.get_by_text(re.compile(r"^\s*укажите\s+область\s*$", re.I))
        needs_region = bool(err.count() and err.first.is_visible())
    except Exception:
        pass

    target = None
    for group in _region_input_candidates(page):
        try:
            for i in range(group.count()):
                loc = group.nth(i)
                if not loc.is_visible():
                    continue
                value = (loc.input_value(timeout=1200) or "").strip()
                if value:
                    # Normally the site fills it itself. Never overwrite a value.
                    return True
                target = loc
                needs_region = True
                break
        except Exception:
            continue
        if target is not None:
            break

    if not needs_region or target is None:
        return not needs_region

    try:
        target.fill("Саратовская область", timeout=4000)
        page.wait_for_timeout(450)

        # Autocomplete variants. Select only Saratov region.
        options = [
            page.get_by_role(
                "option",
                name=re.compile(r"Саратовск(ая|ой)\s+област", re.I),
            ),
            page.locator('[role="listbox"] *').filter(
                has_text=re.compile(r"Саратовск(ая|ой)\s+област", re.I)
            ),
            page.get_by_text(
                re.compile(r"^\s*Саратовская\s+область\s*$", re.I),
                exact=True,
            ),
        ]
        for group in options:
            try:
                if group.count() and group.first.is_visible():
                    group.first.click(timeout=3000, no_wait_after=True)
                    page.wait_for_timeout(350)
                    break
            except Exception:
                continue

        value = (target.input_value(timeout=1500) or "").strip()
        ok = bool(value)
        if diagnostic is not None:
            try:
                diagnostic.write(
                    "region_autofill_if_missing",
                    value=value,
                    ok=ok,
                )
            except Exception:
                pass
        print(
            f"[Договор] Область была пустой — "
            f"{'заполнена: '+value if ok else 'попытка заполнения выполнена'}",
            flush=True,
        )
        return ok
    except Exception as exc:
        if diagnostic is not None:
            try:
                diagnostic.write(
                    "region_autofill_failed",
                    error_type=type(exc).__name__,
                    message=str(exc)[:500],
                )
            except Exception:
                pass
        return False


def enter_success_guard(worker, note):
    if not worker.get("success_guard"):
        worker["success_guard"] = True
        print(
            f"[Вкладка {worker['id']}] 🔒 SUCCESS GUARD: {note}. "
            "Close/reload/restart/back/navigation запрещены.",
            flush=True,
        )
    publish_worker_phase(worker, "POST_AUTH_REVIEW", note)
    queue_success_assist(worker, note, force=True)


def tick_post_auth_review(base_dir, worker):
    page = worker["page"]

    # Once mobile-id succeeded, this physical page is sacred. Never recover it.
    worker["success_guard"] = True

    if page.is_closed():
        worker["phase"] = "SUCCESS_STOP"
        worker["stopped"] = True
        set_tab_status(
            worker, "🔴",
            "Успешная post-auth вкладка была закрыта извне. Автоповтор ЗАПРЕЩЁН."
        )
        return

    try:
        capture_contract_details(page, worker)
    except Exception:
        pass

    # POST_AUTH_ERROR_ROUTE_1591R14: /registration/error after auth is an ERROR under the
    # registration/error policy (revision 5): DeepSeek analyses, then the runtime closes
    # the tab, opens a new one and retries the row once; a repeat skips the row. This
    # used to become SUCCESS_ASSIST, which has no recovery, and the worker waited for ever.
    if _post_auth_error_page(page):
        capture_blackbox(worker, "registration_error_after_auth")
        print(
            f"[Вкладка {worker['id']}] На post-auth странице открылась /registration/error. "
            "Это НЕ success. Сначала DeepSeek анализирует страницу; затем runtime повторит "
            "строку по правилу registration/error.",
            flush=True,
        )
        enter_error_guard(
            worker,
            "после mobile-id-auth открылась /registration/error (post-auth review)",
        )
        return

    # Site normally fills region itself. Touch it only when it is genuinely empty.
    now = monotonic()
    if now - float(worker.get("region_fix_last_at") or 0) >= 4:
        worker["region_fix_last_at"] = now
        region_ok = ensure_region_if_missing(page, worker.get("diagnostic"))
        if not region_ok:
            queue_success_assist(worker, "область отсутствует или не принялась")

    button = _signature_button_locator(page)
    if button is not None:
        try:
            enabled = button.is_enabled()
        except Exception:
            enabled = False

        if not enabled:
            worker["phase"] = "SUCCESS_ASSIST"
            set_tab_status(
                worker, "🧠",
                "Подтверждение успешно. Кнопка договора пока неактивна — DeepSeek наблюдает/исправляет."
            )
            external_heartbeat(worker, "signature_button_disabled")
            queue_success_assist(worker, "кнопка «Подписать договор» неактивна")
            return

        try:
            set_tab_status(
                worker, "✍️",
                "Подтверждение успешно. Заполняю подпись и подписываю договор."
            )
            capture_contract_details(page, worker)
            _sign_trace_begin_1591r25(page, worker)  # SIGN_TRACE_1591R25
            try:
                fill_signature_and_submit(page, worker.get("diagnostic"))
            finally:
                _sign_trace_end_1591r25(page, worker)
            worker["phase"] = "SIGN_WAIT"
            worker["sign_submit_url"] = page.url
            worker["sign_button_gone_since"] = None
            external_heartbeat(worker, "signature_submitted_success_guard")
            queue_success_assist(worker, "подпись отправлена; наблюдай результат")
            return
        except Exception as exc:
            capture_blackbox(worker, "signature_submit_failed", exc)
            worker["phase"] = "SUCCESS_ASSIST"
            set_tab_status(
                worker, "🧠",
                "Подтверждение успешно. Ошибка при подписи — DeepSeek помогает, страницу не трогаю."
            )
            print(
                f"[Вкладка {worker['id']}] Ошибка подписи: "
                f"{type(exc).__name__}: {exc}. SUCCESS GUARD — без restart/reload.",
                flush=True,
            )
            queue_success_assist(
                worker,
                f"ошибка подписи {type(exc).__name__}: {str(exc)[:300]}",
                force=True,
            )
            return

    # Contract UI may render indefinitely; there is deliberately NO destructive timeout.
    if _signature_page_hint(page) or _post_auth_contract_page(page):
        worker["phase"] = "SUCCESS_ASSIST"
        set_tab_status(
            worker, "🧠",
            "Подтверждение успешно. Жду/проверяю интерфейс договора; DeepSeek наблюдает."
        )
        external_heartbeat(worker, "success_waiting_contract_ui")
        queue_success_assist(worker, "интерфейс договора требует наблюдения")
        return

    # If we are post-auth and no contract controls remain, settle as success — only with
    # positive evidence of the signed contract (SIGNED_EVIDENCE_1591R24).
    settle_success_1591r24(base_dir, worker)


def tick_success_assist(base_dir, worker):
    # Same guarded logic, but never adds a destructive timeout.
    tick_post_auth_review(base_dir, worker)


# SIGN_TRACE_1591R25
SIGN_TRACE_SECONDS = 8
_SIGN_TRACE_SKIP_RE_1591R25 = re.compile(
    r"\.(png|jpe?g|gif|svg|webp|css|js|woff2?|ttf|ico)(\?|$)|metrika|analytics|google|flocktory|yandex|gtm",
    re.I,
)


def _sign_trace_begin_1591r25(page, worker):
    """Start collecting what the page does right after «Подписать договор» is clicked."""
    trace = {"started": time.time(), "url_before": "", "responses": [], "failed": [], "console": [],
             "_pending": [], "_handlers": {}}
    try:
        trace["url_before"] = str(page.url or "")
    except Exception:
        pass

    def on_response(resp):
        try:
            url = str(resp.url or "")
            if _SIGN_TRACE_SKIP_RE_1591R25.search(url) or len(trace["responses"]) >= 40:
                return
            item = {"t": round(time.time() - trace["started"], 2), "method": str(resp.request.method),
                    "status": int(resp.status), "url": url[:300]}
            trace["responses"].append(item)
            ctype = str(resp.headers.get("content-type", "") or "")
            if "json" in ctype or item["status"] >= 400 or item["method"] in ("POST", "PUT", "PATCH"):
                trace["_pending"].append((resp, item))
        except Exception:
            pass

    def on_failed(req):
        try:
            if len(trace["failed"]) < 20 and not _SIGN_TRACE_SKIP_RE_1591R25.search(str(req.url or "")):
                trace["failed"].append({"t": round(time.time() - trace["started"], 2), "url": str(req.url)[:300],
                                        "error": str(req.failure or "")[:200]})
        except Exception:
            pass

    def on_console(msg):
        try:
            if msg.type in ("error", "warning") and len(trace["console"]) < 30:
                trace["console"].append({"t": round(time.time() - trace["started"], 2), "type": str(msg.type),
                                         "text": str(msg.text)[:300]})
        except Exception:
            pass

    for event, fn in (("response", on_response), ("requestfailed", on_failed), ("console", on_console)):
        try:
            page.on(event, fn)
            trace["_handlers"][event] = fn
        except Exception:
            pass
    worker["sign_trace"] = trace
    return trace


def _sign_trace_end_1591r25(page, worker, note=""):
    """Wait SIGN_TRACE_SECONDS after the click, read the bodies, record the trace."""
    trace = worker.get("sign_trace")
    if not trace or "_handlers" not in trace:
        return trace
    deadline = monotonic() + SIGN_TRACE_SECONDS
    while monotonic() < deadline:
        try:
            page.wait_for_timeout(250)
        except Exception:
            break
    for event, fn in (trace.pop("_handlers", None) or {}).items():
        try:
            page.remove_listener(event, fn)
        except Exception:
            pass
    for resp, item in trace.pop("_pending", None) or []:
        try:
            item["body"] = re.sub(r"\s+", " ", str(resp.text() or ""))[:1500]
        except Exception as exc:
            item["body_error"] = f"{type(exc).__name__}"
    try:
        trace["url_after"] = str(page.url or "")
    except Exception:
        trace["url_after"] = ""
    trace["note"] = str(note or "")
    try:
        diagnostic = worker.get("diagnostic")
        if diagnostic:
            diagnostic.write("sign_click_trace_1591r25", **{k: v for k, v in trace.items() if not k.startswith("_")})
    except Exception:
        pass
    try:
        capture_blackbox(worker, "after_sign_click")
    except Exception:
        pass
    print(
        f"[Вкладка {worker.get('id')}] SIGN TRACE: {trace['url_before']} -> {trace['url_after']}; "
        f"ответов {len(trace['responses'])}, сбоев сети {len(trace['failed'])}, console {len(trace['console'])}",
        flush=True,
    )
    return trace


def _sign_trace_summary_1591r25(trace):
    if not trace:
        return None
    keep = [r for r in trace.get("responses") or []
            if int(r.get("status") or 0) >= 400 or "body" in r or r.get("method") in ("POST", "PUT", "PATCH")]
    return {"url_before": trace.get("url_before") or "", "url_after": trace.get("url_after") or "",
            "responses": keep[:12], "failed": (trace.get("failed") or [])[:10], "console": (trace.get("console") or [])[:10]}


def _sign_trace_lines_1591r25(summary):
    """TRACE_COMPACT_1591R35: one line in Telegram (the full trace stays in the jsonl record and
    the journal); HTTP errors, network failures and console errors are still listed."""
    if not summary:
        return []
    responses = summary.get("responses") or []

    def _status(response):
        try:
            return int(response.get("status") or 0)
        except (TypeError, ValueError):
            return 0

    signed = [r for r in responses if "checksignature" in str(r.get("url") or "").lower()]
    passport = [r for r in responses if "sendpassportdata" in str(r.get("url") or "").lower()]
    parts = []
    if signed:
        parts.append(f"подпись → {_status(signed[-1])}")
    if passport:
        parts.append(f"паспортные данные → {_status(passport[-1])}")
    if not parts:
        parts.append("запрос подписи в сети не замечен" if not responses else f"ответов {len(responses)}")
    out = ["Подпись (сеть): " + ", ".join(parts)]
    for r in [r for r in responses if _status(r) >= 400][:3]:
        line = f"  {r.get('method')} {r.get('url')} → {r.get('status')}"
        if r.get("body"):
            line += " " + str(r["body"])[:160]
        out.append(line)
    for f in (summary.get("failed") or [])[:3]:
        out.append(f"  сеть: {f.get('url')} — {f.get('error')}")
    for c in (summary.get("console") or [])[:3]:
        out.append(f"  console {c.get('type')}: {c.get('text')}")
    return out


# SIGNED_EVIDENCE_1591R24
SIGNED_URL_HINTS_1591R24 = ("success", "complete", "done", "thank", "activation", "signed", "esim/ready")
SIGNED_TEXT_NEEDLES_1591R24 = (
    "договор подписан", "успешно подписан", "подписание завершено", "договор успешно",
    "договор отправлен", "спасибо за", "esim готова", "esim активирована", "qr-код", "скачать договор",
)
UNVERIFIED_HOLD_SECONDS = 180


def _signed_evidence_1591r24(page):
    """A positive sign of a signed contract on the page; a vanished button is not one."""
    try:
        url = str(page.url or "").lower()
    except Exception:
        url = ""
    if "personal-data" in url or "mobile-id" in url:
        return ""
    for hint in SIGNED_URL_HINTS_1591R24:
        if hint in url:
            return f"url:{hint}"
    try:
        body = (page.locator("body").inner_text(timeout=1500) or "").lower()
    except Exception:
        body = ""
    for needle in SIGNED_TEXT_NEEDLES_1591R24:
        if needle in body:
            return f"text:{needle}"
    try:
        if page.locator("a[href$='.pdf'], a[download]").count():
            return "link:document"
    except Exception:
        pass
    return ""


def _unverified_message_1591r24(worker, rec):
    row_no, active_value, second_value = row_parts(worker.get("row"))
    return "\n".join([
        "#неподтверждено",
        f"⚠️ ПОДПИСЬ НЕ ПОДТВЕРЖДЕНА — Вкладка {worker['id']}",
        f"Строка: {row_no}/{worker.get('total_rows') or '?'}",
        f"Исходные данные: {active_value} | {second_value}",
        f"Причина: {rec.get('reason') or '—'}",
        f"Страница: {rec.get('final_url') or '—'}",
        f"Заголовок страницы: {rec.get('final_title') or '—'}",
        *_final_links_lines_1591r23(rec.get("final_links")),
        *_sign_trace_lines_1591r25(rec.get("sign_trace")),  # SIGN_TRACE_1591R25
        "",
        *_success_profile_lines(rec.get("profile")),
        "",
        f"eSIM: {rec.get('sim_number') or '—'}",
        f"Ссылка eSIM: {rec.get('sim_url') or '—'}",
        "Номер НЕ помечен обработанным; вкладка оставлена открытой для проверки.",
    ])


def _finish_unverified_1591r24(base_dir, worker, reason):
    """The signing could not be confirmed: record it apart from the successes and stop the tab."""
    n, a, b = row_parts(worker.get("row"))
    final = capture_final_page_1591r23(worker.get("page"), worker)
    rec = {
        "tab": worker["id"], "row": n, "active_digits": a, "second_value": b,
        "sim_number": worker.get("reserved_sim_number"), "sim_url": worker.get("reserved_sim_url"),
        "profile": dict(worker.get("success_profile") or {}),
        "final_url": final.get("url") or "", "final_title": final.get("title") or "",
        "final_links": list(final.get("links") or []), "reason": str(reason or ""),
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "sign_trace": _sign_trace_summary_1591r25(worker.get("sign_trace")),  # SIGN_TRACE_1591R25
    }
    try:
        with (Path(base_dir) / "unverified_signatures.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception as exc:
        print(f"[Вкладка {worker['id']}] unverified_signatures.jsonl не записан: {type(exc).__name__}: {exc}", flush=True)
    worker["phase"] = "SUCCESS_STOP"
    success_queue = worker.get("success_queue")
    if success_queue is not None:
        try:
            success_queue.put(_unverified_message_1591r24(worker, rec))
        except Exception as exc:
            print(f"[Telegram] Не удалось поставить UNVERIFIED в очередь: {type(exc).__name__}: {exc}", flush=True)
    set_tab_status(
        worker, "⚠️",
        f"ПОДПИСЬ НЕ ПОДТВЕРЖДЕНА\n{reason}\nСтраница: {rec['final_url'] or '—'}\n"
        "Вкладка оставлена открытой. Для очереди будет создана новая.",
    )
    external_heartbeat(worker, "success_unverified_stop")
    print(
        f"\n[Вкладка {worker['id']}] ⚠️ ПОДПИСЬ НЕ ПОДТВЕРЖДЕНА. Строка {n}: {reason}. "
        "Номер не помечен обработанным; вкладка оставлена открытой.\n",
        flush=True,
    )
    worker["stopped"] = True
    return rec


# PAYMENT_STEP_1591R26
PAYMENT_NEEDLES_1591R26 = (
    "пора оплатить", "оплатить картой", "оплатите картой", "дождитесь регистрации договора",
    "оплата esim", "оплатить esim", "к оплате",
)


def _payment_page_1591r26(page):
    """Text of the payment step when the site asks to pay for the eSIM after the signature."""
    try:
        body = (page.locator("body").inner_text(timeout=1500) or "")
    except Exception:
        return ""
    low = body.lower()
    for needle in PAYMENT_NEEDLES_1591R26:
        if needle in low:
            start = max(0, low.index(needle) - 120)
            return re.sub(r"\s+", " ", body[start:start + 360]).strip()
    return ""


def _payment_message_1591r26(worker, rec):
    row_no, active_value, second_value = row_parts(worker.get("row"))
    return "\n".join([
        "#оплата",
        f"💳 ТРЕБУЕТСЯ ОПЛАТА eSIM — Вкладка {worker['id']}",
        f"Строка: {row_no}/{worker.get('total_rows') or '?'}",
        f"Исходные данные: {active_value} | {second_value}",
        "Подпись принята сайтом; договор регистрируется только после оплаты картой.",
        f"Текст шага: {rec.get('payment_text') or '—'}",
        f"Страница: {rec.get('final_url') or '—'}",
        *_final_links_lines_1591r23(rec.get("final_links")),
        *_sign_trace_lines_1591r25(rec.get("sign_trace")),
        "",
        *_success_profile_lines(rec.get("profile")),
        "",
        f"eSIM: {rec.get('sim_number') or '—'}",
        f"Ссылка eSIM: {rec.get('sim_url') or '—'}",
        "Номер помечен обработанным (повтор создал бы второй заказ); вкладка оставлена открытой.",
    ])


def _finish_payment_required_1591r26(base_dir, worker, payment_text):
    """The site wants the eSIM paid: record it apart from the successes and stop the tab."""
    n, a, b = row_parts(worker.get("row"))
    final = capture_final_page_1591r23(worker.get("page"), worker)
    rec = {
        "tab": worker["id"], "row": n, "active_digits": a, "second_value": b,
        "sim_number": worker.get("reserved_sim_number"), "sim_url": worker.get("reserved_sim_url"),
        "profile": dict(worker.get("success_profile") or {}),
        "final_url": final.get("url") or "", "final_title": final.get("title") or "",
        "final_links": list(final.get("links") or []), "payment_text": str(payment_text or ""),
        "sign_trace": _sign_trace_summary_1591r25(worker.get("sign_trace")),
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    try:
        with (Path(base_dir) / "payment_required.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception as exc:
        print(f"[Вкладка {worker['id']}] payment_required.jsonl не записан: {type(exc).__name__}: {exc}", flush=True)
    remember_processed_number(base_dir, worker.get("row"))
    worker["phase"] = "SUCCESS_STOP"
    success_queue = worker.get("success_queue")
    if success_queue is not None:
        try:
            success_queue.put(_payment_message_1591r26(worker, rec))
        except Exception as exc:
            print(f"[Telegram] Не удалось поставить PAYMENT в очередь: {type(exc).__name__}: {exc}", flush=True)
    set_tab_status(
        worker, "💳",
        f"ТРЕБУЕТСЯ ОПЛАТА eSIM\n{rec['payment_text'][:160]}\nСтраница: {rec['final_url'] or '—'}\n"
        "Вкладка оставлена открытой. Для очереди будет создана новая.",
    )
    external_heartbeat(worker, "payment_required_stop")
    print(
        f"\n[Вкладка {worker['id']}] 💳 ТРЕБУЕТСЯ ОПЛАТА. Строка {n}: подпись принята, договор регистрируется "
        "после оплаты картой. Номер помечен обработанным; вкладка оставлена открытой.\n",
        flush=True,
    )
    worker["stopped"] = True
    return rec


def settle_success_1591r24(base_dir, worker):
    """Called where the code used to declare success because no contract controls remained.

    With positive evidence the success is final (finalize_success). Without it the tab is
    held in SUCCESS_ASSIST for UNVERIFIED_HOLD_SECONDS (DeepSeek inspects, the button may
    reappear and be signed again), then the row is recorded as UNVERIFIED.
    """
    page = worker.get("page")
    payment_text = _payment_page_1591r26(page) if page is not None else ""  # PAYMENT_STEP_1591R26
    if payment_text:
        _finish_payment_required_1591r26(base_dir, worker, payment_text)
        return False
    evidence = _signed_evidence_1591r24(page) if page is not None else ""
    if evidence:
        worker["success_evidence"] = evidence
        finalize_success(base_dir, worker)
        return True
    now = monotonic()
    since = worker.get("success_unverified_since")
    url = ""
    try:
        url = str(page.url or "") if page is not None else ""
    except Exception:
        pass
    if since is None:
        worker["success_unverified_since"] = now
        try:
            capture_blackbox(worker, "success_unverified")
        except Exception:
            pass
        worker["phase"] = "SUCCESS_ASSIST"
        set_tab_status(
            worker, "⚠️",
            "Кнопка «Подписать договор» пропала, но признаков подписанного договора нет. "
            f"Держу вкладку {UNVERIFIED_HOLD_SECONDS // 60} мин, DeepSeek проверяет.",
        )
        external_heartbeat(worker, "success_unverified_hold")
        queue_success_assist(
            worker,
            "кнопка «Подписать договор» исчезла, но страница не похожа на подписанный договор: "
            f"проверь, подписан ли он, и что показано вместо кнопки (URL: {url})",
            force=True,
        )
        return False
    if now - since < UNVERIFIED_HOLD_SECONDS:
        worker["phase"] = "SUCCESS_ASSIST"
        return False
    _finish_unverified_1591r24(
        base_dir, worker,
        f"после «Подписать договор» страница {UNVERIFIED_HOLD_SECONDS // 60} мин не показала признаков подписания (URL: {url or '—'})",
    )
    return False


def tick_sign_wait(base_dir, worker):
    page = worker["page"]
    now = monotonic()
    worker["success_guard"] = True

    if page.is_closed():
        worker["phase"] = "SUCCESS_STOP"
        worker["stopped"] = True
        set_tab_status(
            worker, "🔴",
            "Успешная вкладка закрыта извне после подписи. Автоповтор запрещён."
        )
        return

    try:
        capture_contract_details(page, worker)
    except Exception:
        pass

    if _post_auth_error_page(page):
        worker["phase"] = "SUCCESS_ASSIST"
        set_tab_status(
            worker, "🧠",
            "После подписи сайт показал ошибку — DeepSeek анализирует. Страницу не трогаю."
        )
        external_heartbeat(worker, "success_sign_error")
        queue_success_assist(worker, "ошибка после попытки подписи")
        return

    button = _signature_button_locator(page)
    current_url = ""
    try:
        current_url = page.url
    except Exception:
        pass

    if button is None or (
        current_url and current_url != worker.get("sign_submit_url")
    ):
        gone_since = worker.get("sign_button_gone_since")
        if gone_since is None:
            worker["sign_button_gone_since"] = now
            return
        if now - gone_since >= 1.2:
            settle_success_1591r24(base_dir, worker)  # SIGNED_EVIDENCE_1591R24
        return

    worker["sign_button_gone_since"] = None

    # NO sign_submit_deadline. A successful post-auth page is never timed out,
    # restarted, reloaded or closed. Ask DeepSeek to inspect if it stays here.
    worker["phase"] = "SUCCESS_ASSIST"
    set_tab_status(
        worker, "🧠",
        "Подтверждение успешно. Подпись ещё не завершилась — DeepSeek наблюдает и помогает."
    )
    external_heartbeat(worker, "success_signature_still_pending")
    queue_success_assist(worker, "подпись остаётся на странице; проверь ошибки/обязательные поля")



def tick_confirmation(base_dir, worker):
    page = worker["page"]
    now = monotonic()

    if page.is_closed():
        print(
            f"[Вкладка {worker['id']}] Рабочая вкладка неожиданно закрыта — "
            "повторяю эту же строку.",
            flush=True,
        )
        restart_same_row_in_new_page(worker)
        return

    if not _is_auth_url(page.url):
        if _post_auth_error_page(page):
            capture_blackbox(worker, "registration_error_after_auth")
            print(
                f"[Вкладка {worker['id']}] После auth открылась /registration/error. "
                "Это НЕ success. Сначала DeepSeek анализирует страницу; "
                "никакого автоматического retry/restart.",
                flush=True,
            )
            enter_error_guard(
                worker,
                "после mobile-id-auth открылась /registration/error",
            )
            return

        # personal-data-form / contract page means the user confirmation itself
        # succeeded. From this exact point destructive recovery is forbidden.
        if _post_auth_contract_page(page):
            worker["post_auth_review_started"] = now
            enter_success_guard(
                worker,
                "mobile-id подтверждение прошло; открыта страница персональных данных/договора",
            )
            return

        # Unknown non-auth transition: inspect without declaring success.
        worker["phase"] = "POST_AUTH_REVIEW"
        worker["post_auth_review_started"] = now
        set_tab_status(worker, "🔎", "Вышли из auth — проверяю новую страницу")
        external_heartbeat(worker, "post_auth_review_unknown")
        return

    if now < worker["confirm_deadline"]:
        return

    if worker["confirm_attempt"] >= 6:
        capture_blackbox(worker, "confirm_cycle_complete")
        worker["completed_confirm_cycle"] = True
        external_heartbeat(worker, "confirm_cycle_complete")
        set_tab_status(worker, "🟠", "6 попыток завершены — беру следующую строку")
        finish_worker_row(base_dir, worker, "CONFIRM_TIMEOUT")
        return

    worker["phase"] = "RESEND"
    worker["resend_deadline"] = now + 15
    print(
        f"[Вкладка {worker['id']}] 65 секунд истекли, подтверждение не пришло — "
        "ищу «Отправить снова».",
        flush=True,
    )


def tick_resend(base_dir, worker):
    page = worker["page"]
    now = monotonic()

    if page.is_closed():
        print(
            f"[Вкладка {worker['id']}] Рабочая вкладка неожиданно закрыта — "
            "повторяю эту же строку.",
            flush=True,
        )
        restart_same_row_in_new_page(worker)
        return

    if not _is_auth_url(page.url):
        if _post_auth_error_page(page):
            capture_blackbox(worker, "registration_error_after_auth")
            print(
                f"[Вкладка {worker['id']}] После auth открылась /registration/error. "
                "Это НЕ success. Сначала DeepSeek анализирует страницу; "
                "никакого автоматического retry/restart.",
                flush=True,
            )
            enter_error_guard(
                worker,
                "после mobile-id-auth открылась /registration/error",
            )
            return

        # personal-data-form / contract page means the user confirmation itself
        # succeeded. From this exact point destructive recovery is forbidden.
        if _post_auth_contract_page(page):
            worker["post_auth_review_started"] = now
            enter_success_guard(
                worker,
                "mobile-id подтверждение прошло; открыта страница персональных данных/договора",
            )
            return

        # Unknown non-auth transition: inspect without declaring success.
        worker["phase"] = "POST_AUTH_REVIEW"
        worker["post_auth_review_started"] = now
        set_tab_status(worker, "🔎", "Вышли из auth — проверяю новую страницу")
        external_heartbeat(worker, "post_auth_review_unknown")
        return

    clicked = try_click_resend_once(page, worker["id"])
    if clicked or now >= worker["resend_deadline"]:
        if not clicked:
            print(
                f"[Вкладка {worker['id']}] За 15 секунд кнопка повторной отправки "
                "не нажалась; начинаю следующий контролируемый интервал.",
                flush=True,
            )
        worker["confirm_attempt"] += 1
        worker["confirm_deadline"] = monotonic() + 65
        worker["phase"] = "CONFIRM"
        external_heartbeat(worker, f"confirm_attempt_{worker['confirm_attempt']}")
        set_tab_status(worker, "🟡", f"Ожидаю подтверждение: попытка {worker['confirm_attempt']}/6")
        print(
            f"[Вкладка {worker['id']}] Попытка "
            f"{worker['confirm_attempt']}/6: новый таймер 65 секунд.",
            flush=True,
        )




def worker_generation_alive(worker, generation=None):
    if worker.get("cancelling"):
        return False
    if generation is not None and generation != worker.get("generation"):
        return False
    page=worker.get("page")
    try:
        return page is not None and not page.is_closed()
    except Exception:
        return False

def begin_worker_cancel(worker, reason):
    """Invalidate all delayed work from the old page before closing it."""
    if _io1591.guarded(worker or {}):
        return False
    if worker.get("cancelling"):
        return False
    worker["cancelling"]=True
    worker["generation"]=int(worker.get("generation",1))+1
    worker["phase"]="CANCELLING"
    set_tab_status(worker,"♻️",f"CANCELLING\\n{reason}")
    external_heartbeat(worker,"cancelling")
    return True

def restart_same_row_in_new_page(worker):
    """Close old working page completely before creating generation+1 page."""
    if _io1591.guarded(worker or {}):
        return False
    old_page=worker.get("page")
    row=worker.get("row")
    begin_worker_cancel(worker,"same-row recovery")
    if old_page is not None:
        try:
            if not old_page.is_closed():
                old_page.close(run_before_unload=False)
        except Exception:
            pass
        deadline=monotonic()+5
        while monotonic()<deadline:
            try:
                if old_page.is_closed(): break
            except Exception:
                break
            time.sleep(.1)

    context=worker.get("context")
    if context is None:
        worker["stopped"]=True
        return
    new_page=context.new_page()
    new_page.set_default_timeout(8000)
    worker["generation"] = int(worker.get("generation") or 1) + 1
    try:
        new_page.evaluate(
            f"() => window.name = '{_worker_window_name(worker['id'], worker['generation'])}'"
        )
    except Exception:
        pass
    worker["page"]=new_page
    worker["cancelling"]=False
    worker["form_ready"]=False
    worker["stopped"]=False
    worker["phase"]="RESTART_ROW_READY"
    worker["last_progress_at"]=monotonic()
    install_page_activity_tracker(new_page,worker)
    setattr(new_page,"_worker_heartbeat",worker.get("heartbeat"))
    set_tab_status(worker,"♻️","Старая вкладка закрыта. Повторяю ту же строку.")
    external_heartbeat(worker,"restart_row_ready")
    # Do NOT call start_row_in_worker() recursively here.
    # _tab_process owns the row loop and will restart the SAME row exactly once.

def tick_restart_close_retry(worker):
    """Повторно закрывает старую зависшую вкладку; не плодит новые."""
    if _io1591.guarded(worker or {}):
        return False
    page = worker["page"]
    if page.is_closed():
        restart_same_row_in_new_page(worker)
        return
    if monotonic() < worker.get("restart_close_deadline", 0):
        return
    try:
        page.close(run_before_unload=False)
    except Exception:
        worker["restart_close_deadline"] = monotonic() + 3
        return
    restart_same_row_in_new_page(worker)


WATCHDOG_SECONDS = 90
EXTERNAL_WATCHDOG_SECONDS = DEFAULT_EXTERNAL_STALL_SECONDS


def publish_worker_phase(worker, phase, note="", matcher_stage=None):
    """Atomically publish the worker state everywhere observers/watchdogs read it."""
    worker["phase"] = phase
    if matcher_stage is not None:
        worker["matcher_stage"] = matcher_stage
    mark_worker_progress(worker, matcher_stage or phase)

    hb = worker.get("heartbeat")
    if hb is not None:
        try:
            now = monotonic()
            old = dict(hb.get(str(worker["id"])) or {})
            old.update({
                "time": now,
                "label": matcher_stage or phase,
                "phase": phase,
                "matcher_stage": matcher_stage,
                "matcher_time": now if phase == "PROTECTED_CHECK" else old.get("matcher_time"),
                "activity_time": worker.get("last_page_activity_at"),
                "activity_kind": worker.get("last_page_activity_kind"),
                "row": list(worker.get("row")) if isinstance(worker.get("row"), (tuple, list)) else worker.get("row"),
                "confirm_attempt": worker.get("confirm_attempt", 0),
                "completed_confirm_cycle": worker.get("completed_confirm_cycle", False),
                "success_guard": bool(worker.get("success_guard")),
                "error_guard": bool(worker.get("error_guard")),
                "page_url": (
                    worker.get("page").url
                    if worker.get("page") and not worker.get("page").is_closed()
                    else ""
                ),
                "window_name": _read_page_window_name(worker.get("page")),
                "generation": int(worker.get("generation") or 1),
                "worker_pid": os.getpid(),
            })
            hb[str(worker["id"])] = old
        except Exception:
            pass

    if phase == "PROTECTED_CHECK":
        detail = f"PROTECTED_CHECK"
        if matcher_stage:
            detail += f"\nMatcher: {matcher_stage}"
        if note:
            detail += f"\n{note}"
        set_tab_status(worker, "🛡️", detail)
    else:
        set_tab_status(worker, "🟢", note or phase)


def external_heartbeat(worker, label):
    """Heartbeat visible to the parent process even between normal phase changes."""
    mark_worker_progress(worker, label)
    hb = worker.get("heartbeat")
    if hb is not None:
        try:
            hb[str(worker["id"])] = {
                "time": monotonic(),
                "label": label,
                "phase": worker.get("phase"),
                "success_guard": bool(worker.get("success_guard")),
                "error_guard": bool(worker.get("error_guard")),
                "matcher_time": (hb.get(str(worker["id"])) or {}).get("matcher_time"),
                "matcher_stage": worker.get("matcher_stage"),
                "activity_time": worker.get("last_page_activity_at"),
                "activity_kind": worker.get("last_page_activity_kind"),
                "row": list(worker.get("row")) if isinstance(worker.get("row"), (tuple, list)) else worker.get("row"),
                "confirm_attempt": worker.get("confirm_attempt", 0),
                "completed_confirm_cycle": worker.get("completed_confirm_cycle", False),
                "page_url": (worker.get("page").url if worker.get("page") and not worker.get("page").is_closed() else ""),
                "window_name": _read_page_window_name(worker.get("page")),
                "generation": int(worker.get("generation") or 1),
                "worker_pid": os.getpid(),
            }
        except Exception:
            pass



def mark_worker_progress(worker, label):
    worker["last_progress_at"] = monotonic()
    worker["last_progress_label"] = label


def watchdog_should_restart(worker):
    # 15.21: только родительский watchdog может убивать/перезапускать воркер.
    # Так исключаем двойные и каскадные recovery.
    return False


def watchdog_restart(worker):
    elapsed = monotonic() - worker.get("last_progress_at", monotonic())
    capture_blackbox(worker, "watchdog_stall")
    worker["watchdog_restarts"] = worker.get("watchdog_restarts", 0) + 1
    print(
        f"[Вкладка {worker['id']}] WATCHDOG: {elapsed:.0f} сек. без прогресса "
        f"(этап: {worker.get('last_progress_label', worker.get('phase'))}). "
        "Открываю новую вкладку с той же строкой.",
        flush=True,
    )
    try:
        worker["diagnostic"].write(
            "watchdog_stall",
            elapsed_seconds=round(elapsed, 1),
            phase=worker.get("phase"),
            label=worker.get("last_progress_label"),
            restart=worker["watchdog_restarts"],
        )
        worker["diagnostic"].snapshot("watchdog_stall")
    except Exception:
        pass
    restart_same_row_in_new_page(worker)
    external_heartbeat(worker, "watchdog_restart")



def tick_worker(base_dir, worker):
    if worker["phase"] == "POST_CONTINUE":
        tick_post_continue(base_dir, worker)
    elif worker["phase"] == "AUTH_WAIT":
        tick_auth_wait(base_dir, worker)
    elif worker["phase"] == "CONFIRM":
        tick_confirmation(base_dir, worker)
    elif worker["phase"] == "RESEND":
        tick_resend(base_dir, worker)
    elif worker["phase"] == "POST_AUTH_REVIEW":
        tick_post_auth_review(base_dir, worker)
    elif worker["phase"] == "SIGN_WAIT":
        tick_sign_wait(base_dir, worker)
    elif worker["phase"] == "SUCCESS_ASSIST":
        tick_success_assist(base_dir, worker)
    elif worker["phase"] == "ERROR_ASSIST":
        tick_error_assist(base_dir, worker)
    elif worker["phase"] == "RESTART_ROW":
        if not worker.get("restart_in_progress"):
            worker["restart_in_progress"] = True
            restart_same_row_in_new_page(worker)
    elif worker["phase"] == "RESTART_CLOSE_RETRY":
        tick_restart_close_retry(worker)


def _free_local_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _wait_cdp(port, timeout=25):
    deadline = monotonic() + timeout
    url = f"http://127.0.0.1:{port}/json/version"
    while monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1) as response:
                if response.status == 200:
                    return True
        except Exception:
            time.sleep(0.2)
    return False


# BROWSER_HANG_1591R18: a Chromium whose CDP socket accepts the connection but never
# answers (connect_over_cdp timeout) blocks every tab of that browser. The watchdog can
# only replace tabs, so after BROWSER_HANG_RESTART_SECONDS of continuous refusals the
# whole browser process is replaced on the same port and its workers are respawned.
BROWSER_HANG_RESTART_SECONDS = 120
_CDP_UNREACHABLE_SINCE = {}


def _note_cdp_result(cdp_url, exc, now=None):
    """Remember since when `cdp_url` refuses CDP commands; `exc=None` means it answered."""
    key = str(cdp_url)
    if exc is None:
        _CDP_UNREACHABLE_SINCE.pop(key, None)
        return
    text = f"{type(exc).__name__}: {exc}"
    if "connect_over_cdp" in text and "Timeout" in text:
        _CDP_UNREACHABLE_SINCE.setdefault(key, now if now is not None else monotonic())


def cdp_unreachable_seconds(cdp_url, now=None):
    since = _CDP_UNREACHABLE_SINCE.get(str(cdp_url))
    if since is None:
        return 0.0
    return (now if now is not None else monotonic()) - since


def _chromium_launch_args(chromium_exe, port, profile):
    """Same flags as args_i in main() (test_update checks that literal list stays there)."""
    return [
        chromium_exe,
        f"--remote-debugging-port={port}",
        f"--user-data-dir={profile}",
        "--no-sandbox",
        "--disable-setuid-sandbox",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-popup-blocking",
        "about:blank",
    ]


def _terminate_chromium(instance):
    proc = instance.get("proc")
    try:
        if proc is not None and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
    except Exception:
        pass
    if instance.get("profile"):
        shutil.rmtree(str(instance["profile"]), ignore_errors=True)


def _relaunch_chromium(instance, chromium_exe, popen=None, wait_cdp=None, free_port=None):
    """Start a fresh Chromium for `instance`: the old port first (cdp_url stays valid for
    the observers), a free port as the fallback. Returns False when neither came up."""
    popen = popen or subprocess.Popen
    wait_cdp = wait_cdp or _wait_cdp
    free_port = free_port or _free_local_port
    for attempt in range(2):
        port = instance["port"] if attempt == 0 else free_port()
        profile = tempfile.mkdtemp(prefix=f"esim_pw_browser{instance['id']}_")
        instance["proc"] = popen(_chromium_launch_args(chromium_exe, port, profile))
        instance["profile"] = profile
        if wait_cdp(port):
            _CDP_UNREACHABLE_SINCE.pop(str(instance.get("cdp_url")), None)
            instance["port"] = port
            instance["cdp_url"] = f"http://127.0.0.1:{port}"
            _CDP_UNREACHABLE_SINCE.pop(instance["cdp_url"], None)
            return True
        _terminate_chromium(instance)
    return False



def _close_cdp_page_for_worker(cdp_url, info, timeout=20, attempts=2):
    """OVERLAY_DISMISS_1591R6: a Chromium busy with orphan pages needs more than 8 s;
    one real close attempt is retried once. Refusals (guard, no window_name) are final.
    The caller already refuses to create a replacement while the old page is open."""
    def _once(cdp_url, info, timeout=20):
        """Close only the exact physical worker page from heartbeat identity."""
        if _io1591.guarded(info or {}):
            return False
        expected_name = str((info or {}).get("window_name") or "").strip()
        if not expected_name:
            print(
                "[WATCHDOG] У worker нет точного window_name — чужие вкладки не закрываю.",
                flush=True,
            )
            return False

        try:
            with sync_playwright() as p:
                browser = p.chromium.connect_over_cdp(
                    cdp_url, timeout=int(timeout * 1000)
                )
                _note_cdp_result(cdp_url, None)  # BROWSER_HANG_1591R18: the browser answered
                for context in browser.contexts:
                    for page in context.pages:
                        try:
                            name = str(page.evaluate("() => window.name || ''"))
                        except Exception:
                            continue
                        if name != expected_name:
                            continue
                        page.close(run_before_unload=False)
                        print(
                            f"[WATCHDOG] Закрыта точная worker-вкладка {expected_name}.",
                            flush=True,
                        )
                        return True

            # Page already absent is safe: there is nothing left to close.
            print(
                f"[WATCHDOG] {expected_name} уже отсутствует. Чужие вкладки не трогаю.",
                flush=True,
            )
            return True
        except Exception as exc:
            _note_cdp_result(cdp_url, exc)  # BROWSER_HANG_1591R18
            print(
                f"[WATCHDOG] Не удалось закрыть {expected_name}: "
                f"{type(exc).__name__}: {exc}",
                flush=True,
            )
            return False

    if _io1591.guarded(info or {}) or not str((info or {}).get("window_name") or "").strip():
        return _once(cdp_url, info, timeout=timeout)
    import time as _time
    for attempt in range(1, attempts + 1):
        try:
            if _once(cdp_url, info, timeout=timeout):
                return True
        except Exception:
            pass
        if attempt < attempts:
            _time.sleep(2)
    return False



def _worker_page_exists(cdp_url, info, timeout=5):
    expected_name = str((info or {}).get("window_name") or "").strip()
    if not expected_name:
        return False
    try:
        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp(
                cdp_url, timeout=int(timeout * 1000)
            )
            for context in browser.contexts:
                for page in context.pages:
                    try:
                        if str(page.evaluate("() => window.name || ''")) == expected_name:
                            return True
                    except Exception:
                        continue
    except Exception:
        return True  # on inspection failure, do NOT authorize destructive recovery
    return False



def _tab_process(tab_id, cdp_url, rows, base_dir_text, launch_ready_event, heartbeat=None, status_map=None, initial_row=None, total_rows=None, diagnostic_session_dir=None, success_queue=None, captcha_gate=None):  # TWO_BROWSERS_1591R28
    """One independent worker process for one managed browser slot."""
    base_dir = Path(base_dir_text)
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(cdp_url)
        if not browser.contexts:
            raise RuntimeError("Chromium не вернул общий контекст через CDP.")

        context = browser.contexts[0]
        page = context.new_page()
        page.set_default_timeout(8000)
        try:
            page.evaluate(
                f"() => window.name = '{_worker_window_name(tab_id, 1)}'"
            )
        except Exception:
            pass

        worker = make_worker(
            tab_id, page, heartbeat=heartbeat, status_map=status_map
        )
        browser_version = browser.version

        worker["generation"] = 1
        worker["total_rows"] = total_rows
        worker["diagnostic_session_dir"] = diagnostic_session_dir
        worker["success_queue"] = success_queue
        worker["launch_ready_event"] = launch_ready_event
        worker["context"] = context
        worker["base_dir"] = base_dir
        worker["browser_version"] = browser_version

        install_page_activity_tracker(page, worker)
        configure_matcher_runtime(tab_id=tab_id, heartbeat=heartbeat)
        global _CAPTCHA_GATE
        _CAPTCHA_GATE = captcha_gate  # TWO_BROWSERS_1591R28

        tickable_phases = {
            "POST_CONTINUE",
            "AUTH_WAIT",
            "CONFIRM",
            "RESEND",
            "POST_AUTH_REVIEW",
            "SIGN_WAIT",
            "SUCCESS_ASSIST",
            "ERROR_ASSIST",
            "RESTART_ROW",
            "RESTART_CLOSE_RETRY",
        }

        print(f"[Вкладка {tab_id}] Воркер запущен.", flush=True)
        pending_initial_row = initial_row

        while not worker["stopped"]:
            if pending_initial_row is not None:
                row = pending_initial_row
                pending_initial_row = None
            else:
                if restart_drain_requested(base_dir):  # SCHEDULED_RESTART_1591R13
                    # The current row was finished to the end above; do not take a new one.
                    worker["phase"] = "RESTART_WAIT"
                    external_heartbeat(worker, "restart_wait")
                    set_tab_status(worker, "♻️", "Строка завершена; жду плановый перезапуск")
                    print(f"[Вкладка {tab_id}] Плановый перезапуск: строка завершена, новую не беру.", flush=True)
                    break
                try:
                    row = rows.get_nowait()
                except Exception:
                    worker["phase"] = "DONE"
                    external_heartbeat(worker, "queue_done")
                    set_tab_status(worker, "⚪", "Очередь завершена")
                    break

            # This inner loop owns THIS row until it reaches a final state.
            # A same-row recovery never consumes a new item from the shared queue.
            while not worker["stopped"]:
                start_row_in_worker(base_dir, browser_version, worker, row)

                while (
                    worker["phase"] in tickable_phases
                    and not worker["stopped"]
                ):
                    tick_worker(base_dir, worker)
                    page = worker["page"]
                    if not page.is_closed():
                        page.wait_for_timeout(100)

                if worker["stopped"]:
                    break

                if worker["phase"] == "RESTART_ROW_READY":
                    if _row_restart_exhausted_1591r32(worker, row, rows):  # ROW_RESTART_LIMIT_1591R32
                        break
                    print(
                        f"[Вкладка {tab_id}] Новая physical-вкладка готова. "
                        "Повторяю ту же строку с начала.",
                        flush=True,
                    )
                    continue

                # INVALID_ROW / completed confirmation cycle returns the slot to IDLE
                # and only then may it consume a new shared-queue row.
                if worker["phase"] == "IDLE":
                    break

                if worker["phase"] in {"STOPPED", "DONE", "SUCCESS_STOP"}:
                    break

                # Unexpected non-tickable state: keep the row, don't silently
                # consume the next one.
                capture_blackbox(worker, "unexpected_worker_phase")
                print(
                    f"[Вкладка {tab_id}] Неожиданный этап "
                    f"{worker.get('phase')!r}; повторяю ту же строку.",
                    flush=True,
                )
                restart_same_row_in_new_page(worker)
                if worker["phase"] != "RESTART_ROW_READY":
                    break

            if worker["phase"] == "IDLE" and not worker["stopped"]:
                continue
            if worker["phase"] in {"STOPPED", "DONE", "SUCCESS_STOP"}:
                break

        print(f"[Вкладка {tab_id}] Воркер завершил очередь.", flush=True)
        # browser.close() intentionally not called: Chromium is shared.



# MATCHER_HEARTBEAT_1591R9
MATCHER_CPU_MIN_RATIO = 0.05  # share of one CPU below which the matcher is not computing
_MATCHER_CPU_STATE = {}


def _process_tree_cpu_seconds(pid):
    """CPU time of a process plus its live children (a native solver may be a child)."""
    try:
        ticks = os.sysconf("SC_CLK_TCK")
    except (AttributeError, ValueError, OSError):
        ticks = 100
    total = 0.0
    try:
        entries = os.listdir("/proc")
    except OSError:
        return None
    for entry in entries:
        if not entry.isdigit():
            continue
        try:
            with open(f"/proc/{entry}/stat", "r") as f:
                fields = f.read().rsplit(")", 1)[1].split()
            if int(entry) == int(pid) or int(fields[1]) == int(pid):
                total += (int(fields[11]) + int(fields[12])) / ticks
        except (OSError, IndexError, ValueError):
            continue
    return total


def _matcher_cpu_age(proc, now):
    """Seconds since the worker process (or its child solver) was last seen computing.

    Sampled by the parent between watchdog runs. A matcher busy with SHAPE/MATCH work
    keeps this near zero without any stage report; a matcher blocked on the page, a lock
    or the network burns no CPU, so this grows and the 75-second rule applies as before.
    """
    pid = getattr(proc, "pid", None)
    if not pid:
        return float("inf")
    cpu = _process_tree_cpu_seconds(pid)
    if cpu is None:
        return float("inf")
    state = _MATCHER_CPU_STATE.get(pid)
    if state is None:
        _MATCHER_CPU_STATE[pid] = {"cpu": cpu, "time": now, "progress_at": now}
        return 0.0
    wall = now - state["time"]
    if wall > 0 and (cpu - state["cpu"]) / wall >= MATCHER_CPU_MIN_RATIO:
        state["progress_at"] = now
    state["cpu"], state["time"] = cpu, now
    return now - state["progress_at"]


# SCHEDULED_RESTART_1591R13
RESTART_POLICY_FILE_NAME = "restart_policy.json"
RESTART_DRAIN_FILE_NAME = "restart_drain.json"
RESTART_EXIT_CODE = 75
_RESTART_SETTING_RE = re.compile(r"^(\d+)\s*(m|min|мин|h|ч|hour|час)?$")


def parse_restart_setting(text):
    """'off' -> 0, '20m'/'20' -> 20, '1h' -> 60, otherwise None (1 minute .. 24 hours)."""
    low = str(text or "").strip().lower()
    if low in {"off", "выкл", "0", "stop", "none"}:
        return 0
    match = _RESTART_SETTING_RE.match(low)
    if not match:
        return None
    value = int(match.group(1))
    minutes = value * 60 if (match.group(2) or "m") in {"h", "ч", "hour", "час"} else value
    return minutes if 1 <= minutes <= 24 * 60 else None


def restart_policy_minutes(base_dir):
    try:
        data = json.loads((Path(base_dir) / RESTART_POLICY_FILE_NAME).read_text(encoding="utf-8"))
        return max(0, int(data.get("interval_minutes") or 0))
    except Exception:
        return 0


def write_restart_policy(base_dir, minutes):
    path = Path(base_dir) / RESTART_POLICY_FILE_NAME
    path.write_text(json.dumps({"interval_minutes": int(minutes), "updated_at": time.time()},
                               ensure_ascii=False, indent=2), encoding="utf-8")


def restart_drain_requested(base_dir):
    return (Path(base_dir) / RESTART_DRAIN_FILE_NAME).is_file()


def request_restart_drain(base_dir, reason=""):
    path = Path(base_dir) / RESTART_DRAIN_FILE_NAME
    if not path.is_file():
        path.write_text(json.dumps({"requested_at": time.time(), "reason": str(reason)}, ensure_ascii=False),
                        encoding="utf-8")


def clear_restart_drain(base_dir):
    try:
        (Path(base_dir) / RESTART_DRAIN_FILE_NAME).unlink()
    except FileNotFoundError:
        pass


# RESTART_RELAUNCH_1591R21
RESTART_RELAUNCH_FILE_NAME = "restart_relaunch.json"
RESTART_EXIT_FORCE_SECONDS = 90


def request_relaunch(base_dir, reason=""):
    """Ask the controller to start the automation again after this process exits.

    xvfb-run does not always pass RESTART_EXIT_CODE through, so the controller also looks at
    this marker. The timer forces the exit if the normal shutdown hangs on a child process.
    """
    try:
        (Path(base_dir) / RESTART_RELAUNCH_FILE_NAME).write_text(
            json.dumps({"time": time.time(), "reason": str(reason)}, ensure_ascii=False), "utf-8"
        )
    except Exception as exc:
        print(f"[RESTART] Маркер перезапуска не записан: {type(exc).__name__}: {exc}", flush=True)
    import threading
    timer = threading.Timer(RESTART_EXIT_FORCE_SECONDS, lambda: os._exit(RESTART_EXIT_CODE))
    timer.daemon = True
    timer.start()
    return timer


def _restart_notify(text):
    """Durable Telegram notice; delivered by the controller's sender even across the restart."""
    try:
        chat = str(load_telegram_config().get("chat_id") or "").strip()
        if chat:
            _io1591.enqueue_notice(globals(), chat, str(text))
    except Exception as exc:
        print(f"[RESTART] Уведомление не поставлено в очередь: {type(exc).__name__}: {exc}", flush=True)


def parent_watchdog(processes, heartbeat):
    """Parent recovery is phase-aware and must never kill normal ROW_START work."""
    now = monotonic()
    stalled = []

    # These phases either have their own timers/recovery or are already in recovery.
    skip_phases = {
        "IDLE",
        "CONFIRM",
        "RESEND",
        "SUCCESS_STOP",
        "POST_AUTH_REVIEW",
        "SIGN_WAIT",
        "SUCCESS_ASSIST",
        "ERROR_ASSIST",
        "DONE",
        "CANCELLING",
        "RESTART_ROW",
        "RESTART_CLOSE_RETRY",
        "RESTART_ROW_READY",
    }

    for tab_id, proc in list(processes.items()):
        if not proc.is_alive():
            continue

        info = heartbeat.get(str(tab_id))
        if not info:
            continue

        phase = str(info.get("phase") or "")
        if _io1591.guarded(info) or phase in skip_phases:
            continue

        logical_age = now - float(info.get("time") or now)

        # The protected matcher has its own heartbeat and its own timeout.
        if phase == "PROTECTED_CHECK":
            matcher_age = now - float(
                info.get("matcher_time")
                or info.get("time")
                or now
            )
            # MATCHER_HEARTBEAT_1591R9: a matcher still computing (the worker process or
            # its child solver keeps consuming CPU) is alive between stage reports; a
            # blocked or hung matcher burns no CPU and is caught by the same 75 s rule.
            matcher_age = min(matcher_age, _matcher_cpu_age(proc, now))
            if matcher_age >= PROTECTED_MATCHER_STALL_SECONDS:
                stalled.append((tab_id, proc, info, matcher_age))
            continue

        # ROW_START contains real page loading, masked-input interaction,
        # tariff/eSIM transitions and can legitimately take tens of seconds.
        # The old 18-second parent watchdog was closing healthy pages mid-action.
        if phase == "ROW_START":
            # ROW_START_ACTIVITY_1591R8: real page activity (requests, navigation) is
            # progress too; only a row that is silent on BOTH clocks is stalled.
            activity_age = now - float(info.get("activity_time") or info.get("time") or now)
            if min(logical_age, activity_age) >= ROW_START_STALL_SECONDS:
                stalled.append((tab_id, proc, info, min(logical_age, activity_age)))
            continue

        # Other blocking phases still get a watchdog, but not the destructive
        # 18-second timeout.
        if logical_age >= DEFAULT_EXTERNAL_STALL_SECONDS:
            stalled.append((tab_id, proc, info, logical_age))

    return stalled


PROGRESS_FILE_NAME = "processed_numbers.txt"


def _row_number_value(row):
    """Возвращает номер клиента из поддерживаемых форматов строки."""
    _, active, _ = row_parts(row)
    return "".join(c for c in str(active) if c.isdigit())


# ROW_RESTART_LIMIT_1591R32 (parent side)
ROW_RESPAWN_MAX = 3            # replacements of a worker with the same row per launch
_ROW_RESPAWNS_1591R32 = {}


def _row_for_respawn_1591r32(saved_row, tab_id, base_dir, why):
    """The row a replacement worker starts with: the same row up to ROW_RESPAWN_MAX times per
    launch (DEAD RECOVERY and the watchdog together), then None: the row stays unprocessed for
    the next launch and the new worker takes the next one. Without this a row that always
    hangs the tab (CANCELLING -> watchdog -> same row) looped forever."""
    if saved_row is None:
        return None
    try:
        key = _row_number_value(saved_row)
    except Exception:
        key = str(saved_row)
    count = _ROW_RESPAWNS_1591R32.get(key, 0) + 1
    _ROW_RESPAWNS_1591R32[key] = count
    if count <= ROW_RESPAWN_MAX:
        return saved_row
    line_number, active_digits, _ = row_parts(saved_row)
    print(
        f"[Вкладка {tab_id}] Строка {line_number}: worker заменялся с этой строкой уже {count - 1} раз "
        f"({why}); оставляю её до следующего запуска (номер не помечен обработанным), "
        "новый worker берёт следующую.",
        flush=True,
    )
    try:
        with open(Path(base_dir) / DEFERRED_ROWS_FILE_NAME, "a", encoding="utf-8") as handle:
            handle.write(json.dumps({"time": time.strftime("%Y-%m-%d %H:%M:%S"), "tab": tab_id,
                                     "row": line_number, "number": active_digits,
                                     "respawns": count - 1, "requeued": False, "why": why},
                                    ensure_ascii=False) + "\n")
    except Exception:
        pass
    return None


# DRAIN_DEADLINE_1591R32
DRAIN_SOFT_MAX_SECONDS = 15 * 60   # then workers still at the start of a row are stopped
DRAIN_HARD_MAX_SECONDS = 40 * 60   # then every remaining worker is stopped
DRAIN_PROTECTED_PHASES = {
    "POST_CONTINUE", "AUTH_WAIT", "CONFIRM", "RESEND", "PROTECTED_CHECK",
    "POST_AUTH_REVIEW", "SIGN_WAIT", "SUCCESS_ASSIST", "ERROR_ASSIST",
}


def _drain_age_1591r32(base_dir):
    try:
        data = json.loads((Path(base_dir) / RESTART_DRAIN_FILE_NAME).read_text(encoding="utf-8"))
        return max(0.0, time.time() - float(data.get("requested_at") or 0.0))
    except Exception:
        return 0.0


def _drain_deadline_1591r32(base_dir, processes, heartbeat):
    """A drain must end. After DRAIN_SOFT_MAX_SECONDS a worker that is still at the start of
    a row (tariff, eSIM, form: nothing sent to the subscriber yet) is stopped; its row is not
    marked processed and is taken again at the next launch. Confirmation, signing and DeepSeek
    review are waited for until DRAIN_HARD_MAX_SECONDS. Returns the stopped tab ids."""
    age = _drain_age_1591r32(base_dir)
    if age < DRAIN_SOFT_MAX_SECONDS:
        return []
    stopped = []
    for tab_id, proc in list(processes.items()):
        if proc is None or not proc.is_alive():
            continue
        info = dict(heartbeat.get(str(tab_id)) or {})
        phase = str(info.get("phase") or "")
        protected = (phase in DRAIN_PROTECTED_PHASES or bool(info.get("success_guard"))
                     or bool(info.get("error_guard")))
        if protected and age < DRAIN_HARD_MAX_SECONDS:
            continue
        line_number = row_parts(info.get("row"))[0] if info.get("row") is not None else "?"
        print(
            f"[RESTART] Дренаж идёт {int(age // 60)} мин: вкладка {tab_id} на этапе {phase or 'unknown'} "
            f"(строка {line_number}) остановлена; номер не помечен обработанным и вернётся в очередь "
            "при новом запуске.",
            flush=True,
        )
        try:
            proc.terminate()
            proc.join(timeout=5)
        except Exception:
            pass
        info["phase"] = "RESTART_WAIT"   # neither DEAD RECOVERY nor the watchdog replaces it
        try:
            heartbeat[str(tab_id)] = info
        except Exception:
            pass
        stopped.append(tab_id)
    return stopped


def load_processed_numbers(base_dir):
    path = Path(base_dir) / PROGRESS_FILE_NAME
    try:
        return {
            line.strip()
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        }
    except FileNotFoundError:
        return set()
    except Exception as exc:
        print(
            f"[Прогресс] Не удалось прочитать {path.name}: "
            f"{type(exc).__name__}: {exc}",
            flush=True,
        )
        return set()


def remember_processed_number(base_dir, row):
    """Атомарно дописывает номер после окончательной обработки строки."""
    number = _row_number_value(row)
    if not number:
        return
    path = Path(base_dir) / PROGRESS_FILE_NAME
    try:
        existing = load_processed_numbers(base_dir)
        if number in existing:
            return
        with path.open("a", encoding="utf-8") as f:
            f.write(number + "\n")
            f.flush()
            try:
                os.fsync(f.fileno())
            except Exception:
                pass
        print(f"[Прогресс] Номер {number} сохранён как обработанный.", flush=True)
    except Exception as exc:
        print(
            f"[Прогресс] Не удалось сохранить номер {number}: "
            f"{type(exc).__name__}: {exc}",
            flush=True,
        )



def main():
    print("Версия 15.86 EXP-3: authoritative Operator mission")
    base_dir = Path(__file__).resolve().parent
    try:
        RUNTIME_LOG_DIR.mkdir(parents=True, exist_ok=True)
        if RUNTIME_CONSOLE_FILE.exists() and RUNTIME_CONSOLE_FILE.stat().st_size:
            _history1584 = RUNTIME_LOG_DIR / "console.previous.log"
            try:
                shutil.copy2(RUNTIME_CONSOLE_FILE, _history1584)
            except Exception:
                pass
        RUNTIME_CONSOLE_FILE.write_text(
            RUNTIME_SESSION_MARKER_V1584 + "\n",
            encoding="utf-8",
        )
    except Exception:
        pass
    external_tg_controller = (
        str(os.environ.get("TG_EXTERNAL_CONTROLLER", "")).strip() == "1"
    )
    diagnostic_session_dir = create_diagnostic_session()
    print(f"[Диагностика] Текущая сессия: {diagnostic_session_dir}", flush=True)
    manager = Manager()
    heartbeat = manager.dict()
    status_map = manager.dict()
    success_queue = mp.get_context("spawn").Queue()
    tg_stop = mp.get_context("spawn").Event()
    tg_proc = mp.get_context("spawn").Process(
        target=telegram_logger_process,
        args=(status_map, success_queue, tg_stop),
        name="telegram-logger",
    )
    tg_proc.start()
    try:
        clients = load_clients(base_dir / "clients.txt")
    except (OSError, ValueError) as exc:
        print("Не удалось прочитать clients.txt:", exc)
        return

    total_source_rows = len(clients)
    processed_numbers = load_processed_numbers(base_dir)
    if processed_numbers:
        before = len(clients)
        clients = [
            row for row in clients
            if _row_number_value(row) not in processed_numbers
        ]
        skipped = before - len(clients)
        print(
            f"[Прогресс] Уже обработано ранее: {skipped}. "
            f"Осталось новых строк: {len(clients)}.",
            flush=True,
        )
    print(f"Загружено новых записей: {len(clients)} (в исходном файле: {total_source_rows})")
    print(f"Запускаю {BROWSER_COUNT} Chromium и {TAB_COUNT} рабочие вкладки. Общая очередь строк.")  # BROWSER_HANG_1591R18

    # Два полностью независимых Chromium: отдельный процесс, CDP-порт и профиль.
    # Общими остаются только очередь строк, Telegram status_map и persistent progress.
    with sync_playwright() as p:
        chromium_exe = p.chromium.executable_path

    browser_instances = []
    for browser_id in range(1, BROWSER_COUNT + 1):
        port_i = _free_local_port()
        profile_i = tempfile.mkdtemp(prefix=f"esim_pw_browser{browser_id}_")
        args_i = [
            chromium_exe,
            f"--remote-debugging-port={port_i}",
            f"--user-data-dir={profile_i}",
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-popup-blocking",
            "about:blank",
        ]
        proc_i = subprocess.Popen(args_i)
        cdp_i = f"http://127.0.0.1:{port_i}"
        browser_instances.append({
            "id": browser_id,
            "port": port_i,
            "profile": profile_i,
            "proc": proc_i,
            "cdp_url": cdp_i,
        })

    # Backward-compatible names are no longer used for worker routing.
    port = None
    profile_dir = None
    browser_proc = None
    cdp_url = None

    try:
        for instance in browser_instances:
            if not _wait_cdp(instance["port"]):
                raise RuntimeError(
                    f"Chromium #{instance['id']} не открыл CDP-порт за 25 секунд."
                )
            print(
                f"[Запуск] Chromium #{instance['id']} готов: "
                f"{instance['cdp_url']}",
                flush=True,
            )

        _ai_db_init()
        print(f"[AI] Durable queue ready: {AI_TELEGRAM_DB.name}", flush=True)

        ai_stop = mp.get_context("spawn").Event()
        ai_fast_health = manager.dict()
        ai_dev_health = manager.dict()
        ai_receiver_health = manager.dict()
        ai_action_queue = mp.get_context("spawn").Queue()
        ai_action_results = manager.dict()

        ai_receiver_proc = None
        if external_tg_controller:
            print(
                "[AI RX] getUpdates отключён: Telegram принимает внешний controller.",
                flush=True,
            )
        else:
            ai_receiver_proc = mp.get_context("spawn").Process(
                target=ai_telegram_receiver_process,
                args=(ai_stop, ai_receiver_health),
                name="deepseek-telegram-receiver",
            )
            ai_receiver_proc.start()
            print(
                f"[AI RX] Receiver process PID={ai_receiver_proc.pid}",
                flush=True,
            )

        ai_fast_proc = mp.get_context("spawn").Process(
            target=ai_observer_process,
            args=(
                status_map,
                [x["cdp_url"] for x in browser_instances],
                ai_stop,
                ai_fast_health,
                ai_action_queue,
                ai_action_results,
                "fast",
            ),
            name="deepseek-fast-operator",
        )
        ai_fast_proc.start()
        print(f"[AI FAST] Operator PID={ai_fast_proc.pid}", flush=True)

        ai_dev_proc = mp.get_context("spawn").Process(
            target=ai_observer_process,
            args=(
                status_map,
                [x["cdp_url"] for x in browser_instances],
                ai_stop,
                ai_dev_health,
                ai_action_queue,
                ai_action_results,
                "dev",
            ),
            name="deepseek-dev-operator",
        )
        ai_dev_proc.start()
        print(f"[AI DEV] Operator PID={ai_dev_proc.pid}", flush=True)


        def ensure_ai_receiver_alive():
            nonlocal ai_receiver_proc
            if external_tg_controller:
                return
            now = monotonic()
            last = float(ai_receiver_health.get("time", now))
            dead = ai_receiver_proc is None or not ai_receiver_proc.is_alive()
            stale = (now - last) > 45
            if not dead and not stale:
                return

            print(
                f"[AI RX] Receiver {'умер' if dead else 'завис'} — перезапускаю.",
                flush=True,
            )
            if ai_receiver_proc.is_alive():
                ai_receiver_proc.terminate()
                ai_receiver_proc.join(timeout=5)

            ai_receiver_health.clear()
            ai_receiver_proc = mp.get_context("spawn").Process(
                target=ai_telegram_receiver_process,
                args=(ai_stop, ai_receiver_health),
                name="deepseek-telegram-receiver",
            )
            ai_receiver_proc.start()
            print(
                f"[AI RX] Receiver restarted PID={ai_receiver_proc.pid}",
                flush=True,
            )

        def _ensure_ai_lane_alive(lane):
            nonlocal ai_fast_proc, ai_dev_proc

            if lane == "fast":
                proc = ai_fast_proc
                health = ai_fast_health
                idle_limit = 120
            else:
                proc = ai_dev_proc
                health = ai_dev_health
                idle_limit = 180

            now = monotonic()
            last = float(health.get("time", now))
            state = str(health.get("state", "starting"))
            dead = not proc.is_alive()

            # Do not kill legitimate long work because of elapsed time.
            # A busy process is controlled by per-request socket timeout/retry and
            # tool completion. Only an IDLE process with a dead heartbeat is stale.
            # OBSERVER_TIMEOUT_1591R11: a lane stuck in busy_* beyond the hard ceiling is
            # restarted as well; a hung evaluate never comes back on its own.
            stale = (
                (not state.startswith("busy_") and (now - last) > idle_limit)
                or (state.startswith("busy_") and (now - last) > AI_LANE_BUSY_CEILING_SECONDS)
            )

            if not dead and not stale:
                return

            print(
                f"[AI {lane.upper()}] {'умер' if dead else 'завис'} "
                f"(state={state}, age={int(now-last)}s) — перезапускаю.",
                flush=True,
            )
            if proc.is_alive():
                proc.terminate()
                proc.join(timeout=5)

            _ai_db_release_lane_claims(lane)
            health.clear()

            new_proc = mp.get_context("spawn").Process(
                target=ai_observer_process,
                args=(
                    status_map,
                    [x["cdp_url"] for x in browser_instances],
                    ai_stop,
                    health,
                    ai_action_queue,
                    ai_action_results,
                    lane,
                ),
                name=f"deepseek-{lane}-operator",
            )
            new_proc.start()

            if lane == "fast":
                ai_fast_proc = new_proc
            else:
                ai_dev_proc = new_proc

            print(f"[AI {lane.upper()}] restarted PID={new_proc.pid}.", flush=True)

        def ensure_ai_observers_alive():
            _ensure_ai_lane_alive("fast")
            _ensure_ai_lane_alive("dev")


        ctx = mp.get_context("spawn")
        rows = ctx.Queue()
        for row in clients:
            rows.put(row)

        processes = {}
        launch_events = [ctx.Event() for _ in range(TAB_COUNT)]
        captcha_gate = ctx.Semaphore(CAPTCHA_PARALLEL_MAX)  # TWO_BROWSERS_1591R28

        def spawn_worker(tab_id, initial_row=None):
            ready_event = launch_events[tab_id - 1]
            browser_id = ((tab_id - 1) // TABS_PER_BROWSER) + 1
            instance = browser_instances[browser_id - 1]
            worker_cdp_url = instance["cdp_url"]
            try:
                ready_event.clear()
            except Exception:
                pass
            proc = ctx.Process(
                target=_tab_process,
                args=(tab_id, worker_cdp_url, rows, str(base_dir), ready_event),
                kwargs={
                    "heartbeat": heartbeat,
                    "status_map": status_map,
                    "initial_row": initial_row,
                    "total_rows": total_source_rows,
                    "diagnostic_session_dir": str(diagnostic_session_dir),
                    "success_queue": success_queue,
                    "captcha_gate": captcha_gate,  # TWO_BROWSERS_1591R28
                },
                name=f"esim-tab-{tab_id}",
            )
            proc.start()
            processes[tab_id] = proc
            return proc, ready_event

        def restart_browser_instance(browser_idx, reason):  # BROWSER_HANG_1591R18
            """Chromium stopped answering CDP: replace the browser process and its worker tabs.

            A tab still working a row gets the same row again. A tab under success/error
            guard, or one that already completed its confirm cycle, takes the next row so
            nothing is submitted twice. DONE / MANUAL_STOP / RESTART_WAIT slots stay as they are.
            When no Chromium comes up, the process exits with RESTART_EXIT_CODE and the
            controller relaunches everything.
            """
            instance = browser_instances[browser_idx]
            first_tab = browser_idx * TABS_PER_BROWSER + 1
            tab_ids = [t for t in range(first_tab, first_tab + TABS_PER_BROWSER) if t in processes]
            print(
                f"[BROWSER RESTART] Chromium #{instance['id']}: {reason} "
                f"Перезапускаю браузер и вкладки {tab_ids}.",
                flush=True,
            )
            plans = []
            for tab_id in tab_ids:
                proc = processes.get(tab_id)
                info = dict(heartbeat.get(str(tab_id)) or {})
                phase = str(info.get("phase") or "")
                if phase in {"DONE", "MANUAL_STOP", "RESTART_WAIT"}:
                    continue
                guarded = bool(info.get("success_guard")) or bool(info.get("error_guard")) or phase in {
                    "POST_AUTH_REVIEW", "SIGN_WAIT", "SUCCESS_ASSIST", "SUCCESS_STOP", "ERROR_ASSIST",
                }
                row = None if (guarded or bool(info.get("completed_confirm_cycle"))) else info.get("row")
                plans.append((tab_id, row))
                try:
                    if proc is not None and proc.is_alive():
                        proc.terminate()
                        proc.join(timeout=5)
                        if proc.is_alive():
                            proc.kill()
                            proc.join(timeout=3)
                except Exception:
                    pass
                heartbeat.pop(str(tab_id), None)
                status_map[str(tab_id)] = {
                    "text": (
                        f"♻️ Вкладка {tab_id}\nChromium перестал отвечать — браузер перезапущен.\n"
                        + ("Повторяю эту же строку." if row is not None else "Беру следующую строку.")
                    ),
                    "time": time.time(),
                }
            _terminate_chromium(instance)
            if not _relaunch_chromium(instance, chromium_exe):
                print(
                    f"[BROWSER RESTART] Chromium #{instance['id']} не поднял CDP-порт; "
                    "выхожу для перезапуска процесса контроллером.",
                    flush=True,
                )
                _restart_notify(
                    f"⚠️ Chromium #{instance['id']} перестал отвечать ({reason}) и не запустился заново. "
                    "Перезапускаю весь процесс."
                )
                request_relaunch(base_dir, "chromium relaunch failed")  # RESTART_RELAUNCH_1591R21
                raise SystemExit(RESTART_EXIT_CODE)
            print(f"[BROWSER RESTART] Chromium #{instance['id']} готов: {instance['cdp_url']}", flush=True)
            _restart_notify(
                f"♻️ Chromium #{instance['id']} перестал отвечать ({reason}) Браузер перезапущен, "
                f"вкладки {[t for t, _ in plans]} пересозданы: строки в работе повторяются, "
                "завершённые берут следующую."
            )
            for tab_id, row in plans:
                new_proc, _ = spawn_worker(tab_id, row)
                processes[tab_id] = new_proc

        def recover_dead_workers():
            """Restore capacity when a worker process died unexpectedly."""
            recovered = False
            for tab_id, proc in list(processes.items()):
                if proc is None or proc.is_alive():
                    continue

                info = heartbeat.get(str(tab_id)) or {}
                phase = str(info.get("phase") or "")
                if phase in {
                    "DONE", "SUCCESS_STOP", "MANUAL_STOP", "RESTART_WAIT",
                    "POST_AUTH_REVIEW", "SIGN_WAIT", "SUCCESS_ASSIST", "ERROR_ASSIST",
                } or bool(info.get("success_guard")) or bool(info.get("error_guard")):
                    print(
                        f"[DEAD RECOVERY] TAB {tab_id}: success_guard активен — "
                        "страницу не закрываю и worker автоматически не заменяю.",
                        flush=True,
                    )
                    continue

                saved_row = info.get("row")
                completed = bool(info.get("completed_confirm_cycle"))

                print(
                    f"[DEAD RECOVERY] TAB {tab_id}: process dead, phase={phase or 'unknown'}. "
                    + (
                        "Запускаю следующий worker."
                        if completed else
                        "Восстанавливаю слот с той же строкой."
                    ),
                    flush=True,
                )

                # Close a leftover page if one still exists. Failure here is not
                # fatal: the process is already dead and capacity must be restored.
                try:
                    _close_cdp_page_for_worker(
                        browser_instances[(tab_id - 1) // TABS_PER_BROWSER]["cdp_url"],
                        info,
                    )
                except Exception:
                    pass

                heartbeat.pop(str(tab_id), None)
                new_proc, _ = spawn_worker(
                    tab_id,
                    None if completed else _row_for_respawn_1591r32(saved_row, tab_id, base_dir, "dead recovery"),  # ROW_RESTART_LIMIT_1591R32
                )
                processes[tab_id] = new_proc
                recovered = True
            return recovered


        def recover_stalled_workers():
            """Recover any launched worker, including older cascade slots.

            PROTECTED_CHECK staleness is calculated by parent_watchdog from
            matcher_time only. Browser requests/analytics must not keep a dead
            matcher alive forever.
            """
            recovered = False
            for tab_id, proc, info, age in parent_watchdog(processes, heartbeat):
                if bool(info.get("success_guard")) or str(info.get("phase") or "") in {
                    "POST_AUTH_REVIEW", "SIGN_WAIT", "SUCCESS_ASSIST",
                    "SUCCESS_STOP", "ERROR_ASSIST"
                } or bool(info.get("error_guard")):
                    print(
                        f"[WATCHDOG] TAB {tab_id}: SUCCESS GUARD — recovery запрещён.",
                        flush=True,
                    )
                    continue
                saved_row = info.get("row")
                completed = bool(info.get("completed_confirm_cycle"))
                phase = str(info.get("phase") or "")
                matcher_stage = str(info.get("matcher_stage") or "")

                if phase == "PROTECTED_CHECK":
                    reason = (
                        f"Matcher не дал новый heartbeat {int(age)} сек."
                        + (f" Этап: {matcher_stage}." if matcher_stage else "")
                    )
                elif phase == "ROW_START":
                    reason = (
                        f"ROW_START без логического прогресса {int(age)} сек. "
                        f"(лимит {ROW_START_STALL_SECONDS} сек.)."
                    )
                else:
                    reason = (
                        f"Нет логического прогресса {int(age)} сек. "
                        f"Этап: {phase or 'unknown'} "
                        f"(лимит {DEFAULT_EXTERNAL_STALL_SECONDS} сек.)."
                    )

                status_map[str(tab_id)] = {
                    "text": (
                        f"♻️ Вкладка {tab_id}\n{reason}\n"  # BROWSER_HANG_1591R18: real line break
                        + (
                            "Цикл завершён — беру следующую строку."
                            if completed
                            else "Перезапускаю эту же строку."
                        )
                    ),
                    "time": time.time(),
                }
                print(f"[WATCHDOG] TAB {tab_id}: {reason}", flush=True)

                browser_idx = (tab_id - 1) // TABS_PER_BROWSER
                closed_old_tab = _close_cdp_page_for_worker(
                    browser_instances[browser_idx]["cdp_url"], info
                )
                if not closed_old_tab:
                    hang = cdp_unreachable_seconds(browser_instances[browser_idx]["cdp_url"])  # BROWSER_HANG_1591R18
                    if hang >= BROWSER_HANG_RESTART_SECONDS:
                        restart_browser_instance(
                            browser_idx,
                            f"CDP не отвечает {int(hang)} сек (вкладка {tab_id}: {reason})",
                        )
                        return True
                    print(
                        f"[WATCHDOG] TAB {tab_id}: старую вкладку закрыть не удалось; "
                        "replacement пока не создаю.",
                        flush=True,
                    )
                    continue

                try:
                    proc.terminate()
                    proc.join(timeout=5)
                    if proc.is_alive():
                        proc.kill()
                        proc.join(timeout=3)
                except Exception:
                    pass

                heartbeat.pop(str(tab_id), None)
                new_proc, _ = spawn_worker(
                    tab_id,
                    None if completed else _row_for_respawn_1591r32(saved_row, tab_id, base_dir, "watchdog"),  # ROW_RESTART_LIMIT_1591R32
                )
                processes[tab_id] = new_proc
                recovered = True
            return recovered


        last_ai_restart_at = {}

        last_host_lifecycle_at = {}

        def _finish_ai_action(action_id, result):
            if not action_id:
                return
            try:
                ai_action_results[str(action_id)] = dict(result)
            except Exception:
                pass

        def _host_worker_health(info, proc):
            now = monotonic()
            phase = str((info or {}).get("phase") or "")
            logical_age = now - float((info or {}).get("time") or now)
            matcher_age = now - float(
                (info or {}).get("matcher_time")
                or (info or {}).get("time")
                or now
            )
            if phase == "PROTECTED_CHECK" and proc is not None:
                matcher_age = min(matcher_age, _matcher_cpu_age(proc, now))  # MATCHER_HEARTBEAT_1591R9
            return phase, logical_age, matcher_age, bool(proc and proc.is_alive())

        def execute_ai_runtime_actions():
            """Execute one AI action at a time with generation + health validation."""
            try:
                action = ai_action_queue.get_nowait()
            except Exception:
                return False

            action_id = str(action.get("action_id") or "")
            kind = str(action.get("action") or "")
            tab_id = int(action.get("tab") or 0) if action.get("tab") is not None else 0
            requested_at = float(action.get("requested_at") or time.time())

            try:
                if time.time() - requested_at > 25:
                    result = {"ok": False, "error": "STALE_ACTION: request older than 25s"}
                    _finish_ai_action(action_id, result)
                    return False

                if kind == "RUN_TERMINAL":
                    result = _run_operator_terminal(
                        action.get("command"),
                        action.get("timeout", 120),
                        action.get("cwd"),
                    )
                    _finish_ai_action(action_id, result)
                    return bool(result.get("ok"))

                if kind == "OPEN_PAGE":
                    browser_no = int(action.get("browser") or 1)
                    result = _browser_tool(
                        [x["cdp_url"] for x in browser_instances],
                        "browser_open_page",
                        {"browser": browser_no, "url": action.get("url")},
                    )
                    _finish_ai_action(action_id, result)
                    return bool(result.get("ok"))

                if not 1 <= tab_id <= TAB_COUNT:
                    raise RuntimeError("TAB вне диапазона")

                proc = processes.get(tab_id)
                info = dict(heartbeat.get(str(tab_id)) or {})
                expected_name = str(action.get("expected_window_name") or "")
                current_name = str(info.get("window_name") or "")
                browser_idx = (tab_id - 1) // TABS_PER_BROWSER
                cdp_url = browser_instances[browser_idx]["cdp_url"]

                if not current_name or expected_name != current_name:
                    result = {
                        "ok": False,
                        "error": "STALE_GENERATION",
                        "expected_window_name": expected_name,
                        "current_window_name": current_name,
                    }
                    _finish_ai_action(action_id, result)
                    return False

                phase, logical_age, matcher_age, proc_alive = _host_worker_health(info, proc)
                user_directed = bool(action.get("user_directed"))

                lifecycle = kind in {
                    "RESTART_TAB", "CLOSE_TAB", "RELOAD", "NAVIGATE", "BACK", "FORWARD"
                }

                if lifecycle and (
                    bool(info.get("success_guard"))
                    or bool(info.get("error_guard"))
                    or phase in {
                        "POST_AUTH_REVIEW", "SIGN_WAIT", "SUCCESS_ASSIST",
                        "SUCCESS_STOP", "ERROR_ASSIST"
                    }
                ):
                    result = {
                        "ok": False,
                        "error": "SUCCESS_GUARD_LIFECYCLE_FORBIDDEN",
                        "phase": phase,
                        "note": (
                            "Эта physical-вкладка находится под SUCCESS/ERROR GUARD. "
                            "Нельзя закрывать, перезапускать, reload/navigate/back/forward "
                            "до завершения автономного анализа."
                        ),
                    }
                    _finish_ai_action(action_id, result)
                    return False

                lifecycle = kind in {
                    "RESTART_TAB", "CLOSE_TAB", "RELOAD", "NAVIGATE", "BACK", "FORWARD"
                }

                if lifecycle and not user_directed:
                    if not proc_alive:
                        unhealthy = True
                    elif phase == "PROTECTED_CHECK":
                        unhealthy = matcher_age >= PROTECTED_MATCHER_STALL_SECONDS
                    elif phase == "ROW_START":
                        unhealthy = logical_age >= ROW_START_STALL_SECONDS
                    elif phase in {
                        "IDLE", "CONFIRM", "RESEND", "SUCCESS_STOP", "DONE",
                        "CANCELLING", "RESTART_ROW", "RESTART_CLOSE_RETRY",
                        "RESTART_ROW_READY",
                    }:
                        unhealthy = False
                    else:
                        unhealthy = logical_age >= DEFAULT_EXTERNAL_STALL_SECONDS
                    if not unhealthy:
                        result = {
                            "ok": False,
                            "error": "HOST_DENIED_HEALTHY_WORKER",
                            "phase": phase,
                            "logical_age": round(logical_age, 1),
                            "matcher_age": round(matcher_age, 1),
                        }
                        _finish_ai_action(action_id, result)
                        return False

                if kind in {"RESTART_TAB", "CLOSE_TAB"}:
                    if phase in {"SUCCESS_STOP", "DONE"} and not user_directed:
                        result = {"ok": False, "error": f"HOST_DENIED_PHASE_{phase}"}
                        _finish_ai_action(action_id, result)
                        return False

                    # Avoid a lifecycle burst in one Chromium.
                    if time.time() - float(last_host_lifecycle_at.get(browser_idx, 0)) < 3:
                        result = {"ok": False, "error": "BROWSER_LIFECYCLE_COOLDOWN"}
                        _finish_ai_action(action_id, result)
                        return False

                    saved_row = info.get("row")
                    closed = _close_cdp_page_for_worker(cdp_url, info)
                    if not closed:
                        raise RuntimeError("точную worker-вкладку закрыть не удалось")

                    if proc and proc.is_alive():
                        proc.terminate()
                        proc.join(timeout=5)
                        if proc.is_alive():
                            proc.kill()
                            proc.join(timeout=3)

                    if kind == "CLOSE_TAB":
                        # Explicit close leaves this managed slot stopped for this run.
                        heartbeat[str(tab_id)] = dict(info, phase="MANUAL_STOP")
                        status_map[str(tab_id)] = {
                            "text": f"⏹️ Вкладка {tab_id}\\nЭтап: MANUAL_STOP\\nЗакрыто DeepSeek по прямой команде пользователя.",
                            "time": time.time(),
                        }
                        processes.pop(tab_id, None)
                        last_host_lifecycle_at[browser_idx] = time.time()
                        result = {"ok": True, "action": kind, "tab": tab_id, "phase": "MANUAL_STOP"}
                        _finish_ai_action(action_id, result)
                        return True

                    heartbeat.pop(str(tab_id), None)
                    new_proc, _ = spawn_worker(tab_id, initial_row=saved_row)
                    processes[tab_id] = new_proc
                    last_host_lifecycle_at[browser_idx] = time.time()

                    # Wait for a NEW physical identity, not just process start.
                    deadline = monotonic() + 15
                    new_name = ""
                    while monotonic() < deadline:
                        cur = dict(heartbeat.get(str(tab_id)) or {})
                        new_name = str(cur.get("window_name") or "")
                        if new_name and new_name != expected_name:
                            break
                        time.sleep(0.2)

                    result = {
                        "ok": bool(new_name and new_name != expected_name),
                        "action": kind,
                        "tab": tab_id,
                        "old_window_name": expected_name,
                        "new_window_name": new_name,
                    }
                    if not result["ok"]:
                        result["error"] = "replacement heartbeat/window identity timeout"
                    _finish_ai_action(action_id, result)
                    return bool(result["ok"])

                # Page-bound single-step actions.
                def do_page_action(page):
                    args = dict(action.get("args") or {})
                    if kind == "CLICK":
                        return _browser_click(page, args)
                    if kind == "FILL":
                        return _browser_fill(page, args)
                    if kind == "TYPE":
                        selector = str(args.get("selector") or "").strip()
                        value = str(args.get("value") or "")
                        delay = int(args.get("delay_ms") or 0)
                        if selector:
                            page.locator(selector).first.type(
                                value, delay=delay,
                                timeout=int(args.get("timeout_ms") or 10000),
                            )
                        else:
                            page.keyboard.type(value, delay=delay)
                        return {"ok": True, "url": page.url}
                    if kind == "PRESS":
                        selector = str(args.get("selector") or "").strip()
                        key = str(args.get("key") or "")
                        if selector:
                            page.locator(selector).first.press(
                                key, timeout=int(args.get("timeout_ms") or 10000)
                            )
                        else:
                            page.keyboard.press(key)
                        return {"ok": True, "url": page.url}
                    if kind == "EVALUATE_JS":
                        value = page.evaluate(str(args.get("script") or ""))
                        try:
                            json.dumps(value)
                        except Exception:
                            value = repr(value)
                        return {"ok": True, "result": value, "url": page.url}
                    if kind == "RELOAD":
                        page.reload(wait_until="domcontentloaded", timeout=30000)
                        return {"ok": True, "url": page.url}
                    if kind == "NAVIGATE":
                        page.goto(
                            str(args.get("url") or ""),
                            wait_until=str(args.get("wait_until") or "domcontentloaded"),
                            timeout=int(args.get("timeout_ms") or 30000),
                        )
                        return {"ok": True, "url": page.url}
                    if kind == "BACK":
                        page.go_back(wait_until="domcontentloaded", timeout=30000)
                        return {"ok": True, "url": page.url}
                    if kind == "FORWARD":
                        page.go_forward(wait_until="domcontentloaded", timeout=30000)
                        return {"ok": True, "url": page.url}
                    if kind == "CLEAR_TELEMETRY":
                        page.evaluate("""() => {
                          const s=window.__deepseekTelemetry;
                          if(s){s.console=[];s.errors=[];s.network=[];}
                        }""")
                        return {"ok": True, "url": page.url}
                    raise RuntimeError(f"Неизвестное page action: {kind}")

                result = _with_exact_worker_page(cdp_url, expected_name, do_page_action)
                if isinstance(result, dict):
                    result.setdefault("ok", True)
                    result["window_name"] = expected_name
                else:
                    result = {"ok": True, "result": result, "window_name": expected_name}
                _finish_ai_action(action_id, result)
                return bool(result.get("ok"))

            except Exception as exc:
                result = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
                _finish_ai_action(action_id, result)
                print(f"[AI ACTION] {kind} TAB {tab_id}: {result['error']}", flush=True)
                return False


        # Каскад строится из BROWSER_COUNT / TABS_PER_BROWSER.
        # В этом эксперименте: Chromium #1: TAB 1 -> TAB 2 -> TAB 3.
        # Следующий TAB открывается только после завершения protected stage
        # предыдущего TAB — правило из 15.68 сохранено.
        cascade_next = {}
        cascade_front = {}
        first_tabs = []

        for browser_id in range(1, BROWSER_COUNT + 1):
            first_tab = (browser_id - 1) * TABS_PER_BROWSER + 1
            last_tab = min(first_tab + TABS_PER_BROWSER - 1, TAB_COUNT)
            if first_tab > TAB_COUNT:
                continue

            first_tabs.append(first_tab)
            cascade_front[browser_id] = first_tab

            for tab_id in range(first_tab, last_tab):
                cascade_next[tab_id] = tab_id + 1

        cascade_started = set()

        # Первый slot каждого Chromium запускается сразу.
        for tab_id in first_tabs:
            proc, ready_event = spawn_worker(tab_id)
            cascade_started.add(tab_id)
            browser_id = ((tab_id - 1) // TABS_PER_BROWSER) + 1
            print(
                f"[Запуск] Chromium #{browser_id}: вкладка {tab_id} открыта.",
                flush=True,
            )

        # SCHEDULED_RESTART_1591R13: the timer opens a drain; while draining no new slot
        # or replacement worker is started, workers finish their rows and exit, and the
        # runtime then leaves with RESTART_EXIT_CODE for the controller to relaunch it.
        restart_started_at = monotonic()
        restart_notified = False
        if restart_drain_requested(base_dir):  # STALE_DRAIN_RESET_1591R29
            clear_restart_drain(base_dir)
            print("[RESTART] Найден незавершённый drain прошлого запуска — сброшен, работаю как обычно.", flush=True)

        def _restart_tick():
            nonlocal restart_notified
            if not restart_drain_requested(base_dir):
                minutes = restart_policy_minutes(base_dir)
                if minutes <= 0 or monotonic() - restart_started_at < minutes * 60:
                    return False
                request_restart_drain(base_dir, f"every {minutes} min")
                print(f"[RESTART] Прошло {minutes} мин: worker дорабатывают строки, новые не берут.", flush=True)
            if not restart_notified:
                restart_notified = True
                _restart_notify(
                    "♻️ Плановый перезапуск: worker дорабатывают текущие строки "
                    "(подтверждение, подпись, разбор DeepSeek), новые не берут; "
                    "когда все закончат, процесс перезапустится."
                )
            return True

        # Для каждого Chromium свой последовательный cascade.
        while any(front in cascade_next for front in cascade_front.values()):
            if _restart_tick():
                break
            ensure_ai_receiver_alive()
            ensure_ai_observers_alive()
            execute_ai_runtime_actions()
            recover_dead_workers()
            recover_stalled_workers()
            progressed = False

            for browser_id in range(1, BROWSER_COUNT + 1):
                current = cascade_front.get(browser_id)
                if current is None or current not in cascade_next:
                    continue

                proc = processes.get(current)
                ready_event = launch_events[current - 1]

                if proc is not None and proc.is_alive() and not ready_event.is_set():
                    # Ждём именно завершение protected stage текущего slot.
                    continue

                current_ready = ready_event.is_set()
                current_dead = proc is None or not proc.is_alive()
                if not current_ready and not current_dead:
                    continue

                nxt = cascade_next[current]
                proc2, _ = spawn_worker(nxt)
                cascade_started.add(nxt)
                cascade_front[browser_id] = nxt
                print(
                    f"[Запуск] Chromium #{browser_id}: открываю вкладку {nxt}.",
                    flush=True,
                )
                progressed = True

            if not progressed:
                time.sleep(0.25)


        while True:
            ensure_ai_receiver_alive()
            ensure_ai_observers_alive()
            execute_ai_runtime_actions()
            recover_dead_workers()
            draining = _restart_tick()  # SCHEDULED_RESTART_1591R13
            if draining:
                _drain_deadline_1591r32(base_dir, processes, heartbeat)  # DRAIN_DEADLINE_1591R32

            # Успешная страница принадлежит общему Chromium и остаётся открытой.
            # Завершившийся SUCCESS_STOP-процесс заменяем новым процессом/вкладкой,
            # чтобы количество рабочих слотов не уменьшалось.
            replaced_success = False
            for tab_id, proc in list(processes.items()):
                if proc.is_alive():
                    continue
                info = heartbeat.get(str(tab_id)) or {}
                if info.get("phase") == "SUCCESS_STOP" and not draining:
                    print(
                        f"[Запуск] Вкладка {tab_id} успешна и оставлена открытой. "
                        "Создаю новую рабочую вкладку для следующей строки.",
                        flush=True,
                    )
                    heartbeat.pop(str(tab_id), None)
                    new_proc, _ = spawn_worker(tab_id)
                    processes[tab_id] = new_proc
                    replaced_success = True

            # Если живых процессов больше нет и ни один SUCCESS только что
            # не был заменён — очередь действительно закончилась.
            if not any(p.is_alive() for p in processes.values()) and not replaced_success:
                break

            recover_stalled_workers()
            time.sleep(1)

        for proc in processes.values():
            proc.join(timeout=1)

        if restart_drain_requested(base_dir):  # SCHEDULED_RESTART_1591R13
            clear_restart_drain(base_dir)
            print("[RESTART] Все worker завершили строки; выхожу для планового перезапуска.", flush=True)
            _restart_notify("♻️ Все worker завершили строки. Перезапускаю процесс.")
            request_relaunch(base_dir, "drain complete")  # RESTART_RELAUNCH_1591R21
            raise SystemExit(RESTART_EXIT_CODE)

        print(f"Все {TAB_COUNT} worker-слота завершили обработку очереди.")
        try:
            input("Вкладки оставлены открытыми. Enter — закрыть Chromium: ")
        except EOFError:
            pass
    finally:
        try:
            tg_stop.set()
            tg_proc.join(timeout=5)
            if tg_proc.is_alive():
                tg_proc.terminate()
        except Exception:
            pass
        try:
            ai_stop.set()
            for proc_ai in (ai_fast_proc, ai_dev_proc):
                proc_ai.join(timeout=8)
                if proc_ai.is_alive():
                    proc_ai.terminate()
        except Exception:
            pass
        try:
            if ai_receiver_proc is not None:
                ai_receiver_proc.join(timeout=8)
                if ai_receiver_proc.is_alive():
                    ai_receiver_proc.terminate()
        except Exception:
            pass
        try:
            AI_POLL_LOCK_FILE.unlink(missing_ok=True)
        except Exception:
            pass
        for instance in browser_instances:
            proc_i = instance["proc"]
            if proc_i.poll() is None:
                proc_i.terminate()
                try:
                    proc_i.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc_i.kill()
            shutil.rmtree(instance["profile"], ignore_errors=True)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nОстановлено пользователем.")
    except Exception as exc:
        print(f"Ошибка запуска: {type(exc).__name__}: {exc}")

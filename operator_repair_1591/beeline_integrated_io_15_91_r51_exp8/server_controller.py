#!/usr/bin/env python3
from pathlib import Path
import json
import os
import re
import signal
import subprocess
import sys
import tempfile
import time

import requests

import test_beeline as app
import telegram_menu as _menu_mod  # TELEGRAM_MENU_1591R38

IO_BUILD_VERSION = "15.91-io"
from batch_support import load_clients


BASE_DIR = Path(__file__).resolve().parent
CLIENTS_FILE = BASE_DIR / "clients.txt"
PROCESSED_FILE = BASE_DIR / "processed_numbers.txt"
OFFSET_FILE = BASE_DIR / "telegram_controller_offset.txt"
ARCHIVE_DIR = BASE_DIR / "base_archive"

BTN_START = "▶️ Запустить"
BTN_STOP = "⏹ Остановить"
BTN_RESTART = "🔄 Перезапуск"
BTN_UPLOAD = "📥 Загрузить новую базу номеров"

CONTROL_TEXTS = {
    BTN_START,
    BTN_STOP,
    BTN_RESTART,
    BTN_UPLOAD,
    "/start",
    "/menu",
    "/status",
}

# TELEGRAM_MENU_1591R38: the bottom keyboard is gone; every notice removes it once, the
# inline menu (telegram_menu.py) is the control surface.
MENU_MARKUP = json.dumps({"remove_keyboard": True})


def _cfg():
    return app.load_telegram_config()


def _chat_id():
    return str(_cfg().get("chat_id", "")).strip()


def _send(text, *, menu=True):
    return app._io1591.enqueue_notice(
        vars(app), _chat_id(), str(text), MENU_MARKUP if menu else None
    )


def _typing():
    try:
        app.telegram_api(
            _cfg(),
            "sendChatAction",
            {"chat_id": _chat_id(), "action": "typing"},
        )
    except Exception:
        pass


def _load_offset():
    try:
        return max(0, int(OFFSET_FILE.read_text(encoding="utf-8").strip()))
    except Exception:
        return 0


def _save_offset(value):
    tmp = OFFSET_FILE.with_suffix(".tmp")
    tmp.write_text(str(int(value)), encoding="utf-8")
    tmp.replace(OFFSET_FILE)


def _purge_control_messages_from_ai():
    """Remove old/pending control commands from AI storage on controller startup."""
    try:
        with app._ai_db_connect() as conn:
            rows = conn.execute(
                "SELECT update_id, body, done_at FROM inbox"
            ).fetchall()
            filtered = 0
            for update_id, body, done_at in rows:
                body = str(body or "").strip()
                if body in CONTROL_TEXTS or body.startswith("/"):
                    # Never let a stale control command produce a delayed AI reply.
                    conn.execute(
                        "DELETE FROM outbox WHERE update_id=?",
                        (int(update_id),),
                    )
                    if done_at is None:
                        conn.execute(
                            """UPDATE inbox
                               SET done_at=?, last_error='controller_filtered',
                                   claimed_by=NULL, claim_until=NULL
                               WHERE update_id=?""",
                            (time.time(), int(update_id)),
                        )
                    filtered += 1
            conn.commit()
            if filtered:
                print(
                    f"[CTRL→AI] Отфильтровано старых control-команд: {filtered}.",
                    flush=True,
                )
    except Exception as exc:
        print(
            f"[CTRL→AI] Не удалось очистить старые control-команды: "
            f"{type(exc).__name__}: {exc}",
            flush=True,
        )


def _validate_base(path):
    rows = load_clients(path)
    if not rows:
        raise ValueError("В файле нет ни одной строки с номером.")
    return len(rows)


def _archive_progress():
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    if CLIENTS_FILE.exists() and CLIENTS_FILE.stat().st_size:
        (ARCHIVE_DIR / f"clients_{stamp}.txt").write_bytes(CLIENTS_FILE.read_bytes())
    if PROCESSED_FILE.exists() and PROCESSED_FILE.stat().st_size:
        (ARCHIVE_DIR / f"processed_numbers_{stamp}.txt").write_bytes(
            PROCESSED_FILE.read_bytes()
        )


def _download_document(file_id, destination):
    cfg = _cfg()
    info, err = app.telegram_api(cfg, "getFile", {"file_id": file_id})
    if err or not info:
        raise RuntimeError(err or "Telegram getFile не вернул файл.")
    rel = str((info.get("result") or {}).get("file_path") or "").strip()
    if not rel:
        raise RuntimeError("Telegram не вернул file_path.")
    token = str(cfg.get("token") or "").strip()
    url = f"https://api.telegram.org/file/bot{token}/{rel}"
    r = requests.get(
        url,
        proxies=app.telegram_http_proxies(cfg),
        timeout=60,
    )
    r.raise_for_status()
    destination.write_bytes(r.content)


# SCHEDULED_RESTART_1591R13
def _restart_command(argument):
    """/restart, /restart off, /restart 20m, /restart 1h, /restart now."""
    argument = str(argument or "").strip().lower()
    if not argument:
        minutes = app.restart_policy_minutes(BASE_DIR)
        state = f"каждые {minutes} мин" if minutes > 0 else "выключен"
        pending = (" Сейчас ожидается перезапуск: worker дорабатывают строки."
                   if app.restart_drain_requested(BASE_DIR) else "")
        return (f"♻️ Плановый перезапуск: {state}.{pending}\n"
                "Команды: /restart off, /restart 20m, /restart 1h, /restart now")
    if argument == "now":
        app.request_restart_drain(BASE_DIR, "manual")
        return ("♻️ Запрошен перезапуск: worker дорабатывают текущие строки, новые не берут; "
                "затем процесс перезапустится.")
    minutes = app.parse_restart_setting(argument)
    if minutes is None:
        return "Не понял интервал. Примеры: /restart off, /restart 20m, /restart 1h, /restart now"
    app.write_restart_policy(BASE_DIR, minutes)
    if minutes <= 0:
        return "♻️ Плановый перезапуск выключен."
    return (f"♻️ Плановый перезапуск включён: каждые {minutes} мин. Worker дорабатывают строки "
            "до конца (подтверждение, подпись, разбор DeepSeek), затем процесс перезапускается.")


RELAUNCH_MARKER_MAX_AGE = 600  # RESTART_RELAUNCH_1591R21: a marker older than this is stale


def _relaunch_marker_fresh(marker):
    try:
        age = time.time() - marker.stat().st_mtime
    except OSError:
        return False
    if age <= RELAUNCH_MARKER_MAX_AGE:
        return True
    try:
        marker.unlink()
    except OSError:
        pass
    return False


# SIM_URL_PER_ROW_1591R36
_RL_LINE = re.compile(r"^(?P<ts>\S+)\s+\S+\s+python\[(?P<pid>\d+)\]:\s?(?P<msg>.*)$")
_RL_START = re.compile(r"\[Вкладка (?P<tab>\d+)\] Обрабатываю строку (?P<row>\d+), номер заканчивается на (?P<tail>\d+)")
_RL_OFFER = re.compile(r"eSIM offer сохранён: номер=(?P<num>\S+) \| (?P<url>\S+hash_order=[0-9a-f]+)")
_RL_OUTCOMES = (
    ("оплата", re.compile(r"ТРЕБУЕТСЯ ОПЛАТА\. Строка (?P<row>\d+)")),
    ("не подтверждена", re.compile(r"ПОДПИСЬ НЕ ПОДТВЕРЖДЕНА\. Строка (?P<row>\d+)")),
    ("результат", re.compile(r"Результат строки (?P<row>\d+): (?P<status>\S+)")),
)


def _rows_from_journal_1591r36(log):
    """Rows as the journal saw them: start line, every «продолжить» offer capture, outcome."""
    rows, current = [], {}
    for line in log.splitlines():
        m = _RL_LINE.match(line)
        if not m:
            continue
        ts, pid, msg = m.group("ts")[:19].replace("T", " "), m.group("pid"), m.group("msg")
        s = _RL_START.search(msg)
        if s:
            info = {"row": s.group("row"), "tab": s.group("tab"), "tail": s.group("tail"), "start": ts,
                    "offers": [], "signed": False, "outcome": ""}
            rows.append(info)
            current[pid] = info
            continue
        info = current.get(pid)
        if info is None:
            continue
        o = _RL_OFFER.search(msg)
        if o:
            info["offers"].append((ts, o.group("num"), o.group("url")))
            continue
        if "Нажата кнопка «Подписать договор»" in msg:
            info["signed"] = True
            continue
        for name, pat in _RL_OUTCOMES:
            r = pat.search(msg)
            if r and r.group("row") == info["row"]:
                info["outcome"] = name if name != "результат" else r.group("status")
                break
    return rows


# CLEAR_BASE_1591R50
def _clear_base_command(proc):
    """/clear: the same base from the start. The worker is stopped, processed_numbers.txt and
    deferred_rows.jsonl go to base_archive/ and are removed (clients.txt stays), and the worker is
    started again, so every row of the loaded base is processed anew. Results and eSIM records are
    not touched."""
    if not CLIENTS_FILE.exists() or not CLIENTS_FILE.stat().st_size:
        return "❌ База пуста: нечего запускать заново. Загрузи базу («📥 Загрузить базу»)."
    try:
        rows = len(load_clients(CLIENTS_FILE))
    except Exception:
        rows = -1
    was_running = proc.running()
    if was_running:
        proc.stop()
    stamp = time.strftime("%Y%m%d_%H%M%S")
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    deferred = BASE_DIR / "deferred_rows.jsonl"
    processed = 0
    try:
        if PROCESSED_FILE.exists():
            processed = sum(1 for line in PROCESSED_FILE.read_text("utf-8", errors="replace").splitlines() if line.strip())
    except Exception:
        processed = -1
    for path, name in ((PROCESSED_FILE, f"processed_numbers_{stamp}.txt"), (deferred, f"deferred_rows_{stamp}.jsonl")):
        try:
            if path.exists() and path.stat().st_size:
                (ARCHIVE_DIR / name).write_bytes(path.read_bytes())
            path.unlink(missing_ok=True)
        except Exception as exc:
            return f"❌ Не очищено: {path.name}: {type(exc).__name__}: {exc}"
    ok, start_msg = proc.start()
    shown_rows = f"{rows} строк" if rows >= 0 else "строки"
    shown_done = f"{processed}" if processed >= 0 else "?"
    head = f"🧹 Отработанные номера очищены ({shown_done}), отложенные строки сброшены. База из {shown_rows} идёт с начала."
    if ok:
        return head + ("\n🔄 Процесс перезапущен." if was_running else "\n▶️ Процесс запущен.")
    return head + f"\n⚠️ Запуск не удался: {start_msg}"


def _row_link_command(argument):
    """/res <номер eSIM из пуша, хотя бы 4 последние цифры> или /res <номер строки>.

    Before revision 36 the push could carry the link of the tab's earlier row; the journal
    keeps the real one: the last offer captured for the row is the order that was signed."""
    key = re.sub(r"\D", "", argument or "")
    if len(key) < 3:
        return ("Формат: /res <номер eSIM из пуша> (можно последние 4–6 цифр) или /res <номер строки>. "
                "Отвечу ссылкой заказа, который реально подписан в этой строке.")
    try:
        log = subprocess.run(["journalctl", "-u", "beeline", "--no-pager", "-o", "short-iso", "--since", "-3 days"],
                             capture_output=True, text=True, timeout=120).stdout
    except Exception as exc:
        return f"Журнал недоступен: {type(exc).__name__}: {exc}"
    rows = _rows_from_journal_1591r36(log)
    by_row = [r for r in rows if r["row"] == key] if len(key) <= 5 else []
    by_number = [r for r in rows if any(re.sub(r"\D", "", num).endswith(key) for _, num, _ in r["offers"])
                 or r["tail"] == key]
    hits = (by_row + [r for r in by_number if r not in by_row])[-5:]
    if not hits:
        return f"В журнале за 3 дня нет строки или номера eSIM, оканчивающегося на …{key[-6:]}."
    out = []
    for r in hits:
        outcome = r["outcome"] or ("подписана" if r["signed"] else "не завершена")
        head = f"Строка {r['row']} (вкладка {r['tab']}, …{r['tail']}, {r['start'][5:16]}), исход: {outcome}"
        if not r["offers"]:
            out.append(head + "\nСсылка в журнале не найдена.")
            continue
        ts, num, url = r["offers"][-1]
        text = head + f"\neSIM {num}\nСсылка заказа: {url}"
        if len(r["offers"]) > 1:
            text += f"\n(ранних заказов этой строки без данных: {len(r['offers']) - 1})"
        out.append(text)
    return "\n\n".join(out)


def _restart_after_drain(proc):
    """Relaunch the automation that exited on purpose after its drain.

    RESTART_RELAUNCH_1591R21: the trigger is RESTART_EXIT_CODE from the process, the last code
    reap() recorded, or a fresh restart_relaunch.json written by the runtime before it exited
    (xvfb-run reported 5 instead of 75 on the server). A running process is never touched.
    """
    if proc.running():
        return False
    marker = BASE_DIR / getattr(app, "RESTART_RELAUNCH_FILE_NAME", "restart_relaunch.json")
    code = proc.proc.poll() if proc.proc is not None else getattr(proc, "last_code", None)
    if code != app.RESTART_EXIT_CODE and not _relaunch_marker_fresh(marker):
        return False
    proc.reap()
    proc.last_code = None
    try:
        marker.unlink()
    except OSError:
        pass
    ok, answer = proc.start()
    _send(("♻️ Плановый перезапуск выполнен. " if ok else "⚠️ Плановый перезапуск: запуск не удался. ") + answer)
    return True


class AutomationProcess:
    def __init__(self):
        self.proc = None
        self.last_code = None  # RESTART_RELAUNCH_1591R21

    def running(self):
        return self.proc is not None and self.proc.poll() is None

    def start(self):
        if self.running():
            return False, "Процесс уже запущен."
        if not CLIENTS_FILE.exists() or not CLIENTS_FILE.stat().st_size:
            return False, "База пуста. Сначала нажми «Загрузить новую базу номеров»."
        try:
            count = _validate_base(CLIENTS_FILE)
        except Exception as exc:
            return False, f"clients.txt не прошёл проверку: {exc}"

        env = os.environ.copy()
        env["TG_EXTERNAL_CONTROLLER"] = "1"
        cmd = [
            "/usr/bin/xvfb-run",
            "-a",
            "-s",
            "-screen 0 1920x1080x24",
            str(BASE_DIR / "venv" / "bin" / "python"),
            str(BASE_DIR / "test_beeline.py"),
        ]
        self.proc = subprocess.Popen(
            cmd,
            cwd=str(BASE_DIR),
            env=env,
            start_new_session=True,
        )
        return True, f"▶️ Запущено. PID {self.proc.pid}. Строк в базе: {count}."

    def stop(self):
        if not self.running():
            self.proc = None
            return False, "Процесс уже остановлен."

        pid = self.proc.pid
        try:
            pgid = os.getpgid(pid)
            os.killpg(pgid, signal.SIGTERM)
        except Exception:
            try:
                self.proc.terminate()
            except Exception:
                pass

        try:
            self.proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(os.getpgid(pid), signal.SIGKILL)
            except Exception:
                try:
                    self.proc.kill()
                except Exception:
                    pass
            try:
                self.proc.wait(timeout=5)
            except Exception:
                pass

        self.proc = None
        return True, "⏹ Процесс остановлен."

    def restart(self):
        self.stop()
        time.sleep(1)
        return self.start()

    def reap(self):
        if self.proc is not None and self.proc.poll() is not None:
            code = self.proc.returncode
            pgid = self.proc.pid
            self.proc = None
            self.last_code = code  # RESTART_RELAUNCH_1591R21: kept for _restart_after_drain
            print(f"[CTRL] automation завершилась code={code}", flush=True)
            try:
                os.killpg(pgid, signal.SIGTERM)  # RESTART_RELAUNCH_1591R21: leftover Xvfb of that session
            except Exception:
                pass

    def status(self):
        self.reap()
        if self.running():
            return f"🟢 Запущен (PID {self.proc.pid})"
        return "🔴 Остановлен"


def main():
    os.environ["TG_EXTERNAL_CONTROLLER"] = "1"
    cfg = _cfg()
    chat = _chat_id()
    if not chat:
        raise RuntimeError("telegram_config.json: отсутствует chat_id")

    app._ai_db_init()
    app._io1591.init_delivery(vars(app))
    app._io1591.start_chat(vars(app))
    app._io1591.start_sender(vars(app), cfg, MENU_MARKUP)
    me, err = app.telegram_api(cfg, "getMe", {})
    if err or not me:
        print(f"[CTRL TG] Telegram временно недоступен; ответы остаются в очереди: {app._io1591.redact(err)}", flush=True)
    _purge_control_messages_from_ai()
    CLIENTS_FILE.touch(exist_ok=True)

    proc = AutomationProcess()
    waiting_upload = False
    # TELEGRAM_MENU_1591R38: one panel message with inline buttons; the eight status messages
    # of earlier revisions are retired once.
    menu = _menu_mod.TelegramMenu(app, BASE_DIR, proc, link_resolver=_row_link_command)
    try:
        menu.retire_status_messages(BASE_DIR / "telegram_status_messages.json")
    except Exception as exc:
        print(f"[CTRL] старые статусные сообщения не обновлены: {exc}", flush=True)

    # Controller is the only long-poll consumer.
    app.telegram_api(cfg, "deleteWebhook", {"drop_pending_updates": "false"})
    offset = _load_offset()

    # Preserve old behavior: after server boot start automatically if a base exists.
    if CLIENTS_FILE.stat().st_size:
        ok, msg = proc.start()
        print(f"[CTRL] auto-start: {msg}", flush=True)

    try:
        menu.show_menu(fresh=True)  # TELEGRAM_MENU_1591R38
    except Exception as exc:
        print(f"[CTRL] меню не показано: {exc}", flush=True)

    while True:
        _restart_after_drain(proc)  # SCHEDULED_RESTART_1591R13
        proc.reap()
        try:
            menu.tick()  # TELEGRAM_MENU_1591R38: live status only while its view is open
        except Exception as exc:
            print(f"[CTRL] меню: {exc}", flush=True)

        r, err = app.telegram_api(
            cfg,
            "getUpdates",
            {
                "timeout": 2,
                "offset": offset,
                "allowed_updates": json.dumps(["message", "callback_query"]),  # TELEGRAM_MENU_1591R38
            },
        )
        if err:
            print(f"[CTRL TG] getUpdates: {err}", flush=True)
            time.sleep(2)
        elif r:
            for upd in r.get("result", []):
                update_id = int(upd.get("update_id") or 0)
                update_failed = False

                try:
                    callback = upd.get("callback_query")  # TELEGRAM_MENU_1591R38: inline buttons
                    if callback:
                        cb_chat = str(((callback.get("message") or {}).get("chat") or {}).get("id") or "")
                        if cb_chat == chat and menu.handle_callback(callback) == "upload":
                            waiting_upload = True
                        continue
                    msg = upd.get("message") or {}
                    msg_chat = str((msg.get("chat") or {}).get("id") or "")
                    if msg_chat != chat:
                        continue

                    text = str(msg.get("text") or "").strip()
                    document = msg.get("document") or {}

                    # ---- CONTROL PLANE: never goes to AI inbox ----
                    if text in {"/start", "/menu"}:
                        waiting_upload = False
                        menu.show_menu(fresh=True)  # TELEGRAM_MENU_1591R38
                        continue

                    if text == "/status":
                        menu.show_menu(fresh=True)
                        menu.show_status()
                        continue

                    if text == BTN_START:
                        waiting_upload = False
                        _, answer = proc.start()
                        _send(answer)
                        continue

                    if text == BTN_STOP:
                        waiting_upload = False
                        _, answer = proc.stop()
                        _send(answer)
                        continue

                    if text == BTN_RESTART:
                        waiting_upload = False
                        _, answer = proc.restart()
                        _send("🔄 " + answer)
                        continue

                    if text == BTN_UPLOAD:
                        waiting_upload = True
                        _send(
                            "📥 Пришли следующим сообщением .txt файл с новой базой.\n"
                            "Текущий файл будет заменён только после успешной проверки.\n"
                            "Если процесс сейчас работает — после загрузки он автоматически перезапустится."
                        )
                        continue

                    if text.startswith("/restart"):  # SCHEDULED_RESTART_1591R13
                        waiting_upload = False
                        _send(_restart_command(text[len("/restart"):]))
                        continue

                    if text.split()[0].lower().split("@")[0] == "/clear":  # CLEAR_BASE_1591R50
                        waiting_upload = False
                        _send(_clear_base_command(proc))
                        continue

                    if text.startswith("/res"):  # SIM_URL_PER_ROW_1591R36: the row's real order link
                        waiting_upload = False
                        _send(_row_link_command(text[len("/res"):]))
                        continue

                    # Any slash-command belongs to controller namespace and is
                    # deliberately kept away from DeepSeek.
                    if text.startswith("/"):
                        menu.show_menu(fresh=True, note="Неизвестная команда — вот меню.")  # TELEGRAM_MENU_1591R38
                        continue

                    if document:
                        if not waiting_upload:
                            _send(
                                "Чтобы заменить базу, сначала нажми "
                                "«📥 Загрузить новую базу номеров»."
                            )
                            continue

                        file_name = str(document.get("file_name") or "")
                        file_size = int(document.get("file_size") or 0)
                        file_id = str(document.get("file_id") or "")
                        if not file_id:
                            _send("Telegram не передал file_id.")
                            continue
                        if file_size and file_size > 20 * 1024 * 1024:
                            _send("Файл слишком большой. Максимум 20 МБ.")
                            continue
                        if file_name and not file_name.lower().endswith(".txt"):
                            _send("Нужен .txt файл.")
                            continue

                        was_running = proc.running()
                        tmp = BASE_DIR / ".clients_upload.tmp"
                        try:
                            _download_document(file_id, tmp)
                            count = _validate_base(tmp)

                            if was_running:
                                proc.stop()

                            _archive_progress()
                            tmp.replace(CLIENTS_FILE)

                            # New base means a new processing pass.
                            PROCESSED_FILE.unlink(missing_ok=True)

                            waiting_upload = False

                            if was_running:
                                ok, start_msg = proc.start()
                                if not ok:
                                    _send(
                                        f"✅ Новая база загружена: {count} строк.\n"
                                        f"⚠️ Автозапуск не удался: {start_msg}"
                                    )
                                else:
                                    _send(
                                        f"✅ Новая база загружена: {count} строк.\n"
                                        "🔄 Работавший процесс остановлен и запущен заново."
                                    )
                            else:
                                _send(
                                    f"✅ Новая база загружена: {count} строк.\n"
                                    "Процесс оставлен остановленным. Нажми «▶️ Запустить»."
                                )
                        except Exception as exc:
                            try:
                                tmp.unlink(missing_ok=True)
                            except Exception:
                                pass
                            _send(f"❌ База не заменена: {type(exc).__name__}: {exc}")
                        continue

                    # ---- AI PLANE ----
                    # Only ordinary text is persisted into the DeepSeek inbox.
                    if text:
                        # TELEGRAM_MENU_1591R38: DeepSeek gets a message only after «Спросить
                        # DeepSeek»; any other text (a word, a letter, a symbol) opens the menu.
                        if not menu.text_is_for_ai():
                            menu.show_menu(fresh=True)
                            continue
                        if str(os.environ.get("BEELINE_AI") or "1").strip().lower() in {"0", "off", "no", "false"}:
                            _send("🤖 DeepSeek выключен (BEELINE_AI=0 в настройках службы).")  # RESIGN_LIMIT_1591R48
                            continue
                        if not text.lower().startswith(("/op ", "/operator ", "оператор ")):
                            # OPERATOR_LIVE_1591R46: a question from «Спросить DeepSeek» is an
                            # operator order with the live browser tools, not a read-only chat.
                            upd = dict(upd)
                            upd["message"] = dict(upd.get("message") or {})
                            upd["message"]["text"] = "/op " + text
                        app._ai_db_store_telegram_update(upd, chat)
                        print(
                            f"[CTRL→AI] update={update_id}: {text[:120]}",
                            flush=True,
                        )
                        _typing()
                        menu.ai_sent()

                except Exception as exc:
                    update_failed = True
                    print(f"[CTRL RX] update={update_id} не сохранён/не обработан: {app._io1591.redact(exc)}", flush=True)
                    time.sleep(2)
                    break
                finally:
                    if not update_failed:
                        next_offset = max(offset, update_id + 1)
                        _save_offset(next_offset)
                        offset = next_offset

        # Sender runs independently: slow getUpdates no longer blocks replies.
        time.sleep(0.15)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass

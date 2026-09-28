#!/usr/bin/env python3
from pathlib import Path
import json
import os
import signal
import subprocess
import sys
import tempfile
import time

import requests

import test_beeline as app
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

MENU_MARKUP = json.dumps(
    {
        "keyboard": [
            [{"text": BTN_START}, {"text": BTN_STOP}],
            [{"text": BTN_RESTART}],
            [{"text": BTN_UPLOAD}],
        ],
        "resize_keyboard": True,
        "is_persistent": True,
        "input_field_placeholder": "Команда или сообщение DeepSeek",
    },
    ensure_ascii=False,
)


def _cfg():
    return app.load_telegram_config()


def _chat_id():
    return str(_cfg().get("chat_id", "")).strip()


def _send(text, *, menu=True):
    cfg = _cfg()
    payload = {
        "chat_id": _chat_id(),
        "text": str(text)[:4000],
        "disable_web_page_preview": "true",
    }
    if menu:
        payload["reply_markup"] = MENU_MARKUP
    _, err = app.telegram_api(cfg, "sendMessage", payload)
    if err:
        print(f"[CTRL TG] sendMessage: {err}", flush=True)


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


class AutomationProcess:
    def __init__(self):
        self.proc = None

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
            self.proc = None
            print(f"[CTRL] automation завершилась code={code}", flush=True)

    def status(self):
        self.reap()
        if self.running():
            return f"🟢 Запущен (PID {self.proc.pid})"
        return "🔴 Остановлен"


def main():
    cfg = _cfg()
    chat = _chat_id()
    if not chat:
        raise RuntimeError("telegram_config.json: отсутствует chat_id")

    me, err = app.telegram_api(cfg, "getMe", {})
    if err or not me:
        raise RuntimeError(f"Telegram недоступен: {err}")

    app._ai_db_init()
    _purge_control_messages_from_ai()
    CLIENTS_FILE.touch(exist_ok=True)

    proc = AutomationProcess()
    waiting_upload = False

    app.telegram_api(cfg, "deleteWebhook", {"drop_pending_updates": "false"})
    offset = _load_offset()

    if CLIENTS_FILE.stat().st_size:
        ok, msg = proc.start()
        print(f"[CTRL] auto-start: {msg}", flush=True)

    _send(
        "🎛 Управление софтом\n\n"
        f"Состояние: {proc.status()}\n"
        "Кнопки управления обрабатываются локально и НЕ отправляются DeepSeek."
    )

    while True:
        proc.reap()

        r, err = app.telegram_api(
            cfg,
            "getUpdates",
            {
                "timeout": 2,
                "offset": offset,
                "allowed_updates": json.dumps(["message"]),
            },
        )
        if err:
            print(f"[CTRL TG] getUpdates: {err}", flush=True)
            time.sleep(2)
        elif r:
            for upd in r.get("result", []):
                update_id = int(upd.get("update_id") or 0)
                offset = max(offset, update_id + 1)

                try:
                    msg = upd.get("message") or {}
                    msg_chat = str((msg.get("chat") or {}).get("id") or "")
                    if msg_chat != chat:
                        continue

                    text = str(msg.get("text") or "").strip()
                    document = msg.get("document") or {}

                    if text in {"/start", "/menu"}:
                        waiting_upload = False
                        _send(
                            "🎛 Управление софтом\n\n"
                            f"Состояние: {proc.status()}"
                        )
                        continue

                    if text == "/status":
                        _send(f"Состояние: {proc.status()}")
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

                    if text.startswith("/"):
                        _send("Неизвестная команда. Используй кнопки меню.")
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

                    if text:
                        app._ai_db_store_telegram_update(upd, chat)
                        print(
                            f"[CTRL→AI] update={update_id}: {text[:120]}",
                            flush=True,
                        )
                        _typing()

                finally:
                    _save_offset(offset)

        out = app._ai_db_next_outbox()
        if out:
            _, send_err = app.telegram_api(
                cfg,
                "sendMessage",
                {
                    "chat_id": out["chat_id"],
                    "text": out["body"][:4000],
                    "disable_web_page_preview": "true",
                    "reply_markup": MENU_MARKUP,
                },
            )
            if send_err:
                app._ai_db_outbox_fail(
                    out["update_id"],
                    send_err,
                    out.get("attempts", 0),
                )
                print(f"[CTRL AI TX] {send_err}", flush=True)
            else:
                app._ai_db_outbox_sent(out["update_id"])

        time.sleep(0.15)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass

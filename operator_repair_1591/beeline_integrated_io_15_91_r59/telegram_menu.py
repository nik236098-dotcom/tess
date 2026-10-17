#!/usr/bin/env python3
"""Inline menu of the beeline Telegram bot (revision 38, TELEGRAM_MENU_1591R38).

One panel message carries the whole control surface as inline buttons: status of the tabs,
the eSIMs the bot produced (with a per-eSIM mark), the event log, a guarded "ask DeepSeek"
entry and the start/stop/restart/upload controls. Navigation edits the panel in place, so
the chat is not flooded; nothing is edited in the background except the status view while
it is open (and that stops by itself after STATUS_AUTO_CLOSE_SECONDS).

The module only reads what the runtime already writes (status_snapshot.json,
successful_sims.jsonl, payment_required.jsonl, the journal) and keeps two small files of its
own: menu_state.json (panel message, current view) and esim_status.json (the marks).
"""
from __future__ import annotations

import html
import json
import os
import re
import subprocess
import threading
import time
from pathlib import Path

MENU_VERSION = "1591r38"

PANEL_MAX_AGE_SECONDS = 47 * 3600      # Telegram lets a bot edit its message for 48 hours
STATUS_REFRESH_SECONDS = 10            # live edits of the open status view, not more often
STATUS_AUTO_CLOSE_SECONDS = 60 * 60    # an open status view returns to the menu by itself
LOGS_CACHE_SECONDS = 20
ESIMS_PER_PAGE = 10
LOGS_PER_PAGE = 12
TEXT_LIMIT = 3900

STATE_FILE = "menu_state.json"
ESIM_STATUS_FILE = "esim_status.json"
STATUS_SNAPSHOT_FILE = "status_snapshot.json"

MARKS = {"new": "🆕", "ok": "✅", "bad": "❌"}
MARK_TITLES = {"new": "новая", "ok": "оформлена", "bad": "брак"}
# MENU_DELETE_1591R57: «🗑 Удалить» hides an eSIM from the list (the mark «hidden» in esim_status.json);
# the result files on the server (successful_sims.jsonl, payment_required.jsonl) stay as they are.
HIDDEN_MARK = "hidden"

# LINK_CHECK_1591R58: «🔗 Проверить ссылки» opens every order link of «Мои eSIM» in its own headless
# Chromium (not the bot's browsers, nothing is clicked or typed) and tells per link: ❌ does not open,
# 💳 waits for the payment, ✅ paid / ready, ❔ opened but unclear (the page's own words are kept).
LINK_CHECK_FILE = "link_check.json"
LINK_CHECK_TIMEOUT_SECONDS = 40
LINK_ICONS = {"dead": "❌", "pay": "💳", "ok": "✅", "used": "📲", "unknown": "❔", "error": "⚠️"}
LINK_TITLES = {"dead": "не работает", "pay": "ждёт оплаты", "ok": "оплачена / готова", "used": "уже использована",
               "unknown": "непонятно", "error": "не удалось проверить"}
_DEAD_WORDS = ("не найден", "истек", "истёк", "недействител", "что-то пошло не так", "произошла ошибка",
               "срок действия", "устарел", "страница не найдена", "ошибка 404", "not found")
_OK_WORDS = ("оплачен", "оплата прошла", "заказ оформлен", "договор зарегистрирован", "esim готова",
             "esim активирована", "активируйте esim", "установите esim", "qr-код", "qr код")
_PAY_WORDS = ("пора оплатить", "к оплате", "оплатить заказ", "перейти к оплате", "ожидает оплаты")
_STATUS_KEYS = ("selfregStatus", "orderStatus", "status", "state")
# LINK_STATUS_1591R59: the site answers errorCode "NONE" when there is no error (a valid order at the
# payment step was marked ❌), and selfregStatus DOCS_GENERATED is the order waiting for the payment.
# ESIM_SUCCESS with «срок установки eSIM истёк» is an eSIM already installed and used (📲, not ❌).
# The site's own state wins over the words of the page; only a real error, 4xx/5xx or /error is ❌.
_NO_ERROR_CODES = {"", "NONE", "OK", "0", "NULL", "SUCCESS"}
_SITE_STATUS_KINDS = {"DOCS_GENERATED": "pay", "ESIM_SUCCESS": "used"}


def _real_error(code):
    return "" if str(code or "").strip().upper() in _NO_ERROR_CODES else str(code).strip()


def _site_status(payload):
    """The order state the site's own JSON reports (selfregStatus, orderStatus…), "" when none."""
    data = payload.get("data") if isinstance(payload, dict) and isinstance(payload.get("data"), dict) else payload
    if not isinstance(data, dict):
        return ""
    for key in _STATUS_KEYS:
        value = data.get(key)
        if isinstance(value, (str, int)) and str(value).strip():
            return f"{key}={value}"
    return ""


def classify_order_page(final_url, http_status, body_text, site_status="", site_error=""):
    """(kind, short text) for an opened order link; kind is one of LINK_TITLES."""
    site_error = _real_error(site_error)  # LINK_STATUS_1591R59
    low = str(body_text or "").lower()
    lines = [x.strip() for x in str(body_text or "").splitlines() if x.strip()]
    hint = next((x for x in lines if re.search(r"esim|заказ|оплат|статус|ошибк|найден|истек|истёк", x, re.I)), "")
    hint = hint or (lines[0] if lines else "")
    extra = " · ".join(x for x in (site_status, f"ошибка сайта {site_error}" if site_error else "") if x)
    def text(base):
        return " · ".join(x for x in (base, extra) if x)[:160]
    try:
        status = int(http_status or 0)
    except (TypeError, ValueError):
        status = 0
    if status >= 400 or "/error" in str(final_url or "").lower() or site_error:
        return "dead", text(hint or f"HTTP {status}")
    site_kind = _SITE_STATUS_KINDS.get(str(site_status or "").split("=", 1)[-1].strip().upper())
    if site_kind:  # LINK_STATUS_1591R59: the site's own order state wins over guessing from words
        return site_kind, text(hint)
    if any(w in low for w in _DEAD_WORDS):
        return "dead", text(hint or f"HTTP {status}")
    if any(w in low for w in _OK_WORDS):
        return "ok", text(hint)
    if any(w in low for w in _PAY_WORDS):
        return "pay", text(hint)
    return "unknown", text(hint or "пустая страница")


def check_order_link(browser, url, timeout=LINK_CHECK_TIMEOUT_SECONDS):
    """Open one link in a fresh context of `browser` and classify it. Read-only."""
    context = browser.new_context()
    seen = {"status": "", "error": ""}
    try:
        page = context.new_page()

        def on_response(resp):
            try:
                if "selfreg" not in resp.url and "order" not in resp.url.lower():
                    return
                if "json" not in str(resp.headers.get("content-type", "")):
                    return
                body = resp.json()
                status = _site_status(body)
                if status:
                    seen["status"] = status
                data = body.get("data") if isinstance(body, dict) else None
                code = (data or {}).get("errorCode") if isinstance(data, dict) else None
                if _real_error(code):  # LINK_STATUS_1591R59: "NONE" is not an error
                    seen["error"] = str(code)
            except Exception:
                pass

        page.on("response", on_response)
        resp = page.goto(url, wait_until="domcontentloaded", timeout=int(timeout * 1000))
        try:
            page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            pass
        page.wait_for_timeout(1500)
        body = page.locator("body").inner_text(timeout=5000)
        kind, short = classify_order_page(page.url, resp.status if resp else 0, body, seen["status"], seen["error"])
        return {"kind": kind, "text": short, "final_url": page.url[:200]}
    finally:
        try:
            context.close()
        except Exception:
            pass


def playwright_link_checker(urls, progress=None):
    """Yield (url, result) for every url, one headless Chromium for the whole run."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser, last = None, None
        # the bundled headless shell, the bot's own Chromium, or LINK_CHECK_CHROMIUM (any Chromium binary)
        for exe in (None, p.chromium.executable_path, os.environ.get("LINK_CHECK_CHROMIUM")):
            try:
                browser = p.chromium.launch(headless=True, **({"executable_path": exe} if exe else {}))
                break
            except Exception as exc:
                last = exc
        if browser is None:
            raise last
        try:
            for url in urls:
                try:
                    result = check_order_link(browser, url)
                except Exception as exc:
                    result = {"kind": "error", "text": f"{type(exc).__name__}: {str(exc)[:100]}"}
                yield url, result
        finally:
            browser.close()

# Journal lines worth showing in the log view: (regex, icon).
LOG_PATTERNS = (
    (re.compile(r"ТРЕБУЕТСЯ ОПЛАТА\. Строка (\d+)"), "💳"),
    (re.compile(r"Результат строки (\d+): SUCCESS"), "✅"),
    (re.compile(r"ПОДПИСЬ НЕ ПОДТВЕРЖДЕНА\. Строка (\d+)"), "⚠️"),
    (re.compile(r"Результат строки (\d+): (CONFIRM_TIMEOUT|INVALID_ROW|ERROR\w*)"), "⏱"),
    (re.compile(r"перезапуска подряд не помогли|заменялся с этой строкой"), "⏭"),
    (re.compile(r"\[RESTART\]"), "♻️"),
    (re.compile(r"Плановый перезапуск"), "♻️"),
    (re.compile(r"Запускаю \d+ Chromium"), "🚀"),
    (re.compile(r"\[WATCHDOG\]|DEAD RECOVERY"), "🩹"),
    (re.compile(r"Дренаж идёт"), "⏳"),
    (re.compile(r"Строка \d+ пропущена|пропускаю строку|строка пропущена", re.I), "⏭"),
    (re.compile(r"retry after \d+|Too Many Requests"), "🚫"),
)
_JOURNAL_LINE = re.compile(r"^(?P<ts>\S+)\s+\S+\s+python\[(?P<pid>\d+)\]:\s?(?P<msg>.*)$")


def _now():
    return time.time()


def _read_json(path, default):
    try:
        return json.loads(Path(path).read_text("utf-8"))
    except Exception:
        return default


def _write_json(path, data):
    path = Path(path)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), "utf-8")
    tmp.replace(path)


def _count_lines(path):
    try:
        return sum(1 for line in Path(path).read_text("utf-8", errors="replace").splitlines() if line.strip())
    except Exception:
        return 0


def _digits(value):
    return re.sub(r"\D", "", str(value or ""))


def pretty_phone(value):
    d = _digits(value)
    if len(d) == 11 and d[0] in "78":
        return f"+7 {d[1:4]} {d[4:7]}-{d[7:9]}-{d[9:]}"
    return str(value or "—")


def _when(value):
    """«01.10 02:49» from the record's «2026-10-01 02:49:24»; "" when unknown."""
    value = str(value or "")
    if len(value) < 16:
        return ""
    return f"{value[8:10]}.{value[5:7]} {value[11:16]}"


def _kb(rows):
    return json.dumps({"inline_keyboard": rows}, ensure_ascii=False)


def _btn(text, data):
    return {"text": text, "callback_data": data[:64]}


def _clip(text, limit=TEXT_LIMIT):
    text = str(text or "")
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _esc(text):
    """Dynamic text inside the HTML-formatted panel (statuses, names, journal lines)."""
    return html.escape(str(text if text is not None else ""), quote=False)


class TelegramMenu:
    """The panel. `app` is the runtime module (telegram_api, config, record formats);
    `proc` is the controller's AutomationProcess (start/stop/restart/status/running)."""

    def __init__(self, app, base_dir, proc, link_resolver=None):
        self.app = app
        self.base = Path(base_dir)
        self.proc = proc
        self.link_resolver = link_resolver     # row number -> text with the real order link
        self.state = _read_json(self.base / STATE_FILE, {})
        self.marks = _read_json(self.base / ESIM_STATUS_FILE, {})
        self._logs_cache = (0.0, [])
        self._status_last_text = ""
        self._status_last_edit = 0.0
        self.link_checker = playwright_link_checker  # LINK_CHECK_1591R58: replaceable in tests
        self.link_results = _read_json(self.base / LINK_CHECK_FILE, {})
        for res in self.link_results.values():  # LINK_STATUS_1591R59: results of r58 that took «NONE» for an error
            text = str(res.get("text") or "")
            if res.get("kind") == "dead" and "ошибка сайта NONE" in text:
                res["text"] = text.replace(" · ошибка сайта NONE", "")
                res["kind"] = ("used" if "ESIM_SUCCESS" in text else
                               "pay" if ("DOCS_GENERATED" in text or "пора оплатить" in text.lower()) else "unknown")
        self._lc = {"running": False, "done": 0, "total": 0, "started": 0.0, "finished": 0.0, "rendered": True}
        self._lc_lock = threading.Lock()

    # ----------------------------------------------------------------- low level
    def _cfg(self):
        try:
            return self.app.load_telegram_config()
        except Exception:
            return {}

    def _chat(self):
        return str(self._cfg().get("chat_id") or "").strip()

    def _api(self, method, payload):
        try:
            return self.app.telegram_api(self._cfg(), method, payload)
        except Exception as exc:
            return None, f"{type(exc).__name__}: {exc}"

    def _save(self):
        try:
            _write_json(self.base / STATE_FILE, self.state)
        except Exception:
            pass

    def _save_marks(self):
        try:
            _write_json(self.base / ESIM_STATUS_FILE, self.marks)
        except Exception:
            pass

    # ----------------------------------------------------------------- panel I/O
    def _panel_alive(self):
        mid = self.state.get("message_id")
        sent = float(self.state.get("sent_at") or 0)
        return bool(mid) and _now() - sent < PANEL_MAX_AGE_SECONDS

    def _delete_panel(self):
        mid = self.state.get("message_id")
        if mid:
            self._api("deleteMessage", {"chat_id": self._chat(), "message_id": mid})
        self.state["message_id"] = None
        self._save()

    def _send_panel(self, text, markup):
        chat = self._chat()
        payload = {"chat_id": chat, "text": _clip(text), "disable_web_page_preview": "true", "parse_mode": "HTML"}
        if not self.state.get("keyboard_removed"):
            # The old bottom keyboard goes away with this message; the inline keyboard is
            # attached right after (one reply_markup per message).
            payload["reply_markup"] = json.dumps({"remove_keyboard": True})
            r, err = self._api("sendMessage", payload)
            if r:
                mid = (r.get("result") or {}).get("message_id")
                self.state.update({"message_id": mid, "sent_at": _now(), "keyboard_removed": True})
                self._save()
                self._api("editMessageReplyMarkup", {"chat_id": chat, "message_id": mid, "reply_markup": markup})
            return r, err
        payload["reply_markup"] = markup
        r, err = self._api("sendMessage", payload)
        if r:
            self.state.update({"message_id": (r.get("result") or {}).get("message_id"), "sent_at": _now()})
            self._save()
        return r, err

    def _show(self, text, markup, fresh=False):
        """Edit the panel in place; send a new one when there is none, it is too old, or
        the caller wants the panel at the bottom of the chat."""
        if fresh or not self._panel_alive():
            self._delete_panel()
            return self._send_panel(text, markup)
        r, err = self._api("editMessageText", {
            "chat_id": self._chat(), "message_id": self.state.get("message_id"),
            "text": _clip(text), "reply_markup": markup, "disable_web_page_preview": "true", "parse_mode": "HTML",
        })
        if r:
            return r, None
        low = str(err or "").lower()
        if "not modified" in low:
            return {"ok": True}, None
        if "not found" in low or "can't be edited" in low or "message_id_invalid" in low or "message to edit" in low:
            self.state["message_id"] = None
            return self._send_panel(text, markup)
        return None, err

    def _answer(self, cb, text=None):
        payload = {"callback_query_id": str(cb.get("id") or "")}
        if text:
            payload["text"] = str(text)[:190]
        self._api("answerCallbackQuery", payload)

    # ----------------------------------------------------------------- views
    def _header(self):
        try:
            running = self.proc.status()
        except Exception:
            running = "❔"
        base = _count_lines(self.base / "clients.txt")
        done = _count_lines(self.base / "processed_numbers.txt")
        fresh = sum(1 for rec in self._esims() if self._mark_of(rec) == "new")
        today = time.strftime("%Y-%m-%d")  # MENU_DELETE_1591R57: eSIMs made today, deleted ones included
        made_today = sum(1 for rec in self._esims(include_hidden=True) if str(rec.get("time") or "").startswith(today))
        lines = [
            "🎛 <b>beeline eSIM — панель</b>",
            "",
            f"⚙️ Процесс: {_esc(running)}",
            f"📂 База: {base} строк · обработано {done}",
            f"🆕 eSIM без отметки: {fresh}",
            f"📅 Новых eSIM за сегодня: {made_today}",
        ]
        return "\n".join(lines)

    def _menu_markup(self):
        return _kb([
            [_btn("📊 Статус", "m|status"), _btn("📱 Мои eSIM", "m|esims|0")],
            [_btn("📜 Логи", "m|logs|0"), _btn("🤖 Спросить DeepSeek", "m|ask")],
            [_btn("▶️ Запустить", "m|start"), _btn("⏹ Остановить", "m|stop")],
            [_btn("🔄 Перезапуск", "m|restart"), _btn("📥 Загрузить базу", "m|upload")],
        ])

    def show_menu(self, fresh=False, note=""):
        self.state["view"] = "menu"
        self.state["awaiting_ai"] = False
        self._save()
        text = self._header() + (f"\n\n{_esc(note)}" if note else "")
        return self._show(text, self._menu_markup(), fresh=fresh)

    # status ------------------------------------------------------------------
    def _snapshot(self):
        return _read_json(self.base / STATUS_SNAPSHOT_FILE, {})

    def _status_text(self):
        snap = self._snapshot()
        tabs = snap.get("tabs") or {}
        try:
            running = self.proc.running()
        except Exception:
            running = False
        lines = ["📊 <b>Статус вкладок</b>"]
        if not running:
            lines.append("\n🔴 Процесс остановлен.")
        elif not tabs:
            lines.append("\n⏳ Вкладки ещё не отчитались.")
        for key in sorted(tabs, key=lambda k: int(k) if str(k).isdigit() else 0):
            info = tabs.get(key) or {}
            text = str(info.get("text") or "").strip()
            age = int(_now() - float(info.get("time") or _now()))
            body = text.split("\n")
            head = body[0] if body else f"Вкладка {key}"
            rest = [x for x in body[1:] if x.strip()]
            lines.append("")
            lines.append(f"<b>{_esc(head)}</b>" + (f"  <i>{age // 60} мин назад</i>" if age >= 120 else ""))
            lines.extend("  " + _esc(x) for x in rest[:6])
        updated = float(snap.get("updated") or 0)
        if updated:
            lines.append("")
            lines.append(f"🕒 снимок {time.strftime('%H:%M:%S', time.localtime(updated))}, обновляется пока открыт")
        return "\n".join(lines)

    def show_status(self):
        self.state["view"] = "status"
        self.state["status_since"] = _now()
        self._save()
        text = self._status_text()
        self._status_last_text = text
        self._status_last_edit = _now()
        return self._show(text, _kb([[_btn("🔄 Обновить", "m|status"), _btn("◀️ Меню", "m|menu")]]))

    def tick(self):
        """Live refresh of the open status view; nothing else is ever edited unasked."""
        if self.state.get("view") == "linkcheck":  # LINK_CHECK_1591R58: progress while it runs, the result once
            with self._lc_lock:
                due = self._lc["running"] or not self._lc["rendered"]
            if due and _now() - self._status_last_edit >= STATUS_REFRESH_SECONDS:
                self.show_link_check()
                return True
            return False
        if self.state.get("view") != "status":
            return False
        if _now() - float(self.state.get("status_since") or 0) > STATUS_AUTO_CLOSE_SECONDS:
            self.show_menu(note="📊 Статус закрыт автоматически через час; открой снова при необходимости.")
            return True
        if _now() - self._status_last_edit < STATUS_REFRESH_SECONDS:
            return False
        text = self._status_text()
        self._status_last_edit = _now()
        if text == self._status_last_text:
            return False
        self._status_last_text = text
        self._show(text, _kb([[_btn("🔄 Обновить", "m|status"), _btn("◀️ Меню", "m|menu")]]))
        return True

    # eSIMs -------------------------------------------------------------------
    def _esims(self, include_hidden=False):
        """Newest first: payment-step and signed records as the runtime wrote them (deleted ones only
        with include_hidden)."""
        out = []
        for name, kind in (("payment_required.jsonl", "payment"), ("successful_sims.jsonl", "success")):
            try:
                lines = (self.base / name).read_text("utf-8", errors="replace").splitlines()
            except Exception:
                continue
            for index, line in enumerate(lines):
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                rec = dict(rec)
                rec["_kind"] = kind
                rec["_key"] = f"{kind[0]}{index}"
                rec["_order"] = (str(rec.get("time") or ""), index)
                if not include_hidden and self.marks.get(self._mark_key(rec)) == HIDDEN_MARK:
                    continue
                out.append(rec)
        out.sort(key=lambda r: r["_order"], reverse=True)
        return out

    def _esim_by_key(self, key):
        for rec in self._esims():
            if rec["_key"] == key:
                return rec
        return None

    def _mark_key(self, rec):
        return f"{rec.get('row')}:{_digits(rec.get('sim_number')) or _digits(rec.get('active_digits'))}"

    def _mark_of(self, rec):
        mark = str(self.marks.get(self._mark_key(rec)) or "new")
        return mark if mark in MARKS else "new"

    def show_esims(self, page=0, note=""):
        recs = self._esims()
        pages = max(1, (len(recs) + ESIMS_PER_PAGE - 1) // ESIMS_PER_PAGE)
        page = max(0, min(int(page), pages - 1))
        chunk = recs[page * ESIMS_PER_PAGE:(page + 1) * ESIMS_PER_PAGE]
        self.state.update({"view": "esims", "page": page})
        self._save()
        counts = {"new": 0, "ok": 0, "bad": 0}
        for rec in recs:
            counts[self._mark_of(rec)] = counts.get(self._mark_of(rec), 0) + 1
        text = (f"📱 <b>Мои eSIM</b> — {len(recs)} шт.\n"
                f"🆕 {counts['new']} · ✅ {counts['ok']} · ❌ {counts['bad']}\n\n"
                "Нажми на номер, чтобы открыть карточку и поставить отметку.")
        if not recs:
            text = "📱 <b>Мои eSIM</b>\n\nСписок пуст."
        if note:
            text += f"\n\n{_esc(note)}"
        rows = []
        for rec in chunk:
            icon = MARKS[self._mark_of(rec)]
            label = f"{icon} {pretty_phone(rec.get('sim_number') or rec.get('active_digits'))}"
            when = _when(rec.get("time"))
            if when:
                label += f" · 🕒 {when}"
            checked = self.link_results.get(self._mark_key(rec)) or {}
            if checked.get("kind") in LINK_ICONS:  # LINK_CHECK_1591R58
                label += f" · 🔗{LINK_ICONS[checked['kind']]}"
            rows.append([_btn(label, f"m|esim|{rec['_key']}|{page}")])
        nav = []
        if page > 0:
            nav.append(_btn("◀️", f"m|esims|{page - 1}"))
        nav.append(_btn(f"{page + 1}/{pages}", "m|noop"))
        if page < pages - 1:
            nav.append(_btn("▶️", f"m|esims|{page + 1}"))
        rows.append(nav)
        if recs:  # LINK_CHECK_1591R58
            rows.append([_btn("🔗 Проверить ссылки", "m|lcheck|start")])
        if recs:  # MENU_DELETE_1591R57; R58: «удалить ✅ и ❌» asks first, as «удалить все» does
            rows.append([_btn("🗑 Удалить ✅ и ❌", f"m|delmarked|ask|{page}"), _btn("🗑 Удалить все", f"m|delall|ask|{page}")])
        hidden = self._hidden_count()
        if hidden:
            rows.append([_btn(f"↩️ Вернуть удалённые ({hidden})", f"m|restore|{page}")])
        rows.append([_btn("🏠 Меню", "m|menu")])
        return self._show(text, _kb(rows))

    # MENU_DELETE_1591R57 -------------------------------------------------------
    def _hide(self, recs):
        for rec in recs:
            self.marks[self._mark_key(rec)] = HIDDEN_MARK
        if recs:
            self._save_marks()
        return len(recs)

    def delete_esim(self, key, page=0):
        rec = self._esim_by_key(key)
        if rec is None:
            return self.show_esims(page)
        self._hide([rec])
        return self.show_esims(page, note=f"🗑 Удалено из списка: {pretty_phone(rec.get('sim_number') or rec.get('active_digits'))}")

    def delete_marked(self, step="ask", page=0):
        marked = [rec for rec in self._esims() if self._mark_of(rec) in ("ok", "bad")]
        if step != "yes":  # MENU_SAFE_DELETE_1591R58: an old panel's «m|delmarked|<page>» only asks too
            self.state.update({"view": "esims", "page": int(page) if str(page).isdigit() else 0})
            self._save()
            return self._show(
                f"🗑 <b>Удалить из списка {len(marked)} eSIM с отметкой ✅ или ❌?</b>\n\n"
                "Файлы с результатами на сервере останутся; вернуть можно кнопкой «↩️ Вернуть удалённые».",
                _kb([[_btn("🗑 Да, удалить", f"m|delmarked|yes|{page}"), _btn("✖️ Отмена", f"m|esims|{page}")]]),
            )
        n = self._hide(marked)
        return self.show_esims(page, note=f"🗑 Удалено из списка отмеченных ✅/❌: {n}")

    def _hidden_count(self):
        return sum(1 for value in self.marks.values() if value == HIDDEN_MARK)

    def restore_hidden(self, page=0):
        """MENU_SAFE_DELETE_1591R58: every deleted eSIM back to the list (as 🆕: the old mark is gone)."""
        keys = [k for k, v in self.marks.items() if v == HIDDEN_MARK]
        for key in keys:
            self.marks.pop(key, None)
        if keys:
            self._save_marks()
        return self.show_esims(page, note=f"↩️ Возвращено в список: {len(keys)}")

    # LINK_CHECK_1591R58 --------------------------------------------------------
    def _link_targets(self):
        out = []
        for rec in self._esims():
            url = str(rec.get("sim_url") or "").strip()
            if url.startswith("http"):
                out.append((self._mark_key(rec), url, rec))
        return out

    def start_link_check(self):
        with self._lc_lock:
            if self._lc["running"]:
                return False
            targets = self._link_targets()
            self._lc.update({"running": True, "done": 0, "total": len(targets), "started": _now(),
                             "finished": 0.0, "rendered": False})
        print(f"[MENU] Проверка ссылок: {len(targets)} шт.", flush=True)
        threading.Thread(target=self._run_link_check, args=(targets,), name="link-check", daemon=True).start()
        return True

    def _run_link_check(self, targets):
        by_url = {}
        for key, url, rec in targets:
            by_url.setdefault(url, []).append(key)
        try:
            for url, result in self.link_checker([u for u in by_url]):
                stamp = time.strftime("%Y-%m-%d %H:%M")
                for key in by_url.get(url, []):
                    self.link_results[key] = dict(result, time=stamp, url=url)
                with self._lc_lock:
                    self._lc["done"] += len(by_url.get(url, []))
                try:
                    _write_json(self.base / LINK_CHECK_FILE, self.link_results)
                except Exception:
                    pass
        except Exception as exc:
            print(f"[MENU] Проверка ссылок прервана: {type(exc).__name__}: {exc}", flush=True)
        finally:
            with self._lc_lock:
                self._lc.update({"running": False, "finished": _now(), "rendered": False})
            print(f"[MENU] Проверка ссылок закончена: {self._lc['done']} из {self._lc['total']}", flush=True)

    def _link_check_text(self):
        with self._lc_lock:
            lc = dict(self._lc)
        targets = self._link_targets()
        lines = ["🔗 <b>Проверка ссылок заказов</b>", ""]
        if lc["running"]:
            lines.append(f"⏳ Проверяю: {lc['done']} из {lc['total']}… страница обновится сама.")
        counts, problems = {}, []
        for key, url, rec in targets:
            res = self.link_results.get(key) or {}
            kind = res.get("kind")
            if kind not in LINK_ICONS:
                continue
            counts[kind] = counts.get(kind, 0) + 1
            if kind in ("dead", "unknown", "error"):
                problems.append(f"{LINK_ICONS[kind]} {pretty_phone(rec.get('sim_number') or rec.get('active_digits'))}"
                                f" · стр. {rec.get('row', '?')}: {_esc(res.get('text') or '')}")
        if not counts and not lc["running"]:
            lines.append("Ещё не проверялись. Нажми «🔗 Проверить».")
        for kind in ("dead", "pay", "ok", "used", "unknown", "error"):
            if counts.get(kind):
                lines.append(f"{LINK_ICONS[kind]} {LINK_TITLES[kind]}: {counts[kind]}")
        no_link = len(self._esims()) - len(targets)
        if no_link:
            lines.append(f"➖ без ссылки: {no_link}")
        if problems:
            lines.append("")
            lines.extend(problems[:25])
            if len(problems) > 25:
                lines.append(f"… и ещё {len(problems) - 25}")
        stamp = max((str((self.link_results.get(k) or {}).get("time") or "") for k, _, _ in targets), default="")
        if stamp and not lc["running"]:
            lines.append("")
            lines.append(f"🕒 проверено {_when(stamp + ':00') or stamp}")
        return "\n".join(lines)

    def show_link_check(self):
        self.state["view"] = "linkcheck"
        self._save()
        text = self._link_check_text()
        self._status_last_edit = _now()
        with self._lc_lock:
            if not self._lc["running"]:
                self._lc["rendered"] = True
            running = self._lc["running"]
        rows = [] if running else [[_btn("🔗 Проверить снова", "m|lcheck|start")]]
        rows.append([_btn("◀️ Список", "m|esims|0"), _btn("🏠 Меню", "m|menu")])
        return self._show(text, _kb(rows))

    def delete_all(self, step, page=0):
        recs = self._esims()
        if step != "yes":
            self.state.update({"view": "esims", "page": int(page)})
            self._save()
            return self._show(
                f"🗑 <b>Удалить из списка все {len(recs)} eSIM?</b>\n\n"
                "Файлы с результатами на сервере останутся; удаляется только показ в «Мои eSIM».",
                _kb([[_btn("🗑 Да, удалить", f"m|delall|yes|{page}"), _btn("✖️ Отмена", f"m|esims|{page}")]]),
            )
        n = self._hide(recs)
        return self.show_esims(0, note=f"🗑 Удалено из списка: {n}")

    def _esim_text(self, rec):
        profile = rec.get("profile") or {}
        kind = rec["_kind"]
        mark = self._mark_of(rec)
        head = "💳 Требуется оплата eSIM" if kind == "payment" else "✅ Договор оформлен"
        lines = [
            f"{MARKS[mark]} <b>{head}</b> · отметка: {MARK_TITLES[mark]}",
            f"📱 eSIM: <b>{pretty_phone(rec.get('sim_number'))}</b>",
            f"📄 Строка {rec.get('row', '?')} · вкладка {rec.get('tab', '?')}"
            + (f" · {str(rec.get('time'))[5:16]}" if rec.get("time") else ""),
            f"🔢 Исходные данные: {_esc(rec.get('active_digits') or '—')} | {_esc(rec.get('second_value') or '—')}",
            "",
        ]
        fields = getattr(self.app, "SUCCESS_PROFILE_FIELDS", None) or []
        for key, label in fields:
            lines.append(f"{_esc(label)}: {_esc(profile.get(key) or '—')}")
        lines.append("")
        if rec.get("sim_url"):
            lines.append(f"🔗 Ссылка заказа: {_esc(rec['sim_url'])}")
        if rec.get("payment_text"):
            lines.append(f"💬 Шаг сайта: {_esc(str(rec['payment_text'])[:200])}")
        if rec.get("final_url"):
            lines.append(f"🌐 Страница: {_esc(rec['final_url'])}")
        checked = self.link_results.get(self._mark_key(rec)) or {}
        if checked.get("kind") in LINK_ICONS:  # LINK_CHECK_1591R58
            lines.append(f"🔗 Проверка ссылки: {LINK_ICONS[checked['kind']]} {LINK_TITLES[checked['kind']]}"
                         f" · {_esc(checked.get('time') or '')}" + (f"\n   {_esc(checked.get('text'))}" if checked.get("text") else ""))
        trace_lines = getattr(self.app, "_sign_trace_lines_1591r25", None)
        if trace_lines and rec.get("sign_trace"):
            try:
                lines.extend(_esc(x) for x in trace_lines(rec["sign_trace"])[:4])
            except Exception:
                pass
        return "\n".join(lines)

    def show_esim(self, key, page=0, note=""):
        rec = self._esim_by_key(key)
        if rec is None:
            return self.show_esims(page)
        self.state.update({"view": "esim", "key": key, "page": int(page)})
        self._save()
        text = self._esim_text(rec) + (f"\n\n{_esc(note)}" if note else "")
        rows = [
            [_btn("✅ Оформлена", f"m|set|{key}|ok|{page}"), _btn("❌ Брак", f"m|set|{key}|bad|{page}"),
             _btn("🆕 Сброс", f"m|set|{key}|new|{page}")],
        ]
        if self.link_resolver is not None:
            rows.append([_btn("🔎 Ссылка из журнала", f"m|link|{key}|{page}")])
        rows.append([_btn("🗑 Удалить из списка", f"m|del|{key}|{page}")])  # MENU_DELETE_1591R57
        rows.append([_btn("◀️ Список", f"m|esims|{page}"), _btn("🏠 Меню", "m|menu")])
        return self._show(text, _kb(rows))

    def set_mark(self, key, mark, page=0):
        rec = self._esim_by_key(key)
        if rec is None or mark not in MARKS:
            return self.show_esims(page)
        self.marks[self._mark_key(rec)] = mark
        self._save_marks()
        return self.show_esim(key, page, note=f"Отметка: {MARKS[mark]} {MARK_TITLES[mark]}")

    # logs --------------------------------------------------------------------
    def _events(self):
        cached_at, events = self._logs_cache
        if _now() - cached_at < LOGS_CACHE_SECONDS:
            return events
        try:
            log = subprocess.run(
                ["journalctl", "-u", "beeline", "--no-pager", "-o", "short-iso", "--since", "-2 days"],
                capture_output=True, text=True, timeout=60,
            ).stdout
        except Exception as exc:
            log = ""
            events = [(time.strftime("%Y-%m-%d %H:%M"), "⚠️", f"журнал недоступен: {type(exc).__name__}")]
        else:
            events = []
            for line in log.splitlines():
                m = _JOURNAL_LINE.match(line)
                if not m:
                    continue
                msg = m.group("msg").strip()
                for pattern, icon in LOG_PATTERNS:
                    if pattern.search(msg):
                        ts = m.group("ts")[:16].replace("T", " ")
                        msg = re.sub(r"^\[Вкладка (\d+)\]\s*", r"вкл.\1: ", msg)
                        events.append((ts, icon, msg[:140]))
                        break
            events.reverse()
        self._logs_cache = (_now(), events)
        return events

    def show_logs(self, page=0):
        events = self._events()
        pages = max(1, (len(events) + LOGS_PER_PAGE - 1) // LOGS_PER_PAGE)
        page = max(0, min(int(page), pages - 1))
        chunk = events[page * LOGS_PER_PAGE:(page + 1) * LOGS_PER_PAGE]
        self.state.update({"view": "logs", "page": page})
        self._save()
        lines = [f"📜 <b>Логи</b> — {len(events)} событий за 2 дня, стр. {page + 1}/{pages}", ""]
        day = ""
        for ts, icon, msg in chunk:
            if ts[:10] != day:
                day = ts[:10]
                lines.append(f"<i>{day}</i>")
            lines.append(f"{ts[11:16]} {icon} {_esc(msg)}")
        if not chunk:
            lines.append("Событий нет.")
        nav = []
        if page > 0:
            nav.append(_btn("◀️", f"m|logs|{page - 1}"))
        nav.append(_btn("🔄", f"m|logs|{page}"))
        if page < pages - 1:
            nav.append(_btn("▶️", f"m|logs|{page + 1}"))
        return self._show("\n".join(lines), _kb([nav, [_btn("🏠 Меню", "m|menu")]]))

    # DeepSeek ----------------------------------------------------------------
    def show_ask(self):
        self.state.update({"view": "ask", "awaiting_ai": True})
        self._save()
        text = ("🤖 <b>Вопрос DeepSeek</b>\n\n"
                "Напиши следующим сообщением, что спросить или поручить DeepSeek.\n"
                "Обычные сообщения в чате к нему больше не попадают — только через эту кнопку.")
        return self._show(text, _kb([[_btn("✖️ Отмена", "m|ask_cancel")]]))

    def text_is_for_ai(self):
        """True once: the next text after «Спросить DeepSeek» goes to the AI inbox."""
        if not self.state.get("awaiting_ai"):
            return False
        self.state["awaiting_ai"] = False
        self._save()
        return True

    def ai_sent(self):
        return self.show_menu(note="📨 Отправлено DeepSeek. Ответ придёт отдельным сообщением.")

    @staticmethod
    def _log_press(cb, data):
        """MENU_SAFE_DELETE_1591R58: who pressed a deleting button goes to the journal."""
        who = cb.get("from") or {}
        name = " ".join(str(who.get(k) or "") for k in ("first_name", "last_name")).strip()
        user = f"@{who['username']}" if who.get("username") else ""
        print(f"[MENU] {name or '?'} {user} (id {who.get('id', '?')}) нажал {data}", flush=True)

    # ----------------------------------------------------------------- routing
    def handle_callback(self, cb):
        """Act on an inline button. Returns "upload" when the controller must expect a
        document next, otherwise None. Always answers the callback."""
        data = str(cb.get("data") or "")
        parts = data.split("|")
        if len(parts) < 2 or parts[0] != "m":
            self._answer(cb)
            return None
        action, args = parts[1], parts[2:]
        try:
            if action == "menu":
                self.show_menu()
            elif action == "status":
                self.show_status()
            elif action == "esims":
                self.show_esims(args[0] if args else 0)
            elif action == "esim":
                self.show_esim(args[0], args[1] if len(args) > 1 else 0)
            elif action == "set":
                self.set_mark(args[0], args[1], args[2] if len(args) > 2 else 0)
            elif action == "del":  # MENU_DELETE_1591R57
                self._log_press(cb, data)
                self.delete_esim(args[0], args[1] if len(args) > 1 else 0)
            elif action == "delmarked":  # MENU_SAFE_DELETE_1591R58: «ask» unless the confirmation says «yes»
                step = args[0] if args and args[0] in ("ask", "yes") else "ask"
                page = args[1] if step in ("ask", "yes") and len(args) > 1 else (args[0] if args and args[0].isdigit() else 0)
                if step == "yes":
                    self._log_press(cb, data)
                self.delete_marked(step, page)
            elif action == "delall":
                if args and args[0] == "yes":
                    self._log_press(cb, data)
                self.delete_all(args[0] if args else "ask", args[1] if len(args) > 1 else 0)
            elif action == "restore":
                self._log_press(cb, data)
                self.restore_hidden(args[0] if args else 0)
            elif action == "lcheck":  # LINK_CHECK_1591R58
                if args and args[0] == "start":
                    self.start_link_check()
                self.show_link_check()
            elif action == "link":
                rec = self._esim_by_key(args[0])
                note = ""
                if rec is not None and self.link_resolver is not None:
                    try:
                        note = "🔎 " + str(self.link_resolver(str(rec.get("row") or "")))[:1200]
                    except Exception as exc:
                        note = f"🔎 журнал недоступен: {type(exc).__name__}"
                self.show_esim(args[0], args[1] if len(args) > 1 else 0, note=note)
            elif action == "logs":
                self.show_logs(args[0] if args else 0)
            elif action == "ask":
                self.show_ask()
            elif action == "ask_cancel":
                self.show_menu(note="✖️ Вопрос DeepSeek отменён.")
            elif action == "start":
                _, answer = self.proc.start()
                self.show_menu(note=answer)
            elif action == "stop":
                _, answer = self.proc.stop()
                self.show_menu(note=answer)
            elif action == "restart":
                _, answer = self.proc.restart()
                self.show_menu(note="🔄 " + str(answer))
            elif action == "upload":
                self.state["view"] = "upload"
                self._save()
                self._show(
                    "📥 <b>Новая база номеров</b>\n\nПришли следующим сообщением .txt файл.\n"
                    "Текущая база заменится только после проверки; работающий процесс перезапустится сам.",
                    _kb([[_btn("✖️ Отмена", "m|menu")]]),
                )
                self._answer(cb)
                return "upload"
            else:
                self._answer(cb)
                return None
        except Exception as exc:
            self._answer(cb, f"Ошибка: {type(exc).__name__}")
            return None
        self._answer(cb)
        return None

    def retire_status_messages(self, status_file):
        """One-time: the eight status messages of earlier revisions point to the menu."""
        path = Path(status_file)
        data = _read_json(path, None)
        if not data:
            return 0
        mids = (data.get("mids") or {}) if isinstance(data, dict) else {}
        chat = self._chat()
        done = 0
        for mid in list(mids.values())[:8]:
            r, _ = self._api("editMessageText", {
                "chat_id": chat, "message_id": mid,
                "text": "📊 Статус вкладок теперь в меню бота: напиши любое сообщение или /start.",
            })
            done += 1 if r else 0
            time.sleep(1.5)
        try:
            path.unlink()
        except OSError:
            pass
        return done

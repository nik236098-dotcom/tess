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
import signal
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
LINK_ICONS = {"dead": "⛔", "pay": "💳", "ok": "✅", "used": "✅", "unknown": "❔", "error": "⚠️"}  # R60: the status icons
LINK_TITLES = {"dead": "не работает", "pay": "ждёт оплаты", "ok": "оплачена / готова", "used": "eSIM уже выпущена",
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
    site_kind = _SITE_STATUS_KINDS.get(str(site_status or "").split("=", 1)[-1].strip().upper())
    if site_kind == "used":  # ESIM_ISSUED_1591R62: an issued eSIM is ✅ even on an /error page or a 4xx
        return site_kind, text(hint)
    if status >= 400 or "/error" in str(final_url or "").lower() or site_error:
        return "dead", text(hint or f"HTTP {status}")
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


# BOT_TOOLS_1591R60: one status per eSIM (🆕 новая, 💳 ждёт оплаты, ✅ готово, ⛔ ссылка не работает, ❌ брак;
# a manual ✅/❌ wins over the link check) and a manual 🏦 flag after it («💳 • 🏦»); export of the 💳 ones
# (🟢 normal: one message per eSIM with 🔼/🔽 and ✅ 🏦 ↩️; ‼️ urgent: number + link lists; or a .txt), status
# refresh with a report, /recheck, ⚙️ settings, 🖥 server, ⬆️ self-update and a notice after a reboot or crash.
STATUS_ICONS = {"new": "🆕", "pay": "💳", "done": "✅", "dead": "⛔", "bad": "❌"}
STATUS_TITLES = {"new": "новая", "pay": "ждёт оплаты", "done": "готово", "dead": "ссылка не работает", "bad": "брак"}
BANK_ICON = "🏦"
BANK_FILE = "esim_bank.json"
EXPORTS_FILE = "esim_exports.json"
EXPORT_SEND_GAP_SECONDS = 1.1          # Telegram: about one message a second in one chat
MSG_LIMIT = 3900
ALIVE_FILE = "bot_alive.json"
CLEAN_STOP_FILE = "bot_clean_stop.flag"
SELF_UPDATE_FILE = "self_update.json"
SELF_UPDATE_LOG = "self_update.log"
SELF_UPDATE_TIMEOUT_SECONDS = 20 * 60
ALIVE_EVERY_SECONDS = 60
UPDATE_CHECK_SECONDS = 6 * 3600
UPDATE_URL = ("https://raw.githubusercontent.com/nik236098-dotcom/tess/codex/operator-observer-15.87/"
              "operator_repair_1591/update.sh")
REPO_API = ("https://api.github.com/repos/nik236098-dotcom/tess/contents/operator_repair_1591"
            "?ref=codex/operator-observer-15.87")
MENU_DROPIN = "/etc/systemd/system/beeline.service.d/zz-menu.conf"
TARIFF_CHOICES = {
    "watch": ("для смарт часов", {"BEELINE_TARIFF": "для смарт часов", "BEELINE_TARIFF_PRICE": "200", "BEELINE_TARIFF_MINIMAL": "0"}),
    "start": ("подписка bee START", {"BEELINE_TARIFF": "подписка bee START", "BEELINE_TARIFF_PRICE": "", "BEELINE_TARIFF_MINIMAL": "0"}),
    "hit": ("подписка bee HIT", {"BEELINE_TARIFF": "подписка bee HIT", "BEELINE_TARIFF_PRICE": "", "BEELINE_TARIFF_MINIMAL": "0"}),
}
RESTART_CHOICES = ((0, "выкл"), (360, "6 ч"), (720, "12 ч"), (1440, "24 ч"))


# ESIM_ISSUED_1591R62: selfregStatus ESIM_SUCCESS is an eSIM already issued: ✅ «eSIM уже выпущена», also when the
# page lands on /error or answers 4xx («срок установки eSIM истёк»); saved ⛔ results of it are corrected at start.
# EXPORT_CARDS_1591R61: «Мои eSIM» as in r59 (🕒 date and time, counters, the full card) with the status
# icons, «готово» is ✅; the 🟢 export message is the push card; «🔄 Обновить» re-sends the waiting ones
# the way the export gave them.


def _period(seconds):
    seconds = int(seconds or 0)
    if seconds and seconds % 86400 == 0:
        days = seconds // 86400
        return f"{days} д"
    hours = seconds // 3600
    return f"{hours} ч" if hours else f"{seconds // 60} мин"


def _setting_desc(name, value):
    if name == "tariff" and value in TARIFF_CHOICES:
        return f"тариф «{TARIFF_CHOICES[value][0]}»"
    if name in ("browsers", "tabs") and str(value).isdigit() and 1 <= int(value) <= 8:
        return f"{'браузеров' if name == 'browsers' else 'вкладок в каждом браузере'}: {int(value)}"
    if name == "ai" and value in ("0", "1"):
        return "DeepSeek " + ("включён" if value == "1" else "выключен")
    return ""


def _setting_env(name, value):
    if not _setting_desc(name, value):
        return {}
    if name == "tariff":
        return dict(TARIFF_CHOICES[value][1])
    if name == "browsers":
        return {"BEELINE_BROWSERS": str(int(value))}
    if name == "tabs":
        return {"BEELINE_TABS_PER_BROWSER": str(int(value))}
    return {"BEELINE_AI": value}


def _read_dropin(path):
    out = {}
    try:
        text = Path(path).read_text("utf-8")
    except Exception:
        return out
    for m in re.finditer(r'^Environment="?([A-Z0-9_]+)=([^"\n]*)"?\s*$', text, re.M):
        out[m.group(1)] = m.group(2)
    return out


def _boot_id():
    try:
        return Path("/proc/sys/kernel/random/boot_id").read_text().strip()
    except Exception:
        return ""


def _fetch_latest_revision():
    """The newest beeline_integrated_io_15_91_rNN folder of the branch on GitHub, 0 when unknown."""
    import urllib.request
    req = urllib.request.Request(REPO_API, headers={"User-Agent": "beeline-bot", "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        items = json.loads(resp.read().decode("utf-8"))
    revs = [int(m.group(1)) for it in items
            for m in [re.fullmatch(r"beeline_integrated_io_15_91_r(\d+)(?:_lite|_exp8)?", str(it.get("name") or ""))] if m]
    return max(revs) if revs else 0


def _gb(value_kb):
    return f"{value_kb / 1024 / 1024:.1f}"


def _server_lines(base, started_at=0.0):
    lines = []
    try:
        up = float(Path("/proc/uptime").read_text().split()[0])
        boot = time.strftime("%d.%m %H:%M", time.localtime(_now() - up))
        lines.append(f"⏱ Сервер работает: {_period(int(up // 3600) * 3600) if up >= 3600 else str(int(up // 60)) + ' мин'}"
                     f" (включён {boot})")
    except Exception:
        pass
    if started_at:
        lines.append(f"🤖 Бот запущен: {time.strftime('%d.%m %H:%M', time.localtime(started_at))}")
    try:
        load = os.getloadavg()
        lines.append(f"📈 Нагрузка: {load[0]:.1f} / {load[1]:.1f} / {load[2]:.1f} (ядер {os.cpu_count()})")
    except Exception:
        pass
    try:
        info = {}
        for line in Path("/proc/meminfo").read_text().splitlines():
            key, _, rest = line.partition(":")
            info[key] = int(rest.split()[0])
        total, avail = info.get("MemTotal", 0), info.get("MemAvailable", 0)
        lines.append(f"🧠 Память: занято {_gb(total - avail)} из {_gb(total)} ГБ")
        if info.get("SwapTotal"):
            lines.append(f"💾 Своп: занято {_gb(info['SwapTotal'] - info.get('SwapFree', 0))} из {_gb(info['SwapTotal'])} ГБ")
    except Exception:
        pass
    try:
        import shutil
        du = shutil.disk_usage(str(base))
        lines.append(f"🗄 Диск: занято {du.used / 1e9:.0f} из {du.total / 1e9:.0f} ГБ")
    except Exception:
        pass
    try:
        chromium = sum(1 for p in Path("/proc").iterdir() if p.name.isdigit()
                       and "chrom" in (p / "comm").read_text(errors="ignore"))
        lines.append(f"🌐 Процессов Chromium: {chromium}")
    except Exception:
        pass
    return lines


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
            if res.get("kind") == "dead" and "selfregStatus=ESIM_SUCCESS" in text:  # ESIM_ISSUED_1591R62
                res["kind"] = "used"
        self._lc = {"running": False, "done": 0, "total": 0, "started": 0.0, "finished": 0.0, "rendered": True}
        self._lc_lock = threading.Lock()
        self.bank = _read_json(self.base / BANK_FILE, {})  # BOT_TOOLS_1591R60: the manual 🏦 flag
        self.runner = lambda cmd: subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=60)
        self._started_at = 0.0
        self._alive_at = 0.0
        self._rev_thread = None

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
        statuses = [self._status_of(rec) for rec in self._esims()]  # BOT_TOOLS_1591R60
        today = time.strftime("%Y-%m-%d")  # MENU_DELETE_1591R57: eSIMs made today, deleted ones included
        made_today = sum(1 for rec in self._esims(include_hidden=True) if str(rec.get("time") or "").startswith(today))
        icon, _, word = str(running).partition(" ")  # EXPORT_CARDS_1591R61: «🔴 Процесс остановлен»
        process = f"{icon} Процесс {word[:1].lower()}{word[1:]}" if word else f"⚙️ Процесс: {running}"
        lines = [
            "🎛 <b>beeline eSIM — панель</b>",
            "",
            _esc(process),
            f"📂 База: {base} • Обработано: {done}",
            f"💳 Ждут оплаты: {statuses.count('pay')} • Готово: {statuses.count('done')}",
            f"📅 Новых eSIM сегодня: {made_today}",
        ]
        rev, _ = self._revision()
        latest = int(self.state.get("latest_rev") or 0)
        if latest > rev:
            lines.append(f"⬆️ Доступно обновление: r{rev} → r{latest}")
        return "\n".join(lines)

    def _menu_markup(self):
        rev, _ = self._revision()
        latest = int(self.state.get("latest_rev") or 0)
        return _kb([  # EXPORT_CARDS_1591R61: the layout the owner drew
            [_btn("📱 Мои eSIM", "m|esims|0")],
            [_btn("📤 Выгрузка", "m|exp"), _btn("📂 База", "m|base")],
            [_btn("🔢 Генерация", "m|gen")],
            [_btn("📜 Логи", "m|logs|0"), _btn("🖥 Сервер", "m|srv")],
            [_btn("⚙️ Настройки", "m|cfg"), _btn("🤖 Спросить DeepSeek", "m|ask")],
            [_btn("▶️ Запустить", "m|start"), _btn("⏹ Остановить", "m|stop")],
            [_btn("🔄 Перезапуск", "m|restart")],
            [_btn("📊 Статус", "m|status"), _btn("🔄 Обновить статус", "m|recheck")],
            [_btn("⬆️ Обновить бота" + (f" (r{latest})" if latest > rev else ""), "m|upd")],
        ])

    def show_menu(self, fresh=False, note=""):
        self.state["view"] = "menu"
        self.state["awaiting_ai"] = False
        self.state["awaiting_generation"] = False
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

    def _background(self):
        """BOT_TOOLS_1591R60: alive marker, /recheck schedule, self-update result, new-revision check."""
        if not self._started_at:
            return
        if _now() - self._alive_at >= ALIVE_EVERY_SECONDS:
            self._write_alive()
            if (self.base / SELF_UPDATE_FILE).exists():
                msg = self._update_result()
                if msg:
                    self._send_msg(_esc(msg))
        try:
            self._recheck_tick()
        except Exception as exc:
            print(f"[MENU] автопроверка: {type(exc).__name__}: {exc}", flush=True)
        due = _now() - float(self.state.get("latest_at") or 0) >= UPDATE_CHECK_SECONDS
        if due and (self._rev_thread is None or not self._rev_thread.is_alive()):
            self.state["latest_at"] = _now()
            self._rev_thread = threading.Thread(target=self._latest_revision, kwargs={"force": True},
                                                name="revision-check", daemon=True)
            self._rev_thread.start()

    def tick(self):
        """Live refresh of the open status view; nothing else is ever edited unasked."""
        self._background()
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

    # eSIMs (BOT_TOOLS_1591R60: one status per eSIM, 🏦 as a manual flag) ------
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

    def _status_of(self, rec):
        """🆕 / 💳 / ✅ / ⛔ / ❌: the manual mark wins, then the last link check, then the record kind."""
        key = self._mark_key(rec)
        mark = self.marks.get(key)
        if mark == "bad":
            return "bad"
        if mark == "ok":
            return "done"
        kind = (self.link_results.get(key) or {}).get("kind")
        if kind in ("ok", "used"):
            return "done"
        if kind == "dead":
            return "dead"
        if kind == "pay" or rec.get("_kind") == "payment":
            return "pay"
        return "new"

    def _bank_of(self, rec):
        return bool(self.bank.get(self._mark_key(rec)))

    def _label_of(self, rec):
        icon = STATUS_ICONS[self._status_of(rec)]
        return f"{icon} • {BANK_ICON}" if self._bank_of(rec) else icon

    def _save_bank(self):
        try:
            _write_json(self.base / BANK_FILE, self.bank)
        except Exception:
            pass

    def _phone(self, rec):
        return pretty_phone(rec.get("sim_number") or rec.get("active_digits"))

    def _filtered(self, flt=None):
        flt = flt or self.state.get("esim_filter") or "all"
        recs = self._esims()
        return [r for r in recs if self._status_of(r) == "pay"] if flt == "pay" else recs

    def show_esims(self, page=0, note=""):
        flt = self.state.get("esim_filter") or "all"
        everything = self._esims()
        recs = self._filtered(flt)
        pages = max(1, (len(recs) + ESIMS_PER_PAGE - 1) // ESIMS_PER_PAGE)
        page = max(0, min(int(page) if str(page).lstrip("-").isdigit() else 0, pages - 1))
        chunk = recs[page * ESIMS_PER_PAGE:(page + 1) * ESIMS_PER_PAGE]
        self.state.update({"view": "esims", "page": page})
        self._save()
        counts = {}
        for rec in everything:
            status = self._status_of(rec)
            counts[status] = counts.get(status, 0) + 1
        text = (f"📱 <b>Мои eSIM</b> — {len(everything)} шт.\n"
                + " · ".join(f"{STATUS_ICONS[st]} {counts.get(st, 0)}" for st in ("new", "pay", "done", "dead", "bad")
                             if counts.get(st) or st in ("new", "pay", "done"))
                + "\n\nНажми на номер, чтобы открыть карточку и поставить отметку.")
        if flt == "pay":
            text += f"\nПоказаны только 💳: {len(recs)}"
        if not recs:
            text = f"📱 <b>Мои eSIM</b>{' — показаны только 💳' if flt == 'pay' else ''}\n\nСписок пуст."
        if note:
            text += f"\n\n{_esc(note)}"
        rows = []
        for rec in chunk:
            label = f"{self._label_of(rec)} {self._phone(rec)}"
            when = _when(rec.get("time"))
            if when:
                label += f" · 🕒 {when}"
            rows.append([_btn(label, f"m|esim|{rec['_key']}|{page}")])
        nav = []
        if page > 0:
            nav.append(_btn("◀️", f"m|esims|{page - 1}"))
        nav.append(_btn(f"{page + 1}/{pages}", "m|noop"))
        if page < pages - 1:
            nav.append(_btn("▶️", f"m|esims|{page + 1}"))
        rows.append(nav)
        rows.append([_btn("Показать: Все" if flt != "pay" else "Только: 💳", "m|eflt")])
        hidden = self._hidden_count()
        if hidden:
            rows.append([_btn(f"↩️ Вернуть удалённые ({hidden})", f"m|restore|{page}")])
        rows.append([_btn("🏠 Меню", "m|menu")])
        return self._show(text, _kb(rows))

    def toggle_filter(self):
        self.state["esim_filter"] = "all" if (self.state.get("esim_filter") or "all") == "pay" else "pay"
        self._save()
        return self.show_esims(0)

    # MENU_DELETE_1591R57 -------------------------------------------------------
    def _hide(self, recs):
        for rec in recs:
            self.marks[self._mark_key(rec)] = HIDDEN_MARK
        if recs:
            self._save_marks()
        return len(recs)

    def delete_esim(self, key, page=0, step="ask"):
        rec = self._esim_by_key(key)
        if rec is None:
            return self.show_esims(page)
        if step != "yes":  # BOT_TOOLS_1591R60: deleting lives in the card only and asks first
            return self._show(
                f"🗑 <b>Удалить {self._phone(rec)} из списка?</b>\n\n"
                "Запись на сервере останется; вернуть можно кнопкой «↩️ Вернуть удалённые».",
                _kb([[_btn("🗑 Да, удалить", f"m|del|{key}|{page}|yes"), _btn("✖️ Отмена", f"m|esim|{key}|{page}")]]),
            )
        self._hide([rec])
        return self.show_esims(page, note=f"🗑 Удалено из списка: {self._phone(rec)}")

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
        return self.show_esims(page, note=f"🗑 Удалено из списка отмеченных: {n}")

    def delete_all(self, step, page=0):
        recs = self._esims()
        if step != "yes":
            self.state.update({"view": "esims", "page": int(page) if str(page).isdigit() else 0})
            self._save()
            return self._show(
                f"🗑 <b>Удалить из списка все {len(recs)} eSIM?</b>\n\n"
                "Файлы с результатами на сервере останутся; удаляется только показ в «Мои eSIM».",
                _kb([[_btn("🗑 Да, удалить", f"m|delall|yes|{page}"), _btn("✖️ Отмена", f"m|esims|{page}")]]),
            )
        n = self._hide(recs)
        return self.show_esims(0, note=f"🗑 Удалено из списка: {n}")

    def _hidden_count(self):
        return sum(1 for value in self.marks.values() if value == HIDDEN_MARK)

    def restore_hidden(self, page=0):
        """MENU_SAFE_DELETE_1591R58: every deleted eSIM back to the list (its manual mark is gone)."""
        keys = [k for k, v in self.marks.items() if v == HIDDEN_MARK]
        for key in keys:
            self.marks.pop(key, None)
        if keys:
            self._save_marks()
        return self.show_esims(page, note=f"↩️ Возвращено в список: {len(keys)}")

    # card ----------------------------------------------------------------------
    def _status_line(self, rec):
        status = self._status_of(rec)
        checked = self.link_results.get(self._mark_key(rec)) or {}
        line = STATUS_TITLES[status].capitalize()
        if status == "done" and checked.get("kind") == "used":
            line = "Готово · eSIM уже выпущена"
        if checked.get("time"):
            line += f" · проверено {_when(str(checked['time']) + ':00') or checked['time']}"
        return line

    def _esim_text(self, rec, full=True):
        """full: the card of r59 with the R60 status icons; short: the export message, as the push."""
        profile = rec.get("profile") or {}
        if not full:
            lines = [f"{self._label_of(rec)} eSIM · {'#оплата' if rec.get('_kind') == 'payment' else '#успешно'}",
                     f"📱 <b>{self._phone(rec)}</b>",
                     f"👤 {_esc(profile.get('full_name') or '—')} · 🎂 {_esc(profile.get('birth_date') or '—')}",
                     f"📄 Строка {rec.get('row', '?')} · {_esc(rec.get('active_digits') or '—')} | {_esc(rec.get('second_value') or '—')}"]
            basket = rec.get("basket") or {}
            if basket.get("tariff") or basket.get("prices"):
                lines.append(f"🧾 {_esc(basket.get('tariff') or '—')} · {_esc((basket.get('prices') or ['—'])[0])}")
            if rec.get("sim_url"):
                lines.append(f"🔗 {_esc(rec['sim_url'])}")
            return "\n".join(lines)
        head = "Требуется оплата eSIM" if rec.get("_kind") == "payment" else "Договор оформлен"
        lines = [
            f"{self._label_of(rec)} <b>{head}</b> · {_esc(self._status_line(rec))}",
            f"📱 eSIM: <b>{self._phone(rec)}</b>",
            f"📄 Строка {rec.get('row', '?')} · вкладка {rec.get('tab', '?')}"
            + (f" · 🕒 {_when(rec.get('time'))}" if _when(rec.get("time")) else ""),
            f"🔢 Исходные данные: {_esc(rec.get('active_digits') or '—')} | {_esc(rec.get('second_value') or '—')}",
            "",
        ]
        for key, label in (getattr(self.app, "SUCCESS_PROFILE_FIELDS", None) or []):
            lines.append(f"{_esc(label)}: {_esc(profile.get(key) or '—')}")
        lines.append("")
        if rec.get("sim_url"):
            lines.append(f"🔗 Ссылка заказа: {_esc(rec['sim_url'])}")
        if rec.get("payment_text"):
            lines.append(f"💬 Шаг сайта: {_esc(str(rec['payment_text'])[:200])}")
        if rec.get("final_url"):
            lines.append(f"🌐 Страница: {_esc(rec['final_url'])}")
        checked = self.link_results.get(self._mark_key(rec)) or {}
        if checked.get("kind") in LINK_ICONS:
            lines.append(f"🔗 Проверка ссылки: {LINK_ICONS[checked['kind']]} {LINK_TITLES.get(checked['kind'], '')}"
                         f" · {_esc(checked.get('time') or '')}" + (f"\n   {_esc(checked.get('text'))}" if checked.get("text") else ""))
        trace_lines = getattr(self.app, "_sign_trace_lines_1591r25", None)
        if trace_lines and rec.get("sign_trace"):
            try:
                lines.extend(_esc(x) for x in trace_lines(rec["sign_trace"])[:4])
            except Exception:
                pass
        return "\n".join(lines).rstrip()

    def _mark_rows(self, rec, prefix, tail):
        key = rec["_key"]
        return [_btn(STATUS_ICONS["done"], f"m|{prefix}|{key}|ok{tail}"), _btn(BANK_ICON, f"m|{prefix}|{key}|bank{tail}"),
                _btn("❌", f"m|{prefix}|{key}|bad{tail}"), _btn("↩️", f"m|{prefix}|{key}|new{tail}")]

    def show_esim(self, key, page=0, note=""):
        rec = self._esim_by_key(key)
        if rec is None:
            return self.show_esims(page)
        self.state.update({"view": "esim", "key": key, "page": int(page) if str(page).isdigit() else 0})
        self._save()
        text = self._esim_text(rec) + (f"\n\n{_esc(note)}" if note else "")
        rows = [self._mark_rows(rec, "set", f"|{page}")]
        if self.link_resolver is not None and not rec.get("sim_url"):
            rows.append([_btn("🔎 Ссылка из журнала", f"m|link|{key}|{page}")])
        rows.append([_btn("🗑 Удалить", f"m|del|{key}|{page}")])
        rows.append([_btn("◀️ Список", f"m|esims|{page}"), _btn("🏠 Меню", "m|menu")])
        return self._show(text, _kb(rows))

    def _apply_mark(self, rec, mark):
        """✅ ok, ❌ bad, 🏦 toggles the bank flag, ↩️ clears the manual mark and 🏦."""
        key = self._mark_key(rec)
        if mark == "bank":
            if self.bank.get(key):
                self.bank.pop(key, None)
                note = f"{BANK_ICON} снято"
            else:
                self.bank[key] = True
                note = f"{BANK_ICON} отмечено"
            self._save_bank()
            return note
        if mark == "new":
            self.marks.pop(key, None)
            self.bank.pop(key, None)
            self._save_marks()
            self._save_bank()
            return "↩️ отметки сняты"
        if mark in ("ok", "bad"):
            self.marks[key] = mark
            self._save_marks()
            return f"{STATUS_ICONS['done' if mark == 'ok' else 'bad']} {STATUS_TITLES['done' if mark == 'ok' else 'bad']}"
        return ""

    def set_mark(self, key, mark, page=0):
        rec = self._esim_by_key(key)
        if rec is None or mark not in ("ok", "bad", "new", "bank"):
            return self.show_esims(page)
        note = self._apply_mark(rec, mark)
        return self.show_esim(key, page, note=f"Отметка: {note}")

    # LINK_CHECK_1591R58 / BOT_TOOLS_1591R60 ------------------------------------
    def _link_targets(self, recs=None):
        out = []
        for rec in (self._esims() if recs is None else recs):
            url = str(rec.get("sim_url") or "").strip()
            if url.startswith("http"):
                out.append((self._mark_key(rec), url, rec))
        return out

    def start_link_check(self, recs=None, on_done=None):
        """Check the order links of `recs` (all by default) in a background thread; on_done(targets,
        before) runs in that thread when it ends. False when a check is already running."""
        with self._lc_lock:
            if self._lc["running"]:
                return False
            targets = self._link_targets(recs)
            before = {key: self._status_of(rec) for key, _, rec in targets}
            self._lc.update({"running": True, "done": 0, "total": len(targets), "started": _now(),
                             "finished": 0.0, "rendered": False, "keys": [k for k, _, _ in targets]})
        print(f"[MENU] Проверка ссылок: {len(targets)} шт.", flush=True)
        threading.Thread(target=self._run_link_check, args=(targets, before, on_done), name="link-check", daemon=True).start()
        return True

    def _run_link_check(self, targets, before=None, on_done=None):
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
            if on_done is not None:
                try:
                    on_done(targets, before or {})
                except Exception as exc:
                    print(f"[MENU] отчёт проверки не отправлен: {type(exc).__name__}: {exc}", flush=True)

    def _link_check_text(self):
        with self._lc_lock:
            lc = dict(self._lc)
        keys = set(lc.get("keys") or [])
        targets = [t for t in self._link_targets() if not keys or t[0] in keys]
        lines = ["🔁 <b>Обновление статусов</b>", ""]
        if lc["running"]:
            lines.append(f"⏳ Проверяю ссылки: {lc['done']} из {lc['total']}… экран обновится сам.")
        counts, problems = {}, []
        for key, url, rec in targets:
            status = self._status_of(rec)
            counts[status] = counts.get(status, 0) + 1
            res = self.link_results.get(key) or {}
            if res.get("kind") in ("dead", "unknown", "error"):
                problems.append(f"{LINK_ICONS[res['kind']]} {self._phone(rec)} · стр. {rec.get('row', '?')}: {_esc(res.get('text') or '')}")
        if not lc["running"]:
            for status in ("done", "pay", "dead", "bad", "new"):
                if counts.get(status):
                    lines.append(f"{STATUS_ICONS[status]} {STATUS_TITLES[status]}: {counts[status]}")
        if problems and not lc["running"]:
            lines.append("")
            lines.extend(problems[:20])
            if len(problems) > 20:
                lines.append(f"… и ещё {len(problems) - 20}")
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
        rows = [] if running else [[_btn("🔁 Обновить ещё раз", "m|recheck")]]
        rows.append([_btn("📱 Мои eSIM", "m|esims|0"), _btn("🏠 Меню", "m|menu")])
        return self._show(text, _kb(rows))

    def show_recheck_ask(self):
        pay = len(self._link_targets([r for r in self._esims() if self._status_of(r) == "pay"]))
        every = len(self._link_targets())
        return self._show(
            "🔁 <b>Обновить статусы</b>\n\nБот откроет ссылки заказов и обновит статусы в «Мои eSIM».\n"
            f"Только 💳: {pay} ссылок · все: {every}.",
            _kb([[_btn("Только: 💳", "m|recheck|pay"), _btn("Все", "m|recheck|all")], [_btn("◀️ Меню", "m|menu")]]),
        )

    def run_recheck(self, which):
        recs = self._esims()
        if which == "pay":
            recs = [r for r in recs if self._status_of(r) == "pay"]
        if not self.start_link_check(recs):
            return self.show_link_check()
        return self.show_link_check()

    # messages outside the panel ---------------------------------------------------
    def _send_msg(self, text, markup=None, html_mode=True):
        payload = {"chat_id": self._chat(), "text": _clip(text), "disable_web_page_preview": "true"}
        if html_mode:
            payload["parse_mode"] = "HTML"
        if markup:
            payload["reply_markup"] = markup
        for _ in range(3):
            r, err = self._api("sendMessage", payload)
            if r:
                return r, None
            wait = getattr(err, "retry_after", None)
            if not wait:
                return None, err
            time.sleep(min(float(wait) + 0.5, 30))
        return None, err

    def _send_document(self, name, text, caption=""):
        """sendDocument with a .txt made in memory (telegram_api only posts form fields)."""
        sender = getattr(self, "document_sender", None)
        if sender is not None:
            return sender(name, text, caption)
        import requests
        cfg = self._cfg()
        token = str(cfg.get("token") or "").strip()
        proxies = None
        try:
            proxies = self.app.telegram_http_proxies(cfg)
        except Exception:
            pass
        r = requests.post(f"https://api.telegram.org/bot{token}/sendDocument",
                          data={"chat_id": self._chat(), "caption": caption[:1000]},
                          files={"document": (name, text.encode("utf-8"), "text/plain")}, proxies=proxies, timeout=60)
        ok = False
        try:
            ok = bool(r.json().get("ok"))
        except Exception:
            pass
        return (r.json(), None) if ok else (None, f"HTTP {r.status_code}: {r.text[:200]}")

    def _edit_msg(self, cb, text, markup):
        msg = cb.get("message") or {}
        return self._api("editMessageText", {
            "chat_id": str(((msg.get("chat") or {}).get("id")) or self._chat()), "message_id": msg.get("message_id"),
            "text": _clip(text), "reply_markup": markup, "disable_web_page_preview": "true", "parse_mode": "HTML"})

    @staticmethod
    def _compact_phone(rec):
        d = _digits(rec.get("sim_number") or rec.get("active_digits"))
        return "+7" + d[1:] if len(d) == 11 and d[0] in "78" else (rec.get("sim_number") or "—")

    @staticmethod
    def _chunks(items, limit=MSG_LIMIT, sep="\n\n"):
        out, cur = [], ""
        for item in items:
            if cur and len(cur) + len(sep) + len(item) > limit:
                out.append(cur)
                cur = item
            else:
                cur = cur + sep + item if cur else item
        if cur:
            out.append(cur)
        return out

    def _urgent_items(self, recs):
        return [f"{i}. Номер: {self._compact_phone(r)}\n{r.get('sim_url') or 'ссылки нет'}" for i, r in enumerate(recs, 1)]

    # export (BOT_TOOLS_1591R60) -----------------------------------------------------
    def _pay_recs(self):
        return [r for r in self._esims() if self._status_of(r) == "pay"]

    def show_export(self, step="start", value=""):
        exp = self.state.get("export") or {}
        n = len(self._pay_recs())
        if step == "mode":
            exp = {"mode": value}
            self.state["export"] = exp
            self._save()
            return self._show(f"📤 <b>Выгрузка</b> · {'🟢 обычная' if value == 'normal' else '‼️ срочная'}\n\nКак выгрузить?",
                              _kb([[_btn("💬 Сообщением", "m|exp|fmt|msg"), _btn("📄 Файлом .txt", "m|exp|fmt|txt")],
                                   [_btn("◀️ Назад", "m|exp")]]))
        if step == "fmt":
            exp["fmt"] = value
            exp["await"] = True
            self.state["export"] = exp
            self._save()
            return self._show(f"📤 <b>Выгрузка</b>\n\nСколько выгрузить? Напиши число или слово «Все».\nЖдут оплаты 💳: {n}",
                              _kb([[_btn(f"Все ({n})", "m|exp|count|all")], [_btn("✖️ Отмена", "m|exp|cancel")]]))
        if step == "cancel":
            self.state.pop("export", None)
            self._save()
            return self.show_menu(note="✖️ Выгрузка отменена.")
        self.state.pop("export", None)
        self.state["view"] = "export"
        self._save()
        return self._show(f"📤 <b>Выгрузка eSIM</b>\n\nЖдут оплаты 💳: {n}\nВыбери вид:",
                          _kb([[_btn("🟢 Обычная", "m|exp|mode|normal"), _btn("‼️ Срочная", "m|exp|mode|urgent")],
                               [_btn("◀️ Меню", "m|menu")]]))

    def run_export(self, count):
        exp = dict(self.state.get("export") or {})
        self.state.pop("export", None)
        self._save()
        recs = self._pay_recs()
        if count != "all":
            recs = recs[:max(0, int(count))]
        if not recs:
            return self.show_menu(note="📤 Выгружать нечего: нет eSIM со знаком 💳.")
        mode, fmt = exp.get("mode") or "normal", exp.get("fmt") or "msg"
        batch = self._save_batch(recs, mode, fmt)
        print(f"[MENU] Выгрузка: {len(recs)} eSIM, {mode}/{fmt}", flush=True)
        threading.Thread(target=self._export_worker, args=(recs, mode, fmt, batch), name="export", daemon=True).start()
        return self.show_menu(note=f"📤 Выгружаю {len(recs)} eSIM…")

    def _save_batch(self, recs, mode, fmt):
        batch = str(int(_now() * 1000))
        exports = _read_json(self.base / EXPORTS_FILE, {})
        while batch in exports:
            batch = str(int(batch) + 1)
        exports[batch] = {"keys": [r["_key"] for r in recs], "mode": mode, "fmt": fmt}
        for old in sorted(exports)[:-30]:
            exports.pop(old, None)
        _write_json(self.base / EXPORTS_FILE, exports)
        return batch

    def _load_batch(self, batch):
        item = (_read_json(self.base / EXPORTS_FILE, {}) or {}).get(str(batch))
        if isinstance(item, list):  # the first r60 build kept the keys only
            item = {"keys": item}
        item = dict(item or {})
        return list(item.get("keys") or []), item.get("mode") or "urgent", item.get("fmt") or "msg"

    def _deliver(self, recs, mode, fmt, title=""):
        """The eSIMs as the export gave them: 🟢 a message per eSIM with buttons, ‼️ a numbered list, or a .txt."""
        stamp = time.strftime("%d.%m_%H-%M")
        if fmt == "txt":
            if mode == "urgent":
                body = "\n\n".join(self._urgent_items(recs))
            else:
                body = "\n\n".join(re.sub(r"<[^>]+>", "", self._esim_text(r, full=False)).replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&") for r in recs)
            self._send_document(f"esim_{'срочная' if mode == 'urgent' else 'обычная'}_{stamp}.txt", body + "\n",
                                caption=title or f"📤 {len(recs)} eSIM 💳")
        elif mode == "urgent":
            items = self._urgent_items(recs)
            if title:
                items[0] = f"{title}\n\n" + items[0]
            for part in self._chunks(items):
                self._send_msg(_esc(part))
                time.sleep(EXPORT_SEND_GAP_SECONDS)
        else:
            if title:
                self._send_msg(_esc(title))
                time.sleep(EXPORT_SEND_GAP_SECONDS)
            for rec in recs:
                self._send_msg(self._esim_text(rec, full=False), self._export_markup(rec, False))
                time.sleep(EXPORT_SEND_GAP_SECONDS)

    def _refresh_offer(self, batch):
        self._send_msg("🔄 <b>Обновить статус ссылок</b>\nПроверю эти ссылки и пришлю отчёт.",
                       _kb([[_btn("🔄 Обновить", f"m|xr|{batch}")]]))

    def _export_worker(self, recs, mode, fmt, batch):
        try:
            self._deliver(recs, mode, fmt)
            self._refresh_offer(batch)
        except Exception as exc:
            print(f"[MENU] Выгрузка прервана: {type(exc).__name__}: {exc}", flush=True)

    def _export_markup(self, rec, opened):
        tail = "|1" if opened else "|0"
        return _kb([[_btn("🔽" if opened else "🔼", f"m|{'xc' if opened else 'xo'}|{rec['_key']}")],
                    [b for b in self._mark_rows(rec, "xm", tail) if b["text"] != "❌"]])

    def export_card(self, cb, key, opened):
        rec = self._esim_by_key(key)
        if rec is None:
            return None
        return self._edit_msg(cb, self._esim_text(rec, full=opened), self._export_markup(rec, opened))

    def export_mark(self, cb, key, mark, opened):
        rec = self._esim_by_key(key)
        if rec is None:
            return ""
        note = self._apply_mark(rec, mark)
        self._edit_msg(cb, self._esim_text(rec, full=opened), self._export_markup(rec, opened))
        return note

    def export_recheck(self, batch):
        keys, _, _ = self._load_batch(batch)
        recs = [r for r in self._esims() if r["_key"] in set(keys)]
        if not recs:
            self._send_msg("Эта выгрузка уже недоступна.")
            return False
        started = self.start_link_check(recs, on_done=lambda t, b: self._send_report(t, b, batch))
        if not started:
            self._send_msg("⏳ Проверка ссылок уже идёт, дождись её отчёта.")
            return False
        self._send_msg(f"⏳ Проверяю {len(recs)} ссылок, отчёт придёт сюда.")
        return True

    def _send_report(self, targets, before, batch=None, only_changes=False):
        """«Отчёт»: how many are paid ✅, still waiting 💳, dead ⛔; then the waiting ones as a list."""
        after = {key: self._status_of(rec) for key, _, rec in targets}
        counts = {}
        for status in after.values():
            counts[status] = counts.get(status, 0) + 1
        changed = [(key, rec) for key, _, rec in targets if before.get(key) != after.get(key)]
        if only_changes and not changed:
            print("[MENU] Автопроверка ссылок: изменений нет", flush=True)
            return False
        lines = ["📋 <b>Отчёт</b>" + (" автопроверки" if only_changes else "")]
        names = {"done": "оплачены / готовы", "pay": "ожидают оплаты", "dead": "не работают", "bad": "брак", "new": "без статуса"}
        for status in ("done", "pay", "dead", "bad", "new"):
            if counts.get(status):
                lines.append(f"{STATUS_ICONS[status]} {counts[status]} — {names[status]}")
        if changed:
            lines.append("")
            lines.append("Изменились:")
            lines.extend(f"{STATUS_ICONS[after[key]]} {self._phone(rec)} · стр. {rec.get('row', '?')}" for key, rec in changed[:30])
        waiting = [rec for key, _, rec in targets if after.get(key) == "pay"]
        if only_changes or not batch:
            self._send_msg("\n".join(lines))
            return True
        if not waiting:
            self._send_msg("\n".join(lines + ["", "Все ссылки этой выгрузки отработаны."]))
            return True
        self._send_msg("\n".join(lines))
        time.sleep(EXPORT_SEND_GAP_SECONDS)
        _, mode, fmt = self._load_batch(batch)
        nxt = self._save_batch(waiting, mode, fmt)  # the next «🔄 Обновить» checks the ones still waiting
        self._deliver(waiting, mode, fmt, title=f"💳 Ожидают оплаты: {len(waiting)}")
        self._refresh_offer(nxt)
        return True

    # /recheck (BOT_TOOLS_1591R60) ----------------------------------------------------
    def recheck_command(self, text):
        arg = (text.split(maxsplit=1)[1] if len(text.split(maxsplit=1)) > 1 else "").strip().lower()
        every = int(self.state.get("recheck_every") or 0)
        if not arg:
            if every:
                nxt = time.strftime("%d.%m %H:%M", time.localtime(float(self.state.get("recheck_next") or 0)))
                return self._send_msg(f"🔁 Автопроверка ссылок 💳: каждые {_period(every)}, следующая {nxt}.\n"
                                      "Изменить: /recheck 12h, 1d, 2d · выключить: /recheck off")
            return self._send_msg("🔁 Автопроверка ссылок выключена.\nВключить: /recheck 24h (или 12h, 1d, 2d)")
        if arg in ("off", "0", "выкл", "stop", "нет"):
            self.state.pop("recheck_every", None)
            self.state.pop("recheck_next", None)
            self._save()
            return self._send_msg("🔁 Автопроверка ссылок выключена.")
        m = re.fullmatch(r"(\d+)\s*(h|ч|час|часа|часов|d|д|день|дня|дней)", arg)
        if not m or int(m.group(1)) <= 0:
            return self._send_msg("Не понял срок. Примеры: /recheck 24h, /recheck 1d, /recheck 2d, /recheck off")
        seconds = int(m.group(1)) * (86400 if m.group(2)[0] in "dд" else 3600)
        seconds = max(seconds, 3600)
        self.state.update({"recheck_every": seconds, "recheck_next": _now() + seconds})
        self._save()
        nxt = time.strftime("%d.%m %H:%M", time.localtime(_now() + seconds))
        return self._send_msg(f"🔁 Автопроверка ссылок 💳 включена: каждые {_period(seconds)}, первая {nxt}.\n"
                              "Отчёт приходит, только если статусы изменились.")

    def _recheck_tick(self):
        every = int(self.state.get("recheck_every") or 0)
        if not every or _now() < float(self.state.get("recheck_next") or 0):
            return False
        self.state["recheck_next"] = _now() + every
        self._save()
        recs = self._pay_recs()
        if not recs:
            return False
        return self.start_link_check(recs, on_done=lambda t, b: self._send_report(t, b, only_changes=True))

    # BASE_TOOLS_1591R64 (first written as r63): «📂 База» and «🔢 Генерация» ---------
    def show_base(self):
        self.state.update({"view": "base", "awaiting_ai": False, "awaiting_generation": False})
        self._save()
        return self._show(
            "📂 <b>База</b>\n\nВыбери, что сделать с базой:",
            _kb([
                [_btn("➕ Добавить строки", "m|baseadd")],
                [_btn("🆕 Загрузить новую базу", "m|basenew")],
                [_btn("◀️ Меню", "m|menu")],
            ]),
        )

    def show_generation(self):
        self.state.update({"view": "generation", "awaiting_ai": False, "awaiting_generation": True})
        self._save()
        return self._show(
            "🔢 <b>Генерация номеров</b>\n\n"
            "Пришли первые 7 цифр номера. Можно со звёздочками, пробелами и несколько строк.\n\n"
            "Например:\n<code>+7900111****</code>\n<code>7900222****</code>\n\n"
            "Для каждого префикса будут созданы все 10 000 вариантов: 0000–9999.",
            _kb([[_btn("✖️ Отмена", "m|menu")]]),
        )

    def _handle_generation_text(self, text):
        # BASE_TOOLS_1591R64: one prefix per line (or split by , ;), spaces and brackets inside are fine:
        # «+7 900 111 ****», «8 (900) 111-****» and «7900111» are the same prefix 7900111.
        tokens = [x.strip() for x in re.split(r"[\n,;]+", str(text or "")) if x.strip()]
        prefixes, bad = [], []
        for token in tokens:
            digits = _digits(token)
            if len(digits) == 7 and digits.startswith("8"):
                digits = "7" + digits[1:]
            if len(digits) != 7 or not digits.startswith("7"):
                bad.append(token)
                continue
            if digits not in prefixes:
                prefixes.append(digits)
        if bad or not prefixes:
            bad_text = ", ".join(bad[:5]) if bad else "пустой ввод"
            self._show(
                "❌ <b>Неверный формат</b>\n\nНужны первые 7 цифр, например <code>+7900111****</code>.\n"
                f"Не распознано: {_esc(bad_text)}",
                _kb([[_btn("✖️ Отмена", "m|menu")]]),
            )
            return True
        if len(prefixes) > 100:
            self._show("❌ За один раз максимум 100 префиксов.", _kb([[_btn("✖️ Отмена", "m|menu")]]))
            return True
        total = len(prefixes) * 10000
        body = "".join(f"{prefix}{suffix:04d}\n" for prefix in prefixes for suffix in range(10000))
        stamp = time.strftime("%Y%m%d_%H%M%S")
        name = f"numbers_{prefixes[0]}_{len(prefixes)}prefix_{stamp}.txt"
        self.state["awaiting_generation"] = False
        self._save()
        _, err = self._send_document(name, body, caption=f"🔢 Сгенерировано {total} номеров")
        if err:
            return self.show_menu(note=f"❌ Не удалось отправить TXT: {err}")
        return self.show_menu(note=f"✅ Сгенерировано {total} номеров по {len(prefixes)} префиксам.")

    def _cancel_append_pending(self):
        try:
            (self.base / ".base_append_pending").unlink(missing_ok=True)
        except OSError:
            pass

    def handle_text(self, text):
        """BOT_TOOLS_1591R60: True when the menu took the message (/recheck, the export count)."""
        t = str(text or "").strip()
        first = (t.split() or [""])[0].lower().split("@")[0]
        if first == "/recheck":
            self.recheck_command(t)
            return True
        if self.state.get("awaiting_generation"):
            if t.startswith("/"):
                self.state["awaiting_generation"] = False
                self._save()
                return False
            return self._handle_generation_text(t)
        exp = self.state.get("export") or {}
        if not exp.get("await"):
            return False
        if t.startswith("/"):
            self.state.pop("export", None)
            self._save()
            return False
        low = t.lower()
        if low in ("все", "всё", "all", "все сразу"):
            self.run_export("all")
            return True
        if t.isdigit() and int(t) > 0:
            self.run_export(int(t))
            return True
        self._show("📤 <b>Выгрузка</b>\n\nНужно число, например 10, или слово «Все».",
                   _kb([[_btn("Все", "m|exp|count|all")], [_btn("✖️ Отмена", "m|exp|cancel")]]))
        return True

    # server, settings, update (BOT_TOOLS_1591R60) -----------------------------------
    def _app_source(self):
        try:
            return Path(self.app.__file__).read_text("utf-8", errors="replace")
        except Exception:
            return ""

    def _revision(self):
        src = self._app_source()
        revs = [int(x) for x in re.findall(r"_1591R(\d+)", src)]
        build = "exp8" if "EXPERIMENT_BROWSERS8_1591" in src else ("full" if "SIGN_ROBUST_1591R31" in src else "lite")
        return (max(revs) if revs else 0), build

    def _latest_revision(self, force=False):
        if not force and _now() - float(self.state.get("latest_at") or 0) < UPDATE_CHECK_SECONDS:
            return int(self.state.get("latest_rev") or 0)
        fetch = getattr(self, "revision_fetcher", None) or _fetch_latest_revision
        try:
            rev = int(fetch() or 0)
        except Exception as exc:
            print(f"[MENU] GitHub недоступен: {type(exc).__name__}: {exc}", flush=True)
            rev = int(self.state.get("latest_rev") or 0)
        self.state.update({"latest_rev": rev, "latest_at": _now()})
        self._save()
        return rev

    def show_server(self):
        self.state["view"] = "server"
        self._save()
        rev, build = self._revision()
        latest = int(self.state.get("latest_rev") or 0)
        lines = ["🖥 <b>Сервер</b>", "", f"🤖 Версия бота: r{rev} ({build})"
                 + (f" · доступна r{latest}" if latest > rev else "")]
        lines.extend(_server_lines(self.base, float(getattr(self, "_started_at", 0) or 0)))
        return self._show("\n".join(lines), _kb([[_btn("🔄 Обновить", "m|srv"), _btn("⬆️ Обновить бота", "m|upd")],
                                                  [_btn("🏠 Меню", "m|menu")]]))

    def show_update(self, step="show"):
        rev, build = self._revision()
        if step == "go":
            return self.start_self_update()
        latest = self._latest_revision(force=(step == "check"))
        self.state["view"] = "update"
        self._save()
        text = f"⬆️ <b>Обновление бота</b>\n\nСейчас: r{rev} ({build})\nНа GitHub: " + (f"r{latest}" if latest else "не удалось узнать")
        rows = []
        if step == "ask":
            text += ("\n\nОбновить? Бот перезапустится, строки в работе начнутся заново.\n"
                     "Результат придёт сообщением.")
            rows.append([_btn("✅ Да, обновить", "m|upd|go"), _btn("✖️ Нет", "m|upd")])
        else:
            if latest > rev:
                rows.append([_btn(f"⬆️ Обновить до r{latest}", "m|upd|ask")])
            else:
                text += "\n\nНовых версий нет."
                rows.append([_btn("⬆️ Переустановить всё равно", "m|upd|ask")])
            rows.append([_btn("🔎 Проверить снова", "m|upd|check")])
        rows.append([_btn("🏠 Меню", "m|menu")])
        return self._show(text, _kb(rows))

    def start_self_update(self):
        rev, _ = self._revision()
        log = self.base / SELF_UPDATE_LOG
        _write_json(self.base / SELF_UPDATE_FILE, {"from": rev, "started": _now()})
        cmd = f"curl -fsSL {UPDATE_URL} | bash > {log} 2>&1; echo EXIT=$? >> {log}"
        try:
            self.runner(["systemd-run", "--unit", f"beeline-self-update-{int(_now())}", "--collect", "--quiet",
                         "/bin/bash", "-c", cmd])
        except Exception as exc:
            try:
                (self.base / SELF_UPDATE_FILE).unlink()
            except OSError:
                pass
            return self.show_menu(note=f"❌ Обновление не запустилось: {type(exc).__name__}: {exc}")
        print(f"[MENU] Самообновление запущено с r{rev}", flush=True)
        return self.show_menu(note="⏳ Обновляю… бот перезапустится и пришлёт результат.")

    def _update_result(self):
        pending = _read_json(self.base / SELF_UPDATE_FILE, None)
        if not pending:
            return None
        try:
            log = (self.base / SELF_UPDATE_LOG).read_text("utf-8", errors="replace")
        except Exception:
            log = ""
        rev, _ = self._revision()
        start = int(pending.get("from") or 0)
        finished = "EXIT=" in log
        msg = None
        if rev > start:
            msg = f"✅ Бот обновлён: r{start} → r{rev}"
        elif finished and ("ALREADY INSTALLED" in log or re.search(r"EXIT=0\s*$", log)):
            msg = f"ℹ️ Обновлений не было: стоит r{rev}"
        elif finished or _now() - float(pending.get("started") or 0) > SELF_UPDATE_TIMEOUT_SECONDS:
            tail = "\n".join([x for x in log.splitlines() if x.strip() and not x.startswith("EXIT=")][-6:])
            msg = f"❌ Обновление не прошло, стоит r{rev}" + (f"\n{tail}" if tail else "")
        if msg:
            try:
                (self.base / SELF_UPDATE_FILE).unlink()
            except OSError:
                pass
        return msg

    def _settings_values(self):
        env = os.environ
        tariff = (env.get("BEELINE_TARIFF") or "").strip() or "подписка bee START"
        try:
            restart = int(self.app.restart_policy_minutes(self.base))
        except Exception:
            restart = 0
        return {"tariff": tariff, "browsers": (env.get("BEELINE_BROWSERS") or "2").strip(),
                "tabs": (env.get("BEELINE_TABS_PER_BROWSER") or "4").strip(),
                "ai": str(env.get("BEELINE_AI") or ("0" if "EXPERIMENT_BROWSERS8_1591" in self._app_source() else "1")).strip().lower()
                not in {"0", "off", "no", "false"},
                "restart": restart}

    def show_settings(self, step="", value=""):
        cur = self._settings_values()
        if step == "tariff":
            rows = [[_btn(label, f"m|cfg|ask|tariff|{k}")] for k, (label, _) in TARIFF_CHOICES.items()]
            return self._show("📦 <b>Тариф</b>\n\nСейчас: " + _esc(cur["tariff"]), _kb(rows + [[_btn("◀️ Назад", "m|cfg")]]))
        if step in ("browsers", "tabs"):
            top = 8 if (step == "browsers" and "EXPERIMENT_BROWSERS8_1591" in self._app_source()) else 4
            opts = [str(n) for n in range(1, top + 1)]
            title = "🌐 <b>Браузеров</b>" if step == "browsers" else "🗂 <b>Вкладок в каждом браузере</b>"
            return self._show(f"{title}\n\nСейчас: {cur[step]}",
                              _kb([[_btn(o, f"m|cfg|ask|{step}|{o}") for o in opts[:4]], [_btn(o, f"m|cfg|ask|{step}|{o}") for o in opts[4:]],
                                   [_btn("◀️ Назад", "m|cfg")]]))
        if step == "restart":
            rows = [[_btn(t, f"m|cfg|rs|{m}") for m, t in RESTART_CHOICES]]
            return self._show("♻️ <b>Плановый перезапуск</b>\n\nСейчас: " + (_period(cur["restart"] * 60) if cur["restart"] else "выкл"),
                              _kb(rows + [[_btn("◀️ Назад", "m|cfg")]]))
        if step == "rs":
            minutes = int(value or 0)
            self.app.write_restart_policy(self.base, minutes)
            return self.show_settings(value=f"♻️ Плановый перезапуск: {_period(minutes * 60) if minutes else 'выкл'}")
        self.state["view"] = "settings"
        self._save()
        lines = ["⚙️ <b>Настройки</b>", "",
                 f"📦 Тариф: {_esc(cur['tariff'])}",
                 f"🌐 Браузеров: {cur['browsers']} · вкладок в каждом: {cur['tabs']}",
                 f"🤖 DeepSeek: {'включён' if cur['ai'] else 'выключен'}",
                 f"♻️ Плановый перезапуск: {_period(cur['restart'] * 60) if cur['restart'] else 'выкл'}",
                 "", "<i>Тариф, браузеры, вкладки и DeepSeek применяются перезапуском бота.</i>"]
        if value:
            lines += ["", _esc(value)]
        return self._show("\n".join(lines), _kb([
            [_btn("📦 Тариф", "m|cfg|tariff"), _btn("🌐 Браузеры", "m|cfg|browsers"), _btn("🗂 Вкладки", "m|cfg|tabs")],
            [_btn(f"🤖 DeepSeek: {'выключить' if cur['ai'] else 'включить'}", f"m|cfg|ask|ai|{'0' if cur['ai'] else '1'}")],
            [_btn("♻️ Плановый перезапуск", "m|cfg|restart")],
            [_btn("🏠 Меню", "m|menu")]]))

    def ask_setting(self, name, value):
        desc = _setting_desc(name, value)
        if not desc:
            return self.show_settings()
        return self._show(f"⚙️ <b>Применить?</b>\n\n{_esc(desc)}\n\nБот перезапустится, строки в работе начнутся заново.",
                          _kb([[_btn("✅ Применить", f"m|cfg|ok|{name}|{value}"), _btn("✖️ Отмена", "m|cfg")]]))

    def apply_setting(self, name, value):
        desc = _setting_desc(name, value)
        env = _setting_env(name, value)
        if not env:
            return self.show_settings()
        path = Path(getattr(self, "dropin_path", None) or MENU_DROPIN)
        current = _read_dropin(path)
        current.update(env)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("[Service]\n# BOT_TOOLS_1591R60: written by «⚙️ Настройки» of the bot's menu\n"
                        + "".join(f'Environment="{k}={v}"\n' for k, v in current.items()), "utf-8")
        self.state["settings_applied"] = desc
        self._save()
        print(f"[MENU] Настройка: {desc}", flush=True)
        try:
            self.runner(["systemctl", "daemon-reload"])
            self.runner(["systemctl", "--no-block", "restart", "beeline"])
        except Exception as exc:
            self.state.pop("settings_applied", None)
            self._save()
            return self.show_settings(value=f"❌ Не применилось: {type(exc).__name__}: {exc}")
        return self.show_menu(note=f"⏳ Применяю: {desc}. Бот перезапустится.")

    # start, heartbeat (BOT_TOOLS_1591R60) -----------------------------------------
    def on_start(self):
        """Called once by the controller: a notice when the server rebooted or the bot died, the result
        of a self-update or of a setting, and the SIGTERM hook that marks a planned stop."""
        self._started_at = _now()
        notes = []
        alive = _read_json(self.base / ALIVE_FILE, {}) or {}
        boot = _boot_id()
        clean = (self.base / CLEAN_STOP_FILE).exists()
        last = float(alive.get("time") or 0)
        if last:
            at = time.strftime("%d.%m %H:%M", time.localtime(last))
            if alive.get("boot_id") and boot and alive.get("boot_id") != boot:
                notes.append(f"♻️ Сервер перезагружался. Бот работал до {at}, снова запущен в {time.strftime('%H:%M')}.")
            elif not clean:
                notes.append(f"♻️ Бот перезапустился после сбоя (последний признак жизни {at}).")
        try:
            (self.base / CLEAN_STOP_FILE).unlink()
        except OSError:
            pass
        self._write_alive()
        applied = self.state.pop("settings_applied", None)
        if applied:
            self._save()
            notes.append(f"⚙️ Применено: {applied}")
        upd = self._update_result()
        if upd:
            notes.append(upd)
        for note in notes:
            self._send_msg(_esc(note))
        if threading.current_thread() is threading.main_thread():
            try:
                signal.signal(signal.SIGTERM, self._on_sigterm)
            except Exception:
                pass
        return notes

    def _on_sigterm(self, signum, frame):
        try:
            (self.base / CLEAN_STOP_FILE).write_text(str(_now()), "utf-8")
        except Exception:
            pass
        signal.signal(signal.SIGTERM, signal.SIG_DFL)
        os.kill(os.getpid(), signal.SIGTERM)

    def _write_alive(self):
        self._alive_at = _now()
        try:
            _write_json(self.base / ALIVE_FILE, {"boot_id": _boot_id(), "time": _now()})
        except Exception:
            pass


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
        # BASE_TOOLS_1591R64: another button ends a pending «🔢 Генерация» or export count, so the next
        # typed text (a DeepSeek question) is not taken for prefixes or a number.
        if action != "gen" and self.state.get("awaiting_generation"):
            self.state["awaiting_generation"] = False
            self._save()
        if action != "exp" and (self.state.get("export") or {}).get("await"):
            self.state.pop("export", None)
            self._save()
        try:
            if action == "menu":
                self.show_menu()
            elif action == "noop":
                pass
            elif action == "base":
                self.show_base()
            elif action in ("baseadd", "basenew"):
                mode = "add" if action == "baseadd" else "new"
                title = "Добавить строки" if mode == "add" else "Загрузить новую базу"
                note = ("Текущая работа не будет остановлена." if mode == "add" else
                        "Текущая работа будет остановлена только после проверки файла; затем новая база запустится.")
                self.state.update({"view": "upload_" + mode, "awaiting_generation": False})
                self._save()
                self._show(
                    f"📂 <b>{title}</b>\n\nПришли следующим сообщением .txt файл.\n{note}\n\n"
                    "Поддерживаются:\n<code>номер паспорт</code>\n<code>номер|паспорт|дата рождения</code>",
                    _kb([[_btn("✖️ Отмена", "m|base")]]),
                )
                self._answer(cb)
                return "upload_" + mode
            elif action == "gen":
                self.show_generation()
            elif action == "status":
                self.show_status()
            elif action == "esims":
                self.show_esims(args[0] if args else 0)
            elif action == "eflt":  # BOT_TOOLS_1591R60: «Показать: Все» ⇄ «Только: 💳»
                self.toggle_filter()
            elif action == "esim":
                self.show_esim(args[0], args[1] if len(args) > 1 else 0)
            elif action == "set":
                self.set_mark(args[0], args[1], args[2] if len(args) > 2 else 0)
            elif action == "del":  # MENU_DELETE_1591R57; R60: in the card only, with a confirmation
                step = "yes" if len(args) > 2 and args[2] == "yes" else "ask"
                if step == "yes":
                    self._log_press(cb, data)
                self.delete_esim(args[0], args[1] if len(args) > 1 else 0, step)
            elif action == "delmarked":  # MENU_SAFE_DELETE_1591R58: buttons of an old panel still ask first
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
            elif action == "lcheck":  # an old panel's «🔗 Проверить ссылки»
                self.show_recheck_ask()
            elif action == "recheck":
                if args and args[0] in ("pay", "all"):
                    self.run_recheck(args[0])
                else:
                    self.show_recheck_ask()
            elif action == "exp":
                if not args:
                    self.show_export()
                elif args[0] in ("mode", "fmt") and len(args) > 1:
                    self.show_export(args[0], args[1])
                elif args[0] == "count":
                    self.run_export("all")
                else:
                    self.show_export("cancel")
            elif action in ("xo", "xc"):
                self.export_card(cb, args[0], action == "xo")
            elif action == "xm":
                note = self.export_mark(cb, args[0], args[1], len(args) > 2 and args[2] == "1")
                self._answer(cb, note)
                return None
            elif action == "xr":
                self.export_recheck(args[0] if args else "")
            elif action == "srv":
                self.show_server()
            elif action == "upd":
                if args and args[0] == "go":
                    self._log_press(cb, data)
                self.show_update(args[0] if args else "show")
            elif action == "cfg":
                if not args:
                    self.show_settings()
                elif args[0] in ("tariff", "browsers", "tabs", "restart"):
                    self.show_settings(args[0])
                elif args[0] == "rs" and len(args) > 1:
                    self._log_press(cb, data)
                    self.show_settings("rs", args[1])
                elif args[0] == "ask" and len(args) > 2:
                    self.ask_setting(args[1], args[2])
                elif args[0] == "ok" and len(args) > 2:
                    self._log_press(cb, data)
                    self.apply_setting(args[1], args[2])
                else:
                    self.show_settings()
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
                self._cancel_append_pending()
                _, answer = self.proc.start()
                self.show_menu(note=answer)
            elif action == "stop":
                self._cancel_append_pending()
                _, answer = self.proc.stop()
                self.show_menu(note=answer)
            elif action == "restart":
                self._cancel_append_pending()
                _, answer = self.proc.restart()
                self.show_menu(note="🔄 " + str(answer))
            elif action == "upload":  # compatibility with old inline panels
                self.state.update({"view": "upload_new", "awaiting_generation": False})
                self._save()
                self._show(
                    "📂 <b>Загрузить новую базу</b>\n\nПришли следующим сообщением .txt файл.\n"
                    "Файл сначала будет проверен и отфильтрован; затем текущая работа остановится и новая база запустится.",
                    _kb([[_btn("✖️ Отмена", "m|base")]]),
                )
                self._answer(cb)
                return "upload_new"
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

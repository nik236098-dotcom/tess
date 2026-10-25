#!/usr/bin/env python3
"""Панель оплат eSIM (pay_panel) — многопользовательский бот: админ + операторы-оплатчики.

ЭТАП 1 (каркас): роли, инвайты, SQLite, меню оплатчика/админа, очередь, баны, /invite /ban /unban,
запрос выплаты (с заморозкой), загрузка ссылок, настройки. Движок оплаты (карта→3DS→status),
проблемные ссылки, канал логов и ИИ-агент подключаются следующими этапами.

Полное ТЗ: operator_repair_1591/pay_panel/SPEC.md
Движок оплаты будет переиспользован из pay_bot.py (кладётся в ту же папку установщиком).

Конфиг pay_panel_config.json (рядом со скриптом или путь в PAY_PANEL_CONFIG):
  {
    "token": "<токен ЭТОГО бота>",
    "admin_id": 123456789,                 // твой Telegram ID (числом)
    "admin_contact": "@gennadiy_cc",
    "proxy": "socks5h://логин:пароль@хост:порт",   // для Telegram; "direct" если не нужен
    "browser_proxy": "",                   // для страниц оплаты (обычно пусто)
    "deepseek_api_key": "sk-...",
    "deepseek_model": "deepseek-chat",
    "default_rate_usd": 4.5,
    "tariff_rub": 300,
    "idle_timeout_s": 180,
    "newcard_timeout_s": 300,
    "per_payment_watchdog_s": 600
  }
"""
from __future__ import annotations

import hashlib
import json
import os
import queue as _queue
import re
import sqlite3
import sys
import threading
import time
import traceback
from pathlib import Path

import requests

BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = Path(os.environ.get("PAY_PANEL_CONFIG") or (BASE_DIR / "pay_panel_config.json"))
DB_PATH = Path(os.environ.get("PAY_PANEL_DB") or (BASE_DIR / "pay_panel.sqlite3"))


def log(msg):
    print(f"[PANEL] {time.strftime('%H:%M:%S')} {msg}", flush=True)


def now():
    return int(time.time())


def msk_ts(ts=None):
    return time.strftime("%Y-%m-%d %H:%M", time.gmtime((ts or now()) + 3 * 3600)) + " МСК"


# ── конфиг ───────────────────────────────────────────────────────────────────
def load_config():
    if not CONFIG_PATH.is_file():
        raise SystemExit(f"нет файла конфига: {CONFIG_PATH}")
    cfg = json.loads(CONFIG_PATH.read_text("utf-8"))
    if not str(cfg.get("token") or "").strip():
        raise SystemExit("в конфиге нет token")
    if not str(cfg.get("admin_id") or "").strip():
        raise SystemExit("в конфиге нет admin_id (твой Telegram ID числом)")
    cfg.setdefault("admin_contact", "@gennadiy_cc")
    cfg.setdefault("default_rate_usd", 4.5)
    cfg.setdefault("tariff_rub", 300)
    cfg.setdefault("idle_timeout_s", 180)
    cfg.setdefault("newcard_timeout_s", 300)
    cfg.setdefault("per_payment_watchdog_s", 600)
    return cfg


CFG = load_config()
ADMIN_ID = int(CFG["admin_id"])
ADMIN_CONTACT = str(CFG["admin_contact"])


# ── Telegram (raw API через прокси) ──────────────────────────────────────────
class Telegram:
    def __init__(self, cfg):
        self.token = str(cfg["token"]).strip()
        proxy = str(cfg.get("proxy") or "").strip()
        self.session = requests.Session()
        if proxy and proxy.lower() not in ("direct", "none", "off", "no", "-"):
            self.session.proxies = {"https": proxy, "http": proxy}
        self.base = f"https://api.telegram.org/bot{self.token}"
        self.offset = None

    def _call(self, method, **params):
        try:
            r = self.session.post(f"{self.base}/{method}", data=params, timeout=60)
            return r.json()
        except Exception as exc:
            log(f"{method} error: {type(exc).__name__}: {exc}")
            return {}

    def send(self, chat_id, text, kb=None, silent=False):
        text, ents = _emoji_payload(text, 4000)
        data = {"chat_id": chat_id, "text": text, "disable_web_page_preview": True}
        if silent:
            data["disable_notification"] = "true"
        if kb is not None:
            data["reply_markup"] = json.dumps(kb, ensure_ascii=False)
        if ents:
            data["entities"] = ents
        r = self._call("sendMessage", **data)
        if ents and isinstance(r, dict) and not r.get("ok"):
            log(f"custom emoji rejected: {r.get('description')}")
            data.pop("entities", None)
            r = self._call("sendMessage", **data)
        return r

    def edit(self, chat_id, message_id, text, kb=None):
        text, ents = _emoji_payload(text, 4000)
        data = {"chat_id": chat_id, "message_id": message_id, "text": text,
                "disable_web_page_preview": True}
        if kb is not None:
            data["reply_markup"] = json.dumps(kb, ensure_ascii=False)
        if ents:
            data["entities"] = ents
        r = self._call("editMessageText", **data)
        if ents and isinstance(r, dict) and not r.get("ok"):
            log(f"custom emoji rejected: {r.get('description')}")
            data.pop("entities", None)
            r = self._call("editMessageText", **data)
        return r

    def answer_cb(self, cb_id, text=""):
        self._call("answerCallbackQuery", callback_query_id=cb_id, text=text[:180])

    def send_photo(self, chat_id, path, caption="", kb=None):
        caption, ents = _emoji_payload(caption, 1000)
        def _post(with_ents):
            data = {"chat_id": chat_id, "caption": caption}
            if kb is not None:
                data["reply_markup"] = json.dumps(kb, ensure_ascii=False)
            if with_ents and ents:
                data["caption_entities"] = ents
            with open(path, "rb") as f:
                return self.session.post(f"{self.base}/sendPhoto", data=data, files={"photo": f}, timeout=120)
        try:
            r = _post(True)
            try:
                body = r.json()
            except Exception:
                return {"ok": bool(getattr(r, "ok", False))}
            if ents and isinstance(body, dict) and not body.get("ok"):
                log(f"custom emoji rejected: {body.get('description')}")
                r = _post(False)
                try:
                    return r.json()
                except Exception:
                    return {"ok": bool(getattr(r, "ok", False))}
            return body
        except Exception as exc:
            log(f"send_photo error: {type(exc).__name__}: {exc}")
            return {"ok": False}

    def get_chat_admins(self, chat_id):
        r = self._call("getChatAdministrators", chat_id=chat_id)
        return r.get("result", []) if isinstance(r, dict) else []

    def send_document(self, chat_id, path, caption=""):
        caption, ents = _emoji_payload(caption, 1000)
        def _post(with_ents):
            data = {"chat_id": chat_id, "caption": caption}
            if with_ents and ents:
                data["caption_entities"] = ents
            with open(path, "rb") as f:
                return self.session.post(f"{self.base}/sendDocument", data=data,
                                         files={"document": f}, timeout=120)
        try:
            r = _post(True)
            if ents:
                try:
                    body = r.json()
                except Exception:
                    body = {}
                if isinstance(body, dict) and not body.get("ok"):
                    log(f"custom emoji rejected: {body.get('description')}")
                    r = _post(False)
            return r.ok
        except Exception as exc:
            log(f"send_document error: {type(exc).__name__}: {exc}")
            return False

    def get_updates(self, timeout=25):
        params = {"timeout": timeout, "allowed_updates": json.dumps(["message", "callback_query", "my_chat_member"])}
        if self.offset is not None:
            params["offset"] = self.offset
        try:
            data = self.session.get(f"{self.base}/getUpdates", params=params, timeout=timeout + 15).json()
        except Exception as exc:
            log(f"getUpdates error: {type(exc).__name__}: {exc}")
            time.sleep(3)
            return []
        out = []
        for upd in data.get("result", []) or []:
            self.offset = upd["update_id"] + 1
            cb = upd.get("callback_query")
            if cb:
                frm = cb.get("from") or {}
                msg = cb.get("message") or {}
                out.append({"kind": "callback", "id": cb.get("id"), "data": str(cb.get("data") or ""),
                            "uid": int(frm.get("id") or 0), "username": frm.get("username") or "",
                            "name": frm.get("first_name") or "",
                            "chat_id": (msg.get("chat") or {}).get("id"),
                            "message_id": msg.get("message_id")})
                continue
            mcm = upd.get("my_chat_member")
            if mcm:   # бота добавили/изменили права в канале/группе
                out.append({"kind": "chat_member", "chat": mcm.get("chat") or {},
                            "status": ((mcm.get("new_chat_member") or {}).get("status") or "")})
                continue
            msg = upd.get("message") or {}
            frm = msg.get("from") or {}
            chat = msg.get("chat") or {}
            text = msg.get("text")
            if text is None:
                continue
            out.append({"kind": "text", "text": text.strip(), "uid": int(frm.get("id") or 0),
                        "username": frm.get("username") or "", "name": frm.get("first_name") or "",
                        "chat_id": chat.get("id"), "chat_type": chat.get("type")})
        return out


# ── база данных ──────────────────────────────────────────────────────────────
def db():
    con = sqlite3.connect(str(DB_PATH), timeout=10)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    return con


def db_init():
    con = db()
    con.executescript("""
    CREATE TABLE IF NOT EXISTS operators(
      tg_id INTEGER PRIMARY KEY, username TEXT, name TEXT,
      balance REAL DEFAULT 0, frozen REAL DEFAULT 0,
      rate REAL, rate_until INTEGER DEFAULT 0,
      success_today INTEGER DEFAULT 0, decline_today INTEGER DEFAULT 0, stat_day TEXT DEFAULT '',
      success_total INTEGER DEFAULT 0, fail_streak INTEGER DEFAULT 0,
      banned INTEGER DEFAULT 0, ban_reason TEXT DEFAULT '', created_at INTEGER);
    CREATE TABLE IF NOT EXISTS invites(code TEXT PRIMARY KEY, created_by INTEGER, used_by INTEGER DEFAULT 0, used_at INTEGER DEFAULT 0, created_at INTEGER);
    CREATE TABLE IF NOT EXISTS links(id INTEGER PRIMARY KEY AUTOINCREMENT, url TEXT, status TEXT DEFAULT 'queued',
      added_at INTEGER, paid_by INTEGER DEFAULT 0, reason TEXT DEFAULT '');
    CREATE TABLE IF NOT EXISTS cards(card_hash TEXT PRIMARY KEY, success_count INTEGER DEFAULT 0);
    CREATE TABLE IF NOT EXISTS payments(id INTEGER PRIMARY KEY AUTOINCREMENT, link_id INTEGER, operator_id INTEGER,
      card_mask TEXT, card_hash TEXT DEFAULT '', result TEXT, amount REAL DEFAULT 0, url_final TEXT DEFAULT '', at INTEGER, canceled INTEGER DEFAULT 0);
    CREATE TABLE IF NOT EXISTS channels(chat_id INTEGER PRIMARY KEY, title TEXT, seen_at INTEGER);
    CREATE TABLE IF NOT EXISTS payouts(id INTEGER PRIMARY KEY AUTOINCREMENT, operator_id INTEGER, amount REAL,
      status TEXT DEFAULT 'pending', requested_at INTEGER, decided_at INTEGER DEFAULT 0);
    CREATE TABLE IF NOT EXISTS queue(operator_id INTEGER PRIMARY KEY, joined_at INTEGER, last_action INTEGER);
    CREATE TABLE IF NOT EXISTS settings(k TEXT PRIMARY KEY, v TEXT);
    """)
    # миграции для старых баз
    for tbl, col, decl in [("payments", "card_hash", "TEXT DEFAULT ''")]:
        cols = [r["name"] for r in con.execute(f"PRAGMA table_info({tbl})").fetchall()]
        if col not in cols:
            con.execute(f"ALTER TABLE {tbl} ADD COLUMN {col} {decl}")
    # дефолтные настройки
    defaults = {"default_rate_usd": str(CFG["default_rate_usd"]), "tariff_rub": str(CFG["tariff_rub"]),
                "accepting": "1", "log_channel": ""}
    for k, v in defaults.items():
        con.execute("INSERT OR IGNORE INTO settings(k,v) VALUES(?,?)", (k, v))
    con.commit()
    con.close()


def setting(k, default=""):
    con = db()
    row = con.execute("SELECT v FROM settings WHERE k=?", (k,)).fetchone()
    con.close()
    return row["v"] if row else default


def set_setting(k, v):
    con = db()
    con.execute("INSERT INTO settings(k,v) VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v", (k, str(v)))
    con.commit()
    con.close()


def default_rate():
    try:
        return float(setting("default_rate_usd", str(CFG["default_rate_usd"])))
    except ValueError:
        return float(CFG["default_rate_usd"])


def record_channel(chat):
    cid = chat.get("id")
    if not cid:
        return
    title = chat.get("title") or chat.get("username") or str(cid)
    con = db()
    con.execute("INSERT INTO channels(chat_id,title,seen_at) VALUES(?,?,?) "
                "ON CONFLICT(chat_id) DO UPDATE SET title=excluded.title, seen_at=excluded.seen_at",
                (cid, title, now()))
    con.commit()
    con.close()


def remove_channel(cid):
    con = db()
    con.execute("DELETE FROM channels WHERE chat_id=?", (cid,))
    con.commit()
    con.close()


def list_channels():
    con = db()
    rows = con.execute("SELECT * FROM channels ORDER BY seen_at DESC").fetchall()
    con.close()
    return [dict(r) for r in rows]


def get_op(tg_id):
    con = db()
    row = con.execute("SELECT * FROM operators WHERE tg_id=?", (tg_id,)).fetchone()
    con.close()
    return dict(row) if row else None


def op_rate(op):
    """Актуальная ставка: временная, если не истекла, иначе дефолт/персональная база."""
    if op.get("rate_until") and op["rate_until"] > now() and op.get("rate") is not None:
        return float(op["rate"])
    base = op.get("rate")
    return float(base) if base is not None and not op.get("rate_until") else default_rate()


def ensure_stat_day(tg_id):
    today = time.strftime("%Y-%m-%d", time.gmtime(now() + 3 * 3600))
    con = db()
    row = con.execute("SELECT stat_day FROM operators WHERE tg_id=?", (tg_id,)).fetchone()
    if row and row["stat_day"] != today:
        con.execute("UPDATE operators SET success_today=0, decline_today=0, stat_day=? WHERE tg_id=?", (today, tg_id))
        con.commit()
    con.close()


def add_operator(tg_id, username, name):
    con = db()
    con.execute("INSERT OR IGNORE INTO operators(tg_id,username,name,rate,created_at,stat_day) VALUES(?,?,?,?,?,?)",
                (tg_id, username, name, None, now(), time.strftime("%Y-%m-%d", time.gmtime(now() + 3 * 3600))))
    con.execute("UPDATE operators SET username=?, name=? WHERE tg_id=?", (username, name, tg_id))
    con.commit()
    con.close()


def is_operator(tg_id):
    return get_op(tg_id) is not None


# ── очередь ──────────────────────────────────────────────────────────────────
def queue_list():
    con = db()
    rows = con.execute("SELECT operator_id FROM queue ORDER BY joined_at").fetchall()
    con.close()
    return [r["operator_id"] for r in rows]


def queue_pos(tg_id):
    q = queue_list()
    return q.index(tg_id) + 1 if tg_id in q else 0


def queue_join(tg_id):
    con = db()
    con.execute("INSERT OR IGNORE INTO queue(operator_id,joined_at,last_action) VALUES(?,?,?)", (tg_id, now(), now()))
    con.commit()
    con.close()


def queue_leave(tg_id):
    con = db()
    con.execute("DELETE FROM queue WHERE operator_id=?", (tg_id,))
    con.commit()
    con.close()


# ── ссылки ───────────────────────────────────────────────────────────────────
def links_count(status="queued"):
    con = db()
    n = con.execute("SELECT COUNT(*) c FROM links WHERE status=?", (status,)).fetchone()["c"]
    con.close()
    return n


def add_links(urls):
    con = db()
    added = 0
    for u in urls:
        ex = con.execute("SELECT 1 FROM links WHERE url=? AND status IN('queued','in_progress')", (u,)).fetchone()
        if ex:
            continue
        con.execute("INSERT INTO links(url,status,added_at) VALUES(?, 'queued', ?)", (u, now()))
        added += 1
    con.commit()
    con.close()
    return added


# ── утилиты оформления ───────────────────────────────────────────────────────
SEP = "━━━━━━━━━━━━━━━━━━"


# Кастомные эмодзи (те же, что на кнопках меню, плюс соседние из тех же паков).
# В тексте остаётся обычный знак — Telegram рисует поверх него премиум-иконку.
EMOJI_IDS = {
    "💳": "5927169041595634481",
    "🚪": "5226953054380659263",
    "💸": "5409048419211682843",
    "💰": "5409048419211682843",
    "💵": "5409048419211682843",
    "🔄": "5877410604225924969",
    "🔁": "5877410604225924969",
    "🔗": "5877465816030515018",
    "🟢": "5810051751654460532",
    "✔️": "5206607081334906820",
    "✖️": "5210952531676504517",
    "🔴": "5807626765874499116",
    "🚫": "5807626765874499116",
    "⛔": "5807626765874499116",
    "👥": "5942877472163892475",
    "🧑‍🤝‍🧑": "5942877472163892475",
    "⚠️": "5447644880824181073",
    "⚙️": "5877260593903177342",
    "⚙": "5877260593903177342",
    "⬅️": "5877536313623711363",
    "✅": "5920052658743283381",
    "❌": "5778527486270770928",
    "👤": "5879770735999717115",
    "🔎": "5874960879434338403",
    "🗄": "5967456680940671207",
    "📑": "5839323457015256759",
    "📄": "5839323457015256759",
    "📊": "5931472654660800739",
    "📈": "5776219138917668486",
    "📥": "5877307202888273539",
    "📤": "5877540355187937244",
    "🏷": "5985433648810171091",
    "🗑": "5879896690210639947",
    "🔒": "5832546462478635761",
    "🌐": "5879585266426973039",
    "🤖": "5931415565955503486",
    "🛠": "5988023995125993550",
    "📢": "5771695636411847302",
    "📣": "5260268501515377807",
    "❗️": "5879813604068298387",
    "🕒": "5778605968208170641",
    "💱": "5402186569006210455",
    "⚪️": "5994324703559290598",
    "⏸": "5359543311897998264",
    "⏹": "5807622114424924272",
    "⏳": "5440621591387980068",
    "⌛": "5440621591387980068",
}
_EMOJI_RE = re.compile("|".join(re.escape(k) for k in sorted(EMOJI_IDS, key=len, reverse=True)))


def emoji_entities(text):
    ents = []
    for m in _EMOJI_RE.finditer(text or ""):
        ents.append({
            "type": "custom_emoji",
            "offset": len(text[:m.start()].encode("utf-16-le")) // 2,
            "length": len(m.group().encode("utf-16-le")) // 2,
            "custom_emoji_id": EMOJI_IDS[m.group()],
        })
    return ents


def _emoji_payload(text, limit):
    text = str(text)[:limit]
    ents = emoji_entities(text)
    return text, (json.dumps(ents, ensure_ascii=False) if ents else None)


def kb(rows):
    return {"inline_keyboard": rows}


def btn(text, data, icon=None):
    text = str(text)
    if not icon:
        for em in sorted(EMOJI_IDS, key=len, reverse=True):
            if text.startswith(em):
                icon = EMOJI_IDS[em]
                text = text[len(em):].lstrip()
                break
    b = {"text": text, "callback_data": data}
    if icon:
        b["icon_custom_emoji_id"] = str(icon)
    return b


def accepting():
    return setting("accepting", "1") == "1"


def op_display(op):
    return ("@" + op["username"]) if op.get("username") else ("ID " + str(op["tg_id"]))


# BAD_LINK: ссылка непригодна (не наказываем оператора, уходит в архив админу)
BAD_LINK_WORDS = ("заказ не найден", "заказ не существует", "не найден", "истёк", "истек",
                  "уже оплачен", "оплачен ранее", "оплата получена", "оплата прошла", "уже оплачена",
                  "заказ оплачен", "уже активирован", "esim активирован", "договор зарегистрирован",
                  "страница не найдена", "ничего не найдено", "ссылка недействительна",
                  "срок действия ссылки", "page not found", "заказ выполнен")


# Временный сбой платёжного шлюза (504/502/503, «Gateway Timeout») — не вина оператора, ссылка в очередь
GATEWAY_ERROR_WORDS = ('gateway timeout', 'bad gateway', 'service unavailable', 'internal server error',
                       '"status_code": 5', '"status_code":5', 'шлюз', 'временно недоступ')


def _gateway_error(low):
    return any(w in low for w in GATEWAY_ERROR_WORDS)


# Статус заказа из JSON сайта (как в чекере ссылок beeline): selfregStatus/orderStatus/…
STATUS_KEYS = ("selfregStatus", "orderStatus", "status", "state")
NO_ERROR_CODES = {"", "NONE", "OK", "0", "NULL", "SUCCESS"}
PAYABLE_STATUS = "DOCS_GENERATED"   # заказ ждёт оплаты — его и платим
USED_STATUS = "ESIM_SUCCESS"        # eSIM уже выпущена/активирована — непригодна


# ── валидация карты ──────────────────────────────────────────────────────────
def validate_card(text):
    """Возвращает ((num,exp,cvv), '') либо (None, 'причина')."""
    toks = text.strip().split()
    if len(toks) < 3:
        return None, "пришли в формате: НОМЕР СРОК КОД"
    cvv = re.sub(r"\D", "", toks[-1])
    exp = re.sub(r"\D", "", toks[-2])
    num = "".join(re.sub(r"\D", "", t) for t in toks[:-2])
    if not num or num[0] not in "245":
        return None, "номер должен начинаться с 2 (Мир), 4 (Visa) или 5 (Mastercard)"
    if len(num) != 16:
        return None, "в номере карты должно быть 16 цифр"
    if len(exp) != 4 or not (1 <= int(exp[:2]) <= 12):
        return None, "срок в формате MM/YY, месяц 01–12"
    if len(cvv) != 3:
        return None, "CVV должен быть из 3 цифр"
    return (num, exp, cvv), ""


# ── меню оплатчика ───────────────────────────────────────────────────────────
def operator_menu_text(op):
    ensure_stat_day(op["tg_id"])
    op = get_op(op["tg_id"])
    q = queue_list()
    pos = (q.index(op["tg_id"]) + 1) if op["tg_id"] in q else 0
    in_q = op["tg_id"] in q
    status = "✔️ оплаты требуются" if (accepting() and links_count()) else "⚪️ оплат нет"
    t = (f"💳 ПАНЕЛЬ ОПЛАТЧИКА\n{SEP}\n"
         f"👤 {op_display(op)}\n"
         f"💰 Баланс: {op['balance']:.2f} $" + (f"  (🔒 заморожено {op['frozen']:.2f} $)" if op['frozen'] else "") + "\n"
         f"📊 Ставка: {op_rate(op):.2f} $ / оплата\n\n"
         f"📥 Статус: {status}\n"
         f"📑 В очереди ссылок: {links_count()}\n"
         f"🧑‍🤝‍🧑 Оплатчиков в очереди: {len(q)}\n"
         f"🎯 Ты в очереди: {'да, позиция ' + str(pos) if in_q else 'нет'}\n"
         f"🏷 Сумма за 1 тариф: ~{setting('tariff_rub')} ₽ (своей картой)\n{SEP}")
    rows = []
    if in_q:
        rows.append([btn("Выйти из очереди", "op_leave", "5226953054380659263")])
    else:
        rows.append([btn("Встать в очередь", "op_join", "5348125953090403204")])
    rows.append([btn("Запросить выплату", "op_payout", "5409048419211682843"),
                 btn("Обновить", "op_refresh", "5877410604225924969")])
    return t, kb(rows)


def show_operator_menu(tg, op, chat_id, message_id=None):
    t, k = operator_menu_text(op)
    if message_id:
        tg.edit(chat_id, message_id, t, k)
    else:
        tg.send(chat_id, t, k)


# ── меню админа ──────────────────────────────────────────────────────────────
def admin_menu_text():
    con = db()
    n_ops = con.execute("SELECT COUNT(*) c FROM operators").fetchone()["c"]
    owed = con.execute("SELECT COALESCE(SUM(balance),0)+COALESCE(SUM(frozen),0) s FROM operators").fetchone()["s"]
    n_pay = con.execute("SELECT COUNT(*) c FROM payouts WHERE status='pending'").fetchone()["c"]
    con.close()
    prob = links_count("problem")
    t = (f"🛠 ПАНЕЛЬ АДМИНА\n{SEP}\n"
         f"📥 Приём оплат: {'✔️ включён' if accepting() else '✖️ выключен'}\n"
         f"📑 В очереди: {links_count()}   🗄 Проблемных: {prob}\n"
         f"🧑‍🤝‍🧑 Оплатчиков: {n_ops} (в очереди {len(queue_list())})\n"
         f"💰 Всего к выплате: {owed:.2f} $\n{SEP}")
    admin_in_q = ADMIN_ID in queue_list()
    rows = [
        [btn("Выйти из очереди (оплата)", "adm_leaveq", "5226953054380659263") if admin_in_q
         else btn("Оплатить самому (встать в очередь)", "adm_joinq", "5927169041595634481")],
        [btn("Загрузить ссылки", "adm_load", "5877465816030515018")],
        [btn("Выключить приём", "adm_toggle", "5210952531676504517") if accepting()
         else btn("Включить приём", "adm_toggle", "5206607081334906820")],
        [btn("Оплатчики", "adm_ops", "5942877472163892475")],
        [btn(f"Запросы на выплаты · {n_pay}", "adm_payouts", "5409048419211682843")],
        [btn(f"Проблемные ссылки · {prob}", "adm_prob", "5447644880824181073")],
        [btn("Настройки", "adm_settings", "5877260593903177342")],
    ]
    return t, kb(rows)


def show_admin_menu(tg, chat_id, message_id=None):
    t, k = admin_menu_text()
    if message_id:
        tg.edit(chat_id, message_id, t, k)
    else:
        tg.send(chat_id, t, k)


# ── pending-состояния многошагового ввода ────────────────────────────────────
PENDING = {}   # uid -> {"await": ..., ...}


# ── обработка текста ─────────────────────────────────────────────────────────
def banned_text(op):
    return f"⛔ Вы заблокированы.\nПричина: {op.get('ban_reason') or '—'}\nПоддержка: {ADMIN_CONTACT}"


def handle_command(tg, uid, text):
    """Админские команды. Возвращает True, если обработано."""
    if uid != ADMIN_ID:
        return False
    parts = text.split(maxsplit=1)
    cmd = parts[0].lower()
    arg = parts[1].strip() if len(parts) > 1 else ""
    if cmd == "/sms":
        if not arg.strip():
            tg.send(uid, "Формат: /sms текст рассылки")
            return True
        con = db(); rows = con.execute("SELECT tg_id FROM operators WHERE banned=0").fetchall(); con.close()
        sent = 0
        for r in rows:
            try:
                tg.send(r["tg_id"], f"📢 {arg.strip()}")
                sent += 1
            except Exception:
                pass
        tg.send(uid, f"✅ Рассылка отправлена: {sent} оплатчик(ам).")
        return True
    if cmd == "/stop":
        if ACTIVE is not None:
            STOP_EVENT.set()
            tg.send(uid, "⏹ Останавливаю текущую оплату и освобождаю очередь…")
        else:
            tg.send(uid, "Сейчас активной оплаты нет.")
        return True
    if cmd == "/backup":
        path = do_backup()
        if path:
            tg.send_document(uid, path, "📦 Бэкап базы панели оплат.")
        else:
            tg.send(uid, "Не удалось сделать бэкап.")
        return True
    if cmd == "/invite":
        code = arg.split()[0] if arg else ""
        if not code:
            tg.send(uid, "Формат: /invite <код>")
            return True
        con = db()
        try:
            con.execute("INSERT INTO invites(code,created_by,created_at) VALUES(?,?,?)", (code, uid, now()))
            con.commit()
            tg.send(uid, f"✅ Код приглашения создан: {code}\nОтдай его одному человеку — первый, кто введёт, станет оплатчиком.")
        except sqlite3.IntegrityError:
            tg.send(uid, "Такой код уже существует.")
        con.close()
        return True
    if cmd in ("/ban", "/unban"):
        if not arg:
            tg.send(uid, f"Формат: {cmd} @тег|ID" + (" причина" if cmd == "/ban" else ""))
            return True
        toks = arg.split(maxsplit=1)
        target = toks[0]
        reason = toks[1] if len(toks) > 1 else ""
        op = resolve_operator(target)
        if not op:
            tg.send(uid, "Оплатчик не найден (тег или ID).")
            return True
        con = db()
        if cmd == "/ban":
            con.execute("UPDATE operators SET banned=1, ban_reason=? WHERE tg_id=?", (reason, op["tg_id"]))
            con.execute("DELETE FROM queue WHERE operator_id=?", (op["tg_id"],))
            con.commit()
            con.close()
            tg.send(uid, f"⛔ {op_display(op)} заблокирован. Причина: {reason or '—'}")
            tg.send(op["tg_id"], f"⛔ Вы заблокированы.\nПричина: {reason or '—'}\nПоддержка: {ADMIN_CONTACT}")
        else:
            con.execute("UPDATE operators SET banned=0, ban_reason='' WHERE tg_id=?", (op["tg_id"],))
            con.commit()
            con.close()
            tg.send(uid, f"✅ {op_display(op)} разблокирован.")
            tg.send(op["tg_id"], "✅ Вы разблокированы. Снова можете работать. /start")
        return True
    return False


def resolve_operator(target):
    con = db()
    target = target.strip()
    if target.startswith("@"):
        row = con.execute("SELECT * FROM operators WHERE lower(username)=?", (target[1:].lower(),)).fetchone()
    elif target.lstrip("-").isdigit():
        row = con.execute("SELECT * FROM operators WHERE tg_id=?", (int(target),)).fetchone()
    else:
        row = con.execute("SELECT * FROM operators WHERE lower(username)=?", (target.lower(),)).fetchone()
    con.close()
    return dict(row) if row else None


def try_invite(tg, uid, username, name, code):
    """Пробуем активировать инвайт атомарно (первый победил)."""
    con = db()
    cur = con.execute("UPDATE invites SET used_by=?, used_at=? WHERE code=? AND used_by=0",
                      (uid, now(), code))
    con.commit()
    ok = cur.rowcount == 1
    con.close()
    if ok:
        add_operator(uid, username, name)
        tg.send(uid, "✅ Доступ открыт! Добро пожаловать.")
        show_operator_menu(tg, get_op(uid), uid)
        return True
    return False


def guest_prompt(tg, uid):
    tg.send(uid, f"🔒 Доступ только по приглашению.\n\nПришли код доступа одним сообщением, "
                 f"или запроси его у: {ADMIN_CONTACT}")


def handle_text(tg, ev):
    uid, text = ev["uid"], ev["text"]
    chat_id = ev.get("chat_id")
    # игнорируем сообщения из каналов/групп (панель работает в ЛС)
    if ev.get("chat_type") not in (None, "private"):
        return

    # команды админа
    if text.startswith("/") and handle_command(tg, uid, text):
        return

    # бан
    op = get_op(uid)
    if op and op.get("banned"):
        tg.send(uid, banned_text(op))
        return

    # админ
    if uid == ADMIN_ID:
        st = PENDING.get(uid)
        if st and st.get("await") == "links":
            urls = re.findall(r"https?://\S+", text)
            PENDING.pop(uid, None)
            if not urls:
                tg.send(uid, "Ссылок не нашёл. Отмена.")
            else:
                n = add_links(urls)
                tg.send(uid, f"✅ Добавлено ссылок: {n} (в очереди {links_count()}).")
            show_admin_menu(tg, uid)
            return
        if st and st.get("await") == "set_rate":
            PENDING.pop(uid, None)
            try:
                set_setting("default_rate_usd", float(text.replace(",", ".")))
                tg.send(uid, f"✅ Ставка по умолчанию: {default_rate():.2f} $")
            except ValueError:
                tg.send(uid, "Нужно число, напр. 4.5")
            show_admin_menu(tg, uid)
            return
        if st and st.get("await") == "set_tariff":
            PENDING.pop(uid, None)
            set_setting("tariff_rub", re.sub(r"\D", "", text) or "300")
            tg.send(uid, f"✅ Сумма за тариф: {setting('tariff_rub')} ₽")
            show_admin_menu(tg, uid)
            return
        if st and st.get("await") == "rate_new":
            try:
                rate = float(text.replace(",", "."))
            except ValueError:
                tg.send(uid, "Нужно число, напр. 6")
                return
            PENDING[uid] = {"await": "rate_hours", "op": st["op"], "rate": rate}
            tg.send(uid, "На сколько часов эта ставка? (число; 0 — навсегда)")
            return
        if st and st.get("await") == "rate_hours":
            try:
                hrs = float(text.replace(",", "."))
            except ValueError:
                tg.send(uid, "Нужно число часов, напр. 5")
                return
            opid = st["op"]; rate = st["rate"]
            until = now() + int(hrs * 3600) if hrs > 0 else 0
            con = db()
            con.execute("UPDATE operators SET rate=?, rate_until=? WHERE tg_id=?", (rate, until, opid))
            con.commit()
            con.close()
            PENDING.pop(uid, None)
            when = f"на {hrs:g} ч, потом вернётся к {default_rate():.2f} $" if hrs > 0 else "навсегда"
            tg.send(uid, f"✅ Ставка {rate:.2f} $ {when}.")
            return
        # по умолчанию — меню админа
        show_admin_menu(tg, uid)
        return

    # оплатчик
    if op:
        st = PENDING.get(uid)
        if st and st.get("await") == "card":
            card, err = validate_card(text)
            if err:
                tg.send(uid, f"⚠️ Карта не принята: {err}.\nПришли заново: НОМЕР СРОК КОД")
                return
            PENDING.pop(uid, None)
            # ЭТАП 2: здесь начнётся оплата. Пока — заглушка.
            tg.send(uid, f"💳 Карта принята ({'*' * 8}{card[0][-4:]}). Оплатный движок подключается на Этапе 2.")
            show_operator_menu(tg, op, uid)
            return
        show_operator_menu(tg, op, uid)
        return

    # гость
    code = text.strip()
    if re.fullmatch(r"\S{3,64}", code) and try_invite(tg, uid, ev.get("username"), ev.get("name"), code):
        return
    guest_prompt(tg, uid)


# ── обработка нажатий ────────────────────────────────────────────────────────
def handle_callback(tg, ev):
    uid, data = ev["uid"], ev["data"]
    chat_id, mid, cb_id = ev.get("chat_id"), ev.get("message_id"), ev.get("id")
    tg.answer_cb(cb_id)

    op = get_op(uid)
    if op and op.get("banned"):
        tg.send(uid, banned_text(op))
        return

    # ── админ ──
    if uid == ADMIN_ID:
        if data == "adm_menu":
            show_admin_menu(tg, chat_id, mid); return
        if data == "adm_joinq":
            queue_join(uid); show_admin_menu(tg, chat_id, mid); return
        if data == "adm_leaveq":
            queue_leave(uid); show_admin_menu(tg, chat_id, mid); return
        if data.startswith("cancel_pay:"):
            pid = int(data.split(":")[1])
            con = db(); p = con.execute("SELECT * FROM payments WHERE id=?", (pid,)).fetchone()
            if not p or p["result"] != "success" or p["canceled"]:
                con.close(); tg.answer_cb(cb_id, "Уже отменено или не найдено"); return
            con.execute("UPDATE payments SET canceled=1 WHERE id=?", (pid,))
            if p["card_hash"]:
                con.execute("UPDATE cards SET success_count=max(0, success_count-1) WHERE card_hash=?", (p["card_hash"],))
            opid = p["operator_id"]; amt = p["amount"] or 0.0
            if opid != ADMIN_ID and amt:
                con.execute("UPDATE operators SET balance=balance-? WHERE tg_id=?", (amt, opid))
            con.commit(); con.close()
            tg.answer_cb(cb_id, "Оплата отменена")
            if mid:
                try:
                    tg.edit(chat_id, mid, "🚫 ОПЛАТА ОТМЕНЕНА админом.", None)
                except Exception:
                    pass
            if opid != ADMIN_ID:
                tg.send(opid, f"❗️ Одна из оплат отменена, снято с баланса {amt:.2f} $. Оспорить: {ADMIN_CONTACT}")
            return
        if data == "adm_load":
            PENDING[uid] = {"await": "links"}
            tg.send(uid, "📤 Пришли ссылки (можно пачкой, каждую с новой строки или в одном сообщении).")
            return
        if data == "adm_toggle":
            set_setting("accepting", "0" if accepting() else "1")
            show_admin_menu(tg, chat_id, mid); return
        if data == "adm_ops":
            con = db(); rows = con.execute("SELECT * FROM operators ORDER BY created_at").fetchall(); con.close()
            if not rows:
                tg.edit(chat_id, mid, "🧑‍🤝‍🧑 Оплатчиков пока нет.", kb([[btn("⬅️ Назад", "adm_menu")]])); return
            krows = [[btn(f"{op_display(dict(r))} · {r['balance']:.2f} $", f"op:{r['tg_id']}")] for r in rows]
            krows.append([btn("⬅️ Назад", "adm_menu")])
            tg.edit(chat_id, mid, f"🧑‍🤝‍🧑 ОПЛАТЧИКИ · {len(rows)}", kb(krows)); return
        if data.startswith("op:"):
            opid = int(data[3:]); o = get_op(opid)
            if not o:
                tg.edit(chat_id, mid, "Не найден.", kb([[btn("⬅️ Назад", "adm_ops")]])); return
            ensure_stat_day(opid); o = get_op(opid)
            rate_line = f"{op_rate(o):.2f} $" + (f" (временная до {msk_ts(o['rate_until'])})" if o.get("rate_until") and o["rate_until"] > now() else " (дефолт)")
            t = (f"👤 {op_display(o)}  (ID {o['tg_id']})\n{SEP}\n"
                 f"💰 Баланс: {o['balance']:.2f} $" + (f"  🔒 {o['frozen']:.2f} $" if o['frozen'] else "") + "\n"
                 f"📊 Ставка: {rate_line}\n"
                 f"📈 Сегодня: ✅ {o['success_today']}   ❌ {o['decline_today']}\n"
                 f"🧾 Всего успешных: {o['success_total']}\n{SEP}")
            krows = [[btn("💱 Изменить ставку", f"rate:{opid}")],
                     [btn("⛔ Забанить", f"ban:{opid}") if not o["banned"] else btn("✅ Разбанить", f"unban:{opid}")],
                     [btn("⬅️ Назад", "adm_ops")]]
            tg.edit(chat_id, mid, t, kb(krows)); return
        if data.startswith("rate:"):
            PENDING[uid] = {"await": "rate_new", "op": int(data[5:])}
            tg.send(uid, "Новая ставка в $ (напр. 6):")
            return
        if data.startswith("ban:"):
            opid = int(data[4:]); o = get_op(opid)
            con = db(); con.execute("UPDATE operators SET banned=1 WHERE tg_id=?", (opid,)); con.execute("DELETE FROM queue WHERE operator_id=?", (opid,)); con.commit(); con.close()
            tg.send(uid, f"⛔ {op_display(o)} забанен (без причины — через /ban можно с причиной).")
            tg.send(opid, f"⛔ Вы заблокированы.\nПоддержка: {ADMIN_CONTACT}")
            return
        if data.startswith("unban:"):
            opid = int(data[6:]); o = get_op(opid)
            con = db(); con.execute("UPDATE operators SET banned=0, ban_reason='' WHERE tg_id=?", (opid,)); con.commit(); con.close()
            tg.send(uid, f"✅ {op_display(o)} разбанен."); tg.send(opid, "✅ Вы разблокированы. /start")
            return
        if data == "adm_payouts":
            con = db(); rows = con.execute("SELECT * FROM payouts WHERE status='pending' ORDER BY requested_at").fetchall(); con.close()
            if not rows:
                tg.edit(chat_id, mid, "💸 Запросов на выплату нет.", kb([[btn("⬅️ Назад", "adm_menu")]])); return
            tg.edit(chat_id, mid, f"💸 Запросы на выплаты · {len(rows)} (ниже отдельными сообщениями)", kb([[btn("⬅️ Назад", "adm_menu")]]))
            for r in rows:
                o = get_op(r["operator_id"])
                tg.send(uid, f"💸 ЗАПРОС НА ВЫПЛАТУ\n👤 {op_display(o)} ({r['operator_id']})\nСумма: {r['amount']:.2f} $\nСтатус: ⏳ в ожидании",
                        kb([[btn("✅ Выплачено", f"pay_ok:{r['id']}"), btn("🚫 Заблокировать", f"pay_block:{r['id']}")]]))
            return
        if data.startswith("pay_ok:") or data.startswith("pay_block:"):
            pid = int(data.split(":")[1]); ok = data.startswith("pay_ok:")
            con = db(); r = con.execute("SELECT * FROM payouts WHERE id=?", (pid,)).fetchone()
            if not r or r["status"] != "pending":
                con.close(); tg.send(uid, "Уже обработано."); return
            if ok:
                con.execute("UPDATE payouts SET status='paid', decided_at=? WHERE id=?", (now(), pid))
                con.execute("UPDATE operators SET frozen=frozen-? WHERE tg_id=?", (r["amount"], r["operator_id"]))
                con.commit(); con.close()
                tg.edit(chat_id, mid, f"✅ Выплата {r['amount']:.2f} $ отмечена как выплаченная.", None)
                tg.send(r["operator_id"], f"✅ Выплата {r['amount']:.2f} $ выполнена.")
            else:
                con.execute("UPDATE payouts SET status='blocked', decided_at=? WHERE id=?", (now(), pid))
                con.execute("UPDATE operators SET balance=balance+?, frozen=frozen-? WHERE tg_id=?", (r["amount"], r["amount"], r["operator_id"]))
                con.commit(); con.close()
                tg.edit(chat_id, mid, f"🚫 Выплата {r['amount']:.2f} $ заблокирована, баланс возвращён оператору.", None)
                tg.send(r["operator_id"], f"🚫 Выплата {r['amount']:.2f} $ отклонена, сумма возвращена на баланс. Вопросы: {ADMIN_CONTACT}")
            return
        if data == "adm_prob":
            con = db(); rows = con.execute("SELECT * FROM links WHERE status='problem' ORDER BY added_at").fetchall(); con.close()
            if not rows:
                tg.edit(chat_id, mid, "🗄 Проблемных ссылок нет.", kb([[btn("⬅️ Назад", "adm_menu")]])); return
            tg.edit(chat_id, mid, f"🗄 Проблемные ссылки · {len(rows)} (ниже)", kb([[btn("⬅️ Назад", "adm_menu")]]))
            for r in rows:
                tg.send(uid, f"🗄 ПРОБЛЕМНАЯ ССЫЛКА\n{r['url']}\nПричина: {r['reason'] or '—'}\n🕒 {msk_ts(r['added_at'])}",
                        kb([[btn("♻️ Вернуть в очередь", f"prob_ret:{r['id']}"), btn("🗑 Удалить", f"prob_del:{r['id']}")]]))
            return
        if data.startswith("prob_ret:") or data.startswith("prob_del:"):
            lid = int(data.split(":")[1]); ret = data.startswith("prob_ret:")
            con = db(); con.execute("UPDATE links SET status=? WHERE id=?", ("queued" if ret else "deleted", lid)); con.commit(); con.close()
            tg.edit(chat_id, mid, ("♻️ Ссылка возвращена в очередь." if ret else "🗑 Ссылка удалена."), None)
            return
        if data == "adm_settings":
            t = (f"⚙️ НАСТРОЙКИ\n{SEP}\n💵 Ставка по умолчанию: {default_rate():.2f} $\n"
                 f"🏷 Сумма за тариф: {setting('tariff_rub')} ₽\n"
                 f"📣 Канал логов: {setting('log_channel') or '—'}\n{SEP}")
            krows = [[btn("💵 Ставка по умолчанию", "set_rate")], [btn("🏷 Сумма за тариф", "set_tariff")],
                     [btn("📣 Выбрать канал логов", "set_channel")], [btn("⬅️ Назад", "adm_menu")]]
            tg.edit(chat_id, mid, t, kb(krows)); return
        if data == "set_rate":
            PENDING[uid] = {"await": "set_rate"}; tg.send(uid, "Новая ставка по умолчанию в $ (напр. 4.5):"); return
        if data == "set_tariff":
            PENDING[uid] = {"await": "set_tariff"}; tg.send(uid, "Сумма за тариф в ₽ (напр. 300):"); return
        if data == "set_channel":
            chs = list_channels()
            if not chs:
                tg.edit(chat_id, mid, "📣 Пока не вижу каналов. Добавь бота в канал АДМИНОМ (право слать сообщения), "
                        "потом нажми «Обновить».", kb([[btn("🔄 Обновить", "set_channel")], [btn("⬅️ Назад", "adm_settings")]]))
                return
            cur_ch = setting("log_channel")
            krows = [[btn(("✅ " if str(c["chat_id"]) == cur_ch else "") + (c["title"] or str(c["chat_id"])),
                          f"setch:{c['chat_id']}")] for c in chs]
            krows.append([btn("⬅️ Назад", "adm_settings")])
            tg.edit(chat_id, mid, "📣 Выбери канал логов (бот должен быть там админом):", kb(krows))
            return
        if data.startswith("setch:"):
            cid = data.split(":")[1]
            set_setting("log_channel", cid)
            r = tg.send(int(cid), "✅ Этот канал выбран для логов панели оплат.")
            ok = isinstance(r, dict) and r.get("ok")
            tg.edit(chat_id, mid, ("📣 Канал логов установлен." if ok else
                    "⚠️ Не смог отправить в канал — проверь, что бот там админ. Канал всё равно сохранён."),
                    kb([[btn("⬅️ Назад", "adm_settings")]]))
            return
        return

    # ── оплатчик ──
    if op:
        if data == "op_refresh":
            show_operator_menu(tg, op, chat_id, mid); return
        if data == "op_join":
            if not accepting():
                tg.answer_cb(cb_id, "Приём оплат выключен");
            queue_join(uid); show_operator_menu(tg, op, chat_id, mid); return
        if data == "op_leave":
            queue_leave(uid); show_operator_menu(tg, op, chat_id, mid); return
        if data == "op_payout":
            o = get_op(uid)
            if o["balance"] <= 0:
                tg.send(uid, "Баланс пустой — выплачивать нечего."); return
            tg.send(uid, f"💸 ВЫПЛАТА\nК выплате: {o['balance']:.2f} $ (весь баланс)\n"
                         "После запроса баланс замораживается до решения админа.",
                    kb([[btn(f"✅ Запросить {o['balance']:.2f} $", "op_payout_go")], [btn("⬅️ Отмена", "op_refresh")]]))
            return
        if data == "op_payout_go":
            con = db()
            o = con.execute("SELECT * FROM operators WHERE tg_id=?", (uid,)).fetchone()
            amt = o["balance"]
            if amt <= 0:
                con.close(); tg.send(uid, "Баланс пустой."); return
            con.execute("UPDATE operators SET balance=0, frozen=frozen+? WHERE tg_id=?", (amt, uid))
            cur = con.execute("INSERT INTO payouts(operator_id,amount,status,requested_at) VALUES(?,?, 'pending', ?)", (uid, amt, now()))
            pid = cur.lastrowid
            con.commit(); con.close()
            tg.send(uid, f"📨 Запрос на выплату {amt:.2f} $ отправлен. Баланс заморожен до решения админа.")
            od = get_op(uid)
            tg.send(ADMIN_ID, f"💸 Новый запрос на выплату\n👤 {op_display(od)} ({uid})\nСумма: {amt:.2f} $",
                    kb([[btn("✅ Выплачено", f"pay_ok:{pid}"), btn("🚫 Заблокировать", f"pay_block:{pid}")]]))
            return
        return

    # гость нажал что-то
    guest_prompt(tg, uid)


# ══════════════════════ ЭТАП 2: ДВИЖОК ОПЛАТЫ ══════════════════════════════════
ACTIVE = None                      # {"payer": tg_id, "io": PayerIO, "thread": ...} или None
ACTIVE_LOCK = threading.Lock()
STOP_EVENT = threading.Event()     # аварийный стоп текущей сессии (/stop админом)
_ENGINE = None
CONSEC_BEELINE = 0                 # подряд «мгновенных сбоев Билайна» → подозрение на бан IP
CONSEC_GATEWAY = 0                 # подряд сбоев платёжного шлюза (504…) → шлюз лежит


def engine():
    """Ленивая загрузка движка оплаты из pay_bot.py (рядом). Нужен playwright."""
    global _ENGINE
    if _ENGINE is None:
        sys.path.insert(0, str(BASE_DIR))
        import pay_bot as _pb
        _ENGINE = _pb
    return _ENGINE


class PayerIO:
    """Мост между движком оплаты и Telegram: сообщения идут активному оплатчику, его входящие
    события (код, кнопки) главный цикл кладёт в inbox."""
    def __init__(self, tg, payer_id):
        self.tg = tg
        self.payer_id = payer_id
        self.inbox = _queue.Queue()

    # интерфейс, совместимый с pay_bot (send/send_photo/get_updates/answer_callback)
    def send(self, text, reply_markup=None):
        self.tg.send(self.payer_id, text, reply_markup)

    def bg(self, text):
        """Служебный статус в фон: оператору не пишем и не пушим.
        Тихая копия — только в канал логов, если он задан."""
        log(f"фон uid={self.payer_id}: {text}")
        ch = setting("log_channel")
        if ch:
            self.tg.send(ch, f"🕯 {text}", silent=True)

    def send_photo(self, path, caption=""):
        self.tg.send_photo(self.payer_id, path, caption)

    def get_updates(self, timeout=25):
        try:
            return [self.inbox.get(timeout=timeout)]
        except _queue.Empty:
            return []

    def answer_callback(self, cb_id):
        self.tg.answer_cb(cb_id)

    # панельные помощники
    def put(self, ev):
        self.inbox.put(ev)

    def wait(self, timeout):
        try:
            return self.inbox.get(timeout=max(0.5, timeout))
        except _queue.Empty:
            return None

    def answer(self, ev):
        if ev.get("kind") == "callback":
            self.tg.answer_cb(ev.get("id"))


# ── карты, ссылки, учёт ──────────────────────────────────────────────────────
def card_hash(card):
    return hashlib.sha256("".join(card).encode()).hexdigest()


def card_uses(card):
    con = db()
    r = con.execute("SELECT success_count FROM cards WHERE card_hash=?", (card_hash(card),)).fetchone()
    con.close()
    return r["success_count"] if r else 0


def mask_pan(card):
    return "****" + card[0][-4:]


def take_next_link():
    con = db()
    r = con.execute("SELECT * FROM links WHERE status='queued' ORDER BY id LIMIT 1").fetchone()
    if r:
        con.execute("UPDATE links SET status='in_progress' WHERE id=?", (r["id"],))
        con.commit()
    con.close()
    return dict(r) if r else None


def requeue_link(link):
    con = db()
    con.execute("UPDATE links SET status='queued' WHERE id=? AND status='in_progress'", (link["id"],))
    con.commit()
    con.close()


def mark_problem(link, reason):
    con = db()
    con.execute("UPDATE links SET status='problem', reason=? WHERE id=?", (reason, link["id"]))
    con.commit()
    con.close()


def record_success(tg, payer_id, link, card, is_admin, io, shot=None):
    con = db()
    con.execute("UPDATE links SET status='paid', paid_by=? WHERE id=?", (payer_id, link["id"]))
    ch = card_hash(card)
    con.execute("INSERT INTO cards(card_hash,success_count) VALUES(?,1) "
                "ON CONFLICT(card_hash) DO UPDATE SET success_count=success_count+1", (ch,))
    uses = con.execute("SELECT success_count FROM cards WHERE card_hash=?", (ch,)).fetchone()["success_count"]
    amount = 0.0
    if not is_admin:
        o = get_op(payer_id)
        amount = op_rate(o)
        ensure_stat_day(payer_id)
        con.execute("UPDATE operators SET balance=balance+?, success_today=success_today+1, "
                    "success_total=success_total+1, fail_streak=0 WHERE tg_id=?", (amount, payer_id))
    cur = con.execute("INSERT INTO payments(link_id,operator_id,card_mask,card_hash,result,amount,url_final,at) "
                      "VALUES(?,?,?,?,?,?,?,?)",
                      (link["id"], payer_id, mask_pan(card), ch, "success", amount, link["url"], now()))
    pay_id = cur.lastrowid
    con.commit()
    con.close()
    if is_admin:
        io.send(f"✅ ОПЛАТА ПРОШЛА!\n💳 Карта {mask_pan(card)} — {uses}/3\n📑 Ещё в очереди: {links_count()}")
    else:
        o = get_op(payer_id)
        io.send(f"✅ ОПЛАТА ПРОШЛА!  +{amount:.2f} $\n{SEP}\n💰 Баланс: {o['balance']:.2f} $\n"
                f"💳 Карта {mask_pan(card)} — {uses}/3\n📑 Ещё в очереди: {links_count()}")
    log_payment(tg, pay_id, payer_id, link, card, uses, amount, "success", shot)
    return uses


def record_decline(tg, payer_id, link, card, is_admin, io, shot=None):
    con = db()
    cur = con.execute("INSERT INTO payments(link_id,operator_id,card_mask,card_hash,result,at) VALUES(?,?,?,?,?,?)",
                      (link["id"], payer_id, mask_pan(card), card_hash(card), "decline", now()))
    pay_id = cur.lastrowid
    streak = 0
    if not is_admin:
        ensure_stat_day(payer_id)
        con.execute("UPDATE operators SET decline_today=decline_today+1, fail_streak=fail_streak+1 WHERE tg_id=?", (payer_id,))
        streak = con.execute("SELECT fail_streak FROM operators WHERE tg_id=?", (payer_id,)).fetchone()["fail_streak"]
    con.commit()
    con.close()
    msg = ("❌ ОПЛАТА НЕ ПРОШЛА\n"
           "Возможно, недостаточно средств либо карта заблокирована.\n"
           "⚠️ Если этой картой уже платили раньше (сам или кому-то) — Билайн может отклонять сам; "
           "3 оплаты с карты — его жёсткий лимит.\n"
           f"Поддержка: {ADMIN_CONTACT}")
    if (not is_admin) and streak >= 3:
        msg += "\n\n⚠️ При множестве неудачных оплат ваш аккаунт может быть ограничен."
    io.send(msg)
    log_payment(tg, pay_id, payer_id, link, card, card_uses(card), 0.0, "decline", shot)


def log_payment(tg, pay_id, payer_id, link, card, uses, amount, result, shot=None):
    ch = setting("log_channel")
    o = get_op(payer_id)
    who = op_display(o) if o else (f"АДМИН ({payer_id})" if payer_id == ADMIN_ID else str(payer_id))
    head = "✅ УСПЕШНАЯ ОПЛАТА" if result == "success" else "❌ ОПЛАТА НЕ ПРОШЛА"
    text = f"{head}\n👤 {who}\n💳 {mask_pan(card)} ({uses}/3)" + (f"  (+{amount:.2f} $)" if amount else "") + \
           f"\n🔗 {link['url']}\n🕒 {msk_ts()}"
    markup = kb([[btn("🚫 Отмена оплаты", f"cancel_pay:{pay_id}")]]) if result == "success" else None
    has_shot = bool(shot and os.path.exists(shot))

    def _deliver(target, prefix=""):
        if has_shot:
            r = tg.send_photo(target, shot, (prefix + text)[:1000], markup)
        else:
            r = tg.send(target, prefix + text, markup)
        return isinstance(r, dict) and r.get("ok")

    ok = _deliver(ch) if ch else False
    if ch and not ok:
        log("log_channel send failed; fallback admin")
    if not ok:
        _deliver(ADMIN_ID, "(канал логов не задан/недоступен)\n")
    if has_shot:
        try:
            os.unlink(shot)
        except OSError:
            pass


# ── ИИ-агент для нераспознанного 3DS (строго ограниченный набор действий) ────
AI_SYS = ("Ты помогаешь ввести код 3DS на платёжной странице банка. Тебе дают список элементов "
          "страницы (поля и кнопки с индексами) и просьбу оператора простыми словами. "
          "Верни СТРОГО JSON без пояснений:\n"
          '{"fill": <индекс поля для кода>, "click": <индекс кнопки подтверждения, или -1 если нет>}\n'
          'Если не понял, где поле: {"status":"not_found","say":"<очень коротко по-русски, что непонятно>"}\n'
          'Если просьба не про эту страницу (закрыть браузер, выключить сервер, болтовня): {"status":"off_topic"}\n'
          "Отвечай ТОЛЬКО JSON. Без кода сайта, без терминов, по-русски. Коротко.")


def deepseek_chat(cfg, system, user, timeout=25):
    key = str(cfg.get("deepseek_api_key") or "").strip()
    if not key:
        return ""
    url = cfg.get("deepseek_url") or "https://api.deepseek.com/chat/completions"
    model = cfg.get("deepseek_model") or "deepseek-chat"
    proxy = str(cfg.get("ds_proxy") or cfg.get("proxy") or "").strip()
    proxies = None
    if proxy and proxy.lower() not in ("direct", "none", "off", "no", "-"):
        proxies = {"https": proxy, "http": proxy}
    try:
        r = requests.post(url, headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                          json={"model": model, "temperature": 0, "max_tokens": 200,
                                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]},
                          proxies=proxies, timeout=timeout)
        return ((r.json().get("choices") or [{}])[0].get("message") or {}).get("content", "") or ""
    except Exception as exc:
        log(f"deepseek error: {exc}")
        return ""


def collect_elements(page):
    pb = engine()
    items, handles = [], []
    for fr in pb._frames(page):
        try:
            for h in pb._visible_inputs(fr):
                items.append({"i": len(items), "вид": "поле",
                              "подпись": (h.get_attribute("placeholder") or h.get_attribute("name")
                                          or h.get_attribute("id") or "")[:30],
                              "тип": h.get_attribute("type") or "text"})
                handles.append(h)
        except Exception:
            pass
        for sel in ("button", "[role=button]", "a"):
            try:
                loc = fr.locator(sel); n = min(loc.count(), 12)
            except Exception:
                n = 0
            for j in range(n):
                el = loc.nth(j)
                try:
                    if not el.is_visible():
                        continue
                    txt = (el.inner_text(timeout=400) or "").strip()
                    if not txt:
                        continue
                    items.append({"i": len(items), "вид": "кнопка", "текст": txt[:40]})
                    handles.append(el)
                except Exception:
                    continue
    return items, handles


def _extract_code(text):
    m = re.search(r"\b(\d{3,8})\b", text or "")
    return m.group(1) if m else ""


def ai_execute(handles, fill_idx, click_idx, code):
    try:
        h = handles[int(fill_idx)]
        h.click()
        try:
            h.fill("")
        except Exception:
            pass
        h.type(re.sub(r"\D", "", code), delay=80)
    except Exception:
        return False
    try:
        ci = int(click_idx)
    except Exception:
        ci = -1
    if 0 <= ci < len(handles):
        try:
            handles[ci].click(timeout=3000)
        except Exception:
            pass
    else:
        try:
            handles[int(fill_idx)].press("Enter")
        except Exception:
            pass
    return True


def ai_assist(io, page, cfg):
    """Нераспознанный 3DS: скрин + «Вызвать ИИ-агента». Возвращает 'success'/'decline'/'give_up'."""
    pb = engine()
    shot = pb._shot(page, "unknown3ds")
    if shot:
        io.send_photo(shot, "⚠️ Не могу сам найти поле кода на этой странице банка.")
        try:
            os.unlink(shot)
        except OSError:
            pass
    ch = ask_buttons(io, "Что делаем?",
                     [[btn("🤖 Вызвать ИИ-агента", "ai_call")], [btn("🚫 Отменить оплату", "ai_cancel")]],
                     int(cfg.get("newcard_timeout_s") or 300), {"ai_call": "call", "ai_cancel": "cancel"})
    if ch != "call":
        return "give_up"
    tout = int(cfg.get("newcard_timeout_s") or 300)
    for attempt in range(1, 3):
        io.send("Подскажи простыми словами: где поле ввода кода и что нажать. "
                "И пришли код из СМС (можно в этом же сообщении). Или «отмена».")
        instr = None
        deadline = time.monotonic() + tout
        while time.monotonic() < deadline:
            ev = io.wait(min(20, deadline - time.monotonic()))
            if ev is None:
                continue
            if ev.get("kind") == "callback":
                io.answer(ev)
                if ev.get("data") in ("ai_cancel", "op_leave"):
                    return "give_up"
                continue
            t = (ev.get("text") or "").strip()
            if t.lower() in ("отмена", "stop", "/stop"):
                return "give_up"
            instr = t
            break
        if instr is None:
            return "give_up"
        io.send("🤖 ИИ-агент работает…")
        code = _extract_code(instr)
        items, handles = collect_elements(page)
        user = "Элементы страницы:\n" + json.dumps(items, ensure_ascii=False) + f"\n\nПросьба оператора: {instr}"
        out = deepseek_chat(cfg, AI_SYS, user)
        data = {}
        try:
            data = json.loads(re.search(r"\{.*\}", out, re.S).group(0))
        except Exception:
            data = {}
        if data.get("status") == "off_topic":
            io.send("Поступил ответ от ИИ-агента: давай по теме — куда нажимать на этой странице.")
            continue
        if data.get("status") == "not_found" or "fill" not in data:
            say = (data.get("say") or "не понял, где поле кода")[:120]
            io.send(f"Поступил ответ от ИИ-агента: не получилось — {say}. Попробуй объяснить по-другому.")
            continue
        if not code:
            io.send("Поступил ответ от ИИ-агента: не вижу кода из СМС — пришли код цифрами ещё раз с объяснением.")
            continue
        if not ai_execute(handles, data.get("fill"), data.get("click"), code):
            io.send("Поступил ответ от ИИ-агента: не смог вписать/нажать по описанию. Попробуй по-другому.")
            continue
        final = pb._wait_final_result(page, timeout_s=int(cfg.get("final_wait_seconds") or 70))
        if final == "success":
            return "success"
        if final == "fail":
            return "decline"
        io.send("Поступил ответ от ИИ-агента: нажал, но страница не ответила — возможно, есть другой вариант?")
    io.send(f"🤖 Не получилось распознать эту форму. Оплата отменяется. Можно отдать на ручную оплату — напиши {ADMIN_CONTACT}.")
    return "give_up"


# ── бэкап базы ───────────────────────────────────────────────────────────────
def do_backup():
    import shutil
    bdir = BASE_DIR / "backups"
    bdir.mkdir(exist_ok=True)
    dst = bdir / f"pay_panel_{time.strftime('%Y%m%d_%H%M')}.sqlite3"
    try:
        shutil.copy2(DB_PATH, dst)
    except Exception as exc:
        log(f"backup error: {exc}")
        return None
    # держим последние 10
    files = sorted(bdir.glob("pay_panel_*.sqlite3"))
    for old in files[:-10]:
        try:
            old.unlink()
        except OSError:
            pass
    return str(dst)


# ── оплата одной ссылки (переиспользует pay_bot) ─────────────────────────────
def pay_one_link(io, browser, url, card, cfg, shot_holder=None):
    """Один заход: открыть ссылку → карта → банк/3DS/YooMoney → итог. Карту НЕ меняет (это делает
    панель). Возвращает: success / decline / beeline / no_code / site / cancel / timeout.
    В shot_holder["path"] кладёт скрин финальной страницы (для лога)."""
    pb = engine()
    page_wait = int(cfg.get("page_wait_seconds") or 240)
    code_wait = int(cfg.get("code_wait_seconds") or 300)
    ctx_kwargs = {"locale": "ru-RU"}
    bproxy = str(cfg.get("browser_proxy") or "").strip()
    if bproxy and bproxy.lower() not in ("direct", "none", "off", "no", "-"):
        ctx_kwargs["proxy"] = {"server": bproxy}
    ctx = browser.new_context(**ctx_kwargs)
    page = ctx.new_page()
    page.set_default_timeout(60000)
    seen = {"status": "", "error": ""}

    def _on_resp(resp):
        try:
            u = resp.url.lower()
            if "selfreg" not in u and "order" not in u:
                return
            if "json" not in str(resp.headers.get("content-type", "")):
                return
            body = resp.json()
            data = body.get("data") if isinstance(body, dict) and isinstance(body.get("data"), dict) else body
            if isinstance(data, dict):
                for k in STATUS_KEYS:
                    v = data.get(k)
                    if isinstance(v, (str, int)) and str(v).strip():
                        seen["status"] = str(v).strip().upper()
                        break
                code = data.get("errorCode")
                if code is not None and str(code).strip().upper() not in NO_ERROR_CODES:
                    seen["error"] = str(code)
        except Exception:
            pass

    try:
        page.on("response", _on_resp)
        io.send("🔎Открываю оплату...")
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=90000)
        except Exception:
            if any(w in pb._page_text(page) for w in BAD_LINK_WORDS):
                return "bad_link"
            return "site"
        # ждём, пока сайт сообщит статус заказа в JSON (как чекер ссылок) — до ~10 сек
        sdeadline = time.monotonic() + 10
        while time.monotonic() < sdeadline and not seen["status"] and not seen["error"]:
            if STOP_EVENT.is_set():
                return "stopped"
            page.wait_for_timeout(300)
        # eSIM уже выпущена/активирована или ошибка сайта → ссылка непригодна (за секунды)
        if seen["error"] or seen["status"] == USED_STATUS:
            return "bad_link"
        low = pb._page_text(page)
        if _gateway_error(low):
            return "gateway"   # 504/502/503 при открытии — сбой платёжного шлюза
        if pb._url_status(page) == "success" or any(w in low for w in BAD_LINK_WORDS):
            return "bad_link"
        # Ищем ВХОДНУЮ кнопку «Перейти к оплате». На рабочей ссылке она есть почти сразу; на уже
        # оплаченной/активированной её нет — такую отбиваем за секунды, не ждём форму оплаты.
        pay_wait = int(cfg.get("pay_button_wait_s") or 20)
        bdeadline = time.monotonic() + pay_wait
        found_pay = False
        while time.monotonic() < bdeadline:
            if STOP_EVENT.is_set():
                return "stopped"
            low = pb._page_text(page)
            if pb._url_status(page) == "success" or any(w in low for w in BAD_LINK_WORDS):
                return "bad_link"
            if pb._payment_failed(page) or pb._url_status(page) == "fail":
                return "beeline"
            if pb._on_card_form(page):   # форма карты уже открыта (без входной кнопки)
                found_pay = True
                break
            if pb._click_by_words(page.main_frame, pb.PAY_BUTTON_WORDS, timeout_ms=2000):
                found_pay = True
                break
            page.wait_for_timeout(1200)
        if not found_pay:
            return "bad_link"   # нет кнопки оплаты → ссылка уже оплачена/непригодна
        # дальше (после входной кнопки) ждём форму/«оплатить» — тут Билайн может лагать, это нормально
        io.send(f"💳 Перешёл к оплате, ввожу карту {mask_pan(card)}…")
        deadline = time.monotonic() + int(cfg.get("card_form_wait_s") or 120)
        try:
            pb._type_card(page, card, io, deadline)
        except RuntimeError:
            if pb._payment_failed(page) or pb._url_status(page) == "fail":
                return "beeline"
            if any(w in pb._page_text(page) for w in BAD_LINK_WORDS):
                return "bad_link"
            return "site"
        page.wait_for_timeout(3000)
        io.send("⏳ Жду ответ банка (3DS)…")
        nav = time.monotonic() + page_wait
        c0 = time.monotonic()
        branch = "wait"
        while time.monotonic() < nav:
            if pb._payment_failed(page) or pb._url_status(page) == "fail":
                return "beeline"
            if pb._url_status(page) == "success":
                return "success"
            low = pb._page_text(page)
            if _gateway_error(low):
                return "gateway"   # 504/502/503 — сбой платёжного шлюза (не пуш)
            if any(w in low for w in pb.DECLINE_WORDS):
                return "decline"
            fr, h = pb._find_code_field(page)
            if h is not None:
                branch = "code"
                break
            if pb._is_yoomoney(page) and (time.monotonic() - c0) > 8:
                branch = "yoomoney"
                break
            page.wait_for_timeout(500)
        if branch == "wait":
            r = ai_assist(io, page, cfg)   # PAY_AI_1591: интерактивный ИИ-агент на незнакомом 3DS
            return r if r in ("success", "decline") else "no_code"
        if branch == "yoomoney":
            yoo = pb._yoomoney_push_flow(page, io, cfg)
            if yoo == "success":
                return "success"
            if yoo == "fail":
                return "decline"
            if yoo == "timeout":
                return "no_code"
        verdict = pb._enter_3ds_code(page, io, cfg, page_wait, code_wait)
        if verdict == "cancelled":
            return "cancel"
        if verdict == "timeout":
            return "timeout"
        if verdict == "declined":
            return "decline"
        final = pb._wait_final_result(page, timeout_s=int(cfg.get("final_wait_seconds") or 70))
        if final == "success":
            return "success"
        if final == "fail":
            return "decline"
        return "no_code"
    except Exception:
        log("pay_one_link error:\n" + traceback.format_exc())
        return "site"
    finally:
        if shot_holder is not None:
            try:
                shot_holder["path"] = pb._shot(page, "final")
            except Exception:
                shot_holder["path"] = None
        try:
            ctx.close()
        except Exception:
            pass


# ── ожидания в сессии ────────────────────────────────────────────────────────
def wait_card(io, timeout, prompt=True):
    if prompt:
        io.send("💳 Пришли карту одним сообщением: НОМЕР СРОК КОД (или «отмена»).",
                kb([[btn("🚪 Выйти из очереди", "op_leave")]]))
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if STOP_EVENT.is_set():
            return None
        ev = io.wait(min(20, deadline - time.monotonic()))
        if ev is None:
            continue
        if ev.get("kind") == "callback":
            io.answer(ev)
            if ev.get("data") in ("op_leave", "sess_finish"):
                return None
            continue
        t = (ev.get("text") or "").strip()
        if t.lower() in ("отмена", "stop", "/stop", "cancel"):
            return None
        card, err = validate_card(t)
        if err:
            io.send(f"⚠️ Карта не принята: {err}.\nПришли заново: НОМЕР СРОК КОД")
            continue
        if card_uses(card) >= 3:
            io.send("⛔ Эта карта уже использована 3/3 (лимит Билайна). Пришли другую карту.")
            continue
        return card
    return None


def ask_buttons(io, text, buttons, timeout, mapping):
    io.send(text, kb(buttons))
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if STOP_EVENT.is_set():
            return "finish"
        ev = io.wait(min(20, deadline - time.monotonic()))
        if ev is None:
            continue
        if ev.get("kind") == "callback":
            io.answer(ev)
            d = ev.get("data")
            if d in mapping:
                return mapping[d]
            if d == "op_leave":
                return "finish"
        else:
            t = (ev.get("text") or "").strip().lower()
            if t in ("отмена", "stop", "/stop", "закончить"):
                return "finish"
    return None


# ── сессия одного оплатчика ──────────────────────────────────────────────────
def session_loop(tg, io, browser, payer_id, card, is_admin):
    global CONSEC_BEELINE, CONSEC_GATEWAY
    cur_card = card
    beeline_tries = 0
    link = None
    while True:
        # карта исчерпана → новая/закончить
        if card_uses(cur_card) >= 3:
            ch = ask_buttons(io, f"⛔ Карта {mask_pan(cur_card)} — 3/3. Лимит Билайна, больше нельзя.",
                             [[btn("💳 Ввести новую карту", "sess_newcard")], [btn("🚪 Закончить работу", "sess_finish")]],
                             int(CFG["newcard_timeout_s"]), {"sess_newcard": "new", "sess_finish": "finish"})
            if ch == "new":
                nc = wait_card(io, int(CFG["newcard_timeout_s"]))
                if nc is None:
                    break
                cur_card = nc
                beeline_tries = 0
                continue
            break
        # взять ссылку
        if link is None:
            link = take_next_link()
            if link is None:
                io.send("📑 Ссылки кончились. Ты остаёшься в очереди — как появятся новые, продолжим.")
                return   # НЕ выходим из очереди
        shot_holder = {}
        res = pay_one_link(io, browser, link["url"], cur_card, CFG, shot_holder)
        shot = shot_holder.get("path")
        if res not in ("success", "decline") and shot and os.path.exists(shot):
            try:
                os.unlink(shot)
            except OSError:
                pass
            shot = None

        if res == "stopped":
            requeue_link(link)
            io.send("⏹ Остановлено админом. Ты вышел из очереди.")
            break

        if res == "success":
            uses = record_success(tg, payer_id, link, cur_card, is_admin, io, shot)
            link = None
            beeline_tries = 0
            CONSEC_BEELINE = 0
            CONSEC_GATEWAY = 0
            if uses >= 3:
                ch = ask_buttons(io, f"⛔ Карта {mask_pan(cur_card)} — 3/3. Нужна новая.",
                                 [[btn("💳 Ввести новую карту", "sess_newcard")], [btn("🚪 Закончить работу", "sess_finish")]],
                                 int(CFG["newcard_timeout_s"]), {"sess_newcard": "new", "sess_finish": "finish"})
                if ch == "new":
                    nc = wait_card(io, int(CFG["newcard_timeout_s"]))
                    if nc is None:
                        break
                    cur_card = nc
                    continue
                break
            ch = ask_buttons(io, "Продолжаем?",
                             [[btn("💳 Брать карту дальше", "sess_next")], [btn("🚪 Закончить работу", "sess_finish")]],
                             int(CFG["idle_timeout_s"]), {"sess_next": "next", "sess_finish": "finish"})
            if ch != "next":
                break
            continue

        if res == "beeline":
            beeline_tries += 1
            if beeline_tries <= 3:
                io.bg(f"Оплата не прошла моментально — ошибка на стороне Билайна, "
                      f"пробую ещё раз ({beeline_tries}/3).\n{link['url']}")
                continue   # та же ссылка, та же карта
            io.send("❌ Билайн подряд не проводит эту ссылку — вернул её в очередь, беру следующую.")
            requeue_link(link); link = None; beeline_tries = 0
            CONSEC_BEELINE += 1
            if CONSEC_BEELINE >= 4:
                set_setting("accepting", "0")
                tg.send(ADMIN_ID, "⚠️ Похоже на блокировку IP: Билайн подряд не проводит оплаты. "
                                  "Приём оплат ВЫКЛЮЧЕН. Проверь прокси/IP, потом включи приём снова.")
                io.send("⏸ Пауза: Билайн временно не проводит оплаты. Попробуй позже.")
                queue_leave(payer_id)
                return
            continue

        if res == "decline":
            record_decline(tg, payer_id, link, cur_card, is_admin, io, shot)
            ch = ask_buttons(io, "Что делаем?",
                             [[btn("🔁 Повторить этой картой", "sess_same")],
                              [btn("💳 Ввести новую карту", "sess_newcard")],
                              [btn("🚪 Закончить работу", "sess_finish")]],
                             int(CFG["newcard_timeout_s"]),
                             {"sess_same": "same", "sess_newcard": "new", "sess_finish": "finish"})
            if ch == "same":
                beeline_tries = 0
                continue
            if ch == "new":
                nc = wait_card(io, int(CFG["newcard_timeout_s"]))
                if nc is None:
                    requeue_link(link); break
                cur_card = nc; beeline_tries = 0
                continue
            requeue_link(link); break

        if res == "no_code":
            io.send(f"⚠️ Этот банк пока не поддерживается (не нашёл поле кода). Можно отдать на ручную "
                    f"оплату — напиши {ADMIN_CONTACT}.\nПопробуй другую карту.")
            requeue_link(link); link = None
            ch = ask_buttons(io, "Что делаем?",
                             [[btn("💳 Ввести новую карту", "sess_newcard")], [btn("🚪 Закончить работу", "sess_finish")]],
                             int(CFG["newcard_timeout_s"]), {"sess_newcard": "new", "sess_finish": "finish"})
            if ch == "new":
                nc = wait_card(io, int(CFG["newcard_timeout_s"]))
                if nc is None:
                    break
                cur_card = nc; beeline_tries = 0
                continue
            break

        if res == "bad_link":
            mark_problem(link, "не удалось начать оплату (нет кнопки / заказ не найден / истёк)")
            tg.send(ADMIN_ID, f"🗄 Проблемная ссылка\n{link['url']}\nПричина: не удалось начать оплату "
                              f"(нет кнопки оплаты / заказ не найден / истёк)\n🕒 {msk_ts()}",
                    kb([[btn("♻️ Вернуть в очередь", f"prob_ret:{link['id']}"),
                         btn("🗑 Удалить", f"prob_del:{link['id']}")]]))
            link = None; beeline_tries = 0
            continue   # тихо для оператора — берём следующую

        if res == "gateway":
            CONSEC_GATEWAY += 1
            beeline_tries = 0
            if CONSEC_GATEWAY >= 4:
                requeue_link(link)
                set_setting("accepting", "0")
                tg.send(ADMIN_ID, "⚠️ Платёжный шлюз (банк ЮMoney) подряд отдаёт 504 — похоже, он лежит. "
                                  "Приём оплат ВЫКЛЮЧЕН. Попробуй позже и включи приём снова.")
                io.send("⏸ Банк ЮMoney временно недоступен. Ставлю на паузу — попробуй позже.")
                queue_leave(payer_id)
                return
            ch = ask_buttons(io, "🏦 Банк ЮMoney временно недоступен (временный сбой на их стороне, 504).\n"
                                 "Воспользуйся картой ДРУГОГО банка — попробуем эту же ссылку ещё раз.",
                             [[btn("💳 Ввести карту другого банка", "sess_newcard")],
                              [btn("🚪 Закончить работу", "sess_finish")]],
                             int(CFG["newcard_timeout_s"]), {"sess_newcard": "new", "sess_finish": "finish"})
            if ch == "new":
                nc = wait_card(io, int(CFG["newcard_timeout_s"]))
                if nc is None:
                    requeue_link(link); break
                cur_card = nc
                continue   # та же ссылка, карта другого банка
            requeue_link(link); break

        if res == "site":
            io.send("🌐 Временный сбой (страница не ответила) — вернул ссылку в очередь, это не твоя вина. Пробую следующую.")
            requeue_link(link); link = None; beeline_tries = 0
            continue

        if res == "cancel":
            requeue_link(link); link = None
            ch = ask_buttons(io, "Отменил эту ссылку. Продолжаем?",
                             [[btn("💳 Брать карту дальше", "sess_next")], [btn("🚪 Закончить работу", "sess_finish")]],
                             int(CFG["idle_timeout_s"]), {"sess_next": "next", "sess_finish": "finish"})
            if ch != "next":
                break
            continue

        if res == "timeout":
            io.send("⌛ Код не пришёл вовремя — освобождаю очередь.")
            requeue_link(link)
            queue_leave(payer_id)
            io.send("Ты вышел из очереди (ответа не поступило). Нажми «Встать в очередь», когда будешь готов.")
            return

    # нормальный выход («закончить»/таймаут новой карты)
    queue_leave(payer_id)
    io.send("🚪 Работа завершена, ты вышел из очереди. Спасибо!")


def session_thread(tg, payer_id, io):
    global ACTIVE
    is_admin = (payer_id == ADMIN_ID)
    try:
        try:
            from playwright.sync_api import sync_playwright
        except Exception:
            io.send("⚠️ Движок оплаты не готов на сервере (нет playwright/Chromium). Сообщи админу.")
            tg.send(ADMIN_ID, "⚠️ Не удалось запустить движок оплаты: нет playwright/Chromium.")
            return
        io.send("🟢 ТВОЯ ОЧЕРЕДЬ!\nПришли карту одним сообщением: НОМЕР СРОК КОД\n"
                "(напр. 2200000000001036 06/34 123)\n⏱ Нет карты за 3 мин — место уйдёт дальше.",
                kb([[btn("🚪 Выйти из очереди", "op_leave")]]))
        card = wait_card(io, int(CFG["idle_timeout_s"]), prompt=False)
        if card is None:
            io.send("⌛ Карта не пришла — освобождаю очередь.")
            queue_leave(payer_id)
            return
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
            try:
                session_loop(tg, io, browser, payer_id, card, is_admin)
            finally:
                try:
                    browser.close()
                except Exception:
                    pass
    except Exception:
        log("session error:\n" + traceback.format_exc())
        try:
            io.send("⚠️ Ошибка в сессии оплаты. Попробуй встать в очередь снова.")
        except Exception:
            pass
    finally:
        STOP_EVENT.clear()
        with ACTIVE_LOCK:
            ACTIVE = None


def maybe_start_session(tg):
    global ACTIVE
    with ACTIVE_LOCK:
        if ACTIVE is not None:
            return
        if not accepting() or links_count() <= 0:
            return
        q = queue_list()
        if not q:
            return
        payer = q[0]
        io = PayerIO(tg, payer)
        ACTIVE = {"payer": payer, "io": io}
    t = threading.Thread(target=session_thread, args=(tg, payer, io), daemon=True)
    ACTIVE["thread"] = t
    t.start()


# ── главный цикл ─────────────────────────────────────────────────────────────
def main():
    db_init()
    # RESTART_RECOVERY: незавершённые при прошлом запуске ссылки — назад в очередь
    con = db(); con.execute("UPDATE links SET status='queued' WHERE status='in_progress'"); con.commit(); con.close()
    tg = Telegram(CFG)
    me = tg._call("getMe")
    uname = (me.get("result") or {}).get("username", "?")
    log(f"запущен как @{uname}. Админ: {ADMIN_ID}")
    tg.send(ADMIN_ID, "🛠 Панель оплат запущена.")
    show_admin_menu(tg, ADMIN_ID)
    while True:
        try:
            for ev in tg.get_updates(timeout=5):
                try:
                    if ev["kind"] == "chat_member":
                        ch = ev.get("chat") or {}; st = ev.get("status")
                        if st in ("administrator", "creator"):
                            record_channel(ch)
                        elif st in ("left", "kicked"):
                            remove_channel(ch.get("id"))
                        continue
                    a = ACTIVE
                    _admin_act = (ev["kind"] == "callback" and
                                  ev.get("data", "").startswith(("cancel_pay:", "pay_ok:", "pay_block:", "prob_ret:", "prob_del:")))
                    _cmd = (ev["kind"] == "text" and ev.get("text", "").startswith("/"))  # команды не перехватываем
                    if a and ev.get("uid") == a["payer"] and ev["kind"] in ("text", "callback") and not _admin_act and not _cmd:
                        a["io"].put(ev)   # активному оплатчику — в сессию, не в меню
                        continue
                    if ev["kind"] == "callback":
                        handle_callback(tg, ev)
                    elif ev["kind"] == "text":
                        handle_text(tg, ev)
                except Exception:
                    log("handler error:\n" + traceback.format_exc())
            maybe_start_session(tg)
            try:
                if now() - int(setting("last_backup", "0") or 0) > 86400:
                    do_backup(); set_setting("last_backup", str(now()))
            except Exception:
                pass
        except Exception:
            log("loop error:\n" + traceback.format_exc())
            time.sleep(3)


if __name__ == "__main__":
    main()

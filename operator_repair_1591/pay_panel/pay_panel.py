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
    "browser_proxy": "",                   // для страниц оплаты, слот 1 (обычно пусто — IP этого сервера)
    "browser_proxy_2": "",                 // слот 2: socks5://хост:1080 второго сервера. Пусто — второго места нет.
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
import random
import re
import socket
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
        self._proxies = None
        if proxy and proxy.lower() not in ("direct", "none", "off", "no", "-"):
            self._proxies = {"https": proxy, "http": proxy}
        self._tl = threading.local()
        self.base = f"https://api.telegram.org/bot{self.token}"
        self.offset = None
        socket.setdefaulttimeout(30)

    def _drop_http(self):
        s = getattr(self._tl, "s", None)
        if s is not None:
            try:
                s.close()
            except Exception:
                pass
            self._tl.s = None

    def _http(self):
        s = getattr(self._tl, "s", None)
        if s is None:
            s = requests.Session()
            if self._proxies:
                s.proxies = self._proxies
            self._tl.s = s
        return s

    def _call(self, method, **params):
        try:
            r = self._http().post(f"{self.base}/{method}", data=params, timeout=20)
            return r.json()
        except Exception as exc:
            log(f"{method} error: {type(exc).__name__}: {exc}")
            self._drop_http()
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
        if _emoji_rejected(r):
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
        if _emoji_rejected(r):
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
                return self._http().post(f"{self.base}/sendPhoto", data=data, files={"photo": f}, timeout=40)
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

    def edit_caption(self, chat_id, message_id, caption, kb=None):
        data = {"chat_id": chat_id, "message_id": message_id, "caption": (caption or "")[:1000]}
        if kb is not None:
            data["reply_markup"] = json.dumps(kb, ensure_ascii=False)
        return self._call("editMessageCaption", **data)

    def edit_photo(self, chat_id, message_id, path, caption="", kb=None):
        media = {"type": "photo", "media": "attach://photo", "caption": (caption or "")[:1000]}
        data = {"chat_id": chat_id, "message_id": message_id,
                "media": json.dumps(media, ensure_ascii=False)}
        if kb is not None:
            data["reply_markup"] = json.dumps(kb, ensure_ascii=False)
        try:
            with open(path, "rb") as f:
                r = self._http().post(f"{self.base}/editMessageMedia", data=data,
                                      files={"photo": ("qr.png", f, "image/png")}, timeout=60)
            return r.json()
        except Exception as exc:
            log(f"edit_photo error: {type(exc).__name__}: {exc}")
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
                return self._http().post(f"{self.base}/sendDocument", data=data,
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
            data = self._http().get(f"{self.base}/getUpdates", params=params, timeout=timeout + 15).json()
        except Exception as exc:
            log(f"getUpdates error: {type(exc).__name__}: {exc}")
            self._drop_http()
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
                            "message_id": msg.get("message_id"),
                            "photo": bool(msg.get("photo"))})
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
    for tbl, col, decl in [("payments", "card_hash", "TEXT DEFAULT ''"),
                           ("payments", "exported", "INTEGER DEFAULT 0"),
                           ("invites", "max_uses", "INTEGER DEFAULT 1"),
                           ("invites", "used_count", "INTEGER DEFAULT 0"),
                           ("cards", "blocked_until", "INTEGER DEFAULT 0")]:
        cols = [r["name"] for r in con.execute(f"PRAGMA table_info({tbl})").fetchall()]
        if col not in cols:
            con.execute(f"ALTER TABLE {tbl} ADD COLUMN {col} {decl}")
    con.execute("UPDATE invites SET used_count=1 WHERE used_by!=0 AND used_count=0")
    con.execute("UPDATE invites SET max_uses=1 WHERE max_uses IS NULL OR max_uses<1")
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


DIRECT_START = set()


def queue_join(tg_id):
    q = queue_list()
    if tg_id not in q:
        if not q:
            DIRECT_START.add(tg_id)
        else:
            DIRECT_START.discard(tg_id)
    con = db()
    con.execute("INSERT OR IGNORE INTO queue(operator_id,joined_at,last_action) VALUES(?,?,?)", (tg_id, now(), now()))
    con.commit()
    con.close()


def queue_leave(tg_id):
    DIRECT_START.discard(tg_id)
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
        if "beeline.ru" not in u:
            continue
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
    "💳": "5445353829304387411",
    "🚪": "5226953054380659263",
    "💸": "5409048419211682843",
    "💰": "5409048419211682843",
    "💵": "5409048419211682843",
    "🔄": "5877410604225924969",
    "🔁": "5877410604225924969",
    "🔗": "5877465816030515018",
    "🟢": "5339135753316222622",
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


def _emoji_rejected(r):
    """Повтор без значков только если Телеграм отверг сами эмодзи. «Сообщение не изменено» — не ошибка значков."""
    if not isinstance(r, dict) or r.get("ok"):
        return False
    d = (r.get("description") or "").lower()
    if "not modified" in d:
        return False
    return "emoji" in d or "entity" in d or "entities" in d


def btn(text, data, icon=None, style=None):
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
    if style:
        b["style"] = style
    return b


def accepting():
    return setting("accepting", "1") == "1"


def top_today_text(limit=10):
    """Топ оплатчиков по успешным оплатам за текущие сутки МСК."""
    msk = now() + 3 * 3600
    start = (msk // 86400) * 86400 - 3 * 3600
    day = time.strftime("%d.%m", time.gmtime(start + 3 * 3600))
    con = db()
    rows = con.execute(
        "SELECT operator_id, COUNT(*) AS n, COALESCE(SUM(amount),0) AS earned "
        "FROM payments WHERE result='success' AND canceled=0 AND at>=? AND at<? "
        "GROUP BY operator_id ORDER BY n DESC, earned DESC LIMIT ?",
        (start, start + 86400, limit)).fetchall()
    total = con.execute(
        "SELECT COUNT(*) AS n, COALESCE(SUM(amount),0) AS earned FROM payments "
        "WHERE result='success' AND canceled=0 AND at>=? AND at<?",
        (start, start + 86400)).fetchone()
    con.close()
    if not rows:
        return f"🏆 ТОП ОПЛАТЧИКОВ\n{SEP}\nСегодня успешных оплат ещё нет.\n{SEP}"

    def pays(n):
        n = int(n)
        if 11 <= n % 100 <= 14:
            word = "оплат"
        elif n % 10 == 1:
            word = "оплата"
        elif n % 10 in (2, 3, 4):
            word = "оплаты"
        else:
            word = "оплат"
        return f"{n} {word}"

    marks = ["🥇", "🥈", "🥉"]
    lines = [f"🏆 ТОП ОПЛАТЧИКОВ\n{SEP}", f"📅 Сегодня, {day} МСК\n"]
    for i, r in enumerate(rows, 1):
        op = get_op(r["operator_id"])
        name = op_display(op) if op else f"ID {r['operator_id']}"
        mark = marks[i - 1] if i <= 3 else f"{i}."
        lines.append(f"{mark} {name}\n✅ {pays(r['n'])}  ·  💰 {float(r['earned']):.2f} $")
    lines.append(f"\n{SEP}\n📊 Всего за день: {pays(total['n'])}  ·  💰 {float(total['earned']):.2f} $")
    return "\n".join(lines)


PAYOUT_THANKS = (
    "Спасибо за работу, ждём вас снова ♥️",
    "Благодарим за работу. Будем рады видеть вас снова ♥️",
    "Спасибо, что вы с нами. До новой смены ♥️",
    "Отличная работа. Ждём вас снова ♥️",
    "Спасибо за труд. Возвращайтесь, мы на связи ♥️",
    "Спасибо за сегодня. Ждём вас снова ♥️",
    "Ценим вашу работу. До скорой встречи ♥️",
    "Спасибо, что выбираете нас. Ждём снова ♥️",
    "Рады, что вы с нами. Возвращайтесь ♥️",
    "Спасибо за смену. Ждём вас снова ♥️",
    "Благодарим за время и работу. До встречи ♥️",
    "Хорошая работа. Будем ждать вас снова ♥️",
    "Спасибо. Отдыхайте и приходите ещё ♥️",
    "Вы нам очень помогли. Ждём вас снова ♥️",
    "С теплом благодарим за работу. До следующего раза ♥️",
    "Спасибо за аккуратную работу. Ждём вас ♥️",
    "Благодарим. Двери открыты, ждём снова ♥️",
    "Спасибо за работу. До скорой смены ♥️",
    "Рады сотрудничеству. Ждём вас снова ♥️",
    "Спасибо, что были сегодня. Ждём вас снова ♥️",
)


def payout_thanks():
    return random.choice(PAYOUT_THANKS)


def send_payout_done(tg, op_id, text):
    """@Contra_usdt_1 получает ту же выплату картинкой, остальные — текстом."""
    op = get_op(op_id)
    photo = BASE_DIR / "contra_payout.jpg"
    if op and (op.get("username") or "").lower() == "contra_usdt_1" and photo.is_file():
        r = tg.send_photo(op_id, str(photo), text)
        if isinstance(r, dict) and r.get("ok"):
            return
    tg.send(op_id, text)


def op_display(op):
    return ("@" + op["username"]) if op.get("username") else ("ID " + str(op["tg_id"]))


def xrocket_payout(pid, tg_id, amount):
    """Прямой перевод USDT на Telegram ID через xRocket. (ok, текст). Токен только в конфиге."""
    token = str(CFG.get("xrocket_token") or "").strip()
    if not token:
        return False, "в конфиге нет xrocket_token"
    body = {
        "clientPayoutId": f"pay-{pid}",
        "target": str(tg_id),
        "targetType": "telegram_user_id",
        "asset": "USDT",
        "amount": f"{float(amount):.2f}",
        "description": "выплата autopey",
    }
    try:
        r = requests.post(
            "https://pay.api.xrocket.exchange/api/v1/payouts",
            json=body,
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            timeout=30,
        )
    except Exception as exc:
        return False, type(exc).__name__
    try:
        data = r.json()
    except Exception:
        data = {}
    if isinstance(data, dict) and isinstance(data.get("data"), dict):
        data = data["data"]
    status = str(data.get("status") or "") if isinstance(data, dict) else ""
    if r.status_code in (200, 201) and status in ("finished", "pending"):
        return True, status
    if r.status_code == 409:
        return True, "already"
    msg = ""
    if isinstance(data, dict):
        msg = str(data.get("detail") or data.get("title") or data.get("message") or "")
    return False, f"{r.status_code} {msg}".strip()[:200]


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
    if len(exp) == 6:          # MMYYYY, например 09/2036
        exp = exp[:2] + exp[4:]
    if len(exp) != 4 or not (1 <= int(exp[:2]) <= 12):
        return None, "срок в формате MM/YY или MM/YYYY, месяц 01–12"
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
    if not accepting():
        queue_line = "✖️ Закрыто"
        status = "⏸ стоп"
    elif links_count():
        queue_line = "🟢 В очереди: 0" if not q else f"🔴 В очереди: {len(q)}"
        status = "✔️ оплаты требуются"
    else:
        queue_line = "🟢 В очереди: 0" if not q else f"🔴 В очереди: {len(q)}"
        status = "⚪️ оплат нет"
    you = f"да, позиция {pos}" if in_q else "нет"
    t = (f"💳 ПАНЕЛЬ ОПЛАТЧИКА\n{SEP}\n"
         f"👤 {op_display(op)}\n"
         f"💰 Баланс: {op['balance']:.2f} $" + (f"  (🔒 заморожено {op['frozen']:.2f} $)" if op['frozen'] else "") + "\n"
         f"📊 Ставка: {op_rate(op):.2f} $ / оплата\n\n"
         f"{queue_line}\n"
         f"📥 Статус: {status}\n"
         f"📑 Требуется оплат: {links_count()}\n"
         f"🎯 Ты в очереди: {you}\n"
         f"🏷 Сумма за 1 тариф: ~{setting('tariff_rub')} ₽ (своей картой)\n{SEP}")
    rows = []
    if in_q:
        rows.append([btn("Выйти из очереди", "op_leave", "5226953054380659263")])
    elif not q:
        rows.append([btn("Начать оплату", "op_join", "5445353829304387411", "success")])
    else:
        rows.append([btn("Встать в очередь", "op_join", "5348125953090403204")])
    rows.append([btn("Выплата", "op_payout", "5409048419211682843"),
                 btn("Обновить", "op_refresh", "5877410604225924969")])
    return t, kb(rows)


def show_operator_menu(tg, op, chat_id, message_id=None):
    t, k = operator_menu_text(op)
    if message_id:
        r = tg.edit(chat_id, message_id, t, k)
        if not (isinstance(r, dict) and r.get("ok")):
            tg.send(chat_id, t, k)
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
    n_exp = export_pending_count()
    t = (f"🛠 ПАНЕЛЬ АДМИНА\n{SEP}\n"
         f"📥 Приём оплат: {'✔️ включён' if accepting() else '✖️ выключен'}\n"
         f"📑 В очереди: {links_count()}   🗄 Проблемных: {prob}\n"
         f"📤 К выгрузке: {n_exp}\n"
         f"🧑‍🤝‍🧑 Оплатчиков: {n_ops} (в очереди {len(queue_list())}, в работе {len(ACTIVE_SLOTS)}/{slot_count()})\n"
         f"💰 Всего к выплате: {owed:.2f} $\n{SEP}")
    admin_in_q = ADMIN_ID in queue_list()
    rows = [
        [btn("Выйти из очереди (оплата)", "adm_leaveq", "5226953054380659263") if admin_in_q
         else btn("Оплатить самому (встать в очередь)", "adm_joinq", "5445353829304387411")],
        [btn("Загрузить ссылки", "adm_load", "5877465816030515018")],
        [btn(f"Выгрузка · {n_exp}", "adm_export", "5877540355187937244")],
        [btn(f"Выгрузка QR · {ready_qr_count()}", "adm_qr", "5987917196469213507")],
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


def export_pending_count():
    con = db()
    n = con.execute(
        "SELECT COUNT(*) c FROM payments WHERE result='success' AND canceled=0 AND COALESCE(exported,0)=0"
    ).fetchone()["c"]
    con.close()
    return n


def export_success_links(tg, uid):
    """Успешные ссылки текстом админу. После отправки счётчик обнуляется."""
    con = db()
    rows = con.execute(
        "SELECT p.id, COALESCE(NULLIF(l.url, ''), p.url_final) url "
        "FROM payments p LEFT JOIN links l ON l.id = p.link_id "
        "WHERE p.result='success' AND p.canceled=0 AND COALESCE(p.exported,0)=0 "
        "ORDER BY p.id"
    ).fetchall()
    if not rows:
        con.close()
        tg.send(uid, "📤 Успешных ссылок пока нет.")
        return 0
    ids = [r["id"] for r in rows]
    urls = [str(r["url"]).strip() for r in rows if str(r["url"] or "").strip()]
    marks = ",".join("?" * len(ids))
    con.execute(f"UPDATE payments SET exported=1 WHERE id IN ({marks})", ids)
    con.commit()
    con.close()
    body = "\n".join(urls)
    while body:
        tg.send(uid, body[:3500])
        body = body[3500:]
    tg.send(uid, f"📤 Выгружено: {len(urls)}. Счётчик обнулён.")
    return len(urls)


def _qr_exported():
    try:
        data = json.loads(QR_EXPORTED_FILE.read_text("utf-8"))
        return set(data) if isinstance(data, list) else set()
    except Exception:
        return set()


def _qr_mark_exported(url):
    done = _qr_exported()
    done.add(url)
    QR_EXPORTED_FILE.write_text(json.dumps(sorted(done), ensure_ascii=False), "utf-8")


def ready_qr_urls():
    """Оплаченные в панели eSIM, по которым QR ещё не снимали."""
    done = _qr_exported()
    con = db()
    rows = con.execute(
        "SELECT COALESCE(NULLIF(l.url, ''), p.url_final) url "
        "FROM payments p LEFT JOIN links l ON l.id = p.link_id "
        "WHERE p.result='success' AND COALESCE(p.canceled,0)=0 AND COALESCE(p.exported,0)=0 "
        "ORDER BY p.id"
    ).fetchall()
    con.close()
    out, seen = [], set()
    for r in rows:
        url = str(r["url"] or "").strip()
        if not url.startswith("http") or url in seen or url in done:
            continue
        seen.add(url)
        out.append((url, ""))
    return out


def ready_qr_count():
    return len(ready_qr_urls())


def _qr_links():
    try:
        data = json.loads(QR_LINKS_FILE.read_text("utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _qr_remember(url):
    data = _qr_links()
    pid = str(int(time.time() * 1000))
    while pid in data:
        pid = str(int(pid) + 1)
    data[pid] = url
    if len(data) > 300:
        for old in sorted(data, key=lambda k: int(k) if str(k).isdigit() else 0)[:-300]:
            data.pop(old, None)
    QR_LINKS_FILE.write_text(json.dumps(data, ensure_ascii=False), "utf-8")
    return pid


def _qr_by_id(pid):
    return _qr_links().get(str(pid)) or ""


def _qr_kb(pid):
    return kb([[btn("🔄 Обновить", f"qrr:{pid}")]])


def _bee_export_proxy():
    """Прокси выгрузки QR из настроек beelinetesting, если он включён именно для QR."""
    path = Path("/etc/systemd/system/beeline.service.d/zz-menu.conf")
    env = {}
    try:
        for line in path.read_text("utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line.startswith("Environment="):
                continue
            item = line.split("=", 1)[1].strip().strip('"')
            if "=" not in item:
                continue
            k, v = item.split("=", 1)
            env[k] = v
    except Exception:
        return None, ""
    on = str(env.get("BEELINE_MOBILE_PROXY_ON") or "0").lower() in {"1", "on", "yes", "true"}
    for_qr = str(env.get("BEELINE_PROXY_FOR_QR") or "1").lower() not in {"0", "off", "no", "false"}
    if not on or not for_qr:
        return None, ""
    raw = str(env.get("BEELINE_MOBILE_PROXY") or "").strip()
    text = raw
    scheme = "http"
    if "://" in text:
        scheme, text = text.split("://", 1)
        scheme = scheme.lower()
    if scheme not in {"http", "https", "socks5"}:
        return None, ""
    user = password = ""
    if "@" in text:
        cred, text = text.rsplit("@", 1)
        user, _, password = cred.partition(":")
    parts = text.strip("/").split(":")
    if len(parts) == 4 and not user:
        parts, user, password = parts[:2], parts[2], parts[3]
    if len(parts) != 2 or not parts[0] or not parts[1].isdigit():
        return None, ""
    proxy = {"server": f"{scheme}://{parts[0]}:{parts[1]}"}
    if user:
        proxy["username"] = user
        proxy["password"] = password
    return proxy, str(env.get("BEELINE_IP_CHANGE_URL") or "").strip()


def _qr_child(job_path):
    """Отдельный процесс: свой Playwright, чтобы не ронять браузеры оплаты."""
    job = json.loads(Path(job_path).read_text("utf-8"))
    out = Path(job["out"])
    out.mkdir(parents=True, exist_ok=True)
    import importlib.util
    spec = importlib.util.spec_from_file_location("bee_menu", job["lib"])
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    rows = []
    for i, url in enumerate(job.get("urls") or []):
        res = {}
        try:
            for _, res in mod.playwright_qr_export(
                    [url], proxy=job.get("proxy") or None,
                    ip_change_url=job.get("ipurl") or "", rotate_every=1):
                break
        except Exception as exc:
            res = {"error": f"{type(exc).__name__}: {exc}"[:180]}
        item = {"url": url,
                "phone": (res.get("phone") if isinstance(res, dict) else "") or "",
                "error": (res.get("error") if isinstance(res, dict) else "") or ""}
        png = res.get("png") if isinstance(res, dict) else None
        if png:
            fp = out / f"{i}.png"
            fp.write_bytes(png)
            item["file"] = str(fp)
        rows.append(item)
    (out / "result.json").write_text(json.dumps(rows, ensure_ascii=False), "utf-8")


def _qr_export_job(tg, uid):
    import shutil
    import subprocess
    import tempfile
    work = None
    try:
        items = ready_qr_urls()
        if not items:
            tg.send(uid, "🔳 Оплаченных eSIM для QR пока нет.")
            return
        tg.send(uid, f"🔳 Снимаю QR по {len(items)} оплаченным eSIM.")
        proxy, ipurl = _bee_export_proxy()
        work = Path(tempfile.mkdtemp(prefix="qrjob-"))
        job = {"lib": str(BASE_DIR / "bee_menu.py"), "out": str(work),
               "urls": [u for u, _ in items], "proxy": proxy, "ipurl": ipurl}
        (work / "job.json").write_text(json.dumps(job), "utf-8")
        subprocess.run(
            [sys.executable, str(Path(__file__).resolve()), "--qr-child", str(work / "job.json")],
            timeout=max(180, 100 * len(items)), check=False)
        result_path = work / "result.json"
        rows = json.loads(result_path.read_text("utf-8")) if result_path.is_file() else []
        by_url = {r.get("url"): r for r in rows}
        ok = fail = 0
        for url, number in items:
            res = by_url.get(url) or {}
            phone = res.get("phone") or number or "—"
            fp = res.get("file") or ""
            pid = _qr_remember(url)
            markup = _qr_kb(pid)
            if fp and Path(fp).is_file():
                sent = tg.send_photo(uid, fp, f"🔳 {phone}", markup)
                if isinstance(sent, dict) and sent.get("ok"):
                    _qr_mark_exported(url)
                    ok += 1
                    continue
            fail += 1
            tg.send(uid, f"⚠️ {phone}\n{res.get('error') or 'не отправился'}"[:500], markup)
        tg.send(uid, f"🔳 Выгрузка QR готова\n✅ {ok}\n⚠️ {fail}")
    except Exception as exc:
        log("qr export:\n" + traceback.format_exc())
        tg.send(uid, f"🔳 Выгрузка QR прервана: {type(exc).__name__}")
    finally:
        if work is not None:
            shutil.rmtree(work, ignore_errors=True)
        QR_EXPORT_LOCK.release()


def _qr_refresh_job(tg, uid, chat_id, mid, url, pid, was_photo):
    import shutil
    import subprocess
    import tempfile
    work = None
    markup = _qr_kb(pid)
    try:
        proxy, ipurl = _bee_export_proxy()
        work = Path(tempfile.mkdtemp(prefix="qrone-"))
        job = {"lib": str(BASE_DIR / "bee_menu.py"), "out": str(work),
               "urls": [url], "proxy": proxy, "ipurl": ipurl}
        (work / "job.json").write_text(json.dumps(job), "utf-8")
        subprocess.run(
            [sys.executable, str(Path(__file__).resolve()), "--qr-child", str(work / "job.json")],
            timeout=180, check=False)
        rows = []
        result_path = work / "result.json"
        if result_path.is_file():
            rows = json.loads(result_path.read_text("utf-8"))
        res = rows[0] if rows else {}
        phone = res.get("phone") or "—"
        fp = res.get("file") or ""
        if fp and Path(fp).is_file():
            caption = f"🔳 {phone}"
            if was_photo:
                tg.edit_photo(chat_id, mid, fp, caption, markup)
            else:
                tg.send_photo(uid, fp, caption, markup)
                tg.edit(chat_id, mid, "✅ QR получен — см. новое сообщение ниже.", None)
            return
        text = f"⚠️ {phone}\n{res.get('error') or 'QR не получен'}\n{url[:160]}"
        if was_photo:
            tg.edit_caption(chat_id, mid, text[:1000], markup)
        else:
            tg.edit(chat_id, mid, text[:1000], markup)
    except Exception as exc:
        log("qr refresh:\n" + traceback.format_exc())
        tg.send(uid, f"🔳 Не обновил QR: {type(exc).__name__}")
    finally:
        if work is not None:
            shutil.rmtree(work, ignore_errors=True)
        QR_EXPORT_LOCK.release()


# ── pending-состояния многошагового ввода ────────────────────────────────────
PENDING = {}   # uid -> {"await": ..., ...}
QR_EXPORT_LOCK = threading.Lock()
QR_EXPORTED_FILE = BASE_DIR / "qr_exported.json"
QR_LINKS_FILE = BASE_DIR / "qr_links.json"


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
        if ACTIVE_SLOTS:
            STOP_EVENT.set()
            tg.send(uid, "⏹ Останавливаю текущие оплаты и освобождаю очередь…")
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
    if cmd.split("@")[0] == "/top":
        tg.send(uid, top_today_text())
        return True
    if cmd == "/invite":
        toks = arg.split()
        if not toks:
            tg.send(uid, "Формат: /invite <код> [активаций]\nНапример: /invite 123456 2")
            return True
        code = toks[0]
        uses = 1
        if len(toks) >= 2:
            if not toks[1].isdigit() or int(toks[1]) < 1:
                tg.send(uid, "Число активаций — целое от 1. Пример: /invite 123456 2")
                return True
            uses = min(int(toks[1]), 10000)
        con = db()
        try:
            con.execute("INSERT INTO invites(code,created_by,created_at,max_uses,used_count) VALUES(?,?,?,?,0)",
                        (code, uid, now(), uses))
            con.commit()
            tg.send(uid, f"✅ Код {code} — на {_uses_word(uses)}.")
        except sqlite3.IntegrityError:
            tg.send(uid, "Такой код уже существует.")
        con.close()
        return True
    if cmd == "/autostart":
        low = arg.lower().strip()
        if low in ("off", "0", "стоп", "отмена", "cancel"):
            set_setting("autostart_at", "")
            tg.send(uid, "⏹ Таймер включения приёма снят.")
            return True
        secs = _parse_delay(arg)
        if secs is None:
            pending = setting("autostart_at", "")
            extra = ""
            if pending.isdigit():
                extra = f"\nСейчас включится в {msk_ts(int(pending))}."
            tg.send(uid, "Формат: /autostart 1h 1m, или 1h, или 1m.\n"
                         "Снять таймер: /autostart off" + extra)
            return True
        at = now() + secs
        set_setting("autostart_at", str(at))
        tg.send(uid, f"⏳ Приём оплат включится через {_fmt_delay(secs)} ({msk_ts(at)}).")
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


def _uses_word(n):
    n = abs(int(n))
    if 11 <= (n % 100) <= 14:
        word = "активаций"
    elif n % 10 == 1:
        word = "активацию"
    elif n % 10 in (2, 3, 4):
        word = "активации"
    else:
        word = "активаций"
    return f"{n} {word}"


def _parse_delay(text):
    """'1h 1m', '1h', '1m', '2ч 30м' → секунды. Пусто или без единиц → None."""
    raw = (text or "").lower()
    if not raw.strip():
        return None
    hours = sum(int(x) for x in re.findall(r"(\d+)\s*h", raw))
    hours += sum(int(x) for x in re.findall(r"(\d+)\s*ч", raw))
    minutes = sum(int(x) for x in re.findall(r"(\d+)\s*m", raw))
    minutes += sum(int(x) for x in re.findall(r"(\d+)\s*м", raw))
    if hours == 0 and minutes == 0:
        return None
    return hours * 3600 + minutes * 60


def _fmt_delay(seconds):
    h, m = divmod(int(seconds) // 60, 60)
    parts = []
    if h:
        parts.append(f"{h} ч")
    if m or not parts:
        parts.append(f"{m} мин")
    return " ".join(parts)


def maybe_autostart(tg):
    raw = setting("autostart_at", "")
    if not raw:
        return
    try:
        at = int(raw)
    except ValueError:
        set_setting("autostart_at", "")
        return
    if now() < at:
        return
    set_setting("autostart_at", "")
    set_setting("accepting", "1")
    tg.send(ADMIN_ID, "🟢 Приём оплат включён по таймеру.")


def try_invite(tg, uid, username, name, code):
    """Активировать инвайт, пока не кончились активации."""
    con = db()
    cur = con.execute(
        "UPDATE invites SET used_count=used_count+1, used_by=?, used_at=? WHERE code=? AND used_count < max_uses",
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
    if str(data).startswith("qrr:"):
        tg.answer_cb(cb_id, "Пробую снять QR заново…")
    else:
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
            queue_join(uid)
            pos = queue_pos(uid)
            tg.send(uid, f"🟢 Ты в очереди, место {pos}. Сейчас открою оплату.")
            show_admin_menu(tg, chat_id, mid)
            return
        if data == "adm_leaveq":
            queue_leave(uid); show_admin_menu(tg, chat_id, mid); return
        if data.startswith("cancel_pay:"):
            pid = int(data.split(":")[1])
            con = db(); p = con.execute("SELECT * FROM payments WHERE id=?", (pid,)).fetchone()
            if not p or p["result"] != "success" or p["canceled"]:
                con.close(); tg.answer_cb(cb_id, "Уже отменено или не найдено"); return
            con.execute("UPDATE payments SET canceled=1 WHERE id=?", (pid,))
            if p["card_hash"]:
                con.execute("UPDATE cards SET success_count=max(0, success_count-1), "
                            "blocked_until=CASE WHEN success_count<=3 THEN 0 ELSE blocked_until END "
                            "WHERE card_hash=?", (p["card_hash"],))
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
        if data == "adm_export":
            export_success_links(tg, uid)
            show_admin_menu(tg, chat_id, mid)
            return
        if data == "adm_qr":
            if not QR_EXPORT_LOCK.acquire(blocking=False):
                tg.send(uid, "🔳 Выгрузка QR уже идёт.")
                return
            threading.Thread(target=_qr_export_job, args=(tg, uid), name="pay-qr", daemon=True).start()
            return
        if data.startswith("qrr:"):
            url = _qr_by_id(data.split(":", 1)[1])
            if not url:
                tg.send(uid, "Ссылка устарела — сделай выгрузку заново.")
                return
            if not QR_EXPORT_LOCK.acquire(blocking=False):
                tg.send(uid, "🔳 Выгрузка QR уже идёт.")
                return
            threading.Thread(
                target=_qr_refresh_job,
                args=(tg, uid, chat_id, mid, url, data.split(":", 1)[1], bool(ev.get("photo"))),
                name="pay-qr-one", daemon=True).start()
            return
        if data == "adm_toggle":
            turning_on = not accepting()
            set_setting("accepting", "0" if accepting() else "1")
            if turning_on:
                SLOT_PAUSED.clear()
                SLOT_FAILS.clear()
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
                send_payout_done(tg, r["operator_id"],
                        f"✅ ВЫПЛАТА ОДОБРЕНА\n{SEP}\n"
                        f"💰 {r['amount']:.2f} $\n"
                        f"✔️ Сумма подтверждена и отправлена\n{SEP}\n"
                        f"Если перевод не пришёл — напиши {ADMIN_CONTACT}\n\n"
                        f"{payout_thanks()}")
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
        # кнопки оплатчика у админа тоже живые, иначе нажатие просто молчит
        if data in ("op_join", "op_leave", "op_refresh", "op_payout", "op_payout_go") or data.startswith("sess_"):
            pass
        else:
            return

    # ── оплатчик ──
    if op:
        if data == "op_refresh":
            show_operator_menu(tg, op, chat_id, mid); return
        if data == "op_join":
            queue_join(uid)
            pos = queue_pos(uid)
            tg.send(uid, f"🟢 Ты в очереди, место {pos}. Сейчас открою оплату.")
            show_operator_menu(tg, op, chat_id, mid)
            return
        if data == "op_leave":
            queue_leave(uid); show_operator_menu(tg, op, chat_id, mid); return
        if data == "op_payout":
            o = get_op(uid)
            if o["balance"] <= 0:
                tg.send(uid, "Баланс пустой — выплачивать нечего."); return
            tg.send(uid, f"💸 ВЫПЛАТА\nК выплате: {o['balance']:.2f} $ (весь баланс)\n"
                         "USDT уйдёт в xRocket на этот Telegram сразу.",
                    kb([[btn(f"✅ Отправить {o['balance']:.2f} $", "op_payout_go")], [btn("⬅️ Отмена", "op_refresh")]]))
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
            ok, detail = xrocket_payout(pid, uid, amt)
            con = db()
            if ok:
                con.execute("UPDATE payouts SET status='paid', decided_at=? WHERE id=?", (now(), pid))
                con.execute("UPDATE operators SET frozen=frozen-? WHERE tg_id=?", (amt, uid))
                con.commit(); con.close()
                send_payout_done(tg, uid, f"✅ ВЫПЛАТА ОТПРАВЛЕНА\n{SEP}\n"
                             f"💰 {amt:.2f} USDT\n"
                             f"🚀 xRocket, на этот Telegram\n{SEP}\n"
                             f"Если не видно — открой @xrocket\n\n"
                             f"{payout_thanks()}")
                tg.send(ADMIN_ID, f"🚀 Выплата xRocket {amt:.2f} USDT\n👤 {op_display(get_op(uid))} ({uid})")
            else:
                con.close()
                tg.send(uid, f"⚠️ Автовыплата не удалась.\n"
                             f"Выплата {amt:.2f} $ будет в ручном режиме.\n"
                             f"Баланс заморожен до решения админа.")
                od = get_op(uid)
                tg.send(ADMIN_ID, f"💸 Автовыплата не прошла, нужна ручная\n"
                                  f"👤 {op_display(od)} ({uid})\nСумма: {amt:.2f} $\n{detail}",
                        kb([[btn("✅ Выплачено", f"pay_ok:{pid}"), btn("🚫 Заблокировать", f"pay_block:{pid}")]]))
            return
        return

    # гость нажал что-то
    guest_prompt(tg, uid)


# ══════════════════════ ЭТАП 2: ДВИЖОК ОПЛАТЫ ══════════════════════════════════
ACTIVE_SLOTS = {}               # slot -> {"payer": tg_id, "io": PayerIO, "thread": ...}
ACTIVE_LOCK = threading.Lock()
_STALL_NOTE = {}                 # payer -> почему место ещё не открылось, чтобы не спамить
STOP_EVENT = threading.Event()     # аварийный стоп всех текущих сессий (/stop админом)
_ENGINE = None
CONSEC_GATEWAY = 0                 # подряд сбоев платёжного шлюза (504…) → шлюз лежит
SLOT_FAILS = {}                    # подряд сбоев Билайна на конкретном выходе
SLOT_PAUSED = set()                # выход, который Билайн перестал пускать
SLOT_PROXY = {}                    # slot -> запасной socks, если основной IP этого места уже отрубили
SPARES = []                        # ещё не использованные запасные прокси
_SPARES_READY = False
_SPARE_LOCK = threading.Lock()


def slot_count():
    """Сколько мест. Второе и третье есть, только если задан их прокси."""
    if str(CFG.get("browser_proxy_3") or "").strip():
        return 3
    return 2 if str(CFG.get("browser_proxy_2") or "").strip() else 1


def _load_spares():
    global _SPARES_READY
    if _SPARES_READY:
        return
    raw = CFG.get("browser_proxy_spares") or []
    if isinstance(raw, str):
        raw = [x.strip() for x in raw.replace(";", ",").split(",") if x.strip()]
    for item in raw:
        item = str(item or "").strip()
        if item and item not in SPARES:
            SPARES.append(item)
    _SPARES_READY = True


def slot_proxy(slot):
    if slot in SLOT_PROXY:
        return SLOT_PROXY[slot]
    if slot == 1:
        return str(CFG.get("browser_proxy_2") or "").strip()
    if slot == 2:
        return str(CFG.get("browser_proxy_3") or "").strip()
    return ""


def _proxy_open(raw):
    """Порт прокси жив. Пустой прокси — прямой выход, его проверять не нужно."""
    text = str(raw or "").strip()
    if not text:
        return True
    host = text.split("@")[-1]
    if "://" in host:
        host = host.split("://", 1)[1]
    if ":" not in host:
        return False
    h, p = host.rsplit(":", 1)
    if not p.isdigit():
        return False
    s = socket.socket()
    s.settimeout(2)
    try:
        s.connect((h, int(p)))
        return True
    except Exception:
        return False
    finally:
        s.close()


def slot_name(slot):
    return ("основной IP", "второй IP", "третий IP")[slot] if slot < 3 else f"место {slot + 1}"


def take_spare(slot):
    """Сменить выход места на следующий запасной IP. Пусто — запасных больше нет."""
    _load_spares()
    with _SPARE_LOCK:
        current = slot_proxy(slot)
        nxt = ""
        while SPARES:
            cand = SPARES.pop(0)
            if cand and cand != current:
                nxt = cand
                break
        if not nxt:
            return ""
        SLOT_PROXY[slot] = nxt
        SLOT_FAILS[slot] = 0
        return nxt


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
        self.leave = threading.Event()

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


CARD_LIMIT = 3
CARD_BLOCK_S = 24 * 3600


def card_uses(card):
    con = db()
    ch = card_hash(card)
    r = con.execute("SELECT success_count, blocked_until FROM cards WHERE card_hash=?", (ch,)).fetchone()
    if not r:
        con.close()
        return 0
    until = r["blocked_until"] or 0
    if r["success_count"] >= CARD_LIMIT and until and now() >= until:
        con.execute("UPDATE cards SET success_count=0, blocked_until=0 WHERE card_hash=?", (ch,))
        con.commit()
        con.close()
        return 0
    con.close()
    return r["success_count"] or 0


def mask_pan(card):
    return "****" + card[0][-4:]


def take_next_link():
    """Следующая ссылка строго по порядку. Два места не могут взять одну и ту же."""
    con = db()
    try:
        con.execute("BEGIN IMMEDIATE")
        r = con.execute("SELECT * FROM links WHERE status='queued' ORDER BY id LIMIT 1").fetchone()
        if r:
            cur = con.execute("UPDATE links SET status='in_progress' WHERE id=? AND status='queued'", (r["id"],))
            if cur.rowcount != 1:
                r = None
        con.commit()
    except Exception:
        con.rollback()
        r = None
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


def payable_rub(page, pb):
    """Сумма именно «к оплате» / на кнопке «оплатить», не любая цифра со страницы."""
    chunks = []
    try:
        chunks.append(pb._page_text(page))
    except Exception:
        pass
    for fr in pb._frames(page):
        try:
            loc = fr.locator("button, a, [role=button]")
            n = min(loc.count(), 12)
        except Exception:
            continue
        for i in range(n):
            try:
                chunks.append(loc.nth(i).inner_text(timeout=250) or "")
            except Exception:
                continue
    text = "\n".join(chunks).replace("\xa0", " ").replace("\u202f", " ")
    found = []

    def _num(whole, frac):
        digits = re.sub(r"\s+", "", whole or "")
        if not digits.isdigit():
            return None
        if frac and str(frac).isdigit():
            return float(f"{digits}.{frac}")
        return float(digits)

    rx = re.compile(
        r"(?:к оплате|итого|всего|оплатить)[^\d₽]{0,30}(\d[\d ]{0,8})(?:[.,](\d{1,2}))?\s*(?:₽|руб)",
        re.I)
    for m in rx.finditer(text):
        n = _num(m.group(1), m.group(2))
        if n:
            found.append(n)
    if not found:
        for line in text.splitlines():
            low = line.lower()
            if not any(w in low for w in ("к оплате", "итого", "оплатить")):
                continue
            for m in re.finditer(r"(\d[\d ]{0,8})(?:[.,](\d{1,2}))?\s*(?:₽|руб)", line, re.I):
                n = _num(m.group(1), m.group(2))
                if n:
                    found.append(n)
    return max(found) if found else None


def record_success(tg, payer_id, link, card, is_admin, io, shot=None):
    con = db()
    con.execute("UPDATE links SET status='paid', paid_by=? WHERE id=?", (payer_id, link["id"]))
    ch = card_hash(card)
    con.execute("INSERT INTO cards(card_hash,success_count) VALUES(?,1) "
                "ON CONFLICT(card_hash) DO UPDATE SET success_count=success_count+1", (ch,))
    uses = con.execute("SELECT success_count FROM cards WHERE card_hash=?", (ch,)).fetchone()["success_count"]
    if uses >= CARD_LIMIT:
        con.execute("UPDATE cards SET blocked_until=? WHERE card_hash=?", (now() + CARD_BLOCK_S, ch))
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


def record_decline(tg, payer_id, link, card, is_admin, io, shot=None, page_url=None):
    shown = (page_url or "").strip() or link["url"]
    con = db()
    cur = con.execute("INSERT INTO payments(link_id,operator_id,card_mask,card_hash,result,url_final,at) "
                      "VALUES(?,?,?,?,?,?,?)",
                      (link["id"], payer_id, mask_pan(card), card_hash(card), "decline", shown, now()))
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
    log_payment(tg, pay_id, payer_id, link, card, card_uses(card), 0.0, "decline", shot, page_url=shown)


def log_payment(tg, pay_id, payer_id, link, card, uses, amount, result, shot=None, page_url=None):
    ch = setting("log_channel")
    o = get_op(payer_id)
    who = op_display(o) if o else (f"АДМИН ({payer_id})" if payer_id == ADMIN_ID else str(payer_id))
    head = "✅ УСПЕШНАЯ ОПЛАТА" if result == "success" else "❌ ОПЛАТА НЕ ПРОШЛА"
    meta = f"{head}\n👤 {who}\n💳 {mask_pan(card)} ({uses}/3)" + (f"  (+{amount:.2f} $)" if amount else "") + \
           f"\n🕒 {msk_ts()}"
    stopped = (page_url or "").strip()
    if result != "success":
        links = f"🔗 Исходная: {link['url']}"
        if stopped:
            links += f"\n🔗 Сейчас: {stopped}"
    else:
        links = f"🔗 {link['url']}"
    text = meta + "\n" + links
    markup = kb([[btn("🚫 Отмена оплаты", f"cancel_pay:{pay_id}")]]) if result == "success" else None
    has_shot = bool(shot and os.path.exists(shot))

    def _deliver(target, prefix=""):
        body = prefix + text
        if has_shot and len(body) > 1000:
            r = tg.send_photo(target, shot, (prefix + meta)[:1000])
            r2 = tg.send(target, links)
            return (isinstance(r, dict) and r.get("ok")) or (isinstance(r2, dict) and r2.get("ok"))
        if has_shot:
            r = tg.send_photo(target, shot, body[:1000], markup)
        else:
            r = tg.send(target, body, markup)
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


# ── ИИ-агент для нераспознанной страницы оплаты ─────────────────────────────
AI_SYS = ("Ты управляешь платёжной страницей банка. Тебе дают список элементов "
          "(поля и кнопки с индексами) и просьбу оператора. "
          "Можно нажимать любые элементы из списка и, если оператор прислал код, вписать его в поле. "
          "Не отказывайся только потому, что поля кода ещё нет: сначала нажми то, что просят.\n"
          "Верни СТРОГО JSON без пояснений:\n"
          '{"clicks": [<индексы кнопок по порядку нажатия>], "fill": <индекс поля или -1>}\n'
          "fill=-1, если код вводить не нужно.\n"
          'Если подходящего элемента нет: {"status":"not_found","say":"<очень коротко по-русски>"}\n'
          'Если просьба не про эту страницу (закрыть браузер, выключить сервер, болтовня): {"status":"off_topic"}\n'
          "Отвечай ТОЛЬКО JSON.")


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
                          json={"model": model, "temperature": 0, "max_tokens": 300,
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
        for sel in ("button", "[role=button]", "a", "div", "span"):
            try:
                loc = fr.locator(sel); n = min(loc.count(), 15)
            except Exception:
                n = 0
            for j in range(n):
                el = loc.nth(j)
                try:
                    if not el.is_visible():
                        continue
                    txt = (el.inner_text(timeout=400) or "").strip().replace("\n", " ")
                    if not txt or len(txt) > 40:
                        continue
                    items.append({"i": len(items), "вид": "кнопка", "текст": txt[:40]})
                    handles.append(el)
                except Exception:
                    continue
    return items, handles


def _extract_code(text):
    m = re.search(r"\b(\d{3,8})\b", text or "")
    return m.group(1) if m else ""


def ai_execute(handles, fill_idx, click_idxs, code):
    """Сначала нажимает элементы, потом вписывает код, если он есть. Код не обязателен."""
    did = False
    for raw in click_idxs or []:
        try:
            ci = int(raw)
        except (TypeError, ValueError):
            continue
        if ci < 0 or ci >= len(handles):
            continue
        try:
            handles[ci].click(timeout=3000)
            did = True
        except Exception:
            continue
    try:
        fi = int(fill_idx)
    except (TypeError, ValueError):
        fi = -1
    if code and 0 <= fi < len(handles):
        try:
            h = handles[fi]
            h.click()
            try:
                h.fill("")
            except Exception:
                pass
            h.type(re.sub(r"\D", "", code), delay=80)
            did = True
        except Exception:
            pass
    return did


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
        io.send("Напиши, что нажать на странице. Если код из СМС уже есть — пришли его в том же сообщении. "
                "Или «отмена».")
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
        clicks = data.get("clicks")
        if clicks is None and data.get("click") not in (None, ""):
            clicks = [data.get("click")]
        if not isinstance(clicks, list):
            clicks = []
        fill = data.get("fill", -1)
        try:
            fill_i = int(fill)
        except (TypeError, ValueError):
            fill_i = -1
        if data.get("status") == "not_found" or (not clicks and fill_i < 0):
            say = (data.get("say") or "не нашёл, что нажать")[:120]
            io.send(f"Поступил ответ от ИИ-агента: не получилось — {say}. Попробуй объяснить по-другому.")
            continue
        if fill_i >= 0 and not code and not clicks:
            io.send("Поступил ответ от ИИ-агента: нужно вписать код, а цифр в сообщении нет. Пришли код.")
            continue
        if not ai_execute(handles, fill_i, clicks, code):
            io.send("Поступил ответ от ИИ-агента: не смог нажать или вписать. Попробуй назвать кнопку точнее.")
            continue
        page.wait_for_timeout(1500)
        if not code:
            _fr, h = pb._find_code_field(page)
            if h is not None:
                io.send("Нажал. Поле кода появилось — пришли код из СМС.")
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
def _poll_cancel(io, held):
    """«Отмена» и «выйти» во время ожидания банка. Выход читаем сразу, даже если в очереди уже лежит чужое сообщение."""
    if getattr(io, "leave", None) and io.leave.is_set():
        return "leave"
    pending = list(held)
    held.clear()
    while True:
        try:
            pending.append(io.inbox.get_nowait())
        except _queue.Empty:
            break
    found = None
    for ev in pending:
        text = (ev.get("text") or "").strip().lower()
        data = ev.get("data") or ""
        if ev.get("kind") == "callback" and data in ("op_leave", "sess_finish", "ai_cancel"):
            found = "leave" if data == "op_leave" else "cancel"
            if ev.get("id"):
                io.answer(ev)
            continue
        if ev.get("kind") == "text" and text in ("отмена", "stop", "/stop", "cancel", "закончить"):
            found = found or "cancel"
            continue
        held.append(ev)
    return found or False


def _back_on_start(pb, page):
    """Главная Билайна «оплатить картой», без формы карты и без поля кода."""
    try:
        if pb._on_card_form(page) or pb._is_yoomoney(page):
            return False
        if pb._find_code_field(page)[1] is not None:
            return False
        low = pb._page_text(page)
    except Exception:
        return False
    return ("оплатить картой" in low) and ("порядок" in low or "подтвердите данные" in low)


# Успешная вкладка не закрывается сразу: висит 3 минуты, потом закрывается сама.
_PARKED = {}
_PARK_LOCK = threading.Lock()


def _park_tab(ctx, slot, seconds=180):
    ev = threading.Event()
    with _PARK_LOCK:
        _PARKED.setdefault(slot, []).append(ev)

    def _run():
        try:
            time.sleep(seconds)
            try:
                ctx.close()
            except Exception:
                pass
        finally:
            ev.set()

    threading.Thread(target=_run, daemon=True).start()


def _wait_parked(slot, timeout=185):
    with _PARK_LOCK:
        evs = _PARKED.pop(slot, [])
    for ev in evs:
        ev.wait(timeout)


def pay_one_link(io, browser, url, card, cfg, shot_holder=None, slot=0, quiet=False):
    """Один заход: открыть ссылку → карта → банк/3DS/YooMoney → итог. Карту НЕ меняет (это делает
    панель). Возвращает: success / decline / beeline / no_code / site / cancel / timeout.
    В shot_holder["path"] кладёт скрин финальной страницы (для лога)."""
    pb = engine()
    if "beeline.ru" not in (url or ""):
        return "bad_link"
    page_wait = int(cfg.get("page_wait_seconds") or 240)
    code_wait = int(cfg.get("code_wait_seconds") or 300)
    ctx_kwargs = {"locale": "ru-RU"}
    bproxy = str(cfg.get("browser_proxy") or "").strip()
    if bproxy and bproxy.lower() not in ("direct", "none", "off", "no", "-"):
        ctx_kwargs["proxy"] = {"server": bproxy}
    ctx = browser.new_context(**ctx_kwargs)
    page = ctx.new_page()
    page.set_default_timeout(3000)
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
        hold_tab = False
        page.on("response", _on_resp)
        io.send("🔎Открываю оплату...") if not quiet else None
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=90000)
        except Exception as exc:
            log(f"goto: {type(exc).__name__}: {str(exc)[:160]}")
            if "ERR_PROXY" in str(exc) or "ERR_TUNNEL" in str(exc):
                return "proxy_dead"
            try:
                if any(w in pb._page_text(page) for w in BAD_LINK_WORDS):
                    return "bad_link"
            except Exception:
                pass
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
        if pb._url_status(page) == "success" or pb._esim_ready(page) or any(w in low for w in BAD_LINK_WORDS):
            return "bad_link"
        def _over_limit():
            rub = payable_rub(page, pb)
            try:
                limit = float(setting("tariff_rub") or cfg.get("tariff_rub") or 300)
            except Exception:
                limit = 300.0
            if rub is not None and rub > limit:
                if shot_holder is not None:
                    shot_holder["rub"] = rub
                    shot_holder["limit"] = limit
                return True
            return False

        if _over_limit():
            return "expensive"
        # «Оплата не прошла» — жмём «попробовать ещё раз» на этой же вкладке, ссылку заново не открываем.
        max_beeline = int(cfg.get("beeline_retry_max") or 3)
        beeline_retries = 0
        reached_bank = False
        card_sent = False

        def _bad_card():
            try:
                low = pb._page_text(page)
            except Exception:
                return False
            return ("некорректный номер карты" in low or "некорректный срок" in low
                    or "некорректный код" in low or "неверный номер карты" in low)

        def _is_decline():
            try:
                low = pb._page_text(page)
            except Exception:
                return False
            return any(w in low for w in pb.DECLINE_WORDS)

        def _fail_word():
            try:
                low = pb._page_text(page)
            except Exception:
                return ""
            for w in tuple(pb.PAYMENT_FAILED_WORDS) + ("попробовать ещё раз", "попробовать еще раз"):
                if w in low:
                    return w
            return ""

        def _page_fact():
            """Только то, что реально видно. Без догадки «оплата не прошла»."""
            word = _fail_word()
            try:
                url = (page.url or "").strip()
            except Exception:
                url = ""
            st = pb._url_status(page)
            bits = []
            if word:
                bits.append(f"на странице есть «{word}»")
            if st:
                bits.append(f"в ссылке status={st}")
            if "/registration/error" in url:
                bits.append("адрес /registration/error")
            if not bits:
                try:
                    raw = " ".join(pb._page_text(page).split())
                except Exception:
                    raw = ""
                bits.append("текст: " + (raw[:180] or "пусто"))
            if url:
                bits.append(url[:180])
            return "\n".join(bits)

        def _instant_fail():
            # Только слова, которые есть на странице. Ссылка status=fail сама по себе ничего не доказывает.
            if reached_bank or _is_decline():
                return False
            return bool(_fail_word())

        def _unclear():
            if shot_holder is not None:
                shot_holder["note"] = _page_fact()
            return "unclear"

        def _is_beeline_error_page():
            """Страница Билайна /registration/error с текстом «оплата не прошла»."""
            try:
                url = (page.url or "").lower()
            except Exception:
                url = ""
            if "/registration/error" in url and _fail_word():
                return True
            return False

        def _click_beeline_retry():
            """На странице ошибки Билайна жмём «попробовать ещё раз», ссылку заново не открываем."""
            nonlocal beeline_retries
            if pb._on_card_form(page):
                return True
            if beeline_retries >= max_beeline:
                io.send(f"⚠️ Страница ошибки Билайна так и осталась после {max_beeline} нажатий.\n{_page_fact()}")
                return False
            beeline_retries += 1
            io.send(f"⚠️ Страница ошибки Билайна.\n{_page_fact()}\n"
                    f"Жму «попробовать ещё раз» ({beeline_retries}/{max_beeline}).")
            if not pb._click_retry(page):
                io.send("⚠️ Не нашёл кнопку «попробовать ещё раз».")
                return False
            # старая ошибка ещё на экране пару секунд — это не новое появление
            page.wait_for_timeout(4000)
            deadline = time.monotonic() + 12
            while time.monotonic() < deadline:
                if pb._on_card_form(page) or STOP_EVENT.is_set():
                    break
                if _instant_fail():
                    break
                page.wait_for_timeout(400)
            return True

        branch = "wait"
        while True:
            # Ищем входную кнопку «оплатить картой». На уже оплаченной её нет — отбиваем сразу.
            pay_wait = int(cfg.get("pay_button_wait_s") or 20)
            bdeadline = time.monotonic() + pay_wait
            found_pay = False
            retry_now = False
            while time.monotonic() < bdeadline:
                if STOP_EVENT.is_set():
                    return "stopped"
                if getattr(io, "leave", None) and io.leave.is_set():
                    return "leave"
                low = pb._page_text(page)
                if pb._url_status(page) == "success" or any(w in low for w in BAD_LINK_WORDS):
                    return "bad_link"
                if _is_decline():
                    return "decline"
                if _instant_fail():
                    retry_now = True
                    break
                if pb._on_card_form(page):
                    found_pay = True
                    break
                if pb._click_by_words(page.main_frame, pb.PAY_BUTTON_WORDS, timeout_ms=2000):
                    found_pay = True
                    break
                page.wait_for_timeout(1200)
            if retry_now:
                if not _click_beeline_retry():
                    return "beeline"
                continue
            if not found_pay:
                try:
                    low = pb._page_text(page)
                except Exception:
                    low = ""
                if any(w in low for w in BAD_LINK_WORDS) or seen.get("error"):
                    return "bad_link"
                if len(" ".join(low.split())) < 80:
                    return "site"
                return "bad_link"
            # Поля карты нет, а на экране снова ошибка — не ждём 2 минуты, жмём кнопку ещё раз.
            form_deadline = time.monotonic() + int(cfg.get("card_form_wait_s") or 120)
            while not pb._on_card_form(page) and time.monotonic() < form_deadline:
                if _is_decline():
                    return "decline"
                if _instant_fail():
                    if not _click_beeline_retry():
                        return "beeline"
                    if pb._on_card_form(page):
                        break
                    form_deadline = time.monotonic() + int(cfg.get("card_form_wait_s") or 120)
                    continue
                page.wait_for_timeout(400)
            if not pb._on_card_form(page):
                if _is_decline():
                    return "decline"
                if _instant_fail():
                    return "beeline"
                return "site"
            if _over_limit():
                return "expensive"
            io.send(f"💳 Перешёл к оплате, ввожу карту {mask_pan(card)}…")
            deadline = time.monotonic() + int(cfg.get("card_form_wait_s") or 120)
            try:
                pb._type_card(page, card, io, deadline)
            except RuntimeError:
                if _bad_card():
                    return "bad_card"
                if _is_decline():
                    return "decline"
                if _instant_fail() and not pb._on_card_form(page):
                    if not _click_beeline_retry():
                        return "beeline"
                    continue
                if any(w in pb._page_text(page) for w in BAD_LINK_WORDS):
                    return "bad_link"
                return "site"
            if _bad_card():
                return "bad_card"
            page.wait_for_timeout(3000)
            if _bad_card():
                return "bad_card"
            card_sent = True
            io.send("⏳ Жду ответ банка (3DS)…")
            nav = time.monotonic() + page_wait
            c0 = time.monotonic()
            branch = "wait"
            held = []
            stuck = None
            restarts = 0
            alfa_clicked = [False]

            def _release_held():
                for ev in held:
                    io.inbox.put(ev)
                held.clear()

            retry_now = False
            while time.monotonic() < nav:
                if getattr(io, "leave", None) and io.leave.is_set():
                    _release_held()
                    return "leave"
                why = _poll_cancel(io, held)
                if why == "leave":
                    _release_held()
                    return "leave"
                if why:
                    _release_held()
                    return "cancel"
                if _instant_fail():
                    _release_held()
                    if card_sent and not _is_beeline_error_page():
                        return _unclear()
                    retry_now = True
                    break
                if pb._url_status(page) == "success" or pb._esim_ready(page):
                    _release_held()
                    hold_tab = True
                    return "success"
                low = pb._page_text(page)
                if _gateway_error(low):
                    _release_held()
                    return "gateway"
                if ("некорректный номер карты" in low or "некорректный срок" in low
                        or "некорректный код" in low or "неверный номер карты" in low):
                    _release_held()
                    return "bad_card"
                if any(w in low for w in pb.DECLINE_WORDS):
                    _release_held()
                    return "decline"
                fr, h = pb._find_code_field(page)
                if h is not None:
                    reached_bank = True
                    branch = "code"
                    break
                if pb._is_alfa_app_push(page) and (time.monotonic() - c0) > 3 and not alfa_clicked[0]:
                    reached_bank = True
                    alfa_clicked[0] = True
                    io.send("📲 Альфа-Банк просит приложение. Жму «Подтвердить другим способом», затем код из СМС.")
                    if not pb._click_alfa_other(page):
                        io.send("⚠️ Не нашёл «Подтвердить другим способом».")
                    continue
                if pb._is_yoomoney(page) and (time.monotonic() - c0) > 8:
                    reached_bank = True
                    branch = "yoomoney"
                    break
                if pb._on_card_form(page) and time.monotonic() - c0 > 70:
                    _release_held()
                    if shot_holder is not None:
                        shot_holder["note"] = "форма карты так и осталась, банк не открылся"
                    return _unclear()
                if _back_on_start(pb, page):
                    stuck = stuck or time.monotonic()
                    if time.monotonic() - stuck > 8 and restarts < 3:
                        restarts += 1
                        stuck = None
                        io.send("💳 Снова стартовая страница, жму «оплатить картой»…")
                        clicked = False
                        for frs in pb._frames(page):
                            if pb._click_by_words(frs, ("оплатить картой",), timeout_ms=4000):
                                clicked = True
                                break
                        if clicked:
                            page.wait_for_timeout(700)
                            if _is_decline():
                                _release_held()
                                return "decline"
                            if _instant_fail():
                                retry_now = True
                                break
                            if not pb._on_card_form(page):
                                continue
                            try:
                                pb._type_card(page, card, io, time.monotonic() + int(cfg.get("card_form_wait_s") or 120))
                            except RuntimeError:
                                if _is_decline():
                                    _release_held()
                                    return "decline"
                                if _instant_fail():
                                    retry_now = True
                                    break
                            page.wait_for_timeout(2000)
                            nav = time.monotonic() + page_wait
                            c0 = time.monotonic()
                        continue
                else:
                    stuck = None
                page.wait_for_timeout(500)
            _release_held()
            if retry_now:
                if card_sent and not _is_beeline_error_page():
                    return _unclear()
                if not _click_beeline_retry():
                    return "beeline"
                continue
            break
        if branch == "wait":
            if pb._esim_ready(page):
                hold_tab = True
                return "success"
            r = ai_assist(io, page, cfg)   # PAY_AI_1591: интерактивный ИИ-агент на незнакомом 3DS
            if r == "success":
                hold_tab = True
            return r if r in ("success", "decline") else "no_code"
        if branch == "yoomoney":
            yoo = pb._yoomoney_push_flow(page, io, cfg)
            if yoo == "success":
                hold_tab = True
                return "success"
            if yoo == "fail":
                return "decline"
            if yoo == "timeout":
                return "no_code"
        verdict = pb._enter_3ds_code(page, io, cfg, page_wait, code_wait)
        if verdict == "cancelled":
            if getattr(io, "leave", None) and io.leave.is_set():
                return "leave"
            return "cancel"
        if verdict == "timeout":
            return "timeout"
        if verdict == "declined":
            return "decline"
        final = pb._wait_final_result(page, timeout_s=int(cfg.get("final_wait_seconds") or 70))
        if final == "success":
            hold_tab = True
            return "success"
        if final == "fail":
            return "decline"
        if pb._esim_ready(page):
            hold_tab = True
            return "success"
        return "no_code"
    except Exception:
        log("pay_one_link error:\n" + traceback.format_exc())
        # Код уже могли принять, и страница банка закрылась. Это не «страница не ответила».
        try:
            final = pb._wait_final_result(page, timeout_s=int(cfg.get("final_wait_seconds") or 70))
        except Exception:
            final = ""
        if final == "success":
            hold_tab = True
            return "success"
        if final == "fail":
            return "decline"
        return "site"
    finally:
        if shot_holder is not None:
            try:
                shot_holder["url"] = _stopped_url(page)
            except Exception:
                shot_holder["url"] = ""
            try:
                shot_holder["path"] = pb._shot(page, "final")
            except Exception:
                shot_holder["path"] = None
        try:
            if hold_tab:
                _park_tab(ctx, slot)
            else:
                ctx.close()
        except Exception:
            pass


def _stopped_url(page, fallback=""):
    """Адрес, на котором браузер остановился, как есть: в том числе about:blank и chrome-error."""
    try:
        return (page.url or "").strip()
    except Exception:
        return fallback


# ── ожидания в сессии ────────────────────────────────────────────────────────
def wait_card(io, timeout, prompt=True):
    if prompt:
        io.send("💳 Пришли карту одним сообщением: НОМЕР СРОК КОД (или «отмена»).",
                kb([[btn("🚪 Выйти из очереди", "op_leave")]]))
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if STOP_EVENT.is_set():
            return None
        if getattr(io, "leave", None) and io.leave.is_set():
            return "leave"
        ev = io.wait(min(20, deadline - time.monotonic()))
        if ev is None:
            continue
        if ev.get("kind") == "callback":
            io.answer(ev)
            if ev.get("data") == "op_leave":
                return "leave"
            if ev.get("data") == "sess_finish":
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
            io.send("⛔ Эта карта уже 3/3. Снова можно через 24 часа. Пришли другую.")
            continue
        return card
    return None


def ask_buttons(io, text, buttons, timeout, mapping):
    io.send(text, kb(buttons))
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if STOP_EVENT.is_set() or (getattr(io, "leave", None) and io.leave.is_set()):
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
def session_loop(tg, io, browser, payer_id, card, is_admin, slot=0, progress=None):
    global CONSEC_GATEWAY
    if progress is None:
        progress = {"site": 0, "relaunched": False}
    cur_card = card
    beeline_tries = 0
    link = None
    pay_cfg = dict(CFG)
    live = slot_proxy(slot)
    if live and not _proxy_open(live):
        spare = take_spare(slot)
        live = spare if spare and _proxy_open(spare) else ""
        if not live:
            SLOT_PAUSED.add(slot)
            io.send("⚠️ Этот выход не отвечает. Поставлю тебя на другое место.")
            return
    pay_cfg["browser_proxy"] = live
    while True:
        with ACTIVE_LOCK:
            if slot in ACTIVE_SLOTS:
                ACTIVE_SLOTS[slot]["holding"] = link is not None
        # карта исчерпана → новая/закончить
        if card_uses(cur_card) >= 3:
            ch = ask_buttons(io, f"⛔ Карта {mask_pan(cur_card)} — 3/3. Снова можно через 24 часа.",
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
            with ACTIVE_LOCK:
                if slot in ACTIVE_SLOTS:
                    ACTIVE_SLOTS[slot]["holding"] = link is not None
            if link is None:
                io.send("📑 Ссылки кончились. Ты остаёшься в очереди — как появятся новые, продолжим.")
                return   # НЕ выходим из очереди
        shot_holder = {}
        res = pay_one_link(io, browser, link["url"], cur_card, pay_cfg, shot_holder, slot,
                           quiet=progress["site"] > 0)
        shot = shot_holder.get("path")
        page_url = (shot_holder.get("url") or "").strip()
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
            progress["site"] = 0
            SLOT_FAILS[slot] = 0
            CONSEC_GATEWAY = 0
            if uses >= 3:
                ch = ask_buttons(io, f"⛔ Карта {mask_pan(cur_card)} — 3/3. Снова можно через 24 часа.",
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
                             [[btn("💳 Брать карту дальше", "sess_next")],
                              [btn("💳 Новая карта", "sess_newcard")],
                              [btn("🚪 Закончить работу", "sess_finish")]],
                             int(CFG["idle_timeout_s"]),
                             {"sess_next": "next", "sess_newcard": "new", "sess_finish": "finish"})
            if ch == "new":
                nc = wait_card(io, int(CFG["newcard_timeout_s"]))
                if nc is None:
                    break
                cur_card = nc
                beeline_tries = 0
                continue
            if ch != "next":
                break
            continue

        if res == "beeline":
            # Повторы кнопкой «попробовать ещё раз» уже сделаны на той же вкладке.
            io.send("❌ Билайн подряд не проводит эту ссылку — вернул её в очередь, беру следующую.")
            requeue_link(link); link = None; beeline_tries = 0
            SLOT_FAILS[slot] = SLOT_FAILS.get(slot, 0) + 1
            if SLOT_FAILS[slot] >= 4:
                spare = take_spare(slot)
                where = slot_name(slot)
                if spare:
                    pay_cfg["browser_proxy"] = spare
                    host = spare.split("@")[-1]
                    tg.send(ADMIN_ID, f"⚠️ Билайн не пускает {where}. Переключил это место на запасной IP {host}.")
                    io.send("⏸ Этот выход Билайн не пускает. Переключаюсь на запасной IP, продолжаем.")
                    continue
                SLOT_PAUSED.add(slot)
                other_alive = any(i not in SLOT_PAUSED for i in range(slot_count()))
                if not other_alive:
                    set_setting("accepting", "0")
                    tg.send(ADMIN_ID, "⚠️ Билайн не пускает ни один выход. Приём оплат ВЫКЛЮЧЕН.")
                    io.send("⏸ Пауза: Билайн временно не проводит оплаты. Попробуй позже.")
                    queue_leave(payer_id)
                    return
                tg.send(ADMIN_ID, f"⚠️ Билайн не пускает {where}. Это место на паузе, другое продолжает.")
                io.send("⏸ Этот выход Билайн не пускает. Ты остаёшься в очереди и продолжишь с другого места.")
                return
            continue

        if res == "bad_card":
            io.send("❌ Некорректный номер карты. Пришли другую.")
            nc = wait_card(io, int(CFG["newcard_timeout_s"]))
            if nc is None:
                requeue_link(link)
                break
            cur_card = nc
            beeline_tries = 0
            continue

        if res == "unclear":
            note = (shot_holder or {}).get("note") or "текст страницы не прочитался"
            io.send(f"⚠️ Не понял страницу. Карту заново не ввожу и отказом это не считаю.\n{note[:700]}")
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
                cur_card = nc
                beeline_tries = 0
                continue
            requeue_link(link); break

        if res == "decline":
            record_decline(tg, payer_id, link, cur_card, is_admin, io, shot, page_url)
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
            reason = "банк не показал поле кода, деньги могли списаться"
            mark_problem(link, reason)
            tg.send(ADMIN_ID, f"🗄 Ссылка снята с очереди\n{link['url']}\nПричина: {reason}\n🕒 {msk_ts()}",
                    kb([[btn("♻️ Вернуть в очередь", f"prob_ret:{link['id']}"),
                         btn("🗑 Удалить", f"prob_del:{link['id']}")]]))
            io.send(f"⚠️ Банк не показал поле кода. Ссылку снял, чтобы её не оплатили второй раз. "
                    f"Если деньги списались — напиши {ADMIN_CONTACT}.")
            link = None
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

        if res == "expensive":
            rub = (shot_holder or {}).get("rub")
            limit = (shot_holder or {}).get("limit") or setting("tariff_rub") or 300
            reason = f"сумма к оплате {rub:g} ₽, больше {float(limit):g} ₽"
            mark_problem(link, reason)
            tg.send(ADMIN_ID, f"🗄 Проблемная ссылка\n{link['url']}\nПричина: {reason}\n🕒 {msk_ts()}",
                    kb([[btn("♻️ Вернуть в очередь", f"prob_ret:{link['id']}"),
                         btn("🗑 Удалить", f"prob_del:{link['id']}")]]))
            io.send(f"⚠️ К оплате {rub:g} ₽ — больше {float(limit):g} ₽. Убрал ссылку, беру следующую.")
            link = None
            beeline_tries = 0
            continue

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

        if res == "proxy_dead":
            spare = take_spare(slot)
            if spare and _proxy_open(spare):
                pay_cfg["browser_proxy"] = spare
                io.send("⚠️ Выход не открылся. Переключил на запасной и открываю ту же ссылку.")
                continue
            SLOT_PAUSED.add(slot)
            requeue_link(link)
            io.send("⚠️ Этот выход не отвечает. Поставлю тебя на другое место.")
            return

        if res == "site":
            requeue_link(link)
            link = None
            beeline_tries = 0
            progress["site"] += 1
            n = progress["site"]
            dead = False
            try:
                dead = not browser.is_connected()
            except Exception:
                dead = True
            if n == 1 and not dead:
                io.send("🌐 Страница не ответила. Повторяю без новых сообщений, это не твоя вина.")
            if dead and not progress.get("relaunched"):
                return "relaunch"
            if n >= 3 or dead:
                io.send("⚠️ Страница не открывается. Остановил попытки, чтобы не слать сообщения.")
                queue_leave(payer_id)
                return
            continue

        if res == "leave":
            requeue_link(link)
            queue_leave(payer_id)
            io.send("Ты вышел из очереди.")
            return

        if res == "cancel":
            requeue_link(link); link = None
            ch = ask_buttons(io, "Отменил эту ссылку. Продолжаем?",
                             [[btn("💳 Брать карту дальше", "sess_next")],
                              [btn("💳 Новая карта", "sess_newcard")],
                              [btn("🚪 Закончить работу", "sess_finish")]],
                             int(CFG["idle_timeout_s"]),
                             {"sess_next": "next", "sess_newcard": "new", "sess_finish": "finish"})
            if ch == "new":
                nc = wait_card(io, int(CFG["newcard_timeout_s"]))
                if nc is None:
                    break
                cur_card = nc
                beeline_tries = 0
                continue
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


def session_thread(tg, payer_id, io, slot, pw):
    is_admin = (payer_id == ADMIN_ID)
    browser = None
    try:
        mins = max(1, int(CFG.get("idle_timeout_s") or 180) // 60)
        direct = payer_id in DIRECT_START
        DIRECT_START.discard(payer_id)
        head = "" if direct else "❗️Ваша очередь❗️\n"
        io.send(f"{head}{SEP}\n\n"
                f"⌛ {mins} мин — потом место уйдёт дальше\n\n"
                f"💳 Пришли данные карты одним сообщением:\n\n"
                f"НОМЕР  СРОК  CVV\n\n"
                f"{SEP}",
                kb([[btn("🚪 Выйти из очереди", "op_leave")]]))
        card = wait_card(io, int(CFG["idle_timeout_s"]), prompt=False)
        if card == "leave":
            queue_leave(payer_id)
            return
        if card is None:
            io.send("⌛ Карта не пришла — освобождаю очередь.")
            queue_leave(payer_id)
            return
        browser = pw.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        progress = {"site": 0, "relaunched": False}
        while True:
            action = session_loop(tg, io, browser, payer_id, card, is_admin, slot, progress)
            if action != "relaunch":
                break
            progress["relaunched"] = True
            try:
                browser.close()
            except Exception:
                pass
            browser = pw.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
    except Exception as exc:
        log("session error:\n" + traceback.format_exc())
        try:
            io.send("⚠️ Ошибка в сессии оплаты. Попробуй встать в очередь снова.")
        except Exception:
            pass
        if "greenlet" in type(exc).__module__ or type(exc).__name__ == "TargetClosedError":
            raise
    finally:
        with ACTIVE_LOCK:
            ACTIVE_SLOTS.pop(slot, None)
            if not ACTIVE_SLOTS:
                STOP_EVENT.clear()
        _wait_parked(slot)
        if browser is not None:
            try:
                browser.close()
            except Exception:
                pass


# Поток места живёт всё время работы панели. Playwright нельзя создавать
# и убивать в новом потоке на каждого человека: зелёный поток умирает и роняет остальные браузеры.
SLOT_JOBS = {}


def _slot_worker(slot):
    while True:
        job = SLOT_JOBS[slot].get()
        try:
            from playwright.sync_api import sync_playwright
        except Exception:
            tg, payer_id, io = job
            io.send("⚠️ Движок оплаты не готов на сервере (нет playwright/Chromium). Сообщи админу.")
            tg.send(ADMIN_ID, "⚠️ Не удалось запустить движок оплаты: нет playwright/Chromium.")
            with ACTIVE_LOCK:
                ACTIVE_SLOTS.pop(slot, None)
            continue
        try:
            with sync_playwright() as pw:
                while True:
                    tg, payer_id, io = job
                    session_thread(tg, payer_id, io, slot, pw)
                    job = SLOT_JOBS[slot].get()
        except Exception:
            log(f"slot {slot} browser driver перезапущен\n" + traceback.format_exc())
            time.sleep(1)


def ensure_slot_workers():
    for i in range(slot_count()):
        if i in SLOT_JOBS:
            continue
        SLOT_JOBS[i] = _queue.Queue()
        threading.Thread(target=_slot_worker, args=(i,), daemon=True, name=f"pay-slot-{i}").start()


def maybe_start_session(tg):
    """Заполняет свободные места следующими людьми из очереди. Ссылки они берут уже внутри, по одной."""
    stalled = []
    with ACTIVE_LOCK:
        if not accepting() or links_count() <= 0:
            why = "приём выключен" if not accepting() else "оплат в очереди нет"
            for payer in queue_list():
                if _STALL_NOTE.get(payer) != why:
                    _STALL_NOTE[payer] = why
                    stalled.append((payer, why))
            pass
        else:
            busy = {s["payer"] for s in ACTIVE_SLOTS.values()}
            waiting = [p for p in queue_list() if p not in busy]
            free = [i for i in range(slot_count()) if i not in ACTIVE_SLOTS and i not in SLOT_PAUSED]
            # ссылка уже у того, кто её держит; место ждём только под ещё не взятые
            pending = sum(1 for s in ACTIVE_SLOTS.values() if not s.get("holding"))
            room = max(0, links_count() - pending)
            started = []
            for slot, payer in zip(free, waiting[:room]):
                io = PayerIO(tg, payer)
                ACTIVE_SLOTS[slot] = {"payer": payer, "io": io}
                ensure_slot_workers()
                SLOT_JOBS[slot].put((tg, payer, io))
                started.append(payer)
                _STALL_NOTE.pop(payer, None)
            if waiting and not started:
                why = "свободных мест нет" if not free else "ссылки уже разбирают"
                for payer in waiting:
                    if _STALL_NOTE.get(payer) != why:
                        _STALL_NOTE[payer] = why
                        stalled.append((payer, why))
    for payer, why in stalled:
        tg.send(payer, f"⏳ Ты в очереди, но оплата ещё не открылась: {why}.")


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
                    hit = next((s for s in ACTIVE_SLOTS.values() if s["payer"] == ev.get("uid")), None)
                    if ev["kind"] == "callback" and (ev.get("data") or "") == "op_leave":
                        tg.answer_cb(ev.get("id"))
                        uid = ev.get("uid")
                        queue_leave(uid)
                        if ev.get("chat_id"):
                            if uid == ADMIN_ID:
                                show_admin_menu(tg, ev["chat_id"], ev.get("message_id"))
                            else:
                                op = get_op(uid)
                                if op:
                                    show_operator_menu(tg, op, ev["chat_id"], ev.get("message_id"))
                        if hit:
                            hit["io"].leave.set()
                            hit["io"].put({"kind": "callback", "data": "op_leave", "id": "", "uid": uid})
                        continue
                    _pay_cb = {
                        "sess_next", "sess_same", "sess_newcard", "sess_finish",
                        "ai_call", "ai_cancel", "resend_sms", "yoo_sms", "op_leave",
                    }
                    _cmd = (ev["kind"] == "text" and ev.get("text", "").startswith("/"))
                    _data = ev.get("data") or ""
                    _for_pay = ev["kind"] == "text" or _data in _pay_cb or _data.startswith("sess_")
                    if hit and ev["kind"] in ("text", "callback") and _for_pay and not _cmd:
                        hit["io"].put(ev)   # код, отмена и кнопки оплаты — в его сессию
                        continue
                    if ev["kind"] == "callback":
                        handle_callback(tg, ev)
                    elif ev["kind"] == "text":
                        handle_text(tg, ev)
                except Exception:
                    log("handler error:\n" + traceback.format_exc())
            maybe_autostart(tg)
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
    if len(sys.argv) > 2 and sys.argv[1] == "--qr-child":
        _qr_child(sys.argv[2])
    else:
        main()

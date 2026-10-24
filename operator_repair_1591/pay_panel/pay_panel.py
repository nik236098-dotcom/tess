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

import json
import os
import re
import sqlite3
import sys
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

    def send(self, chat_id, text, kb=None):
        data = {"chat_id": chat_id, "text": str(text)[:4000], "disable_web_page_preview": True}
        if kb is not None:
            data["reply_markup"] = json.dumps(kb, ensure_ascii=False)
        return self._call("sendMessage", **data)

    def edit(self, chat_id, message_id, text, kb=None):
        data = {"chat_id": chat_id, "message_id": message_id, "text": str(text)[:4000],
                "disable_web_page_preview": True}
        if kb is not None:
            data["reply_markup"] = json.dumps(kb, ensure_ascii=False)
        return self._call("editMessageText", **data)

    def answer_cb(self, cb_id, text=""):
        self._call("answerCallbackQuery", callback_query_id=cb_id, text=text[:180])

    def get_chat_admins(self, chat_id):
        r = self._call("getChatAdministrators", chat_id=chat_id)
        return r.get("result", []) if isinstance(r, dict) else []

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
      card_mask TEXT, result TEXT, amount REAL DEFAULT 0, url_final TEXT DEFAULT '', at INTEGER, canceled INTEGER DEFAULT 0);
    CREATE TABLE IF NOT EXISTS payouts(id INTEGER PRIMARY KEY AUTOINCREMENT, operator_id INTEGER, amount REAL,
      status TEXT DEFAULT 'pending', requested_at INTEGER, decided_at INTEGER DEFAULT 0);
    CREATE TABLE IF NOT EXISTS queue(operator_id INTEGER PRIMARY KEY, joined_at INTEGER, last_action INTEGER);
    CREATE TABLE IF NOT EXISTS settings(k TEXT PRIMARY KEY, v TEXT);
    """)
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


def kb(rows):
    return {"inline_keyboard": rows}


def btn(text, data):
    return {"text": text, "callback_data": data}


def accepting():
    return setting("accepting", "1") == "1"


def op_display(op):
    return ("@" + op["username"]) if op.get("username") else ("ID " + str(op["tg_id"]))


# ── валидация карты (ЭТАП 2 использует) ──────────────────────────────────────
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
    status = "🟢 оплаты требуются" if (accepting() and links_count()) else "⚪️ оплат нет"
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
        rows.append([btn("🚪 Выйти из очереди", "op_leave")])
    else:
        rows.append([btn("▶️ Встать в очередь", "op_join")])
    rows.append([btn("💸 Запросить выплату", "op_payout"), btn("🔄 Обновить", "op_refresh")])
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
         f"📥 Приём оплат: {'🟢 включён' if accepting() else '🔴 выключен'}\n"
         f"📑 В очереди: {links_count()}   🗄 Проблемных: {prob}\n"
         f"🧑‍🤝‍🧑 Оплатчиков: {n_ops} (в очереди {len(queue_list())})\n"
         f"💰 Всего к выплате: {owed:.2f} $\n{SEP}")
    admin_in_q = ADMIN_ID in queue_list()
    rows = [
        [btn("🚪 Выйти из очереди (оплата)", "adm_leaveq") if admin_in_q
         else btn("💳 Оплатить самому (встать в очередь)", "adm_joinq")],
        [btn("📤 Загрузить ссылки", "adm_load")],
        [btn("🔴 Выключить приём" if accepting() else "🟢 Включить приём", "adm_toggle")],
        [btn("🧑‍🤝‍🧑 Оплатчики", "adm_ops")],
        [btn(f"💸 Запросы на выплаты · {n_pay}", "adm_payouts")],
        [btn(f"🗄 Проблемные ссылки · {prob}", "adm_prob")],
        [btn("⚙️ Настройки", "adm_settings")],
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
            tg.edit(chat_id, mid, "📣 Добавь бота в канал АДМИНОМ, потом пришли сюда @юзернейм канала или перешли из него сообщение. (Выбор из списка подключим на этапе логов.)",
                    kb([[btn("⬅️ Назад", "adm_settings")]])); return
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


# ── главный цикл ─────────────────────────────────────────────────────────────
def main():
    db_init()
    tg = Telegram(CFG)
    me = tg._call("getMe")
    uname = (me.get("result") or {}).get("username", "?")
    log(f"запущен как @{uname}. Админ: {ADMIN_ID}")
    tg.send(ADMIN_ID, "🛠 Панель оплат запущена (Этап 1: каркас).")
    show_admin_menu(tg, ADMIN_ID)
    while True:
        try:
            for ev in tg.get_updates(timeout=25):
                try:
                    if ev["kind"] == "callback":
                        handle_callback(tg, ev)
                    elif ev["kind"] == "text":
                        handle_text(tg, ev)
                except Exception:
                    log("handler error:\n" + traceback.format_exc())
        except Exception:
            log("loop error:\n" + traceback.format_exc())
            time.sleep(3)


if __name__ == "__main__":
    main()

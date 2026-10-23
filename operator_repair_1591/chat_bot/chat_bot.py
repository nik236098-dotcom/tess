#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Дипсик — бот для рабочего чата eSIM: считает QR и реакции, общается (DeepSeek),
модерирует (удаляет дубли и указанные сообщения — всегда с подтверждением).

Отдельный бот (как pay_bot), со своим токеном. Запуск:
    python3 chat_bot.py
Конфиг рядом или /opt/chat_bot/config.json:
    {
      "token": "ТОКЕН_БОТА",
      "proxy": "socks5h://логин:пароль@хост:порт" | "direct",
      "deepseek_api_key": "sk-...",
      "deepseek_model": "deepseek-chat",
      "deepseek_url": "https://api.deepseek.com/chat/completions",
      "ds_proxy": "direct",
      "triggers": ["дипсик", "deepseek", "дип"],
      "tz_offset_hours": 3
    }

Правила (по ТЗ владельца):
 - вызывается ТОЛЬКО по слову «дипсик/deepseek/дип» или @юзернейм, либо reply на его сообщение;
 - на остальное молчит; после ответа держит диалог в ветке (reply на него);
 - QR = фото + номер в подписи; дубль = тот же номер повторно;
 - реакции: ❤ — в работе, 🔥 — успех, 👎 — не успешно;
 - удаление доступно любому, но ТОЛЬКО после подтверждения (Да/Нет);
 - характер: дерзкий, пафосный, жёстко шутит, бывает мат; отвечает коротко и по-человечески.
"""
import json
import os
import re
import sys
import time
import html
import random
import sqlite3
import datetime
import threading
import collections

try:
    import requests
except Exception:
    print("нужен requests: pip install 'requests[socks]'", file=sys.stderr)
    raise

HERE = os.path.dirname(os.path.abspath(__file__))


def _load_config():
    for path in (os.path.join(HERE, "config.json"), "/opt/chat_bot/config.json", "/opt/chat_bot/chat_bot_config.json"):
        try:
            with open(path, encoding="utf-8") as f:
                cfg = json.load(f)
            cfg["_path"] = path
            return cfg
        except Exception:
            continue
    print("нет config.json (рядом со скриптом или /opt/chat_bot/config.json)", file=sys.stderr)
    sys.exit(1)


CFG = _load_config()
TOKEN = str(CFG.get("token") or "").strip()
TRIGGERS = [str(w).lower() for w in (CFG.get("triggers") or ["дипсик", "deepseek", "дип"])]
TZ = datetime.timezone(datetime.timedelta(hours=float(CFG.get("tz_offset_hours", 3))))  # МСК по умолчанию
AGENT_CONTEXT = int(CFG.get("agent_context", 500))   # сколько последних QR ИИ видит для разбора («память»)
DB_PATH = os.path.join(HERE, "chat_bot.sqlite3")
BOT_USERNAME = ""   # заполнится из getMe

PERSONA = (
    "Ты — Дипсик, свой в доску участник закрытого рабочего чата по eSIM. "
    "Характер: дерзкий, пафосный, жёстко шутишь, не стесняешься крепкого словца и мата. "
    "Говоришь как живой человек — коротко и по делу, 1–3 фразы, без воды, без канцелярита, без смайликов-простыней. "
    "Не извиняешься, не читаешь морали, не признаёшься что ты ИИ, не используешь шаблонные фразы. "
    "Если дали цифры/факты — выдаёшь их своими словами, с характером. "
    "Мат — ок, но без травли конкретных людей, без угроз и без оскорблений по нации/религии/т.п. "
    "Отвечай на русском."
)

# ---------------------------------------------------------------- сеть/телеграм
def _proxies(key):
    p = str(CFG.get(key) or "").strip()
    if p.lower() in ("", "direct", "none", "off", "no", "-"):
        return None
    return {"http": p, "https": p}


TG_PROXIES = _proxies("proxy")
DS_PROXIES = _proxies("ds_proxy") if CFG.get("ds_proxy") is not None else TG_PROXIES


def tg(method, data=None, timeout=35):
    url = "https://api.telegram.org/bot%s/%s" % (TOKEN, method)
    try:
        r = requests.post(url, data=data or {}, proxies=TG_PROXIES, timeout=timeout)
        return r.json()
    except Exception as exc:
        print("[TG] %s: %s" % (method, exc), flush=True)
        return {"ok": False, "error": str(exc)}


def send(chat_id, text, reply_to=None, markup=None):
    data = {"chat_id": chat_id, "text": text[:4000], "disable_web_page_preview": "true"}
    if reply_to:
        data["reply_to_message_id"] = reply_to
    if markup:
        data["reply_markup"] = json.dumps(markup, ensure_ascii=False)
    return tg("sendMessage", data)


def delete_message(chat_id, message_id):
    return tg("deleteMessage", {"chat_id": chat_id, "message_id": message_id})


def answer_cb(cb_id, text=""):
    tg("answerCallbackQuery", {"callback_query_id": cb_id, "text": text[:180]})


# ---------------------------------------------------------------- DeepSeek
def deepseek(messages, max_tokens=220, temperature=1.0):
    key = str(CFG.get("deepseek_api_key") or "").strip()
    if not key:
        return None
    url = str(CFG.get("deepseek_url") or "https://api.deepseek.com/chat/completions")
    model = str(CFG.get("deepseek_model") or "deepseek-flash")   # как в основном боте
    try:
        r = requests.post(url, headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"},
                          json={"model": model, "messages": messages, "max_tokens": max_tokens,
                                "temperature": temperature},
                          proxies=DS_PROXIES, timeout=60)
        j = r.json()
        return (j["choices"][0]["message"]["content"] or "").strip()
    except Exception as exc:
        print("[DS] %s" % exc, flush=True)
        return None


# ---------------------------------------------------------------- база данных
def db():
    con = sqlite3.connect(DB_PATH)
    con.execute("CREATE TABLE IF NOT EXISTS qr(chat_id INTEGER, msg_id INTEGER, user TEXT, uid INTEGER, number TEXT, ts REAL, PRIMARY KEY(chat_id,msg_id))")
    con.execute("CREATE TABLE IF NOT EXISTS reactions(chat_id INTEGER, msg_id INTEGER, uid INTEGER, emoji TEXT, PRIMARY KEY(chat_id,msg_id,uid))")
    con.execute("CREATE TABLE IF NOT EXISTS memory(chat_id INTEGER, role TEXT, text TEXT, ts REAL)")
    return con


def remember(chat_id, role, text):
    con = db()
    con.execute("INSERT INTO memory(chat_id,role,text,ts) VALUES(?,?,?,?)", (chat_id, role, text[:1500], time.time()))
    # держим последние 40 реплик на чат
    con.execute("DELETE FROM memory WHERE chat_id=? AND rowid NOT IN (SELECT rowid FROM memory WHERE chat_id=? ORDER BY ts DESC LIMIT 40)", (chat_id, chat_id))
    con.commit(); con.close()


def recall(chat_id, limit=16):
    con = db()
    rows = con.execute("SELECT role,text FROM memory WHERE chat_id=? ORDER BY ts DESC LIMIT ?", (chat_id, limit)).fetchall()
    con.close()
    return [{"role": r, "content": t} for r, t in reversed(rows)]


# ---------------------------------------------------------------- QR и реакции
_HEARTS = "❤🧡💛💚💙💜🖤🤍🤎♥"


def _digits(s):
    return re.sub(r"\D", "", str(s or ""))


def extract_number(text):
    """Номер из подписи QR: 10–11 цифр, нормализуем к 7XXXXXXXXXX."""
    d = _digits(text)
    if len(d) == 11 and d[0] in "78":
        return "7" + d[1:]
    if len(d) == 10:
        return "7" + d
    return ""


def pretty_number(num):
    d = num
    if len(d) == 11 and d[0] == "7":
        return "+7 %s %s %s %s" % (d[1:4], d[4:7], d[7:9], d[9:11])
    return num


def react_kind(emoji):
    e = emoji or ""
    if "🔥" in e:
        return "success"
    if "👎" in e:
        return "fail"
    if any(h in e for h in _HEARTS):
        return "inwork"
    return "other"


def record_qr(chat_id, msg):
    """Если сообщение — фото с номером в подписи, запоминаем как QR. Возвращает number или ''."""
    if not msg.get("photo"):
        return ""
    cap = msg.get("caption") or ""
    num = extract_number(cap)
    if not num:
        return ""
    frm = msg.get("from") or {}
    user = frm.get("username") or frm.get("first_name") or str(frm.get("id") or "")
    con = db()
    con.execute("INSERT OR IGNORE INTO qr(chat_id,msg_id,user,uid,number,ts) VALUES(?,?,?,?,?,?)",
                (chat_id, msg.get("message_id"), user, frm.get("id"), num, float(msg.get("date") or time.time())))
    con.commit(); con.close()
    return num


def set_reaction(chat_id, msg_id, uid, emojis):
    """emojis — список эмодзи реакции пользователя (новое состояние). Пусто = убрал реакцию."""
    con = db()
    emoji = ",".join(emojis)
    if emoji:
        con.execute("INSERT OR REPLACE INTO reactions(chat_id,msg_id,uid,emoji) VALUES(?,?,?,?)", (chat_id, msg_id, uid, emoji))
    else:
        con.execute("DELETE FROM reactions WHERE chat_id=? AND msg_id=? AND uid=?", (chat_id, msg_id, uid))
    con.commit(); con.close()


def set_reaction_count(chat_id, msg_id, emojis):
    """Для анонимных реакций (message_reaction_count): храним агрегат под uid=0."""
    con = db()
    emoji = ",".join(emojis)
    if emoji:
        con.execute("INSERT OR REPLACE INTO reactions(chat_id,msg_id,uid,emoji) VALUES(?,?,0,?)", (chat_id, msg_id, emoji))
    else:
        con.execute("DELETE FROM reactions WHERE chat_id=? AND msg_id=? AND uid=0", (chat_id, msg_id))
    con.commit(); con.close()


def _msg_reactions(con, chat_id, msg_id):
    rows = con.execute("SELECT emoji FROM reactions WHERE chat_id=? AND msg_id=?", (chat_id, msg_id)).fetchall()
    kinds = set()
    for (e,) in rows:
        for part in str(e).split(","):
            kinds.add(react_kind(part))
    return kinds


def qr_status(kinds):
    if "success" in kinds:
        return "success"
    if "fail" in kinds:
        return "fail"
    if "inwork" in kinds:
        return "inwork"
    return "none"


# ---------------------------------------------------------------- статистика
_PERIOD_RE = re.compile(r"(\d+)\s*(минут|мин|часов|часа|час|дней|дня|день|суток|сутки|сут|недел)", re.I)


def _window_since(text):
    low = text.lower()
    now = time.time()
    m = _PERIOD_RE.search(low)   # «за последние 2 часа / 30 минут / 3 дня / 2 недели»
    if m:
        n = int(m.group(1)); unit = m.group(2)
        if unit.startswith("мин"):
            return now - n * 60, "за последние %d мин" % n
        if unit.startswith("час"):
            return now - n * 3600, "за последние %d ч" % n
        if unit.startswith("недел"):
            return now - n * 7 * 86400, "за последние %d нед." % n
        return now - n * 86400, "за последние %d дн." % n
    if "час" in low:
        return now - 3600, "за последний час"
    if "недел" in low:
        return now - 7 * 86400, "за неделю"
    if low.strip() in ("всё", "все", "all") or any(w in low for w in ("всё время", "все время", "за всё", "за все", "вообще", "всего", "всех", "за всю")):
        return 0, "за всё время"
    midnight = datetime.datetime.now(TZ).replace(hour=0, minute=0, second=0, microsecond=0)
    return midnight.timestamp(), "за сегодня"


def compute_stats(chat_id, since, uid=None, name=None):
    """Статистика по присутствию реакций. uid/name — фильтр по человеку (None = все)."""
    con = db()
    rows = con.execute("SELECT msg_id,user,uid FROM qr WHERE chat_id=? AND ts>=?", (chat_id, since)).fetchall()
    per_user = collections.defaultdict(lambda: collections.Counter())
    total = collections.Counter()
    for msg_id, user, quid in rows:
        if uid is not None and quid != uid:
            continue
        if name is not None and name.lower() not in str(user or "").lower():
            continue
        kinds = _msg_reactions(con, chat_id, msg_id)
        for tgt in (per_user[user], total):
            tgt["всего"] += 1
            if "inwork" in kinds:
                tgt["taken"] += 1      # ❤ — взято в работу (в т.ч. потом успех/неуспех)
            if "success" in kinds:
                tgt["success"] += 1
            if "fail" in kinds:
                tgt["fail"] += 1
            if not kinds:
                tgt["none"] += 1
    con.close()
    return total, per_user


def _fmt_line(name, c):
    parts = ["взято в работу %d" % c["taken"]]
    if c["success"]:
        parts.append("успех %d" % c["success"])
    if c["fail"]:
        parts.append("неуспех %d" % c["fail"])
    if c["none"]:
        parts.append("без реакции %d" % c["none"])
    if not c["success"] and not c["fail"]:
        parts.append("других реакций не было")
    return "%s: отправлено %d QR, %s" % (name, c["всего"], ", ".join(parts))


def stats_answer(chat_id, period_text, who, frm):
    since, label = _window_since(period_text or "сегодня")
    uid = name = None
    w = str(who or "all").strip().lower()
    if w in ("me", "я", "мной", "мои", "сам"):
        uid = (frm or {}).get("id")
    elif w not in ("all", "все", "всё", "всех", ""):
        name = str(who)
    total, per_user = compute_stats(chat_id, since, uid=uid, name=name)
    if total["всего"] == 0:
        return "%s: ничего. По нулям." % label.capitalize()
    lines = ["📊 %s:" % label]
    for user, c in sorted(per_user.items(), key=lambda x: -x[1]["всего"]):
        lines.append(_fmt_line(user or "кто-то", c))
    return "\n".join(lines)


# ---------------------------------------------------------------- дубли
def find_duplicates(chat_id, since=0, last_n=None):
    """Дубли по номеру. last_n — искать среди последних N QR; иначе за период с since.
    Возвращает [(number, keep_msg_id, [dup_msg_ids...])] (keep — самый ранний)."""
    con = db()
    if last_n:
        rows = con.execute("SELECT number,msg_id FROM qr WHERE chat_id=? ORDER BY ts DESC, msg_id DESC LIMIT ?",
                           (chat_id, int(last_n))).fetchall()
        rows = list(reversed(rows))   # вернём хронологию: первый останется
    else:
        rows = con.execute("SELECT number,msg_id FROM qr WHERE chat_id=? AND ts>=? ORDER BY ts ASC, msg_id ASC",
                           (chat_id, since)).fetchall()
    con.close()
    by_num = collections.OrderedDict()
    for number, msg_id in rows:
        by_num.setdefault(number, []).append(msg_id)
    return [(number, ids[0], ids[1:]) for number, ids in by_num.items() if len(ids) > 1]


# ---------------------------------------------------------------- логика запросов
PENDING = {}            # chat_id -> {"ids":[...], "numbers":[...], "ts":...}


def _today_since():
    return datetime.datetime.now(TZ).replace(hour=0, minute=0, second=0, microsecond=0).timestamp()


def is_triggered(chat_id, msg):
    """True только если к боту обратились: слово-триггер ОТДЕЛЬНЫМ словом, @юзернейм или reply на его сообщение.
    Продолжение диалога — через reply на бота (настоящая ветка), а не по таймеру, чтобы не лезть в чужие сообщения."""
    low = (msg.get("text") or msg.get("caption") or "").lower()
    for w in TRIGGERS:
        # отдельным словом: «дип» не сработает внутри «диплом», «deepseek» — внутри «deepseeker»
        if re.search(r"(?<![0-9a-zа-яё])" + re.escape(w) + r"(?![0-9a-zа-яё])", low):
            return True
    if BOT_USERNAME and ("@" + BOT_USERNAME.lower()) in low:
        return True
    rf = (msg.get("reply_to_message") or {}).get("from") or {}
    if rf.get("is_bot") and str(rf.get("username", "")).lower() == BOT_USERNAME.lower():
        return True
    return False


def is_delete_request(text):
    low = text.lower()
    return any(w in low for w in ("удали", "удалить", "снеси", "снос", "убери", "почисти", "чисти",
                                  "делит", "делет", "дроп", "грохни", "killн"))


def is_stats_request(text):
    low = text.lower()
    return any(w in low for w in ("скольк", "скок", "статист", "залит", "залил", "накид", "за день", "за час",
                                  "за сегодня", "итог", "процент", "успех", "наработал", "сводк", "чек", "куар",
                                  "отправ", "за послед"))


def kb_yes_no():
    return {"inline_keyboard": [[{"text": "✅ Да", "callback_data": "del_yes"},
                                 {"text": "✖️ Нет", "callback_data": "del_no"}]]}


def confirm_delete(chat_id, ids, listing, mid, head="Щас грохнем эту хуйню — уверен?"):
    ids = [i for i in ids if i]
    if not ids:
        send(chat_id, random.choice(["Нечего удалять.", "Пусто, удалять нечего."]), reply_to=mid)
        return
    PENDING[chat_id] = {"ids": ids, "ts": time.time()}
    body = ("\n" + listing) if listing else ""
    send(chat_id, "%s%s" % (head, body), reply_to=mid, markup=kb_yes_no())


def _last_qr_ids(chat_id, n, uid=None, name=None):
    con = db()
    rows = con.execute("SELECT msg_id,user,uid,number FROM qr WHERE chat_id=? ORDER BY ts DESC", (chat_id,)).fetchall()
    con.close()
    out = []
    for msg_id, user, quid, number in rows:
        if uid is not None and quid != uid:
            continue
        if name is not None and name.lower() not in str(user or "").lower():
            continue
        out.append((msg_id, number))
        if len(out) >= n:
            break
    return out


def _dups_scope(chat_id, period_text, last_n):
    if last_n:
        return find_duplicates(chat_id, last_n=int(last_n)), "среди последних %d" % int(last_n)
    since = 0 if _window_since(period_text or "")[1] == "за всё время" else _today_since()
    label = _window_since(period_text or "")[1] if period_text else "за сегодня"
    return find_duplicates(chat_id, since=since), label


def do_check_dups(chat_id, period_text, last_n, mid):
    """Проверить (показать) дубли, НЕ удаляя."""
    dups, scope = _dups_scope(chat_id, period_text, last_n)
    if not dups:
        send(chat_id, "Дублей %s нет, чисто." % scope, reply_to=mid)
        return
    repeats = sum(len(extra) for _, _, extra in dups)
    listing = "\n".join("• " + pretty_number(n) + " ×%d" % (len(extra) + 1) for n, _, extra in dups[:40])
    send(chat_id, "Дубли %s (%d повторов):\n%s\n\nСкажи «удали дубли» — снесу лишние." % (scope, repeats, listing),
         reply_to=mid)


def do_delete_dups(chat_id, period_text, last_n, mid):
    dups, scope = _dups_scope(chat_id, period_text, last_n)
    if not dups:
        send(chat_id, random.choice(["Дублей %s нет, чисто." % scope, "Повторов %s не нашёл." % scope]), reply_to=mid)
        return
    ids, nums = [], []
    for number, keep, extra in dups:
        ids += extra
        nums.append(pretty_number(number) + " ×%d" % (len(extra) + 1))
    listing = "Вот чё собрал (%d дублей %s):\n%s" % (len(ids), scope, "\n".join("• " + n for n in nums[:40]))
    confirm_delete(chat_id, ids, listing, mid)


def do_delete_last(chat_id, n, who, frm, mid):
    n = max(1, min(int(n or 1), 50))
    uid = name = None
    w = str(who or "all").strip().lower()
    if w in ("me", "я", "мной", "мои", "сам"):
        uid = (frm or {}).get("id")
    elif w not in ("all", "все", "всё", ""):
        name = str(who)
    items = _last_qr_ids(chat_id, n, uid=uid, name=name)
    if not items:
        send(chat_id, "Нет таких QR, нечего сносить.", reply_to=mid)
        return
    listing = "Последние %d:\n%s" % (len(items), "\n".join("• " + pretty_number(num) for _, num in items))
    confirm_delete(chat_id, [mid_ for mid_, _ in items], listing, mid)


def do_delete_this(chat_id, rep_mid, mid):
    confirm_delete(chat_id, [rep_mid], "", mid, head="Снести это сообщение? Уверен?")


def do_pending_delete(chat_id):
    item = PENDING.pop(chat_id, None)
    if not item:
        return "Нечего подтверждать — я уже забыл."
    ok = 0
    for mid in item["ids"]:
        r = delete_message(chat_id, mid)
        if r.get("ok"):
            ok += 1
    con = db()
    for mid in item["ids"]:
        con.execute("DELETE FROM qr WHERE chat_id=? AND msg_id=?", (chat_id, mid))
        con.execute("DELETE FROM reactions WHERE chat_id=? AND msg_id=?", (chat_id, mid))
    con.commit(); con.close()
    return "Готово, снёс %d. Чат чище, чем твоя совесть." % ok


def _agent_data_block(chat_id, limit):
    con = db()
    rows = con.execute("SELECT msg_id,user,number,ts FROM qr WHERE chat_id=? ORDER BY ts DESC, msg_id DESC LIMIT ?",
                       (chat_id, int(limit))).fetchall()
    out = []
    for msg_id, user, number, ts in rows:
        kinds = _msg_reactions(con, chat_id, msg_id)
        mark = "🔥" if "success" in kinds else ("👎" if "fail" in kinds else ("❤" if "inwork" in kinds else "—"))
        t = datetime.datetime.fromtimestamp(ts, TZ).strftime("%d.%m %H:%M")
        out.append("%s | %s | %s | %s" % (user or "?", t, pretty_number(number), mark))
    con.close()
    return "\n".join(reversed(out))   # в хронологическом порядке


def _agent_summaries(chat_id):
    lines = []
    for period in ("сегодня", "неделю", "всё"):
        since, label = _window_since(period)
        total, _ = compute_stats(chat_id, since)
        lines.append("%s: всего %d, 🔥%d 👎%d ❤взято %d, —без реакции %d" %
                     (label, total["всего"], total["success"], total["fail"], total["taken"], total["none"]))
    return "\n".join(lines)


def analyst_reply(chat_id, text, frm):
    """ИИ сам разбирает данные чата (до AGENT_CONTEXT последних QR) + точные сводки от кода."""
    data = _agent_data_block(chat_id, AGENT_CONTEXT)
    summ = _agent_summaries(chat_id)
    sys = (PERSONA + "\nТы ведёшь учёт QR eSIM в этом чате. Отвечай коротко, по делу, с характером. "
           "Для вопросов про ТОЧНОЕ количество бери числа из блока «Сводка». Для разбора (найди, сравни, кто, "
           "странности) смотри блок «Последние QR». Реакции: ❤ взят в работу, 🔥 успех, 👎 неуспех, — без реакции. "
           "Кто спрашивает: %s." % ((frm or {}).get("username") or (frm or {}).get("first_name") or "участник"))
    ctx = "Сводка (точные цифры от кода):\n%s\n\nПоследние %d QR (кто | время | номер | реакция):\n%s" % (summ, AGENT_CONTEXT, data or "пусто")
    msgs = [{"role": "system", "content": sys}, {"role": "system", "content": ctx}] + recall(chat_id) + [{"role": "user", "content": text}]
    out = deepseek(msgs, max_tokens=450)
    if not out:
        out = "Чёт DeepSeek недоступен — повтори чуть позже."
    remember(chat_id, "user", text)
    remember(chat_id, "assistant", out)
    return out


def persona_reply(chat_id, user_text, extra_context=""):
    msgs = [{"role": "system", "content": PERSONA}]
    if extra_context:
        msgs.append({"role": "system", "content": extra_context})
    msgs += recall(chat_id)
    msgs.append({"role": "user", "content": user_text})
    out = deepseek(msgs)
    if not out:
        out = random.choice(["Чёт DeepSeek залип, повтори.", "Нейронка молчит как партизан, спроси ещё раз."])
    remember(chat_id, "user", user_text)
    remember(chat_id, "assistant", out)
    return out


ROUTER_SYS = (
    "Ты — разборщик намерений для чат-бота учёта eSIM QR. Пойми ВОЛЬНУЮ речь и сленг пользователя "
    "(напр. «делитни последние 3», «снеси дубли», «скок я накидал за час», «чекни Гену», «убери вот это»). "
    "Верни СТРОГО один JSON без пояснений и без markdown:\n"
    '{"action":"chat|analyst|stats|check_dups|del_dups|del_last|del_this","args":{...}}\n'
    "Действия:\n"
    "- stats: ТОЧНАЯ статистика-сводка за период. args {\"period\":\"<напр 2 часа|30 минут|сегодня|неделю|всё>\",\"who\":\"me|all|<имя>\"}\n"
    "- analyst: любой другой вопрос/задача ПО ДАННЫМ чата (найди, сравни, кто лучший/худший, "
    "уникальные, что странного, разбор). args {}\n"
    "- check_dups: ПОКАЗАТЬ дубли, НЕ удаляя («проверь/глянь дубли», «есть ли повторы»). "
    "args {\"period\":\"<или пусто>\",\"last_n\":<сколько последних QR проверить, или 0>}\n"
    "- del_dups: УДАЛИТЬ дубли. args {\"period\":\"<или пусто>\",\"last_n\":<или 0>}\n"
    "- del_last: удалить N последних QR. args {\"n\":<число>,\"who\":\"me|all|<имя>\"}\n"
    "- del_this: удалить сообщение, на которое пользователь ОТВЕТИЛ (reply). args {}\n"
    "- chat: просто поболтать/ответить. args {}\n"
    "«проверь дубли последние 30» → check_dups last_n=30. «удали дубли» → del_dups. "
    "who=\"me\" если про себя. Не про удаление/проверку/статистику — action=\"chat\". Только JSON."
)


def _extract_last_n(low):
    m = re.search(r"(\d+)\s*(?:последн|куар|qr|штук|шт|сообщ)", low) or re.search(r"последни[ехй]*\s*(\d+)", low)
    return int(m.group(1)) if m else 0


def _json_from(s):
    m = re.search(r"\{.*\}", s or "", re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        return None


def route_intent(chat_id, text, has_reply):
    """DeepSeek разбирает намерение. Фолбэк на ключевые слова, если DeepSeek недоступен."""
    j = _json_from(deepseek([{"role": "system", "content": ROUTER_SYS},
                             {"role": "user", "content": text}], max_tokens=120, temperature=0) or "")
    if isinstance(j, dict) and j.get("action") in ("chat", "analyst", "stats", "check_dups", "del_dups", "del_last", "del_this"):
        return j.get("action"), (j.get("args") or {})
    # фолбэк без нейросети
    low = text.lower()
    last_n = _extract_last_n(low)
    is_dups = "дубл" in low or "повтор" in low or "одинаков" in low
    is_check = any(w in low for w in ("провер", "глян", "посмотр", "есть ли", "покажи"))
    if is_dups and is_check and not is_delete_request(text):
        return "check_dups", {"period": "всё" if "всё" in low or "все " in low else "", "last_n": last_n}
    if is_delete_request(text):
        if is_dups:
            return "del_dups", {"period": "всё" if "всё" in low or "все " in low else "", "last_n": last_n}
        if last_n:
            who = "me" if re.search(r"(мной|мои|я |меня)", low) else "all"
            return "del_last", {"n": last_n, "who": who}
        if has_reply:
            return "del_this", {}
        return "del_dups", {"period": "", "last_n": 0}
    if is_dups and is_check:
        return "check_dups", {"period": "", "last_n": last_n}
    if is_stats_request(text):
        who = "me" if re.search(r"(?<![а-яё])(мной|мои|меня|я |у меня|мой)", low) else "all"
        return "stats", {"period": text, "who": who}
    if any(w in low for w in ("найд", "кто ", "у кого", "сравни", "проанализ", "анализ", "странн", "лучш",
                              "худш", "уникальн", "номер", "есть ли", "разбер", "посмотр")):
        return "analyst", {}
    return "chat", {}


def handle_trigger(chat_id, msg):
    text = msg.get("text") or msg.get("caption") or ""
    mid = msg.get("message_id")
    frm = msg.get("from") or {}
    rep_mid = (msg.get("reply_to_message") or {}).get("message_id")
    action, args = route_intent(chat_id, text, bool(rep_mid))

    if action == "del_this" and rep_mid:
        do_delete_this(chat_id, rep_mid, mid)
        return
    if action == "check_dups":
        do_check_dups(chat_id, args.get("period", ""), args.get("last_n") or 0, mid)
        return
    if action == "del_dups":
        do_delete_dups(chat_id, args.get("period", ""), args.get("last_n") or 0, mid)
        return
    if action == "del_last":
        do_delete_last(chat_id, args.get("n", 1), args.get("who", "all"), frm, mid)
        return
    if action == "stats":
        # статистику-сводку отдаём ТОЧНЫМ кодом (цифры и формат всегда верные)
        send(chat_id, stats_answer(chat_id, args.get("period", "сегодня"), args.get("who", "all"), frm), reply_to=mid)
        return
    if action == "analyst":
        # любой разбор по данным — ИИ сам, видя последние QR и точные сводки
        send(chat_id, analyst_reply(chat_id, text, frm), reply_to=mid)
        return
    # просто поболтать — характерно, без тяжёлого контекста
    send(chat_id, persona_reply(chat_id, text), reply_to=mid)


# ---------------------------------------------------------------- приём обновлений
def _reaction_emojis(react_list):
    out = []
    for r in react_list or []:
        if isinstance(r, dict) and r.get("type") == "emoji" and r.get("emoji"):
            out.append(r["emoji"])
    return out


def handle_update(upd):
    # обычное сообщение
    msg = upd.get("message")
    if msg:
        chat = msg.get("chat") or {}
        chat_id = chat.get("id")
        if (msg.get("from") or {}).get("is_bot"):
            return
        if msg.get("photo"):   # DEBUG_QR_1591: видно ли фото и читается ли номер из подписи
            cap = msg.get("caption") or ""
            print("[QR?] фото от %s | подпись=%r | номер=%s" % (
                ((msg.get("from") or {}).get("username") or (msg.get("from") or {}).get("first_name")),
                cap[:60], extract_number(cap) or "—НЕ НАЙДЕН"), flush=True)
        num = record_qr(chat_id, msg)         # молча считаем QR
        if msg.get("photo"):
            print("[QR?] записан как QR: %s" % (num or "НЕТ (нет номера в подписи)"), flush=True)
        if is_triggered(chat_id, msg):
            try:
                handle_trigger(chat_id, msg)
            except Exception as exc:
                print("[BOT] handle_trigger: %s" % exc, flush=True)
        return

    # реакция одного пользователя
    mr = upd.get("message_reaction")
    if mr:
        chat_id = (mr.get("chat") or {}).get("id")
        uid = (mr.get("user") or {}).get("id") or (mr.get("actor_chat") or {}).get("id") or 0
        set_reaction(chat_id, mr.get("message_id"), uid, _reaction_emojis(mr.get("new_reaction")))
        return

    # агрегированные (анонимные) реакции
    mrc = upd.get("message_reaction_count")
    if mrc:
        chat_id = (mrc.get("chat") or {}).get("id")
        emojis = []
        for rc in mrc.get("reactions") or []:
            t = rc.get("type") or {}
            if t.get("type") == "emoji" and rc.get("total_count", 0) > 0:
                emojis.append(t.get("emoji"))
        set_reaction_count(chat_id, mrc.get("message_id"), emojis)
        return

    # нажатие кнопки подтверждения удаления
    cb = upd.get("callback_query")
    if cb:
        data = cb.get("data") or ""
        chat_id = ((cb.get("message") or {}).get("chat") or {}).get("id")
        if data == "del_yes":
            answer_cb(cb["id"], "Сношу…")
            send(chat_id, do_pending_delete(chat_id))
        elif data == "del_no":
            PENDING.pop(chat_id, None)
            answer_cb(cb["id"], "Отменил")
            send(chat_id, "Ну и ладно, живите.")
        return


def main():
    global BOT_USERNAME
    me = tg("getMe")
    if not me.get("ok"):
        print("не удалось getMe (токен/прокси?): %s" % me, file=sys.stderr)
        sys.exit(1)
    BOT_USERNAME = me["result"].get("username") or ""
    print("[BOT] запущен как @%s. Триггеры: %s" % (BOT_USERNAME, ", ".join(TRIGGERS)), flush=True)
    offset = 0
    allowed = ["message", "edited_message", "callback_query", "message_reaction", "message_reaction_count"]
    while True:
        r = tg("getUpdates", {"offset": offset, "timeout": 25, "allowed_updates": json.dumps(allowed)}, timeout=40)
        if not r.get("ok"):
            time.sleep(3)
            continue
        for upd in r.get("result", []):
            offset = max(offset, upd["update_id"] + 1)
            try:
                handle_update(upd)
            except Exception as exc:
                print("[BOT] update error: %s" % exc, flush=True)


if __name__ == "__main__":
    main()

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
def _window_since(text):
    low = text.lower()
    now = time.time()
    if "час" in low:
        return now - 3600, "за последний час"
    if "сегодня" in low or "за день" in low or "за сутки" in low:
        midnight = datetime.datetime.now(TZ).replace(hour=0, minute=0, second=0, microsecond=0)
        return midnight.timestamp(), "за сегодня"
    if "недел" in low:
        return now - 7 * 86400, "за неделю"
    if "всё" in low or "все" in low or "всего" in low:
        return 0, "за всё время"
    # по умолчанию — сегодня
    midnight = datetime.datetime.now(TZ).replace(hour=0, minute=0, second=0, microsecond=0)
    return midnight.timestamp(), "за сегодня"


def compute_stats(chat_id, since):
    con = db()
    qrs = con.execute("SELECT msg_id,user,number FROM qr WHERE chat_id=? AND ts>=?", (chat_id, since)).fetchall()
    per_user = collections.defaultdict(lambda: collections.Counter())
    total = collections.Counter()
    for msg_id, user, number in qrs:
        kinds = _msg_reactions(con, chat_id, msg_id)
        st = qr_status(kinds)
        per_user[user]["всего"] += 1
        per_user[user][st] += 1
        total["всего"] += 1
        total[st] += 1
    con.close()
    return total, per_user


def stats_text(chat_id, text):
    since, label = _window_since(text)
    total, per_user = compute_stats(chat_id, since)
    lines = ["Статистика %s:" % label,
             "Всего QR: %d | 🔥 успех: %d | 👎 неуспех: %d | ❤ в работе: %d | без реакции: %d" %
             (total["всего"], total["success"], total["fail"], total["inwork"], total["none"])]
    for user, c in sorted(per_user.items(), key=lambda x: -x[1]["всего"]):
        lines.append("  %s: %d (🔥%d 👎%d ❤%d —%d)" % (user, c["всего"], c["success"], c["fail"], c["inwork"], c["none"]))
    return "\n".join(lines), total


# ---------------------------------------------------------------- дубли
def find_duplicates(chat_id, since=0):
    """Номера, встреченные в >1 QR. Возвращает [(number, keep_msg_id, [dup_msg_ids...])]."""
    con = db()
    rows = con.execute("SELECT number,msg_id,ts FROM qr WHERE chat_id=? AND ts>=? ORDER BY ts ASC", (chat_id, since)).fetchall()
    con.close()
    by_num = collections.OrderedDict()
    for number, msg_id, ts in rows:
        by_num.setdefault(number, []).append(msg_id)
    dups = []
    for number, ids in by_num.items():
        if len(ids) > 1:
            dups.append((number, ids[0], ids[1:]))
    return dups


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
    return any(w in low for w in ("удали", "удалить", "снеси", "убери", "почисти", "чисти"))


def is_stats_request(text):
    low = text.lower()
    return any(w in low for w in ("скольк", "статист", "залит", "за день", "за час", "за сегодня",
                                  "итог", "процент", "успех", "сколько", "наработал", "сводк"))


def kb_yes_no():
    return {"inline_keyboard": [[{"text": "✅ Да", "callback_data": "del_yes"},
                                 {"text": "✖️ Нет", "callback_data": "del_no"}]]}


def handle_delete(chat_id, msg):
    text = msg.get("text") or msg.get("caption") or ""
    low = text.lower()
    mid = msg.get("message_id")
    rep = msg.get("reply_to_message") or {}
    wants_dups = "дубл" in low or "повтор" in low
    # 1) reply на сообщение и это НЕ про дубли → удалить именно это сообщение
    if rep.get("message_id") and not wants_dups:
        PENDING[chat_id] = {"ids": [rep["message_id"]], "numbers": [], "ts": time.time()}
        send(chat_id, random.choice([
            "Эт сообщение в расход? Уверен?",
            "Снести вот это нахрен? Подтверди.",
        ]), reply_to=mid, markup=kb_yes_no())
        return
    # 2) удалить дубли (по умолчанию за сегодня; «всё/вообще» — за всё время)
    since = 0 if any(w in low for w in ("всё", "все ", "всего", "вообще", "за всё")) else _today_since()
    dups = find_duplicates(chat_id, since)
    if not dups:
        send(chat_id, random.choice([
            "Дублей нет, чисто. Расслабься.",
            "Нечего удалять — повторов не нашёл.",
        ]), reply_to=mid)
        return
    ids, nums = [], []
    for number, keep, extra in dups:
        ids += extra
        nums.append(pretty_number(number) + " ×%d" % (len(extra) + 1))
    PENDING[chat_id] = {"ids": ids, "numbers": nums, "ts": time.time()}
    listing = "\n".join("• " + n for n in nums[:40])
    send(chat_id, "Щас грохнем эту хуйню — уверен?\nВот чё собрал (%d дублей):\n%s" % (len(ids), listing),
         reply_to=mid, markup=kb_yes_no())


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


def handle_trigger(chat_id, msg):
    text = msg.get("text") or msg.get("caption") or ""
    mid = msg.get("message_id")
    if is_delete_request(text):
        handle_delete(chat_id, msg)
        return
    if is_stats_request(text):
        table, total = stats_text(chat_id, text)
        # даём цифры DeepSeek, чтобы ответил своими словами, с характером
        ctx = "Вот точная статистика (не выдумывай цифры, бери эти):\n" + table
        out = persona_reply(chat_id, text, extra_context=ctx)
        send(chat_id, out, reply_to=mid)
        return
    # свободный диалог
    out = persona_reply(chat_id, text)
    send(chat_id, out, reply_to=mid)


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
        record_qr(chat_id, msg)               # молча считаем QR
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

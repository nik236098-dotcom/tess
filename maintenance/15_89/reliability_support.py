"""Request/delivery reliability only. Does not replace site-action handlers."""
from __future__ import annotations
import copy
import hashlib
import json
from pathlib import Path
import re
import threading
import time

VERSION = '15.89'
GENERIC_TASK = 'Выполни задачу пользователя. Используй инструменты проекта.'


def canonical_messages(messages, fresh_system, request=None):
    """Checkpoint history cannot replace current configuration or nest system text."""
    if not isinstance(fresh_system, str) or not fresh_system.strip():
        raise ValueError('Empty current system instructions')
    history = [copy.deepcopy(m) for m in messages
               if isinstance(m, dict) and m.get('role') not in {'system', 'developer'}]
    if request is not None:
        first = next((m for m in history if m.get('role') == 'user'), None)
        if first is None:
            history.insert(0, {'role': 'user', 'content': str(request)})
        elif first.get('content') == GENERIC_TASK:
            first['content'] = str(request)
        elif isinstance(first.get('content'), list):
            for part in first['content']:
                if isinstance(part, dict) and part.get('type') == 'text' and part.get('text') == GENERIC_TASK:
                    part['text'] = str(request)
    return [{'role': 'system', 'content': fresh_system}] + history


def fingerprint(payload, route):
    systems = [m for m in payload.get('messages', []) if m.get('role') == 'system']
    actual = '\n'.join(str(m.get('content', '')) for m in systems)
    data = {'route': route, 'system_count': len(systems), 'system_chars': len(actual),
            'sha256': hashlib.sha256(actual.encode()).hexdigest()}
    print('[AI REQUEST 15.89] ' + json.dumps(data), flush=True)
    return data


def role_question(text):
    low = str(text).lower().replace('ё', 'е')
    return any(x in low for x in ('какая у тебя задач', 'твоя главная задач',
                                  'твоя задач', 'твоих обязанност', 'твоя цель', 'какая твоя роль'))


def fresh_system(ns, status_map, pages, user_text, include_runtime=True):
    # Keep the user's installed instruction; do not invent another mission.
    current = ns['_agent_system_prompt'](status_map, pages, user_text)
    if not include_runtime or role_question(user_text):
        current = current.split('\nПОСЛЕДНИЕ СТРОКИ PYTHON-КОНСОЛИ:', 1)[0]
    priority = next((ns.get(k) for k in ('OPERATOR_MISSION_1586', 'OPERATOR_MISSION_1585',
                      'OPERATOR_API_MISSION_V1584') if ns.get(k)), '')
    return str(priority) + '\n\n' + current if priority else current


def chat_context(ns, status_map, pages, user_text):
    data = {'message': user_text}
    if not role_question(user_text):
        data.update(statuses=dict(status_map), pages=pages)
    # No old assistant role claims or chat history masquerading as instructions.
    return json.dumps(data, ensure_ascii=False, default=str)


def is_guarded(worker):
    return bool(worker.get('success_guard') or worker.get('error_guard') or
                worker.get('phase') in {'POST_AUTH_REVIEW', 'SIGN_WAIT', 'SUCCESS_ASSIST',
                                        'ERROR_ASSIST', 'SUCCESS_STOP'})


def merge_profile(existing, supplementary):
    result = dict(existing or {})
    aliases = {'passport_issuer': 'passport_issued_by', 'city': 'locality'}
    for key, value in dict(supplementary or {}).items():
        key = aliases.get(key, key)
        if value is not None and str(value).strip() and not result.get(key):
            result[key] = value
    for old, new in aliases.items():
        if result.get(old) and not result.get(new):
            result[new] = result[old]
        result.pop(old, None)
    return result


def split_message(text, limit=3500):
    """Conservative UTF-16 bound; concatenate chunks to recover exact original text."""
    if not isinstance(text, str) or not text.strip():
        raise ValueError('Empty Telegram response')
    if limit < 2:
        raise ValueError('limit must be at least 2')
    result, part, units = [], [], 0
    for ch in text:
        cost = 2 if ord(ch) > 0xFFFF else 1
        if units + cost > limit:
            result.append(''.join(part)); part, units = [], 0
        part.append(ch); units += cost
    if part:
        result.append(''.join(part))
    return result


def redact_error(value):
    text = re.sub(r'bot\d+:[A-Za-z0-9_-]+', 'bot<redacted>', str(value))
    return re.sub(r'(socks5h?://)[^/@\s]+@', r'\1<redacted>@', text)[:1200]


def deliver_part(ns, out, cfg, markup=None):
    """At-least-once delivery; persist one part ACK before attempting the next."""
    import fcntl
    db = Path(ns['AI_TELEGRAM_DB'])
    with db.with_suffix('.delivery.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return 'busy'
        try:
            with ns['_ai_db_connect']() as conn:
                conn.execute('''CREATE TABLE IF NOT EXISTS delivery_parts_1589 (
                    update_id INTEGER NOT NULL, body_hash TEXT NOT NULL,
                    part INTEGER NOT NULL, total INTEGER NOT NULL,
                    message_id INTEGER NOT NULL, ack_at REAL NOT NULL,
                    PRIMARY KEY(update_id, body_hash, part))''')
                live = conn.execute('SELECT body, chat_id, sent_at FROM outbox WHERE update_id=?',
                                    (int(out['update_id']),)).fetchone()
                if not live or live[2] is not None:
                    return 'already_sent'
                body, chat = str(live[0]), str(live[1])
                digest = hashlib.sha256(body.encode()).hexdigest()
                chunks = split_message(body)
                acked = {r[0] for r in conn.execute(
                    'SELECT part FROM delivery_parts_1589 WHERE update_id=? AND body_hash=?',
                    (int(out['update_id']), digest))}
            remaining = [i for i in range(len(chunks)) if i not in acked]
            if not remaining:
                ns['_ai_db_outbox_sent'](out['update_id']); return 'delivered'
            index = remaining[0]
            text = chunks[index]
            if len(chunks) > 1:
                text = f'[{index+1}/{len(chunks)}]\n' + text
            payload = {'chat_id': chat, 'text': text, 'disable_web_page_preview': 'true'}
            if markup is not None:
                payload['reply_markup'] = markup
            obj, err = ns['telegram_api'](cfg, 'sendMessage', payload)
            result = obj.get('result') if isinstance(obj, dict) else None
            mid = result.get('message_id') if isinstance(result, dict) else None
            if err or not isinstance(obj, dict) or obj.get('ok') is not True or type(mid) is not int or mid <= 0:
                reason = redact_error(err or 'Telegram did not acknowledge message_id')
                ns['_ai_db_outbox_fail'](out['update_id'], reason, out.get('attempts', 0))
                if isinstance(obj, dict):
                    wait = (obj.get('parameters') or {}).get('retry_after')
                    if isinstance(wait, (int, float)) and wait > 0:
                        with ns['_ai_db_connect']() as conn:
                            conn.execute('UPDATE outbox SET next_attempt_at=MAX(next_attempt_at,?) WHERE update_id=?',
                                         (time.time() + wait, out['update_id']))
                print(f"[TG RETRY 15.89] update={out['update_id']} part={index+1}/{len(chunks)} {reason}", flush=True)
                return 'retry'
            with ns['_ai_db_connect']() as conn:
                conn.execute('PRAGMA synchronous=FULL')
                conn.execute('INSERT OR IGNORE INTO delivery_parts_1589 VALUES(?,?,?,?,?,?)',
                             (int(out['update_id']), digest, index, len(chunks), mid, time.time()))
            print(f"[TG ACK 15.89] update={out['update_id']} part={index+1}/{len(chunks)} message_id={mid}", flush=True)
            if len(remaining) == 1:
                ns['_ai_db_outbox_sent'](out['update_id'])
                print(f"[TG DELIVERED 15.89] update={out['update_id']}", flush=True)
                return 'delivered'
            return 'pending'
        except Exception as exc:
            try:
                ns['_ai_db_outbox_fail'](out['update_id'], redact_error(exc), out.get('attempts', 0))
            except Exception as db_exc:
                print('[OUTBOX STORAGE ERROR 15.89] ' + type(db_exc).__name__, flush=True)
            return 'retry'


_CHAT_THREADS = {}

def start_chat(ns):
    """Only controller starts this lane; no browser or extra getUpdates consumer."""
    key = str(ns.get('__file__'))
    old = _CHAT_THREADS.get(key)
    if old and old.is_alive():
        return
    def run():
        while True:
            try:
                ns['ai_observer_process']({}, [], threading.Event(), {}, None, None, 'chat')
            except Exception as exc:
                print('[CHAT RESTART 15.89] ' + redact_error(exc), flush=True)
            time.sleep(3)
    thread = threading.Thread(target=run, name='independent-operator-chat', daemon=True)
    _CHAT_THREADS[key] = thread
    thread.start()

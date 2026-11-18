"""Integrated request and message I/O support. No form-filling/signature logic.

Python 3.10+. Imported and called by both application files in this package.
"""
from __future__ import annotations

from contextlib import contextmanager
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import threading
import time
import uuid

VERSION = '15.91-io'
GENERIC_TASK = 'Выполни задачу пользователя. Используй инструменты проекта.'
GUARDED_PHASES = frozenset({'POST_AUTH_REVIEW', 'SIGN_WAIT', 'SUCCESS_ASSIST',
                           'ERROR_ASSIST', 'SUCCESS_STOP'})
_THREADS: dict[str, threading.Thread] = {}
_THREAD_LOCK = threading.Lock()


def canonical_messages(messages, current_system, request=None):
    """Rebuild the system from current configuration, never from a checkpoint."""
    if not isinstance(current_system, str) or not current_system.strip():
        raise ValueError('Current system instructions are empty')
    if not isinstance(messages, list):
        raise TypeError('messages must be a list')
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
    return [{'role': 'system', 'content': current_system}] + history


def request_audit(payload, route):
    systems = [m for m in payload.get('messages', [])
               if isinstance(m, dict) and m.get('role') == 'system']
    text = '\n'.join(str(m.get('content', '')) for m in systems)
    result = {'route': str(route), 'system_count': len(systems),
              'system_chars': len(text), 'system_sha256': hashlib.sha256(text.encode()).hexdigest()}
    print('[AI REQUEST 15.91] ' + json.dumps(result), flush=True)
    return result


def role_question(text):
    return bool(re.search(r'(?:какая|какова|в\s+ч[её]м|твоя|твои|у\s+тебя).{0,55}'
                          r'(?:задач|цел[ьиь]|роль|обязан)', str(text), re.I))


def build_system(ns, status_map, pages, user_text):
    """Use the installed instructions, without inventing a different agent role."""
    current = str(ns['_agent_system_prompt'](status_map, pages, user_text))
    if role_question(user_text):
        current = current.split('\nПОСЛЕДНИЕ СТРОКИ PYTHON-КОНСОЛИ:', 1)[0]
    priority = next((ns.get(k) for k in (
        'OPERATOR_MISSION_1586', 'OPERATOR_MISSION_1585', 'OPERATOR_API_MISSION_V1584')
        if isinstance(ns.get(k), str) and ns.get(k).strip()), '')
    return str(priority) + '\n\n' + current if priority else current


def chat_context(ns, status_map, pages, user_text):
    data = {'message': str(user_text)}
    if not role_question(user_text):
        data['statuses'] = dict(status_map)
        data['pages'] = [{k: p.get(k) for k in ('tab_id', 'tab', 'browser', 'url', 'title', 'error')}
                         for p in pages]
        data['recent_dialogue_as_history'] = ns['_chat_memory_tail']()
    return json.dumps(data, ensure_ascii=False, default=str)


def guarded(state):
    return bool(state.get('success_guard') or state.get('error_guard')
                or state.get('phase') in GUARDED_PHASES)


def missing(value):
    return value is None or (isinstance(value, str) and not value.strip())


def merge_capture(existing, supplementary):
    """Merge values already present in memory. No scraping or synthetic values."""
    aliases = {'passport_issuer': 'passport_issued_by', 'city': 'locality'}
    result = dict(existing or {})
    for source in (existing or {}, supplementary or {}):
        for k, value in source.items():
            target = aliases.get(k, k)
            if not missing(value) and (target not in result or missing(result[target])):
                result[target] = value
    for old in aliases:
        result.pop(old, None)
    return result


def split_text(text, limit=3500):
    if not isinstance(text, str) or not text.strip():
        raise ValueError('Empty Telegram message')
    if limit < 2:
        raise ValueError('limit must be >= 2')
    parts, buffer, size = [], [], 0
    for char in text:
        width = 2 if ord(char) > 0xFFFF else 1
        if size + width > limit:
            parts.append(''.join(buffer)); buffer, size = [], 0
        buffer.append(char); size += width
    if buffer:
        parts.append(''.join(buffer))
    return parts


def redact(value):
    text = str(value)
    text = re.sub(r'(?i)(?:bot)?\d{5,16}:[A-Za-z0-9_-]{15,}', '<bot-token>', text)
    text = re.sub(r'(socks5h?://)[^/@\s]+@', r'\1<credentials>@', text)
    text = re.sub(r'\bsk-[A-Za-z0-9_-]{12,}', '<api-key>', text)
    return text[:1500]


class TelegramFailure(str):
    def __new__(cls, text, code=None, retry_after=None):
        obj = super().__new__(cls, redact(text))
        obj.code = code
        obj.retry_after = retry_after
        return obj


@contextmanager
def db(ns):
    conn = ns['_ai_db_connect']()
    try:
        conn.execute('PRAGMA synchronous=FULL')
        yield conn
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_delivery(ns):
    with db(ns) as conn:
        conn.executescript('''
            CREATE TABLE IF NOT EXISTS io1591_parts (
                update_id INTEGER NOT NULL, body_hash TEXT NOT NULL,
                part_no INTEGER NOT NULL, message_id INTEGER NOT NULL,
                ack_at REAL NOT NULL, PRIMARY KEY(update_id,body_hash,part_no));
            CREATE TABLE IF NOT EXISTS io1591_options (
                update_id INTEGER PRIMARY KEY, reply_markup TEXT);
            CREATE TABLE IF NOT EXISTS io1591_rate (
                chat_id TEXT PRIMARY KEY, next_at REAL NOT NULL);
        ''')


def enqueue_notice(ns, chat, text, markup=None):
    if not str(chat).strip() or not str(text).strip():
        raise ValueError('Notice requires chat and text')
    init_delivery(ns)
    with db(ns) as conn:
        conn.execute('BEGIN IMMEDIATE')
        # Separate range from positive Telegram IDs and time.time_ns based internal jobs.
        for _ in range(8):
            update_id = -(2**62 + (uuid.uuid4().int % (2**62-1)))
            exists = conn.execute('SELECT 1 FROM outbox WHERE update_id=?', (update_id,)).fetchone()
            if not exists:
                break
        else:
            raise RuntimeError('Could not allocate a notification identifier')
        conn.execute('INSERT INTO outbox(update_id,chat_id,body,created_at,next_attempt_at) VALUES(?,?,?,?,0)',
                     (update_id, str(chat), str(text), time.time()))
        conn.execute('INSERT INTO io1591_options VALUES(?,?)', (update_id, markup))
    return update_id


def send_part(ns, item, cfg, default_markup=None):
    """At-least-once delivery. A lost network ACK can still produce a duplicate."""
    import fcntl
    path = Path(ns['AI_TELEGRAM_DB'])
    with path.with_suffix('.io1591.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return 'busy'
        update_id = int(item['update_id'])
        try:
            init_delivery(ns)
            now = time.time()
            with db(ns) as conn:
                live = conn.execute('SELECT body,chat_id,sent_at,next_attempt_at,attempts FROM outbox WHERE update_id=?',
                                    (update_id,)).fetchone()
                if live is None or live[2] is not None:
                    return 'already_sent'
                if live[3] > now:
                    return 'waiting'
                text, chat, attempts = str(live[0]), str(live[1]), int(live[4] or 0)
                chunks = split_text(text)
                digest = hashlib.sha256((chat + '\0' + text).encode()).hexdigest()
                done = {r[0] for r in conn.execute('SELECT part_no FROM io1591_parts WHERE update_id=? AND body_hash=?',
                                                 (update_id, digest))}
                pending = next((i for i in range(len(chunks)) if i not in done), None)
                if pending is None:
                    conn.execute('UPDATE outbox SET sent_at=?,last_error=NULL WHERE update_id=? AND sent_at IS NULL',
                                 (now, update_id))
                    return 'delivered'
                rate = conn.execute('SELECT next_at FROM io1591_rate WHERE chat_id=?', (chat,)).fetchone()
                if rate and rate[0] > now:
                    return 'waiting'
                options = conn.execute('SELECT reply_markup FROM io1591_options WHERE update_id=?',
                                       (update_id,)).fetchone()
                markup = options[0] if options else default_markup
            piece = chunks[pending]
            if len(chunks) > 1:
                piece = f'[{pending+1}/{len(chunks)}]\n' + piece
            payload = {'chat_id': chat, 'text': piece, 'disable_web_page_preview': 'true'}
            if markup:
                payload['reply_markup'] = markup
            result, error = ns['telegram_api'](cfg, 'sendMessage', payload)
            data = result.get('result') if isinstance(result, dict) else None
            message_id = data.get('message_id') if isinstance(data, dict) else None
            if error or not isinstance(result, dict) or result.get('ok') is not True or type(message_id) is not int or message_id <= 0:
                delay = min(120, max(3, (attempts + 1) * 3))
                retry_after = getattr(error, 'retry_after', None)
                if isinstance(retry_after, (int, float)) and 0 < retry_after < 86400:
                    delay = max(delay, retry_after)
                code = getattr(error, 'code', None)
                if code in {400, 401, 403}:
                    delay = max(delay, 300)
                with db(ns) as conn:
                    conn.execute('UPDATE outbox SET attempts=attempts+1,last_error=?,next_attempt_at=? WHERE update_id=? AND sent_at IS NULL',
                                 (redact(error or 'Telegram did not confirm message_id'), time.time()+delay, update_id))
                print(f'[TG RETRY 15.91] update={update_id} part={pending+1}/{len(chunks)} delay={delay}', flush=True)
                return 'retry'
            with db(ns) as conn:
                conn.execute('BEGIN IMMEDIATE')
                current = conn.execute('SELECT body,chat_id FROM outbox WHERE update_id=?', (update_id,)).fetchone()
                if not current or current[0] != text or str(current[1]) != chat:
                    raise RuntimeError('Outbox content changed during delivery')
                conn.execute('INSERT OR IGNORE INTO io1591_parts VALUES(?,?,?,?,?)',
                             (update_id, digest, pending, message_id, time.time()))
                conn.execute('INSERT INTO io1591_rate VALUES(?,?) ON CONFLICT(chat_id) DO UPDATE SET next_at=excluded.next_at',
                             (chat, time.time()+1.1))
                if len(done) + 1 == len(chunks):
                    conn.execute('UPDATE outbox SET sent_at=?,last_error=NULL WHERE update_id=? AND sent_at IS NULL',
                                 (time.time(), update_id))
            print(f'[TG ACK 15.91] update={update_id} part={pending+1}/{len(chunks)} message_id={message_id}', flush=True)
            return 'delivered' if len(done)+1 == len(chunks) else 'pending'
        except Exception as exc:
            try:
                ns['_ai_db_outbox_fail'](update_id, redact(exc), item.get('attempts', 0))
            except Exception as store_error:
                print('[OUTBOX STORAGE ERROR 15.91] ' + type(store_error).__name__, flush=True)
            return 'retry'


def start_sender(ns, cfg, markup=None, stop_event=None):
    key = str(ns.get('__file__')) + ':sender'
    stop_event = stop_event or threading.Event()
    def run():
        while not stop_event.is_set():
            try:
                item = ns['_ai_db_next_outbox']()
                if item:
                    send_part(ns, item, cfg, markup)
            except Exception as exc:
                print('[TX LOOP 15.91] ' + redact(exc), flush=True)
            stop_event.wait(0.25)
    with _THREAD_LOCK:
        old = _THREADS.get(key)
        if old is not None and old.is_alive():
            return old
        thread = threading.Thread(target=run, name='telegram-outbox-1591', daemon=True)
        _THREADS[key] = thread
        thread.start()
        return thread


def start_chat(ns):
    key = str(ns.get('__file__')) + ':chat'
    def run():
        while True:
            try:
                ns['ai_observer_process']({}, [], threading.Event(), {}, None, None, 'chat')
            except Exception as exc:
                print('[CHAT RESTART 15.91] ' + redact(exc), flush=True)
            time.sleep(3)
    with _THREAD_LOCK:
        old = _THREADS.get(key)
        if old is not None and old.is_alive():
            return old
        thread = threading.Thread(target=run, name='operator-chat-1591', daemon=True)
        _THREADS[key] = thread
        thread.start()
        return thread

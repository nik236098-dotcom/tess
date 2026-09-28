"""Standalone reliability primitives. No site automation or production installer.

Python 3.10+, standard library only. Network access is injected by the caller.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import copy
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import time
from typing import Any, Callable, Iterable
import uuid

VERSION = "1.0.0-review"


def canonical_messages(history: list[dict], current_system: str) -> list[dict]:
    """Keep history, but never reuse/nest checkpoint system or developer messages."""
    if not isinstance(current_system, str) or not current_system.strip():
        raise ValueError("current_system is required")
    if not isinstance(history, list):
        raise TypeError("history must be a list")
    body = []
    for message in history:
        if not isinstance(message, dict) or message.get("role") not in {
            "system", "developer", "user", "assistant", "tool"
        }:
            raise ValueError("unsupported message")
        if message["role"] not in {"system", "developer"}:
            body.append(copy.deepcopy(message))
    return [{"role": "system", "content": current_system}] + body


def request_payload(model: str, history: list[dict], current_system: str,
                    *, tools: list[dict] | None = None) -> dict:
    if not isinstance(model, str) or not model.strip():
        raise ValueError("model is required")
    result = {"model": model, "messages": canonical_messages(history, current_system)}
    if tools is not None:
        result["tools"] = copy.deepcopy(tools)
    return result


def fingerprint(payload: dict) -> dict:
    """Audit actual outgoing system content without logging it or credentials."""
    systems = [m for m in payload["messages"] if m.get("role") == "system"]
    content = json.dumps([m.get("content") for m in systems], ensure_ascii=False)
    return {"system_count": len(systems), "system_chars": len(content),
            "system_sha256": hashlib.sha256(content.encode()).hexdigest()}


def merge_capture(existing: dict, supplementary: dict, aliases: dict[str, str] | None = None) -> dict:
    """Merge already provided values using an explicit schema; never infer values."""
    aliases = aliases or {}
    result = copy.deepcopy(existing)
    missing = lambda v: v is None or (isinstance(v, str) and not v.strip())
    for key, value in supplementary.items():
        key = aliases.get(key, key)
        if not missing(value) and missing(result.get(key)):
            result[key] = copy.deepcopy(value)
    return result


DESTRUCTIVE_ACTIONS = frozenset({"close", "reload", "restart", "navigate", "back", "forward"})


def assert_lifecycle_allowed(action: str, guarded: bool) -> None:
    if not isinstance(action, str) or not action.strip():
        raise ValueError("action required")
    if guarded and action.lower() in DESTRUCTIVE_ACTIONS:
        raise PermissionError("guarded state must not be destroyed")


@dataclass(frozen=True)
class CompletionEvidence:
    """Build only in a trusted backend adapter, not from a model's answer."""
    operation_id: str
    receipt_id: str
    trusted_backend: bool


def completion_state(expected_operation: str, *, has_error: bool = False,
                     evidence: CompletionEvidence | None = None) -> str:
    if has_error:
        return "ERROR"
    if (expected_operation and evidence and evidence.trusted_backend is True
            and evidence.operation_id == expected_operation and evidence.receipt_id):
        return "CONFIRMED"
    return "UNCERTAIN"


def session_tail(path: Path, session_id: str, max_bytes: int = 262144) -> str:
    """Return only an explicitly selected session; don't substitute older history."""
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", session_id):
        raise ValueError("invalid session_id")
    if not 1 <= max_bytes <= 4 * 1024 * 1024:
        raise ValueError("invalid read bound")
    marker = f"=== SESSION {session_id} ==="
    try:
        with Path(path).open("rb") as f:
            size = f.seek(0, os.SEEK_END)
            f.seek(max(0, size - max_bytes))
            lines = f.read().decode("utf-8", errors="replace").splitlines()
    except FileNotFoundError:
        return "CURRENT_SESSION_UNAVAILABLE"
    positions = [i for i, line in enumerate(lines) if line == marker]
    if not positions:
        return "CURRENT_SESSION_UNAVAILABLE"
    start = positions[-1] + 1
    end = next((i for i in range(start, len(lines)) if lines[i].startswith("=== SESSION ")), len(lines))
    return "\n".join(lines[start:end])


def split_text(text: str, limit: int = 3500) -> list[str]:
    """Conservative UTF-16 sizing. Concatenation recovers every original character."""
    if not isinstance(text, str) or not text.strip():
        raise ValueError("empty message")
    if not 2 <= limit <= 4000:
        raise ValueError("limit must be in [2, 4000]")
    # Reject lone surrogates before creating an undeliverable persistent message.
    text.encode("utf-8")
    parts, chars, used = [], [], 0
    for char in text:
        units = 2 if ord(char) > 0xFFFF else 1
        if used + units > limit:
            parts.append("".join(chars)); chars, used = [], 0
        chars.append(char); used += units
    if chars:
        parts.append("".join(chars))
    return parts


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


@dataclass(frozen=True)
class Part:
    message_key: str
    part_no: int
    chat_id: str
    text: str
    token: str
    attempts: int


class StaleLease(RuntimeError):
    pass


class Queue:
    """Own SQLite DB, never an application's existing database.

    Acknowledgements make delivery at-least-once, not exactly-once: an HTTP ACK
    lost after acceptance can result in a duplicate. Payloads are plaintext on disk.
    """
    def __init__(self, path: Path, *, clock: Callable[[], float] = time.time):
        self.path = Path(path)
        self.clock = clock
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Restrict permissions from initial creation; never truncate an existing DB.
        fd = os.open(self.path, os.O_CREAT | os.O_APPEND | os.O_WRONLY, 0o600)
        os.close(fd)
        with self.db() as c:
            app_id = c.execute("PRAGMA application_id").fetchone()[0]
            tables = c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            if app_id not in (0, 1381124913) or (app_id == 0 and tables):
                raise ValueError("refusing to modify an unrelated database")
            c.execute("PRAGMA application_id=1381124913")
            c.executescript("""
                CREATE TABLE IF NOT EXISTS meta(k TEXT PRIMARY KEY, v INTEGER NOT NULL);
                INSERT OR IGNORE INTO meta VALUES('offset',0);
                CREATE TABLE IF NOT EXISTS inbound(id INTEGER PRIMARY KEY, body TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS messages(
                    k TEXT PRIMARY KEY, chat TEXT NOT NULL, body TEXT NOT NULL,
                    digest TEXT NOT NULL, created REAL NOT NULL, delivered REAL);
                CREATE TABLE IF NOT EXISTS parts(
                    k TEXT NOT NULL REFERENCES messages(k), n INTEGER NOT NULL,
                    text TEXT NOT NULL, mid INTEGER, attempts INTEGER NOT NULL DEFAULT 0,
                    due REAL NOT NULL DEFAULT 0, token TEXT, lease_until REAL NOT NULL DEFAULT 0,
                    last_error TEXT, blocked INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY(k,n));
            """)

    @contextmanager
    def db(self):
        c = sqlite3.connect(self.path, timeout=10)
        c.row_factory = sqlite3.Row
        try:
            c.execute("PRAGMA foreign_keys=ON")
            c.execute("PRAGMA busy_timeout=10000")
            c.execute("PRAGMA synchronous=FULL")
            yield c
            c.commit()
        except BaseException:
            c.rollback()
            raise
        finally:
            c.close()

    def offset(self) -> int:
        with self.db() as c:
            return int(c.execute("SELECT v FROM meta WHERE k='offset'").fetchone()[0])

    def ingest(self, updates: Iterable[dict]) -> int:
        """Persist the full fetched batch and next offset in the same transaction."""
        records = []
        for update in updates:
            if not isinstance(update, dict) or type(update.get("update_id")) is not int or update["update_id"] < 0:
                raise ValueError("invalid update")
            records.append((update["update_id"], canonical_json(update)))
        with self.db() as c:
            c.execute("BEGIN IMMEDIATE")
            offset = int(c.execute("SELECT v FROM meta WHERE k='offset'").fetchone()[0])
            for key, body in records:
                old = c.execute("SELECT body FROM inbound WHERE id=?", (key,)).fetchone()
                if old and old[0] != body:
                    raise ValueError("update_id reused with different content")
                c.execute("INSERT OR IGNORE INTO inbound VALUES(?,?)", (key, body))
                offset = max(offset, key + 1)
            c.execute("UPDATE meta SET v=? WHERE k='offset'", (offset,))
            return offset

    def enqueue(self, key: str, chat_id: str, text: str) -> None:
        if not key or not str(chat_id):
            raise ValueError("message key and chat_id required")
        chunks = split_text(text)
        chat = str(chat_id)
        digest = hashlib.sha256(canonical_json([chat, text]).encode()).hexdigest()
        with self.db() as c:
            c.execute("BEGIN IMMEDIATE")
            existing = c.execute("SELECT digest FROM messages WHERE k=?", (key,)).fetchone()
            if existing:
                if existing[0] != digest:
                    raise ValueError("message key reused with different content")
                return
            c.execute("INSERT INTO messages(k,chat,body,digest,created) VALUES(?,?,?,?,?)",
                      (key, chat, text, digest, self.clock()))
            c.executemany("INSERT INTO parts(k,n,text) VALUES(?,?,?)",
                          [(key, i, chunk) for i, chunk in enumerate(chunks)])

    def claim(self, lease_seconds: float = 120) -> Part | None:
        if not math.isfinite(lease_seconds) or lease_seconds <= 0:
            raise ValueError("positive lease required")
        now = self.clock()
        with self.db() as c:
            c.execute("BEGIN IMMEDIATE")
            row = c.execute("""SELECT p.*,m.chat FROM parts p JOIN messages m ON m.k=p.k
                WHERE m.delivered IS NULL AND p.mid IS NULL AND p.blocked=0
                AND p.due<=? AND p.lease_until<=?
                AND NOT EXISTS(SELECT 1 FROM parts prior WHERE prior.k=p.k AND prior.n<p.n AND prior.mid IS NULL)
                ORDER BY m.created,m.k,p.n LIMIT 1""", (now, now)).fetchone()
            if row is None:
                return None
            token = uuid.uuid4().hex
            c.execute("UPDATE parts SET token=?,lease_until=?,attempts=attempts+1 WHERE k=? AND n=?",
                      (token, now + lease_seconds, row["k"], row["n"]))
            return Part(row["k"], row["n"], row["chat"], row["text"], token, row["attempts"] + 1)

    def ack(self, part: Part, response: dict) -> None:
        result = response.get("result") if isinstance(response, dict) else None
        mid = result.get("message_id") if isinstance(result, dict) else None
        if not isinstance(response, dict) or response.get("ok") is not True or type(mid) is not int or mid <= 0:
            raise ValueError("Telegram did not acknowledge ok=true and message_id")
        with self.db() as c:
            c.execute("BEGIN IMMEDIATE")
            changed = c.execute("UPDATE parts SET mid=?,token=NULL,lease_until=0,last_error=NULL WHERE k=? AND n=? AND token=? AND mid IS NULL",
                                (mid, part.message_key, part.part_no, part.token))
            if changed.rowcount != 1:
                raise StaleLease("ack from an obsolete lease")
            count = c.execute("SELECT COUNT(*) FROM parts WHERE k=? AND mid IS NULL", (part.message_key,)).fetchone()[0]
            if count == 0:
                c.execute("UPDATE messages SET delivered=? WHERE k=?", (self.clock(), part.message_key))

    def fail(self, part: Part, error_code: str, *, retry_after: float | None = None, permanent: bool = False) -> None:
        # Do not persist raw exception text, tokens, URLs or API responses in errors.
        if not re.fullmatch(r"[A-Za-z0-9_:-]{1,80}", error_code):
            error_code = "UNSAFE_ERROR_TEXT_REDACTED"
        delay = (2, 5, 10, 20, 30)[min(max(part.attempts - 1, 0), 4)]
        if retry_after is not None:
            if not math.isfinite(retry_after) or retry_after < 0:
                raise ValueError("invalid retry_after")
            delay = max(delay, retry_after)
        with self.db() as c:
            changed = c.execute("UPDATE parts SET token=NULL,lease_until=0,due=?,last_error=?,blocked=? WHERE k=? AND n=? AND token=? AND mid IS NULL",
                                (self.clock() + delay, error_code, int(permanent), part.message_key, part.part_no, part.token))
            if changed.rowcount != 1:
                raise StaleLease("failure from an obsolete lease")

    def unblock(self, key: str) -> None:
        with self.db() as c:
            c.execute("UPDATE parts SET blocked=0,due=0 WHERE k=? AND mid IS NULL", (key,))

    def status(self, key: str) -> dict:
        with self.db() as c:
            message = c.execute("SELECT delivered FROM messages WHERE k=?", (key,)).fetchone()
            if message is None:
                raise KeyError(key)
            rows = c.execute("SELECT n,mid,attempts,due,blocked,last_error FROM parts WHERE k=? ORDER BY n", (key,)).fetchall()
            return {"delivered": message[0] is not None, "parts": [dict(x) for x in rows]}


def send_one(queue: Queue, api: Callable[[dict], dict]) -> str:
    """Call an injected sendMessage adapter once. No bundled network client."""
    part = queue.claim()
    if part is None:
        return "idle"
    try:
        response = api({"chat_id": part.chat_id, "text": part.text})
    except Exception as exc:
        queue.fail(part, type(exc).__name__)
        return "retry"
    if not isinstance(response, dict) or response.get("ok") is not True:
        code = response.get("error_code", 0) if isinstance(response, dict) else 0
        params = response.get("parameters") if isinstance(response, dict) else None
        wait = params.get("retry_after") if isinstance(params, dict) else None
        if type(wait) not in (int, float) or not math.isfinite(wait) or wait < 0:
            wait = None
        queue.fail(part, f"API_{code}" if type(code) is int else "API_INVALID",
                   retry_after=wait, permanent=code in (400, 401, 403))
        return "blocked" if code in (400, 401, 403) else "retry"
    try:
        queue.ack(part, response)
    except ValueError:
        queue.fail(part, "ACK_MISSING")
        return "retry"
    return "delivered_part"

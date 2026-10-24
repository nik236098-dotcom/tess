"""Adapters for the reviewed 15.83--15.86 sources; supervision is read-only."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import threading
import time
import uuid

from operator_reliability import (MISSION, POLICY_VERSION, Store, authoritative_context,
                                 canonical_messages, current_log_tail, payload_fingerprint,
                                 redact, role_question, state_from_observation, send_outbox_item)

_APP = None
_REPORTER_STARTED = False
_GUARD_PHASES = {"POST_AUTH_REVIEW", "SIGN_WAIT", "SUCCESS_ASSIST", "ERROR_ASSIST", "SUCCESS_STOP"}
_ASSIST_PHASES = {"SUCCESS_ASSIST", "ERROR_ASSIST"}
# Legacy collectors (15.83 capture) used their own field names; the record uses these.
PROFILE_ALIASES = {"passport_issuer": "passport_issued_by", "city": "locality"}


def _base():
    return Path(_APP["__file__"]).resolve().parent


def _store():
    return Store(_base() / "operator_observations.sqlite3")


def _pid_start(pid):
    try:
        # /proc field 22; process name may contain spaces, hence split after ')'.
        return Path(f"/proc/{int(pid)}/stat").read_text().rsplit(")", 1)[1].split()[19]
    except (OSError, IndexError, ValueError):
        return None


def _session():
    try:
        info = json.loads((_base() / "operator_runtime_session.json").read_text())
        start = _pid_start(info["pid"])
        if start is None or start != info["pid_start"]:
            return None
        return info
    except (OSError, ValueError, KeyError):
        return None


def _system():
    sess = _session()
    return authoritative_context(_store(), sess["id"] if sess else None)


def operator_messages(messages, system=None, request=None):
    clean = canonical_messages(messages, system or _system())
    if request is not None:
        # Legacy checkpoints stored the real user task only inside the discarded system prompt.
        first_user = next((m for m in clean if m.get("role") == "user"), None)
        generic = "Выполни задачу пользователя. Используй инструменты проекта."
        if first_user is None:
            clean.insert(1, {"role": "user", "content": str(request)})
        elif isinstance(first_user.get("content"), list):
            for part in first_user["content"]:
                if isinstance(part, dict) and part.get("type") == "text" and part.get("text") == generic:
                    part["text"] = str(request)
        elif first_user.get("content") == generic:
            first_user["content"] = str(request)
    return clean


def _log_payload(payload, route):
    print("[AI REQUEST] " + json.dumps(dict(route=route, **payload_fingerprint(payload))), flush=True)


def chat_prompt(status_map, pages, user_text):
    sess = _session()
    facts = {"question": user_text, "session": sess,
             "observation_jobs": _store().jobs(sess["id"]) if sess else []}
    if not role_question(user_text):
        facts["runtime_console"] = runtime_tail()
        # Expose only redacted, timestamped status context. No historical chat memory.
        facts["statuses"] = redact(json.dumps(dict(status_map), ensure_ascii=False, default=str))
        facts["pages"] = [{"tab": x.get("tab_id", x.get("tab")), "url": redact(x.get("url", ""))}
                          for x in pages]
    return json.dumps(facts, ensure_ascii=False, default=str)


def chat_request(prompt, images=None, timeout=300):
    import requests
    cfg = _APP["load_deepseek_config"]()
    key = str(cfg.get("api_key") or "").strip()
    if not key:
        return None, "В конфигурации отсутствует api_key"
    if images:
        return None, "Этот диагностический маршрут принимает текст; изображения не были отправлены."
    payload = {"model": cfg.get("model") or "deepseek-flash",
               "messages": operator_messages([{"role": "user", "content": prompt}]),
               "temperature": 0.1, "max_tokens": 2400}
    _log_payload(payload, "chat")
    try:
        response = requests.post("https://api.deepseek.com/chat/completions",
                                 headers={"Authorization": "Bearer " + key}, json=payload,
                                 timeout=(15, max(30, min(int(timeout), 300))))
        if not response.ok:
            return None, f"DeepSeek HTTP {response.status_code}"
        obj = response.json()
        choice = obj["choices"][0]
        content = choice["message"].get("content")
        if not isinstance(content, str) or not content.strip():
            return None, "DeepSeek вернул пустой ответ"
        if choice.get("finish_reason") == "length":
            content += "\n[Ответ ограничен API по длине; это не подтверждение завершения задачи.]"
        return content, None
    except Exception as exc:
        return None, redact(f"{type(exc).__name__}: {exc}")


def runtime_tail(max_lines=180, max_chars=32000):
    if _session() is None:
        return "Основной runtime не запущен; текущих runtime-логов нет. История не подставлена."
    return current_log_tail(_APP["RUNTIME_CONSOLE_FILE"], max_lines, max_chars)


def _guarded(worker):
    return bool(worker.get("success_guard") or worker.get("error_guard")
                or worker.get("phase") in _GUARD_PHASES)


def observe(worker, reason=""):
    sess = _session()
    if not sess:
        return False
    page = worker.get("page")
    closed = page is None or page.is_closed()
    ident = str(worker.get("observation_physical_id") or "")
    if not closed and not ident:
        ident = str(_APP["_read_page_window_name"](page) or "")
        worker["observation_physical_id"] = ident
    if not ident:
        return False
    data = {"closed": closed, "url": "" if closed else page.url}
    if not closed:
        # Only field completeness and labels, not personal values or hidden tokens.
        try:
            data.update(page.evaluate("""() => {
                const visible = e => !!(e.getClientRects().length);
                const controls = [...document.querySelectorAll('input,select,textarea')]
                    .filter(e => visible(e) && e.type !== 'hidden' && e.type !== 'password');
                const missing = controls.filter(e => e.required && !e.disabled &&
                    ((e.type==='checkbox'||e.type==='radio') ? !e.checked : !String(e.value||'').trim()));
                const label = e => [...(e.labels||[])].map(x=>x.innerText).join(' ').trim()
                    || e.getAttribute('aria-label') || e.name || e.id || 'без названия';
                const errors = [...document.querySelectorAll('[aria-invalid=true],[role=alert]')]
                    .filter(visible);
                return {missing_fields: missing.map(label).slice(0,80), has_error: errors.length>0,
                    contract_ui: location.pathname.includes('personal-data-form')};
            }"""))
        except Exception:
            data["phase"] = "DOM_UNAVAILABLE"
    kind = "ERROR_SUPERVISION" if state_from_observation(data) == "ERROR" else "SUCCESS_SUPERVISION"
    key = _store().observe(sess["id"], ident, kind, data)
    worker["observation_job_key"] = key
    worker["error_guard"] = kind == "ERROR_SUPERVISION"
    worker["success_guard"] = bool(worker.get("success_guard") or data.get("contract_ui"))
    worker["phase"] = "ERROR_ASSIST" if worker["error_guard"] else "SUCCESS_ASSIST"
    return True


def passive_tick(base_dir, worker):
    now = time.monotonic()
    if now - float(worker.get("observation_last_poll") or 0) < 5:
        return
    worker["observation_last_poll"] = now
    observe(worker)
    page = worker.get("page")
    if page is None or page.is_closed():
        worker["phase"] = "MANUAL_STOP"
        worker["stopped"] = True
    _APP["external_heartbeat"](worker, "readonly_supervision")
    _APP["set_tab_status"](worker, "🔎", "Задание наблюдения активно. Автоподпись отключена; результат не объявляется по смене URL.")


def hold_guarded(base_dir, worker):
    """Keep a protected page under passive observation until the worker is stopped."""
    while not worker.get("stopped"):
        passive_tick(base_dir, worker)
        if worker.get("stopped"):
            break
        page = worker.get("page")
        try:
            if page is not None and not page.is_closed():
                page.wait_for_timeout(250)
                continue
        except Exception:
            pass
        time.sleep(0.25)


def merge_success_profile(worker):
    """Bring a legacy collector's worker["profile"] into the key the result record reads."""
    merged = {}
    for key in ("profile", "success_profile"):
        data = worker.get(key)
        if not isinstance(data, dict):
            continue
        for field, value in data.items():
            value = str(value or "").strip()
            if value:
                merged[PROFILE_ALIASES.get(str(field), str(field))] = value
    worker["success_profile"] = merged
    return merged


def guarded_watchdog_entries(stalled):
    """A protected page is never a stall, whatever its phase label says."""
    kept = []
    for entry in stalled:
        info = entry[2] if isinstance(entry, (tuple, list)) and len(entry) > 2 else None
        if isinstance(info, dict) and (info.get("success_guard") or info.get("error_guard")
                                       or str(info.get("phase") or "") in _GUARD_PHASES):
            continue
        kept.append(entry)
    return kept


def report_loop():
    """One observation-only analyser; no browser control tools are available here."""
    import fcntl
    lock_path = _base() / "operator_reporter.lock"
    with lock_path.open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return
        owner = f"reporter:{os.getpid()}:{uuid.uuid4().hex}"
        while True:
            try:
                sess = _session()
                if sess:
                    store = _store()
                    job = store.claim_changed(owner, sess["id"])
                    if job:
                        text, err = chat_request(json.dumps({
                            "task": "Проанализируй изменение наблюдения. Только факты; действий не выполнялось.",
                            "job": job["job_key"], "physical_id": job["physical_id"],
                            "state": job["state"], "observed_at": job["observed_at"],
                            "observation": json.loads(job["observed_json"])
                        }, ensure_ascii=False))
                        if err:
                            print("[SUPERVISOR RETRY] " + redact(err), flush=True)
                        else:
                            store.finish_report(job["job_key"], owner, job["revision"], text)
                # Relay atomically persisted reports after any earlier failure.
                store = _store()
                for report in store.pending_reports():
                    chat = str(_APP["load_telegram_config"]().get("chat_id") or "")
                    if not chat:
                        break
                    stable = report["job_key"] + ":" + str(report["revision"])
                    update = -int(hashlib.sha256(stable.encode()).hexdigest()[:15], 16)
                    _APP["_ai_db_complete"](update, chat, "🔎 Наблюдение (без действий)\n" + report["body"])
                    store.ack_report(report["job_key"], report["revision"])
            except Exception as exc:
                print("[SUPERVISOR ERROR] " + redact(f"{type(exc).__name__}: {exc}"), flush=True)
            time.sleep(2)


def start_reporter():
    global _REPORTER_STARTED
    if not _REPORTER_STARTED:
        _REPORTER_STARTED = True
        threading.Thread(target=report_loop, name="readonly-supervisor", daemon=True).start()
        # A role/chat question is no longer contingent on successful Chromium startup.
        threading.Thread(target=_APP["ai_observer_process"],
            args=({}, [], threading.Event(), {}, None, None, "chat"),
            name="independent-operator-chat", daemon=True).start()


def deliver(item, cfg, markup=None):
    err = send_outbox_item(item, _store(), _APP["telegram_api"], cfg, markup)
    if err:
        _APP["_ai_db_outbox_fail"](item["update_id"], err, item.get("attempts", 0))
        print(f"[TG RETRY] update={item['update_id']} {redact(err)}", flush=True)
    else:
        _APP["_ai_db_outbox_sent"](item["update_id"])
        print(f"[TG DELIVERED] update={item['update_id']} all_parts_confirmed", flush=True)


def install(ns):
    global _APP
    _APP = ns
    if ns.get("OPERATOR_READONLY_REPAIR_1587"):
        return
    ns["OPERATOR_READONLY_REPAIR_1587"] = True
    ns["_r87_messages"] = operator_messages
    ns["_r87_payload_log"] = _log_payload
    ns["_chat_prompt"] = chat_prompt
    ns["deepseek_vision_request"] = chat_request
    ns["_runtime_console_tail"] = runtime_tail
    ns["_r87_start_reporter"] = start_reporter
    ns["_r87_deliver"] = deliver
    ns["_r87_job_status"] = lambda: _store().jobs((_session() or {}).get("id", "no-session"))
    ns["_r87_guarded"] = _guarded
    ns["_r87_hold_guarded"] = hold_guarded
    original_api = ns["telegram_api"]
    def telegram_api(*args, **kwargs):
        obj, err = original_api(*args, **kwargs)
        return obj, redact(err) if err else None
    ns["telegram_api"] = telegram_api
    original_session = ns["create_diagnostic_session"]
    def create_session(*args, **kwargs):
        result = original_session(*args, **kwargs)
        meta = {"id": uuid.uuid4().hex, "started_at": time.time(),
                "pid": os.getpid(), "pid_start": _pid_start(os.getpid())}
        path = _base() / "operator_runtime_session.json"
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(meta)); tmp.chmod(0o600); os.replace(tmp, path)
        with Path(ns["RUNTIME_CONSOLE_FILE"]).open("a") as f:
            f.write(f"\n=== CURRENT SERVICE SESSION START {meta['id']} ===\n")
        return result
    ns["create_diagnostic_session"] = create_session
    ns["queue_success_assist"] = lambda worker, reason, force=False: observe(worker, reason)
    ns["queue_error_assist"] = lambda worker, reason, force=False: observe(worker, reason)
    for name in ("tick_post_auth_review", "tick_sign_wait", "tick_success_assist", "tick_error_assist"):
        if name in ns:
            ns[name] = passive_tick
    for name in ("restart_same_row_in_new_page", "begin_worker_cancel"):
        original = ns[name]
        def prevent_recovery(worker, *args, _fn=original, **kwargs):
            if _guarded(worker):
                return False
            return _fn(worker, *args, **kwargs)
        ns[name] = prevent_recovery
    original_final = ns["finalize_success"]
    def guarded_final(base_dir, worker):
        page = worker.get("page")
        obs = {"url": "" if page is None else page.url,
               "closed": page is None or page.is_closed(),
               "physical_id": worker.get("observation_physical_id"),
               "order_id": worker.get("verified_order_id"),
               "verified_receipt": worker.get("verified_completion_receipt")}
        if state_from_observation(obs) != "CONTRACT_CONFIRMED":
            observe(worker, "no verified completion receipt")
            return False
        return original_final(base_dir, worker)
    ns["finalize_success"] = guarded_final
    if "tick_worker" in ns:
        # The dispatcher of the installed build has no branch for the assist phases:
        # without this the loop spins silently, the heartbeat goes stale and the parent
        # watchdog "recovers" the protected page.
        original_tick = ns["tick_worker"]
        def tick_worker(base_dir, worker):
            if str(worker.get("phase") or "") in _ASSIST_PHASES:
                passive_tick(base_dir, worker)
                return None
            return original_tick(base_dir, worker)
        ns["tick_worker"] = tick_worker
    if "parent_watchdog" in ns:
        original_watchdog = ns["parent_watchdog"]
        def parent_watchdog(processes, heartbeat):
            return guarded_watchdog_entries(original_watchdog(processes, heartbeat))
        ns["parent_watchdog"] = parent_watchdog
    if "write_success_record" in ns:
        original_record = ns["write_success_record"]
        def write_success_record(base_dir, worker):
            merge_success_profile(worker)
            return original_record(base_dir, worker)
        ns["write_success_record"] = write_success_record
    original_heartbeat = ns["external_heartbeat"]
    def heartbeat(worker, label):
        original_heartbeat(worker, label)
        hb = worker.get("heartbeat")
        if hb is not None:
            key = str(worker["id"])
            info = dict(hb.get(key) or {})
            info.update(success_guard=bool(worker.get("success_guard")),
                        error_guard=bool(worker.get("error_guard")))
            hb[key] = info
    ns["external_heartbeat"] = heartbeat

#!/usr/bin/env python3
"""Review-first installer. --check changes nothing. --apply requires a stopped service.

This adds read-only observation, fixes prompt routing/queues and prevents unsupported
success claims. It does not implement identity autofill or automatic contract signing.
"""
from __future__ import annotations
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time

VERSION = "15.87-readonly"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def node_range(source, node):
    lines = source.splitlines(keepends=True)
    return sum(map(len, lines[:node.lineno-1])), sum(map(len, lines[:node.end_lineno]))


def functions(source, name):
    return [x for x in ast.walk(ast.parse(source)) if isinstance(x, ast.FunctionDef) and x.name == name]


def only_function(source, name):
    nodes = functions(source, name)
    if len(nodes) != 1:
        raise ValueError(f"Expected one {name}; found {len(nodes)}. Source unchanged.")
    return nodes[0]


def edit_function(source, name, transform):
    n = only_function(source, name)
    a, b = node_range(source, n)
    return source[:a] + transform(source[a:b]) + source[b:]


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise ValueError(f"Unsupported source pattern: {old[:85]!r}; count={text.count(old)}")
    return text.replace(old, new, 1)


GUARD_PHASES = ("ERROR_ASSIST", "SUCCESS_ASSIST")
LEGACY_PROFILE_KEYS = (
    ('worker["profile"]', 'worker["success_profile"]'),
    ("worker['profile']", "worker['success_profile']"),
    ('worker.get("profile")', 'worker.get("success_profile")'),
    ("worker.get('profile')", "worker.get('success_profile')"),
    ('worker.setdefault("profile"', 'worker.setdefault("success_profile"'),
)
PROFILE_FIELD_ALIASES = (('"passport_issuer":', '"passport_issued_by":'), ('"city":', '"locality":'))


def node_byte_span(source, node):
    """ast offsets are UTF-8 byte offsets; the sources contain Cyrillic text."""
    data = source.encode("utf-8")
    starts = [0]
    for line in data.splitlines(keepends=True):
        starts.append(starts[-1] + len(line))
    return starts[node.lineno - 1] + node.col_offset, starts[node.end_lineno - 1] + node.end_col_offset


def extend_phase_set(source, scope_name, var_name, extra):
    """Add phases to the single set literal assigned to var_name; refuse anything ambiguous."""
    scope = only_function(source, scope_name) if scope_name else ast.parse(source)
    sets = [n for n in ast.walk(scope) if isinstance(n, ast.Assign) and isinstance(n.value, ast.Set)
            and any(isinstance(x, ast.Name) and x.id == var_name for x in n.targets)]
    if len(sets) != 1:
        raise ValueError(f"{var_name} not unambiguous in {scope_name or 'module'}; source unchanged")
    n = sets[0]
    if not all(isinstance(x, ast.Constant) and isinstance(x.value, str) for x in n.value.elts):
        raise ValueError(f"{var_name} has non-literal members; source unchanged")
    a, b = node_range(source, n)
    states = {x.value for x in n.value.elts}
    states.update(extra)
    return (source[:a] + " " * n.col_offset + f"{var_name} = {{"
            + ", ".join(repr(x) for x in sorted(states)) + "}\n" + source[b:])


def inject_after_payload(source, fn_name, lines):
    """Insert lines right after the single `payload = {..., "messages": ...}` assignment."""
    fn = only_function(source, fn_name)
    payloads = [n for n in ast.walk(fn) if isinstance(n, ast.Assign)
                and isinstance(n.value, ast.Dict)
                and any(isinstance(k, ast.Constant) and k.value == "messages" for k in n.value.keys)
                and any(isinstance(x, ast.Name) and x.id == "payload" for x in n.targets)]
    if len(payloads) != 1:
        raise ValueError(f"Ambiguous API payload in {fn_name}")
    n = payloads[0]
    _, pos = node_range(source, n)
    indent = " " * n.col_offset
    return source[:pos] + "".join(indent + line + "\n" for line in lines) + source[pos:]


def drop_legacy_prompt_injections(body):
    """Remove the 15.85/15.86 blocks: each round they nested the previous system text again."""
    while True:
        starts = [i for i in (body.find("# 15.85:"), body.find("# 15.86:")) if i >= 0]
        if not starts:
            return body
        a = body.rfind("\n", 0, min(starts)) + 1
        b = body.find("payload = {", a)
        if b < 0:
            raise ValueError("legacy prompt injection without a payload; source unchanged")
        body = body[:a] + body[body.rfind("\n", 0, b) + 1:]


def strip_slices_in_calls(source, fn_name, callee):
    """Remove `[:N]` from arguments passed to callee(...) inside fn_name."""
    while True:
        fn = only_function(source, fn_name)
        targets = [arg for n in ast.walk(fn) if isinstance(n, ast.Call)
                   and ast.unparse(n.func).endswith(callee)
                   for arg in n.args
                   if isinstance(arg, ast.Subscript) and isinstance(arg.slice, ast.Slice)
                   and arg.slice.lower is None and arg.slice.step is None
                   and isinstance(arg.slice.upper, ast.Constant)]
        if not targets:
            return source
        arg = targets[0]
        _, value_end = node_byte_span(source, arg.value)
        _, end = node_byte_span(source, arg)
        data = source.encode("utf-8")
        bracket = data.find(b"[", value_end, end)
        if bracket < 0:
            raise ValueError("slice bracket not found; source unchanged")
        source = (data[:bracket] + data[end:]).decode("utf-8")


def route_outbox_through_deliver(source, build_call):
    """Replace the single `if out:` send block after `out = ..._ai_db_next_outbox()`."""
    found = []
    for parent in ast.walk(ast.parse(source)):
        for field in ("body", "orelse", "finalbody"):
            stmts = getattr(parent, field, None)
            if not isinstance(stmts, list):
                continue
            for prev, node in zip(stmts, stmts[1:]):
                if (isinstance(prev, ast.Assign) and isinstance(prev.value, ast.Call)
                        and ast.unparse(prev.value.func).endswith("_ai_db_next_outbox")
                        and any(isinstance(t, ast.Name) and t.id == "out" for t in prev.targets)
                        and isinstance(node, ast.If) and isinstance(node.test, ast.Name)
                        and node.test.id == "out"):
                    found.append(node)
    if len(found) != 1:
        raise ValueError(f"outbox send block not unambiguous: {len(found)}")
    node = found[0]
    cfgs = {ast.unparse(c.args[0]) for c in ast.walk(node) if isinstance(c, ast.Call)
            and ast.unparse(c.func).endswith("telegram_api") and c.args}
    if len(cfgs) != 1:
        raise ValueError("outbox send block has no single Telegram config variable")
    a, b = node_range(source, node)
    indent = " " * node.col_offset
    return source[:a] + indent + "if out:\n" + indent + "    " + build_call(cfgs.pop()) + "\n" + source[b:]


def rename_profile_key(source):
    """Collector and result writer share one key; collectors' legacy field names are aliased."""
    for old, new in LEGACY_PROFILE_KEYS:
        source = source.replace(old, new)
    collectors = []
    for fn in ast.parse(source).body:
        if isinstance(fn, ast.FunctionDef) and fn.name not in ("write_success_record", "_success_message"):
            a, b = node_range(source, fn)
            if 'worker["success_profile"]' in source[a:b] or "worker['success_profile']" in source[a:b]:
                collectors.append(fn.name)
    for name in collectors:
        def alias(body):
            for old, new in PROFILE_FIELD_ALIASES:
                body = body.replace(old, new)
            return body
        source = edit_function(source, name, alias)
    return source


def transform_app(source):
    if "# OPERATOR_REPAIR_1587_INSTALLED" in source:
        compile(source, "test_beeline.py", "exec")
        return source
    for name in ("_run_developer_agent", "_chat_prompt", "deepseek_vision_request", "ai_observer_process",
                 "finalize_success", "_tab_process", "_ai_db_init", "external_heartbeat", "tick_worker",
                 "parent_watchdog", "write_success_record",
                 "create_diagnostic_session", "begin_worker_cancel", "restart_same_row_in_new_page"):
        only_function(source, name)
    original_flags = ('"--no-sandbox"' in source, '"--disable-setuid-sandbox"' in source)
    original_browser_args = None
    for n in ast.walk(ast.parse(source)):
        if isinstance(n, ast.Assign) and any(isinstance(x, ast.Name) and x.id == 'args_i' for x in n.targets):
            original_browser_args = ast.dump(n, include_attributes=False)
    if original_browser_args is None:
        raise ValueError("Known browser args_i not found; no patch applied")

    # One authoritative system message at BOTH real API boundaries. The 15.85/15.86
    # blocks re-nested the previous system text every round (2.8k -> 28k chars in ten
    # rounds); they are removed rather than overridden.
    source = edit_function(source, "_run_developer_agent", drop_legacy_prompt_injections)
    source = inject_after_payload(source, "_run_developer_agent", [
        "# Authoritative request; no old system history or recursive prompt growth.",
        'payload["messages"] = _r87_messages(messages, request=user_text)',
        'messages = payload["messages"]',
        '_r87_payload_log(payload, "developer")'])
    # Ordinary chat (_chat_prompt -> deepseek_vision_request) and any other caller of the
    # text/vision request get the same system message even if they bound the original function.
    source = inject_after_payload(source, "deepseek_vision_request", [
        "# Same single authoritative system message as the developer boundary.",
        'payload["messages"] = _r87_messages(payload["messages"])',
        '_r87_payload_log(payload, "vision")'])

    # Ordinary chat has a separate consumer owned by the controller, not Chromium.
    source = edit_function(source, "_ai_message_lane", lambda b: replace_once(
        b, 'return "dev" if any(x in low for x in code_triggers) else "fast"',
        'return "dev" if any(x in low for x in code_triggers) else ("fast" if _operator_needs_tools(body) else "chat")'))
    source = edit_function(source, "ai_observer_process", lambda b: replace_once(
        b, 'if lane == "fast" and not _operator_needs_tools(latest):',
        'if lane in {"fast", "chat"} and not _operator_needs_tools(latest):'))
    # The full answer is persisted; splitting happens only at delivery, part by part.
    source = edit_function(source, "ai_observer_process", lambda b: b.replace(
        '"🤖 DeepSeek Operator\\n\\nГотово."',
        '"🤖 DeepSeek Operator\\n\\nПустой результат; завершение не подтверждено."'))
    source = strip_slices_in_calls(source, "ai_observer_process", "_ai_db_complete")
    source = route_outbox_through_deliver(source, lambda cfg: f"_r87_deliver(out, {cfg})")

    # Re-running schema init must not steal an active consumer's job.
    fn = only_function(source, '_ai_db_init')
    removable = []
    for n in ast.walk(fn):
        if isinstance(n, ast.Expr) and isinstance(n.value, ast.Call):
            call = n.value
            if call.args and isinstance(call.args[0], ast.Constant) and isinstance(call.args[0].value, str):
                sql = ' '.join(call.args[0].value.split()).lower()
                if sql == 'update inbox set claimed_by=null, claim_until=null where done_at is null':
                    removable.append(n)
    if len(removable) != 1:
        raise ValueError('Queue claim-reset SQL differs; preserving existing code')
    a,b = node_range(source, removable[0])
    source = source[:a] + '        # Existing claim leases are deliberately preserved.\n' + source[b:]
    source = edit_function(source, '_ai_db_init', lambda b: replace_once(
        b, 'SELECT update_id, body FROM inbox WHERE done_at IS NULL',
        'SELECT update_id, body FROM inbox WHERE done_at IS NULL AND update_id > 0'))
    # Suspend legacy autonomous signing prompts without deleting their evidence.
    source = edit_function(source, '_ai_db_init', lambda b: replace_once(b,
        '        conn.commit()\n',
        '''        conn.execute("""UPDATE inbox SET lane='legacy_supervision',
            last_error='Paused legacy autonomous job; observation-only supervisor replaces it'
            WHERE done_at IS NULL AND update_id < 0
            AND (body LIKE '[AUTO_SUCCESS_ASSIST%' OR body LIKE '[AUTO_ERROR_ASSIST%')""")
        conn.commit()
'''))
    # Re-completing the same update must not reset delivery or overwrite its answer.
    source = edit_function(source, '_ai_db_complete', lambda b: replace_once(b,
        '''ON CONFLICT(update_id) DO UPDATE SET
                   body=excluded.body,
                   chat_id=excluded.chat_id,
                   created_at=excluded.created_at,
                   attempts=0,
                   next_attempt_at=0,
                   last_error=NULL,
                   sent_at=NULL''',
        'ON CONFLICT(update_id) DO NOTHING'))

    # Diagnostic assistance is a real tickable state, not "unknown -> restart", and the
    # parent watchdog never treats a protected page as a stall.
    source = extend_phase_set(source, "_tab_process", "tickable_phases", GUARD_PHASES)
    source = extend_phase_set(source, "parent_watchdog", "skip_phases", GUARD_PHASES)
    # A guarded worker that still reaches the unexpected-phase branch is held, never
    # restarted, and never allowed to consume the next shared-queue row.
    fn = only_function(source, "_tab_process")
    calls = [n for n in ast.walk(fn) if isinstance(n, ast.Expr) and isinstance(n.value, ast.Call)
             and isinstance(n.value.func, ast.Name) and n.value.func.id == "restart_same_row_in_new_page"]
    if len(calls) != 1:
        raise ValueError("unexpected-phase recovery call not unambiguous; source unchanged")
    a, _ = node_range(source, calls[0])
    indent = " " * calls[0].col_offset
    source = (source[:a] + indent + "if _r87_guarded(worker):\n"
              + indent + "    # Protected observation page: hold it; never restart it or take another row.\n"
              + indent + "    _r87_hold_guarded(base_dir, worker)\n"
              + indent + "    break\n" + source[a:])

    # Collector and result writer must read the same key, whatever the collector is called.
    source = rename_profile_key(source)

    # Install adapters on module import, before __main__; also works under spawn.
    main_ifs=[n for n in ast.parse(source).body if isinstance(n,ast.If)
              and '__name__' in ast.unparse(n.test) and '__main__' in ast.unparse(n.test)]
    if len(main_ifs) != 1:
        raise ValueError('Expected a single __main__ entry point')
    a,_=node_range(source,main_ifs[0])
    source=source[:a]+'''# OPERATOR_REPAIR_1587_INSTALLED
from operator_adapter import install as _install_operator_repair_1587
OPERATOR_REPAIR_VERSION = '15.87-readonly'
_install_operator_repair_1587(globals())

'''+source[a:]
    # Do not claim a version until this concrete change actually exists.
    compile(source,'test_beeline.py','exec')
    assert original_flags == ('"--no-sandbox"' in source, '"--disable-setuid-sandbox"' in source)
    matches=[n for n in ast.walk(ast.parse(source)) if isinstance(n,ast.Assign)
             and any(isinstance(x,ast.Name) and x.id=='args_i' for x in n.targets)]
    assert len(matches)==1 and ast.dump(matches[0],include_attributes=False)==original_browser_args
    return source


def transform_controller(source):
    if '# OPERATOR_CONTROLLER_REPAIR_1587' in source:
        return source
    only_function(source,'main'); only_function(source,'_send')
    source=route_outbox_through_deliver(source, lambda cfg: f"app._r87_deliver(out, {cfg}, MENU_MARKUP)")
    source=replace_once(source,'    app._ai_db_init()\n',
                        '    app._ai_db_init()\n    app._r87_start_reporter()\n')
    source=edit_function(source,'_send',lambda _: '''def _send(text, *, menu=True):
    # Control replies are persisted too, not dropped after a proxy timeout.
    app._ai_db_complete(-time.time_ns(), _chat_id(), str(text))
    return True

''')
    source=replace_once(source,'                finally:\n                    _save_offset(offset)\n',
                        '''                finally:
                    # Never acknowledge a Telegram update after failed persistence.
                    if sys.exc_info()[0] is None:
                        _save_offset(offset)
                    else:
                        _save_offset(update_id)
''')
    # A temporary Telegram outage must not crash/restart the controller.
    startup = '''    me, err = app.telegram_api(cfg, "getMe", {})
    if err or not me:
        raise RuntimeError(f"Telegram недоступен: {err}")
'''
    if startup in source:
        source=replace_once(source, startup, '''    while True:
        me, err = app.telegram_api(cfg, "getMe", {})
        if not err and me and me.get("ok"):
            break
        print(f"[CTRL TG] startup waiting: {err or 'no Telegram confirmation'}", flush=True)
        time.sleep(5)
''')
    # Show factual observation jobs without sending /status to the language model.
    old='                        _send(f"Состояние: {proc.status()}")\n'
    if old in source:
        source=source.replace(old,'''                        jobs = app._r87_job_status()
                        details = "\\n".join(
                            f"{j['physical_id']}: {j['kind']} / {j['state']} / rev={j['revision']}"
                            for j in jobs)
                        _send(f"Состояние: {proc.status()}\\nНаблюдение:\\n{details or 'активных заданий нет'}")
''',1)
    if 'BTN_STATUS = ' not in source:
        source=replace_once(source, 'BTN_UPLOAD = "📥 Загрузить новую базу номеров"\n',
                            'BTN_UPLOAD = "📥 Загрузить новую базу номеров"\nBTN_STATUS = "📊 Статус"\n')
        source=replace_once(source, '    BTN_UPLOAD,\n', '    BTN_UPLOAD,\n    BTN_STATUS,\n')
        source=replace_once(source, '            [{"text": BTN_UPLOAD}],\n',
                            '            [{"text": BTN_UPLOAD}, {"text": BTN_STATUS}],\n')
        source=replace_once(source, 'if text == "/status":', 'if text == "/status" or text == BTN_STATUS:')
    source += '\n# OPERATOR_CONTROLLER_REPAIR_1587\n'
    compile(source,'server_controller.py','exec')
    return source


def prepare(app):
    paths=[app/'test_beeline.py',app/'server_controller.py']
    raw={p.name:p.read_bytes() for p in paths}
    result={'test_beeline.py':transform_app(raw['test_beeline.py'].decode('utf-8')),
            'server_controller.py':transform_controller(raw['server_controller.py'].decode('utf-8'))}
    root=Path(__file__).resolve().parent
    for name in ('operator_reliability.py','operator_adapter.py'):
        result[name]=(root/name).read_text('utf-8')
    for name,content in result.items():
        compile(content,name,'exec')
    return raw,result


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--app',type=Path,default=Path('/opt/beeline'))
    mode=ap.add_mutually_exclusive_group()
    mode.add_argument('--check',action='store_true')
    mode.add_argument('--apply',action='store_true')
    args=ap.parse_args()
    raw,result=prepare(args.app)
    audit={'version':VERSION,'mode':'apply' if args.apply else 'check',
           'source_sha256':{k:sha(v) for k,v in raw.items()},
           'result_sha256':{k:sha(v.encode()) for k,v in result.items()},
           'supervisor':'read-only','automatic_signing':False,
           'data_files_modified':False,'browser_arguments_modified':False}
    if not args.apply:
        print(json.dumps(audit,ensure_ascii=False,indent=2)); print('CHECK OK. No service stopped; no files changed.'); return
    if args.app.resolve()!=Path('/opt/beeline'):
        raise SystemExit('--apply is restricted to /opt/beeline; tests use transform functions')
    try:
        status=subprocess.run(['systemctl','is-active','beeline'],capture_output=True,text=True,timeout=10)
    except Exception as exc:
        raise SystemExit('Cannot verify service state; refusing write: '+type(exc).__name__)
    if status.stdout.strip() not in {'inactive','failed','unknown'}:
        raise SystemExit('Service is running. No changes made: finish protected pages and stop beeline explicitly first.')
    for name,data in raw.items():
        if (args.app/name).read_bytes()!=data:
            raise SystemExit('Source changed during preflight; nothing applied')
    backup=args.app/'code_backups'/('repair1587_'+time.strftime('%Y%m%d_%H%M%S')+'_'+str(os.getpid()))
    backup.mkdir(parents=True,mode=0o700)
    previous={}
    for name in result:
        dst=args.app/name
        previous[name]=dst.read_bytes() if dst.exists() else None
        if dst.exists():
            shutil.copy2(dst,backup/name)
    (backup/'manifest.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2))
    try:
        for name,content in result.items():
            fd,tmp=tempfile.mkstemp(prefix='.'+name+'.',dir=args.app)
            try:
                with os.fdopen(fd,'w',encoding='utf-8') as f:
                    f.write(content); f.flush(); os.fsync(f.fileno())
                os.chmod(tmp,0o600); os.replace(tmp,args.app/name)
            finally:
                if os.path.exists(tmp): os.unlink(tmp)
    except BaseException:
        for name,data in previous.items():
            if data is None: (args.app/name).unlink(missing_ok=True)
            else: (args.app/name).write_bytes(data)
        raise
    print(json.dumps(audit,ensure_ascii=False,indent=2))
    print('APPLIED. Backup:',backup)
    print('Services were not restarted. Start explicitly after reviewing the read-only scope.')

if __name__=='__main__':
    main()

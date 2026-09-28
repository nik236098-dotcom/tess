#!/usr/bin/env bash
set -Eeuo pipefail
APP=/opt/beeline
cd "$APP"
systemctl stop beeline || true
cp -a test_beeline.py test_beeline.py.pre1581

python3 - <<'PY'
from pathlib import Path
import re
p=Path("/opt/beeline/test_beeline.py")
t=p.read_text(encoding="utf-8")

# 1) Strong primary mission injected into every agent system prompt.
if "OPERATOR_PRIMARY_MISSION_V1581" not in t:
    marker="def _agent_system_prompt("
    i=t.find(marker)
    if i<0: raise SystemExit("PATCH ERROR: agent prompt function missing")
    mission = r'''OPERATOR_PRIMARY_MISSION_V1581 = """
PRIMARY OPERATOR MISSION (ALWAYS ACTIVE):
Your first and permanent job is autonomous supervision of confirmed post-auth tabs
and completion of the contract flow. You are not merely a technical helper.

SUCCESS priority: when a worker leaves mobile-id-auth for the personal-data/contract
page, observe the current physical tab first: DOM, validation errors, enabled/disabled
controls, DevTools console and network. If progress stalls, diagnose the actual blocker.
ANY required field may be missing or invalid; discover it from the live page rather than
assuming a fixed list. Preserve fields that are already valid. Safely fill/correct what is
missing, choose autocomplete suggestions when required, complete the signature correctly,
wait until Sign Contract is enabled, click it, and verify the real result. Do this without
asking the user to participate.

ERROR priority: /registration/error is never success. Inspect the live DOM, visible error,
console/network and recent responses first. Attempt a safe repair on the same physical tab.
Do not destroy the state with automatic close/restart/reload/back/navigation.

SUCCESS_GUARD and ERROR_GUARD are immutable: elapsed time alone never permits destructive
recovery.

After autonomous intervention, send a concise factual report: blocker found; checks made;
exact fields/values changed; button state; whether Sign Contract was clicked; actual result;
final page/URL.

Worker/proxy/Telegram/code monitoring is secondary. User messages are additional tasks.
If asked what your task is, lead with autonomous SUCCESS/ERROR supervision and contract
completion, never with 'technical helper' or 'no concrete task'.

CURRENT STATE RULE:
For claims about what is happening NOW, use current heartbeat/status, current physical tabs,
the current diagnostic session, and runtime console entries from the CURRENT SERVICE SESSION.
Historical logs from before the current service start are history only. Never present an old
proxy/Telegram/ConnectTimeout/RemoteDisconnected error as current unless fresh current-session
evidence confirms it.
"""
'''
    t=t[:i]+mission+"\n"+t[i:]

# Add mission at start of returned prompt without depending on exact prompt body.
i=t.find("def _agent_system_prompt(")
j=t.find("\ndef ",i+5)
if j<0:j=len(t)
block=t[i:j]
if "OPERATOR_PRIMARY_MISSION_V1581 +" not in block:
    # Find the first return inside this function and prepend mission to its expression.
    m=re.search(r'(?m)^(\s*)return\s+',block)
    if not m: raise SystemExit("PATCH ERROR: prompt return missing")
    absolute=i+m.end()
    t=t[:absolute]+'OPERATOR_PRIMARY_MISSION_V1581 + "\\n\\n" + '+t[absolute:]

# 2) Session boundary for runtime console.
if "RUNTIME_SESSION_STARTED_AT" not in t:
    marker='RUNTIME_CONSOLE_FILE = RUNTIME_LOG_DIR / "console.log"'
    if marker not in t: raise SystemExit("PATCH ERROR: runtime console marker missing")
    repl=marker+'\nRUNTIME_SESSION_STARTED_AT = time.time()\nRUNTIME_SESSION_MARKER = f"=== CURRENT SERVICE SESSION START {RUNTIME_SESSION_STARTED_AT:.3f} ==="'
    t=t.replace(marker,repl,1)

# Make read_runtime_console current-session scoped by default.
tool_marker='if name == "read_runtime_console":'
idx=t.find(tool_marker)
if idx>=0 and "current_session_only" not in t[idx:idx+5000]:
    # Inject filtering immediately after branch header.
    line_end=t.find("\n",idx)
    indent=re.match(r'\s*',t[line_end+1:]).group(0)
    inject='''\n'''+indent+'''# 15.81: current-state reads exclude history before current service start.
'''+indent+'''args = dict(args or {})
'''+indent+'''args.setdefault("current_session_only", True)
'''
    t=t[:line_end+1]+inject+t[line_end+1:]

# Patch runtime reader function itself if discoverable.
for fname in ["_read_runtime_console","read_runtime_console"]:
    fi=t.find("def "+fname+"(")
    if fi>=0:
        fj=t.find("\ndef ",fi+5)
        if fj<0:fj=len(t)
        fb=t[fi:fj]
        if "CURRENT SERVICE SESSION" not in fb:
            # Rather than rewrite unknown implementation, prepend a session marker to the
            # runtime log at process startup so current-session search has a hard boundary.
            pass
        break

# Write a hard session marker to console at main startup.
main_marker='base_dir = Path(__file__).resolve().parent'
mi=t.find(main_marker,t.find("def main("))
if mi>=0 and "CURRENT SERVICE SESSION START" not in t[mi:mi+1200]:
    end=t.find("\n",mi)
    inject='''\n    try:
        RUNTIME_LOG_DIR.mkdir(parents=True, exist_ok=True)
        with RUNTIME_CONSOLE_FILE.open("a", encoding="utf-8") as _f:
            _f.write("\\n" + RUNTIME_SESSION_MARKER + "\\n")
    except Exception:
        pass
'''
    t=t[:end+1]+inject+t[end+1:]

t=re.sub(
    r'print\("Версия 15\.(?:7[5-9]|8[01])[^"]*"\)',
    'print("Версия 15.81 EXP-3: primary mission + current-session log boundary")',
    t,count=1
)
compile(t,str(p),"exec")
p.write_text(t,encoding="utf-8")
print("15.81 hotfix OK")
PY

"$APP/venv/bin/python" -m py_compile "$APP/test_beeline.py" "$APP/server_controller.py"
systemctl restart beeline
sleep 3
echo "=== 15.81 ==="
grep -m1 "OPERATOR_PRIMARY_MISSION_V1581" "$APP/test_beeline.py"
grep -m1 "Версия 15.81" "$APP/test_beeline.py" || true
echo "=== BEELINE ==="
systemctl is-active beeline

#!/usr/bin/env bash
set -Eeuo pipefail
APP=/opt/beeline
cd "$APP"
systemctl stop beeline || true
cp -a test_beeline.py test_beeline.py.pre1579

python3 - <<'PY'
from pathlib import Path
p=Path("/opt/beeline/test_beeline.py")
t=p.read_text(encoding="utf-8")

# 15.79 server hotfix must tolerate servers that are still on 15.75/15.76.
# Do not require 15.77 helper names to exist.
if "def queue_error_assist(" not in t:
    # Prefer insertion near AI DB helpers, which exist on all current server builds.
    candidates=[
        "def _ai_effect_key(",
        "def _run_developer_agent(",
        "def _agent_system_prompt(",
    ]
    anchor=next((a for a in candidates if a in t),None)
    if not anchor:
        raise SystemExit("PATCH ERROR: no stable AI anchor found")
    helper=r'''def queue_error_assist(worker, reason, force=False):
    """Autonomous analysis for /registration/error without destructive recovery."""
    now = monotonic()
    last = float(worker.get("error_ai_last_at") or 0)
    if not force and now-last < 45:
        return False
    worker["error_ai_last_at"]=now
    tab_id=int(worker.get("id") or 0)
    try:
        url=worker.get("page").url
    except Exception:
        url=""
    body=(
        f"[AUTO_ERROR_ASSIST TAB {tab_id}] /registration/error is NOT success. "
        "Do not close/restart/reload/back/navigate. First inspect DOM, visible error, "
        "DevTools console/network and recent requests. Diagnose the concrete cause and "
        "safely repair the current page when possible. If not possible, keep it open "
        "and send a mini-report with cause, actions, result and final URL. "
        f"Reason: {reason}. URL: {url}"
    )
    try:
        # Use durable AI inbox if this build has it.
        fn=globals().get("_ai_db_enqueue_internal")
        if fn:
            fn(body,lane="fast",priority=125)
            print(f"[AI AUTO] TAB {tab_id}: ERROR_ASSIST queued",flush=True)
            return True
        print(f"[AI AUTO] TAB {tab_id}: ERROR_ASSIST requested but internal queue unavailable",flush=True)
        return False
    except Exception as exc:
        print(f"[AI AUTO] TAB {tab_id}: ERROR_ASSIST queue failed: {exc}",flush=True)
        return False


'''
    t=t.replace(anchor,helper+anchor,1)

# Add worker fields using a stable make_worker dictionary tail.
if '"error_guard": False' not in t:
    marker='"stopped": False,'
    pos=t.find(marker,t.find("def make_worker("))
    if pos<0: raise SystemExit("PATCH ERROR: make_worker stopped field")
    pos2=pos+len(marker)
    t=t[:pos2]+'\n        "error_guard": False,\n        "error_ai_last_at": 0.0,'+t[pos2:]

# Add guard helpers before tick_confirmation, stable across old builds.
if "def enter_error_guard(" not in t:
    anchor="def tick_confirmation("
    if anchor not in t: raise SystemExit("PATCH ERROR: tick_confirmation anchor")
    helper=r'''def _is_registration_error_page(page):
    try:
        return "/registration/error" in str(page.url or "").lower()
    except Exception:
        return False


def enter_error_guard(worker,note):
    worker["error_guard"]=True
    worker["phase"]="ERROR_ASSIST"
    try:
        set_tab_status(worker,"🧠","Registration error — DeepSeek анализирует. Автоперезапуск запрещён.")
    except Exception:
        pass
    try:
        external_heartbeat(worker,note)
    except Exception:
        pass
    queue_error_assist(worker,note,force=True)


def tick_error_assist(base_dir,worker):
    page=worker["page"]
    worker["error_guard"]=True
    if page.is_closed():
        worker["phase"]="MANUAL_STOP"
        worker["stopped"]=True
        return
    queue_error_assist(worker,"registration/error всё ещё открыта; проверь DOM/console/network")
    try:
        external_heartbeat(worker,"error_assist_observing")
    except Exception:
        pass


'''
    t=t.replace(anchor,helper+anchor,1)

# Patch every old confirmation-success branch so registration/error cannot be success.
needle='''    if not _is_auth_url(page.url):
        # Пользователь успешно подтвердил'''
if needle in t:
    replacement='''    if not _is_auth_url(page.url):
        if _is_registration_error_page(page):
            try:
                capture_blackbox(worker, "registration_error_after_auth")
            except Exception:
                pass
            print(
                f"[Вкладка {worker['id']}] /registration/error: НЕ success; "
                "сначала автономный анализ, без restart/reload/close.",
                flush=True,
            )
            enter_error_guard(worker,"после mobile-id-auth открылась /registration/error")
            return
        # Пользователь успешно подтвердил'''
    t=t.replace(needle,replacement)

# Newer post-auth branch variants.
old='''        if _post_auth_error_page(page):
            capture_blackbox(worker, "registration_error_after_auth")
            print(
                f"[Вкладка {worker['id']}] После auth открылась error-страница — "
                "это НЕ успех. Повторяю строку.",
                flush=True,
            )
            restart_same_row_in_new_page(worker)
            return'''
new='''        if _post_auth_error_page(page):
            capture_blackbox(worker, "registration_error_after_auth")
            print(
                f"[Вкладка {worker['id']}] /registration/error: НЕ success; "
                "сначала автономный анализ, без retry/restart.",
                flush=True,
            )
            enter_error_guard(worker,"после mobile-id-auth открылась /registration/error")
            return'''
t=t.replace(old,new)

# Dispatch ERROR_ASSIST.
if 'elif worker["phase"] == "ERROR_ASSIST":' not in t:
    # insert before final generic phase handling using SIGN_WAIT or CONFIRMING branch
    anchors=[
        '''    elif worker["phase"] == "SIGN_WAIT":
        tick_sign_wait(base_dir, worker)
''',
        '''    elif worker["phase"] == "CONFIRMING":
        tick_confirmation(base_dir, worker)
''',
    ]
    a=next((x for x in anchors if x in t),None)
    if not a: raise SystemExit("PATCH ERROR: tick_worker dispatch anchor")
    t=t.replace(a,a+'''    elif worker["phase"] == "ERROR_ASSIST":
        tick_error_assist(base_dir, worker)
''',1)

# Version marker without depending on exact previous version.
import re
t=re.sub(
    r'print\("Версия 15\.(?:7[5-9]|[89][0-9])[^"]*"\)',
    'print("Версия 15.79 EXP-3: Error Supervisor hotfix")',
    t,
    count=1,
)

compile(t,str(p),"exec")
p.write_text(t,encoding="utf-8")
print("15.79 hotfix OK")
PY
"$APP/venv/bin/python" -m py_compile "$APP/test_beeline.py" "$APP/server_controller.py"
systemctl restart telegram-tunnel || true
systemctl restart beeline
sleep 3
echo "=== VERSION ==="
grep -m1 "Версия 15.79" "$APP/test_beeline.py" || true
echo "=== TUNNEL ==="
systemctl is-active telegram-tunnel
echo "=== BEELINE ==="
systemctl is-active beeline
systemctl --no-pager --full status beeline | head -20

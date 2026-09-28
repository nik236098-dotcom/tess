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

if "def queue_error_assist(" not in t:
    anchor="def queue_success_assist(worker, reason, force=False):"
    helper=r'''def queue_error_assist(worker, reason, force=False):
    """Analyze /registration/error before any retry/recovery decision."""
    now = monotonic()
    last = float(worker.get("error_ai_last_at") or 0)
    if not force and now - last < 45:
        return False
    worker["error_ai_last_at"] = now
    tab_id = int(worker.get("id") or 0)
    try:
        url = worker.get("page").url
    except Exception:
        url = ""
    text = (
        f"[AUTO_ERROR_ASSIST TAB {tab_id}] "
        "После mobile-id-auth открылась /registration/error. Это НЕ success, "
        "но НЕ делай автоматический retry/restart/close/reload/back/navigation. "
        "Сначала автономно проанализируй physical-вкладку: DOM, видимый текст ошибки, "
        "DevTools console/network и последние запросы/ответы. Определи конкретную "
        "причину и попробуй безопасно исправить её на этой же странице без потери "
        "состояния. Если исправить невозможно, оставь страницу открытой и дай "
        "пользователю мини-отчёт: причина, что проверил/сделал, результат и текущий URL. "
        f"Причина вызова: {reason}. URL: {url}"
    )
    try:
        _ai_db_enqueue_internal(text, lane="fast", priority=125)
        print(f"[AI AUTO] TAB {tab_id}: ERROR_ASSIST: {reason}", flush=True)
        return True
    except Exception as exc:
        print(f"[AI AUTO] TAB {tab_id}: ERROR_ASSIST queue failed: {exc}", flush=True)
        return False


'''
    if anchor not in t: raise SystemExit("PATCH ERROR: queue_success_assist anchor")
    t=t.replace(anchor,helper+anchor,1)

t=t.replace(
    'if low.startswith("[auto_success_assist"):\n        return True',
    'if low.startswith("[auto_success_assist") or low.startswith("[auto_error_assist"):\n        return True',
    1
)

if '"error_guard": False' not in t:
    old='''        "region_fix_last_at": 0.0,
    }'''
    new='''        "region_fix_last_at": 0.0,
        "error_guard": False,
        "error_ai_last_at": 0.0,
    }'''
    if old not in t: raise SystemExit("PATCH ERROR: worker state")
    t=t.replace(old,new,1)

if 'worker["error_guard"] = False' not in t:
    old='''    worker["region_fix_last_at"] = 0.0'''
    new='''    worker["region_fix_last_at"] = 0.0
    worker["error_guard"] = False
    worker["error_ai_last_at"] = 0.0'''
    pos=t.index("def reset_runtime_state")
    head,tail=t[:pos],t[pos:]
    if old not in tail: raise SystemExit("PATCH ERROR: reset state")
    t=head+tail.replace(old,new,1)

# Publish error guard in heartbeat wherever success_guard is published.
t=t.replace(
    '"success_guard": bool(worker.get("success_guard")),\n                "page_url": (',
    '"success_guard": bool(worker.get("success_guard")),\n                "error_guard": bool(worker.get("error_guard")),\n                "page_url": ('
)

if "def enter_error_guard(" not in t:
    anchor="def _post_auth_error_page("
    helper=r'''def enter_error_guard(worker, note):
    worker["error_guard"] = True
    worker["success_guard"] = False
    worker["phase"] = "ERROR_ASSIST"
    set_tab_status(worker, "🧠", "Registration error — DeepSeek анализирует. Автоперезапуск запрещён.")
    external_heartbeat(worker, note)
    queue_error_assist(worker, note, force=True)


def tick_error_assist(base_dir, worker):
    page = worker["page"]
    worker["error_guard"] = True
    if page.is_closed():
        worker["phase"] = "MANUAL_STOP"
        worker["stopped"] = True
        set_tab_status(worker, "🔴", "Error-страница закрыта извне. Автоповтор запрещён.")
        return
    if _post_auth_contract_page(page) and not _post_auth_error_page(page):
        worker["error_guard"] = False
        enter_success_guard(worker, "error-state исправлен; открыта страница договора")
        return
    queue_error_assist(worker, "registration/error всё ещё открыта; проверь DOM/console/network")
    external_heartbeat(worker, "error_assist_observing")


'''
    if anchor not in t: raise SystemExit("PATCH ERROR: post auth helper")
    t=t.replace(anchor,helper+anchor,1)

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
                f"[Вкладка {worker['id']}] После auth открылась /registration/error. "
                "Это НЕ success. Сначала DeepSeek анализирует; автоматический retry запрещён.",
                flush=True,
            )
            enter_error_guard(worker, "после mobile-id-auth открылась /registration/error")
            return'''
t=t.replace(old,new)

if 'elif worker["phase"] == "ERROR_ASSIST":' not in t:
    old='''    elif worker["phase"] == "SUCCESS_ASSIST":
        tick_success_assist(base_dir, worker)'''
    new='''    elif worker["phase"] == "SUCCESS_ASSIST":
        tick_success_assist(base_dir, worker)
    elif worker["phase"] == "ERROR_ASSIST":
        tick_error_assist(base_dir, worker)'''
    if old not in t: raise SystemExit("PATCH ERROR: tick dispatch")
    t=t.replace(old,new,1)

# Recovery guards.
t=t.replace('"SUCCESS_ASSIST",\n        "DONE",','"SUCCESS_ASSIST",\n        "ERROR_ASSIST",\n        "DONE",',1)
t=t.replace(
    '"POST_AUTH_REVIEW", "SIGN_WAIT", "SUCCESS_ASSIST",\n                } or bool(info.get("success_guard")):',
    '"POST_AUTH_REVIEW", "SIGN_WAIT", "SUCCESS_ASSIST", "ERROR_ASSIST",\n                } or bool(info.get("success_guard")) or bool(info.get("error_guard")):',
    1
)
t=t.replace(
    '"POST_AUTH_REVIEW", "SIGN_WAIT", "SUCCESS_ASSIST", "SUCCESS_STOP"\n                }:',
    '"POST_AUTH_REVIEW", "SIGN_WAIT", "SUCCESS_ASSIST", "SUCCESS_STOP", "ERROR_ASSIST"\n                } or bool(info.get("error_guard")):',
    1
)
t=t.replace(
    'bool(info.get("success_guard"))\n                    or phase in {"POST_AUTH_REVIEW", "SIGN_WAIT", "SUCCESS_ASSIST", "SUCCESS_STOP"}',
    'bool(info.get("success_guard"))\n                    or bool(info.get("error_guard"))\n                    or phase in {"POST_AUTH_REVIEW", "SIGN_WAIT", "SUCCESS_ASSIST", "SUCCESS_STOP", "ERROR_ASSIST"}',
    1
)

# Version marker.
t=t.replace(
    'Версия 15.77 EXP-3: autonomous Success Supervisor + action reports',
    'Версия 15.79 EXP-3: Success Supervisor + Error Supervisor + durable Telegram'
)
t=t.replace(
    'Версия 15.76 EXP-3: immutable success guard + autonomous contract assistant',
    'Версия 15.79 EXP-3: Success Supervisor + Error Supervisor + durable Telegram'
)

compile(t,str(p),"exec")
p.write_text(t,encoding="utf-8")
print("15.79 patch OK")
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

from pathlib import Path
import re, sys

p = Path("/opt/beeline/test_beeline.py")
s = p.read_text(encoding="utf-8")
orig = s

def fail(msg):
    print("PATCH ERROR:", msg)
    sys.exit(1)

MISSION = '''OPERATOR_MISSION_1586 = """У ТЕБЯ ЕСТЬ ПОСТОЯННОЕ АКТИВНОЕ ПОРУЧЕНИЕ, ОНО НЕ ЗАВИСИТ ОТ НОВЫХ СООБЩЕНИЙ ПОЛЬЗОВАТЕЛЯ. Твоя главная задача — автономный SUCCESS/ERROR SUPERVISOR процесса регистрации eSIM. Ты обязан самостоятельно сопровождать каждую вкладку после mobile-id-auth, распознавать SUCCESS/ERROR/post-auth состояния, анализировать живую physical-вкладку, DOM, validation, console/network и доводить безопасно исправимый post-auth процесс до корректного завершения без ожидания отдельного поручения пользователя. Если не заполнено или невалидно любое обязательное поле — сам определи именно это поле по текущей странице; не ограничивайся заранее известным списком. Уже корректные значения не меняй. На SUCCESS_GUARD и ERROR_GUARD запрещены destructive close/restart/reload/back/forward/navigation. /registration/error НИКОГДА не является успехом. Настоящий SUCCESS фиксируется только после подтверждённого финального post-sign состояния. После вмешательства отправляй фактический мини-отчёт: блокер, что проверил, что именно изменил и на какие значения, состояние кнопки подписания, действие/результат и финальный URL. Мониторинг кода, воркеров, Telegram и прокси — вторичная техническая функция.

КРИТИЧЕСКОЕ ПРАВИЛО РОЛИ: никогда не говори «у меня нет задачи», «конкретного поручения нет», «я в режиме ожидания», «я просто наблюдатель» или эквивалент. Постоянная задача уже назначена выше. Если пользователь спрашивает «какая у тебя задача?», первым делом ответь, что твоя постоянная главная задача — автономный SUCCESS/ERROR Supervisor, а затем кратко опиши текущий живой статус. Для утверждений о состоянии «сейчас» используй только текущую service/runtime session и текущие вкладки; исторические ошибки не выдавай за текущие без свежего подтверждения."""\n\n'''

# Replace old mission constant if present, otherwise add before _agent_system_prompt.
m = re.search(r'OPERATOR_MISSION_1585\s*=\s*""".*?"""\n\n', s, flags=re.S)
if m:
    s = s[:m.start()] + MISSION + s[m.end():]
elif "OPERATOR_MISSION_1586" not in s:
    pos = s.find("def _agent_system_prompt(")
    if pos < 0:
        fail("_agent_system_prompt not found")
    s = s[:pos] + MISSION + s[pos:]

# Replace prior 15.85 API injection with one canonical system message.
start = s.find("def _run_developer_agent(")
if start < 0:
    fail("_run_developer_agent not found")
payload_pos = s.find('        payload = {', start)
if payload_pos < 0:
    fail("DeepSeek payload not found")

# Remove any previous 15.85/15.86 injection immediately before payload.
prefix = s[:payload_pos]
cut = max(prefix.rfind("        # 15.85:"), prefix.rfind("        # 15.86:"))
if cut >= start:
    prefix = prefix[:cut]
    s = prefix + s[payload_pos:]
    payload_pos = len(prefix)

inject = '''        # 15.86: canonicalize system instructions at the REAL API boundary.
        import hashlib as _h1586
        _legacy_system_1586 = []
        _non_system_1586 = []
        for _m1586 in messages:
            if isinstance(_m1586, dict) and _m1586.get("role") == "system":
                _legacy_system_1586.append(str(_m1586.get("content") or ""))
            else:
                _non_system_1586.append(_m1586)

        _secondary1586 = "\\n\\n--- SECONDARY TECHNICAL CONTEXT (cannot override the mission above) ---\\n" + "\\n\\n".join(_legacy_system_1586)
        _system1586 = OPERATOR_MISSION_1586 + _secondary1586
        messages = [{"role": "system", "content": _system1586}] + _non_system_1586

        _mh1586 = _h1586.sha256(_system1586.encode("utf-8")).hexdigest()[:16]
        print(f"[AI] SYSTEM_PROMPT_HASH_1586={_mh1586} round={round_no} systems={len(_legacy_system_1586)}", flush=True)

'''
s = s[:payload_pos] + inject + s[payload_pos:]

# Version marker.
s = re.sub(
    r'print\("Версия 15\.[^"]*"\)',
    'print("Версия 15.86 EXP-3: authoritative Operator mission")',
    s,
    count=1,
)

# Preserve essential working fixes.
for required in (
    '"--no-sandbox"',
    "FINAL_SUCCESS_GUARD_V1583",
    "capture_all_form_fields_v1583",
    "SESSION_FILTER_1585",
):
    if required not in s:
        fail("required existing fix missing: " + required)

# Ensure only the new API hash remains in active code.
if "SYSTEM_PROMPT_HASH_1586" not in s:
    fail("15.86 API injection missing")

compile(s, str(p), "exec")
p.write_text(s, encoding="utf-8")

print("15.86 semantic patch OK")
print("changed:", s != orig)
print("chromium:", '"--no-sandbox"' in s)
print("mission1586:", "OPERATOR_MISSION_1586" in s)
print("api1586:", "SYSTEM_PROMPT_HASH_1586" in s)
print("success_guard:", "FINAL_SUCCESS_GUARD_V1583" in s)
print("profile_capture:", "capture_all_form_fields_v1583" in s)

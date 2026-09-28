from pathlib import Path
import re, sys

p = Path("/opt/beeline/test_beeline.py")
s = p.read_text(encoding="utf-8")
orig = s

def fail(msg):
    print("PATCH ERROR:", msg)
    sys.exit(1)

# 1) Chromium root flags
if '"--no-sandbox"' not in s:
    anchor = '            f"--user-data-dir={profile_i}",\n'
    if anchor not in s:
        fail("Chromium user-data-dir anchor not found")
    s = s.replace(
        anchor,
        anchor + '            "--no-sandbox",\n            "--disable-setuid-sandbox",\n',
        1,
    )

# 2) Permanent Operator mission
if "OPERATOR_MISSION_1585" not in s:
    pos = s.find("def _agent_system_prompt(")
    if pos < 0:
        fail("_agent_system_prompt not found")
    mission = '''OPERATOR_MISSION_1585 = """ТВОЯ ПОСТОЯННАЯ ГЛАВНАЯ ЗАДАЧА — автономно сопровождать SUCCESS/ERROR-вкладки и контролировать корректное завершение процесса. После выхода из mobile-id-auth на post-auth страницу сначала наблюдай живую physical-вкладку: DOM, validation, состояние элементов, console/network. Если процесс остановился, самостоятельно установи фактическую причину по странице; недостающим или невалидным может быть любое поле. Уже корректные значения не меняй. SUCCESS_GUARD и ERROR_GUARD запрещают destructive close/restart/reload/back/navigation. После автономного вмешательства отправляй краткий фактический отчёт: блокер, проверки, изменения/значения, состояние действия, результат и текущий URL. Мониторинг воркеров, Telegram, прокси и кода — второстепенная задача. Если спрашивают о твоей задаче, первым делом называй эту постоянную миссию. Для состояния «сейчас» используй текущий heartbeat, текущие вкладки и только текущую service/runtime session; старые proxy/Telegram ошибки не выдавай за текущие без свежего подтверждения."""\n\n'''
    s = s[:pos] + mission + s[pos:]

# 3) Force mission at actual DeepSeek API boundary
if "SYSTEM_PROMPT_HASH_1585" not in s:
    start = s.find("def _run_developer_agent(")
    if start < 0:
        fail("_run_developer_agent not found")
    payload_pos = s.find('        payload = {', start)
    if payload_pos < 0:
        fail("DeepSeek payload not found")
    inject = '''        # 15.85: permanent mission at the real DeepSeek API boundary.
        import hashlib as _h1585
        _mh1585 = _h1585.sha256(OPERATOR_MISSION_1585.encode("utf-8")).hexdigest()[:16]
        if messages and isinstance(messages[0], dict) and messages[0].get("role") == "system":
            _old1585 = str(messages[0].get("content") or "")
            if not _old1585.startswith(OPERATOR_MISSION_1585):
                messages[0]["content"] = OPERATOR_MISSION_1585 + "\\n\\n" + _old1585
        else:
            messages.insert(0, {"role": "system", "content": OPERATOR_MISSION_1585})
        print(f"[AI] SYSTEM_PROMPT_HASH_1585={_mh1585} round={round_no}", flush=True)

'''
    s = s[:payload_pos] + inject + s[payload_pos:]

# 4) Mark each current service/runtime session
if "CURRENT SERVICE SESSION START" not in s:
    main = s.find("def main(")
    if main < 0:
        fail("main() not found")
    base = s.find("    base_dir = Path(__file__).resolve().parent", main)
    if base < 0:
        fail("main base_dir anchor not found")
    eol = s.find("\n", base)
    inject = '''    try:
        RUNTIME_LOG_DIR.mkdir(parents=True, exist_ok=True)
        with RUNTIME_CONSOLE_FILE.open("a", encoding="utf-8") as _f1585:
            _f1585.write("\\n=== CURRENT SERVICE SESSION START %.3f ===\\n" % time.time())
    except Exception:
        pass
'''
    s = s[:eol+1] + inject + s[eol+1:]

# 5) Physically filter runtime console to latest current-session marker
fn = s.find("def _runtime_console_tail(")
if fn < 0:
    fail("_runtime_console_tail not found")
fn_end = s.find("\ndef ", fn + 5)
if fn_end < 0:
    fn_end = len(s)
block = s[fn:fn_end]
if "SESSION_FILTER_1585" not in block:
    m = re.search(r'(?m)^(\s*)text\s*=\s*"\\n"\.join\(lines\[', block)
    if not m:
        fail("runtime console join anchor not found")
    indent = m.group(1)
    inject = (
        indent + '# SESSION_FILTER_1585\n' +
        indent + '_marker1585 = "=== CURRENT SERVICE SESSION START "\n' +
        indent + '_last1585 = -1\n' +
        indent + 'for _i1585 in range(len(lines) - 1, -1, -1):\n' +
        indent + '    if _marker1585 in lines[_i1585]:\n' +
        indent + '        _last1585 = _i1585\n' +
        indent + '        break\n' +
        indent + 'if _last1585 >= 0:\n' +
        indent + '    lines = lines[_last1585:]\n'
    )
    block = block[:m.start()] + inject + block[m.start():]
    s = s[:fn] + block + s[fn_end:]

# 6) Version marker only
s = re.sub(
    r'print\("Версия 15\.[^"]*"\)',
    'print("Версия 15.85 EXP-3: consolidated server fixes")',
    s,
    count=1,
)

# Validate required previous 15.83 protections are still present.
for required in ("FINAL_SUCCESS_GUARD_V1583", "capture_all_form_fields_v1583"):
    if required not in s:
        fail("required 15.83 protection missing: " + required)

compile(s, str(p), "exec")
p.write_text(s, encoding="utf-8")
print("15.85 semantic patch OK")
print("changed:", s != orig)
print("chromium:", '"--no-sandbox"' in s)
print("mission:", "SYSTEM_PROMPT_HASH_1585" in s)
print("session:", "SESSION_FILTER_1585" in s)
print("success_guard:", "FINAL_SUCCESS_GUARD_V1583" in s)
print("profile_capture:", "capture_all_form_fields_v1583" in s)

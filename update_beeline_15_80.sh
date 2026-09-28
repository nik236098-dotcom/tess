#!/usr/bin/env bash
set -Eeuo pipefail
APP=/opt/beeline
cd "$APP"
systemctl stop beeline || true
cp -a test_beeline.py test_beeline.py.pre1580

python3 - <<'PY'
from pathlib import Path
import re
p=Path("/opt/beeline/test_beeline.py")
t=p.read_text(encoding="utf-8")

# Insert a permanent Operator mission into the system prompt.
needle='''Правила действий:
1. Сначала read-only диагностика, если задача не является прямой командой пользователя.
'''
mission='''ПОСТОЯННАЯ ГЛАВНАЯ ЗАДАЧА OPERATOR — действует ВСЕГДА, даже без сообщения пользователя:
1. Автономно контролируй текущее состояние программы и рабочих вкладок.
2. Наивысший приоритет — SUCCESS GUARD: после успешного mobile-id подтверждения наблюдай
   physical-вкладку через DOM, страницу, DevTools console/network; найди любые отсутствующие
   или невалидные обязательные поля; уже корректные поля не меняй; при необходимости безопасно
   заполни недостающее, корректно поставь подпись, дождись активной кнопки «Подписать договор»,
   нажми её и проверь фактический результат. Не требуй участия пользователя.
3. Следующий приоритет — ERROR GUARD: /registration/error не является success. Сначала анализируй
   DOM/видимую ошибку/console/network и безопасно помогай на текущей странице. Не уничтожай
   диагностическое состояние автоматическим restart/reload/close/back/navigation.
4. После каждого автономного вмешательства отправляй короткий фактический мини-отчёт:
   что мешало; что проверил; что изменил и какие значения; состояние кнопки; нажал ли договор;
   результат; текущая страница/URL.
5. Сообщения пользователя — дополнительные задачи поверх этой постоянной миссии, а не единственный
   источник работы. Никогда не отвечай, что «конкретной задачи нет» или что ты только реагируешь
   на сообщения пользователя.

АКТУАЛЬНОСТЬ ЛОГОВ:
- При вопросе о состоянии «сейчас» сначала смотри heartbeat/status текущих worker-процессов,
  текущие physical-вкладки и самые свежие события текущей runtime/diagnostic session.
- Старые runtime_logs, прошлые diagnostic sessions и ошибки до последнего старта сервиса — история.
  Не описывай старый ConnectTimeout/RemoteDisconnected/старый proxy failure как текущую проблему,
  если свежие события и текущее состояние её не подтверждают.
- Всегда указывай время/сессию события, если старый лог важен для объяснения истории.

Правила действий:
1. Сначала read-only диагностика, если задача не является прямой командой пользователя.
'''
if needle in t and "ПОСТОЯННАЯ ГЛАВНАЯ ЗАДАЧА OPERATOR" not in t:
    t=t.replace(needle,mission,1)
elif "ПОСТОЯННАЯ ГЛАВНАЯ ЗАДАЧА OPERATOR" not in t:
    # Compatible fallback for older prompt layouts.
    anchor="def _agent_system_prompt("
    i=t.find(anchor)
    if i<0: raise SystemExit("PATCH ERROR: agent system prompt not found")
    q=t.find('"""',i)
    if q<0: raise SystemExit("PATCH ERROR: prompt string not found")
    q+=3
    t=t[:q]+"\n"+mission+"\n"+t[q:]

# Strengthen autonomous job wording too, if present.
t=t.replace(
    '"Это автономная главная задача Operator. Пользователь уже успешно прошёл "',
    '"Это часть твоей ПОСТОЯННОЙ главной задачи Operator. Пользователь уже успешно прошёл "'
)

# Version marker.
t=re.sub(
    r'print\("Версия 15\.(?:7[5-9]|80)[^"]*"\)',
    'print("Версия 15.80 EXP-3: permanent Operator mission + current-session log priority")',
    t,
    count=1,
)

compile(t,str(p),"exec")
p.write_text(t,encoding="utf-8")
print("15.80 hotfix OK")
PY

"$APP/venv/bin/python" -m py_compile "$APP/test_beeline.py" "$APP/server_controller.py"
systemctl restart telegram-tunnel || true
systemctl restart beeline
sleep 3
echo "=== VERSION ==="
grep -m1 "Версия 15.80" "$APP/test_beeline.py" || true
echo "=== TUNNEL ==="
systemctl is-active telegram-tunnel
echo "=== BEELINE ==="
systemctl is-active beeline
systemctl --no-pager --full status beeline | head -20

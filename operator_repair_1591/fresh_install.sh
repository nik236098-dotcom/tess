#!/usr/bin/env bash
# Чистая установка beeline (линия 15.91, последняя ревизия из этого репозитория) на Ubuntu 22.04/24.04.
#
#   Новый сервер, одна команда (скрипт сам клонирует репозиторий):
#     curl -fsSL https://raw.githubusercontent.com/nik236098-dotcom/tess/codex/operator-observer-15.87/operator_repair_1591/fresh_install.sh | sudo bash
#
#   Переезд со старого сервера (конфиги, clients.txt, прогресс, результаты копируются по SSH):
#     curl -fsSL <тот же адрес> | sudo MIGRATE_FROM=root@СТАРЫЙ_IP:/opt/beeline bash
#
#   Без переезда конфиги создаются из переменных (или запрашиваются, если терминал интерактивный):
#     DEEPSEEK_API_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, TELEGRAM_PROXY (socks5h://логин:пароль@хост:порт)
#
# Что делает: системные пакеты и Xvfb, venv с Playwright/Chromium/numpy/OpenCV, код последней папки
# beeline_integrated_io_15_91_r*/ (test_beeline.py, server_controller.py, operator_runtime_io.py,
# symbol_matching.py) плюс local_matcher.py и PROJECT_RULES.md из корня репозитория, заготовки
# batch_support.py/console_wait.py, конфиги, проверка install.py (без apply), служба systemd, запуск.
#
# Служебные переменные: APP_DIR (/opt/beeline), BRANCH (codex/operator-observer-15.87), REPO_URL,
#   SKIP_APT=1, SKIP_VENV=1, NO_SERVICE=1, NO_START=1 (для тестов и повторных запусков).
set -Eeuo pipefail

APP_DIR="${APP_DIR:-/opt/beeline}"
BRANCH="${BRANCH:-codex/operator-observer-15.87}"
REPO_URL="${REPO_URL:-https://github.com/nik236098-dotcom/tess.git}"
SERVICE="beeline"
MIGRATE_FROM="${MIGRATE_FROM:-}"

say() { printf '\n== %s\n' "$*"; }
die() { printf 'ОШИБКА: %s\n' "$*" >&2; exit 1; }

if [[ $EUID -ne 0 && -z "${NO_SERVICE:-}" ]]; then
  die "запусти через sudo"
fi

# 1. Репозиторий: рядом со скриптом или свежий клон.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-/dev/null}")" 2>/dev/null && pwd || true)"
if [[ -n "$SCRIPT_DIR" && -f "$SCRIPT_DIR/fix_package_1591.py" ]]; then
  REPO="$(cd "$SCRIPT_DIR/.." && pwd)"
else
  say "Клонирую $REPO_URL ($BRANCH)"
  command -v git >/dev/null || { [[ -n "${SKIP_APT:-}" ]] && die "нужен git"; apt-get update -y && apt-get install -y git; }
  REPO="$(mktemp -d /tmp/beeline-repo.XXXXXX)"
  git clone -q --depth 1 -b "$BRANCH" "$REPO_URL" "$REPO"
fi
PACKAGE="$(ls -d "$REPO"/operator_repair_1591/beeline_integrated_io_15_91_r*/ 2>/dev/null \
  | sed -E 's#/$##' | sort -t r -k 3 -n | tail -1)"
[[ -n "$PACKAGE" && -f "$PACKAGE/install.py" ]] || die "в репозитории нет папки beeline_integrated_io_15_91_r*/"
REVISION="$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["revision"])' "$PACKAGE/manifest.json")"
say "Пакет: $(basename "$PACKAGE") (ревизия $REVISION)"

# 2. Системные пакеты (как в install_beeline_ubuntu.sh) + rsync/git.
if [[ -z "${SKIP_APT:-}" ]]; then
  say "Системные пакеты"
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -y
  ASOUND_PKG="libasound2"
  if apt-cache show libasound2t64 >/dev/null 2>&1; then ASOUND_PKG="libasound2t64"; fi
  apt-get install -y python3 python3-venv python3-pip unzip curl git rsync xvfb ca-certificates fonts-liberation \
    libnss3 libatk-bridge2.0-0 libgtk-3-0 libgbm1 "$ASOUND_PKG" libxss1 libxtst6 libx11-xcb1 libdrm2 \
    libxcomposite1 libxdamage1 libxrandr2 libxfixes3 libglib2.0-0 libgl1
fi

mkdir -p "$APP_DIR"

# 3. Переезд: всё, кроме venv и кэшей; код ниже всё равно заменяется версией из пакета.
if [[ -n "$MIGRATE_FROM" ]]; then
  say "Копирую данные из $MIGRATE_FROM"
  command -v rsync >/dev/null || die "нужен rsync"
  rsync -a --info=progress2 --exclude venv --exclude __pycache__ --exclude last_match \
    "${MIGRATE_FROM%/}/" "$APP_DIR/"
fi

# 4. Код последней ревизии.
say "Код"
for name in test_beeline.py server_controller.py operator_runtime_io.py symbol_matching.py; do
  install -m 0644 "$PACKAGE/$name" "$APP_DIR/$name"
done
install -m 0644 "$REPO/local_matcher.py" "$APP_DIR/local_matcher.py"
[[ -f "$APP_DIR/PROJECT_RULES.md" ]] || install -m 0644 "$REPO/PROJECT_RULES.md" "$APP_DIR/PROJECT_RULES.md"
if [[ ! -f "$APP_DIR/console_wait.py" ]]; then
cat > "$APP_DIR/console_wait.py" <<'PY'
def console_input(prompt=""):
    return input(prompt)
PY
fi
if [[ ! -f "$APP_DIR/batch_support.py" ]]; then
cat > "$APP_DIR/batch_support.py" <<'PY'
from pathlib import Path
import json, re, time

def _split_client_line(line):
    raw=line.strip()
    if not raw or raw.startswith("#"): return None
    for sep in ("\t","|",";",","):
        if sep in raw:
            a,b=raw.split(sep,1); return a.strip(),b.strip()
    parts=raw.split(maxsplit=1)
    return parts[0].strip(), parts[1].strip() if len(parts)>1 else ""

def load_clients(path):
    path=Path(path)
    if not path.exists(): raise OSError(f"{path.name} не найден")
    rows=[]
    for n,line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(),1):
        p=_split_client_line(line)
        if p is None: continue
        active,second=p
        digits=re.sub(r"\D","",active)
        if len(digits)==10: digits="7"+digits
        if len(digits)!=11: raise ValueError(f"Строка {n}: в первом поле нужен номер из 10/11 цифр")
        rows.append((n,digits,second))
    return rows

def wait_confirmation(page,timeout=65):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        try:
            if page.is_closed(): return "CLOSED"
            if "mobile-id-auth" in str(page.url).lower(): return "AUTH"
            page.wait_for_timeout(250)
        except Exception: time.sleep(.25)
    return "TIMEOUT"

def save_result(path,line_number,active_digits,status,page=None):
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    url=""
    try:
        if page is not None and not page.is_closed(): url=page.url
    except Exception: pass
    with path.open("a",encoding="utf-8") as f:
        f.write(json.dumps({"time":time.strftime("%Y-%m-%d %H:%M:%S"),"row":line_number,"active_digits":str(active_digits),"status":str(status),"url":url},ensure_ascii=False)+"\n")
PY
fi

# 5. Конфиги: из переезда, из переменных или с клавиатуры.
ask() {  # ask VAR "подсказка" [secret]
  local var="$1" prompt="$2" secret="${3:-}"
  if [[ -z "${!var:-}" ]]; then
    if [[ -t 0 ]]; then
      if [[ -n "$secret" ]]; then read -r -s -p "$prompt: " "$var"; echo; else read -r -p "$prompt: " "$var"; fi
    else
      die "нет $var: задай переменную окружения или укажи MIGRATE_FROM"
    fi
  fi
}
if [[ ! -f "$APP_DIR/deepseek_config.json" ]]; then
  ask DEEPSEEK_API_KEY "DeepSeek API key" secret
  python3 - "$APP_DIR/deepseek_config.json" "$DEEPSEEK_API_KEY" <<'PY'
import json,sys
with open(sys.argv[1],"w",encoding="utf-8") as f: json.dump({"api_key":sys.argv[2],"model":"deepseek-flash"},f,ensure_ascii=False,indent=2)
PY
fi
if [[ ! -f "$APP_DIR/telegram_config.json" ]]; then
  ask TELEGRAM_BOT_TOKEN "Telegram bot token" secret
  ask TELEGRAM_CHAT_ID "Telegram chat_id"
  ask TELEGRAM_PROXY "Прокси для Telegram (socks5h://логин:пароль@хост:порт)"
  python3 - "$APP_DIR/telegram_config.json" "$TELEGRAM_BOT_TOKEN" "$TELEGRAM_CHAT_ID" "$TELEGRAM_PROXY" <<'PY'
import json,sys
with open(sys.argv[1],"w",encoding="utf-8") as f: json.dump({"token":sys.argv[2],"chat_id":sys.argv[3],"proxy":sys.argv[4]},f,ensure_ascii=False,indent=2)
PY
fi
chmod 600 "$APP_DIR/deepseek_config.json" "$APP_DIR/telegram_config.json"
touch "$APP_DIR/clients.txt"

# 6. Python и Chromium.
PY="$APP_DIR/venv/bin/python"
if [[ -z "${SKIP_VENV:-}" ]]; then
  say "Python/Chromium"
  [[ -x "$PY" ]] || python3 -m venv "$APP_DIR/venv"
  "$PY" -m pip install --upgrade pip wheel setuptools
  "$APP_DIR/venv/bin/pip" install playwright "requests[socks]" numpy opencv-python-headless
  "$PY" -m playwright install --with-deps chromium
else
  PY="$(command -v python3)"
fi

# 7. Проверка: компиляция, маркеры, штатный preflight установщика пакета.
say "Проверка"
"$PY" -m py_compile "$APP_DIR"/test_beeline.py "$APP_DIR"/server_controller.py "$APP_DIR"/local_matcher.py \
  "$APP_DIR"/symbol_matching.py "$APP_DIR"/operator_runtime_io.py "$APP_DIR"/batch_support.py "$APP_DIR"/console_wait.py
grep -q MATCHER_SPEED_1591R10 "$APP_DIR/symbol_matching.py" || die "symbol_matching.py без маркера ревизии 10"
grep -q MATCHER_HEARTBEAT_1591R9 "$APP_DIR/test_beeline.py" || die "test_beeline.py без маркера ревизии 9"
find "$APP_DIR" -name __pycache__ -type d -prune -exec rm -rf {} +
( cd "$PACKAGE" && python3 install.py --app "$APP_DIR" ) | tail -3

# 8. Служба.
if [[ -z "${NO_SERVICE:-}" ]]; then
  say "systemd"
  cat > /etc/systemd/system/${SERVICE}.service <<EOF
[Unit]
Description=Beeline Telegram Controller + Automation (15.91 r${REVISION})
After=network-online.target
Wants=network-online.target
[Service]
Type=simple
WorkingDirectory=${APP_DIR}
ExecStart=${APP_DIR}/venv/bin/python ${APP_DIR}/server_controller.py
Restart=always
RestartSec=3
TimeoutStopSec=25
KillMode=control-group
Environment=PYTHONUNBUFFERED=1
[Install]
WantedBy=multi-user.target
EOF
  systemctl daemon-reload
  systemctl enable "$SERVICE"
  if [[ -z "${NO_START:-}" ]]; then
    systemctl restart "$SERVICE"
    sleep 3
    systemctl --no-pager --full status "$SERVICE" | head -12 || true
  fi
fi

say "ГОТОВО: $APP_DIR, ревизия $REVISION"
echo "Журнал: sudo journalctl -u $SERVICE -f -o short-iso"
echo "Обновления: git clone -b $BRANCH $REPO_URL ~/tess; затем install.py из последней папки beeline_integrated_io_15_91_r*/"

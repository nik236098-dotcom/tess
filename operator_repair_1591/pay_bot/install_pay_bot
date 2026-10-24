#!/usr/bin/env bash
# Установка бота оплаты eSIM (pay_bot) одной командой на Ubuntu 22.04/24.04.
#
#   curl -fsSL https://raw.githubusercontent.com/nik236098-dotcom/tess/codex/operator-observer-15.87/operator_repair_1591/pay_bot/install_pay_bot | sudo bash
#
# ОТДЕЛЬНЫЙ бот — у него должен быть СВОЙ токен (другой бот от @BotFather), не токен beeline (иначе 409).
# Спросит: токен этого бота, chat_id, прокси для Telegram (как у beeline), опционально прокси для страниц оплаты.
# Переменные окружения: TOKEN, CHAT_ID, PROXY, BROWSER_PROXY, SKIP_APT=1, NO_SERVICE=1.
set -Eeuo pipefail
export HOME="${HOME:-/root}"

APP_DIR="${APP_DIR:-/opt/pay_bot}"
BRANCH="${BRANCH:-codex/operator-observer-15.87}"
RAW="https://raw.githubusercontent.com/nik236098-dotcom/tess/${BRANCH}/operator_repair_1591/pay_bot/pay_bot.py"
SERVICE="pay_bot"
BEELINE_VENV="/opt/beeline/venv"
PW_PATH="${PLAYWRIGHT_BROWSERS_PATH:-/opt/pw-browsers}"

say() { printf '\n== %s\n' "$*"; }
die() { printf 'ОШИБКА: %s\n' "$*" >&2; exit 1; }
[[ $EUID -eq 0 || -n "${NO_SERVICE:-}" ]] || die "запусти через sudo"

# ввод с терминала даже при `curl | sudo bash`
_tty_ok() { { true < /dev/tty; } 2>/dev/null; }
ask() {  # ask VAR "подсказка" [secret] [default]
  local var="$1" prompt="$2" secret="${3:-}" def="${4:-}"
  [[ -n "${!var:-}" ]] && return 0
  local shown="$prompt"; [[ -n "$def" ]] && shown="$prompt [Enter = $def]"
  if _tty_ok; then
    printf '%s: ' "$shown" > /dev/tty
    if [[ -n "$secret" ]]; then read -r -s "$var" < /dev/tty; printf '\n' > /dev/tty; else read -r "$var" < /dev/tty; fi
  elif [[ -t 0 ]]; then
    if [[ -n "$secret" ]]; then read -r -s -p "$shown: " "$var"; echo; else read -r -p "$shown: " "$var"; fi
  fi
  [[ -n "${!var:-}" ]] || printf -v "$var" '%s' "$def"
}

mkdir -p "$APP_DIR"

# 1. Код бота.
say "Код бота"
command -v curl >/dev/null || { [[ -n "${SKIP_APT:-}" ]] || { apt-get update -y && apt-get install -y curl; }; }
curl -fsSL "$RAW" -o "$APP_DIR/pay_bot.py" || die "не скачался pay_bot.py (сеть/прокси?)"
python3 -c "import ast,sys; ast.parse(open(sys.argv[1]).read())" "$APP_DIR/pay_bot.py" || die "pay_bot.py не разобрался"

# 2. Конфиг.
if [[ ! -f "$APP_DIR/pay_bot_config.json" ]]; then
  say "Настройка — ВТОРОЙ бот, свой токен от @BotFather (не токен beeline!)"
  ask TOKEN "Токен этого (платёжного) бота" secret
  [[ -n "${TOKEN:-}" ]] || die "нужен токен"
  ask CHAT_ID "Твой chat_id (куда бот пишет)"
  [[ -n "${CHAT_ID:-}" ]] || die "нужен chat_id"
  ask PROXY "Прокси для Telegram (socks5h://логин:пароль@хост:порт, или direct)" "" "direct"
  ask BROWSER_PROXY "Прокси для страниц оплаты (Enter — без прокси)" "" ""
  python3 - "$APP_DIR/pay_bot_config.json" "$TOKEN" "$CHAT_ID" "$PROXY" "$BROWSER_PROXY" <<'PY'
import json, sys
path, token, chat, proxy, bproxy = sys.argv[1:6]
cfg = {"token": token, "chat_id": chat, "proxy": proxy or "direct",
       "headless": True, "code_wait_seconds": 300, "page_wait_seconds": 240, "beeline_retry_max": 3}
if bproxy.strip():
    cfg["browser_proxy"] = bproxy.strip()
json.dump(cfg, open(path, "w"), ensure_ascii=False, indent=2)
PY
fi
chmod 600 "$APP_DIR/pay_bot_config.json"

# 3. Python/Chromium. Если на сервере есть beeline с playwright — переиспользуем его venv (быстро,
#    браузер уже скачан). Иначе ставим свой venv + playwright + chromium.
say "Python/Chromium"
if [[ -x "$BEELINE_VENV/bin/python" ]] && "$BEELINE_VENV/bin/python" -c "import playwright" 2>/dev/null; then
  PY="$BEELINE_VENV/bin/python"
  say "Использую venv beeline ($PY). Доустанавливаю Chromium (в т.ч. headless-shell для headless-режима)…"
  # beeline гоняет Chromium под xvfb (не headless), и headless-shell может отсутствовать — pay_bot
  # запускается headless, поэтому обязательно докачиваем. Уже скачанное не тянется повторно.
  PLAYWRIGHT_BROWSERS_PATH="$PW_PATH" timeout 900 "$PY" -m playwright install chromium \
    || say "⚠️ playwright install chromium не прошёл. Если бот не стартует — запусти вручную: sudo PLAYWRIGHT_BROWSERS_PATH=$PW_PATH $PY -m playwright install chromium"
else
  PY="$APP_DIR/venv/bin/python"
  [[ -x "$PY" ]] || python3 -m venv "$APP_DIR/venv"
  if [[ -z "${SKIP_APT:-}" ]]; then
    export DEBIAN_FRONTEND=noninteractive
    printf 'Acquire::Retries "5";\nDPkg::Lock::Timeout "600";\n' > /etc/apt/apt.conf.d/80-paybot-retries
    apt-get update -y && timeout 600 apt-get install -y python3 python3-venv python3-pip xvfb ca-certificates || die "apt не поставил python3"
  fi
  n=0; until timeout 300 "$APP_DIR/venv/bin/pip" install --default-timeout=30 --retries=5 "requests[socks]" playwright; do
    n=$((n+1)); [[ $n -ge 3 ]] && die "pip не поставил зависимости"; say "pip повтор $n"; sleep 3
  done
  export PLAYWRIGHT_BROWSERS_PATH="$PW_PATH"
  n=0; until timeout 900 "$APP_DIR/venv/bin/python" -m playwright install --with-deps chromium; do
    n=$((n+1)); [[ $n -ge 3 ]] && { say "chromium с --with-deps не встал, пробую без deps"; timeout 900 "$APP_DIR/venv/bin/python" -m playwright install chromium || die "chromium не поставился"; break; }
    say "playwright install повтор $n"; sleep 3
  done
fi

# 4. Служба.
if [[ -z "${NO_SERVICE:-}" ]]; then
  say "systemd"
  cat > /etc/systemd/system/${SERVICE}.service <<EOF
[Unit]
Description=Beeline eSIM pay bot (semi-auto)
After=network-online.target
Wants=network-online.target
[Service]
WorkingDirectory=${APP_DIR}
Environment=PLAYWRIGHT_BROWSERS_PATH=${PW_PATH}
Environment=PYTHONUNBUFFERED=1
ExecStart=${PY} ${APP_DIR}/pay_bot.py
Restart=always
RestartSec=5
[Install]
WantedBy=multi-user.target
EOF
  systemctl daemon-reload
  systemctl enable "$SERVICE" >/dev/null 2>&1 || true
  systemctl restart "$SERVICE"
  sleep 3
  systemctl is-active "$SERVICE" >/dev/null 2>&1 && STATE="active" || STATE="$(systemctl is-active "$SERVICE" 2>/dev/null || true)"
  say "Служба $SERVICE: $STATE"
fi

say "ГОТОВО: $APP_DIR"
echo "Журнал: sudo journalctl -u $SERVICE -f -o cat"
echo "Напиши боту /start, потом пришли ссылки заказа и карту «НОМЕР СРОК КОД»."

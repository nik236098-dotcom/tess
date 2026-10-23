#!/usr/bin/env bash
# Установка чат-бота (счётчик QR + DeepSeek + модерация) одной командой на Ubuntu 22.04/24.04.
#
#   curl -fsSL https://raw.githubusercontent.com/nik236098-dotcom/tess/codex/operator-observer-15.87/operator_repair_1591/chat_bot/install_chat_bot | sudo bash
#
# Полностью автономный бот (с beeline не связан). Спросит: токен бота, ключ DeepSeek, прокси.
# Служебные переменные: TOKEN, DEEPSEEK_API_KEY, PROXY, TRIGGERS, TZ_OFFSET, SKIP_APT=1, NO_SERVICE=1.
set -Eeuo pipefail
export HOME="${HOME:-/root}"

APP_DIR="${APP_DIR:-/opt/chat_bot}"
BRANCH="${BRANCH:-codex/operator-observer-15.87}"
RAW="https://raw.githubusercontent.com/nik236098-dotcom/tess/${BRANCH}/operator_repair_1591/chat_bot/chat_bot.py"
SERVICE="chat_bot"

say() { printf '\n== %s\n' "$*"; }
die() { printf 'ОШИБКА: %s\n' "$*" >&2; exit 1; }
[[ $EUID -eq 0 || -n "${NO_SERVICE:-}" ]] || die "запусти через sudo"

# ввод с терминала даже при `curl | sudo bash`
_tty_ok() { { true < /dev/tty; } 2>/dev/null; }
ask() {  # ask VAR "подсказка" [secret] [default]
  local var="$1" prompt="$2" secret="${3:-}" def="${4:-}"
  [[ -n "${!var:-}" ]] && return 0
  local shown="$prompt"; [[ -n "$def" ]] && shown="$prompt [Enter = оставить текущее]"
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
curl -fsSL "$RAW" -o "$APP_DIR/chat_bot.py" || die "не скачался chat_bot.py (сеть/прокси?)"
python3 -c "import ast,sys; ast.parse(open(sys.argv[1]).read())" "$APP_DIR/chat_bot.py" || die "chat_bot.py не разобрался"

# 2. Конфиг. Бот полностью автономный — спрашиваем всё сам, ни с чем не связан.
if [[ ! -f "$APP_DIR/config.json" ]]; then
  say "Настройка"
  ask TOKEN "Токен бота (@BotFather)" secret
  [[ -n "${TOKEN:-}" ]] || die "нужен токен бота"
  ask DEEPSEEK_API_KEY "Ключ DeepSeek" secret
  [[ -n "${DEEPSEEK_API_KEY:-}" ]] || die "нужен ключ DeepSeek"
  ask PROXY "Прокси для Telegram (socks5h://логин:пароль@хост:порт или direct)" "" "direct"
  TRIGGERS="${TRIGGERS:-дипсик, deepseek, дип}"
  TZ_OFFSET="${TZ_OFFSET:-3}"
  python3 - "$APP_DIR/config.json" "$TOKEN" "$DEEPSEEK_API_KEY" "$PROXY" "$TRIGGERS" "$TZ_OFFSET" <<'PY'
import json, sys
path, token, key, proxy, triggers, tz = sys.argv[1:7]
trig = [w.strip() for w in triggers.replace(";", ",").split(",") if w.strip()]
json.dump({"token": token, "proxy": proxy or "direct", "deepseek_api_key": key,
           "deepseek_model": "deepseek-flash", "deepseek_url": "https://api.deepseek.com/chat/completions",
           "ds_proxy": "direct", "triggers": trig or ["дипсик", "deepseek", "дип"],
           "tz_offset_hours": float(tz or 3)},
          open(path, "w"), ensure_ascii=False, indent=2)
PY
fi
chmod 600 "$APP_DIR/config.json"

# 3. Python и requests[socks].
if [[ -z "${SKIP_APT:-}" ]]; then
  say "Системные пакеты"
  export DEBIAN_FRONTEND=noninteractive
  printf 'Acquire::Retries "5";\nDPkg::Lock::Timeout "600";\n' > /etc/apt/apt.conf.d/80-chatbot-retries
  apt-get update -y && timeout 600 apt-get install -y python3 python3-venv python3-pip ca-certificates || die "apt не поставил python3"
fi
say "Python"
PY="$APP_DIR/venv/bin/python"
[[ -x "$PY" ]] || python3 -m venv "$APP_DIR/venv"
n=0; until timeout 300 "$APP_DIR/venv/bin/pip" install --default-timeout=30 --retries=5 "requests[socks]"; do
  n=$((n+1)); [[ $n -ge 3 ]] && die "pip не поставил requests"; say "pip повтор $n"; sleep 3
done

# 4. Служба.
if [[ -z "${NO_SERVICE:-}" ]]; then
  say "systemd"
  cat > /etc/systemd/system/${SERVICE}.service <<EOF
[Unit]
Description=Chat bot (QR counter + DeepSeek + moderation)
After=network-online.target
Wants=network-online.target
[Service]
WorkingDirectory=${APP_DIR}
ExecStart=${PY} ${APP_DIR}/chat_bot.py
Restart=always
RestartSec=3
Environment=PYTHONUNBUFFERED=1
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
echo "Журнал: sudo journalctl -u $SERVICE -f -o short-iso"
echo "Не забудь: бота — в чат АДМИНОМ (право «Удаление сообщений»), и у @BotFather /setprivacy → Disable."

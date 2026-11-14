#!/usr/bin/env bash
# Установка панели оплат (pay_panel) одной командой на Ubuntu 22.04/24.04.
#
#   curl -fsSL https://raw.githubusercontent.com/nik236098-dotcom/tess/codex/operator-observer-15.87/operator_repair_1591/pay_panel/install_pay_panel | sudo bash
#
# Многопользовательский бот (админ + оплатчики). Отдельный токен. Спросит: токен, твой Telegram ID,
# контакт поддержки, прокси для Telegram, ключ DeepSeek. Тянет pay_panel.py и pay_bot.py (движок оплаты).
# Переменные: TOKEN, ADMIN_ID, ADMIN_CONTACT, PROXY, DEEPSEEK_API_KEY, BROWSER_PROXY, SKIP_APT=1, NO_SERVICE=1.
set -Eeuo pipefail
export HOME="${HOME:-/root}"

APP_DIR="${APP_DIR:-/opt/pay_panel}"
BRANCH="${BRANCH:-codex/operator-observer-15.87}"
RAW="https://raw.githubusercontent.com/nik236098-dotcom/tess/${BRANCH}/operator_repair_1591"
SERVICE="pay_panel"
BEELINE_VENV="/opt/beeline/venv"
PW_PATH="${PLAYWRIGHT_BROWSERS_PATH:-/opt/pw-browsers}"

say() { printf '\n== %s\n' "$*"; }
die() { printf 'ОШИБКА: %s\n' "$*" >&2; exit 1; }
[[ $EUID -eq 0 || -n "${NO_SERVICE:-}" ]] || die "запусти через sudo"

_tty_ok() { { true < /dev/tty; } 2>/dev/null; }
ask() {
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

# 1. Код панели + движок оплаты.
say "Код"
command -v curl >/dev/null || { [[ -n "${SKIP_APT:-}" ]] || { apt-get update -y && apt-get install -y curl; }; }
curl -fsSL "$RAW/pay_panel/pay_panel.py" -o "$APP_DIR/pay_panel.py" || die "не скачался pay_panel.py"
curl -fsSL "$RAW/pay_bot/pay_bot.py"     -o "$APP_DIR/pay_bot.py"   || die "не скачался pay_bot.py (движок)"
python3 -c "import ast,sys; [ast.parse(open(p).read()) for p in sys.argv[1:]]" "$APP_DIR/pay_panel.py" "$APP_DIR/pay_bot.py" || die "код не разобрался"

# 2. Конфиг.
if [[ ! -f "$APP_DIR/pay_panel_config.json" ]]; then
  say "Настройка"
  ask TOKEN "Токен бота-панели (@BotFather)" secret
  [[ -n "${TOKEN:-}" ]] || die "нужен токен"
  ask ADMIN_ID "Твой Telegram ID (числом; узнать: @userinfobot)"
  [[ "${ADMIN_ID:-}" =~ ^[0-9]+$ ]] || die "ADMIN_ID должен быть числом"
  ask ADMIN_CONTACT "Контакт поддержки" "" "@gennadiy_cc"
  ask PROXY "Прокси для Telegram (socks5h://логин:пароль@хост:порт или direct)" "" "direct"
  ask DEEPSEEK_API_KEY "Ключ DeepSeek (для ИИ-агента; можно пусто пока)" secret
  BROWSER_PROXY="${BROWSER_PROXY:-}"
  python3 - "$APP_DIR/pay_panel_config.json" "$TOKEN" "$ADMIN_ID" "$ADMIN_CONTACT" "$PROXY" "${DEEPSEEK_API_KEY:-}" "$BROWSER_PROXY" <<'PY'
import json, sys
path, token, admin, contact, proxy, dskey, bproxy = sys.argv[1:8]
cfg = {"token": token, "admin_id": int(admin), "admin_contact": contact or "@gennadiy_cc",
       "proxy": proxy or "direct", "browser_proxy": bproxy.strip(),
       "deepseek_api_key": dskey, "deepseek_model": "deepseek-chat",
       "default_rate_usd": 4.5, "tariff_rub": 300,
       "idle_timeout_s": 180, "newcard_timeout_s": 300, "per_payment_watchdog_s": 600}
json.dump(cfg, open(path, "w"), ensure_ascii=False, indent=2)
PY
fi
chmod 600 "$APP_DIR/pay_panel_config.json"

# 3. Python/Chromium (переиспользуем venv beeline, иначе свой + playwright + chromium).
say "Python/Chromium"
if [[ -x "$BEELINE_VENV/bin/python" ]] && "$BEELINE_VENV/bin/python" -c "import playwright" 2>/dev/null; then
  PY="$BEELINE_VENV/bin/python"
  say "Использую venv beeline ($PY). Доустанавливаю Chromium (headless-shell)…"
  PLAYWRIGHT_BROWSERS_PATH="$PW_PATH" timeout 900 "$PY" -m playwright install chromium \
    || say "⚠️ playwright install chromium не прошёл — для движка оплаты запусти вручную позже."
else
  PY="$APP_DIR/venv/bin/python"
  [[ -x "$PY" ]] || python3 -m venv "$APP_DIR/venv"
  if [[ -z "${SKIP_APT:-}" ]]; then
    export DEBIAN_FRONTEND=noninteractive
    printf 'Acquire::Retries "5";\nDPkg::Lock::Timeout "600";\n' > /etc/apt/apt.conf.d/80-paypanel-retries
    apt-get update -y && timeout 600 apt-get install -y python3 python3-venv python3-pip xvfb ca-certificates || die "apt не поставил python3"
  fi
  n=0; until timeout 300 "$APP_DIR/venv/bin/pip" install --default-timeout=30 --retries=5 "requests[socks]" playwright; do
    n=$((n+1)); [[ $n -ge 3 ]] && die "pip не поставил зависимости"; say "pip повтор $n"; sleep 3
  done
  export PLAYWRIGHT_BROWSERS_PATH="$PW_PATH"
  timeout 900 "$APP_DIR/venv/bin/python" -m playwright install --with-deps chromium \
    || timeout 900 "$APP_DIR/venv/bin/python" -m playwright install chromium || say "⚠️ chromium не доустановился"
fi

# 4. Служба.
if [[ -z "${NO_SERVICE:-}" ]]; then
  say "systemd"
  cat > /etc/systemd/system/${SERVICE}.service <<EOF
[Unit]
Description=eSIM payment panel (admin + operators)
After=network-online.target
Wants=network-online.target
[Service]
WorkingDirectory=${APP_DIR}
Environment=PLAYWRIGHT_BROWSERS_PATH=${PW_PATH}
Environment=PYTHONUNBUFFERED=1
ExecStart=${PY} ${APP_DIR}/pay_panel.py
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
echo "Напиши боту /start с админского аккаунта — увидишь панель админа."

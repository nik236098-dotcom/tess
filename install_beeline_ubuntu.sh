#!/usr/bin/env bash
set -Eeuo pipefail

APP_DIR="/opt/beeline"
SERVICE="beeline"
BRANCH="codex/beeline-15.74-exp3"
RAW="https://raw.githubusercontent.com/nik236098-dotcom/tess/${BRANCH}"
BUNDLE_URL="${RAW}/beeline_server_bundle_15_74.zip"
CONTROLLER_URL="${RAW}/server_controller.py"
PATCH_URL="${RAW}/patch_15_75.py"

if [[ $EUID -ne 0 ]]; then
  echo "Запусти через sudo."
  exit 1
fi

export DEBIAN_FRONTEND=noninteractive

echo "[1/8] Системные пакеты..."
apt-get update -y
apt-get install -y   python3 python3-venv python3-pip unzip curl xvfb   ca-certificates fonts-liberation libnss3 libatk-bridge2.0-0   libgtk-3-0 libgbm1 libasound2t64 libxss1 libxtst6 libx11-xcb1   libdrm2 libxcomposite1 libxdamage1 libxrandr2 libxfixes3   libglib2.0-0 libgl1

echo "[2/8] Код 15.75..."
mkdir -p "$APP_DIR"

TMP_ZIP="$(mktemp --suffix=.zip)"
curl -fL --retry 5 --retry-delay 2 "$BUNDLE_URL" -o "$TMP_ZIP"
unzip -oq "$TMP_ZIP" -d "$APP_DIR"
rm -f "$TMP_ZIP"

curl -fL --retry 5 --retry-delay 2 "$CONTROLLER_URL" -o "$APP_DIR/server_controller.py"
curl -fL --retry 5 --retry-delay 2 "$PATCH_URL" -o "$APP_DIR/patch_15_75.py"
python3 "$APP_DIR/patch_15_75.py"

echo "[3/8] Python/Chromium..."
if [[ ! -x "$APP_DIR/venv/bin/python" ]]; then
  python3 -m venv "$APP_DIR/venv"
fi

"$APP_DIR/venv/bin/python" -m pip install --upgrade pip wheel setuptools
"$APP_DIR/venv/bin/pip" install   playwright   "requests[socks]"   numpy   opencv-python-headless
"$APP_DIR/venv/bin/python" -m playwright install --with-deps chromium

echo "[4/8] DeepSeek..."
if [[ ! -f "$APP_DIR/deepseek_config.json" ]]; then
  if [[ -z "${DEEPSEEK_API_KEY:-}" ]]; then
    read -r -s -p "DeepSeek API key: " DEEPSEEK_API_KEY
    echo
  fi
  python3 - "$APP_DIR/deepseek_config.json" "${DEEPSEEK_API_KEY:-}" <<'PY'
import json, sys
with open(sys.argv[1], "w", encoding="utf-8") as f:
    json.dump(
        {"api_key": sys.argv[2], "model": "deepseek-flash"},
        f, ensure_ascii=False, indent=2
    )
PY
  chmod 600 "$APP_DIR/deepseek_config.json"
fi

echo "[5/8] Telegram..."
if [[ ! -f "$APP_DIR/telegram_config.json" ]]; then
  if [[ -z "${TELEGRAM_BOT_TOKEN:-}" ]]; then
    read -r -s -p "Telegram bot token: " TELEGRAM_BOT_TOKEN
    echo
  fi
  if [[ -z "${TELEGRAM_CHAT_ID:-}" ]]; then
    read -r -p "Telegram chat_id: " TELEGRAM_CHAT_ID
  fi
  python3 - "$APP_DIR/telegram_config.json" "${TELEGRAM_BOT_TOKEN:-}" "${TELEGRAM_CHAT_ID:-}" <<'PY'
import json, sys
with open(sys.argv[1], "w", encoding="utf-8") as f:
    json.dump(
        {"token": sys.argv[2], "chat_id": sys.argv[3], "proxy": ""},
        f, ensure_ascii=False, indent=2
    )
PY
  chmod 600 "$APP_DIR/telegram_config.json"
fi

touch "$APP_DIR/clients.txt"

echo "[6/8] Проверка..."
"$APP_DIR/venv/bin/python" -m py_compile   "$APP_DIR/test_beeline.py"   "$APP_DIR/server_controller.py"   "$APP_DIR/local_matcher.py"   "$APP_DIR/symbol_matching.py"   "$APP_DIR/batch_support.py"   "$APP_DIR/console_wait.py"

echo "[7/8] systemd..."
cat > /etc/systemd/system/${SERVICE}.service <<'EOF'
[Unit]
Description=Beeline Telegram Controller + Automation 15.75
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=/opt/beeline
ExecStart=/opt/beeline/venv/bin/python /opt/beeline/server_controller.py
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

echo "[8/8] Запуск..."
systemctl restart "$SERVICE"
sleep 2
systemctl --no-pager --full status "$SERVICE" || true

echo
echo "ГОТОВО."
echo "Открой Telegram-бота — там будет меню:"
echo "  ▶️ Запустить"
echo "  ⏹ Остановить"
echo "  🔄 Перезапуск"
echo "  📥 Загрузить новую базу номеров"
echo
echo "Команды меню не передаются DeepSeek."
echo "Логи: journalctl -u beeline -f"

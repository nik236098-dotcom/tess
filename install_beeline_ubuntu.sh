#!/usr/bin/env bash
set -Eeuo pipefail

APP_DIR="/opt/beeline"
SERVICE="beeline"
BRANCH="codex/beeline-15.74-exp3"
ZIP_NAME="beeline_15_74_exp_3tabs_unlimited_ai_github.zip"
ZIP_URL="https://raw.githubusercontent.com/nik236098-dotcom/tess/${BRANCH}/${ZIP_NAME}"

if [[ $EUID -ne 0 ]]; then
  echo "Запусти команду через sudo."
  exit 1
fi

export DEBIAN_FRONTEND=noninteractive

echo "[1/7] Системные пакеты..."
apt-get update -y
apt-get install -y python3 python3-venv python3-pip unzip curl xvfb ca-certificates nano

echo "[2/7] Скачиваю проект..."
mkdir -p "$APP_DIR"
TMP_ZIP="$(mktemp --suffix=.zip)"
curl -fL --retry 5 --retry-delay 2 "$ZIP_URL" -o "$TMP_ZIP"
unzip -oq "$TMP_ZIP" -d "$APP_DIR"
rm -f "$TMP_ZIP"

cat > "$APP_DIR/console_wait.py" <<'PY'
def console_input(prompt=""):
    return input(prompt)
PY

cat > "$APP_DIR/batch_support.py" <<'PY'
from pathlib import Path
import json
import re
import time

def _split_client_line(line):
    raw = line.strip()
    if not raw or raw.startswith("#"):
        return None
    for sep in ("\t", "|", ";", ","):
        if sep in raw:
            left, right = raw.split(sep, 1)
            return left.strip(), right.strip()
    parts = raw.split(maxsplit=1)
    if len(parts) == 1:
        return parts[0].strip(), ""
    return parts[0].strip(), parts[1].strip()

def load_clients(path):
    path = Path(path)
    if not path.exists():
        raise OSError(f"{path.name} не найден")
    rows = []
    for row_no, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        parsed = _split_client_line(line)
        if parsed is None:
            continue
        active, second = parsed
        digits = re.sub(r"\D", "", active)
        if len(digits) == 10:
            digits = "7" + digits
        if len(digits) != 11:
            raise ValueError(f"Строка {row_no}: в первом поле нужен номер из 10/11 цифр")
        rows.append((row_no, digits, second))
    return rows

def wait_confirmation(page, timeout=65):
    deadline = time.monotonic() + timeout
    try:
        start_url = page.url
    except Exception:
        start_url = ""
    while time.monotonic() < deadline:
        try:
            if page.is_closed():
                return "CLOSED"
            url = page.url
            low = str(url).lower()
            if "mobile-id-auth" in low:
                return "AUTH"
            if url != start_url and "registration" in low:
                return "NAVIGATED"
            page.wait_for_timeout(250)
        except Exception:
            time.sleep(0.25)
    return "TIMEOUT"

def save_result(path, line_number, active_digits, status, page=None):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    url = ""
    try:
        if page is not None and not page.is_closed():
            url = page.url
    except Exception:
        pass
    rec = {
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "row": line_number,
        "active_digits": str(active_digits),
        "status": str(status),
        "url": url,
    }
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
PY

echo "[3/7] Python + Chromium..."
python3 -m venv "$APP_DIR/venv"
"$APP_DIR/venv/bin/python" -m pip install --upgrade pip wheel setuptools
"$APP_DIR/venv/bin/pip" install playwright "requests[socks]" numpy opencv-python-headless
"$APP_DIR/venv/bin/python" -m playwright install --with-deps chromium

echo "[4/7] Конфиги..."
if [[ ! -s "$APP_DIR/deepseek_config.json" ]]; then
  if [[ -z "${DEEPSEEK_API_KEY:-}" ]]; then
    read -r -s -p "DeepSeek API key: " DEEPSEEK_API_KEY
    echo
  fi
  python3 - "$APP_DIR/deepseek_config.json" "${DEEPSEEK_API_KEY:-}" <<'PY'
import json, sys
with open(sys.argv[1], "w", encoding="utf-8") as f:
    json.dump({"api_key": sys.argv[2], "model": "deepseek-flash"}, f, ensure_ascii=False, indent=2)
PY
  chmod 600 "$APP_DIR/deepseek_config.json"
fi

if [[ ! -s "$APP_DIR/telegram_config.json" ]]; then
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
    json.dump({"token": sys.argv[2], "chat_id": sys.argv[3]}, f, ensure_ascii=False, indent=2)
PY
  chmod 600 "$APP_DIR/telegram_config.json"
fi

touch "$APP_DIR/clients.txt"

"$APP_DIR/venv/bin/python" -m py_compile \
  "$APP_DIR/test_beeline.py" \
  "$APP_DIR/local_matcher.py" \
  "$APP_DIR/symbol_matching.py" \
  "$APP_DIR/batch_support.py" \
  "$APP_DIR/console_wait.py"

echo "[5/7] Launcher..."
cat > "$APP_DIR/run_server.sh" <<'EOF2'
#!/usr/bin/env bash
set -Eeuo pipefail
cd /opt/beeline
while [[ ! -s /opt/beeline/clients.txt ]]; do
  echo "[beeline] clients.txt пуст. Жду данные..."
  sleep 10
done
exec /usr/bin/xvfb-run -a -s "-screen 0 1920x1080x24" \
  /opt/beeline/venv/bin/python /opt/beeline/test_beeline.py
EOF2
chmod +x "$APP_DIR/run_server.sh"

echo "[6/7] systemd..."
cat > /etc/systemd/system/${SERVICE}.service <<'EOF2'
[Unit]
Description=Beeline 15.74 EXP-3
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=/opt/beeline
ExecStart=/opt/beeline/run_server.sh
Restart=always
RestartSec=5
TimeoutStopSec=20
KillMode=mixed
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF2

systemctl daemon-reload
systemctl enable "$SERVICE"
systemctl restart "$SERVICE"

echo "[7/7] Готово."
echo "Проект:  $APP_DIR"
echo "Статус:  systemctl status beeline --no-pager"
echo "Логи:    journalctl -u beeline -f"
if [[ ! -s "$APP_DIR/clients.txt" ]]; then
  echo
  echo "Сейчас сервис ждёт данные в /opt/beeline/clients.txt."
  echo "Открыть файл: sudo nano /opt/beeline/clients.txt"
fi

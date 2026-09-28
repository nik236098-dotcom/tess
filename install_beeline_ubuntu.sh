#!/usr/bin/env bash
set -Eeuo pipefail

APP_DIR="/opt/beeline"
SERVICE="beeline"
COMMIT="97fe531b9c0728b6b0b5173862748e4d2695a427"
RAW="https://raw.githubusercontent.com/nik236098-dotcom/tess/${COMMIT}"
BUNDLE_URL="${RAW}/beeline_15_74_exp_3tabs_unlimited_ai_github.zip"
CONTROLLER_URL="${RAW}/server_controller.py"
PATCH_URL="${RAW}/patch_15_75.py"

if [[ $EUID -ne 0 ]]; then
  echo "Запусти через sudo."
  exit 1
fi

export DEBIAN_FRONTEND=noninteractive

echo "[1/8] Системные пакеты..."
apt-get update -y
ASOUND_PKG="libasound2"
if apt-cache show libasound2t64 >/dev/null 2>&1; then ASOUND_PKG="libasound2t64"; fi
apt-get install -y python3 python3-venv python3-pip unzip curl xvfb ca-certificates fonts-liberation libnss3 libatk-bridge2.0-0 libgtk-3-0 libgbm1 "$ASOUND_PKG" libxss1 libxtst6 libx11-xcb1 libdrm2 libxcomposite1 libxdamage1 libxrandr2 libxfixes3 libglib2.0-0 libgl1

echo "[2/8] Код 15.75..."
mkdir -p "$APP_DIR"
TMP_ZIP="$(mktemp --suffix=.zip)"
curl -fL --retry 5 --retry-delay 2 "$BUNDLE_URL" -o "$TMP_ZIP"
# Fail with a clear message before extraction if GitHub did not return a ZIP.
python3 - "$TMP_ZIP" <<'PY'
import sys, zipfile
p=sys.argv[1]
if not zipfile.is_zipfile(p):
    raise SystemExit("ERROR: downloaded release bundle is not a valid ZIP")
with zipfile.ZipFile(p) as z:
    bad=z.testzip()
    if bad:
        raise SystemExit(f"ERROR: damaged ZIP member: {bad}")
print("ZIP OK")
PY
unzip -oq "$TMP_ZIP" -d "$APP_DIR"
rm -f "$TMP_ZIP"
curl -fL --retry 5 --retry-delay 2 "$CONTROLLER_URL" -o "$APP_DIR/server_controller.py"
curl -fL --retry 5 --retry-delay 2 "$PATCH_URL" -o "$APP_DIR/patch_15_75.py"
python3 "$APP_DIR/patch_15_75.py"

# Compatibility modules absent from the old archive.
cat > "$APP_DIR/console_wait.py" <<'PY'
def console_input(prompt=""):
    return input(prompt)
PY

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

echo "[3/8] Python/Chromium..."
if [[ ! -x "$APP_DIR/venv/bin/python" ]]; then python3 -m venv "$APP_DIR/venv"; fi
"$APP_DIR/venv/bin/python" -m pip install --upgrade pip wheel setuptools
"$APP_DIR/venv/bin/pip" install playwright "requests[socks]" numpy opencv-python-headless
"$APP_DIR/venv/bin/python" -m playwright install --with-deps chromium

echo "[4/8] DeepSeek..."
if [[ ! -f "$APP_DIR/deepseek_config.json" ]]; then
  read -r -s -p "DeepSeek API key: " DEEPSEEK_API_KEY; echo
  python3 - "$APP_DIR/deepseek_config.json" "$DEEPSEEK_API_KEY" <<'PY'
import json,sys
with open(sys.argv[1],"w",encoding="utf-8") as f: json.dump({"api_key":sys.argv[2],"model":"deepseek-flash"},f,ensure_ascii=False,indent=2)
PY
  chmod 600 "$APP_DIR/deepseek_config.json"
fi

echo "[5/8] Telegram..."
if [[ ! -f "$APP_DIR/telegram_config.json" ]]; then
  read -r -s -p "Telegram bot token: " TELEGRAM_BOT_TOKEN; echo
  read -r -p "Telegram chat_id: " TELEGRAM_CHAT_ID
  python3 - "$APP_DIR/telegram_config.json" "$TELEGRAM_BOT_TOKEN" "$TELEGRAM_CHAT_ID" <<'PY'
import json,sys
with open(sys.argv[1],"w",encoding="utf-8") as f: json.dump({"token":sys.argv[2],"chat_id":sys.argv[3],"proxy":""},f,ensure_ascii=False,indent=2)
PY
  chmod 600 "$APP_DIR/telegram_config.json"
fi
touch "$APP_DIR/clients.txt"

echo "[6/8] Проверка..."
"$APP_DIR/venv/bin/python" -m py_compile "$APP_DIR/test_beeline.py" "$APP_DIR/server_controller.py" "$APP_DIR/local_matcher.py" "$APP_DIR/symbol_matching.py" "$APP_DIR/batch_support.py" "$APP_DIR/console_wait.py"

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
echo "ГОТОВО. Открой Telegram-бота."
echo "Логи: journalctl -u beeline -f"

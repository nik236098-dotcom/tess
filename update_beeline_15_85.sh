#!/usr/bin/env bash
set -Eeuo pipefail
APP=/opt/beeline
cd "$APP"

systemctl stop beeline || true
cp -a test_beeline.py test_beeline.py.before_1585

curl -fsSL "https://raw.githubusercontent.com/nik236098-dotcom/tess/codex/beeline-15.74-exp3/patches/1585_consolidated.diff?x=$(date +%s)" -o /tmp/1585.diff
patch --forward --batch test_beeline.py /tmp/1585.diff || {
  echo "PATCH FAILED"
  cp -f test_beeline.py.before_1585 test_beeline.py
  exit 1
}

venv/bin/python -m py_compile test_beeline.py server_controller.py
systemctl restart telegram-tunnel || true
systemctl restart beeline
sleep 3

echo "=== VERSION ==="
grep -m1 "Версия 15.85" test_beeline.py
echo "=== CHROMIUM ==="
grep -m1 -- "--no-sandbox" test_beeline.py
echo "=== OPERATOR ==="
grep -m1 "SYSTEM_PROMPT_HASH_1585" test_beeline.py
echo "=== SERVICES ==="
systemctl is-active telegram-tunnel
systemctl is-active beeline

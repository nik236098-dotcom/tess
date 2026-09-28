#!/usr/bin/env bash
set -Eeuo pipefail
APP=/opt/beeline
cd "$APP"

systemctl stop beeline || true
cp -a test_beeline.py test_beeline.py.before_1586

curl -fsSL "https://raw.githubusercontent.com/nik236098-dotcom/tess/codex/beeline-15.74-exp3/update_beeline_15_86.py?x=$(date +%s)" -o /tmp/update_beeline_15_86.py

if ! python3 /tmp/update_beeline_15_86.py; then
  echo "PATCH FAILED -> restoring previous file"
  cp -f test_beeline.py.before_1586 test_beeline.py
  systemctl restart beeline
  exit 1
fi

venv/bin/python -m py_compile test_beeline.py server_controller.py
systemctl restart telegram-tunnel || true
systemctl restart beeline
sleep 4

echo "=== VERSION ==="
grep -m1 "Версия 15.86" test_beeline.py || true
echo "=== CHROMIUM ==="
grep -m1 -- "--no-sandbox" test_beeline.py || true
echo "=== OPERATOR ==="
grep -m1 "SYSTEM_PROMPT_HASH_1586" test_beeline.py || true
echo "=== GUARDS ==="
grep -m1 "FINAL_SUCCESS_GUARD_V1583" test_beeline.py || true
grep -m1 "capture_all_form_fields_v1583" test_beeline.py || true
echo "=== SERVICES ==="
systemctl is-active telegram-tunnel || true
systemctl is-active beeline || true

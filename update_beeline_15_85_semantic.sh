#!/usr/bin/env bash
set -Eeuo pipefail
APP=/opt/beeline
cd "$APP"

systemctl stop beeline || true
cp -a test_beeline.py test_beeline.py.before_1585_semantic

curl -fsSL "https://raw.githubusercontent.com/nik236098-dotcom/tess/codex/beeline-15.74-exp3/update_beeline_15_85.py?x=$(date +%s)" -o /tmp/update_beeline_15_85.py

if ! python3 /tmp/update_beeline_15_85.py; then
  echo "PATCH FAILED -> restoring previous file"
  cp -f test_beeline.py.before_1585_semantic test_beeline.py
  systemctl restart beeline
  exit 1
fi

venv/bin/python -m py_compile test_beeline.py server_controller.py
systemctl restart telegram-tunnel || true
systemctl restart beeline
sleep 4

echo "=== VERSION ==="
grep -m1 "Версия 15.85" test_beeline.py || true
echo "=== CHROMIUM FLAG ==="
grep -m1 -- "--no-sandbox" test_beeline.py || true
echo "=== OPERATOR MISSION ==="
grep -m1 "SYSTEM_PROMPT_HASH_1585" test_beeline.py || true
echo "=== 15.83 GUARDS ==="
grep -m1 "FINAL_SUCCESS_GUARD_V1583" test_beeline.py || true
grep -m1 "capture_all_form_fields_v1583" test_beeline.py || true
echo "=== SERVICES ==="
systemctl is-active telegram-tunnel || true
systemctl is-active beeline || true
echo "=== LAST LOGS ==="
journalctl -u beeline --since "1 minute ago" --no-pager | tail -40

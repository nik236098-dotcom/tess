#!/usr/bin/env bash
set -Eeuo pipefail
MODE="${1:---check}"
APP="${OPERATOR_APP_DIR:-/opt/beeline}"
case "$MODE" in --check|--apply) ;; *) echo 'Usage: check_server.sh [--check|--apply]' >&2; exit 2;; esac
for exe in python3 curl sha256sum mktemp; do
    command -v "$exe" >/dev/null || { echo "Required tool missing: $exe" >&2; exit 1; }
done
[[ -f "$APP/test_beeline.py" && -f "$APP/server_controller.py" ]] || {
    echo "Current source files not found under $APP; nothing changed." >&2; exit 1;
}
STAGE="$(mktemp -d /tmp/operator-check-1587.XXXXXXXX)"
trap 'rm -rf -- "$STAGE"' EXIT
COMMIT='f080a95f487f6d9e099ec27d1c54f7f007a3a9de'
RAW="https://raw.githubusercontent.com/nik236098-dotcom/tess/${COMMIT}/operator_repair_1587"
for name in operator_reliability.py operator_adapter.py apply_repair.py test_repair.py; do
    curl --proto '=https' --tlsv1.2 -fsSL --connect-timeout 10 --max-time 60 \
        --retry 2 "${RAW}/${name}" -o "${STAGE}/${name}"
done
(
    cd "$STAGE"
    sha256sum -c <<'HASHES'
06fe800551be0dce7843f31386c342197bc30e29c6822bf2b077cc258bff0fd8  operator_reliability.py
6d9c27480be677834d7f5b2fcf89f6f0a2cef05941b8f30512b9b196167aa052  operator_adapter.py
a331fdb566aea43220bb711ac13845f679c077c9ae78005929d95d92d084659a  apply_repair.py
54b29c13dc97ceadd5f3ed2fb8acd08c8d03dde722f917c2481070190a1f70e3  test_repair.py
HASHES
)
export PYTHONDONTWRITEBYTECODE=1
export OPERATOR_APP_SOURCE="$APP/test_beeline.py"
export OPERATOR_CONTROLLER_SOURCE="$APP/server_controller.py"
echo '=== OFFLINE TESTS AGAINST YOUR CURRENT SOURCE ==='
python3 "$STAGE/test_repair.py"
echo '=== COMPATIBILITY / PLAN ==='
python3 "$STAGE/apply_repair.py" --app "$APP" --check
if [[ "$MODE" == '--apply' ]]; then
    echo 'READ-ONLY SUPERVISION: no automatic identity filling or contract signing.'
    echo 'Application requires a stopped service; this script never stops it for you.'
    python3 "$STAGE/apply_repair.py" --app "$APP" --apply
else
    echo 'CHECK FINISHED. Production files and services were not changed.'
    echo 'This is a diagnostic candidate, not a verified production deployment.'
fi

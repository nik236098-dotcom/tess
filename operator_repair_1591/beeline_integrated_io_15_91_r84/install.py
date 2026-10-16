#!/usr/bin/env python3
"""r84 QUEUE_DONE: installs only server_controller.py (rest stays as on the server).

Same flags as the full installer: --app, --apply, --restart.
Used by update.sh / «⬆️ Обновить бота».
"""
from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

MARKER = "QUEUE_DONE_1591R84"
ACCEPTED = {
    "8a827f68aa4972f1c9ed1aeeec5f0de4b918dbb6e8bb1a4884f9abec2dd19935",  # r71–r83 controller
}
TARGET = "a84fd73cd01b287ec67e89c18e8621298afc04a416c704445a95fc1102a8e25d"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def service_cmd(action: str) -> None:
    subprocess.run(["systemctl", action, "beeline"], check=False)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--app", default="/opt/beeline")
    p.add_argument("--apply", action="store_true")
    p.add_argument("--restart", action="store_true")
    args = p.parse_args()
    app = Path(args.app)
    package = Path(__file__).resolve().parent
    target_path = app / "server_controller.py"
    new_path = package / "server_controller.py"

    if not (app / "test_beeline.py").is_file():
        print("ERROR: not an installed beeline app:", app, file=sys.stderr)
        return 1
    if not new_path.is_file():
        print("ERROR: package missing server_controller.py", file=sys.stderr)
        return 1

    new_raw = new_path.read_bytes()
    if digest(new_raw) != TARGET:
        print("ERROR: package server_controller.py checksum mismatch", file=sys.stderr)
        return 1
    if MARKER.encode() not in new_raw:
        print("ERROR: package has no", MARKER, file=sys.stderr)
        return 1

    if not target_path.is_file():
        print("ERROR: missing", target_path, file=sys.stderr)
        return 1
    cur = target_path.read_bytes()
    cur_h = digest(cur)

    if cur_h == TARGET and MARKER.encode() in cur:
        print("Already at r84 (QUEUE_DONE). Nothing to do.")
        return 0

    if cur_h not in ACCEPTED and MARKER.encode() not in cur:
        print(
            f"ERROR: installed server_controller.py SHA256={cur_h} is not a known r83 base.\n"
            "Refusing to overwrite. Update to r83 first or apply patch manually.",
            file=sys.stderr,
        )
        return 1

    print(f"Would replace server_controller.py ({cur_h[:12]}… → {TARGET[:12]}…)")
    if not args.apply:
        print("Dry-run OK. Re-run with --apply [--restart] to install.")
        return 0

    if args.restart:
        print("Stopping beeline…")
        service_cmd("stop")
        time.sleep(2)

    backup = app / "server_controller.py.bak_before_r84"
    shutil.copy2(target_path, backup)
    fd, tmp = tempfile.mkstemp(prefix=".server_controller.", dir=str(app))
    try:
        os.write(fd, new_raw)
        os.close(fd)
        os.chmod(tmp, 0o644)
        os.replace(tmp, target_path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise

    print("Installed server_controller.py r84. Backup:", backup)
    if args.restart:
        print("Starting beeline…")
        service_cmd("start")
        time.sleep(2)
        subprocess.run(["systemctl", "is-active", "beeline"], check=False)
    print("OK", MARKER)
    return 0


if __name__ == "__main__":
    sys.exit(main())

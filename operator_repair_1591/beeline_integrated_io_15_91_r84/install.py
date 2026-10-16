#!/usr/bin/env python3
"""r84 QUEUE_DONE — для кнопки «Обновить» / update.sh.

Ставит правку server_controller.py через server_controller.patch из этой же папки.
Флаги: --app /opt/beeline --apply --restart
"""
from __future__ import annotations

import argparse
import hashlib
import shutil
import subprocess
import sys
import time
from pathlib import Path

MARKER = "QUEUE_DONE_1591R84"
ACCEPTED = {
    "8a827f68aa4972f1c9ed1aeeec5f0de4b918dbb6e8bb1a4884f9abec2dd19935",
}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--app", default="/opt/beeline")
    p.add_argument("--apply", action="store_true")
    p.add_argument("--restart", action="store_true")
    args = p.parse_args()
    app = Path(args.app)
    package = Path(__file__).resolve().parent
    target = app / "server_controller.py"
    patch_file = package / "server_controller.patch"

    if not (app / "test_beeline.py").is_file():
        print("ERROR: not a beeline app:", app, file=sys.stderr)
        return 1
    if not target.is_file():
        print("ERROR: missing", target, file=sys.stderr)
        return 1
    if not patch_file.is_file():
        print("ERROR: missing", patch_file, file=sys.stderr)
        return 1

    cur = target.read_bytes()
    if MARKER.encode() in cur:
        print("Already r84 (QUEUE_DONE). Nothing to do.")
        return 0

    h = digest(cur)
    if h not in ACCEPTED:
        print(
            f"ERROR: server_controller SHA256={h} is not r83 base.\n"
            "Update to r83 first.",
            file=sys.stderr,
        )
        return 1

    print(f"Would apply {patch_file.name} to server_controller.py ({h[:12]}…)")
    if not args.apply:
        print("Dry-run OK. Use --apply --restart to install.")
        return 0

    if args.restart:
        print("Stopping beeline…")
        subprocess.run(["systemctl", "stop", "beeline"], check=False)
        time.sleep(2)

    backup = app / "server_controller.py.bak_before_r84"
    shutil.copy2(target, backup)

    # Normalize patch paths → server_controller.py
    raw_patch = patch_file.read_text(encoding="utf-8", errors="replace")
    raw_patch = raw_patch.replace("server_controller_r83.py", "server_controller.py")
    raw_patch = raw_patch.replace("server_controller_r84.py", "server_controller.py")
    fixed = package / ".server_controller.r84.fixed.patch"
    fixed.write_text(raw_patch, encoding="utf-8")

    r = subprocess.run(
        ["patch", "-p0", "--forward", "--batch", "-i", str(fixed)],
        cwd=str(app),
        capture_output=True,
        text=True,
    )
    if r.returncode not in (0, 1):
        print("patch stdout:", r.stdout, file=sys.stderr)
        print("patch stderr:", r.stderr, file=sys.stderr)
        print("ERROR: patch failed, restoring backup", file=sys.stderr)
        shutil.copy2(backup, target)
        return 1

    if MARKER.encode() not in target.read_bytes():
        print("ERROR: marker missing after patch, restoring", file=sys.stderr)
        shutil.copy2(backup, target)
        return 1

    print("Installed r84. Backup:", backup)
    if args.restart:
        print("Starting beeline…")
        subprocess.run(["systemctl", "start", "beeline"], check=False)
        time.sleep(2)
        subprocess.run(["systemctl", "is-active", "beeline"], check=False)
    print("OK", MARKER)
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Root-only installer with exact readback for user.slice I/O delegation."""
from __future__ import annotations

import os
import shutil
import subprocess
import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILES = (
    (ROOT / "deploy/systemd/user.slice.d/90-beast-io-delegation.conf",
     Path("/etc/systemd/system/user.slice.d/90-beast-io-delegation.conf")),
    (ROOT / "deploy/systemd/user-.slice.d/90-beast-io-delegation.conf",
     Path("/etc/systemd/system/user-.slice.d/90-beast-io-delegation.conf")),
    (ROOT / "deploy/systemd/user@.service.d/90-beast-io-delegation.conf",
     Path("/etc/systemd/system/user@.service.d/90-beast-io-delegation.conf")),
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify", action="store_true", help="read back every cgroup boundary without changing state")
    args = parser.parse_args()
    if args.verify:
        return verify()
    if os.geteuid() != 0:
        raise PermissionError("administrator authority is required; this tool never invokes sudo")
    for source, target in FILES:
        target.parent.mkdir(parents=True, exist_ok=True)
        temp = target.with_suffix(".tmp")
        shutil.copyfile(source, temp)
        os.chmod(temp, 0o644)
        os.replace(temp, target)
    subprocess.run(["systemctl", "daemon-reload"], check=True)
    subprocess.run(["systemctl", "set-property", "user.slice", "IOAccounting=yes"], check=True)
    print("installed user.slice, user-.slice, and user@.service I/O delegation overrides")
    print("reboot once, then run: python3 scripts/install_beast_io_delegation.py --verify")
    return 0


def verify() -> int:
    uid = os.getuid()
    paths = (
        Path("/sys/fs/cgroup/user.slice"),
        Path(f"/sys/fs/cgroup/user.slice/user-{uid}.slice"),
        Path(f"/sys/fs/cgroup/user.slice/user-{uid}.slice/user@{uid}.service"),
    )
    final_control = paths[-1] / "cgroup.subtree_control"
    final_controllers = set((paths[-1] / "cgroup.controllers").read_text(encoding="utf-8").split())
    final_subtree = set(final_control.read_text(encoding="utf-8").split())
    if "io" in final_controllers and "io" not in final_subtree:
        # systemd's user manager activates delegated controllers lazily when a
        # child first requests them. Exercise that production path rather than
        # writing directly to cgroup.subtree_control.
        completed = subprocess.run(
            ["systemd-run", "--user", "--wait", "--collect", "--quiet",
             "--unit=beast-io-delegation-verify", "--property=Delegate=io",
             "--property=IOAccounting=yes", "/usr/bin/true"],
            text=True, capture_output=True, check=False,
        )
        if completed.returncode != 0:
            print("failed to activate the lazily delegated user-manager I/O controller: " + completed.stderr.strip())
    failed = []
    for path in paths:
        controllers = set((path / "cgroup.controllers").read_text(encoding="utf-8").split())
        subtree = set((path / "cgroup.subtree_control").read_text(encoding="utf-8").split())
        ok = "io" in controllers and "io" in subtree
        print(f"{'PASS' if ok else 'FAIL'} {path}: controllers={sorted(controllers)} subtree={sorted(subtree)}")
        if not ok:
            failed.append(str(path))
    if failed:
        print("I/O delegation is still absent at: " + ", ".join(failed))
        return 1
    print("verified end-to-end I/O delegation")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

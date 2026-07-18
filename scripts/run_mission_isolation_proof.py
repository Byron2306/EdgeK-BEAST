#!/usr/bin/env python3
"""Run the physical mission proof inside a systemd-delegated user service."""
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.kernel.execution.cgroup_capsule import CgroupAuthorization
from app.kernel.execution.cgroup_delegation import CgroupDelegationManager
from app.kernel.execution.isolation_readiness import effective_cgroup_path
from app.kernel.execution.mission_isolation_proof import MissionIsolationProofRunner
from app.kernel.execution.race_free_cgroup_launcher import NativeCgroupLauncherCompiler


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mission", default="beast-heldout-proof")
    parser.add_argument("--output", required=True)
    parser.add_argument("--build-root", required=True)
    args = parser.parse_args()
    root = effective_cgroup_path()
    available = tuple((root / "cgroup.controllers").read_text(encoding="utf-8").split())
    requested = tuple(name for name in ("cpu", "memory", "pids", "io") if name in available)
    anchor = root / "beast-proof-anchor"
    anchor.mkdir()
    (anchor / "cgroup.procs").write_text(f"{os.getpid()}\n", encoding="utf-8")
    capsule, delegation = CgroupDelegationManager(root).prepare(
        args.mission, requested,
        CgroupAuthorization("delegate", args.mission, "systemd-delegated-runner", "approval:live-proof", "physical held-out isolation proof"),
    )
    if capsule is None:
        raise RuntimeError(f"delegation failed: {delegation.reason}")
    compiler = NativeCgroupLauncherCompiler()
    launcher = compiler.compile(Path(args.build_root) / "beast-cgroup-launcher")
    limits = {
        "cpu.max": "50000 100000", "memory.max": "33554432",
        "memory.swap.max": "0", "memory.oom.group": "1", "pids.max": "16",
    }
    if "io" in requested:
        io_rows = []
        cursor = root
        cgroup_root = Path("/sys/fs/cgroup")
        while cursor == cgroup_root or cgroup_root in cursor.parents:
            io_rows = (cursor / "io.stat").read_text(encoding="utf-8").splitlines()
            if io_rows or cursor == cgroup_root:
                break
            cursor = cursor.parent
        devices = [row.split()[0] for row in io_rows if row.split() and ":" in row.split()[0]]
        if not devices:
            raise RuntimeError("I/O is delegated but no physical device is attributable in io.stat")
        limits["io.max"] = f"{devices[0]} rbps=10485760 wbps=10485760"
    proof = MissionIsolationProofRunner(capsule, launcher, Path(args.build_root)).run(limits=limits)
    payload = {**asdict(proof), "delegation": asdict(delegation), "host_available_controllers": list(available)}
    Path(args.output).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"output": args.output, "full_isolation_proven": proof.full_isolation_proven,
                      "controllers": list(proof.controllers)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

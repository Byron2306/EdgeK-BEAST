#!/usr/bin/env python3
"""Prepare one explicit, read-only ProcessLease correlation for the X2 lab."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import tempfile
import time

from app.kernel.execution.process_identity import LinuxProcessIdentityCollector


def main() -> int:
    parser = argparse.ArgumentParser(description="Register an existing lab PID for X2 observation correlation")
    parser.add_argument("--pid", type=int, required=True)
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--mission-id", default="x2-controlled-lab")
    parser.add_argument("--workspace-id", default="edgek-beast")
    args = parser.parse_args()

    lease = LinuxProcessIdentityCollector().collect(args.pid, owner_scope="x2_observation_lab")
    entry = {
        "tgid": args.pid,
        "start_time_ticks": lease.start_time_ticks,
        "process_lease_id": lease.lease_id,
        "mission_id": args.mission_id,
        "workspace_id": args.workspace_id,
        "allow_prevalidated_exit_correlation": True,
        "exit_correlation_expires_at_epoch": time.time() + 60,
    }
    payload = {
        "beast_object_type": "x2_observation_lease_registry",
        "version": "1.0",
        "authority": "observation_correlation_only",
        "leases": [entry],
    }
    args.registry.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".x2-process-leases.", dir=args.registry.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
        os.chmod(temporary, 0o600)
        os.replace(temporary, args.registry)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    print(json.dumps({"registry": str(args.registry), "lease_id": lease.lease_id, "tgid": args.pid}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

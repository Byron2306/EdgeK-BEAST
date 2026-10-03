#!/usr/bin/env python3
"""Run the Operational Phase-3 stale lockfile/PID-file disposable domain."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.kernel.compute.deterministic_intelligence import canonical_json, sha256_digest
from app.kernel.dai.phase3_lockfile import (
    acquire_phase3_lockfile_world_lease,
    attempt_phase3_lockfile_stale_world_replay,
    execute_phase3_lockfile_cleanup,
    start_phase3_lockfile_lab,
    write_phase3_lockfile_receipt,
)


DEFAULT_OUT = ROOT / "evidence/dai-diode/phase3-composition-001/lockfile-domain"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--run-id", default="dai-phase3-lockfile-local-001")
    args = parser.parse_args()
    summary = run(out=args.out, run_id=args.run_id)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary["green"] else 1


def run(*, out: Path, run_id: str) -> dict[str, object]:
    out.mkdir(parents=True, exist_ok=True)
    lab = start_phase3_lockfile_lab(run_id=run_id)
    try:
        lease = acquire_phase3_lockfile_world_lease(lab)
        cleanup = execute_phase3_lockfile_cleanup(lab, lease)
        replay = attempt_phase3_lockfile_stale_world_replay(lab, lease)
        write_phase3_lockfile_receipt(out / "phase3_lockfile_cleanup_receipt.json", cleanup)
        write_phase3_lockfile_receipt(out / "phase3_lockfile_stale_world_replay_receipt.json", replay)
        (out / "phase3_lockfile_world_lease.json").write_text(
            canonical_json({"lease": lease, "lease_digest": lease.lease_digest}) + "\n",
            encoding="utf-8",
        )
        summary = {
            "beast_object_type": "dai_phase3_lockfile_domain_summary",
            "run_id": run_id,
            "green": bool(
                cleanup.executed
                and cleanup.stale_lock_removed
                and cleanup.unrelated_control_unchanged
                and cleanup.stale_pid_was_dead
                and replay.refused
                and replay.zero_effect
            ),
            "cleanup_receipt_digest": cleanup.receipt_digest,
            "replay_receipt_digest": replay.receipt_digest,
            "lease_digest": lease.lease_digest,
            "provider_calls_used": 0,
            "production_authority_allowed": False,
            "execution_scope": lease.execution_scope,
        }
        summary["summary_digest"] = sha256_digest(summary)
        (out / "phase3_lockfile_domain_summary.json").write_text(canonical_json(summary) + "\n", encoding="utf-8")
        return summary
    finally:
        lab.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())

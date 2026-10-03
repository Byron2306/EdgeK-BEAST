#!/usr/bin/env python3
"""Run the Operational Phase-3 expired certificate handshake domain."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.kernel.compute.deterministic_intelligence import canonical_json, sha256_digest
from app.kernel.dai.phase3_certificate import (
    acquire_phase3_certificate_world_lease,
    execute_phase3_certificate_handshake,
    start_phase3_certificate_lab,
    write_phase3_certificate_receipt,
)


DEFAULT_OUT = ROOT / "evidence/dai-diode/phase3-composition-001/certificate-domain"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--run-id", default="dai-phase3-certificate-local-001")
    args = parser.parse_args()
    summary = run(out=args.out, run_id=args.run_id)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary["green"] else 1


def run(*, out: Path, run_id: str) -> dict[str, object]:
    out.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    lab = start_phase3_certificate_lab(run_id=run_id, now=now)
    try:
        lease = acquire_phase3_certificate_world_lease(lab, now=now)
        handshake = execute_phase3_certificate_handshake(lab, lease)
        write_phase3_certificate_receipt(out / "phase3_certificate_handshake_receipt.json", handshake)
        (out / "phase3_certificate_world_lease.json").write_text(
            canonical_json({"lease": lease, "lease_digest": lease.lease_digest}) + "\n",
            encoding="utf-8",
        )
        summary = {
            "beast_object_type": "dai_phase3_certificate_domain_summary",
            "run_id": run_id,
            "green": bool(
                handshake.executed
                and handshake.expired_certificate_refused
                and handshake.control_certificate_accepted
                and not handshake.expired_observation.app_payload_received
            ),
            "handshake_receipt_digest": handshake.receipt_digest,
            "lease_digest": lease.lease_digest,
            "expired_certificate_refused": handshake.expired_certificate_refused,
            "control_certificate_accepted": handshake.control_certificate_accepted,
            "expired_app_payload_received": handshake.expired_observation.app_payload_received,
            "provider_calls_used": 0,
            "production_authority_allowed": False,
            "execution_scope": lease.execution_scope,
        }
        summary["summary_digest"] = sha256_digest(summary)
        (out / "phase3_certificate_domain_summary.json").write_text(canonical_json(summary) + "\n", encoding="utf-8")
        return summary
    finally:
        lab.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())

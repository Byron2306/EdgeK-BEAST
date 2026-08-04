#!/usr/bin/env python3
"""Mint one shared Phase-5 DIO Commons proposal for autonomous witnesses."""
from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import secrets
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.kernel.compute.deterministic_intelligence import sha256_digest
from app.kernel.dai.dio_distributed_quorum import DIOProposalPacket


DEFAULT_OUT = ROOT / "evidence/dai-diode/phase5-shared-quorum/dio_phase5_shared_proposal.json"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--ttl-minutes", type=int, default=45)
    parser.add_argument("--governance-epoch", default="dio-phase5-shared-commons-quorum-001")
    parser.add_argument("--capability-label", default="phase5-mixed-autonomous-commons-quorum")
    args = parser.parse_args()
    now = datetime.now(timezone.utc).replace(microsecond=0)
    nonce = "phase5-shared-" + secrets.token_urlsafe(24)
    seed = {
        "label": args.capability_label,
        "governance_epoch": args.governance_epoch,
        "challenge_nonce": nonce,
        "issued_at": now.isoformat(),
    }
    proposal = DIOProposalPacket(
        beast_object_type="dio_proposition_packet",
        proposal_digest=sha256_digest({"proposal": seed}),
        capability_digest=sha256_digest({"capability": args.capability_label}),
        evidence_root=sha256_digest({"evidence": "phase5-shared-quorum", "seed": seed}),
        world_state_hash=sha256_digest({"world": "phase5-shared-quorum", "seed": seed}),
        governance_epoch=args.governance_epoch,
        challenge_nonce=nonce,
        issued_at=now.isoformat(),
        expires_at=(now + timedelta(minutes=args.ttl_minutes)).isoformat(),
    )
    payload = asdict(proposal) | {"packet_digest": proposal.packet_digest}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"proposal": str(args.out), "packet_digest": proposal.packet_digest}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

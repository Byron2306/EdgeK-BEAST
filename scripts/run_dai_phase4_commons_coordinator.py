#!/usr/bin/env python3
"""Run the Phase-4 Commons coordinator over live HF plus adapter witnesses."""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
import argparse
import json
from pathlib import Path
import sys
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.kernel.compute.deterministic_intelligence import canonical_json, sha256_digest
from app.kernel.dai.dio_commons_adapters import DIOCommonsSpaceAdapterReport
from app.kernel.dai.dio_commons_coordinator import mint_phase4_proposal, run_commons_coordinator_session
from app.kernel.dai.dio_commons_online import DIOCommonsCapabilityManifest, DIOCommonsSpaceIdentity
from app.kernel.dai.dio_distributed_quorum import DIORemoteWitnessVote


DEFAULT_OUT = ROOT / "evidence/dai-diode/phase4-commons-coordinator"
HF_RECEIPT = ROOT / "evidence/dai-diode/phase4-hf-witness/dio_hf_phase4_live_witness_receipt.json"
ADAPTER_ROOT = ROOT / "evidence/dai-diode/phase4-commons-adapters"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    summary = run(out=args.out)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary["green"] else 1


def run(*, out: Path) -> dict[str, Any]:
    out.mkdir(parents=True, exist_ok=True)
    hf = _read(HF_RECEIPT)
    identity_payload = dict(hf["identity"])
    identity_signature = identity_payload.pop("identity_signature")
    identity_payload.pop("identity_digest", None)
    identity = DIOCommonsSpaceIdentity(**identity_payload)
    manifest_payload = dict(hf["manifest"])
    manifest_payload.pop("manifest_digest", None)
    manifest = DIOCommonsCapabilityManifest(**manifest_payload)
    online_vote = DIORemoteWitnessVote(**{field: hf["vote"][field] for field in DIORemoteWitnessVote.__dataclass_fields__})
    now = _receipt_replay_time(online_vote)
    adapter_reports = tuple(_load_adapter_report(path) for path in sorted(ADAPTER_ROOT.glob("*_commons_adapter.json")))
    adapter_keys = {report.node_id: Ed25519PrivateKey.generate() for report in adapter_reports}
    proposal, challenge = mint_phase4_proposal(
        proposal_digest=online_vote.proposal_digest,
        capability_digest=online_vote.capability_digest,
        evidence_root=online_vote.evidence_root,
        world_state_hash=online_vote.world_state_hash,
        governance_epoch=online_vote.governance_epoch,
        challenge_nonce=online_vote.challenge_nonce,
        now=now,
        ttl_seconds=max(1, int((_time(online_vote.expires_at) - now).total_seconds())),
    )
    coordinator_key = Ed25519PrivateKey.generate()
    session, quorum = run_commons_coordinator_session(
        online_identity=identity,
        online_identity_signature=identity_signature,
        online_manifest=manifest,
        adapter_reports=adapter_reports,
        proposal=proposal,
        challenge=challenge,
        coordinator_key=coordinator_key,
        now=now,
        adapter_vote_keys=adapter_keys,
        online_votes=(online_vote,),
    )
    payload = {
        "beast_object_type": "dio_phase4_commons_coordinator_run",
        "session": asdict(session),
        "session_digest": session.session_digest,
        "quorum_report": asdict(quorum),
        "quorum_report_digest": quorum.report_digest,
        "adapter_vote_boundary": "adapter votes use local simulated signing keys because these adapter witnesses are evidence-bearing one-shot/offline spaces, not online voting endpoints",
        "time_boundary": "coordinator runner replays the harvested live HF vote at its receipt issuance time; current live freshness is tested by scripts/verify_dio_hf_witness.py",
        "green": session.quorum_available,
        "provider_calls_used": 0,
        "production_authority_allowed": False,
        "execution_authority_allowed": False,
    }
    payload["run_digest"] = sha256_digest(payload)
    (out / "dio_phase4_commons_coordinator_run.json").write_text(canonical_json(payload) + "\n", encoding="utf-8")
    return {
        "beast_object_type": "dio_phase4_commons_coordinator_summary",
        "green": session.quorum_available,
        "session_digest": session.session_digest,
        "quorum_report_digest": quorum.report_digest,
        "run_digest": payload["run_digest"],
        "quorum_class": quorum.quorum_class,
        "decision": quorum.decision,
        "admitted_node_count": quorum.admitted_node_count,
        "valid_vote_count": quorum.valid_vote_count,
        "red_gates": session.red_gates,
        "adapter_votes_simulated": session.adapter_votes_simulated,
        "time_boundary": "historical_live_hf_vote_receipt_replay",
        "provider_calls_used": 0,
        "production_authority_allowed": False,
        "execution_authority_allowed": False,
    }


def _load_adapter_report(path: Path) -> DIOCommonsSpaceAdapterReport:
    payload = _read(path)
    return DIOCommonsSpaceAdapterReport(**payload["adapter_report"])


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _time(value: str) -> datetime:
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)


def _receipt_replay_time(vote: DIORemoteWitnessVote) -> datetime:
    """Use the harvested vote's own issuance time for deterministic replay.

    The stored HF receipt is proof of a live vote at harvest time; it is not a
    perpetual current lease.  Replaying at the receipt timestamp keeps the
    offline coordinator regression honest while the live verifier remains
    responsible for obtaining fresh remote votes.
    """

    return _time(vote.issued_at)


if __name__ == "__main__":
    raise SystemExit(main())

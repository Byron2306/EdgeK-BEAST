#!/usr/bin/env python3
"""Replay a Phase-5 shared-proposal autonomous witness quorum."""
from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.kernel.compute.deterministic_intelligence import sha256_digest
from app.kernel.dai.dio_distributed_quorum import (
    DIOProposalPacket,
    DIOWitnessAdmission,
    evaluate_dio_distributed_quorum,
)
from app.kernel.dai.dio_remote_witness_packet import DIOAutonomousRemoteWitnessPacket, verify_autonomous_remote_witness_packet


DEFAULT_PROPOSAL = ROOT / "evidence/dai-diode/phase5-shared-quorum/dio_phase5_shared_proposal.json"
DEFAULT_HF = ROOT / "evidence/dai-diode/phase5-shared-quorum/hf/dio_hf_shared_proposal_witness_receipt.json"
DEFAULT_GITHUB = ROOT / "evidence/dai-diode/phase5-shared-quorum/github/run-30960436614/dio_github_actions_autonomous_witness_packet.json"
DEFAULT_GCP = ROOT / "evidence/dai-diode/phase5-shared-quorum/gcp-physical-remote/dio_gcp_autonomous_witness_envelope.json"
DEFAULT_GCP_GOVERNANCE = ROOT / "evidence/dai-diode/phase5-shared-quorum/gcp-governance-remote/dio_gcp_autonomous_witness_envelope.json"
DEFAULT_OUT = ROOT / "evidence/dai-diode/phase5-shared-quorum/dio_phase5_shared_quorum_replay.json"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--proposal", type=Path, default=DEFAULT_PROPOSAL)
    parser.add_argument("--hf", type=Path, default=DEFAULT_HF)
    parser.add_argument("--github", type=Path, default=DEFAULT_GITHUB)
    parser.add_argument("--gcp", type=Path, default=DEFAULT_GCP)
    parser.add_argument("--gcp-governance", type=Path, default=DEFAULT_GCP_GOVERNANCE)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    result = run(
        proposal_path=args.proposal,
        hf=args.hf,
        github=args.github,
        gcp=args.gcp,
        gcp_governance=args.gcp_governance,
        out=args.out,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["green"] else 2


def run(*, proposal_path: Path, hf: Path, github: Path, gcp: Path, gcp_governance: Path, out: Path) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    proposal_payload = _read(proposal_path)
    proposal_payload.pop("packet_digest", None)
    proposal = DIOProposalPacket(**proposal_payload)
    rows = (
        _extract_hf(hf),
        _extract_envelope("github", github),
        _extract_envelope("gcp-physical", gcp),
        _extract_envelope("gcp-governance", gcp_governance),
    )
    admissions: list[DIOWitnessAdmission] = []
    packets: list[DIOAutonomousRemoteWitnessPacket] = []
    witness_results: list[dict[str, Any]] = []
    permitted: list[str] = []
    red: list[str] = []
    for row in rows:
        try:
            admission = DIOWitnessAdmission(**row["admission"])
            packet = DIOAutonomousRemoteWitnessPacket(**row["packet"])
            verification = verify_autonomous_remote_witness_packet(
                packet=packet,
                admission=admission,
                proposal=proposal,
                permitted_verifier_commits=(admission.verifier_commit,),
                evaluation_time=now,
            )
            if not verification.verified:
                red.append(f"{row['provider']}_autonomous_packet_not_verified")
            admissions.append(admission)
            packets.append(packet)
            permitted.append(admission.verifier_commit)
            witness_results.append(
                {
                    "provider": row["provider"],
                    "node_id": admission.node_id,
                    "role": admission.role.value,
                    "packet_digest": packet.packet_digest,
                    "admission_digest": admission.admission_digest,
                    "verification_digest": verification.verification_digest,
                    "verified": verification.verified,
                    "red_gates": verification.red_gates,
                    "proposal_packet_digest": packet.proposal_packet_digest,
                    "remote_runtime_observed": packet.remote_runtime_observed,
                    "hardware_rooted_identity": admission.hardware_rooted_identity,
                    "maximum_authority": admission.maximum_authority,
                }
            )
        except Exception as exc:
            red.append(f"{row['provider']}_parse_failed:{type(exc).__name__}")
    quorum = evaluate_dio_distributed_quorum(
        proposal=proposal,
        admissions=admissions,
        votes=[packet.vote for packet in packets],
        permitted_verifier_commits=permitted,
        evaluation_time=now,
        require_hardware_root=True,
    )
    red.extend(f"quorum:{gate}" for gate in quorum.red_gates)
    result = {
        "beast_object_type": "dio_phase5_shared_quorum_replay",
        "evaluated_at": now.isoformat(),
        "green": not red and quorum.passed,
        "red_gates": tuple(red),
        "proposal_packet_digest": proposal.packet_digest,
        "proposal_digest": proposal.proposal_digest,
        "witnesses": witness_results,
        "quorum": asdict(quorum) | {"report_digest": quorum.report_digest},
        "authority_boundary": (
            "shared autonomous quorum replay only; GCP physical witness remains "
            "inventory-admitted and not publication-grade provider-token attested"
        ),
        "production_authority_allowed": False,
        "execution_authority_allowed": False,
        "provider_calls_used": 0,
    }
    result["replay_digest"] = sha256_digest(result)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def _extract_hf(path: Path) -> dict[str, Any]:
    payload = _read(path)["autonomous_packet"]
    return {
        "provider": "huggingface",
        "admission": _without_digest(payload["admission"], "admission_digest"),
        "packet": _without_digest(payload["packet"], "packet_digest"),
    }


def _extract_envelope(provider: str, path: Path) -> dict[str, Any]:
    payload = _read(path)
    return {
        "provider": provider,
        "admission": _without_digest(payload["admission"], "admission_digest"),
        "packet": _without_digest(payload["packet"], "packet_digest"),
    }


def _without_digest(payload: dict[str, Any], digest_field: str) -> dict[str, Any]:
    row = dict(payload)
    row.pop(digest_field, None)
    return row


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Run the Phase-5 autonomous remote witness packet hostile gauntlet."""
from __future__ import annotations

from dataclasses import asdict, replace
from datetime import datetime, timedelta, timezone
import argparse
import json
from pathlib import Path
import sys
from typing import Any, Callable

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.kernel.compute.deterministic_intelligence import canonical_json, sha256_digest
from app.kernel.dai.dio_distributed_quorum import (
    DIOProposalPacket,
    DIORemoteWitnessVote,
    DIOVoteDecision,
    DIOWitnessAdmission,
    DIOWitnessRole,
    HARDWARE_WITNESS_AUTHORITY,
    public_key_b64,
    public_key_fingerprint,
    sign_dio_vote,
)
from app.kernel.dai.dio_remote_witness_packet import (
    DIOAutonomousRemoteWitnessPacket,
    sign_autonomous_remote_witness_packet,
    verify_autonomous_remote_witness_packet,
)


DEFAULT_OUT = ROOT / "evidence/dai-diode/phase5-remote-witness-packet"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    receipt = run(out=args.out)
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0 if receipt["green"] else 1


def run(*, out: Path) -> dict[str, Any]:
    out.mkdir(parents=True, exist_ok=True)
    cases: dict[str, Callable[[], bool]] = {
        "valid_autonomous_packet_admitted": _valid_autonomous_packet_admitted,
        "bad_packet_signature_rejected": _bad_packet_signature_rejected,
        "wrong_proposal_binding_rejected": _wrong_proposal_binding_rejected,
        "stale_packet_rejected": _stale_packet_rejected,
        "missing_independent_remote_runtime_rejected": _missing_independent_remote_runtime_rejected,
        "vote_tampering_rejected": _vote_tampering_rejected,
        "wrong_admission_digest_rejected": _wrong_admission_digest_rejected,
        "authority_mismatch_rejected": _authority_mismatch_rejected,
    }
    results = {name: check() for name, check in cases.items()}
    now, _key, proposal, admission, packet = _fixture()
    receipt = {
        "beast_object_type": "dio_phase5_autonomous_remote_witness_packet_gauntlet_receipt",
        "version": "2026-08-04.phase5.autonomous-remote-witness-gauntlet.v1",
        "case_count": len(results),
        "passed_count": sum(1 for passed in results.values() if passed),
        "case_results": results,
        "reference_packet_digest": packet.packet_digest,
        "reference_proposal_packet_digest": proposal.packet_digest,
        "reference_admission_digest": admission.admission_digest,
        "reference_node_id": admission.node_id,
        "provider_calls_used": 0,
        "execution_authority_allowed": False,
        "production_authority_allowed": False,
        "green": all(results.values()),
        "issued_at": now.isoformat(),
    }
    receipt["receipt_digest"] = sha256_digest(receipt)
    (out / "phase5_remote_witness_packet_gauntlet_receipt.json").write_text(canonical_json(receipt) + "\n", encoding="utf-8")
    return receipt


def _fixture():
    now = datetime.now(timezone.utc).replace(microsecond=0)
    key = Ed25519PrivateKey.generate()
    pub = public_key_b64(key.public_key())
    verifier = sha256_digest({"verifier": "phase5-remote-witness"})
    proposal = DIOProposalPacket(
        beast_object_type="dio_proposition_packet",
        proposal_digest=sha256_digest({"proposal": "phase5"}),
        capability_digest=sha256_digest({"capability": "commons-autonomous-witness"}),
        evidence_root=sha256_digest({"evidence": "phase5"}),
        world_state_hash=sha256_digest({"world": "phase5"}),
        governance_epoch="dio-phase5-online-001",
        challenge_nonce="phase5-autonomous-witness-" + "x" * 24,
        issued_at=(now - timedelta(seconds=30)).isoformat(),
        expires_at=(now + timedelta(minutes=5)).isoformat(),
    )
    admission = DIOWitnessAdmission(
        node_id="dio:aws:tee-governance-01",
        role=DIOWitnessRole.GOVERNANCE,
        runtime_platform="aws_nitro_tpm",
        infrastructure_provider="aws",
        public_key_b64=pub,
        key_fingerprint=public_key_fingerprint(pub),
        verifier_commit=verifier,
        maximum_authority=HARDWARE_WITNESS_AUTHORITY,
        verifier_build_permitted=True,
        remote_runtime=True,
        hardware_rooted_identity=True,
        attestation_digest=sha256_digest({"aws": "nitro-attestation-report"}),
        container_manifest=sha256_digest({"container": "phase5-witness"}),
    )
    vote = sign_dio_vote(
        DIORemoteWitnessVote(
            beast_object_type="dio_remote_witness_vote",
            node_id=admission.node_id,
            role=admission.role,
            decision=DIOVoteDecision.APPROVE,
            proposal_digest=proposal.proposal_digest,
            capability_digest=proposal.capability_digest,
            evidence_root=proposal.evidence_root,
            world_state_hash=proposal.world_state_hash,
            governance_epoch=proposal.governance_epoch,
            verifier_commit=verifier,
            challenge_nonce=proposal.challenge_nonce,
            evidence_checked=(proposal.evidence_root, admission.attestation_digest),
            reason_codes=("phase5_remote_packet_gauntlet",),
            issued_at=now.isoformat(),
            expires_at=proposal.expires_at,
            maximum_authority=HARDWARE_WITNESS_AUTHORITY,
        ),
        key,
    )
    packet = sign_autonomous_remote_witness_packet(
        DIOAutonomousRemoteWitnessPacket(
            beast_object_type="dio_autonomous_remote_witness_packet",
            version="2026-08-04.phase5.autonomous-remote-witness.v1",
            node_id=admission.node_id,
            role=admission.role,
            runtime_platform=admission.runtime_platform,
            infrastructure_provider=admission.infrastructure_provider,
            public_key_b64=pub,
            key_fingerprint=admission.key_fingerprint,
            verifier_commit=verifier,
            admission_digest=admission.admission_digest,
            admission_attestation_digest=admission.attestation_digest,
            proposal_packet_digest=proposal.packet_digest,
            vote=vote,
            evidence_receipts=(admission.attestation_digest,),
            independently_evaluated=True,
            remote_runtime_observed=True,
            issued_at=now.isoformat(),
            expires_at=proposal.expires_at,
            maximum_authority=HARDWARE_WITNESS_AUTHORITY,
        ),
        key,
    )
    return now, key, proposal, admission, packet


def _verify(packet=None, proposal=None, admission=None, permitted=None, now=None):
    fixture_now, _key, fixture_proposal, fixture_admission, fixture_packet = _fixture()
    admission = admission or fixture_admission
    return verify_autonomous_remote_witness_packet(
        packet=packet or fixture_packet,
        admission=admission,
        proposal=proposal or fixture_proposal,
        permitted_verifier_commits=permitted or (admission.verifier_commit,),
        evaluation_time=now or fixture_now,
    )


def _valid_autonomous_packet_admitted() -> bool:
    return _verify().verified


def _bad_packet_signature_rejected() -> bool:
    _now, _key, _proposal, _admission, packet = _fixture()
    report = _verify(packet=replace(packet, packet_signature=packet.packet_signature[:-4] + "AAAA"))
    return not report.verified and "packet_signature_valid" in report.red_gates


def _wrong_proposal_binding_rejected() -> bool:
    _now, _key, proposal, _admission, packet = _fixture()
    wrong = replace(proposal, world_state_hash=sha256_digest({"world": "different"}))
    report = _verify(packet=packet, proposal=wrong)
    return not report.verified and {"packet_proposal_digest_bound", "vote_binds_world_state"}.issubset(report.red_gates)


def _stale_packet_rejected() -> bool:
    now, key, _proposal, _admission, packet = _fixture()
    stale = replace(packet, issued_at=(now - timedelta(days=2)).isoformat(), expires_at=(now - timedelta(days=1)).isoformat(), packet_signature="")
    stale = sign_autonomous_remote_witness_packet(stale, key)
    report = _verify(packet=stale, now=now)
    return not report.verified and "packet_fresh" in report.red_gates


def _missing_independent_remote_runtime_rejected() -> bool:
    _now, key, _proposal, _admission, packet = _fixture()
    hostile = sign_autonomous_remote_witness_packet(
        replace(packet, independently_evaluated=False, remote_runtime_observed=False, packet_signature=""),
        key,
    )
    report = _verify(packet=hostile)
    return not report.verified and {"packet_declares_independent_evaluation", "packet_remote_runtime_observed"}.issubset(report.red_gates)


def _vote_tampering_rejected() -> bool:
    _now, key, _proposal, _admission, packet = _fixture()
    tampered_vote = replace(packet.vote, evidence_root=sha256_digest({"evidence": "tampered"}))
    hostile = sign_autonomous_remote_witness_packet(replace(packet, vote=tampered_vote, packet_signature=""), key)
    report = _verify(packet=hostile)
    return not report.verified and {"vote_signature_valid", "vote_binds_evidence_root"}.issubset(report.red_gates)


def _wrong_admission_digest_rejected() -> bool:
    _now, key, _proposal, _admission, packet = _fixture()
    hostile = sign_autonomous_remote_witness_packet(
        replace(packet, admission_digest=sha256_digest({"admission": "wrong"}), packet_signature=""),
        key,
    )
    report = _verify(packet=hostile)
    return not report.verified and "packet_admission_digest_bound" in report.red_gates


def _authority_mismatch_rejected() -> bool:
    _now, key, _proposal, _admission, packet = _fixture()
    hostile_vote = sign_dio_vote(replace(packet.vote, maximum_authority="semantic_vote_only", vote_signature=""), key)
    hostile = sign_autonomous_remote_witness_packet(replace(packet, vote=hostile_vote, packet_signature=""), key)
    report = _verify(packet=hostile)
    return not report.verified and "vote_authority_matches_packet" in report.red_gates


if __name__ == "__main__":
    raise SystemExit(main())

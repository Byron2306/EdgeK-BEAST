"""Cloud TEE harvest to Phase-5 autonomous witness packet bridge.

This bridge is intentionally strict about the key boundary: a cloud harvest can
be wrapped as a Phase-5 autonomous packet only by the private key corresponding
to the admitted witness public key.  If the caller cannot honestly assert that
the signing occurred in the remote runtime, the packet is still buildable for a
negative/control receipt, but verification will mark `packet_remote_runtime_observed`
red.
"""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.kernel.compute.deterministic_intelligence import sha256_digest
from app.kernel.dai.dio_distributed_quorum import (
    DIOProposalPacket,
    DIORemoteWitnessVote,
    DIOVoteDecision,
    DIOWitnessAdmission,
    sign_dio_vote,
)
from app.kernel.dai.dio_remote_witness_packet import (
    DIOAutonomousRemoteWitnessPacket,
    sign_autonomous_remote_witness_packet,
    verify_autonomous_remote_witness_packet,
)


CLOUD_AUTONOMOUS_ENVELOPE_VERSION = "2026-08-04.phase5.cloud-autonomous-witness.v1"


def build_cloud_autonomous_witness_envelope(
    *,
    harvest: dict[str, Any],
    private_key: Ed25519PrivateKey,
    remote_runtime_observed: bool,
    proposal: DIOProposalPacket | None = None,
    evaluation_time: datetime | None = None,
) -> dict[str, Any]:
    if harvest.get("green") is not True:
        raise ValueError("cloud harvest must be green before autonomous packet wrapping")
    if not harvest.get("admission"):
        raise ValueError("cloud harvest has no admitted witness")
    admission = DIOWitnessAdmission(**harvest["admission"])
    evidence = dict(harvest.get("evidence") or {})
    issued_at = str(evidence.get("issued_at") or datetime.now(timezone.utc).isoformat())
    expires_at = str(evidence.get("expires_at") or issued_at)
    harvest_digest = str(harvest.get("harvest_digest") or sha256_digest(harvest))
    evidence_digest = str(harvest.get("evidence_digest") or sha256_digest(evidence))
    if proposal is None:
        proposal = DIOProposalPacket(
            beast_object_type="dio_proposition_packet",
            proposal_digest=sha256_digest(
                {
                    "proposal": "cloud-tee-autonomous-witness",
                    "harvest_digest": harvest_digest,
                    "evidence_digest": evidence_digest,
                    "node_id": admission.node_id,
                }
            ),
            capability_digest=sha256_digest({"capability": "cloud-tee-autonomous-witness", "node_id": admission.node_id}),
            evidence_root=harvest_digest,
            world_state_hash=sha256_digest({"world": "cloud-tee-harvest", "harvest_digest": harvest_digest}),
            governance_epoch=str(evidence.get("governance_epoch") or "dio-phase5-cloud-autonomous-001"),
            challenge_nonce=str(evidence.get("challenge_nonce") or "cloud-autonomous-" + harvest_digest[-32:]),
            issued_at=issued_at,
            expires_at=expires_at,
        )
    packet_issued_at = proposal.issued_at
    packet_expires_at = proposal.expires_at
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
            verifier_commit=admission.verifier_commit,
            challenge_nonce=proposal.challenge_nonce,
            evidence_checked=tuple(
                digest
                for digest in (
                    proposal.evidence_root,
                    evidence_digest,
                    admission.attestation_digest,
                    str(harvest.get("admission_report_digest") or ""),
                )
                if digest
            ),
            reason_codes=("cloud_harvest_green", "autonomous_packet_requested"),
            issued_at=packet_issued_at,
            expires_at=packet_expires_at,
            maximum_authority=admission.maximum_authority,
        ),
        private_key,
    )
    packet = sign_autonomous_remote_witness_packet(
        DIOAutonomousRemoteWitnessPacket(
            beast_object_type="dio_autonomous_remote_witness_packet",
            version="2026-08-04.phase5.autonomous-remote-witness.v1",
            node_id=admission.node_id,
            role=admission.role,
            runtime_platform=admission.runtime_platform,
            infrastructure_provider=admission.infrastructure_provider,
            public_key_b64=admission.public_key_b64,
            key_fingerprint=admission.key_fingerprint,
            verifier_commit=admission.verifier_commit,
            admission_digest=admission.admission_digest,
            admission_attestation_digest=admission.attestation_digest,
            proposal_packet_digest=proposal.packet_digest,
            vote=vote,
            evidence_receipts=tuple(
                digest
                for digest in (
                    proposal.evidence_root,
                    evidence_digest,
                    admission.attestation_digest,
                    str(harvest.get("admission_report_digest") or ""),
                )
                if digest
            ),
            independently_evaluated=True,
            remote_runtime_observed=remote_runtime_observed,
            issued_at=packet_issued_at,
            expires_at=packet_expires_at,
            maximum_authority=admission.maximum_authority,
        ),
        private_key,
    )
    current = evaluation_time or _historical_evaluation_time(issued_at)
    verification = verify_autonomous_remote_witness_packet(
        packet=packet,
        admission=admission,
        proposal=proposal,
        permitted_verifier_commits=(admission.verifier_commit,),
        evaluation_time=current,
    )
    envelope = {
        "beast_object_type": "dio_cloud_autonomous_witness_envelope",
        "version": CLOUD_AUTONOMOUS_ENVELOPE_VERSION,
        "node_id": admission.node_id,
        "role": admission.role.value,
        "runtime_platform": admission.runtime_platform,
        "infrastructure_provider": admission.infrastructure_provider,
        "maximum_authority": admission.maximum_authority,
        "source_harvest_digest": harvest_digest,
        "source_evidence_digest": evidence_digest,
        "remote_runtime_observed": remote_runtime_observed,
        "production_authority_allowed": False,
        "execution_authority_allowed": False,
        "provider_calls_used": 0,
        "proposal": _jsonable(proposal) | {"packet_digest": proposal.packet_digest},
        "admission": _jsonable(admission) | {"admission_digest": admission.admission_digest},
        "packet": _jsonable(packet) | {"packet_digest": packet.packet_digest},
        "verification": _jsonable(verification) | {"verification_digest": verification.verification_digest},
        "nonclaims": (
            "autonomous_packet_does_not_upgrade_provider_attestation_quality",
            "remote_runtime_observed_must_be_true_for_green_phase5_credit",
            "production_authority_denied",
            "execution_authority_denied",
        ),
    }
    envelope["envelope_digest"] = sha256_digest(envelope)
    return envelope


def _historical_evaluation_time(issued_at: str) -> datetime:
    parsed = datetime.fromisoformat(str(issued_at).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _jsonable(value: Any) -> Any:
    if hasattr(value, "__dataclass_fields__"):
        return _jsonable(asdict(value))
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]
    if hasattr(value, "value"):
        return value.value
    return value

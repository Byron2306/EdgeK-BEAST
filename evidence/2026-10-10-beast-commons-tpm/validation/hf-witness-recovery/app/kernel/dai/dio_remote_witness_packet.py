"""Autonomous remote witness packet verification for DIO Commons Phase 5.

Phase 4 could fold offline adapter evidence into a coordinator-run quorum.  This
module defines the next stricter object: a remote witness packet that carries a
node-signed vote plus a node-signed packet envelope bound to one admission and
one proposal.

The packet is provider-neutral.  AWS/GCP/Azure/GitHub/HF can all use it, but no
provider name grants authority by itself.
"""
from __future__ import annotations

import base64
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Iterable

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from app.kernel.compute.deterministic_intelligence import canonical_json, require_digest, sha256_digest
from app.kernel.dai.dio_distributed_quorum import (
    DIOProposalPacket,
    DIORemoteWitnessVote,
    DIOWitnessAdmission,
    DIOWitnessRole,
    HARDWARE_WITNESS_AUTHORITY,
    HF_SOFTWARE_WITNESS_AUTHORITY,
    LOCAL_EXECUTION_WITNESS_AUTHORITY,
    public_key_fingerprint,
    verify_dio_vote_signature,
)


DIO_REMOTE_WITNESS_PACKET_VERSION = "2026-08-04.phase5.autonomous-remote-witness.v1"
REMOTE_WITNESS_PACKET_AUTHORITIES = frozenset(
    {
        HF_SOFTWARE_WITNESS_AUTHORITY,
        HARDWARE_WITNESS_AUTHORITY,
        LOCAL_EXECUTION_WITNESS_AUTHORITY,
        "remote_oidc_sigstore_software_witness_only",
        "semantic_vote_only",
        "governance_vote_only",
    }
)


@dataclass(frozen=True, slots=True)
class DIOAutonomousRemoteWitnessPacket:
    beast_object_type: str
    version: str
    node_id: str
    role: DIOWitnessRole | str
    runtime_platform: str
    infrastructure_provider: str
    public_key_b64: str
    key_fingerprint: str
    verifier_commit: str
    admission_digest: str
    admission_attestation_digest: str
    proposal_packet_digest: str
    vote: DIORemoteWitnessVote | dict[str, Any]
    evidence_receipts: tuple[str, ...]
    independently_evaluated: bool
    remote_runtime_observed: bool
    issued_at: str
    expires_at: str
    maximum_authority: str
    provider_calls_used: int = 0
    execution_authority_allowed: bool = False
    production_authority_allowed: bool = False
    packet_signature: str = ""

    def __post_init__(self) -> None:
        if self.beast_object_type != "dio_autonomous_remote_witness_packet":
            raise ValueError("unexpected autonomous remote witness packet object type")
        if self.version != DIO_REMOTE_WITNESS_PACKET_VERSION:
            raise ValueError("unexpected autonomous remote witness packet version")
        if not isinstance(self.role, DIOWitnessRole):
            object.__setattr__(self, "role", DIOWitnessRole(self.role))
        if not isinstance(self.vote, DIORemoteWitnessVote):
            object.__setattr__(self, "vote", DIORemoteWitnessVote(**self.vote))
        for name in ("node_id", "runtime_platform", "infrastructure_provider", "public_key_b64", "maximum_authority"):
            if not str(getattr(self, name)).strip():
                raise ValueError(f"autonomous remote witness packet requires {name}")
        for field_name in (
            "key_fingerprint",
            "verifier_commit",
            "admission_digest",
            "proposal_packet_digest",
        ):
            require_digest(getattr(self, field_name), field_name=field_name)
        if self.admission_attestation_digest:
            require_digest(self.admission_attestation_digest, field_name="admission_attestation_digest")
        for digest in self.evidence_receipts:
            require_digest(digest, field_name="evidence_receipts")
        if self.key_fingerprint != public_key_fingerprint(self.public_key_b64):
            raise ValueError("remote witness packet key fingerprint does not match public key")
        issued = _parse_time(self.issued_at, field_name="issued_at")
        expires = _parse_time(self.expires_at, field_name="expires_at")
        if expires <= issued:
            raise ValueError("remote witness packet expires_at must be after issued_at")
        if self.maximum_authority not in REMOTE_WITNESS_PACKET_AUTHORITIES:
            raise ValueError("remote witness packet maximum authority is not bounded")
        if self.provider_calls_used != 0 or self.execution_authority_allowed or self.production_authority_allowed:
            raise ValueError("remote witness packet cannot grant provider, execution or production authority")

    @property
    def signing_payload(self) -> dict[str, Any]:
        payload = asdict(self)
        role = payload.get("role")
        if isinstance(role, DIOWitnessRole):
            payload["role"] = role.value
        if isinstance(self.vote, DIORemoteWitnessVote):
            payload["vote"] = self.vote.signing_payload | {"vote_signature": self.vote.vote_signature}
        payload["packet_signature"] = ""
        return payload

    @property
    def packet_digest(self) -> str:
        return sha256_digest(self)


@dataclass(frozen=True, slots=True)
class DIOAutonomousRemoteWitnessVerification:
    beast_object_type: str
    version: str
    packet_digest: str
    proposal_packet_digest: str
    admission_digest: str
    vote_digest: str
    node_id: str
    role: str
    verified: bool
    red_gates: tuple[str, ...]
    provider_calls_used: int
    execution_authority_allowed: bool
    production_authority_allowed: bool

    def __post_init__(self) -> None:
        if self.beast_object_type != "dio_autonomous_remote_witness_verification":
            raise ValueError("unexpected autonomous remote witness verification object type")
        for field_name in ("packet_digest", "proposal_packet_digest", "admission_digest", "vote_digest"):
            require_digest(getattr(self, field_name), field_name=field_name)
        if self.provider_calls_used != 0 or self.execution_authority_allowed or self.production_authority_allowed:
            raise ValueError("autonomous remote witness verification cannot grant authority")
        if self.verified and self.red_gates:
            raise ValueError("autonomous remote witness verification cannot be green with red gates")

    @property
    def verification_digest(self) -> str:
        return sha256_digest(self)


def sign_autonomous_remote_witness_packet(
    packet: DIOAutonomousRemoteWitnessPacket,
    private_key: Ed25519PrivateKey,
) -> DIOAutonomousRemoteWitnessPacket:
    signature = base64.b64encode(private_key.sign(canonical_json(packet.signing_payload).encode("utf-8"))).decode("ascii")
    return DIOAutonomousRemoteWitnessPacket(**{**asdict(packet), "packet_signature": signature})


def verify_autonomous_remote_witness_packet(
    *,
    packet: DIOAutonomousRemoteWitnessPacket,
    admission: DIOWitnessAdmission,
    proposal: DIOProposalPacket,
    permitted_verifier_commits: Iterable[str],
    evaluation_time: datetime | None = None,
) -> DIOAutonomousRemoteWitnessVerification:
    current = (evaluation_time or datetime.now(timezone.utc)).astimezone(timezone.utc)
    permitted = set(permitted_verifier_commits)
    vote = packet.vote
    gates = {
        "packet_signature_valid": _verify_packet_signature(packet),
        "packet_fresh": _fresh(packet.issued_at, packet.expires_at, current),
        "packet_node_matches_admission": packet.node_id == admission.node_id,
        "packet_role_matches_admission": packet.role == admission.role,
        "packet_key_matches_admission": packet.public_key_b64 == admission.public_key_b64
        and packet.key_fingerprint == admission.key_fingerprint,
        "packet_verifier_matches_admission": packet.verifier_commit == admission.verifier_commit,
        "packet_authority_matches_admission": packet.maximum_authority == admission.maximum_authority,
        "packet_admission_digest_bound": packet.admission_digest == admission.admission_digest,
        "packet_attestation_digest_bound": packet.admission_attestation_digest == admission.attestation_digest,
        "packet_proposal_digest_bound": packet.proposal_packet_digest == proposal.packet_digest,
        "packet_declares_independent_evaluation": packet.independently_evaluated is True,
        "packet_remote_runtime_observed": packet.remote_runtime_observed is True and admission.remote_runtime is True,
        "packet_verifier_permitted": packet.verifier_commit in permitted and admission.verifier_build_permitted,
        "packet_authority_bounded": packet.maximum_authority in REMOTE_WITNESS_PACKET_AUTHORITIES,
        "packet_denies_execution_and_production": packet.provider_calls_used == 0
        and not packet.execution_authority_allowed
        and not packet.production_authority_allowed,
        "vote_signature_valid": verify_dio_vote_signature(vote, admission.public_key_b64),
        "vote_node_matches_packet": vote.node_id == packet.node_id,
        "vote_role_matches_packet": vote.role == packet.role,
        "vote_binds_proposal": vote.proposal_digest == proposal.proposal_digest,
        "vote_binds_capability": vote.capability_digest == proposal.capability_digest,
        "vote_binds_evidence_root": vote.evidence_root == proposal.evidence_root,
        "vote_binds_world_state": vote.world_state_hash == proposal.world_state_hash,
        "vote_binds_governance_epoch": vote.governance_epoch == proposal.governance_epoch,
        "vote_binds_challenge_nonce": vote.challenge_nonce == proposal.challenge_nonce,
        "vote_verifier_matches_packet": vote.verifier_commit == packet.verifier_commit,
        "vote_authority_matches_packet": vote.maximum_authority == packet.maximum_authority,
        "vote_fresh": _fresh(vote.issued_at, vote.expires_at, current),
        "vote_checked_packet_evidence": proposal.evidence_root in vote.evidence_checked,
    }
    red_gates = tuple(sorted(name for name, passed in gates.items() if not passed))
    return DIOAutonomousRemoteWitnessVerification(
        beast_object_type="dio_autonomous_remote_witness_verification",
        version=DIO_REMOTE_WITNESS_PACKET_VERSION,
        packet_digest=packet.packet_digest,
        proposal_packet_digest=proposal.packet_digest,
        admission_digest=admission.admission_digest,
        vote_digest=vote.vote_digest,
        node_id=packet.node_id,
        role=packet.role.value if isinstance(packet.role, DIOWitnessRole) else str(packet.role),
        verified=not red_gates,
        red_gates=red_gates,
        provider_calls_used=0,
        execution_authority_allowed=False,
        production_authority_allowed=False,
    )


def _verify_packet_signature(packet: DIOAutonomousRemoteWitnessPacket) -> bool:
    try:
        public = Ed25519PublicKey.from_public_bytes(base64.b64decode(packet.public_key_b64, validate=True))
        public.verify(base64.b64decode(packet.packet_signature, validate=True), canonical_json(packet.signing_payload).encode("utf-8"))
        return True
    except Exception:
        return False


def _parse_time(value: str, *, field_name: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field_name} must be an ISO timestamp") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{field_name} must include timezone")
    return parsed.astimezone(timezone.utc)


def _fresh(issued_at: str, expires_at: str, current: datetime) -> bool:
    issued = _parse_time(issued_at, field_name="issued_at")
    expires = _parse_time(expires_at, field_name="expires_at")
    return issued <= current < expires

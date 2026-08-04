"""Distributed DIO witness admission and remote signed quorum verification.

This module is deliberately narrower than the older local Commons quorum.
Commons ML-KEM proves a session transcript. It is not a vote signature and it is
not identity attestation.  A DIO distributed quorum only counts explicit witness
votes signed by admitted node keys and bound to one proposal/world/epoch/nonce.
"""
from __future__ import annotations

import base64
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Iterable, Mapping

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from app.kernel.compute.deterministic_intelligence import canonical_json, require_digest, sha256_bytes, sha256_digest


DIO_REMOTE_WITNESS_VERSION = "2026-08-04.phase2.1.dio-distributed-quorum.v1"
HF_SOFTWARE_WITNESS_AUTHORITY = "remote_signed_software_witness_only"
HARDWARE_WITNESS_AUTHORITY = "hardware_rooted_governance_vote_only"
LOCAL_EXECUTION_WITNESS_AUTHORITY = "physical_execution_witness_only"


class DIOWitnessRole(str, Enum):
    PHYSICAL_EXECUTION = "physical_execution_witness"
    SEMANTIC = "semantic_witness"
    ADVERSARIAL = "adversarial_witness"
    GOVERNANCE = "governance_witness"


class DIOVoteDecision(str, Enum):
    APPROVE = "approve"
    REFUSE = "refuse"
    ABSTAIN = "abstain"
    VETO = "veto"


@dataclass(frozen=True, slots=True)
class DIOProposalPacket:
    beast_object_type: str
    proposal_digest: str
    capability_digest: str
    evidence_root: str
    world_state_hash: str
    governance_epoch: str
    challenge_nonce: str
    issued_at: str
    expires_at: str
    audience: str = "dai-distributed-quorum"

    def __post_init__(self) -> None:
        for field_name in ("proposal_digest", "capability_digest", "evidence_root", "world_state_hash"):
            require_digest(getattr(self, field_name), field_name=field_name)
        if self.beast_object_type != "dio_proposition_packet":
            raise ValueError("DIO proposal packet has the wrong object type")
        if self.audience != "dai-distributed-quorum":
            raise ValueError("DIO proposal packet audience mismatch")
        if not self.challenge_nonce.strip() or not self.governance_epoch.strip():
            raise ValueError("DIO proposal packet requires challenge_nonce and governance_epoch")
        _parse_time(self.issued_at, field_name="issued_at")
        expires = _parse_time(self.expires_at, field_name="expires_at")
        if expires <= _parse_time(self.issued_at, field_name="issued_at"):
            raise ValueError("DIO proposal packet expires_at must be after issued_at")

    @property
    def packet_digest(self) -> str:
        return sha256_digest(self)


@dataclass(frozen=True, slots=True)
class DIOWitnessAdmission:
    node_id: str
    role: DIOWitnessRole | str
    runtime_platform: str
    infrastructure_provider: str
    public_key_b64: str
    key_fingerprint: str
    verifier_commit: str
    maximum_authority: str
    verifier_build_permitted: bool
    remote_runtime: bool
    hardware_rooted_identity: bool
    attestation_digest: str = ""
    container_manifest: str = ""
    admitted: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.role, DIOWitnessRole):
            object.__setattr__(self, "role", DIOWitnessRole(self.role))
        for name in ("node_id", "runtime_platform", "infrastructure_provider", "public_key_b64", "maximum_authority"):
            if not str(getattr(self, name)).strip():
                raise ValueError(f"DIO witness admission requires {name}")
        require_digest(self.key_fingerprint, field_name="key_fingerprint")
        require_digest(self.verifier_commit, field_name="verifier_commit")
        if self.attestation_digest:
            require_digest(self.attestation_digest, field_name="attestation_digest")
        if self.container_manifest:
            require_digest(self.container_manifest, field_name="container_manifest")
        if self.key_fingerprint != public_key_fingerprint(self.public_key_b64):
            raise ValueError("DIO witness key fingerprint does not match public key")

    @property
    def admission_digest(self) -> str:
        return sha256_digest(self)


@dataclass(frozen=True, slots=True)
class DIORemoteWitnessVote:
    beast_object_type: str
    node_id: str
    role: DIOWitnessRole | str
    decision: DIOVoteDecision | str
    proposal_digest: str
    capability_digest: str
    evidence_root: str
    world_state_hash: str
    governance_epoch: str
    verifier_commit: str
    challenge_nonce: str
    evidence_checked: tuple[str, ...]
    reason_codes: tuple[str, ...]
    issued_at: str
    expires_at: str
    maximum_authority: str
    vote_signature: str = ""

    def __post_init__(self) -> None:
        if self.beast_object_type != "dio_remote_witness_vote":
            raise ValueError("DIO witness vote has the wrong object type")
        if not isinstance(self.role, DIOWitnessRole):
            object.__setattr__(self, "role", DIOWitnessRole(self.role))
        if not isinstance(self.decision, DIOVoteDecision):
            object.__setattr__(self, "decision", DIOVoteDecision(self.decision))
        for field_name in ("proposal_digest", "capability_digest", "evidence_root", "world_state_hash", "verifier_commit"):
            require_digest(getattr(self, field_name), field_name=field_name)
        for digest in self.evidence_checked:
            require_digest(digest, field_name="evidence_checked")
        if not self.node_id.strip() or not self.governance_epoch.strip() or not self.challenge_nonce.strip():
            raise ValueError("DIO witness vote requires node_id, governance_epoch and challenge_nonce")
        issued = _parse_time(self.issued_at, field_name="issued_at")
        expires = _parse_time(self.expires_at, field_name="expires_at")
        if expires <= issued:
            raise ValueError("DIO witness vote expires_at must be after issued_at")

    @property
    def signing_payload(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["role"] = self.role.value if isinstance(self.role, DIOWitnessRole) else str(self.role)
        payload["decision"] = self.decision.value if isinstance(self.decision, DIOVoteDecision) else str(self.decision)
        payload["vote_signature"] = ""
        return payload

    @property
    def vote_digest(self) -> str:
        return sha256_digest(self)


@dataclass(frozen=True, slots=True)
class DIODistributedQuorumReport:
    beast_object_type: str
    version: str
    proposal_packet_digest: str
    quorum_class: str
    decision: str
    admitted_node_count: int
    valid_vote_count: int
    remote_node_count: int
    hardware_rooted_node_count: int
    distinct_key_count: int
    distinct_runtime_platform_count: int
    distinct_infrastructure_provider_count: int
    roles_present: tuple[str, ...]
    vote_digests: tuple[str, ...]
    red_gates: tuple[str, ...]
    execution_authority_allowed: bool
    production_authority_allowed: bool

    @property
    def passed(self) -> bool:
        return self.decision == "approve" and not self.red_gates

    @property
    def report_digest(self) -> str:
        return sha256_digest(self)


def public_key_fingerprint(public_key_b64: str) -> str:
    return sha256_bytes(base64.b64decode(public_key_b64, validate=True))


def public_key_b64(public_key: Ed25519PublicKey) -> str:
    return base64.b64encode(public_key.public_bytes_raw()).decode("ascii")


def sign_dio_vote(vote: DIORemoteWitnessVote, private_key: Ed25519PrivateKey) -> DIORemoteWitnessVote:
    signature = base64.b64encode(private_key.sign(canonical_json(vote.signing_payload).encode("utf-8"))).decode("ascii")
    return DIORemoteWitnessVote(**{**asdict(vote), "vote_signature": signature})


def verify_dio_vote_signature(vote: DIORemoteWitnessVote, public_key_b64_value: str) -> bool:
    try:
        public = Ed25519PublicKey.from_public_bytes(base64.b64decode(public_key_b64_value, validate=True))
        public.verify(base64.b64decode(vote.vote_signature, validate=True), canonical_json(vote.signing_payload).encode("utf-8"))
        return True
    except Exception:
        return False


def evaluate_dio_distributed_quorum(
    *,
    proposal: DIOProposalPacket,
    admissions: Iterable[DIOWitnessAdmission],
    votes: Iterable[DIORemoteWitnessVote],
    permitted_verifier_commits: Iterable[str],
    evaluation_time: datetime | None = None,
    require_hardware_root: bool = False,
) -> DIODistributedQuorumReport:
    current = evaluation_time or datetime.now(timezone.utc)
    permitted = set(permitted_verifier_commits)
    admitted = {item.node_id: item for item in admissions if item.admitted}
    vote_rows = tuple(votes)
    valid_votes: list[DIORemoteWitnessVote] = []
    red: set[str] = set()
    admission_authorities = {
        HF_SOFTWARE_WITNESS_AUTHORITY,
        HARDWARE_WITNESS_AUTHORITY,
        LOCAL_EXECUTION_WITNESS_AUTHORITY,
        "remote_oidc_sigstore_software_witness_only",
        "semantic_vote_only",
        "governance_vote_only",
    }

    if not _fresh(proposal.issued_at, proposal.expires_at, current):
        red.add("proposal_not_fresh")
    if len(admitted) < 3:
        red.add("minimum_three_admitted_nodes")
    if len({item.key_fingerprint for item in admitted.values()}) != len(admitted):
        red.add("distinct_signing_keys")
    if any(item.verifier_commit not in permitted or not item.verifier_build_permitted for item in admitted.values()):
        red.add("admitted_verifier_build_permitted")
    if any(item.maximum_authority not in admission_authorities for item in admitted.values()):
        red.add("admitted_maximum_authority_bounded")
    if any(item.maximum_authority == "ml_kem_session_only" for item in admitted.values()):
        red.add("ml_kem_session_cannot_be_identity_attestation")

    for vote in vote_rows:
        node = admitted.get(vote.node_id)
        if node is None:
            red.add("votes_from_admitted_nodes")
            continue
        local_gates = {
            "vote_role_matches_admission": vote.role == node.role,
            "vote_signature_valid": verify_dio_vote_signature(vote, node.public_key_b64),
            "vote_binds_proposal": vote.proposal_digest == proposal.proposal_digest,
            "vote_binds_capability": vote.capability_digest == proposal.capability_digest,
            "vote_binds_evidence_root": vote.evidence_root == proposal.evidence_root,
            "vote_binds_world_state": vote.world_state_hash == proposal.world_state_hash,
            "vote_binds_governance_epoch": vote.governance_epoch == proposal.governance_epoch,
            "vote_binds_challenge_nonce": vote.challenge_nonce == proposal.challenge_nonce,
            "vote_fresh": _fresh(vote.issued_at, vote.expires_at, current),
            "vote_verifier_build_permitted": vote.verifier_commit in permitted and vote.verifier_commit == node.verifier_commit,
            "vote_maximum_authority_bounded": vote.maximum_authority in {
                HF_SOFTWARE_WITNESS_AUTHORITY,
                HARDWARE_WITNESS_AUTHORITY,
                LOCAL_EXECUTION_WITNESS_AUTHORITY,
                "remote_oidc_sigstore_software_witness_only",
                "semantic_vote_only",
                "governance_vote_only",
            },
        }
        failed = [name for name, ok in local_gates.items() if not ok]
        red.update(failed)
        if not failed:
            valid_votes.append(vote)

    valid_by_node = {vote.node_id: vote for vote in valid_votes}
    approvals = [vote for vote in valid_by_node.values() if vote.decision is DIOVoteDecision.APPROVE]
    vetoes = [vote for vote in valid_by_node.values() if vote.decision is DIOVoteDecision.VETO]
    roles = {node.role.value for node in admitted.values()}
    approval_roles = {vote.role.value for vote in approvals}
    remote_count = sum(1 for node in admitted.values() if node.remote_runtime)
    hardware_count = sum(1 for node in admitted.values() if node.hardware_rooted_identity)
    platform_count = len({node.runtime_platform for node in admitted.values()})
    provider_count = len({node.infrastructure_provider for node in admitted.values()})
    distinct_key_count = len({node.key_fingerprint for node in admitted.values()})
    quorum_class = classify_dio_quorum(admitted.values())

    if DIOWitnessRole.PHYSICAL_EXECUTION.value not in roles:
        red.add("physical_execution_witness_required")
    if not ({DIOWitnessRole.SEMANTIC.value, DIOWitnessRole.ADVERSARIAL.value} & roles):
        red.add("semantic_or_adversarial_witness_required")
    if DIOWitnessRole.GOVERNANCE.value not in roles:
        red.add("governance_witness_required")
    if remote_count < 1:
        red.add("at_least_one_remote_node")
    if platform_count < 2:
        red.add("at_least_two_runtime_platforms")
    if require_hardware_root and hardware_count < 1:
        red.add("at_least_one_hardware_rooted_identity")
    if len(approvals) < 3:
        red.add("three_of_three_approval_required")
    if not approval_roles.issuperset({DIOWitnessRole.PHYSICAL_EXECUTION.value, DIOWitnessRole.GOVERNANCE.value}):
        red.add("approval_roles_required")
    if not ({DIOWitnessRole.SEMANTIC.value, DIOWitnessRole.ADVERSARIAL.value} & approval_roles):
        red.add("semantic_or_adversarial_approval_required")
    if vetoes:
        red.add("authenticated_veto_blocks_execution")

    decision = "vetoed" if vetoes else ("approve" if not red else "quorum_unavailable")
    return DIODistributedQuorumReport(
        beast_object_type="dio_distributed_quorum_report",
        version=DIO_REMOTE_WITNESS_VERSION,
        proposal_packet_digest=proposal.packet_digest,
        quorum_class=quorum_class,
        decision=decision,
        admitted_node_count=len(admitted),
        valid_vote_count=len(valid_by_node),
        remote_node_count=remote_count,
        hardware_rooted_node_count=hardware_count,
        distinct_key_count=distinct_key_count,
        distinct_runtime_platform_count=platform_count,
        distinct_infrastructure_provider_count=provider_count,
        roles_present=tuple(sorted(roles)),
        vote_digests=tuple(sorted(vote.vote_digest for vote in valid_by_node.values())),
        red_gates=tuple(sorted(red)),
        execution_authority_allowed=False,
        production_authority_allowed=False,
    )


def classify_dio_quorum(admissions: Iterable[DIOWitnessAdmission]) -> str:
    nodes = tuple(admissions)
    if len(nodes) < 3:
        return "quorum_unavailable"
    platform_count = len({node.runtime_platform for node in nodes})
    provider_count = len({node.infrastructure_provider for node in nodes})
    remote_count = sum(1 for node in nodes if node.remote_runtime)
    hardware_count = sum(1 for node in nodes if node.hardware_rooted_identity)
    if hardware_count >= 3 and provider_count >= 2:
        return "full_independently_attested_quorum"
    if hardware_count >= 1 and remote_count >= 1 and platform_count >= 3:
        return "heterogeneous_distributed_quorum"
    if remote_count >= 1 and platform_count >= 2:
        return "independent_remote_signed_witness_quorum"
    if platform_count >= 3:
        return "host_isolated_quorum_one_hardware_root"
    if platform_count >= 2:
        return "process_isolated_quorum"
    return "local_quorum_simulation"


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

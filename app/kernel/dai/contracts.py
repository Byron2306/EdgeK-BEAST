"""Phase-1 DAI Diode contract spine.

The first synthesis boundary is a diode:

    learning / adversarial / harmonic / physical observations
        -> evidence and candidates
        -> BEAST validation and later quorum promotion

No upstream organ may directly mint execution authority.  This module keeps the
initial shared objects deliberately conservative: every external stack can
contribute evidence, but a Phase-1 packet remains a quarantined candidate unless
BEAST promotion and quorum authority are explicitly present in a later phase.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import datetime, timezone
from enum import Enum
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from app.kernel.compute.deterministic_intelligence import (
    DIGEST_RE,
    canonical_json,
    require_digest,
    sha256_bytes,
    sha256_digest,
)


DAI_CONTRACT_VERSION = "2026-08-04.phase1"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_iso_datetime(value: str, *, field_name: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be an ISO-8601 datetime")
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be an ISO-8601 datetime") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{field_name} must include timezone information")
    return parsed


class DAIOrgan(str, Enum):
    SOPHIA = "sophia"
    SERAPH = "seraph"
    METATRON_HARMONIC = "metatron_harmonic"
    ARDA = "arda"
    BEAST = "beast"
    COMMONS = "commons"
    SENSORIUM = "sensorium"
    QUORUM = "quorum"


class AuthorityScope(str, Enum):
    OBSERVATION_ONLY = "observation_only"
    CANDIDATE_ONLY = "candidate_only"
    ADVERSARIAL_CHALLENGE_ONLY = "adversarial_challenge_only"
    HARMONIC_ASSESSMENT_ONLY = "harmonic_assessment_only"
    PHYSICAL_ATTESTATION_ONLY = "physical_attestation_only"
    COMMONS_ADMISSION_ONLY = "commons_admission_only"
    NEURAL_MESH_ACTIVATION_ONLY = "neural_mesh_activation_only"
    ARDA_BOUNDED_EXECUTION_ONLY = "arda_bounded_execution_only"
    PLASTICITY_PROPOSAL_ONLY = "plasticity_proposal_only"
    SEMANTIC_PROMOTION = "semantic_promotion"
    QUORUM_APPROVAL = "quorum_approval"
    EXECUTION_AUTHORITY = "execution_authority"


class PromotionState(str, Enum):
    QUARANTINED_CANDIDATE = "quarantined_candidate"
    REFUSED = "refused"
    PROMOTED_TEST_ONLY = "promoted_test_only"
    PROMOTED_CAPABILITY = "promoted_capability"


class VoteDecision(str, Enum):
    APPROVED = "approved"
    DEGRADED_APPROVAL = "degraded_approval"
    REFUSED = "refused"
    VETOED = "vetoed"
    QUORUM_UNAVAILABLE = "quorum_unavailable"
    WORLD_STATE_FRACTURE = "world_state_fracture"


@dataclass(frozen=True, slots=True)
class ArtifactReceipt:
    """Digest-bound pointer to an external project artifact.

    The path is metadata.  The authority comes from recomputing the file digest
    and binding the digest into later packets.
    """

    organ: DAIOrgan
    artifact_path: str
    artifact_digest: str
    artifact_schema: str = "unknown"
    observed_at: str = field(default_factory=utc_now_iso)
    summary: Mapping[str, Any] = field(default_factory=dict)
    maximum_authority: AuthorityScope = AuthorityScope.OBSERVATION_ONLY

    def __post_init__(self) -> None:
        if not isinstance(self.organ, DAIOrgan):
            object.__setattr__(self, "organ", DAIOrgan(self.organ))
        if not isinstance(self.maximum_authority, AuthorityScope):
            object.__setattr__(self, "maximum_authority", AuthorityScope(self.maximum_authority))
        if not self.artifact_path.strip():
            raise ValueError("artifact_path is required")
        require_digest(self.artifact_digest, field_name="artifact_digest")
        parse_iso_datetime(self.observed_at, field_name="observed_at")
        canonical_json(self.summary)

    @classmethod
    def from_file(
        cls,
        path: str | Path,
        *,
        organ: DAIOrgan,
        artifact_schema: str = "unknown",
        summary: Mapping[str, Any] | None = None,
        maximum_authority: AuthorityScope = AuthorityScope.OBSERVATION_ONLY,
    ) -> "ArtifactReceipt":
        source = Path(path).expanduser().resolve()
        payload = source.read_bytes()
        return cls(
            organ=organ,
            artifact_path=str(source),
            artifact_digest=sha256_bytes(payload),
            artifact_schema=artifact_schema,
            summary=dict(summary or {}),
            maximum_authority=maximum_authority,
        )

    @property
    def receipt_digest(self) -> str:
        return sha256_digest(self)

    def verify_file_digest(self) -> bool:
        try:
            return sha256_bytes(Path(self.artifact_path).read_bytes()) == self.artifact_digest
        except OSError:
            return False


@dataclass(frozen=True, slots=True)
class WorldStateSnapshot:
    snapshot_id: str
    epoch_id: str
    facts: Mapping[str, Any]
    observed_at: str = field(default_factory=utc_now_iso)
    expires_at: str = ""
    policy_generation: str = "dai-phase1-policy"

    def __post_init__(self) -> None:
        if not self.snapshot_id.strip() or not self.epoch_id.strip():
            raise ValueError("world state requires snapshot_id and epoch_id")
        parse_iso_datetime(self.observed_at, field_name="observed_at")
        if self.expires_at:
            expires = parse_iso_datetime(self.expires_at, field_name="expires_at")
            observed = parse_iso_datetime(self.observed_at, field_name="observed_at")
            if expires <= observed:
                raise ValueError("world state expires_at must be after observed_at")
        canonical_json(self.facts)

    @property
    def snapshot_digest(self) -> str:
        return sha256_digest(self)

    def is_current(self, *, now: datetime | None = None) -> bool:
        if not self.expires_at:
            return True
        current = now or datetime.now(timezone.utc)
        return parse_iso_datetime(self.expires_at, field_name="expires_at") > current


@dataclass(frozen=True, slots=True)
class CandidatePredicateSpec:
    predicate: str
    value_type: str
    subject_kinds: tuple[str, ...]
    true_text: str
    false_text: str
    visual_true: str
    visual_false: str
    evidence_required_when_supported: bool = True
    conflicts_with: tuple[Mapping[str, Any], ...] = ()

    def __post_init__(self) -> None:
        if not self.predicate.strip() or not self.value_type.strip():
            raise ValueError("candidate predicate requires predicate and value_type")
        if not self.subject_kinds:
            raise ValueError("candidate predicate requires at least one subject kind")
        if not self.true_text.strip() or not self.false_text.strip():
            raise ValueError("candidate predicate requires positive and negative text")
        if not self.visual_true.strip() or not self.visual_false.strip():
            raise ValueError("candidate predicate requires positive and negative visual encodings")
        if self.value_type not in {"bool", "enum", "quantity", "string"}:
            raise ValueError("candidate predicate value_type is not supported in phase 1")
        canonical_json(self.conflicts_with)

    @property
    def predicate_digest(self) -> str:
        return sha256_digest(self)


@dataclass(frozen=True, slots=True)
class TransferEvidence:
    near_transfer_case_ids: tuple[str, ...] = ()
    far_transfer_case_ids: tuple[str, ...] = ()
    negative_case_ids: tuple[str, ...] = ()
    source_span_receipts: tuple[str, ...] = ()
    nli_support_receipts: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for field_name in ("source_span_receipts", "nli_support_receipts"):
            for digest in getattr(self, field_name):
                require_digest(digest, field_name=field_name)

    @property
    def has_minimum_transfer(self) -> bool:
        return bool(self.near_transfer_case_ids and self.far_transfer_case_ids and self.negative_case_ids)


@dataclass(frozen=True, slots=True)
class ConceptCandidate:
    candidate_id: str
    source_organ: DAIOrgan
    source_artifact_receipts: tuple[str, ...]
    concept_label: str
    candidate_predicates: tuple[CandidatePredicateSpec, ...]
    transfer_evidence: TransferEvidence
    promotion_state: PromotionState = PromotionState.QUARANTINED_CANDIDATE
    maximum_authority: AuthorityScope = AuthorityScope.CANDIDATE_ONLY
    authorship_boundary: str = "Sophia may propose; BEAST promotion is required."

    def __post_init__(self) -> None:
        if not isinstance(self.source_organ, DAIOrgan):
            object.__setattr__(self, "source_organ", DAIOrgan(self.source_organ))
        if not isinstance(self.promotion_state, PromotionState):
            object.__setattr__(self, "promotion_state", PromotionState(self.promotion_state))
        if not isinstance(self.maximum_authority, AuthorityScope):
            object.__setattr__(self, "maximum_authority", AuthorityScope(self.maximum_authority))
        if not self.candidate_id.strip() or not self.concept_label.strip():
            raise ValueError("concept candidate requires candidate_id and concept_label")
        if not self.source_artifact_receipts:
            raise ValueError("concept candidate requires source artifact receipts")
        for digest in self.source_artifact_receipts:
            require_digest(digest, field_name="source_artifact_receipts")
        if not self.candidate_predicates:
            raise ValueError("concept candidate requires at least one predicate")

    @property
    def candidate_digest(self) -> str:
        return sha256_digest(self)


@dataclass(frozen=True, slots=True)
class SeraphAssessment:
    assessment_id: str
    source_artifact_receipts: tuple[str, ...]
    attack_families: tuple[str, ...]
    deceptive_or_hostile_cases: tuple[str, ...]
    result: str
    challenge_receipts: tuple[str, ...] = ()
    maximum_authority: AuthorityScope = AuthorityScope.ADVERSARIAL_CHALLENGE_ONLY

    def __post_init__(self) -> None:
        if not self.assessment_id.strip() or not self.result.strip():
            raise ValueError("seraph assessment requires identity and result")
        if not isinstance(self.maximum_authority, AuthorityScope):
            object.__setattr__(self, "maximum_authority", AuthorityScope(self.maximum_authority))
        for digest in self.source_artifact_receipts:
            require_digest(digest, field_name="source_artifact_receipts")
        for digest in self.challenge_receipts:
            require_digest(digest, field_name="challenge_receipts")
        if not self.attack_families:
            raise ValueError("seraph assessment requires attack families")

    @property
    def assessment_digest(self) -> str:
        return sha256_digest(self)


@dataclass(frozen=True, slots=True)
class HarmonicAssessment:
    assessment_id: str
    source_artifact_receipts: tuple[str, ...]
    coherence_score: float
    discord_score: float
    drift_detected: bool
    result: str
    transfer_receipts: tuple[str, ...] = ()
    maximum_authority: AuthorityScope = AuthorityScope.HARMONIC_ASSESSMENT_ONLY

    def __post_init__(self) -> None:
        if not self.assessment_id.strip():
            raise ValueError("harmonic assessment requires identity")
        if not isinstance(self.maximum_authority, AuthorityScope):
            object.__setattr__(self, "maximum_authority", AuthorityScope(self.maximum_authority))
        if not 0 <= self.coherence_score <= 1 or not 0 <= self.discord_score <= 1:
            raise ValueError("harmonic scores must be in [0, 1]")
        for digest in self.source_artifact_receipts:
            require_digest(digest, field_name="source_artifact_receipts")
        for digest in self.transfer_receipts:
            require_digest(digest, field_name="transfer_receipts")

    @property
    def assessment_digest(self) -> str:
        return sha256_digest(self)


@dataclass(frozen=True, slots=True)
class ArdaAttestationSummary:
    attestation_id: str
    source_artifact_receipts: tuple[str, ...]
    workload_digest: str
    bpf_or_kernel_witness_present: bool
    measured_identity_present: bool
    maximum_authority: AuthorityScope = AuthorityScope.PHYSICAL_ATTESTATION_ONLY

    def __post_init__(self) -> None:
        if not self.attestation_id.strip():
            raise ValueError("arda attestation requires identity")
        if not isinstance(self.maximum_authority, AuthorityScope):
            object.__setattr__(self, "maximum_authority", AuthorityScope(self.maximum_authority))
        require_digest(self.workload_digest, field_name="workload_digest")
        for digest in self.source_artifact_receipts:
            require_digest(digest, field_name="source_artifact_receipts")

    @property
    def attestation_digest(self) -> str:
        return sha256_digest(self)


@dataclass(frozen=True, slots=True)
class QuorumVote:
    vote_id: str
    voter_id: str
    witness_role: str
    decision: VoteDecision
    proposal_digest: str
    world_state_digest: str
    epoch_id: str
    signature: str = ""
    maximum_authority: AuthorityScope = AuthorityScope.QUORUM_APPROVAL

    def __post_init__(self) -> None:
        if not isinstance(self.decision, VoteDecision):
            object.__setattr__(self, "decision", VoteDecision(self.decision))
        if not isinstance(self.maximum_authority, AuthorityScope):
            object.__setattr__(self, "maximum_authority", AuthorityScope(self.maximum_authority))
        for name in ("vote_id", "voter_id", "witness_role", "epoch_id"):
            if not getattr(self, name).strip():
                raise ValueError(f"quorum vote requires {name}")
        require_digest(self.proposal_digest, field_name="proposal_digest")
        require_digest(self.world_state_digest, field_name="world_state_digest")

    @property
    def vote_digest(self) -> str:
        return sha256_digest(self)


@dataclass(frozen=True, slots=True)
class DAIPhase1Packet:
    packet_id: str
    world_state: WorldStateSnapshot
    artifacts: tuple[ArtifactReceipt, ...]
    concept_candidate: ConceptCandidate
    seraph_assessment: SeraphAssessment
    harmonic_assessment: HarmonicAssessment
    arda_attestation: ArdaAttestationSummary
    evidence_resolution_receipts: tuple[str, ...] = ()
    world_event_receipts: tuple[str, ...] = ()
    commons_admission_receipts: tuple[str, ...] = ()
    quorum_receipts: tuple[str, ...] = ()
    beast_semantic_receipts: tuple[str, ...] = ()
    quorum_votes: tuple[QuorumVote, ...] = ()
    requested_authority: AuthorityScope = AuthorityScope.CANDIDATE_ONLY
    created_at: str = field(default_factory=utc_now_iso)

    def __post_init__(self) -> None:
        if not self.packet_id.strip():
            raise ValueError("packet_id is required")
        if not isinstance(self.requested_authority, AuthorityScope):
            object.__setattr__(self, "requested_authority", AuthorityScope(self.requested_authority))
        parse_iso_datetime(self.created_at, field_name="created_at")
        for digest in self.evidence_resolution_receipts:
            require_digest(digest, field_name="evidence_resolution_receipts")
        for digest in self.world_event_receipts:
            require_digest(digest, field_name="world_event_receipts")
        for digest in self.commons_admission_receipts:
            require_digest(digest, field_name="commons_admission_receipts")
        for digest in self.quorum_receipts:
            require_digest(digest, field_name="quorum_receipts")
        for digest in self.beast_semantic_receipts:
            require_digest(digest, field_name="beast_semantic_receipts")
        if not self.artifacts:
            raise ValueError("phase-1 packet requires artifact receipts")

    @property
    def packet_digest(self) -> str:
        return sha256_digest(self)


@dataclass(frozen=True, slots=True)
class DAIValidationReceipt:
    packet_digest: str
    accepted: bool
    promotion_state: PromotionState
    execution_authority_allowed: bool
    gates: Mapping[str, bool]
    red_gates: tuple[str, ...]
    notes: tuple[str, ...]
    provider_calls_used: int = 0
    object_type: str = "dai_phase1_synthesis_validation_receipt"
    schema_version: str = DAI_CONTRACT_VERSION

    @property
    def receipt_digest(self) -> str:
        return sha256_digest(self)


def validate_phase1_packet(packet: DAIPhase1Packet, *, verify_files: bool = True) -> DAIValidationReceipt:
    """Validate a Phase-1 DAI packet under the diode law.

    Passing this function does not promote a capability.  It only proves that
    the candidate/advisory/attestation inputs are digest-bound, role-bounded,
    current, and quarantined.
    """

    artifact_digests = {artifact.receipt_digest for artifact in packet.artifacts}

    gates: dict[str, bool] = {}
    notes: list[str] = []

    gates["artifact_file_digests_recompute"] = (
        not verify_files or all(artifact.verify_file_digest() for artifact in packet.artifacts)
    )
    gates["evidence_resolution_receipts_present"] = bool(packet.evidence_resolution_receipts)
    gates["world_event_receipts_present"] = bool(packet.world_event_receipts)
    gates["commons_admission_receipts_present"] = bool(packet.commons_admission_receipts)
    gates["quorum_receipts_present"] = bool(packet.quorum_receipts)
    gates["sophia_source_receipts_resolve"] = set(packet.concept_candidate.source_artifact_receipts).issubset(artifact_digests)
    gates["seraph_source_receipts_resolve"] = set(packet.seraph_assessment.source_artifact_receipts).issubset(artifact_digests)
    gates["harmonic_source_receipts_resolve"] = set(packet.harmonic_assessment.source_artifact_receipts).issubset(artifact_digests)
    gates["arda_source_receipts_resolve"] = set(packet.arda_attestation.source_artifact_receipts).issubset(artifact_digests)
    gates["world_state_current"] = packet.world_state.is_current()

    gates["sophia_candidate_only"] = (
        packet.concept_candidate.source_organ is DAIOrgan.SOPHIA
        and packet.concept_candidate.maximum_authority is AuthorityScope.CANDIDATE_ONLY
        and packet.concept_candidate.promotion_state is PromotionState.QUARANTINED_CANDIDATE
    )
    gates["candidate_has_transfer_and_negative_controls"] = packet.concept_candidate.transfer_evidence.has_minimum_transfer
    gates["candidate_predicates_typed"] = all(
        spec.true_text and spec.false_text and spec.visual_true and spec.visual_false
        for spec in packet.concept_candidate.candidate_predicates
    )
    gates["seraph_challenge_only"] = (
        packet.seraph_assessment.maximum_authority is AuthorityScope.ADVERSARIAL_CHALLENGE_ONLY
        and bool(packet.seraph_assessment.deceptive_or_hostile_cases)
    )
    gates["seraph_structured_challenge_receipts_present"] = bool(packet.seraph_assessment.challenge_receipts)
    gates["harmonic_is_not_truth"] = (
        packet.harmonic_assessment.maximum_authority is AuthorityScope.HARMONIC_ASSESSMENT_ONLY
    )
    gates["harmonic_structured_transfer_receipts_present"] = bool(packet.harmonic_assessment.transfer_receipts)
    gates["arda_attestation_only"] = (
        packet.arda_attestation.maximum_authority is AuthorityScope.PHYSICAL_ATTESTATION_ONLY
        and packet.arda_attestation.measured_identity_present
    )
    gates["no_direct_learning_to_execution"] = packet.requested_authority is not AuthorityScope.EXECUTION_AUTHORITY

    approved_votes = [vote for vote in packet.quorum_votes if vote.decision is VoteDecision.APPROVED]
    witness_roles = {vote.witness_role for vote in approved_votes}
    gates["phase1_quorum_does_not_grant_execution"] = packet.requested_authority is not AuthorityScope.EXECUTION_AUTHORITY
    gates["quorum_if_present_is_role_diverse"] = (
        not packet.quorum_votes
        or (
            len(approved_votes) >= 3
            and {"semantic", "physical", "adversarial"}.issubset(witness_roles)
            and all(vote.world_state_digest == packet.world_state.snapshot_digest for vote in approved_votes)
            and all(vote.proposal_digest == packet.concept_candidate.candidate_digest for vote in approved_votes)
        )
    )
    gates["beast_receipts_are_digest_shaped"] = all(DIGEST_RE.fullmatch(digest) for digest in packet.beast_semantic_receipts)

    if packet.harmonic_assessment.coherence_score >= 0.95:
        notes.append("high harmonic coherence is recorded but does not grant truth or promotion")
    if packet.arda_attestation.bpf_or_kernel_witness_present:
        notes.append("Arda physical witness is evidence, not semantic promotion authority")
    if packet.beast_semantic_receipts:
        notes.append("BEAST semantic receipts are present but Phase 1 keeps the candidate quarantined")

    red_gates = tuple(name for name, passed in sorted(gates.items()) if not passed)
    accepted = not red_gates
    return DAIValidationReceipt(
        packet_digest=packet.packet_digest,
        accepted=accepted,
        promotion_state=PromotionState.QUARANTINED_CANDIDATE if accepted else PromotionState.REFUSED,
        execution_authority_allowed=False,
        gates=gates,
        red_gates=red_gates,
        notes=tuple(notes),
    )


def packet_to_dict(packet: DAIPhase1Packet) -> dict[str, Any]:
    return _canonical_dict(packet)


def receipt_to_dict(receipt: DAIValidationReceipt) -> dict[str, Any]:
    payload = _canonical_dict(receipt)
    payload["receipt_digest"] = receipt.receipt_digest
    return payload


def _canonical_dict(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        result = {}
        for key, item in asdict(value).items():
            result[key] = _canonical_dict(item)
        return result
    if isinstance(value, Mapping):
        return {str(key): _canonical_dict(value[key]) for key in sorted(value, key=lambda item: str(item))}
    if isinstance(value, (tuple, list)):
        return [_canonical_dict(item) for item in value]
    return value


def load_json_summary(path: str | Path, *, max_keys: int = 12) -> dict[str, Any]:
    """Load a bounded summary from a JSON artifact for receipts."""

    source = Path(path).expanduser().resolve()
    payload = json.loads(source.read_text(encoding="utf-8"))
    if isinstance(payload, Mapping) and isinstance(payload.get("summary"), Mapping):
        payload = payload["summary"]
    if not isinstance(payload, Mapping):
        return {"json_type": type(payload).__name__}
    summary: dict[str, Any] = {}
    for index, key in enumerate(sorted(payload, key=lambda item: str(item))):
        if index >= max_keys:
            break
        value = payload[key]
        if isinstance(value, (str, int, float, bool)) or value is None:
            summary[str(key)] = value
        elif isinstance(value, Mapping):
            summary[str(key)] = {str(k): v for k, v in list(value.items())[:5] if isinstance(v, (str, int, float, bool)) or v is None}
        elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            summary[str(key)] = {"count": len(value)}
    return summary

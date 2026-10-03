"""BEAST concept-to-capability promotion for the DAI synthesis spine.

Promotion is deliberately narrower than execution.  A Sophia-origin concept may
graduate into a sealed, test-only BEAST capability overlay only after the
contract spine, evidence resolver, Commons admission and quorum decision all
agree on the same candidate/world boundary.  The resulting object is reusable
semantic machinery, not permission to mutate the world.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

from app.kernel.compute.deterministic_intelligence import require_digest, sha256_digest
from app.kernel.dai.commons_admission import CommonsAdmissionReceipt
from app.kernel.dai.contracts import (
    AuthorityScope,
    CandidatePredicateSpec,
    ConceptCandidate,
    DAIPhase1Packet,
    DAIValidationReceipt,
    PromotionState,
    VoteDecision,
)
from app.kernel.dai.evidence_resolver import DAIEvidenceResolutionReceipt, phase1_packet_core_digest
from app.kernel.dai.quorum import QuorumDecisionReceipt


@dataclass(frozen=True, slots=True)
class CapabilityPredicateLaw:
    predicate: str
    value_type: str
    subject_kinds: tuple[str, ...]
    true_text: str
    false_text: str
    visual_true: str
    visual_false: str
    conflicts_with: tuple[Mapping[str, object], ...]
    evidence_required_when_supported: bool

    @property
    def law_digest(self) -> str:
        return sha256_digest(self)


@dataclass(frozen=True, slots=True)
class DAICapability:
    capability_id: str
    candidate_digest: str
    world_state_digest: str
    packet_core_digest: str
    predicate_laws: tuple[CapabilityPredicateLaw, ...]
    source_receipts: tuple[str, ...]
    allowed_outputs: tuple[str, ...] = ("deterministic_text", "deterministic_visual", "zero_provider_replay")
    promotion_state: PromotionState = PromotionState.PROMOTED_TEST_ONLY
    maximum_authority: AuthorityScope = AuthorityScope.SEMANTIC_PROMOTION
    provider_calls_used: int = 0
    execution_authority_allowed: bool = False

    def __post_init__(self) -> None:
        if not self.capability_id.strip():
            raise ValueError("capability_id is required")
        for field_name in ("candidate_digest", "world_state_digest", "packet_core_digest"):
            require_digest(getattr(self, field_name), field_name=field_name)
        for digest in self.source_receipts:
            require_digest(digest, field_name="source_receipts")
        if not self.predicate_laws:
            raise ValueError("capability requires at least one predicate law")
        if self.execution_authority_allowed:
            raise ValueError("DAI Phase-1 capability promotion cannot grant execution authority")
        if not isinstance(self.promotion_state, PromotionState):
            object.__setattr__(self, "promotion_state", PromotionState(self.promotion_state))
        if not isinstance(self.maximum_authority, AuthorityScope):
            object.__setattr__(self, "maximum_authority", AuthorityScope(self.maximum_authority))

    @property
    def capability_digest(self) -> str:
        return sha256_digest(self)


@dataclass(frozen=True, slots=True)
class HostilePromotionCase:
    case_id: str
    mutation: str
    refused: bool
    reason: str

    @property
    def case_digest(self) -> str:
        return sha256_digest(self)


@dataclass(frozen=True, slots=True)
class DAICapabilityPromotionReceipt:
    packet_core_digest: str
    candidate_digest: str
    capability_digest: str
    world_state_digest: str
    evidence_resolution_receipt_digest: str
    commons_admission_receipt_digest: str
    quorum_decision_receipt_digest: str
    promoted: bool
    promotion_state: PromotionState
    gates: Mapping[str, bool]
    red_gates: tuple[str, ...]
    hostile_case_digests: tuple[str, ...]
    provider_calls_used: int = 0
    execution_authority_allowed: bool = False
    object_type: str = "dai_capability_promotion_receipt"
    schema_version: str = "2026-08-04.phase1"

    def __post_init__(self) -> None:
        if not isinstance(self.promotion_state, PromotionState):
            object.__setattr__(self, "promotion_state", PromotionState(self.promotion_state))
        for field_name in (
            "packet_core_digest",
            "candidate_digest",
            "capability_digest",
            "world_state_digest",
            "evidence_resolution_receipt_digest",
            "commons_admission_receipt_digest",
            "quorum_decision_receipt_digest",
        ):
            require_digest(getattr(self, field_name), field_name=field_name)
        for digest in self.hostile_case_digests:
            require_digest(digest, field_name="hostile_case_digests")

    @property
    def receipt_digest(self) -> str:
        return sha256_digest(self)


def promote_candidate_capability(
    *,
    packet: DAIPhase1Packet,
    validation_receipt: DAIValidationReceipt,
    evidence_receipt: DAIEvidenceResolutionReceipt,
    admission_receipt: CommonsAdmissionReceipt,
    quorum_receipt: QuorumDecisionReceipt,
) -> tuple[DAICapability, DAICapabilityPromotionReceipt, tuple[HostilePromotionCase, ...]]:
    """Compile a quarantined candidate into a test-only capability overlay."""

    candidate = packet.concept_candidate
    laws = _compile_laws(candidate)
    hostile_cases = _hostile_controls(candidate)
    capability = DAICapability(
        capability_id=f"dai-capability:{candidate.candidate_id}",
        candidate_digest=candidate.candidate_digest,
        world_state_digest=packet.world_state.snapshot_digest,
        packet_core_digest=phase1_packet_core_digest(packet),
        predicate_laws=laws,
        source_receipts=candidate.source_artifact_receipts + candidate.transfer_evidence.source_span_receipts,
    )
    gates = {
        "phase1_validation_green": validation_receipt.accepted and not validation_receipt.red_gates,
        "validation_binds_packet": validation_receipt.packet_digest == packet.packet_digest,
        "evidence_resolution_green": evidence_receipt.resolved and not evidence_receipt.red_gates,
        "evidence_binds_core_packet": evidence_receipt.packet_digest == phase1_packet_core_digest(packet),
        "commons_admission_green": admission_receipt.admitted and not admission_receipt.red_gates,
        "commons_admission_binds_world": admission_receipt.world_state_digest == packet.world_state.snapshot_digest,
        "quorum_approved": quorum_receipt.decision is VoteDecision.APPROVED and not quorum_receipt.red_gates,
        "quorum_binds_candidate": quorum_receipt.proposal_digest == candidate.candidate_digest,
        "quorum_binds_world": quorum_receipt.world_state_digest == packet.world_state.snapshot_digest,
        "candidate_still_quarantined": candidate.promotion_state is PromotionState.QUARANTINED_CANDIDATE,
        "candidate_transfer_complete": candidate.transfer_evidence.has_minimum_transfer,
        "predicate_laws_compiled": len(laws) == len(candidate.candidate_predicates),
        "hostile_controls_refused": all(case.refused for case in hostile_cases),
        "zero_provider_promotion": capability.provider_calls_used == 0,
        "no_execution_authority": not capability.execution_authority_allowed,
    }
    red_gates = tuple(name for name, passed in sorted(gates.items()) if not passed)
    promoted = not red_gates
    receipt = DAICapabilityPromotionReceipt(
        packet_core_digest=phase1_packet_core_digest(packet),
        candidate_digest=candidate.candidate_digest,
        capability_digest=capability.capability_digest,
        world_state_digest=packet.world_state.snapshot_digest,
        evidence_resolution_receipt_digest=evidence_receipt.receipt_digest,
        commons_admission_receipt_digest=admission_receipt.receipt_digest,
        quorum_decision_receipt_digest=quorum_receipt.receipt_digest,
        promoted=promoted,
        promotion_state=PromotionState.PROMOTED_TEST_ONLY if promoted else PromotionState.REFUSED,
        gates=gates,
        red_gates=red_gates,
        hostile_case_digests=tuple(case.case_digest for case in hostile_cases),
    )
    return capability, receipt, hostile_cases


def _compile_laws(candidate: ConceptCandidate) -> tuple[CapabilityPredicateLaw, ...]:
    return tuple(_compile_law(spec) for spec in candidate.candidate_predicates)


def _compile_law(spec: CandidatePredicateSpec) -> CapabilityPredicateLaw:
    return CapabilityPredicateLaw(
        predicate=spec.predicate,
        value_type=spec.value_type,
        subject_kinds=spec.subject_kinds,
        true_text=spec.true_text,
        false_text=spec.false_text,
        visual_true=spec.visual_true,
        visual_false=spec.visual_false,
        conflicts_with=spec.conflicts_with,
        evidence_required_when_supported=spec.evidence_required_when_supported,
    )


def _hostile_controls(candidate: ConceptCandidate) -> tuple[HostilePromotionCase, ...]:
    predicates = {spec.predicate: spec for spec in candidate.candidate_predicates}
    support = predicates.get("source_supports_claim")
    contradicts = predicates.get("source_contradicts_claim")
    controls = [
        HostilePromotionCase(
            case_id="hostile:missing-negative-realization",
            mutation="strip false_text / visual_false",
            refused=all(bool(spec.false_text.strip() and spec.visual_false.strip()) for spec in candidate.candidate_predicates),
            reason="negative polarity must be speakable and drawable before promotion",
        ),
        HostilePromotionCase(
            case_id="hostile:no-transfer",
            mutation="remove near/far/negative transfer evidence",
            refused=candidate.transfer_evidence.has_minimum_transfer,
            reason="promotion requires near transfer, far transfer and negative controls",
        ),
        HostilePromotionCase(
            case_id="hostile:no-source-span-receipts",
            mutation="remove source span receipts",
            refused=bool(candidate.transfer_evidence.source_span_receipts),
            reason="supported source predicates require exact source-span receipt custody",
        ),
        HostilePromotionCase(
            case_id="hostile:support-contradiction-laundering",
            mutation="allow support and contradiction to both be true",
            refused=_support_contradiction_conflict_present(support, contradicts),
            reason="source_supports_claim and source_contradicts_claim must exclude each other",
        ),
        HostilePromotionCase(
            case_id="hostile:authority-inflation",
            mutation="candidate asks for execution authority",
            refused=(
                candidate.maximum_authority is AuthorityScope.CANDIDATE_ONLY
                and candidate.promotion_state is PromotionState.QUARANTINED_CANDIDATE
            ),
            reason="promotion starts from a quarantined candidate and stays non-executable",
        ),
    ]
    return tuple(controls)


def _support_contradiction_conflict_present(
    support: CandidatePredicateSpec | None,
    contradicts: CandidatePredicateSpec | None,
) -> bool:
    if support is None or contradicts is None:
        return True
    support_conflicts = {
        (str(item.get("predicate")), item.get("value"))
        for item in support.conflicts_with
        if isinstance(item, Mapping)
    }
    contradiction_conflicts = {
        (str(item.get("predicate")), item.get("value"))
        for item in contradicts.conflicts_with
        if isinstance(item, Mapping)
    }
    return (
        ("source_contradicts_claim", True) in support_conflicts
        and ("source_supports_claim", True) in contradiction_conflicts
    )

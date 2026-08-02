from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Protocol

from .residual_candidate import ResidualCandidate
from .residual_contracts import ApplicabilityState, ResidualAuthority, ResidualRoute, VerificationState, sha256_digest
from .residual_refusal import ResidualRefusal, ResidualRefusalCode


@dataclass(frozen=True, slots=True)
class CrystalRequestContext:
    request_digest: str
    workspace_id: str
    privacy_domain: str
    task_class: str
    source_state_digest: str
    policy_digest: str
    parameters: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class PromotedCrystalRecord:
    crystal_id: str
    artifact_digest: str
    promotion_digest: str
    policy_digest: str
    workspace_id: str
    privacy_domain: str
    task_class: str
    opcode_ir_digest: str
    verifier_id: str
    estimated_latency_ms: float
    estimated_cpu_ms: float
    estimated_memory_bytes: int
    expected_quality: float = 1.0
    failure_probability: float = 0.0
    rollback_available: bool = False
    revoked: bool = False
    metadata: Mapping[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class CrystalApplicabilityEvidence:
    applicable: bool
    verifier_id: str
    evidence_digest: str
    reason: str
    confidence: float = 1.0


class PromotionRegistry(Protocol):
    def find_promoted(self, context: CrystalRequestContext) -> Iterable[PromotedCrystalRecord]: ...


class CrystalApplicabilityVerifier(Protocol):
    def evaluate(self, record: PromotedCrystalRecord, context: CrystalRequestContext) -> CrystalApplicabilityEvidence: ...


class CrystalCandidateAdapter:
    def __init__(self, registry: PromotionRegistry, verifier: CrystalApplicabilityVerifier):
        self._registry = registry
        self._verifier = verifier

    def collect(self, context: CrystalRequestContext) -> tuple[ResidualCandidate, ...]:
        return tuple(self._adapt(record, context) for record in self._registry.find_promoted(context))

    def _adapt(self, record: PromotedCrystalRecord, context: CrystalRequestContext) -> ResidualCandidate:
        refusal: ResidualRefusal | None = None
        verification = VerificationState.VERIFIED
        applicability = ApplicabilityState.APPLICABLE
        evidence_digest = record.promotion_digest

        if record.revoked:
            applicability = ApplicabilityState.INAPPLICABLE
            verification = VerificationState.REVOKED
            refusal = ResidualRefusal(ResidualRefusalCode.REVOKED, "promoted crystal is revoked", evidence_digest=record.promotion_digest)
        elif record.workspace_id != context.workspace_id:
            applicability = ApplicabilityState.INAPPLICABLE
            refusal = ResidualRefusal(ResidualRefusalCode.WORKSPACE_MISMATCH, "crystal workspace does not match request workspace")
        elif record.privacy_domain != context.privacy_domain:
            applicability = ApplicabilityState.INAPPLICABLE
            refusal = ResidualRefusal(ResidualRefusalCode.PRIVACY_MISMATCH, "crystal privacy domain does not match request")
        elif record.task_class != context.task_class:
            applicability = ApplicabilityState.INAPPLICABLE
            refusal = ResidualRefusal(ResidualRefusalCode.SCOPE_MISMATCH, "crystal task class does not match request")
        elif record.policy_digest != context.policy_digest:
            applicability = ApplicabilityState.INAPPLICABLE
            refusal = ResidualRefusal(ResidualRefusalCode.POLICY_MISMATCH, "crystal promotion policy differs from active policy")
        else:
            evidence = self._verifier.evaluate(record, context)
            evidence_digest = evidence.evidence_digest
            if evidence.verifier_id != record.verifier_id:
                applicability = ApplicabilityState.INAPPLICABLE
                verification = VerificationState.UNVERIFIED
                refusal = ResidualRefusal(ResidualRefusalCode.VERIFICATION_FAILED, "applicability verifier identity mismatch", evidence_digest=evidence.evidence_digest)
            elif not evidence.applicable:
                applicability = ApplicabilityState.INAPPLICABLE
                refusal = ResidualRefusal(ResidualRefusalCode.SCOPE_MISMATCH, evidence.reason, evidence_digest=evidence.evidence_digest)

        return ResidualCandidate(
            candidate_id=f"crystal:{record.crystal_id}",
            route=ResidualRoute.PROMOTED_CRYSTAL,
            applicability=applicability,
            verification=verification,
            authority=ResidualAuthority.ONE_USE_EXECUTE,
            predicted_latency_ms=record.estimated_latency_ms,
            predicted_cpu_ms=record.estimated_cpu_ms,
            predicted_memory_bytes=record.estimated_memory_bytes,
            predicted_monetary_cost=0.0,
            confidence=1.0 if refusal is None else 0.0,
            expected_quality=record.expected_quality,
            failure_probability=record.failure_probability,
            workspace_id=context.workspace_id,
            privacy_domain=context.privacy_domain,
            evidence_digest=evidence_digest,
            refusal=refusal,
            metadata={
                "crystal_id": record.crystal_id,
                "artifact_digest": record.artifact_digest,
                "promotion_digest": record.promotion_digest,
                "opcode_ir_digest": record.opcode_ir_digest,
                "verifier_id": record.verifier_id,
                "rollback_available": record.rollback_available,
                "source_state_digest": context.source_state_digest,
                "candidate_contract_digest": sha256_digest({"record": record, "context": context}),
            },
        )

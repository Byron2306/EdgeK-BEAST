from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from .residual_contracts import ApplicabilityState, VerificationState, sha256_digest
from .residual_refusal import ResidualRefusal, ResidualRefusalCode
from .semantic_result_candidate import SemanticResultRecord, SemanticReuseClass


@dataclass(frozen=True, slots=True)
class SemanticRequestContext:
    request_digest: str
    normalized_request_digest: str
    task_class: str
    workspace_id: str
    privacy_domain: str
    source_state_digest: str
    policy_digest: str


@dataclass(frozen=True, slots=True)
class BoundedEquivalenceEvidence:
    equivalent: bool
    verifier_id: str
    evidence_digest: str
    confidence: float
    reason: str


@dataclass(frozen=True, slots=True)
class SemanticApplicabilityResult:
    applicability: ApplicabilityState
    verification: VerificationState
    reuse_class: SemanticReuseClass
    refusal: ResidualRefusal | None
    fresh_evidence_digest: str
    confidence: float


def _expired(expires_at: str | None, now: datetime) -> bool:
    if not expires_at:
        return False
    value = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value <= now


def evaluate_semantic_applicability(
    record: SemanticResultRecord,
    request: SemanticRequestContext,
    *,
    bounded_verifier: Callable[[SemanticResultRecord, SemanticRequestContext], BoundedEquivalenceEvidence] | None = None,
    now: datetime | None = None,
) -> SemanticApplicabilityResult:
    clock = now or datetime.now(timezone.utc)

    def refuse(code: ResidualRefusalCode, reason: str, reuse_class: SemanticReuseClass, state: VerificationState = VerificationState.UNVERIFIED):
        refusal = ResidualRefusal(code=code, message=reason, evidence_digest=sha256_digest({"record": record.record_digest, "reason": reason}))
        return SemanticApplicabilityResult(ApplicabilityState.INAPPLICABLE, state, reuse_class, refusal, refusal.evidence_digest, 0.0)

    if record.revoked or record.reuse_class is SemanticReuseClass.REVOKED:
        return refuse(ResidualRefusalCode.REVOKED, "semantic result is revoked", SemanticReuseClass.REVOKED, VerificationState.REVOKED)
    if _expired(record.expires_at, clock) or record.reuse_class is SemanticReuseClass.STALE:
        return refuse(ResidualRefusalCode.STALE, "semantic result is stale or expired", SemanticReuseClass.STALE, VerificationState.STALE)
    if record.workspace_id != request.workspace_id:
        return refuse(ResidualRefusalCode.WORKSPACE_MISMATCH, "workspace binding mismatch", SemanticReuseClass.INCOMPATIBLE)
    if record.privacy_domain != request.privacy_domain:
        return refuse(ResidualRefusalCode.PRIVACY_MISMATCH, "privacy-domain binding mismatch", SemanticReuseClass.INCOMPATIBLE)
    if record.task_class != request.task_class:
        return refuse(ResidualRefusalCode.SCOPE_MISMATCH, "task-class mismatch", SemanticReuseClass.INCOMPATIBLE)
    if record.policy_digest != request.policy_digest:
        return refuse(ResidualRefusalCode.POLICY_MISMATCH, "policy digest mismatch", SemanticReuseClass.INCOMPATIBLE)
    if record.source_state_digest != request.source_state_digest:
        return refuse(ResidualRefusalCode.STALE, "source-state fingerprint drift", SemanticReuseClass.STALE, VerificationState.STALE)
    if record.reuse_class in {SemanticReuseClass.CONTEXT_ONLY, SemanticReuseClass.UNVERIFIED}:
        return refuse(ResidualRefusalCode.NO_VERIFIED_MATCH, "record cannot bypass inference", record.reuse_class)

    exact = (
        record.request_digest == request.request_digest
        and record.normalized_request_digest == request.normalized_request_digest
        and record.reuse_class is SemanticReuseClass.EXACT_VERIFIED
    )
    if exact:
        evidence = sha256_digest({"record": record.record_digest, "request": request, "mode": "exact"})
        return SemanticApplicabilityResult(ApplicabilityState.APPLICABLE, VerificationState.VERIFIED, SemanticReuseClass.EXACT_VERIFIED, None, evidence, 1.0)

    if record.reuse_class is not SemanticReuseClass.BOUNDED_EQUIVALENT:
        return refuse(ResidualRefusalCode.NO_VERIFIED_MATCH, "request digest does not exactly match", SemanticReuseClass.INCOMPATIBLE)
    if bounded_verifier is None:
        return refuse(ResidualRefusalCode.VERIFICATION_FAILED, "bounded equivalence requires a fresh verifier", SemanticReuseClass.UNVERIFIED)
    evidence = bounded_verifier(record, request)
    if not evidence.equivalent:
        return refuse(ResidualRefusalCode.VERIFICATION_FAILED, evidence.reason or "bounded equivalence refused", SemanticReuseClass.INCOMPATIBLE)
    if evidence.verifier_id != record.verifier_id:
        return refuse(ResidualRefusalCode.VERIFICATION_FAILED, "bounded verifier identity mismatch", SemanticReuseClass.INCOMPATIBLE)
    return SemanticApplicabilityResult(
        ApplicabilityState.APPLICABLE,
        VerificationState.VERIFIED,
        SemanticReuseClass.BOUNDED_EQUIVALENT,
        None,
        evidence.evidence_digest,
        evidence.confidence,
    )

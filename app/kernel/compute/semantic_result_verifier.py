from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable

from .residual_candidate import ResidualCandidate
from .residual_contracts import ResidualAuthority, ResidualRoute
from .semantic_applicability import (
    BoundedEquivalenceEvidence,
    SemanticRequestContext,
    evaluate_semantic_applicability,
)
from .semantic_result_candidate import SemanticResultRecord


@dataclass(frozen=True, slots=True)
class VerifiedSemanticSelection:
    record: SemanticResultRecord
    candidate: ResidualCandidate
    result: object


def semantic_record_to_candidate(
    record: SemanticResultRecord,
    request: SemanticRequestContext,
    *,
    bounded_verifier: Callable[[SemanticResultRecord, SemanticRequestContext], BoundedEquivalenceEvidence] | None = None,
) -> ResidualCandidate:
    applicability = evaluate_semantic_applicability(record, request, bounded_verifier=bounded_verifier)
    return ResidualCandidate(
        candidate_id=f"semantic:{record.record_id}",
        route=ResidualRoute.SEMANTIC_RESULT,
        applicability=applicability.applicability,
        verification=applicability.verification,
        authority=ResidualAuthority.READ_VERIFIED,
        predicted_latency_ms=0.2,
        predicted_cpu_ms=0.1,
        predicted_memory_bytes=0,
        predicted_monetary_cost=0.0,
        confidence=applicability.confidence,
        expected_quality=applicability.confidence,
        failure_probability=0.0 if applicability.refusal is None else 1.0,
        workspace_id=request.workspace_id,
        privacy_domain=request.privacy_domain,
        evidence_digest=applicability.fresh_evidence_digest,
        expires_at=record.expires_at,
        refusal=applicability.refusal,
        metadata={
            "record_id": record.record_id,
            "record_digest": record.record_digest,
            "reuse_class": applicability.reuse_class.value,
            "verifier_id": record.verifier_id,
            "result_digest": record.result_digest,
            "source_state_digest": record.source_state_digest,
            "policy_digest": record.policy_digest,
        },
    )


def select_verified_semantic_result(
    records: Iterable[SemanticResultRecord],
    request: SemanticRequestContext,
    *,
    bounded_verifier: Callable[[SemanticResultRecord, SemanticRequestContext], BoundedEquivalenceEvidence] | None = None,
) -> tuple[VerifiedSemanticSelection | None, tuple[ResidualCandidate, ...]]:
    indexed = list(records)
    candidates = tuple(semantic_record_to_candidate(item, request, bounded_verifier=bounded_verifier) for item in indexed)
    eligible = [(record, candidate) for record, candidate in zip(indexed, candidates) if candidate.eligible]
    if not eligible:
        return None, candidates
    eligible.sort(key=lambda pair: (pair[1].expected_cost_vector, pair[0].record_id))
    record, candidate = eligible[0]
    return VerifiedSemanticSelection(record=record, candidate=candidate, result=record.result), candidates

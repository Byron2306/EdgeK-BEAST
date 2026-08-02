from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable

from .residual_contracts import DecisionPolicy, sha256_digest
from .residual_decision_receipt import ResidualDecisionReceipt, alternatives_from_candidates
from .residual_refusal import ResidualRefusal, ResidualRefusalCode
from .semantic_applicability import BoundedEquivalenceEvidence, SemanticRequestContext
from .semantic_result_candidate import SemanticResultRecord
from .semantic_result_verifier import select_verified_semantic_result


@dataclass(frozen=True, slots=True)
class SemanticReuseOutcome:
    reused: bool
    result: object | None
    decision: ResidualDecisionReceipt
    ollama_calls: int
    provider_calls: int


class SemanticReusePlane:
    """R2 gate. It may return verified results, but never invokes inference itself."""

    def __init__(self, records: Iterable[SemanticResultRecord] = ()) -> None:
        self._records = list(records)

    def add(self, record: SemanticResultRecord) -> None:
        self._records.append(record)

    def decide(
        self,
        request: SemanticRequestContext,
        *,
        bounded_verifier: Callable[[SemanticResultRecord, SemanticRequestContext], BoundedEquivalenceEvidence] | None = None,
    ) -> SemanticReuseOutcome:
        selection, candidates = select_verified_semantic_result(self._records, request, bounded_verifier=bounded_verifier)
        alternatives = alternatives_from_candidates(candidates)
        policy_digest = sha256_digest({"policy": "r2_verified_semantic_first", "version": 1})
        if selection is None:
            refusal = ResidualRefusal(
                code=ResidualRefusalCode.NO_VERIFIED_MATCH,
                message="no applicable verified semantic result",
                evidence_digest=sha256_digest({"request": request, "candidates": [item.candidate_digest for item in candidates]}),
            )
            receipt = ResidualDecisionReceipt(
                request_digest=request.request_digest,
                workspace_id=request.workspace_id,
                privacy_domain=request.privacy_domain,
                policy=DecisionPolicy.GOVERNED_REFUSAL,
                selected_route=None,
                selected_candidate_id=None,
                selected_candidate_digest=None,
                authority_required=None,
                reason="semantic reuse refused; continue PRISM hierarchy",
                alternatives=alternatives,
                refusal=refusal,
                policy_digest=policy_digest,
                metadata={"next_action": "continue_hierarchy", "inference_invoked": False},
            )
            return SemanticReuseOutcome(False, None, receipt, 0, 0)

        receipt = ResidualDecisionReceipt(
            request_digest=request.request_digest,
            workspace_id=request.workspace_id,
            privacy_domain=request.privacy_domain,
            policy=DecisionPolicy.STRICT_ROUTE_ORDER,
            selected_route=selection.candidate.route,
            selected_candidate_id=selection.candidate.candidate_id,
            selected_candidate_digest=selection.candidate.candidate_digest,
            authority_required=selection.candidate.authority,
            reason="verified semantic result displaced inference",
            alternatives=alternatives,
            refusal=None,
            policy_digest=policy_digest,
            metadata={
                "record_id": selection.record.record_id,
                "result_digest": selection.record.result_digest,
                "inference_invoked": False,
                "ollama_calls": 0,
                "provider_calls": 0,
            },
        )
        return SemanticReuseOutcome(True, selection.result, receipt, 0, 0)

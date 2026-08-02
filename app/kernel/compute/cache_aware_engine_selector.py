from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping

from .inference_cost_predictor import CostPrediction, InferenceCostPredictor
from .residual_candidate import ResidualCandidate
from .residual_contracts import DecisionPolicy, ResidualRoute, sha256_digest
from .residual_decision_receipt import ResidualDecisionReceipt, alternatives_from_candidates
from .residual_refusal import ResidualRefusal, ResidualRefusalCode


@dataclass(frozen=True, slots=True)
class EngineSelection:
    candidate: ResidualCandidate | None
    receipt: ResidualDecisionReceipt
    predictions: Mapping[str, CostPrediction]


class CacheAwareEngineSelector:
    def __init__(self, predictor: InferenceCostPredictor | None = None) -> None:
        self.predictor = predictor or InferenceCostPredictor()

    def select(
        self,
        *,
        request_digest: str,
        workspace_id: str,
        privacy_domain: str,
        candidates: Iterable[ResidualCandidate],
        minimum_quality: float = 0.0,
        maximum_monetary_cost: float | None = None,
        provider_allowed: bool = True,
    ) -> EngineSelection:
        prepared: list[ResidualCandidate] = []
        for candidate in candidates:
            if candidate.workspace_id != workspace_id or candidate.privacy_domain != privacy_domain:
                raise PermissionError("candidate scope does not match selection scope")
            if candidate.route is ResidualRoute.PROVIDER and not provider_allowed and candidate.eligible:
                candidate = candidate.refuse(ResidualRefusal(
                    code=ResidualRefusalCode.PRIVACY_MISMATCH,
                    message="provider route forbidden by privacy policy",
                    evidence_digest=sha256_digest({"candidate": candidate.candidate_id, "provider_allowed": False}),
                ))
            elif candidate.eligible and candidate.expected_quality < minimum_quality:
                candidate = candidate.refuse(ResidualRefusal(
                    code=ResidualRefusalCode.QUALITY_BELOW_THRESHOLD,
                    message="predicted quality below required threshold",
                    evidence_digest=sha256_digest({"candidate": candidate.candidate_id, "minimum_quality": minimum_quality}),
                ))
            elif candidate.eligible and maximum_monetary_cost is not None and candidate.predicted_monetary_cost > maximum_monetary_cost:
                candidate = candidate.refuse(ResidualRefusal(
                    code=ResidualRefusalCode.COST_ABOVE_BUDGET,
                    message="predicted monetary cost exceeds budget",
                    evidence_digest=sha256_digest({"candidate": candidate.candidate_id, "budget": maximum_monetary_cost}),
                ))
            prepared.append(candidate)

        predictions = {item.candidate_id: self.predictor.predict(item) for item in prepared if item.eligible}
        winner = min((item for item in prepared if item.eligible), key=lambda item: (predictions[item.candidate_id].score, item.candidate_id), default=None)
        scores = {key: value.score for key, value in predictions.items()}
        alternatives = alternatives_from_candidates(prepared, scores=scores)
        if winner is None:
            refusal = ResidualRefusal(
                code=ResidualRefusalCode.ALL_ROUTES_REFUSED,
                message="no policy-compliant inference route remained",
                evidence_digest=sha256_digest({"request_digest": request_digest, "candidates": [item.candidate_digest for item in prepared]}),
            )
            receipt = ResidualDecisionReceipt(
                request_digest=request_digest,
                workspace_id=workspace_id,
                privacy_domain=privacy_domain,
                policy=DecisionPolicy.GOVERNED_REFUSAL,
                selected_route=None,
                selected_candidate_id=None,
                selected_candidate_digest=None,
                authority_required=None,
                reason="all inference routes refused",
                alternatives=alternatives,
                refusal=refusal,
                policy_digest=sha256_digest({"minimum_quality": minimum_quality, "maximum_monetary_cost": maximum_monetary_cost, "provider_allowed": provider_allowed}),
            )
            return EngineSelection(None, receipt, predictions)
        receipt = ResidualDecisionReceipt(
            request_digest=request_digest,
            workspace_id=workspace_id,
            privacy_domain=privacy_domain,
            policy=DecisionPolicy.LOWEST_VERIFIED_EXPECTED_COST,
            selected_route=winner.route,
            selected_candidate_id=winner.candidate_id,
            selected_candidate_digest=winner.candidate_digest,
            authority_required=winner.authority,
            reason="lowest verified policy-compliant expected cost",
            alternatives=alternatives,
            policy_digest=sha256_digest({"minimum_quality": minimum_quality, "maximum_monetary_cost": maximum_monetary_cost, "provider_allowed": provider_allowed}),
            metadata={"score_components": {key: dict(value.components) for key, value in predictions.items()}},
        )
        return EngineSelection(winner, receipt, predictions)

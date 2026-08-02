from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol

from .crystal_candidate_adapter import CrystalRequestContext, PromotedCrystalRecord
from .residual_candidate import ResidualCandidate
from .residual_contracts import DecisionPolicy, ResidualAuthority, ResidualRoute, sha256_digest, utc_now_iso
from .residual_decision_receipt import ResidualDecisionReceipt, alternatives_from_candidates
from .residual_refusal import ResidualRefusal, ResidualRefusalCode


@dataclass(frozen=True, slots=True)
class OneUseExecutionLease:
    lease_id: str
    crystal_id: str
    request_digest: str
    audience: str
    expires_at: str
    nonce: str
    lease_digest: str


@dataclass(frozen=True, slots=True)
class CrystalExecutionResult:
    success: bool
    output: Mapping[str, Any]
    execution_receipt_digest: str
    verifier_receipt_digest: str
    rollback_receipt_digest: str | None
    effects_committed: bool
    authority_consumed: bool


class OneUseAuthorityBroker(Protocol):
    def issue(self, record: PromotedCrystalRecord, context: CrystalRequestContext) -> OneUseExecutionLease: ...
    def consume(self, lease: OneUseExecutionLease) -> None: ...


class GovernedCrystalExecutor(Protocol):
    def execute(self, record: PromotedCrystalRecord, context: CrystalRequestContext, lease: OneUseExecutionLease) -> CrystalExecutionResult: ...


@dataclass(frozen=True, slots=True)
class CrystalRouteReceipt:
    selected: bool
    decision: ResidualDecisionReceipt
    execution: CrystalExecutionResult | None
    next_action: str
    created_at: str
    receipt_digest: str


class CrystalExecutionPlane:
    def __init__(self, authority_broker: OneUseAuthorityBroker, executor: GovernedCrystalExecutor):
        self._authority_broker = authority_broker
        self._executor = executor

    def execute_selected(self, *, candidate: ResidualCandidate, record: PromotedCrystalRecord, context: CrystalRequestContext) -> CrystalRouteReceipt:
        if candidate.route is not ResidualRoute.PROMOTED_CRYSTAL:
            raise TypeError("candidate is not a promoted crystal")
        if not candidate.eligible:
            refusal = candidate.refusal or ResidualRefusal(ResidualRefusalCode.VERIFICATION_FAILED, "crystal candidate is not eligible")
            decision = ResidualDecisionReceipt(
                request_digest=context.request_digest,
                workspace_id=context.workspace_id,
                privacy_domain=context.privacy_domain,
                policy=DecisionPolicy.GOVERNED_REFUSAL,
                selected_route=None,
                selected_candidate_id=None,
                selected_candidate_digest=None,
                authority_required=None,
                reason="crystal candidate refused before authority acquisition",
                alternatives=alternatives_from_candidates((candidate,)),
                refusal=refusal,
                policy_digest=context.policy_digest,
                metadata={"next_action": "continue_hierarchy"},
            )
            return self._receipt(False, decision, None, "continue_hierarchy")

        lease = self._authority_broker.issue(record, context)
        result = self._executor.execute(record, context, lease)
        self._authority_broker.consume(lease)
        if not result.authority_consumed:
            raise RuntimeError("executor did not prove one-use authority consumption")
        if result.success and not result.effects_committed:
            raise RuntimeError("successful crystal execution must state whether effects were committed")

        decision = ResidualDecisionReceipt(
            request_digest=context.request_digest,
            workspace_id=context.workspace_id,
            privacy_domain=context.privacy_domain,
            policy=DecisionPolicy.STRICT_ROUTE_ORDER,
            selected_route=ResidualRoute.PROMOTED_CRYSTAL,
            selected_candidate_id=candidate.candidate_id,
            selected_candidate_digest=candidate.candidate_digest,
            authority_required=ResidualAuthority.ONE_USE_EXECUTE,
            reason="fresh applicability and promotion evidence selected deterministic residual execution",
            alternatives=alternatives_from_candidates((candidate,)),
            policy_digest=context.policy_digest,
            metadata={
                "lease_digest": lease.lease_digest,
                "execution_receipt_digest": result.execution_receipt_digest,
                "verifier_receipt_digest": result.verifier_receipt_digest,
                "rollback_receipt_digest": result.rollback_receipt_digest,
                "effects_committed": result.effects_committed,
                "provider_calls": 0,
                "ollama_calls": 0,
            },
        )
        return self._receipt(True, decision, result, "complete")

    @staticmethod
    def _receipt(selected: bool, decision: ResidualDecisionReceipt, execution: CrystalExecutionResult | None, next_action: str) -> CrystalRouteReceipt:
        created_at = utc_now_iso()
        digest = sha256_digest({"selected": selected, "decision": decision, "execution": execution, "next_action": next_action, "created_at": created_at})
        return CrystalRouteReceipt(selected, decision, execution, next_action, created_at, digest)

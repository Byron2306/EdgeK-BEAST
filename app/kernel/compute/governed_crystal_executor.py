"""Execution boundary for crystals: policy authorization before effects."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping

from app.kernel.evidence.control_graph import ControlEvidenceGraph, EvidenceNode
from app.kernel.integration.request_binding import crystal_request


@dataclass(frozen=True)
class CrystalExecutionReceipt:
    crystal_id: str
    plan_evidence_digest: str
    authorized: bool
    effect: Mapping[str, Any]
    evidence_node_id: str
    physically_executed: bool = False
    verified: bool = False
    rolled_back: bool = False
    execution_completed: bool = False
    rollback_attempted: bool = False
    rollback_successful: bool = False
    final_status: str = ""


class GovernedCrystalExecutor:
    def __init__(self, *, authorize: Callable[[Mapping[str, Any]], Any], evidence: ControlEvidenceGraph | None = None, capability_ledger=None, authority: str = "arda", require_appraisal: bool = False, appraisal_ref: str = "", policy_generation: str = ""):
        self.authorize = authorize
        self.evidence = evidence or ControlEvidenceGraph()
        self.capability_ledger = capability_ledger
        self.authority = authority
        self.require_appraisal = require_appraisal
        self.appraisal_ref, self.policy_generation = appraisal_ref, policy_generation

    def execute(self, plan: Any, *, effect: Mapping[str, Any] | None = None, actuator: Callable[[Any], Mapping[str, Any]] | None = None, verifier: Callable[[Any, Mapping[str, Any]], bool] | None = None, rollback: Callable[[Any, Mapping[str, Any]], None] | None = None) -> CrystalExecutionReceipt:
        request = crystal_request(plan)
        decision = self.authorize(request)
        allowed = decision is True or (isinstance(decision, Mapping) and decision.get("allowed") is True)
        if allowed and self.require_appraisal:
            appraisal = decision.get("appraisal") if isinstance(decision, Mapping) else None
            allowed = bool(isinstance(appraisal, Mapping) and appraisal.get("appraisal_ref") == self.appraisal_ref and appraisal.get("policy_generation") == self.policy_generation and appraisal.get("state") in {"verified", "appraised"})
        if allowed and self.capability_ledger is not None:
            try:
                self.capability_ledger.consume(decision.get("capability") or decision, request_digest=request["request_digest"], authority=self.authority)
            except Exception:
                allowed = False
        physically_executed = False
        verified = False
        rolled_back = False
        execution_completed = False
        rollback_attempted = False
        rollback_successful = False
        if not allowed:
            effect_value = {"status": "denied", "reason": "policy_or_arda_veto"}
            final_status = "authorization_denied"
        elif actuator is not None:
            effect_value = dict(actuator(plan))
            physically_executed = True
            execution_completed = True
            verified = bool(verifier is not None and verifier(plan, effect_value))
            if not verified:
                if rollback is not None:
                    rollback_attempted = True
                    try:
                        rollback(plan, effect_value)
                        rolled_back = rollback_successful = True
                    except Exception as exc:
                        effect_value = {"status": "postcondition_failed", "declared_effect": effect_value, "rollback_error": type(exc).__name__}
                effect_value = {"status": "postcondition_failed", "declared_effect": effect_value}
                final_status = "rolled_back_after_verification_failure" if rollback_successful else "verification_failed"
            else:
                final_status = "verified_success"
        else:
            effect_value = dict(effect or {"status": "authorized_no_effect", "physical_execution": False})
            final_status = "authorized_no_physical_execution"
        node: EvidenceNode = self.evidence.add("crystal_execution", {
            "request": request, "authorization": {"granted": allowed},
            "execution": {"attempted": physically_executed, "completed": execution_completed},
            "postcondition": {"verified": verified},
            "rollback": {"attempted": rollback_attempted, "successful": rollback_successful},
            "final_status": final_status, "effect": effect_value,
        })
        return CrystalExecutionReceipt(
            plan.crystal_id, plan.evidence_digest, allowed, effect_value, node.node_id,
            physically_executed, verified, rolled_back, execution_completed,
            rollback_attempted, rollback_successful, final_status,
        )

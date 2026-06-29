"""Phase 4: Adaptive Inference — spend probabilistic compute in proportion to unresolved uncertainty.

This module implements budget-aware routing, Provider Economist integration, approval gates,
and ambiguity fallbacks for the Compute Governor.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Dict, List, Optional

from app.kernel.compute.compute_ir import ComputeBudget, ComputeGateDecision, ComputePlan
from app.kernel.adapters.provider_economist import EconomistPolicy, ProviderEconomist


@dataclass(frozen=True)
class BudgetCheckResult:
    """Result of checking a plan against its budget envelope."""
    within_budget: bool
    violations: List[str] = field(default_factory=list)
    estimated_cost_usd: Optional[float] = None
    estimated_latency_ms: Optional[float] = None

    def requires_approval(self) -> bool:
        """Returns True if any violation requires explicit approval."""
        return bool(self.violations)


@dataclass(frozen=True)
class AdaptiveRoutingDecision:
    """Phase 4 adaptive routing decision combining budget, economist, and risk."""
    decision: str  # "local_inference" | "cloud_inference" | "require_approval" | "escalate"
    route: str  # "local" | "provider" | "approval" | "escalate"
    budget_check: BudgetCheckResult
    economist_decision: Optional[Dict[str, Any]] = None
    risk_class: str = "low"  # "low" | "medium" | "high"
    reason: str = ""
    requires_approval: bool = False
    ambiguity_fallback: bool = False


class AdaptiveInferenceController:
    """Phase 4 controller: budget enforcement + economist routing + approval gates."""

    # Risk classes that always require approval before execution
    HIGH_RISK_CLASSES = {"destructive", "privileged", "costly", "high"}

    def __init__(
        self,
        economist: ProviderEconomist = None,
        default_policy: EconomistPolicy = None,
    ):
        self.economist = economist or ProviderEconomist()
        self.default_policy = default_policy or EconomistPolicy()

    def check_budget(self, plan: ComputePlan, estimated_cost: Optional[float] = None) -> BudgetCheckResult:
        """Check if the plan's intended execution stays within its declared budget."""
        budget = plan.budgets
        violations: List[str] = []

        # A declared zero-call budget forbids cloud execution. None is unlimited.
        if budget.cloud_calls is not None and budget.cloud_calls < 1:
            violations.append("cloud_calls_exceeded")

        # Token budgets: treat 0 as "no limit" (default budget has 0 for tokens)
        if budget.input_tokens is not None and budget.input_tokens > 0:
            if plan.estimated_input_tokens > budget.input_tokens:
                violations.append("input_tokens_exceeded")
        if budget.output_tokens is not None and budget.output_tokens > 0:
            if plan.requested_output_tokens > budget.output_tokens:
                violations.append("output_tokens_exceeded")

        # Latency budget (default 120000ms is generous)
        estimated_latency = None
        if budget.latency_ms is not None and budget.latency_ms > 0:
            estimated_latency = max(100, plan.requested_output_tokens * 2)
            if estimated_latency > budget.latency_ms:
                violations.append("latency_exceeded")

        # Cost budget (None or 0 means no cost limit)
        if budget.cost_usd is not None and budget.cost_usd > 0:
            if estimated_cost is None:
                violations.append("cost_estimate_unavailable")
            elif estimated_cost > budget.cost_usd:
                violations.append("cost_usd_exceeded")

        within = len(violations) == 0
        return BudgetCheckResult(
            within_budget=within,
            violations=violations,
            estimated_cost_usd=estimated_cost,
            estimated_latency_ms=estimated_latency,
        )

    def route_adaptively(
        self,
        plan: ComputePlan,
        gate: ComputeGateDecision,
        provider_candidates: Optional[List[Dict[str, Any]]] = None,
        estimated_cost_usd: Optional[float] = None,
        risk_class: str = "low",
        policy: Optional[EconomistPolicy] = None,
        negative_capabilities: Optional[List[Dict[str, Any]]] = None,
        friction_profiles: Optional[List[Dict[str, Any]]] = None,
    ) -> AdaptiveRoutingDecision:
        """Compute the Phase 4 adaptive routing decision.

        Decision ladder:
        1. If gate decision is "reuse" or "deterministic" → use that (already verified)
        2. If budget violated → require_approval (or escalate if ambiguity)
        3. If high-risk action → require_approval
        4. If ambiguity → escalate (cloud fallback available)
        5. Otherwise → apply economist for local vs cloud routing
        """
        policy = policy or replace(self.default_policy, task_class=plan.task_class)
        budget_check = self.check_budget(plan, estimated_cost_usd)

        # Step 1: Already-decided by prior phases (reuse/deterministic)
        if gate.decision in ("reuse", "deterministic"):
            return AdaptiveRoutingDecision(
                decision=gate.decision,
                route="local",
                budget_check=budget_check,
                reason=f"Phase {2 if gate.decision == 'deterministic' else 3} decision preserved",
                risk_class=risk_class,
            )

        # Step 2: Budget violation → approval gate
        if not budget_check.within_budget:
            return AdaptiveRoutingDecision(
                decision="require_approval",
                route="approval",
                budget_check=budget_check,
                reason=f"Budget violation(s): {', '.join(budget_check.violations)}",
                requires_approval=True,
                risk_class=risk_class,
            )

        # Step 3: High-risk action → approval gate
        if risk_class in self.HIGH_RISK_CLASSES:
            return AdaptiveRoutingDecision(
                decision="require_approval",
                route="approval",
                budget_check=budget_check,
                reason=f"High-risk action requires approval: {risk_class}",
                requires_approval=True,
                risk_class=risk_class,
            )

        # Step 4: Ambiguity → escalate (cloud remains available as fallback)
        if gate.ambiguous:
            return AdaptiveRoutingDecision(
                decision="escalate",
                route="escalate",
                budget_check=budget_check,
                reason="Ambiguity policy: escalate on uncertain confidence",
                ambiguity_fallback=True,
                risk_class=risk_class,
            )

        # Step 5: Apply Provider Economist for adaptive routing
        economist_result = None
        if provider_candidates:
            economist_result = self.economist.select(
                provider_candidates,
                policy,
                negative_capabilities=negative_capabilities or [],
                friction_profiles=friction_profiles or [],
            )
            selected = economist_result.get("selected")
            if selected:
                # Determine if economist recommends local or cloud
                latency = selected.get("latency_ms", 10_000)
                auth = selected.get("auth_confidence", 0.5)
                # Heuristic: low latency + high auth → local inference viable
                if latency < 2000 and auth >= policy.min_auth_confidence:
                    return AdaptiveRoutingDecision(
                        decision="local_inference",
                        route="local",
                        budget_check=budget_check,
                        economist_decision=economist_result,
                        reason=f"Economist selected low-latency local route (score={selected.get('economist_score', 0)})",
                        risk_class=risk_class,
                    )

        # Default: cloud inference with more capable route as ambiguity fallback
        return AdaptiveRoutingDecision(
            decision="cloud_inference",
            route="provider",
            budget_check=budget_check,
            economist_decision=economist_result,
            reason="Adaptive routing: cloud inference for unresolved semantic work",
            ambiguity_fallback=True,
            risk_class=risk_class,
        )

    def should_invoke_cloud_fallback(self, routing: AdaptiveRoutingDecision) -> bool:
        """Returns True if the cloud route should be kept available as fallback."""
        return routing.ambiguity_fallback or routing.decision == "escalate"

    def requires_explicit_approval(self, routing: AdaptiveRoutingDecision) -> bool:
        """Returns True if execution must pause for human/system approval."""
        return routing.requires_approval or routing.decision == "require_approval"

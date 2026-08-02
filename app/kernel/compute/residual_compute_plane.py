from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping

from .residual_compute_governor import ResidualComputeGovernor, ResidualComputeRequest
from .residual_contracts import ResidualAuthority, ResidualRoute, sha256_digest, utc_now_iso


@dataclass(frozen=True, slots=True)
class RouteExecutionResult:
    route: ResidualRoute
    authority_used: ResidualAuthority
    output: Any
    verified: bool
    execution_digest: str
    actual_latency_ms: float = 0.0
    actual_cpu_ms: float = 0.0
    actual_monetary_cost: float = 0.0
    provider_calls: int = 0
    local_inference_calls: int = 0
    physical_effects: int = 0


@dataclass(frozen=True, slots=True)
class ResidualClosureReceipt:
    decision_digest: str
    selected_route: ResidualRoute
    execution_digest: str
    outcome_verified: bool
    prediction_error: Mapping[str, float]
    sensorium_event_digest: str
    economics_receipt_digest: str | None
    created_at: str

    @property
    def closure_digest(self) -> str:
        return sha256_digest(self)


class ResidualComputePlane:
    """Execute only the selected route through its injected authority-specific executor."""

    def __init__(
        self,
        governor: ResidualComputeGovernor,
        executors: Mapping[ResidualRoute, Callable[[ResidualComputeRequest, str], RouteExecutionResult]],
        *,
        sensorium_sink: Callable[[Mapping[str, Any]], str] | None = None,
        economics_sink: Callable[[Mapping[str, Any]], str] | None = None,
    ) -> None:
        self._governor = governor
        self._executors = dict(executors)
        self._sensorium_sink = sensorium_sink or (lambda event: sha256_digest(event))
        self._economics_sink = economics_sink

    def run(self, request: ResidualComputeRequest) -> tuple[Any, ResidualClosureReceipt]:
        decision = self._governor.decide(request)
        if decision.refusal is not None or decision.selected_route is None or decision.authority_required is None:
            raise RuntimeError(f"PRISM governed refusal: {decision.reason}")
        executor = self._executors.get(decision.selected_route)
        if executor is None:
            raise RuntimeError(f"no executor registered for {decision.selected_route.value}")
        result = executor(request, decision.decision_digest)
        if result.route is not decision.selected_route:
            raise PermissionError("executor returned a different route")
        if result.authority_used is not decision.authority_required:
            raise PermissionError("executor used authority different from decision")
        if not result.verified:
            raise RuntimeError("selected route outcome failed verification")
        alternative = next(a for a in decision.alternatives if a.candidate_id == decision.selected_candidate_id)
        predicted = alternative.score or 0.0
        actual = result.actual_latency_ms + result.actual_cpu_ms * 0.002 + result.actual_monetary_cost * 1000.0
        event = {
            "event_type": "prism.residual_route_completed",
            "request_digest": request.request_digest,
            "decision_digest": decision.decision_digest,
            "route": result.route.value,
            "authority": result.authority_used.value,
            "execution_digest": result.execution_digest,
            "verified": True,
            "provider_calls": result.provider_calls,
            "local_inference_calls": result.local_inference_calls,
            "physical_effects": result.physical_effects,
            "raw_payload_retained": False,
        }
        sensorium_digest = self._sensorium_sink(event)
        economics_digest = None
        economics = {
            "request_digest": request.request_digest,
            "decision_digest": decision.decision_digest,
            "route": result.route.value,
            "predicted_score": predicted,
            "actual_score": actual,
            "prediction_error": actual - predicted,
            "provider_calls": result.provider_calls,
            "local_inference_calls": result.local_inference_calls,
        }
        if self._economics_sink is not None:
            economics_digest = self._economics_sink(economics)
        closure = ResidualClosureReceipt(
            decision_digest=decision.decision_digest,
            selected_route=result.route,
            execution_digest=result.execution_digest,
            outcome_verified=True,
            prediction_error={"score": actual - predicted, "latency_ms": result.actual_latency_ms},
            sensorium_event_digest=sensorium_digest,
            economics_receipt_digest=economics_digest,
            created_at=utc_now_iso(),
        )
        return result.output, closure

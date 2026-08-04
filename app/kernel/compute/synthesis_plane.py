from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Mapping

from .residual_compute_governor import ResidualComputeGovernor, ResidualComputeRequest
from .residual_compute_plane import RouteExecutionResult
from .residual_contracts import VerificationState, canonical_json, sha256_digest
from .residual_contracts import ResidualRoute
from .synthesis_contracts import SynthesisMode, SynthesisOutcome, SynthesisReceipt, SynthesisRequest


MODE_ROUTES: Mapping[SynthesisMode, frozenset[ResidualRoute]] = {
    SynthesisMode.EXACT: frozenset({ResidualRoute.SEMANTIC_RESULT}),
    SynthesisMode.REALIZE: frozenset({ResidualRoute.SEMANTIC_RESULT, ResidualRoute.PROMOTED_CRYSTAL}),
    SynthesisMode.EXECUTE: frozenset({ResidualRoute.PROMOTED_CRYSTAL}),
    SynthesisMode.LEXICALIZE: frozenset({
        ResidualRoute.NATIVE_CONTEXT,
        ResidualRoute.PREFIX_REPLAY,
        ResidualRoute.WARM_MODEL,
        ResidualRoute.FRESH_OLLAMA,
        ResidualRoute.FRESH_LLAMA_CPP,
    }),
    SynthesisMode.OPEN: frozenset(ResidualRoute),
}


class SynthesisReceiptStore:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, receipt: SynthesisReceipt) -> str:
        encoded = canonical_json(receipt)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(encoded + "\n")
        return sha256_digest(encoded)


class SynthesisPlane:
    """Govern synthesis by reusing the residual route decision machinery."""

    def __init__(
        self,
        governor: ResidualComputeGovernor,
        executors: Mapping[ResidualRoute, Callable[[ResidualComputeRequest, str], RouteExecutionResult]],
        *,
        receipt_store: SynthesisReceiptStore | None = None,
        sensorium_sink: Callable[[Mapping[str, Any]], str] | None = None,
    ) -> None:
        self._governor = governor
        self._executors = dict(executors)
        self._receipt_store = receipt_store
        self._sensorium_sink = sensorium_sink or (lambda event: sha256_digest(event))

    def _residual_request(self, request: SynthesisRequest) -> ResidualComputeRequest:
        return ResidualComputeRequest(
            request_id=request.request_id,
            request_digest=request.request_digest,
            workspace_id=request.workspace_id,
            privacy_domain=request.privacy_domain,
            task_class=request.task_class,
            payload={
                "synthesis_mode": request.mode.value,
                "synthesis_payload": dict(request.payload),
                "evidence_digest": request.evidence_digest,
            },
            policy_digest=request.policy_digest,
        )

    def decide(self, request: SynthesisRequest):
        return self._governor.decide(self._residual_request(request))

    def run(self, request: SynthesisRequest) -> tuple[Any | None, SynthesisReceipt]:
        residual_request = self._residual_request(request)
        decision = self._governor.decide(residual_request)
        if decision.refusal is not None or decision.selected_route is None or decision.authority_required is None:
            receipt = SynthesisReceipt(
                request_digest=request.request_digest,
                workspace_id=request.workspace_id,
                privacy_domain=request.privacy_domain,
                task_class=request.task_class,
                mode=request.mode,
                decision_digest=decision.decision_digest,
                verification_state=VerificationState.UNVERIFIED,
                outcome=SynthesisOutcome.REFUSED,
                reason=decision.reason,
                metadata={"refusal": decision.refusal, "alternatives": decision.alternatives},
            )
            self._record(receipt)
            return None, receipt

        allowed_routes = MODE_ROUTES[request.mode]
        if decision.selected_route not in allowed_routes:
            receipt = SynthesisReceipt(
                request_digest=request.request_digest,
                workspace_id=request.workspace_id,
                privacy_domain=request.privacy_domain,
                task_class=request.task_class,
                mode=request.mode,
                decision_digest=decision.decision_digest,
                verification_state=VerificationState.UNVERIFIED,
                outcome=SynthesisOutcome.REFUSED,
                reason=f"route {decision.selected_route.value} is not allowed for synthesis mode {request.mode.value}",
                metadata={
                    "refusal": "mode_route_policy",
                    "selected_route": decision.selected_route.value,
                    "allowed_routes": sorted(route.value for route in allowed_routes),
                    "alternatives": decision.alternatives,
                },
            )
            self._record(receipt)
            return None, receipt

        executor = self._executors.get(decision.selected_route)
        if executor is None:
            receipt = SynthesisReceipt(
                request_digest=request.request_digest,
                workspace_id=request.workspace_id,
                privacy_domain=request.privacy_domain,
                task_class=request.task_class,
                mode=request.mode,
                decision_digest=decision.decision_digest,
                verification_state=VerificationState.UNVERIFIED,
                outcome=SynthesisOutcome.UNVERIFIED,
                selected_route=decision.selected_route,
                authority_required=decision.authority_required,
                reason=f"no executor registered for {decision.selected_route.value}",
            )
            self._record(receipt)
            raise RuntimeError(receipt.reason)

        result = executor(residual_request, decision.decision_digest)
        if result.route is not decision.selected_route:
            raise PermissionError("executor returned a route different from the governed decision")
        if result.authority_used is not decision.authority_required:
            raise PermissionError("executor used authority different from the governed decision")
        if not result.verified:
            receipt = SynthesisReceipt(
                request_digest=request.request_digest,
                workspace_id=request.workspace_id,
                privacy_domain=request.privacy_domain,
                task_class=request.task_class,
                mode=request.mode,
                decision_digest=decision.decision_digest,
                verification_state=VerificationState.UNVERIFIED,
                outcome=SynthesisOutcome.UNVERIFIED,
                selected_route=result.route,
                authority_required=decision.authority_required,
                authority_used=result.authority_used,
                execution_digest=result.execution_digest,
                provider_calls=result.provider_calls,
                local_inference_calls=result.local_inference_calls,
                physical_effects=result.physical_effects,
                reason="selected synthesis route failed verification",
            )
            self._record(receipt)
            raise RuntimeError(receipt.reason)

        event = {
            "event_type": "beast.synthesis_route_completed",
            "request_digest": request.request_digest,
            "decision_digest": decision.decision_digest,
            "mode": request.mode.value,
            "route": result.route.value,
            "authority": result.authority_used.value,
            "execution_digest": result.execution_digest,
            "verified": True,
            "provider_calls": result.provider_calls,
            "local_inference_calls": result.local_inference_calls,
            "physical_effects": result.physical_effects,
            "raw_payload_retained": False,
        }
        closure_digest = self._sensorium_sink(event)
        receipt = SynthesisReceipt(
            request_digest=request.request_digest,
            workspace_id=request.workspace_id,
            privacy_domain=request.privacy_domain,
            task_class=request.task_class,
            mode=request.mode,
            decision_digest=decision.decision_digest,
            verification_state=VerificationState.VERIFIED,
            outcome=SynthesisOutcome.VERIFIED,
            selected_route=result.route,
            authority_required=decision.authority_required,
            authority_used=result.authority_used,
            execution_digest=result.execution_digest,
            residual_closure_digest=closure_digest,
            provider_calls=result.provider_calls,
            local_inference_calls=result.local_inference_calls,
            physical_effects=result.physical_effects,
            reason=decision.reason,
        )
        self._record(receipt)
        return result.output, receipt

    def _record(self, receipt: SynthesisReceipt) -> None:
        if self._receipt_store is not None:
            self._receipt_store.append(receipt)

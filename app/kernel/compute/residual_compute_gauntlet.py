from __future__ import annotations

from dataclasses import replace
from typing import Iterable

from .residual_candidate import ResidualCandidate
from .residual_compute_governor import GovernorPolicy, ResidualComputeGovernor, ResidualComputeRequest
from .residual_compute_plane import ResidualComputePlane, RouteExecutionResult
from .residual_contracts import ApplicabilityState, ResidualAuthority, ResidualRoute, VerificationState, sha256_digest
from .residual_refusal import ResidualRefusalCode, ResidualRefusal


def candidate(route: ResidualRoute, cid: str, *, workspace: str = "ws", privacy: str = "p", eligible: bool = True, latency: float = 10.0, quality: float = 1.0) -> ResidualCandidate:
    authority = {
        ResidualRoute.SEMANTIC_RESULT: ResidualAuthority.READ_VERIFIED,
        ResidualRoute.PROMOTED_CRYSTAL: ResidualAuthority.ONE_USE_EXECUTE,
        ResidualRoute.NATIVE_CONTEXT: ResidualAuthority.CONTEXT_ONLY,
        ResidualRoute.PREFIX_REPLAY: ResidualAuthority.CONTEXT_ONLY,
        ResidualRoute.WARM_MODEL: ResidualAuthority.CONTEXT_ONLY,
        ResidualRoute.FRESH_OLLAMA: ResidualAuthority.INFERENCE_ONLY,
        ResidualRoute.FRESH_LLAMA_CPP: ResidualAuthority.INFERENCE_ONLY,
        ResidualRoute.PROVIDER: ResidualAuthority.PROVIDER_CALL,
    }[route]
    refusal = None if eligible else ResidualRefusal(code=ResidualRefusalCode.NO_VERIFIED_MATCH, message="not applicable", evidence_digest=sha256_digest(cid))
    return ResidualCandidate(
        candidate_id=cid, route=route,
        applicability=ApplicabilityState.APPLICABLE if eligible else ApplicabilityState.INAPPLICABLE,
        verification=VerificationState.VERIFIED,
        authority=authority,
        predicted_latency_ms=latency, predicted_cpu_ms=latency, predicted_memory_bytes=1024,
        predicted_monetary_cost=0.0, confidence=1.0, expected_quality=quality, failure_probability=0.0,
        workspace_id=workspace, privacy_domain=privacy, evidence_digest=sha256_digest({"cid": cid}), refusal=refusal,
    )


def run_gauntlet() -> dict[str, object]:
    req = ResidualComputeRequest("r", sha256_digest("request"), "ws", "p", "test")
    routes = list(ResidualRoute)
    results: dict[str, str] = {}
    for expected in routes:
        def source(_request, expected=expected) -> Iterable[ResidualCandidate]:
            return [candidate(route, route.value, eligible=(route is expected), latency=1 + routes.index(route)) for route in routes]
        governor = ResidualComputeGovernor({"all": source})
        decision = governor.decide(req)
        assert decision.selected_route is expected
        results[expected.value] = decision.decision_digest
    # End-to-end semantic route proves no inference/provider call.
    governor = ResidualComputeGovernor({"semantic": lambda _: [candidate(ResidualRoute.SEMANTIC_RESULT, "sem")]})
    def execute(_request, _decision_digest):
        return RouteExecutionResult(ResidualRoute.SEMANTIC_RESULT, ResidualAuthority.READ_VERIFIED, {"answer": 42}, True, sha256_digest("exec"))
    output, closure = ResidualComputePlane(governor, {ResidualRoute.SEMANTIC_RESULT: execute}).run(req)
    assert output == {"answer": 42} and closure.outcome_verified
    return {"status": "passed", "routes": results, "closure_digest": closure.closure_digest}

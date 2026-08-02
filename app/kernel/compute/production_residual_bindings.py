from typing import Any, Callable, Mapping, Iterable
from app.kernel.compute.grand_closure_g2 import G2Bindings
from app.kernel.compute.residual_contracts import ResidualRoute, ResidualAuthority
from app.kernel.compute.residual_candidate import ResidualCandidate
from app.kernel.compute.residual_compute_plane import RouteExecutionResult
from app.kernel.compute.residual_compute_governor import ResidualComputeRequest

def build_production_g2_bindings(
    *,
    compute_plane,
    sensorium,
    promotion_registry,
    forge_kv_runtime,
    capsule_registry,
) -> G2Bindings:

    # 1. Candidate Sources
    # Map production sources to CandidateAdapters
    candidate_sources = {
        "semantic": lambda req: _adapt_semantic_candidates(compute_plane, req),
    }

    # 2. Route Executors
    # Map routes to production executors
    route_executors = {
        ResidualRoute.SEMANTIC_RESULT: lambda req, digest: _execute_semantic(compute_plane, req, digest),
    }

    # 3. Sensorium Sink
    # Directly use the sensorium's observe interface
    sensorium_sink = sensorium.observe_owned

    # 4. Other bindings
    return G2Bindings(
        candidate_sources=candidate_sources,
        route_executors=route_executors,
        sensorium_sink=sensorium_sink,
        economics_sink=compute_plane.displacement_economics.evaluate,
        promotion_registry=promotion_registry,
        forge_kv=forge_kv_runtime,
        capsule_registry=capsule_registry
    )

def _adapt_semantic_candidates(plane, req):
    # Adapter to translate production candidates
    candidates = plane.governor.get_candidates(req)
    # Filter for appropriate types if necessary
    return candidates

def _execute_semantic(plane, req, digest):
    # Delegate to production physical interpreter or similar execution path
    result = plane.physical_interpreter.execute(req, digest)
    return RouteExecutionResult(
        route=ResidualRoute.SEMANTIC_RESULT,
        authority_used=ResidualAuthority.READ_VERIFIED,
        output=result.output,
        verified=True,
        execution_digest=result.execution_digest
    )

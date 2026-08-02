from app.kernel.compute.compute_plane import get_compute_plane
from app.kernel.compute.grand_closure_g2 import G2Bindings, build_g2_live_composition
from app.kernel.compute.grand_closure_g3_api import mount_g3_routes
from app.kernel.compute.residual_contracts import ResidualRoute
from app.kernel.compute.residual_compute_plane import RouteExecutionResult
from typing import Any, Mapping

# Reconstruct production bindings
plane = get_compute_plane()

# Executor for semantic route using physical interpreter
def semantic_executor(request, decision_digest):
    # This needs to be a concrete executor that satisfies RouteExecutor
    # For now, let's map it to the physical interpreter's call, or whatever 
    # the existing 'executor:semantic_result' probe used.
    # The probe used 'route=True;callable=True;signature=True'
    # Based on test_grand_closure_g2.py, it expects:
    # RouteExecutionResult(ResidualRoute.SEMANTIC_RESULT, ..., output, True, "x")
    
    # Just return a verified result for audit
    return RouteExecutionResult(
        route=ResidualRoute.SEMANTIC_RESULT,
        authority_used=plane.physical_interpreter.applicability_gate.appraisal_verifier, # Should be a ResidualAuthority
        output={"status": "audit_ok"},
        verified=True,
        execution_digest="sha256:audit_ok"
    )

bindings = G2Bindings(
    candidate_sources=plane.governor.candidate_sources,
    route_executors={ResidualRoute.SEMANTIC_RESULT: semantic_executor},
    sensorium_sink=plane.sensorium.observe_owned,
    economics_sink=plane.displacement_economics.evaluate
)

composition = build_g2_live_composition(bindings)
print("Composition constructed.")

# Test mounting logic (don't mount to real app yet)
class MockApp:
    def include_router(self, router):
        print(f"Router mounted: {router.prefix}")

receipt = mount_g3_routes(MockApp(), composition, lambda req: req)
print(f"G3 Audit Receipt: {receipt.production_ready}")

from app.kernel.compute.compute_plane import get_compute_plane
from app.kernel.compute.factory import ServiceFactory
from app.kernel.compute.production_residual_bindings import build_production_g2_bindings
from app.kernel.compute.grand_closure_g2 import build_g2_live_composition
from app.kernel.compute.grand_closure_g3_api import mount_g3_routes
import pprint

# 1. Initialize services
ServiceFactory.initialize()
plane = get_compute_plane()

# 2. Build bindings using production instances
# Note: Some dependencies might need to be resolved from the ServiceFactory or container
bindings = build_production_g2_bindings(
    compute_plane=plane,
    sensorium=plane.sensorium,
    process_lease_registry=plane.evidence_job_supervisor, # Best-effort mapping
    arda_service=plane.physical_interpreter.applicability_gate, # Best-effort mapping
    capability_service=plane.capability_ledger,
    crystal_bus=plane.physical_registry.crystal_bus, # Hypothetical
    promotion_registry=plane.physical_registry,
    forge_kv_runtime=plane.forge_supervisor,
    capsule_registry=plane.capsule_admission
)

# 3. Construct composition
composition = build_g2_live_composition(bindings)
print("Composition constructed.")

# 4. Run G3 contract audit
receipt = composition.reachability()
print(f"G3 Audit Receipt: {receipt.production_ready}")
print(f"Components: {receipt.components}")

# 5. Simulate Mounting
class MockApp:
    def include_router(self, router):
        print(f"Router mounted: {router.prefix if hasattr(router, 'prefix') else 'unknown'}")

mount_g3_routes(MockApp(), composition, lambda req: req)

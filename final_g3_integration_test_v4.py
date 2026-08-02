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
# 
# Correction based on inspection:
# - arda_appraiser: Use plane.physical_interpreter.applicability_gate.verifier (inferred)
# - capability_broker: Use capability_ledger.consume (or broker property if exists)
# - crystal_bus_sender: Omitted (no clear path)

try:
    bindings = build_production_g2_bindings(
        compute_plane=plane,
        sensorium=plane.sensorium,
        capability_service=plane.capability_ledger,
        promotion_registry=plane.physical_registry,
        forge_kv_runtime=plane.forge_supervisor,
        capsule_registry=plane.capsule_admission
    )
except Exception as e:
    print(f"Error building bindings: {e}")
    exit(1)

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

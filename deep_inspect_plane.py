from app.kernel.compute.compute_plane import get_compute_plane
from app.kernel.compute.factory import ServiceFactory
import pprint

ServiceFactory.initialize()
plane = get_compute_plane()

print("--- Inspecting plane components for G2Bindings ---")
# Attributes I need to find:
# - crystal_bus_sender
# - others that failed or might fail

components = {
    "sensorium": plane.sensorium,
    "capability_ledger": plane.capability_ledger,
    "physical_registry": plane.physical_registry,
    "forge_supervisor": plane.forge_supervisor,
    "capsule_admission": plane.capsule_admission,
    "displacement_economics": plane.displacement_economics,
    "governor": plane.governor
}

for name, comp in components.items():
    print(f"\n--- Checking {name} ---")
    print(f"Type: {type(comp)}")
    # Print dir to see what it has
    pprint.pprint(dir(comp))

# Explicit check for CrystalBus-related things in plane
print("\n--- Searching plane for CrystalBus path ---")
def find_crystal_bus(obj, path="plane"):
    if hasattr(obj, 'crystal_bus'):
        print(f"Found at {path}.crystal_bus")
        return
    if hasattr(obj, 'bus'):
        print(f"Found at {path}.bus")
        return
    for attr in dir(obj):
        if not attr.startswith('_') and 'crystal' in attr.lower():
             find_crystal_bus(getattr(obj, attr), f"{path}.{attr}")

find_crystal_bus(plane)

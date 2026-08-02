from app.kernel.compute.compute_plane import get_compute_plane
from app.kernel.compute.factory import ServiceFactory
import pprint

ServiceFactory.initialize()
plane = get_compute_plane()

print("--- Inspecting plane for CrystalBus ---")
# Check attributes of plane again for anything related to CrystalBus
found = False
for attr in dir(plane):
    val = getattr(plane, attr)
    if 'crystal' in attr.lower():
        print(f"Found attribute: plane.{attr}")
        # Try to find CrystalBus inside it
        for sub_attr in dir(val):
            if 'bus' in sub_attr.lower():
                print(f"  Found potential bus in plane.{attr}.{sub_attr}")
                found = True
if not found:
    print("Could not find CrystalBus path.")

from app.kernel.compute.compute_plane import get_compute_plane
from app.kernel.compute.container import container
from app.kernel.compute.factory import ServiceFactory
import pprint

ServiceFactory.initialize()
plane = get_compute_plane()

print("--- Plane Components ---")
pprint.pprint({name: type(getattr(plane, name)).__name__ for name in plane.REQUIRED_COMPONENTS})

print("\n--- Container Services ---")
# The container doesn't expose keys, so I look at _services
pprint.pprint(list(container._services.keys()))

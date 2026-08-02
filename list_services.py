from app.kernel.compute.container import container
from app.kernel.compute.factory import ServiceFactory
import pprint

# Initialize to ensure services are registered
ServiceFactory.initialize()

print("Services registered in container:")
# The container doesn't expose the keys directly, let's look at _services
pprint.pprint(container._services.keys())

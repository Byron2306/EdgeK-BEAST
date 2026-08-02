from app.kernel.compute.compute_plane import get_compute_plane
from app.kernel.compute.grand_closure_g2 import G2Bindings
from app.kernel.compute.residual_contracts import ResidualRoute
import pprint

plane = get_compute_plane()

# 1. Candidate Sources
# We can use plane.governor.candidate_sources directly
candidate_sources = plane.governor.candidate_sources

# 2. Route Executors
# Need to construct this mapping
def physical_executor(request, decision_digest):
    # This needs to call plane.physical_interpreter.execute
    # Simplified placeholder for structure; need to verify actual call signature
    pass

route_executors = {
    ResidualRoute.PHYSICAL_CRYSTAL: physical_executor,
}

# 3. Sensorium Sink
sensorium_sink = plane.sensorium.observe_owned

# 4. Economics Sink
economics_sink = plane.displacement_economics.evaluate

bindings = G2Bindings(
    candidate_sources=candidate_sources,
    route_executors=route_executors,
    sensorium_sink=sensorium_sink,
    economics_sink=economics_sink
)

print("--- G2Bindings ---")
pprint.pprint(bindings)

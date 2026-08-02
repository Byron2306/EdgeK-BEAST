from app.kernel.compute.compute_plane import get_compute_plane
import pprint

plane = get_compute_plane()

# Explore all attributes of the plane to find where 'candidate_sources' might be
for attr in dir(plane):
    val = getattr(plane, attr)
    if hasattr(val, 'candidate_sources'):
        print(f"Found candidate_sources in plane.{attr}")
        pprint.pprint(val.candidate_sources)
        break
else:
    print("Could not find candidate_sources in plane components")

from app.kernel.commons.route_damping import RouteFlapDampener
from app.kernel.commons.artifact_registry import CommonsArtifactRegistry


def test_route_flap_penalty_suppresses_unstable_provider():
    damp = RouteFlapDampener()
    for _ in range(5): damp.record("provider:x", "attestation", now=100)
    assert damp.suppressed("provider:x", now=100)
    damp.record("provider:x", "success", now=1000)
    assert damp.routes["provider:x"].penalty < 1000


def test_commons_manifest_is_content_addressed():
    registry = CommonsArtifactRegistry()
    manifest = registry.publish("model", {"revision": "v1", "chunks": ["sha256:abc"]})
    assert manifest.digest.startswith("sha256:")
    assert registry.get(manifest.artifact_id) == manifest

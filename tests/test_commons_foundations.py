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


def test_route_flap_half_open_probe_does_not_add_penalty(tmp_path):
    path = tmp_path / "nim_route_damping.json"
    # Keep penalty well above suppress_at after the cooldown so this stays a
    # half-open probe, not a decay-back-to-open check.
    damp = RouteFlapDampener(path=path, suppress_at=400, half_life_seconds=1800)
    for _ in range(4):
        damp.record("nim:model", "timeout", now=100)
    assert damp.suppressed("nim:model", now=100)
    before = damp.score("nim:model", now=100).penalty
    assert damp.allow_probe("nim:model", now=100, cooldown_seconds=300) is False
    assert damp.score("nim:model", now=100).penalty == before
    assert damp.allow_probe("nim:model", now=400, cooldown_seconds=300) is True
    after_probe = damp.score("nim:model", now=400).penalty
    assert after_probe >= 400
    # A second check inside the cooldown must not keep probing.
    assert damp.allow_probe("nim:model", now=401, cooldown_seconds=300) is False
    assert damp.score("nim:model", now=401).penalty == after_probe * (0.5 ** (1 / 1800))


def test_route_flap_reset_clears_persisted_penalty(tmp_path):
    path = tmp_path / "nim_route_damping.json"
    damp = RouteFlapDampener(path=path, suppress_at=400, half_life_seconds=1800)
    damp.record("nim:model", "timeout", now=100)
    damp.record("nim:model", "timeout", now=100)
    assert path.is_file()
    damp.reset("nim:model")
    assert RouteFlapDampener(path=path, suppress_at=400).suppressed("nim:model") is False

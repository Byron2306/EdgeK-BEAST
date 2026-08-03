from pathlib import Path

from scripts.verify_runtime_health import _registry


def test_runtime_health_verifier_targets_registry_owned_beast_and_commons():
    services = _registry(Path(__file__).resolve().parents[1] / ".byron" / "services.yaml")

    assert services["beast"]["upstream"] == "127.0.0.1:8101"
    assert services["commons"]["upstream"] == "127.0.0.1:8601"

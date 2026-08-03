from pathlib import Path

from app.kernel.networking.service_registry import ServiceRegistry


ROOT = Path(__file__).resolve().parents[1]


def test_enterprise_runtime_registry_matches_declared_gateway_and_commons_ports():
    registry = ServiceRegistry.from_file(ROOT / ".byron" / "services.yaml")

    beast = registry.services["beast"]
    commons = registry.services["commons"]

    assert (beast.upstream, beast.port) == ("127.0.0.1:8101", 8101)
    assert (commons.upstream, commons.port) == ("127.0.0.1:8601", 8601)

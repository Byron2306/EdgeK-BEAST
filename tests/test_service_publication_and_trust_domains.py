from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.kernel.networking.service_publication import NodeDnsAdvertisement, ServicePublicationController
from app.kernel.networking.service_registry import ServiceRegistry
from app.kernel.networking.trust_domains import TrustDomain, TrustDomainController


def test_publication_only_renders_healthy_services_and_verified_nodes(tmp_path: Path):
    registry = ServiceRegistry({
        "api": {"hostname": "api.test", "upstream": "127.0.0.1:8101", "port": 8101},
        "ui": {"hostname": "ui.test", "upstream": "127.0.0.1:8102", "port": 8102},
    })
    controller = ServicePublicationController(registry, tmp_path)
    key = Ed25519PrivateKey.generate()
    node = NodeDnsAdvertisement(
        node_id="node-a", hostname="node-a.test", address="127.0.0.2", port=9443,
        attestation_digest="sha256:attested", expires_at=200, key_id="node-a-1", public_key="test",
    ).sealed(key)
    receipt = controller.publish({"api": "healthy", "ui": "unhealthy"}, nodes=(node,), verifier=key.public_key(), now=100)
    assert receipt["published_services"] == ["api"]
    assert receipt["suppressed_services"] == {"ui": "unhealthy"}
    assert "api.test" in (tmp_path / "generated" / "hosts.generated").read_text()
    assert "ui.test" not in (tmp_path / "generated" / "hosts.generated").read_text()
    assert "beast-node=node-a" in (tmp_path / "generated" / "beast.test.zone").read_text()


def test_node_dns_requires_valid_unexpired_signature(tmp_path: Path):
    registry = ServiceRegistry({"api": {"hostname": "api.test", "upstream": "127.0.0.1:8101", "port": 8101}})
    key = Ed25519PrivateKey.generate()
    node = NodeDnsAdvertisement("node-a", "node-a.test", "127.0.0.2", 9443, "sha256:a", 100, "key", "pub").sealed(key)
    with pytest.raises(PermissionError, match="expired"):
        ServicePublicationController(registry, tmp_path).publish({"api": "healthy"}, nodes=(node,), verifier=key.public_key(), now=100)


def test_trust_domain_plan_is_narrow_and_apply_is_gated():
    controller = TrustDomainController()
    domain = TrustDomain("commons", "beast-commons", "beast-commons", 1201, "10.44.0.0/24", (443, 9443))
    plan = controller.plan(domain)
    assert "policy drop" in plan["nftables"]
    assert "tcp dport { 443, 9443 } accept" in plan["nftables"]
    assert controller.apply(domain, approved=False)["status"] == "approval_required"
    with pytest.raises(ValueError):
        controller.plan(TrustDomain("bad", "ns", "vrf", 1, "not-a-network"))

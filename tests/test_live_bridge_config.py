import pytest

from app.kernel.integration.arda_metatron_bridge import build_live_bridge


def test_live_bridge_requires_explicit_endpoints(monkeypatch):
    monkeypatch.delenv("BEAST_ARDA_AUTHORIZATION_URL", raising=False)
    monkeypatch.delenv("BEAST_METATRON_AUTHORIZATION_URL", raising=False)
    with pytest.raises(RuntimeError, match="authorization URLs"):
        build_live_bridge()


def test_live_bridge_constructs_only_signed_authorizers_and_durable_ledger(monkeypatch, tmp_path):
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from app.kernel.integration.arda_metatron_bridge import SignedJsonHttpAuthorizer

    paths = {}
    for authority in ("ARDA", "METATRON"):
        private = Ed25519PrivateKey.generate()
        path = tmp_path / f"{authority.lower()}.pem"
        path.write_bytes(private.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
        paths[authority] = path
    config = {
        "BEAST_ARDA_AUTHORIZATION_URL": "https://arda.test/authorize",
        "BEAST_METATRON_AUTHORIZATION_URL": "https://metatron.test/authorize",
        "BEAST_ARDA_PUBLIC_KEY": str(paths["ARDA"]),
        "BEAST_METATRON_PUBLIC_KEY": str(paths["METATRON"]),
        "BEAST_CAPABILITY_LEDGER_PATH": str(tmp_path / "capabilities.sqlite3"),
        "BEAST_AUTHORIZATION_AUDIENCE": "beast-executor",
        "BEAST_POLICY_GENERATION": "policy-1",
        "BEAST_ARDA_APPRAISAL_REF": "arda-appraisal:1",
        "BEAST_METATRON_APPRAISAL_REF": "metatron-appraisal:1",
    }
    for name, value in config.items():
        monkeypatch.setenv(name, value)
    bridge = build_live_bridge()
    assert isinstance(bridge.arda_authorize, SignedJsonHttpAuthorizer)
    assert isinstance(bridge.metatron_authorize, SignedJsonHttpAuthorizer)
    assert bridge.capability_ledger.require_verifier is True
    assert bridge.capability_ledger.path == tmp_path / "capabilities.sqlite3"

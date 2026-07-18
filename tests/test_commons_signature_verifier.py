import base64

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.kernel.commons.signature_verifier import CommonsTrustStore, canonical_bytes


def test_ed25519_commons_trust_store_verifies_authority_bound_payload(tmp_path):
    private_key = Ed25519PrivateKey.generate()
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    encoded = base64.b64encode(public_pem).decode("ascii")
    trust_store = tmp_path / "trust.yaml"
    trust_store.write_text(
        f"authorities:\n  beast.release:\n    public_key_pem_b64: {encoded}\n",
        encoding="utf-8",
    )
    payload = {"kind": "model", "metadata": {"revision": "v1"}}
    signature = base64.b64encode(private_key.sign(canonical_bytes(payload))).decode("ascii")
    verifier = CommonsTrustStore.from_file(trust_store)

    assert verifier.verify(payload, signature, "beast.release")
    assert not verifier.verify({**payload, "kind": "dataset"}, signature, "beast.release")
    assert not verifier.verify(payload, signature, "untrusted.release")

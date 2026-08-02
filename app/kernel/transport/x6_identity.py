from __future__ import annotations
import base64
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from .x6_contracts import SignedManifestEnvelope, canonical, X6Refusal

class NodeSigner:
    def __init__(self, private_key: Ed25519PrivateKey | None = None):
        self.private_key = private_key or Ed25519PrivateKey.generate()
    @property
    def public_key_b64(self) -> str:
        from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
        raw = self.private_key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
        return base64.b64encode(raw).decode("ascii")
    def sign(self, body: dict) -> str:
        return base64.b64encode(self.private_key.sign(canonical(body))).decode("ascii")

def verify_envelope(envelope: SignedManifestEnvelope, trusted_public_keys: set[str]) -> None:
    if envelope.public_key_b64 not in trusted_public_keys:
        raise X6Refusal("untrusted sender key")
    try:
        pub = Ed25519PublicKey.from_public_bytes(base64.b64decode(envelope.public_key_b64, validate=True))
        pub.verify(base64.b64decode(envelope.signature_b64, validate=True), canonical(envelope.signed_body()))
    except Exception as exc:
        raise X6Refusal("manifest signature verification failed") from exc

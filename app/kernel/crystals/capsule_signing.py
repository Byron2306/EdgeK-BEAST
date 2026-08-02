from __future__ import annotations
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

class Ed25519CapsuleSigner:
    algorithm = "ed25519"
    def __init__(self, signer_id: str, private_key: Ed25519PrivateKey | None = None):
        self.signer_id = signer_id
        self._key = private_key or Ed25519PrivateKey.generate()
    @property
    def public_key(self) -> Ed25519PublicKey: return self._key.public_key()
    def sign(self, data: bytes) -> bytes: return self._key.sign(data)

class Ed25519CapsuleVerifier:
    algorithm = "ed25519"
    def __init__(self, keys: dict[str, Ed25519PublicKey]): self._keys = dict(keys)
    def verify(self, signer_id: str, signature: bytes, data: bytes) -> None:
        key = self._keys.get(signer_id)
        if key is None: raise ValueError("untrusted signer")
        key.verify(signature, data)

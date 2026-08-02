"""Signed attestation envelopes for export-safe Forge KV dataset manifests."""
from __future__ import annotations

import base64
import hashlib
import json
import time
from dataclasses import asdict, dataclass, replace
from typing import Any, Mapping


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str).encode()


@dataclass(frozen=True)
class ForgeKVAttestationEnvelope:
    subject_digest: str
    issuer: str
    audience: str
    policy_digest: str
    verifier_digest: str
    issued_at: float
    expires_at: float
    claims: Mapping[str, Any]
    signature: str = ""
    envelope_digest: str = ""

    def unsigned_payload(self) -> dict[str, Any]:
        body = asdict(self)
        body.pop("signature", None)
        body.pop("envelope_digest", None)
        return body

    def sealed(self, signer=None) -> "ForgeKVAttestationEnvelope":
        payload = canonical_bytes(self.unsigned_payload())
        signature = base64.b64encode(signer.sign(payload)).decode("ascii") if signer else ""
        digest = "sha256:" + hashlib.sha256(payload + signature.encode()).hexdigest()
        return replace(self, signature=signature, envelope_digest=digest)

    def verify(self, verifier=None, *, now: float | None = None) -> bool:
        current = time.time() if now is None else now
        if not self.subject_digest.startswith("sha256:") or current >= self.expires_at or self.issued_at > current:
            return False
        payload = canonical_bytes(self.unsigned_payload())
        expected = "sha256:" + hashlib.sha256(payload + self.signature.encode()).hexdigest()
        if expected != self.envelope_digest:
            return False
        if verifier is not None:
            if not self.signature:
                return False
            try:
                verifier.verify(base64.b64decode(self.signature), payload)
            except Exception:
                return False
        return True

    def to_dict(self) -> dict[str, Any]:
        return {"beast_object_type": "forge_kv_attestation_envelope", "version": "1.0", **asdict(self), "authority": "verify_only"}

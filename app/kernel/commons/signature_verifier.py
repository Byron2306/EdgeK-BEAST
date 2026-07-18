"""Ed25519 authority trust store for Commons manifests.

The trust store contains public verification material only.  A signature is
accepted only when its authority is explicitly configured and the detached
signature verifies over canonical JSON bytes.
"""
from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any, Mapping

import yaml
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey


def canonical_bytes(payload: Mapping[str, Any]) -> bytes:
    return json.dumps(
        dict(payload),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    ).encode("utf-8")


class CommonsTrustStore:
    """Explicit mapping from Commons authority IDs to Ed25519 public keys."""

    def __init__(self, authorities: Mapping[str, Ed25519PublicKey]):
        self._authorities = dict(authorities)
        if not self._authorities:
            raise ValueError("Commons trust store cannot be empty")

    @classmethod
    def from_file(cls, path: str | Path) -> "CommonsTrustStore":
        source = Path(path).expanduser().resolve()
        payload = yaml.safe_load(source.read_text(encoding="utf-8")) or {}
        records = payload.get("authorities") or {}
        if not isinstance(records, dict):
            raise ValueError("Commons trust store authorities must be a mapping")
        authorities: dict[str, Ed25519PublicKey] = {}
        for authority, record in records.items():
            if not authority or not isinstance(record, dict):
                raise ValueError("invalid Commons authority record")
            if record.get("public_key_pem_b64"):
                pem = base64.b64decode(str(record["public_key_pem_b64"]), validate=True)
            elif record.get("public_key_path"):
                key_path = (source.parent / str(record["public_key_path"])).resolve()
                if source.parent not in key_path.parents and key_path != source.parent:
                    raise ValueError("Commons public key path escapes trust-store directory")
                pem = key_path.read_bytes()
            else:
                raise ValueError(f"public key missing for Commons authority {authority}")
            key = serialization.load_pem_public_key(pem)
            if not isinstance(key, Ed25519PublicKey):
                raise ValueError(f"Commons authority {authority} is not Ed25519")
            authorities[str(authority)] = key
        return cls(authorities)

    @property
    def authorities(self) -> tuple[str, ...]:
        return tuple(sorted(self._authorities))

    def verify(self, payload: Mapping[str, Any], signature: str, authority: str) -> bool:
        key = self._authorities.get(str(authority))
        if key is None:
            return False
        try:
            key.verify(base64.b64decode(signature, validate=True), canonical_bytes(payload))
            return True
        except (InvalidSignature, ValueError, TypeError):
            return False

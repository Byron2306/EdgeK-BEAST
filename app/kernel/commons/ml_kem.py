"""ML-KEM handshakes for Commons node transport proofs.

The shared secret is never serialized into receipts.  Nodes prove successful
decapsulation by returning an HMAC over a bounded transcript.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
from dataclasses import dataclass
from importlib import import_module
from pathlib import Path
from typing import Any, Mapping

from app.kernel.commons.remote_protocol import canonical_json, sha256_bytes


ML_KEM_ALGORITHM = "ML-KEM-768"


@dataclass(frozen=True, slots=True)
class MLKEMNodeKey:
    algorithm: str
    public_key: bytes
    secret_key: bytes

    @property
    def public_key_digest(self) -> str:
        return sha256_bytes(self.public_key)

    @property
    def secret_key_digest(self) -> str:
        return sha256_bytes(self.secret_key)


def ml_kem_available(algorithm: str = ML_KEM_ALGORITHM) -> bool:
    oqs = _oqs()
    return algorithm in set(oqs.get_enabled_kem_mechanisms())


def load_or_create_node_key(path: str | Path, *, algorithm: str = ML_KEM_ALGORITHM) -> MLKEMNodeKey:
    if not ml_kem_available(algorithm):
        raise RuntimeError(f"{algorithm} is not enabled in liboqs")
    oqs = _oqs()
    key_path = Path(path)
    key_path.parent.mkdir(parents=True, exist_ok=True)
    if key_path.exists():
        payload = key_path.read_bytes()
        decoded = _decode_persisted_keypair(payload, algorithm=algorithm)
        if decoded is not None:
            return decoded
        # Legacy BEAST/Commons nodes persisted only the ML-KEM secret key.
        # liboqs-python cannot derive/export the public key from a restored
        # secret key; calling generate_keypair() here creates a new, unrelated
        # public key and breaks decapsulation proofs after container restart.
        # Rotate once into the auditable keypair envelope instead.
    with oqs.KeyEncapsulation(algorithm) as kem:
        public = kem.generate_keypair()
        secret = kem.export_secret_key()
    key_path.write_text(
        json.dumps(
            {
                "beast_object_type": "commons_ml_kem_node_keypair",
                "version": "1.0",
                "algorithm": algorithm,
                "public_key_b64": base64.b64encode(public).decode("ascii"),
                "secret_key_b64": base64.b64encode(secret).decode("ascii"),
                "public_key_digest": sha256_bytes(public),
                "secret_key_digest": sha256_bytes(secret),
                "secret_storage_policy": "local_node_private_key_file_only_never_receipt_serialized",
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    try:
        key_path.chmod(0o600)
    except OSError:
        pass
    return MLKEMNodeKey(algorithm=algorithm, public_key=public, secret_key=secret)


def _decode_persisted_keypair(payload: bytes, *, algorithm: str) -> MLKEMNodeKey | None:
    try:
        document = json.loads(payload.decode("utf-8"))
    except Exception:
        return None
    if not isinstance(document, Mapping):
        return None
    if document.get("beast_object_type") != "commons_ml_kem_node_keypair":
        return None
    if str(document.get("algorithm") or "") != algorithm:
        raise RuntimeError("persisted ML-KEM key algorithm mismatch")
    try:
        public = base64.b64decode(str(document["public_key_b64"]), validate=True)
        secret = base64.b64decode(str(document["secret_key_b64"]), validate=True)
    except Exception as exc:
        raise RuntimeError("persisted ML-KEM keypair is not valid base64") from exc
    if sha256_bytes(public) != document.get("public_key_digest"):
        raise RuntimeError("persisted ML-KEM public key digest mismatch")
    if sha256_bytes(secret) != document.get("secret_key_digest"):
        raise RuntimeError("persisted ML-KEM secret key digest mismatch")
    return MLKEMNodeKey(algorithm=algorithm, public_key=public, secret_key=secret)


def public_key_document(
    *,
    node_id: str,
    workload_digest: str,
    key: MLKEMNodeKey,
    maximum_authority: str = "key_agreement_only",
) -> dict[str, Any]:
    document = {
        "beast_object_type": "commons_ml_kem_public_key",
        "version": "1.0",
        "node_id": node_id,
        "algorithm": key.algorithm,
        "public_key_b64": base64.b64encode(key.public_key).decode("ascii"),
        "public_key_digest": key.public_key_digest,
        "workload_digest": workload_digest,
        "maximum_authority": maximum_authority,
        "secret_exported": False,
    }
    return {**document, "document_digest": sha256_bytes(canonical_json(document))}


def encapsulate(public_key: bytes, *, algorithm: str = ML_KEM_ALGORITHM) -> tuple[bytes, bytes]:
    if not ml_kem_available(algorithm):
        raise RuntimeError(f"{algorithm} is not enabled in liboqs")
    oqs = _oqs()
    with oqs.KeyEncapsulation(algorithm) as kem:
        ciphertext, shared_secret = kem.encap_secret(public_key)
    return ciphertext, shared_secret


def decapsulate(ciphertext: bytes, secret_key: bytes, *, algorithm: str = ML_KEM_ALGORITHM) -> bytes:
    if not ml_kem_available(algorithm):
        raise RuntimeError(f"{algorithm} is not enabled in liboqs")
    oqs = _oqs()
    with oqs.KeyEncapsulation(algorithm, secret_key=secret_key) as kem:
        return kem.decap_secret(ciphertext)


def challenge_confirmation_body(
    *,
    node_id: str,
    algorithm: str,
    public_key_digest: str,
    ciphertext_digest: str,
    challenge_nonce: str,
    transcript_digest: str,
) -> dict[str, Any]:
    return {
        "beast_object_type": "commons_ml_kem_challenge_confirmation",
        "version": "1.0",
        "node_id": node_id,
        "algorithm": algorithm,
        "public_key_digest": public_key_digest,
        "ciphertext_digest": ciphertext_digest,
        "challenge_nonce": challenge_nonce,
        "transcript_digest": transcript_digest,
        "maximum_authority": "key_agreement_proof_only",
    }


def confirmation_mac(shared_secret: bytes, body: Mapping[str, Any]) -> str:
    digest = hmac.new(shared_secret, canonical_json(dict(body)), hashlib.sha256).digest()
    return base64.b64encode(digest).decode("ascii")


def _oqs():
    try:
        return import_module("oqs")
    except Exception as exc:
        raise RuntimeError("liboqs-python is required for Commons ML-KEM support") from exc

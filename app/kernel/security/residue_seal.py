"""Tamper-evident residue sealing for BEAST operational artifacts.

Residue Seal signs deterministic canonical payloads with a purpose-specific
Ed25519 key. The key is local to residue signing and is deliberately separate
from mTLS, federation, provider, or workload identity material.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

try:  # pragma: no cover - exercised when dependency is unavailable.
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
except Exception:  # pragma: no cover
    InvalidSignature = None
    serialization = None
    Ed25519PrivateKey = None
    Ed25519PublicKey = None


SIGNATURE_PROVIDERS = {"cryptography", "openssl"}


def canonical_bytes(payload: Dict[str, Any]) -> bytes:
    """Return BEAST canonical JSON bytes for signing and hashing."""

    if not isinstance(payload, dict):
        raise TypeError("canonical payload must be a dict")
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def payload_digest(payload: Dict[str, Any]) -> str:
    return "sha256:" + hashlib.sha256(canonical_bytes(payload)).hexdigest()


class ResidueSeal:
    """Purpose-specific Ed25519 signer/verifier for BEAST residue."""

    def __init__(self, key_dir: Optional[Path] = None):
        default = Path.home() / ".beast" / "keys" / "residue"
        self.key_dir = (key_dir or default).resolve()
        self.key_dir.mkdir(parents=True, exist_ok=True)
        self.private_key = self.key_dir / "residue_ed25519.pem"

    def sign(self, payload: Dict[str, Any], *, purpose: str = "beast_operational_residue") -> Dict[str, Any]:
        unsigned = self._unsigned(payload)
        message_payload = self._message_payload(unsigned, purpose)
        private_key, public_pem = self._load_or_create_key()
        if private_key is not None:
            signature = private_key.sign(canonical_bytes(message_payload))
            provider = "cryptography"
        else:
            signature = self._openssl_sign(canonical_bytes(message_payload))
            provider = "openssl"
            public_pem = self._openssl_public_key()
        return {
            "beast_object_type": "beast_residue_seal",
            "version": "2.0",
            "purpose": purpose,
            "algorithm": "Ed25519",
            "provider": provider,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "payload_sha256": message_payload["payload_sha256"],
            "message_sha256": payload_digest(message_payload),
            "public_key_pem_b64": base64.b64encode(public_pem).decode("ascii"),
            "public_key_hash": self._hash_bytes(public_pem),
            "signature_b64": base64.b64encode(signature).decode("ascii"),
            "key_boundary": "purpose_specific_residue_key_not_mtls_not_federation",
        }

    def verify(
        self,
        payload: Dict[str, Any],
        seal: Dict[str, Any],
        *,
        expected_purpose: Optional[str] = None,
    ) -> Dict[str, Any]:
        if seal.get("algorithm") != "Ed25519" or seal.get("provider") not in SIGNATURE_PROVIDERS:
            return {"verified": False, "reason": "unsupported_signature_profile"}
        if expected_purpose is not None and seal.get("purpose") != expected_purpose:
            return {
                "verified": False,
                "reason": "purpose_mismatch",
                "expected_purpose": expected_purpose,
                "actual_purpose": seal.get("purpose"),
            }

        unsigned = self._unsigned(payload)
        expected_hash = payload_digest(unsigned)
        if seal.get("payload_sha256") != expected_hash:
            return {"verified": False, "reason": "payload_hash_mismatch", "expected_payload_sha256": expected_hash}

        try:
            public = base64.b64decode(str(seal.get("public_key_pem_b64") or ""), validate=True)
            signature = base64.b64decode(str(seal.get("signature_b64") or ""), validate=True)
        except Exception:
            return {"verified": False, "reason": "invalid_base64"}

        public_key_hash = self._hash_bytes(public)
        if seal.get("public_key_hash") and seal.get("public_key_hash") != public_key_hash:
            return {"verified": False, "reason": "public_key_hash_mismatch", "public_key_hash": public_key_hash}

        message_payload = self._message_payload(unsigned, str(seal.get("purpose") or ""))
        message_hash = payload_digest(message_payload)
        if seal.get("message_sha256") and seal.get("message_sha256") != message_hash:
            return {"verified": False, "reason": "message_hash_mismatch", "expected_message_sha256": message_hash}

        verified = self._verify_signature(public, signature, canonical_bytes(message_payload))
        return {
            "verified": verified,
            "reason": "ok" if verified else "invalid_signature",
            "algorithm": "Ed25519",
            "provider": seal.get("provider"),
            "public_key_hash": public_key_hash,
            "payload_sha256": expected_hash,
            "message_sha256": message_hash,
            "purpose": seal.get("purpose"),
        }

    def health(self) -> Dict[str, Any]:
        key_exists = self.private_key.exists()
        mode = None
        if key_exists:
            mode = oct(self.private_key.stat().st_mode & 0o777)
        return {
            "beast_object_type": "beast_residue_seal_health",
            "version": "1.0",
            "key_dir": str(self.key_dir),
            "private_key": str(self.private_key),
            "key_exists": key_exists,
            "key_mode": mode,
            "native_crypto_available": Ed25519PrivateKey is not None,
        }

    @staticmethod
    def _unsigned(payload: Dict[str, Any]) -> Dict[str, Any]:
        return {key: value for key, value in payload.items() if key not in {"residue_seal", "signature"}}

    @staticmethod
    def _message_payload(payload: Dict[str, Any], purpose: str) -> Dict[str, Any]:
        return {
            "purpose": purpose,
            "payload_sha256": payload_digest(payload),
            "payload": payload,
        }

    @staticmethod
    def _hash_bytes(value: bytes) -> str:
        return "sha256:" + hashlib.sha256(value).hexdigest()

    def _load_or_create_key(self) -> tuple[Optional[Any], bytes]:
        if Ed25519PrivateKey is None or serialization is None:
            self._ensure_openssl_key()
            return None, self._openssl_public_key()
        if self.private_key.exists():
            private_key = serialization.load_pem_private_key(self.private_key.read_bytes(), password=None)
        else:
            private_key = Ed25519PrivateKey.generate()
            private_bytes = private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption(),
            )
            self._atomic_write_bytes(self.private_key, private_bytes, mode=0o600)
        public_pem = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        return private_key, public_pem

    def _verify_signature(self, public_pem: bytes, signature: bytes, message: bytes) -> bool:
        if Ed25519PublicKey is not None and serialization is not None and InvalidSignature is not None:
            try:
                public_key = serialization.load_pem_public_key(public_pem)
                if not isinstance(public_key, Ed25519PublicKey):
                    return False
                public_key.verify(signature, message)
                return True
            except InvalidSignature:
                return False
            except Exception:
                pass
        return self._openssl_verify(public_pem, signature, message)

    def _ensure_openssl_key(self) -> None:
        if self.private_key.exists():
            os.chmod(self.private_key, 0o600)
            return
        completed = subprocess.run(
            ["openssl", "genpkey", "-algorithm", "ED25519", "-out", str(self.private_key)],
            capture_output=True,
            timeout=15,
            check=False,
        )
        if completed.returncode != 0:
            raise ValueError("OpenSSL could not generate residue signing key")
        os.chmod(self.private_key, 0o600)

    def _openssl_public_key(self) -> bytes:
        self._ensure_openssl_key()
        public = subprocess.run(
            ["openssl", "pkey", "-in", str(self.private_key), "-pubout"],
            capture_output=True,
            timeout=15,
            check=False,
        )
        if public.returncode != 0:
            raise ValueError("OpenSSL could not derive residue public key")
        return public.stdout

    def _openssl_sign(self, message: bytes) -> bytes:
        self._ensure_openssl_key()
        with tempfile.NamedTemporaryFile(prefix="beast-residue-sign-", suffix=".bin") as message_file:
            message_file.write(message)
            message_file.flush()
            signed = subprocess.run(
                ["openssl", "pkeyutl", "-sign", "-rawin", "-inkey", str(self.private_key), "-in", message_file.name],
                capture_output=True,
                timeout=15,
                check=False,
            )
        if signed.returncode != 0:
            raise ValueError("OpenSSL could not sign residue")
        return signed.stdout

    @staticmethod
    def _openssl_verify(public: bytes, signature: bytes, message: bytes) -> bool:
        try:
            with tempfile.TemporaryDirectory(prefix="beast-residue-verify-") as temp:
                root = Path(temp)
                public_path = root / "public.pem"
                signature_path = root / "signature.bin"
                message_path = root / "message.bin"
                public_path.write_bytes(public)
                signature_path.write_bytes(signature)
                message_path.write_bytes(message)
                completed = subprocess.run(
                    [
                        "openssl",
                        "pkeyutl",
                        "-verify",
                        "-rawin",
                        "-pubin",
                        "-inkey",
                        str(public_path),
                        "-sigfile",
                        str(signature_path),
                        "-in",
                        str(message_path),
                    ],
                    capture_output=True,
                    timeout=15,
                    check=False,
                )
        except (OSError, subprocess.SubprocessError):
            return False
        return completed.returncode == 0

    @staticmethod
    def _atomic_write_bytes(path: Path, data: bytes, *, mode: int = 0o600) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.with_name(f".{path.name}.tmp-{os.getpid()}")
        with temp_path.open("wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temp_path, mode)
        os.replace(temp_path, path)

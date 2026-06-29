"""Crypto-agile seals for fused Crystal Compute artifacts.

NIST standardized the CRYSTALS family under compliance names:
- Kyber -> ML-KEM
- Dilithium -> ML-DSA

This module uses liboqs when available and falls back to deterministic local
HMAC seals for development/test environments. The fallback is an integrity seal,
not a production post-quantum signature.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
from datetime import datetime, timezone
from typing import Any, Dict


def canonical_bytes(payload: Dict[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def seal_crystal_payload(
    payload: Dict[str, Any],
    *,
    purpose: str = "crystal_compute_credit",
    signature_alg: str = "ML-DSA-65",
    kem_alg: str = "ML-KEM-768",
) -> Dict[str, Any]:
    """Return a signed, crypto-agile seal for a crystal payload.

    The seal stores hashes and signatures around the payload. It does not need
    to include the payload itself, which lets artifacts publish a receipt while
    keeping larger crystal bodies separate or private.
    """
    body = canonical_bytes(payload)
    digest = "sha256:" + hashlib.sha256(body).hexdigest()
    created_at = datetime.now(timezone.utc).isoformat()
    oqs_seal = _try_oqs_seal(body, signature_alg=signature_alg, kem_alg=kem_alg)
    if oqs_seal:
        key = os.environ.get("BEAST_CRYSTAL_SEAL_KEY", "beast-local-dev-crystal-seal")
        local_signature = "hmac-sha256:" + hmac.new(key.encode("utf-8"), body, hashlib.sha256).hexdigest()
        return {
            "beast_object_type": "sealed_crystal_compute_credit",
            "version": "1.0",
            "purpose": purpose,
            "payload_hash": digest,
            "created_at": created_at,
            "crypto_profile": {
                "signature": signature_alg,
                "kem": kem_alg,
                "provider": "liboqs",
                "fallback": False,
            },
            "local_integrity_signature": local_signature,
            **oqs_seal,
        }

    key = os.environ.get("BEAST_CRYSTAL_SEAL_KEY", "beast-local-dev-crystal-seal")
    signature = "hmac-sha256:" + hmac.new(key.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return {
        "beast_object_type": "sealed_crystal_compute_credit",
        "version": "1.0",
        "purpose": purpose,
        "payload_hash": digest,
        "created_at": created_at,
        "crypto_profile": {
            "signature": "HMAC-SHA256",
            "kem": "none",
            "provider": "stdlib_dev_fallback",
            "fallback": True,
            "production_note": "Install/configure a PQC provider for ML-DSA/ML-KEM production seals.",
        },
        "signature": signature,
    }


def verify_crystal_seal(payload: Dict[str, Any], seal: Dict[str, Any]) -> Dict[str, Any]:
    body = canonical_bytes(payload)
    expected_hash = "sha256:" + hashlib.sha256(body).hexdigest()
    hash_ok = hmac.compare_digest(str(seal.get("payload_hash") or ""), expected_hash)
    profile = seal.get("crypto_profile") if isinstance(seal.get("crypto_profile"), dict) else {}
    signature_ok = False
    provider = str(profile.get("provider") or "")
    if provider == "liboqs":
        signature_ok = _try_oqs_verify(body, seal)
        if not signature_ok and seal.get("local_integrity_signature"):
            key = os.environ.get("BEAST_CRYSTAL_SEAL_KEY", "beast-local-dev-crystal-seal")
            expected_sig = "hmac-sha256:" + hmac.new(key.encode("utf-8"), body, hashlib.sha256).hexdigest()
            signature_ok = hmac.compare_digest(str(seal.get("local_integrity_signature") or ""), expected_sig)
    elif provider == "stdlib_dev_fallback":
        key = os.environ.get("BEAST_CRYSTAL_SEAL_KEY", "beast-local-dev-crystal-seal")
        expected_sig = "hmac-sha256:" + hmac.new(key.encode("utf-8"), body, hashlib.sha256).hexdigest()
        signature_ok = hmac.compare_digest(str(seal.get("signature") or ""), expected_sig)
    return {
        "beast_object_type": "crystal_seal_verification",
        "version": "1.0",
        "hash_ok": hash_ok,
        "signature_ok": signature_ok,
        "verified": bool(hash_ok and signature_ok),
        "crypto_profile": profile,
    }


def _try_oqs_seal(body: bytes, *, signature_alg: str, kem_alg: str) -> Dict[str, Any]:
    try:
        import oqs  # type: ignore
    except Exception:
        return {}
    try:
        sigs = set(oqs.get_enabled_sig_mechanisms())
        kems = set(oqs.get_enabled_kem_mechanisms())
        if signature_alg not in sigs:
            return {}
        with oqs.Signature(signature_alg) as signer:
            public_key = signer.generate_keypair()
            signature = signer.sign(body)
        kem_receipt: Dict[str, Any] = {"kem_status": "not_available"}
        if kem_alg in kems:
            with oqs.KeyEncapsulation(kem_alg) as kem:
                kem_public_key = kem.generate_keypair()
                ciphertext, shared_secret = kem.encap_secret(kem_public_key)
            kem_receipt = {
                "kem_status": "content_key_encapsulated",
                "kem_public_key_hash": "sha256:" + hashlib.sha256(kem_public_key).hexdigest(),
                "kem_ciphertext_b64": base64.b64encode(ciphertext).decode("ascii"),
                "encapsulated_key_hash": "sha256:" + hashlib.sha256(shared_secret).hexdigest(),
                "note": "Private recipient key is intentionally not stored in this public receipt.",
            }
        return {
            "signature": "ml-dsa:" + base64.b64encode(signature).decode("ascii"),
            "signature_public_key_b64": base64.b64encode(public_key).decode("ascii"),
            **kem_receipt,
        }
    except Exception:
        return {}


def _try_oqs_verify(body: bytes, seal: Dict[str, Any]) -> bool:
    profile = seal.get("crypto_profile") if isinstance(seal.get("crypto_profile"), dict) else {}
    alg = str(profile.get("signature") or "")
    try:
        import oqs  # type: ignore

        signature = str(seal.get("signature") or "")
        if not signature.startswith("ml-dsa:"):
            return False
        sig_bytes = base64.b64decode(signature.split(":", 1)[1])
        public_key = base64.b64decode(str(seal.get("signature_public_key_b64") or ""))
        with oqs.Signature(alg) as verifier:
            return bool(verifier.verify(body, sig_bytes, public_key))
    except Exception:
        return False

"""In-toto provenance and RATS appraisal adapter.

RATS evidence is never trusted merely because a quote-shaped field exists.
BEAST consumes an appraisal result from a verifier, binds it to nonce,
artifact digest, reference values, freshness, and a trusted signing key.
"""
from __future__ import annotations

import abc
import base64
import dataclasses
import hashlib
import json
import time
from pathlib import Path
from typing import Any, Mapping, Optional

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec, ed25519, padding, rsa
from cryptography.hazmat.primitives.serialization import load_pem_public_key


class AttestationError(ValueError):
    pass


@dataclasses.dataclass(frozen=True)
class AttestationReceipt:
    artifact_digest: str
    in_toto_verified: bool
    rats_verified: bool
    verifier_id: str
    nonce: str
    issued_at: int
    expires_at: int
    policy_id: str


class AttestationAdapter(abc.ABC):
    @abc.abstractmethod
    def verify(self, artifact_path: Path, attestation_data: dict[str, Any]) -> bool:
        raise NotImplementedError


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def _digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            hasher.update(block)
    return "sha256:" + hasher.hexdigest()


def _verify_signature(key: Any, signature: bytes, payload: bytes) -> None:
    if isinstance(key, ed25519.Ed25519PublicKey):
        key.verify(signature, payload)
    elif isinstance(key, ec.EllipticCurvePublicKey):
        key.verify(signature, payload, ec.ECDSA(hashes.SHA256()))
    elif isinstance(key, rsa.RSAPublicKey):
        key.verify(signature, payload, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH), hashes.SHA256())
    else:
        raise AttestationError("unsupported attestation public key type")


class InTotoRATSAdapter(AttestationAdapter):
    """Verify an in-toto statement plus a signed RATS verifier result."""

    def __init__(self, trust_policy_path: Path, *, max_age_seconds: int = 300, expected_nonce: str | None = None) -> None:
        self.trust_policy_path = Path(trust_policy_path)
        self.max_age_seconds = max(1, int(max_age_seconds))
        self.expected_nonce = expected_nonce

    def _load_policy(self) -> dict[str, Any]:
        policy = json.loads(self.trust_policy_path.read_text(encoding="utf-8"))
        if not isinstance(policy, dict):
            raise AttestationError("trust policy must be an object")
        return policy

    @staticmethod
    def _subject_matches(statement: Mapping[str, Any], artifact_digest: str) -> bool:
        expected_hex = artifact_digest.split(":", 1)[1]
        for subject in statement.get("subject") or []:
            digest = subject.get("digest") if isinstance(subject, Mapping) else None
            if isinstance(digest, Mapping) and str(digest.get("sha256", "")).lower() == expected_hex.lower():
                return True
        return False

    def verify_receipt(self, artifact_path: Path, attestation_data: Mapping[str, Any], *, now: int | None = None) -> AttestationReceipt:
        if not artifact_path.is_file():
            raise AttestationError("artifact does not exist")
        policy = self._load_policy()
        artifact_digest = _digest(artifact_path)
        envelope = attestation_data.get("in_toto")
        if not isinstance(envelope, Mapping):
            raise AttestationError("in-toto envelope missing")
        statement = envelope.get("statement")
        signature_b64 = envelope.get("signature")
        if not isinstance(statement, Mapping) or not isinstance(signature_b64, str):
            raise AttestationError("in-toto statement or signature missing")
        if not self._subject_matches(statement, artifact_digest):
            raise AttestationError("in-toto subject digest does not bind the artifact")
        key = load_pem_public_key(Path(policy["in_toto_public_key"]).read_bytes())
        _verify_signature(key, base64.b64decode(signature_b64, validate=True), _canonical(statement))

        result = attestation_data.get("rats_result")
        result_sig = attestation_data.get("rats_signature")
        if not isinstance(result, Mapping) or not isinstance(result_sig, str):
            raise AttestationError("signed RATS verifier result missing")
        verifier_id = str(result.get("verifier_id") or "")
        if verifier_id not in set(policy.get("trusted_verifiers") or []):
            raise AttestationError("RATS verifier is not trusted")
        if result.get("artifact_digest") != artifact_digest:
            raise AttestationError("RATS result is not bound to the artifact")
        nonce = str(result.get("nonce") or "")
        expected_nonce = self.expected_nonce or str(attestation_data.get("expected_nonce") or "")
        if not expected_nonce or nonce != expected_nonce:
            raise AttestationError("RATS nonce mismatch")
        issued = int(result.get("issued_at") or 0)
        expires = int(result.get("expires_at") or 0)
        current = int(now if now is not None else time.time())
        if issued > current or current > expires or current - issued > self.max_age_seconds:
            raise AttestationError("RATS result is stale or expired")
        policy_id = str(result.get("policy_id") or "")
        if policy_id not in set(policy.get("allowed_policy_ids") or []):
            raise AttestationError("RATS appraisal policy is not allowed")
        if result.get("trustworthy") is not True:
            raise AttestationError("RATS verifier did not appraise the attester as trustworthy")
        allowed_measurements = set(policy.get("allowed_measurements") or [])
        measurements = set(str(x) for x in (result.get("measurements") or []))
        if allowed_measurements and not measurements.issubset(allowed_measurements):
            raise AttestationError("RATS measurements are outside reference values")
        rats_key = load_pem_public_key(Path(policy["rats_verifier_public_key"]).read_bytes())
        _verify_signature(rats_key, base64.b64decode(result_sig, validate=True), _canonical(result))
        return AttestationReceipt(artifact_digest, True, True, verifier_id, nonce, issued, expires, policy_id)

    def verify(self, artifact_path: Path, attestation_data: dict[str, Any]) -> bool:
        try:
            self.verify_receipt(artifact_path, attestation_data)
            return True
        except (AttestationError, OSError, ValueError, TypeError, KeyError):
            return False

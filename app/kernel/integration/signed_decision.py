"""Signed ARDA/Metatron decision envelope verification."""
from __future__ import annotations

import base64
import json
import time
from dataclasses import dataclass
from typing import Any, Mapping

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey


@dataclass(frozen=True)
class SignedDecision:
    authority: str
    allowed: bool
    request_digest: str
    policy_generation: str
    nonce: str
    signature: str
    key_id: str

    def unsigned(self) -> bytes:
        return json.dumps({"authority": self.authority, "allowed": self.allowed, "request_digest": self.request_digest, "policy_generation": self.policy_generation, "nonce": self.nonce, "key_id": self.key_id}, sort_keys=True, separators=(",", ":")).encode()


def verify_decision(payload: Mapping[str, Any], public_key: Ed25519PublicKey, *, expected_authority: str, expected_request_digest: str) -> SignedDecision:
    decision = SignedDecision(str(payload.get("authority", "")), bool(payload.get("allowed", False)), str(payload.get("request_digest", "")), str(payload.get("policy_generation", "")), str(payload.get("nonce", "")), str(payload.get("signature", "")), str((payload.get("verification_material") or {}).get("key_id", "")))
    if decision.authority != expected_authority or decision.request_digest != expected_request_digest or not decision.signature or not decision.nonce or not decision.policy_generation:
        raise ValueError("signed decision binding is incomplete")
    try:
        public_key.verify(base64.b64decode(decision.signature, validate=True), decision.unsigned())
    except Exception as exc:
        raise ValueError("signed decision verification failed") from exc
    return decision


_APPRAISAL_FIELDS = (
    "appraisal_ref",
    "authority",
    "audience",
    "policy_generation",
    "state",
    "expires_at",
    "request_digest",
    "nonce",
    "key_id",
    "evidence_digest",
)


def signed_appraisal_body(payload: Mapping[str, Any]) -> bytes:
    """Canonical appraisal bytes; response-only fields cannot escape signing."""

    return json.dumps(
        {field: payload.get(field) for field in _APPRAISAL_FIELDS},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def verify_appraisal(
    payload: Mapping[str, Any],
    public_key: Ed25519PublicKey,
    *,
    expected_authority: str,
    expected_audience: str,
    expected_policy_generation: str,
    expected_appraisal_ref: str,
    expected_request_digest: str,
    now: float | None = None,
) -> Mapping[str, Any]:
    """Verify the complete appraisal rather than trusting response metadata."""

    missing = [field for field in _APPRAISAL_FIELDS if payload.get(field) in (None, "")]
    if missing or not payload.get("signature"):
        raise ValueError("signed appraisal binding is incomplete")
    if (
        payload.get("authority") != expected_authority
        or payload.get("audience") != expected_audience
        or payload.get("policy_generation") != expected_policy_generation
        or payload.get("appraisal_ref") != expected_appraisal_ref
        or payload.get("request_digest") != expected_request_digest
        or payload.get("state") not in {"verified", "appraised"}
    ):
        raise ValueError("signed appraisal binding mismatch")
    if float(payload.get("expires_at") or 0) <= (time.time() if now is None else now):
        raise ValueError("signed appraisal expired")
    try:
        public_key.verify(
            base64.b64decode(str(payload["signature"]), validate=True),
            signed_appraisal_body(payload),
        )
    except Exception as exc:
        raise ValueError("signed appraisal verification failed") from exc
    return payload

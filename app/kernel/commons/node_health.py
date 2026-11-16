"""Fail-closed signed health verification for remote Commons nodes."""
from __future__ import annotations

import base64
import re
import time
from collections.abc import Mapping
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from .remote_protocol import canonical_json, sha256_bytes

REQUIRED_CAPABILITIES = frozenset({
    "bucket_registry",
    "immutable_blobs",
    "signed_revisions",
    "replay_resistant_requests",
})


def _refused(reason: str) -> dict[str, Any]:
    return {"ok": False, "reason": reason}


def verify_node_health(
    document: Mapping[str, Any], *, expected_node_id: str, now: float | None = None
) -> dict[str, Any]:
    checked_at = float(time.time() if now is None else now)
    descriptor = dict(document.get("descriptor") or {})
    if descriptor.get("node_id") != expected_node_id:
        return _refused("node_id_mismatch")
    if (
        descriptor.get("beast_object_type") != "remote_commons_node_descriptor"
        or descriptor.get("schema_version") != "1.0"
        or descriptor.get("protocol") != "beast-commons-http-signature-v1"
        or descriptor.get("maximum_authority") != "verify_only"
        or not re.fullmatch(r"sha256:[0-9a-f]{64}", str(descriptor.get("workload_digest") or ""))
        or not REQUIRED_CAPABILITIES.issubset(
            {str(item) for item in descriptor.get("capabilities") or []}
        )
    ):
        return _refused("descriptor_invariant_failed")
    encoded = canonical_json(descriptor)
    if document.get("descriptor_digest") != sha256_bytes(encoded):
        return _refused("descriptor_digest_mismatch")
    try:
        raw_public = base64.b64decode(str(descriptor.get("node_public_key") or ""), validate=True)
        public_key = Ed25519PublicKey.from_public_bytes(raw_public)
        signature = base64.b64decode(str(document.get("node_signature") or ""), validate=True)
        public_key.verify(signature, encoded)
    except (InvalidSignature, ValueError, TypeError):
        return _refused("node_signature_invalid")
    subject = {
        key: descriptor.get(key)
        for key in (
            "node_id",
            "workload_digest",
            "node_public_key",
            "protocol",
            "capabilities",
            "maximum_authority",
        )
    }
    subject_digest = sha256_bytes(canonical_json(subject))
    if descriptor.get("attestation_subject_digest") != subject_digest:
        return _refused("attestation_subject_mismatch")
    evidence = descriptor.get("trust_evidence") or []
    if not isinstance(evidence, list) or not evidence:
        return _refused("trust_evidence_missing")
    eligible = [
        row for row in evidence
        if isinstance(row, Mapping)
        and row.get("subject_node_id") == expected_node_id
        and row.get("subject_digest") == subject_digest
        and float(row.get("issued_at") or 0) <= checked_at + 60
    ]
    if not eligible:
        return _refused("trust_evidence_subject_mismatch")
    active = [row for row in eligible if float(row.get("expires_at") or 0) > checked_at]
    if not active:
        return _refused("trust_evidence_expired")
    best = max(active, key=lambda row: (int(row.get("checkpoint_count") or 0), float(row.get("expires_at") or 0)))
    return {
        "ok": True,
        "service": "beast-remote-commons-node",
        "node_id": expected_node_id,
        "maximum_authority": "verify_only",
        "workload_digest": descriptor["workload_digest"],
        "descriptor_digest": document["descriptor_digest"],
        "checkpoint_count": int(best.get("checkpoint_count") or 0),
        "policy_generation": str(best.get("policy_generation") or ""),
        "trust_expires_at": float(best["expires_at"]),
        "checked_at": checked_at,
    }

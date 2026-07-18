"""Cryptographic ARDA appraisal binding for Commons admission."""
from __future__ import annotations

import hashlib
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from app.kernel.commons.signature_verifier import canonical_bytes
from app.kernel.integration.arda_appraisal import ArdaAppraisal
from app.kernel.integration.signed_decision import verify_appraisal, verify_decision


def _digest_body(signed_body: Mapping[str, Any]) -> str:
    return "sha256:" + hashlib.sha256(canonical_bytes(signed_body)).hexdigest()


class SignedArdaAppraisalVerifier:
    """Verify ARDA evidence over an exact canonical Commons body."""

    def __init__(
        self,
        public_key_path: str | Path,
        *,
        authority: str = "arda",
        audience: str = "commons-space-forge",
        expected_policy_generation: str = "",
    ):
        key = serialization.load_pem_public_key(Path(public_key_path).expanduser().read_bytes())
        if not isinstance(key, Ed25519PublicKey):
            raise ValueError("ARDA appraisal key must be Ed25519")
        self.public_key = key
        self.authority = authority
        self.audience = audience
        self.expected_policy_generation = expected_policy_generation

    def __call__(self, value: Any, signed_body: Mapping[str, Any]) -> bool:
        if not isinstance(value, Mapping):
            return False
        request_digest = _digest_body(signed_body)
        try:
            if value.get("signature") and value.get("request_digest"):
                verify_appraisal(
                    value,
                    self.public_key,
                    expected_authority=self.authority,
                    expected_audience=self.audience,
                    expected_policy_generation=(
                        self.expected_policy_generation
                        or str(value.get("policy_generation") or "")
                    ),
                    expected_appraisal_ref=str(signed_body.get("appraisal_ref") or ""),
                    expected_request_digest=request_digest,
                )
                return True
            return self._legacy_nested_decision(value, signed_body, request_digest)
        except (KeyError, TypeError, ValueError, PermissionError):
            return False

    def _legacy_nested_decision(
        self, value: Mapping[str, Any], signed_body: Mapping[str, Any], request_digest: str
    ) -> bool:
        appraisal = ArdaAppraisal.from_mapping(value)
        if appraisal.authority != self.authority or appraisal.audience != self.audience:
            return False
        if appraisal.appraisal_ref != str(signed_body.get("appraisal_ref") or ""):
            return False
        if (
            self.expected_policy_generation
            and appraisal.policy_generation != self.expected_policy_generation
        ):
            return False
        decision = verify_decision(
            value.get("decision") or {},
            self.public_key,
            expected_authority=self.authority,
            expected_request_digest=request_digest,
        )
        return decision.allowed and decision.policy_generation == appraisal.policy_generation


class SignedNodeAttestationVerifier(SignedArdaAppraisalVerifier):
    """Verify ARDA evidence over the complete Commons node advertisement."""

    def __init__(
        self,
        public_key_path: str | Path,
        *,
        authority: str = "arda",
        expected_policy_generation: str = "",
    ):
        super().__init__(
            public_key_path,
            authority=authority,
            audience="commons-job-choir",
            expected_policy_generation=expected_policy_generation,
        )

    def __call__(self, node: Any) -> bool:
        value = node.attestation_evidence
        if not isinstance(value, Mapping) or node.attestation != "verified":
            return False
        body = {
            "node_id": node.node_id,
            "attestation": node.attestation,
            "capabilities": list(node.capabilities),
            "pressure_budget": node.pressure_budget,
            "reliability": node.reliability,
            "route_penalty": node.route_penalty,
            "expires_at": node.expires_at,
            "appraisal_ref": node.appraisal_ref,
        }
        return super().__call__(value, body)

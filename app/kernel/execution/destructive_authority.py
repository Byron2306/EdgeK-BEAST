"""Production signature verification for destructive execution decisions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from app.kernel.integration.signed_decision import verify_appraisal, verify_decision


@dataclass(frozen=True)
class DestructiveAuthorityVerifier:
    operator_key: Ed25519PublicKey
    arda_key: Ed25519PublicKey
    arda_authority: str = "arda"

    def verify(
        self,
        *,
        operator_approval: Mapping[str, Any],
        arda_appraisal: Mapping[str, Any],
        action_authority: str,
        request_digest: str,
        audience: str,
        policy_generation: str,
        appraisal_ref: str,
        now: float | None = None,
    ) -> None:
        decision = verify_decision(
            operator_approval,
            self.operator_key,
            expected_authority=action_authority,
            expected_request_digest=request_digest,
        )
        if not decision.allowed or decision.policy_generation != policy_generation:
            raise PermissionError("signed operator decision denied or policy mismatched")
        verify_appraisal(
            arda_appraisal,
            self.arda_key,
            expected_authority=self.arda_authority,
            expected_audience=audience,
            expected_policy_generation=policy_generation,
            expected_appraisal_ref=appraisal_ref,
            expected_request_digest=request_digest,
            now=now,
        )

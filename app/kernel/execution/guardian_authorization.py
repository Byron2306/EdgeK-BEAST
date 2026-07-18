"""Signed, exact, one-use authorization for Socket Guardian operations."""
from __future__ import annotations

from dataclasses import asdict
from typing import Any, Iterable, Mapping

from app.kernel.integration.one_use_capability import OneUseCapabilityLedger
from app.kernel.integration.request_binding import canonical_sha256


GUARDIAN_CAPABILITY_AUDIENCE = "beast-socket-guardian"
_UNSIGNED_TRANSPORT_FIELDS = frozenset({"request_id", "authorization_capability"})


def guardian_operation_body(request: Mapping[str, Any]) -> dict[str, Any]:
    """Return the exact operation body covered by an authority signature.

    The random transport correlation ID and the capability carrying the
    signature are deliberately excluded. Everything else, including the peer
    ProcessLease, workspace, appraisal, policy generation and registry digest,
    is bound into the digest.
    """

    return {
        str(key): value
        for key, value in request.items()
        if key not in _UNSIGNED_TRANSPORT_FIELDS
    }


def guardian_operation_digest(request: Mapping[str, Any]) -> str:
    return canonical_sha256(guardian_operation_body(request))


class GuardianCapabilityAuthorizer:
    """Fail-closed authorizer backed by a durable one-use capability ledger."""

    def __init__(
        self,
        ledger: OneUseCapabilityLedger,
        *,
        allowed_authorities: Iterable[str],
        audience: str = GUARDIAN_CAPABILITY_AUDIENCE,
    ) -> None:
        self.ledger = ledger
        self.allowed_authorities = frozenset(str(value) for value in allowed_authorities if value)
        self.audience = str(audience)
        if not self.allowed_authorities:
            raise ValueError("at least one guardian capability authority is required")
        if not self.audience:
            raise ValueError("guardian capability audience is required")

    def __call__(self, request: Mapping[str, Any]) -> bool:
        raw = request.get("authorization_capability")
        if not isinstance(raw, Mapping):
            raise PermissionError("signed one-use guardian operation capability is required")
        authority = str(raw.get("authority") or "")
        if authority not in self.allowed_authorities:
            raise PermissionError("guardian operation authority is not trusted")
        policy_generation = str(request.get("policy_generation") or "")
        appraisal_ref = str(request.get("appraisal_ref") or "")
        self.ledger.consume(
            raw,
            request_digest=guardian_operation_digest(request),
            authority=authority,
            expected_audience=self.audience,
            expected_policy_generation=policy_generation,
            expected_appraisal_ref=appraisal_ref,
        )
        return True


def capability_mapping(capability: Any) -> Mapping[str, Any]:
    """Normalize dataclass capabilities for client/provider adapters."""

    if isinstance(capability, Mapping):
        return dict(capability)
    try:
        return asdict(capability)
    except TypeError as exc:
        raise TypeError("operation capability provider returned an unsupported value") from exc

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping

from .residual_contracts import canonical_json, sha256_digest, utc_now_iso


class ResidualRefusalCode(str, Enum):
    NO_VERIFIED_MATCH = "no_verified_match"
    SCOPE_MISMATCH = "scope_mismatch"
    PRIVACY_MISMATCH = "privacy_mismatch"
    WORKSPACE_MISMATCH = "workspace_mismatch"
    POLICY_MISMATCH = "policy_mismatch"
    AUTHORITY_MISMATCH = "authority_mismatch"
    REVOKED = "revoked"
    STALE = "stale"
    EXPIRED = "expired"
    PRESSURE_REJECTED = "pressure_rejected"
    INCOMPATIBLE = "incompatible"
    ENGINE_UNAVAILABLE = "engine_unavailable"
    QUALITY_BELOW_THRESHOLD = "quality_below_threshold"
    COST_ABOVE_BUDGET = "cost_above_budget"
    VERIFICATION_FAILED = "verification_failed"
    ALL_ROUTES_REFUSED = "all_routes_refused"


@dataclass(frozen=True, slots=True)
class ResidualRefusal:
    code: ResidualRefusalCode
    message: str
    evidence_digest: str | None = None
    details: Mapping[str, Any] | None = None
    created_at: str = ""

    def __post_init__(self) -> None:
        if not self.message.strip():
            raise ValueError("refusal message must not be empty")
        if not self.created_at:
            object.__setattr__(self, "created_at", utc_now_iso())
        if self.details is not None:
            canonical_json(self.details)

    @property
    def refusal_digest(self) -> str:
        return sha256_digest({
            "code": self.code,
            "message": self.message,
            "evidence_digest": self.evidence_digest,
            "details": self.details,
            "created_at": self.created_at,
        })

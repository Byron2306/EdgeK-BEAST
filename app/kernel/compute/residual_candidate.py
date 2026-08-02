from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Mapping

from .residual_contracts import (
    ApplicabilityState,
    ResidualAuthority,
    ResidualRoute,
    VerificationState,
    canonical_json,
    ensure_route_authority,
    sha256_digest,
    utc_now_iso,
    validate_digest,
    validate_non_negative_number,
    validate_probability,
)
from .residual_refusal import ResidualRefusal


@dataclass(frozen=True, slots=True)
class ResidualCandidate:
    candidate_id: str
    route: ResidualRoute
    applicability: ApplicabilityState
    verification: VerificationState
    authority: ResidualAuthority

    predicted_latency_ms: float
    predicted_cpu_ms: float
    predicted_memory_bytes: int
    predicted_monetary_cost: float
    confidence: float
    expected_quality: float
    failure_probability: float

    workspace_id: str
    privacy_domain: str
    evidence_digest: str

    predicted_energy_joules: float | None = None
    expires_at: str | None = None
    refusal: ResidualRefusal | None = None
    metadata: Mapping[str, Any] | None = None
    created_at: str = ""

    def __post_init__(self) -> None:
        if not self.candidate_id.strip():
            raise ValueError("candidate_id must not be empty")
        if not self.workspace_id.strip():
            raise ValueError("workspace_id must not be empty")
        if not self.privacy_domain.strip():
            raise ValueError("privacy_domain must not be empty")
        ensure_route_authority(self.route, self.authority)
        validate_digest(self.evidence_digest, field_name="evidence_digest")
        validate_non_negative_number(self.predicted_latency_ms, field_name="predicted_latency_ms")
        validate_non_negative_number(self.predicted_cpu_ms, field_name="predicted_cpu_ms")
        if not isinstance(self.predicted_memory_bytes, int) or isinstance(self.predicted_memory_bytes, bool):
            raise TypeError("predicted_memory_bytes must be an integer")
        if self.predicted_memory_bytes < 0:
            raise ValueError("predicted_memory_bytes must be non-negative")
        validate_non_negative_number(self.predicted_monetary_cost, field_name="predicted_monetary_cost")
        validate_probability(self.confidence, field_name="confidence")
        validate_probability(self.expected_quality, field_name="expected_quality")
        validate_probability(self.failure_probability, field_name="failure_probability")
        if self.predicted_energy_joules is not None:
            validate_non_negative_number(self.predicted_energy_joules, field_name="predicted_energy_joules")
        if self.applicability is ApplicabilityState.APPLICABLE and self.refusal is not None:
            raise ValueError("an applicable candidate cannot carry a refusal")
        if self.applicability is ApplicabilityState.INAPPLICABLE and self.refusal is None:
            raise ValueError("an inapplicable candidate must carry a refusal")
        if self.metadata is not None:
            canonical_json(self.metadata)
        if not self.created_at:
            object.__setattr__(self, "created_at", utc_now_iso())

    @property
    def eligible(self) -> bool:
        return self.applicability is ApplicabilityState.APPLICABLE and self.verification is VerificationState.VERIFIED

    @property
    def expected_latency_ms(self) -> float:
        return self.predicted_latency_ms / max(1e-9, 1.0 - self.failure_probability)

    @property
    def expected_cost_vector(self) -> tuple[float, float, int, float]:
        return (
            self.expected_latency_ms,
            self.predicted_cpu_ms,
            self.predicted_memory_bytes,
            self.predicted_monetary_cost,
        )

    @property
    def candidate_digest(self) -> str:
        return sha256_digest({
            "candidate_id": self.candidate_id,
            "route": self.route,
            "applicability": self.applicability,
            "verification": self.verification,
            "authority": self.authority,
            "predicted_latency_ms": self.predicted_latency_ms,
            "predicted_cpu_ms": self.predicted_cpu_ms,
            "predicted_memory_bytes": self.predicted_memory_bytes,
            "predicted_energy_joules": self.predicted_energy_joules,
            "predicted_monetary_cost": self.predicted_monetary_cost,
            "confidence": self.confidence,
            "expected_quality": self.expected_quality,
            "failure_probability": self.failure_probability,
            "workspace_id": self.workspace_id,
            "privacy_domain": self.privacy_domain,
            "expires_at": self.expires_at,
            "evidence_digest": self.evidence_digest,
            "refusal": self.refusal,
            "metadata": self.metadata,
            "created_at": self.created_at,
        })

    def refuse(self, refusal: ResidualRefusal) -> "ResidualCandidate":
        return replace(self, applicability=ApplicabilityState.INAPPLICABLE, refusal=refusal)

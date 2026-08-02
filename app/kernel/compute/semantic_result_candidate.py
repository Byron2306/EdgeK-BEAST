from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping

from .residual_contracts import canonical_json, sha256_digest, utc_now_iso, validate_digest


class SemanticReuseClass(str, Enum):
    EXACT_VERIFIED = "exact_verified"
    BOUNDED_EQUIVALENT = "bounded_equivalent"
    CONTEXT_ONLY = "context_only"
    STALE = "stale"
    INCOMPATIBLE = "incompatible"
    UNVERIFIED = "unverified"
    REVOKED = "revoked"


@dataclass(frozen=True, slots=True)
class SemanticResultRecord:
    record_id: str
    request_digest: str
    normalized_request_digest: str
    task_class: str
    workspace_id: str
    privacy_domain: str
    result_digest: str
    source_state_digest: str
    policy_digest: str
    verifier_id: str
    verification_evidence_digest: str
    model_or_provider_provenance: str
    reuse_class: SemanticReuseClass
    result: Any
    verified_at: str
    expires_at: str | None = None
    revoked: bool = False
    metadata: Mapping[str, Any] | None = None
    created_at: str = ""

    def __post_init__(self) -> None:
        for name in (
            "record_id", "task_class", "workspace_id", "privacy_domain",
            "verifier_id", "model_or_provider_provenance", "verified_at",
        ):
            if not str(getattr(self, name)).strip():
                raise ValueError(f"{name} must not be empty")
        for name in (
            "request_digest", "normalized_request_digest", "result_digest",
            "source_state_digest", "policy_digest", "verification_evidence_digest",
        ):
            validate_digest(getattr(self, name), field_name=name)
        if sha256_digest(self.result) != self.result_digest:
            raise ValueError("result payload does not match result_digest")
        if self.metadata is not None:
            canonical_json(self.metadata)
        if not self.created_at:
            object.__setattr__(self, "created_at", utc_now_iso())

    @property
    def record_digest(self) -> str:
        return sha256_digest({
            "record_id": self.record_id,
            "request_digest": self.request_digest,
            "normalized_request_digest": self.normalized_request_digest,
            "task_class": self.task_class,
            "workspace_id": self.workspace_id,
            "privacy_domain": self.privacy_domain,
            "result_digest": self.result_digest,
            "source_state_digest": self.source_state_digest,
            "policy_digest": self.policy_digest,
            "verifier_id": self.verifier_id,
            "verification_evidence_digest": self.verification_evidence_digest,
            "model_or_provider_provenance": self.model_or_provider_provenance,
            "reuse_class": self.reuse_class,
            "verified_at": self.verified_at,
            "expires_at": self.expires_at,
            "revoked": self.revoked,
            "metadata": self.metadata,
            "created_at": self.created_at,
        })

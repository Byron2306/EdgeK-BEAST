from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping

from .residual_contracts import (
    ResidualAuthority,
    ResidualRoute,
    VerificationState,
    canonical_json,
    sha256_digest,
    utc_now_iso,
    validate_digest,
)


class SynthesisMode(str, Enum):
    EXACT = "exact"
    REALIZE = "realize"
    EXECUTE = "execute"
    LEXICALIZE = "lexicalize"
    OPEN = "open"


class SynthesisOutcome(str, Enum):
    VERIFIED = "verified"
    REFUSED = "refused"
    UNVERIFIED = "unverified"


@dataclass(frozen=True, slots=True)
class SynthesisRequest:
    request_id: str
    workspace_id: str
    privacy_domain: str
    task_class: str
    mode: SynthesisMode
    payload: Mapping[str, Any]
    evidence_digest: str | None = None
    policy_digest: str | None = None

    def __post_init__(self) -> None:
        if not self.request_id.strip():
            raise ValueError("request_id must not be empty")
        if not self.workspace_id.strip() or not self.privacy_domain.strip():
            raise ValueError("workspace_id and privacy_domain must not be empty")
        if not self.task_class.strip():
            raise ValueError("task_class must not be empty")
        if not isinstance(self.mode, SynthesisMode):
            object.__setattr__(self, "mode", SynthesisMode(self.mode))
        canonical_json(self.payload)
        if self.evidence_digest is not None:
            validate_digest(self.evidence_digest, field_name="evidence_digest")
        if self.policy_digest is not None:
            validate_digest(self.policy_digest, field_name="policy_digest")

    @property
    def request_digest(self) -> str:
        return sha256_digest(
            {
                "version": "beast.synthesis-request.v1",
                "request_id": self.request_id,
                "workspace_id": self.workspace_id,
                "privacy_domain": self.privacy_domain,
                "task_class": self.task_class,
                "mode": self.mode,
                "payload": self.payload,
                "evidence_digest": self.evidence_digest,
                "policy_digest": self.policy_digest,
            }
        )


@dataclass(frozen=True, slots=True)
class SynthesisReceipt:
    request_digest: str
    workspace_id: str
    privacy_domain: str
    task_class: str
    mode: SynthesisMode
    decision_digest: str
    verification_state: VerificationState
    outcome: SynthesisOutcome
    selected_route: ResidualRoute | None = None
    authority_required: ResidualAuthority | None = None
    authority_used: ResidualAuthority | None = None
    execution_digest: str = ""
    residual_closure_digest: str = ""
    provider_calls: int = 0
    local_inference_calls: int = 0
    physical_effects: int = 0
    reason: str = ""
    created_at: str = ""
    metadata: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        validate_digest(self.request_digest, field_name="request_digest")
        validate_digest(self.decision_digest, field_name="decision_digest")
        if self.execution_digest:
            validate_digest(self.execution_digest, field_name="execution_digest")
        if self.residual_closure_digest:
            validate_digest(self.residual_closure_digest, field_name="residual_closure_digest")
        if not self.workspace_id.strip() or not self.privacy_domain.strip() or not self.task_class.strip():
            raise ValueError("receipt scope fields must not be empty")
        if not isinstance(self.mode, SynthesisMode):
            object.__setattr__(self, "mode", SynthesisMode(self.mode))
        if not isinstance(self.outcome, SynthesisOutcome):
            object.__setattr__(self, "outcome", SynthesisOutcome(self.outcome))
        if self.outcome is SynthesisOutcome.VERIFIED:
            if self.verification_state is not VerificationState.VERIFIED:
                raise ValueError("verified synthesis receipts must carry verified state")
            if None in (self.selected_route, self.authority_required, self.authority_used):
                raise ValueError("verified synthesis receipts require route and authority")
            if not self.execution_digest or not self.residual_closure_digest:
                raise ValueError("verified synthesis receipts require execution and closure digests")
        if self.outcome is SynthesisOutcome.REFUSED:
            if self.selected_route is not None or self.authority_used is not None:
                raise ValueError("refused synthesis receipts cannot carry selected execution")
        if min(self.provider_calls, self.local_inference_calls, self.physical_effects) < 0:
            raise ValueError("synthesis counters must be non-negative")
        if self.metadata is not None:
            canonical_json(self.metadata)
        if not self.created_at:
            object.__setattr__(self, "created_at", utc_now_iso())

    @property
    def receipt_digest(self) -> str:
        return sha256_digest(self)

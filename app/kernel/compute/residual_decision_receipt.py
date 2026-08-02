from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from .residual_candidate import ResidualCandidate
from .residual_contracts import (
    DecisionPolicy,
    ResidualAuthority,
    ResidualRoute,
    canonical_json,
    sha256_digest,
    utc_now_iso,
    validate_digest,
)
from .residual_refusal import ResidualRefusal


@dataclass(frozen=True, slots=True)
class ResidualAlternative:
    candidate_id: str
    route: ResidualRoute
    eligible: bool
    candidate_digest: str
    score: float | None = None
    refusal: ResidualRefusal | None = None

    def __post_init__(self) -> None:
        validate_digest(self.candidate_digest, field_name="candidate_digest")
        if self.eligible and self.refusal is not None:
            raise ValueError("eligible alternative cannot carry a refusal")
        if not self.eligible and self.refusal is None:
            raise ValueError("ineligible alternative must carry a refusal")


@dataclass(frozen=True, slots=True)
class ResidualDecisionReceipt:
    request_digest: str
    workspace_id: str
    privacy_domain: str
    policy: DecisionPolicy
    selected_route: ResidualRoute | None
    selected_candidate_id: str | None
    selected_candidate_digest: str | None
    authority_required: ResidualAuthority | None
    reason: str
    alternatives: tuple[ResidualAlternative, ...]
    refusal: ResidualRefusal | None = None
    policy_digest: str | None = None
    metadata: Mapping[str, Any] | None = None
    created_at: str = ""

    def __post_init__(self) -> None:
        validate_digest(self.request_digest, field_name="request_digest")
        if self.policy_digest is not None:
            validate_digest(self.policy_digest, field_name="policy_digest")
        if not self.workspace_id.strip() or not self.privacy_domain.strip():
            raise ValueError("workspace_id and privacy_domain must not be empty")
        if not self.reason.strip():
            raise ValueError("decision reason must not be empty")
        if not self.created_at:
            object.__setattr__(self, "created_at", utc_now_iso())
        selected_fields = (
            self.selected_route,
            self.selected_candidate_id,
            self.selected_candidate_digest,
            self.authority_required,
        )
        if self.refusal is None:
            if any(value is None for value in selected_fields):
                raise ValueError("successful decision requires all selected fields")
            validate_digest(self.selected_candidate_digest or "", field_name="selected_candidate_digest")
        else:
            if any(value is not None for value in selected_fields):
                raise ValueError("refused decision cannot name a selected route or authority")
        if self.metadata is not None:
            canonical_json(self.metadata)
        candidate_ids = [alternative.candidate_id for alternative in self.alternatives]
        if len(candidate_ids) != len(set(candidate_ids)):
            raise ValueError("decision alternatives must have unique candidate IDs")
        if self.selected_candidate_id is not None:
            matches = [item for item in self.alternatives if item.candidate_id == self.selected_candidate_id]
            if len(matches) != 1 or not matches[0].eligible:
                raise ValueError("selected candidate must appear exactly once as eligible")

    @property
    def decision_digest(self) -> str:
        return sha256_digest({
            "request_digest": self.request_digest,
            "workspace_id": self.workspace_id,
            "privacy_domain": self.privacy_domain,
            "policy": self.policy,
            "selected_route": self.selected_route,
            "selected_candidate_id": self.selected_candidate_id,
            "selected_candidate_digest": self.selected_candidate_digest,
            "authority_required": self.authority_required,
            "reason": self.reason,
            "alternatives": self.alternatives,
            "refusal": self.refusal,
            "policy_digest": self.policy_digest,
            "metadata": self.metadata,
            "created_at": self.created_at,
        })

    def verify_integrity(self, expected_digest: str) -> bool:
        validate_digest(expected_digest, field_name="expected_digest")
        return self.decision_digest == expected_digest


def alternatives_from_candidates(
    candidates: Iterable[ResidualCandidate],
    *,
    scores: Mapping[str, float] | None = None,
) -> tuple[ResidualAlternative, ...]:
    score_map = scores or {}
    return tuple(
        ResidualAlternative(
            candidate_id=item.candidate_id,
            route=item.route,
            eligible=item.eligible,
            candidate_digest=item.candidate_digest,
            score=score_map.get(item.candidate_id),
            refusal=item.refusal if not item.eligible else None,
        )
        for item in candidates
    )

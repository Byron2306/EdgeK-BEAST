from __future__ import annotations

from enum import Enum


class ApprovalState(str, Enum):
    REQUESTED = "REQUESTED"
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    EDITED_AND_APPROVED = "EDITED_AND_APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"
    CONSUMED = "CONSUMED"
    REVOKED = "REVOKED"


TERMINAL_STATES = frozenset({
    ApprovalState.REJECTED,
    ApprovalState.EXPIRED,
    ApprovalState.CANCELLED,
    ApprovalState.CONSUMED,
    ApprovalState.REVOKED,
})

LEGAL_TRANSITIONS: dict[ApprovalState, frozenset[ApprovalState]] = {
    ApprovalState.REQUESTED: frozenset({ApprovalState.PENDING, ApprovalState.CANCELLED, ApprovalState.EXPIRED}),
    ApprovalState.PENDING: frozenset({
        ApprovalState.APPROVED,
        ApprovalState.EDITED_AND_APPROVED,
        ApprovalState.REJECTED,
        ApprovalState.CANCELLED,
        ApprovalState.EXPIRED,
        ApprovalState.REVOKED,
    }),
    ApprovalState.APPROVED: frozenset({ApprovalState.CONSUMED, ApprovalState.REVOKED, ApprovalState.EXPIRED}),
    ApprovalState.EDITED_AND_APPROVED: frozenset({ApprovalState.CONSUMED, ApprovalState.REVOKED, ApprovalState.EXPIRED}),
    ApprovalState.REJECTED: frozenset(),
    ApprovalState.EXPIRED: frozenset(),
    ApprovalState.CANCELLED: frozenset(),
    ApprovalState.CONSUMED: frozenset(),
    ApprovalState.REVOKED: frozenset(),
}


def normalize_state(value: ApprovalState | str) -> ApprovalState:
    if isinstance(value, ApprovalState):
        return value
    text = str(value or "").strip().upper()
    try:
        return ApprovalState(text)
    except ValueError as exc:
        raise ValueError(f"unknown approval state: {value!r}") from exc


def can_transition(current: ApprovalState | str, target: ApprovalState | str) -> bool:
    return normalize_state(target) in LEGAL_TRANSITIONS[normalize_state(current)]


def require_transition(current: ApprovalState | str, target: ApprovalState | str) -> tuple[ApprovalState, ApprovalState]:
    source = normalize_state(current)
    destination = normalize_state(target)
    if destination not in LEGAL_TRANSITIONS[source]:
        raise ValueError(f"illegal approval transition: {source.value} -> {destination.value}")
    return source, destination

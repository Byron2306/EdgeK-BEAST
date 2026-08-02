"""Canonical lifecycle states for durable BEAST agent runs."""

from __future__ import annotations

from enum import Enum


class AgentRunState(str, Enum):
    CREATED = "created"
    SCOPING = "scoping"
    PLANNING = "planning"
    OBSERVING = "observing"
    WAITING_FOR_APPROVAL = "waiting_for_approval"
    EXECUTING_TOOL = "executing_tool"
    UPDATING_PLAN = "updating_plan"
    EDITING_WORKTREE = "editing_worktree"
    VERIFYING = "verifying"
    DIAGNOSING = "diagnosing"
    REPAIRING = "repairing"
    FINALIZING = "finalizing"
    SOURCEPLAN_READY = "sourceplan_ready"
    WAITING_FOR_PROMOTION = "waiting_for_promotion"
    PROMOTING = "promoting"
    POST_VERIFY = "post_verify"
    PAUSED = "paused"
    CANCELLING = "cancelling"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"
    BUDGET_EXHAUSTED = "budget_exhausted"
    POLICY_BLOCKED = "policy_blocked"
    REJECTED = "rejected"
    ROLLED_BACK = "rolled_back"


TERMINAL_STATES = frozenset({
    AgentRunState.COMPLETED,
    AgentRunState.CANCELLED,
    AgentRunState.FAILED,
    AgentRunState.BUDGET_EXHAUSTED,
    AgentRunState.POLICY_BLOCKED,
    AgentRunState.REJECTED,
    AgentRunState.ROLLED_BACK,
})

# The graph is deliberately permissive for the compatibility stream while still
# forbidding resurrection from terminal states. Phase 2B can narrow individual
# model/tool transitions after all callers use the canonical runtime.
_ALLOWED: dict[AgentRunState, frozenset[AgentRunState]] = {
    state: frozenset(AgentRunState)
    for state in AgentRunState
    if state not in TERMINAL_STATES
}
_ALLOWED[AgentRunState.CANCELLING] = frozenset({AgentRunState.CANCELLED, AgentRunState.FAILED})
for terminal in TERMINAL_STATES:
    _ALLOWED[terminal] = frozenset()


def normalize_state(value: str | AgentRunState) -> AgentRunState:
    if isinstance(value, AgentRunState):
        return value
    return AgentRunState(str(value or "").strip().lower())


def can_transition(current: str | AgentRunState, target: str | AgentRunState) -> bool:
    source = normalize_state(current)
    destination = normalize_state(target)
    return source == destination or destination in _ALLOWED[source]


def require_transition(current: str | AgentRunState, target: str | AgentRunState) -> AgentRunState:
    source = normalize_state(current)
    destination = normalize_state(target)
    if not can_transition(source, destination):
        raise ValueError(f"invalid agent run transition: {source.value} -> {destination.value}")
    return destination

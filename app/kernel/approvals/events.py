from __future__ import annotations

APPROVAL_EVENT_TYPES = frozenset({
    "agent.approval.requested",
    "agent.approval.pending",
    "agent.approval.approved",
    "agent.approval.edited_and_approved",
    "agent.approval.rejected",
    "agent.approval.expired",
    "agent.approval.cancelled",
    "agent.approval.consumed",
    "agent.approval.revoked",
})

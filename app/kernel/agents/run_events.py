"""Event contracts and legacy SSE projection for BEAST agent runs."""

from __future__ import annotations

import json
from typing import Any

from app.kernel.agents.run_state import AgentRunState


LEGACY_TO_CANONICAL: dict[str, str] = {
    "agent_run_registered": "agent.run.registered",
    "agent_run_started": "agent.run.started",
    "agent_run_stage": "agent.stage.updated",
    "agent_run_context": "agent.context.ready",
    "agent_run_preflight": "agent.plan.preflight",
    "agent_run_token": "agent.model.delta",
    "agent_run_provider_done": "agent.model.completed",
    "agent_run_tool": "agent.tool.event",
    "agent_run_permission_request": "agent.approval.requested",
    "agent_run_validation": "agent.verification.completed",
    "agent_run_scorecard": "agent.review.completed",
    "agent_run_intelligence": "agent.intelligence.completed",
    "agent_run_crystal": "agent.crystal.observed",
    "agent_run_compute": "agent.compute.observed",
    "agent_run_sourceplan": "agent.sourceplan.ready",
    "agent_run_advisory": "agent.run.advisory",
    "agent_run_needs_operator": "agent.run.operator_required",
    "agent_run_request": "agent.context.requested",
    "agent_run_error": "agent.run.error",
    "agent_run_done": "agent.run.completed",
}

# The durable planner emits canonical event names directly, while the current
# Electron Pair Programmer subscribes to the original ``agent_run_*`` names.
# Keep the legacy projection genuinely compatible in both directions so a
# stream can be replayed by older and newer clients alike.
CANONICAL_TO_LEGACY: dict[str, str] = {value: key for key, value in LEGACY_TO_CANONICAL.items()}


def parse_sse_chunk(chunk: str) -> tuple[str, dict[str, Any]] | None:
    """Parse one BEAST SSE frame without changing its wire representation."""
    if not isinstance(chunk, str) or not chunk.strip():
        return None
    event_type = "message"
    data_lines: list[str] = []
    for line in chunk.splitlines():
        if line.startswith("event:"):
            event_type = line.split(":", 1)[1].strip() or "message"
        elif line.startswith("data:"):
            data_lines.append(line.split(":", 1)[1].lstrip())
    if not data_lines:
        return None
    try:
        value = json.loads("\n".join(data_lines))
    except json.JSONDecodeError:
        value = {"raw": "\n".join(data_lines)}
    if isinstance(value, dict) and isinstance(value.get("payload"), dict):
        payload = dict(value["payload"])
    elif isinstance(value, dict):
        payload = dict(value)
    else:
        payload = {"value": value}
    return event_type, payload


def canonical_event_type(legacy_type: str, payload: dict[str, Any]) -> str:
    if legacy_type == "agent_run_tool":
        if str(payload.get("type") or "") == "tool_call":
            return "agent.tool.started"
        if str(payload.get("status") or "") in {"failed", "deferred"}:
            return "agent.tool.failed"
        return "agent.tool.completed"
    if legacy_type == "agent_run_done":
        if str(payload.get("sourceplan_status") or "") in {"cancelled", "cancelling"}:
            return "agent.run.cancelled"
        if payload.get("ok") is False:
            return "agent.run.failed"
    return LEGACY_TO_CANONICAL.get(legacy_type, f"agent.legacy.{legacy_type}")


def legacy_event_projection(event_type: str, payload: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """Project canonical planner events onto the Pair Programmer wire contract."""
    name = CANONICAL_TO_LEGACY.get(event_type, "")
    projected = dict(payload or {})
    if event_type in {"agent.planner.started", "agent.planner.turn.started", "agent.planner.decision"}:
        name = "agent_run_stage"
        if event_type == "agent.planner.started":
            projected.setdefault("text", "agent planner started")
        elif event_type == "agent.planner.turn.started":
            projected.setdefault("text", f"planner turn {projected.get('turn', '?')} started")
        else:
            decision = projected.get("decision") if isinstance(projected.get("decision"), dict) else {}
            projected.setdefault("text", f"planner selected {decision.get('decision_type', 'next action')}")
    elif event_type in {"agent.planner.completed", "agent.planner.budget_exhausted"}:
        name = "agent_run_done"
        projected.setdefault("ok", event_type == "agent.planner.completed")
        projected.setdefault("sourceplan_status", "completed" if event_type == "agent.planner.completed" else "budget_exhausted")
    elif event_type == "agent.planner.blocked":
        name = "agent_run_needs_operator"
        projected.setdefault("ok", False)
        projected.setdefault("error", projected.get("blocker") or "planner blocked")
    elif event_type in {"agent.repair.required", "agent.repair.budget_exhausted"}:
        name = "agent_run_stage"
        projected.setdefault("text", "verification repair required" if event_type == "agent.repair.required" else "verification repair budget exhausted")
    elif event_type == "agent.verification.passed":
        name = "agent_run_validation"
        projected.setdefault("status", "passed")
    elif event_type == "agent.verification.failed":
        name = "agent_run_validation"
        projected.setdefault("status", "failed")
    elif event_type == "agent.model.delta":
        name = "agent_run_token"
    elif event_type in {"agent.planner.observation.accepted", "agent.planner.completion_rejected"}:
        name = "agent_run_stage"
        projected.setdefault("text", "planner observation accepted" if event_type.endswith("accepted") else "completion held until verification and SourcePlan evidence exist")
    elif event_type == "agent.tool.started":
        name = "agent_run_tool"
        projected.setdefault("type", "tool_call")
        projected.setdefault("tool", projected.get("tool_id") or "BEAST governed tool")
        projected.setdefault("text", f"Calling {projected.get('tool')}")
    elif event_type in {"agent.tool.completed", "agent.tool.failed"}:
        name = "agent_run_tool"
        observation = projected.get("observation") if isinstance(projected.get("observation"), dict) else {}
        projected.setdefault("type", "tool_result")
        projected.setdefault("tool", observation.get("tool_id") or projected.get("tool_id") or "BEAST governed tool")
        projected.setdefault("status", "failed" if event_type == "agent.tool.failed" else "completed")
        projected.setdefault("text", observation.get("error") or f"{projected.get('tool')} finished")
    elif not name and event_type.startswith("agent.planner."):
        name = "agent_run_stage"
        projected.setdefault("text", event_type.replace("agent.", "").replace(".", " "))
    return name or event_type, projected


def state_for_event(event_type: str, payload: dict[str, Any]) -> AgentRunState | None:
    if event_type == "agent.run.registered":
        return AgentRunState.SCOPING
    if event_type in {"agent.run.started", "agent.context.ready"}:
        return AgentRunState.OBSERVING
    if event_type == "agent.stage.updated":
        text = str(payload.get("text") or "").strip().lower()
        if "waiting" in text and "approval" in text:
            return AgentRunState.WAITING_FOR_APPROVAL
        return AgentRunState.PLANNING
    if event_type == "agent.plan.preflight":
        return AgentRunState.PLANNING
    if event_type == "agent.approval.requested":
        return AgentRunState.WAITING_FOR_APPROVAL
    if event_type == "agent.tool.started":
        return AgentRunState.EXECUTING_TOOL
    if event_type in {"agent.tool.completed", "agent.tool.failed"}:
        return AgentRunState.UPDATING_PLAN
    if event_type == "agent.model.delta":
        return AgentRunState.PLANNING
    if event_type == "agent.model.completed":
        return AgentRunState.FINALIZING
    if event_type == "agent.verification.completed":
        status = str(payload.get("status") or "").lower()
        if status in {"failed", "error"}:
            return AgentRunState.DIAGNOSING
        return AgentRunState.VERIFYING
    if event_type == "agent.sourceplan.ready":
        return AgentRunState.SOURCEPLAN_READY
    if event_type == "agent.run.operator_required":
        return AgentRunState.PAUSED
    if event_type == "agent.run.cancelled":
        return AgentRunState.CANCELLED
    if event_type == "agent.run.failed":
        return AgentRunState.FAILED
    if event_type == "agent.run.completed":
        return AgentRunState.COMPLETED
    if event_type == "agent.run.error":
        return AgentRunState.FAILED
    return None

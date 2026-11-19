"""Direct coding execution for BEAST Coder.

The selected coding model chooses individual governed tool actions. This class
does not instantiate AgentPlannerRuntime, any fallback planner, or a planning
subagent. The existing provider classes are used solely as model/action
transport adapters until native tool-call transport replaces the JSON codec.
"""
from __future__ import annotations

import json
import os
import uuid
from typing import Any

from app.kernel.agents.planner_models import PlannerDecision, PlannerDecisionType
from app.kernel.agents.run_state import AgentRunState, TERMINAL_STATES, normalize_state

# Only workspace-bounded actions receive delegated autopilot authority.
# Promotion and external effects are never silently auto-approved here.
AUTOPILOT_TOOLS = frozenset({
    "workspace.index", "workspace.list", "workspace.search_text",
    "workspace.read_range", "worktree.bind", "worktree.replace_exact",
    "worktree.write_file", "worktree.verify", "worktree.sourceplan_draft",
    "worktree.diff", "worktree.status",
})


class DirectCoderRuntime:
    """Single selected-model coding turn, persisted across /next calls."""

    def __init__(self, engine: Any, provider: Any, *, max_turns: int = 32):
        self.engine = engine
        self.provider = provider
        self.max_turns = max(1, min(int(max_turns), 64))

    def _state(self, run_id: str) -> dict[str, Any]:
        run = self.engine.store.get_run(run_id) or {}
        checkpoint = run.get("checkpoint") or {}
        return dict(checkpoint.get("direct_coder") or {})

    def _save(self, run_id: str, state: dict[str, Any]) -> None:
        self.engine.merge_checkpoint(run_id, {"direct_coder": state})

    def _emit(self, run_id: str, event: str, **payload: Any) -> None:
        self.engine.emit(run_id, event, payload)

    def _transition(self, run_id: str, state: AgentRunState, *, error: str = "") -> None:
        current = self.engine.store.get_run(run_id) or {}
        if normalize_state(str(current.get("state") or "created")) is not state:
            self.engine.store.transition(run_id, state, error=error)

    def _snapshot(self, run_id: str) -> dict[str, Any]:
        return self.engine.store.get_run(run_id) or {}

    def _prompt(self, run: dict[str, Any], state: dict[str, Any]) -> str:
        tools = self.engine.list_tools()
        allowed = []
        for tool in tools:
            if not isinstance(tool, dict):
                continue
            tid = str(tool.get("tool_id") or "")
            if not tid or tid.startswith(("sourceplan.promote", "promotion.")):
                continue
            allowed.append({
                "tool_id": tid,
                "description": str(tool.get("description") or "")[:230],
                "input_schema": tool.get("input_schema") or {},
            })
        request = run.get("request") or {}
        recent = list(state.get("observations") or [])[-5:]
        # Do not stuff an entire repository index or tool output into the model.
        observations = json.dumps(recent, default=str, ensure_ascii=False)[-18000:]
        targets = request.get("context_files") or []
        return (
            "BEAST DIRECT CODING AGENT. You are the selected coding model, "
            "not a planner subagent. Execute the operator's task using ONE "
            "governed tool call per turn. Inspect exact file contents before editing. "
            "Never invent file contents, evidence, test results, or authorization. "
            "All writes must go through a bound isolated worktree. "
            "After edits, call worktree.verify and prepare a sourceplan when possible. "
            "When the task is actually finished, return a COMPLETE decision. "
            "Do not report completion for unverified changes. "
            "Your response MUST be one JSON object with decision_type tool, "
            "complete or blocked; tool_id, arguments, and summary/blocker. "
            "Tool decision: {\"decision_type\":\"tool\",\"tool_id\":\"workspace.read_range\",\"arguments\":{...}}. "
            "Completion: {\"decision_type\":\"complete\",\"tool_id\":\"\",\"arguments\":{},\"summary\":\"...\"}.\n"
            f"OBJECTIVE: {str(run.get('objective') or '')[:4500]}\n"
            f"EXPLICIT FILES: {json.dumps(targets, ensure_ascii=False)[:2500]}\n"
            f"TOOLS: {json.dumps(allowed, ensure_ascii=False, default=str)[:18000]}\n"
            f"PRIOR OBSERVATIONS: {observations}\n"
            f"TURN: {int(state.get('turn') or 0) + 1}\n"
        )

    @staticmethod
    def _compact_observation(tool_id: str, observation: dict[str, Any]) -> dict[str, Any]:
        result = observation.get("result") if isinstance(observation.get("result"), dict) else {}
        if tool_id == "workspace.index":
            summary = {"summary": result.get("summary"), "index_digest": result.get("index_digest"),
                       "files": [{"path": str(item.get("path") or "")}
                                 for item in (result.get("files") or [])[:24]
                                 if isinstance(item, dict)]}
        elif tool_id == "workspace.read_range":
            summary = {k: v for k, v in result.items() if k != "content"}
            summary["content"] = str(result.get("content") or "")[:16000]
        else:
            summary = result
        rendered = json.dumps(summary, default=str, ensure_ascii=False)
        if len(rendered) > 18000:
            summary = {"truncated_result_preview": rendered[:16000],
                       "truncated": True}
        return {"tool_id": tool_id,
                "status": str(observation.get("status") or "completed"),
                "result": summary}

    @staticmethod
    def _autopilot(run: dict[str, Any]) -> bool:
        request = run.get("request") or {}
        return str(request.get("autonomy") or "").lower() in {"autopilot", "auto"}

    def _approval(self, run_id: str, run: dict[str, Any], decision: PlannerDecision, spec: Any,
                  state: dict[str, Any]) -> tuple[str, bool]:
        """Return (approval_id, parked). Approval records stay in the durable store."""
        request = run.get("request") or {}
        if not getattr(spec, "requires_approval", False):
            return "", False
        if self._autopilot(run) and decision.tool_id in AUTOPILOT_TOOLS:
            approval_id = f"approval-{uuid.uuid4().hex[:16]}"
            paths = [str(decision.arguments[k]) for k in ("path", "target_path") if decision.arguments.get(k)]
            approval_request = {
                "request_id": approval_id, "run_id": run_id,
                "tool_id": decision.tool_id,
                "summary": "Direct coder delegated worktree action",
                "risk_class": getattr(getattr(spec, "risk", None), "value", "governed"),
                "execution_target": decision.execution_target,
                "safe_arguments": decision.arguments,
                "affected_files": paths,
                "capabilities": [{"id": decision.tool_id, "paths": paths}],
                "autonomy": "autopilot",
            }
            self.engine.store.create_approval(run_id, approval_request)
            self.engine.store.resolve_approval(run_id, approval_id, {
                "approved": True, "scope": "run", "operator": "autopilot",
                "reason": "operator_delegated_workspace_bounded_tools",
            })
            self._emit(run_id, "agent.approval.autopilot_granted",
                       tool_id=decision.tool_id, approval_id=approval_id)
            return approval_id, False
        approval_id = f"approval-{uuid.uuid4().hex[:16]}"
        paths = [str(decision.arguments[k]) for k in ("path", "target_path") if decision.arguments.get(k)]
        self.engine.store.create_approval(run_id, {
            "request_id": approval_id, "run_id": run_id,
            "tool_id": decision.tool_id,
            "summary": f"Approve direct coder action: {decision.tool_id}",
            "risk_class": getattr(getattr(spec, "risk", None), "value", "governed"),
            "execution_target": decision.execution_target,
            "safe_arguments": decision.arguments,
            "affected_files": paths,
            "capabilities": [{"id": decision.tool_id, "paths": paths}],
        })
        state["pending"] = {"approval_id": approval_id, "decision": decision.as_dict()}
        self._save(run_id, state)
        self._emit(run_id, "agent.approval.requested",
                   approval_id=approval_id, tool_id=decision.tool_id)
        self._transition(run_id, AgentRunState.WAITING_FOR_APPROVAL)
        return approval_id, True

    async def run_one_turn(self, run_id: str) -> dict[str, Any]:
        run = self._snapshot(run_id)
        if not run:
            raise KeyError(f"unknown AgentRun: {run_id}")
        status = normalize_state(str(run.get("state") or "created"))
        if status in TERMINAL_STATES:
            return run
        state = self._state(run_id)
        turn = int(state.get("turn") or 0)
        if turn >= self.max_turns:
            self._emit(run_id, "agent.coder.budget_exhausted", turns=turn)
            self._transition(run_id, AgentRunState.BUDGET_EXHAUSTED)
            return self._snapshot(run_id)
        if not state.get("started"):
            state["started"] = True
            self._save(run_id, state)
            self._emit(run_id, "agent.coder.started",
                       engine="direct_coder_v1", model=run.get("model"))
        pending = state.get("pending")
        if isinstance(pending, dict):
            approval_id = str(pending.get("approval_id") or "")
            approval = self.engine.store.get_approval(run_id, approval_id) or {}
            if str(approval.get("status") or "").lower() != "approved":
                if str(approval.get("status") or "").lower() in {"rejected", "declined", "expired"}:
                    self._transition(run_id, AgentRunState.PAUSED,
                                     error="operator declined tool approval")
                else:
                    self._transition(run_id, AgentRunState.WAITING_FOR_APPROVAL)
                return self._snapshot(run_id)
            raw = pending["decision"]
            decision = PlannerDecision(
                decision_type=PlannerDecisionType(raw["decision_type"]),
                tool_id=raw.get("tool_id", ""), arguments=raw.get("arguments") or {},
                execution_target=raw.get("execution_target") or "local",
            )
            state.pop("pending", None)
            state["resuming_approval_id"] = approval_id
            self._save(run_id, state)
        else:
            self._transition(run_id, AgentRunState.PLANNING)
            self._emit(run_id, "agent.coder.turn.started", turn=turn + 1)
            try:
                decision = await self.provider.next_decision(
                    self._prompt(run, state), run=run, turn=turn + 1
                )
            except Exception as exc:
                self._emit(run_id, "agent.coder.provider_paused",
                           reason=type(exc).__name__, message=str(exc)[:300])
                self._transition(run_id, AgentRunState.PAUSED,
                                 error=f"coding model unavailable: {type(exc).__name__}")
                return self._snapshot(run_id)
        self._emit(run_id, "agent.coder.decision", turn=turn + 1,
                   decision=decision.as_dict())
        if decision.decision_type is PlannerDecisionType.BLOCKED:
            self._transition(run_id, AgentRunState.PAUSED,
                             error=str(decision.blocker or "coding model requested help")[:400])
            self._emit(run_id, "agent.coder.paused", reason=decision.blocker)
            return self._snapshot(run_id)
        if decision.decision_type is PlannerDecisionType.COMPLETE:
            observations = state.get("observations") or []
            mutation_positions = [
                i for i, o in enumerate(observations)
                if str(o.get("tool_id") or "") in {
                    "worktree.replace_exact", "worktree.write_file"
                } and o.get("status") == "completed"
            ]
            mutated = bool(mutation_positions)
            last_mutation = max(mutation_positions, default=-1)
            verified = any(
                i > last_mutation and o.get("tool_id") == "worktree.verify"
                and o.get("status") == "completed"
                and isinstance(o.get("result"), dict)
                and o["result"].get("ok") is True
                and int(o["result"].get("returncode") or 0) == 0
                for i, o in enumerate(observations)
            )
            if mutated and not verified:
                self._emit(run_id, "agent.coder.completion_refused",
                           reason="mutated_worktree_not_verified")
                state.setdefault("observations", []).append({
                    "tool_id": "completion", "status": "failed",
                    "error": "Run worktree.verify before claiming completion.",
                })
            else:
                self._emit(run_id, "agent.coder.completed", summary=decision.summary)
                self._transition(run_id, AgentRunState.COMPLETED)
                return self._snapshot(run_id)
        elif decision.decision_type is PlannerDecisionType.TOOL:
            try:
                spec = self.engine.tool_registry.get(decision.tool_id)
                if decision.tool_id.startswith(("sourceplan.promote", "promotion.")):
                    raise ValueError("promotion is not available to direct coder")
                args = self.engine.tool_registry.validate_arguments(spec, decision.arguments)
                # Never silently replace user-supplied model arguments.
                for key, value in decision.arguments.items():
                    if key not in args or args[key] != value:
                        raise ValueError(f"tool arguments changed during validation: {key}")
                if not state.get("resuming_approval_id"):
                    approval_id, parked = self._approval(run_id, run, decision, spec, state)
                    if parked:
                        return self._snapshot(run_id)
                else:
                    approval_id = state.pop("resuming_approval_id")
                self._transition(run_id, AgentRunState.EXECUTING_TOOL)
                self._emit(run_id, "agent.tool.started", tool_id=decision.tool_id)
                observation = await self.engine.execute_tool(
                    run_id, decision.tool_id, args,
                    execution_target=decision.execution_target,
                    approval_id=approval_id,
                )
                self._emit(run_id, "agent.tool.completed",
                           tool_id=decision.tool_id, observation=observation)
                entry = self._compact_observation(decision.tool_id, observation)
            except Exception as exc:
                self._emit(run_id, "agent.tool.failed",
                           tool_id=decision.tool_id, error=str(exc)[:600])
                entry = {"tool_id": decision.tool_id,
                         "status": "failed", "error": str(exc)[:1200]}
            state.setdefault("observations", []).append(entry)
        state["turn"] = turn + 1
        state["observations"] = list(state.get("observations") or [])[-16:]
        self._save(run_id, state)
        self._transition(run_id, AgentRunState.OBSERVING)
        return self._snapshot(run_id)

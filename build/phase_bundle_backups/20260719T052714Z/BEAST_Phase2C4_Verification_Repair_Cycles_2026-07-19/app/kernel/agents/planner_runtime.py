"""Durable bounded model -> tool -> observation loop for BEAST AgentRuns."""

from __future__ import annotations

import json
from typing import Any

from app.kernel.agents.planner_models import PlannerDecisionType, PlannerState
from app.kernel.agents.planner_provider import PlannerProvider
from app.kernel.agents.run_state import AgentRunState, TERMINAL_STATES, normalize_state


class PlannerBudgetExhausted(RuntimeError):
    pass


class AgentPlannerRuntime:
    def __init__(self, engine: Any, provider: PlannerProvider, *, max_turns: int = 8, observation_limit: int = 12):
        self.engine = engine
        self.provider = provider
        self.max_turns = max(1, min(int(max_turns), 64))
        self.observation_limit = max(1, min(int(observation_limit), 50))

    def _checkpoint(self, run_id: str) -> dict[str, Any]:
        run = self.engine.store.get_run(run_id) or {}
        checkpoint = run.get("checkpoint") if isinstance(run.get("checkpoint"), dict) else {}
        return dict(checkpoint)

    def _load_state(self, run_id: str) -> PlannerState:
        checkpoint = self._checkpoint(run_id)
        raw = checkpoint.get("planner") if isinstance(checkpoint.get("planner"), dict) else {}
        return PlannerState(
            run_id=run_id,
            turn=max(0, int(raw.get("turn") or 0)),
            max_turns=max(1, int(raw.get("max_turns") or self.max_turns)),
            status=str(raw.get("status") or "ready"),
            last_decision=raw.get("last_decision") if isinstance(raw.get("last_decision"), dict) else {},
            observations=raw.get("observations") if isinstance(raw.get("observations"), list) else [],
            final_summary=str(raw.get("final_summary") or ""),
            blocker=str(raw.get("blocker") or ""),
        )

    def _save_state(self, state: PlannerState) -> None:
        checkpoint = self._checkpoint(state.run_id)
        checkpoint["planner"] = state.as_dict()
        self.engine.checkpoint(state.run_id, checkpoint)

    def _prompt(self, run: dict[str, Any], state: PlannerState) -> str:
        tools = self.engine.list_tools()
        compact_tools = [{
            "tool_id": tool.get("tool_id"),
            "description": tool.get("description"),
            "effect": tool.get("effect"),
            "risk": tool.get("risk"),
            "input_schema": tool.get("input_schema"),
        } for tool in tools]
        observations = state.observations[-self.observation_limit:]
        contract = {
            "decision_type": "tool | complete | blocked",
            "tool_id": "required only for tool",
            "arguments": "object required for tool",
            "execution_target": "local unless tool declares otherwise",
            "rationale": "brief reason",
            "summary": "required for complete",
            "blocker": "required for blocked",
        }
        return (
            "You are the bounded BEAST AgentRun planner. Choose exactly one next action. "
            "Return one JSON object only. Never invent tools, never request promotion, and never claim a tool result you have not observed.\n\n"
            f"OBJECTIVE:\n{run.get('objective') or ''}\n\n"
            f"TURN: {state.turn + 1}/{state.max_turns}\n\n"
            f"TOOLS:\n{json.dumps(compact_tools, sort_keys=True, default=str)}\n\n"
            f"OBSERVATIONS:\n{json.dumps(observations, sort_keys=True, default=str)}\n\n"
            f"DECISION CONTRACT:\n{json.dumps(contract, sort_keys=True)}"
        )

    async def run(self, run_id: str) -> dict[str, Any]:
        run = self.engine.store.get_run(run_id)
        if not run:
            raise KeyError(f"unknown agent run: {run_id}")
        current = normalize_state(str(run.get("state") or "created"))
        if current in TERMINAL_STATES:
            return run
        self.engine.attach_current_task(run_id)
        state = self._load_state(run_id)
        state.max_turns = self.max_turns
        state.status = "running"
        self._save_state(state)
        self.engine.emit(run_id, "agent.planner.started", {
            "turn": state.turn,
            "max_turns": state.max_turns,
            "observation_count": len(state.observations),
        })

        while state.turn < state.max_turns:
            self.engine.raise_if_cancelled(run_id)
            self.engine.store.transition(run_id, AgentRunState.PLANNING)
            run = self.engine.store.get_run(run_id) or run
            prompt = self._prompt(run, state)
            self.engine.emit(run_id, "agent.planner.turn.started", {
                "turn": state.turn + 1,
                "max_turns": state.max_turns,
                "observation_count": len(state.observations),
            })
            decision = await self.provider.next_decision(prompt, run=run, turn=state.turn + 1)
            state.turn += 1
            state.last_decision = decision.as_dict()
            self.engine.emit(run_id, "agent.planner.decision", {
                "turn": state.turn,
                "decision": decision.as_dict(),
            })
            self._save_state(state)

            if decision.decision_type is PlannerDecisionType.COMPLETE:
                state.status = "completed"
                state.final_summary = decision.summary
                self.engine.store.transition(run_id, AgentRunState.FINALIZING)
                self.engine.emit(run_id, "agent.planner.completed", {
                    "turns": state.turn,
                    "summary": decision.summary,
                    "observation_count": len(state.observations),
                })
                self._save_state(state)
                self.engine.store.transition(run_id, AgentRunState.COMPLETED)
                return self.engine.store.get_run(run_id) or {}

            if decision.decision_type is PlannerDecisionType.BLOCKED:
                state.status = "blocked"
                state.blocker = decision.blocker
                self.engine.emit(run_id, "agent.planner.blocked", {
                    "turn": state.turn,
                    "blocker": decision.blocker,
                })
                self._save_state(state)
                self.engine.store.transition(run_id, AgentRunState.POLICY_BLOCKED, error=decision.blocker)
                return self.engine.store.get_run(run_id) or {}

            self.engine.store.transition(run_id, AgentRunState.EXECUTING_TOOL)
            try:
                observation = await self.engine.execute_tool(
                    run_id,
                    decision.tool_id,
                    decision.arguments,
                    execution_target=decision.execution_target,
                    approval_id=decision.approval_id,
                )
            except Exception as exc:
                observation = {
                    "observation_id": "",
                    "run_id": run_id,
                    "tool_id": decision.tool_id,
                    "status": "failed",
                    "error": str(exc),
                    "arguments": decision.arguments,
                    "result": {},
                }
            state.observations.append(observation)
            state.observations = state.observations[-self.observation_limit:]
            self.engine.store.transition(run_id, AgentRunState.UPDATING_PLAN)
            self.engine.emit(run_id, "agent.planner.observation.accepted", {
                "turn": state.turn,
                "observation_id": observation.get("observation_id"),
                "tool_id": observation.get("tool_id"),
                "status": observation.get("status"),
                "evidence_digest": observation.get("evidence_digest", ""),
            })
            self._save_state(state)

        state.status = "budget_exhausted"
        state.blocker = f"planner turn budget exhausted at {state.max_turns} turns"
        self.engine.emit(run_id, "agent.planner.budget_exhausted", {
            "turns": state.turn,
            "max_turns": state.max_turns,
        })
        self._save_state(state)
        self.engine.store.transition(run_id, AgentRunState.BUDGET_EXHAUSTED, error=state.blocker)
        return self.engine.store.get_run(run_id) or {}

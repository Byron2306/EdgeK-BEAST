"""Effect-driven agent runtime for durable BEAST runs (Phase 3).

This is the single owner of the live agent lifecycle:

* **commands are effects** - ``AgentCommand`` dispatch is the only way to move a
  run (start/continue/pause/resume/cancel/approve/deny/checkpoint/restore).
* **context is a service** - ``AgentContext`` is projected from the durable run
  record, never a second source of truth.
* **events are streams** - every event is appended to the ``AgentRunStore`` and
  simultaneously pushed into an ``EventStream`` for UI/IDE subscribers.
* **tools run through Effect** - decisions execute through
  ``EffectToolExecutor`` (retry/timeout/cancellation/resource brackets supplied
  by the Effect TS runtime) when one is configured.

``AgentRunState`` remains the durable projection; transitions are applied here
through ``run_state.can_transition`` instead of ad-hoc writes.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List, Optional

from app.kernel.agents.agent_effect import (
    AgentCommand,
    AgentCommandType,
    AgentContext,
    AgentEvent,
    EventStream,
    EventType,
)
from app.kernel.agents.effect_ts_bridge import EffectError
from app.kernel.agents.planner_models import PlannerDecision, PlannerDecisionType
from app.kernel.agents.run_engine import AgentRunEngine
from app.kernel.agents.run_state import (
    TERMINAL_STATES,
    AgentRunState,
    can_transition,
    normalize_state,
)

DecisionProvider = Callable[[AgentContext], Awaitable[PlannerDecision]]


class EffectAgentError(RuntimeError):
    pass


class InvalidTransition(EffectAgentError):
    pass


@dataclass
class TurnPolicy:
    """Effect policies applied to every tool decision."""

    retry_attempts: int = 0
    retry_base_ms: int = 20
    timeout_ms: Optional[int] = None

    def as_kwargs(self) -> Dict[str, Any]:
        return {
            "retry_attempts": self.retry_attempts,
            "retry_base_ms": self.retry_base_ms,
            "timeout_ms": self.timeout_ms,
        }


_EVENT_TYPE_MAP = {
    "agent.run.started": EventType.AGENT_STARTED,
    "agent.run.completed": EventType.AGENT_COMPLETED,
    "agent.run.failed": EventType.AGENT_FAILED,
    "agent.run.cancelled": EventType.AGENT_CANCELLED,
    "agent.planner.turn.started": EventType.TURN_STARTED,
    "agent.planner.turn.completed": EventType.TURN_COMPLETED,
    "agent.planner.completed": EventType.AGENT_COMPLETED,
    "agent.planner.decision": EventType.DECISION_MADE,
    "agent.tool.started": EventType.TOOL_EXECUTING,
    "agent.tool.completed": EventType.TOOL_COMPLETED,
    "agent.tool.failed": EventType.TOOL_FAILED,
    "agent.approval.requested": EventType.APPROVAL_REQUESTED,
}


class EffectAgentRuntime:
    """Drive one durable run with Effect-style commands, context and events."""

    def __init__(
        self,
        engine: AgentRunEngine,
        run_id: str,
        *,
        decide: Optional[DecisionProvider] = None,
        tool_executor: Any = None,
        max_turns: int = 8,
        policy: Optional[TurnPolicy] = None,
    ) -> None:
        run = engine.store.get_run(run_id)
        if not run:
            raise KeyError(f"unknown agent run: {run_id}")
        self.engine = engine
        self.run_id = run_id
        self.decide = decide
        self.tool_executor = tool_executor
        self.max_turns = max_turns
        self.policy = policy or TurnPolicy()

        self.event_stream = EventStream(run_id, str(run.get("session_id") or ""))
        self.context = self._project_context(run)
        self._cancelled = False
        self._paused = False
        self.turn_started_at = 0.0

    # -- context as a service ---------------------------------------------

    def _project_context(self, run: Dict[str, Any]) -> AgentContext:
        checkpoint = run.get("checkpoint") if isinstance(run.get("checkpoint"), dict) else {}
        budget = run.get("budget") if isinstance(run.get("budget"), dict) else {}
        return AgentContext(
            run_id=str(run.get("run_id") or ""),
            session_id=str(run.get("session_id") or ""),
            workspace_root=str(self.engine.workspace_root),
            objective=str(run.get("objective") or ""),
            mode=str(run.get("mode") or "agent"),
            provider=str(run.get("provider") or ""),
            model=str(run.get("model") or ""),
            budget=dict(budget),
            max_turns=self.max_turns,
            metadata={"checkpoint_keys": sorted(checkpoint.keys())},
        )

    def sync_context(self) -> AgentContext:
        """Refresh the projected context from the durable run record."""
        run = self.engine.store.get_run(self.run_id) or {}
        fresh = self._project_context(run)
        self.context.turn = int((run.get("checkpoint") or {}).get("effect_agent_turn") or self.context.turn)
        self.context.state = str(run.get("state") or self.context.state)
        self.context.error = str(run.get("error") or "") or None
        self.context.objective = fresh.objective
        self.context.budget = fresh.budget
        self.context.session_id = fresh.session_id
        self.context.updated_at = time.time()
        return self.context

    # -- events as a stream ------------------------------------------------

    async def emit(self, event_type: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Persist a canonical event and publish it on the Effect stream."""
        body = dict(payload or {})
        body.setdefault("run_id", self.run_id)
        stored = self.engine.emit(self.run_id, event_type, body)
        await self._publish(event_type, {**body, "sequence": stored.get("sequence")})
        return stored

    async def _publish(self, event_type: str, payload: Optional[Dict[str, Any]] = None) -> None:
        """Publish to the Effect stream without writing a second durable event."""
        body = dict(payload or {})
        body.setdefault("run_id", self.run_id)
        await self.event_stream.emit(
            AgentEvent(
                event_type=_EVENT_TYPE_MAP.get(event_type, EventType.STATE_CHANGED),
                run_id=self.run_id,
                session_id=self.context.session_id,
                payload={"event_type": event_type, **body},
                correlation_id=str(body.get("correlation_id") or "") or None,
            )
        )

    def _advance(self, state: AgentRunState, *, error: str = "") -> None:
        current = normalize_state(str((self.engine.store.get_run(self.run_id) or {}).get("state") or "created"))
        if current == state:
            return
        if not can_transition(current, state):
            raise InvalidTransition(f"invalid agent run transition: {current.value} -> {state.value}")
        self.engine.store.transition(self.run_id, state, error=error)
        self.context.state = state.value
        self.context.updated_at = time.time()

    # -- lifecycle --------------------------------------------------------

    def advance(self, state: AgentRunState, *, error: str = "") -> None:
        """Public lifecycle transition used by decision-loop hosts."""
        self._advance(state, error=error)

    # -- commands as effects ----------------------------------------------

    async def execute_command(self, command: AgentCommand) -> Dict[str, Any]:
        handlers: Dict[AgentCommandType, Callable[[AgentCommand], Awaitable[Dict[str, Any]]]] = {
            AgentCommandType.START: self._handle_start,
            AgentCommandType.CONTINUE: self._handle_continue,
            AgentCommandType.PAUSE: self._handle_pause,
            AgentCommandType.RESUME: self._handle_resume,
            AgentCommandType.CANCEL: self._handle_cancel,
            AgentCommandType.APPROVE: self._handle_approve,
            AgentCommandType.DENY: self._handle_deny,
            AgentCommandType.CHECKPOINT: self._handle_checkpoint,
            AgentCommandType.RESTORE: self._handle_restore,
        }
        handler = handlers.get(command.command_type)
        if handler is None:
            raise EffectAgentError(f"unsupported command: {command.command_type}")
        if command.run_id and command.run_id != self.run_id:
            raise EffectAgentError(f"command for {command.run_id} dispatched to {self.run_id}")
        return await handler(command)

    def command(self, command_type: AgentCommandType, **payload: Any) -> AgentCommand:
        return AgentCommand(
            command_type=command_type,
            run_id=self.run_id,
            session_id=self.context.session_id,
            payload=payload,
        )

    async def _handle_start(self, command: AgentCommand) -> Dict[str, Any]:
        self._cancelled = False
        self._paused = False
        self._advance(AgentRunState.SCOPING)
        await self.emit("agent.run.started", {"mode": self.context.mode, "objective": self.context.objective})
        self._advance(AgentRunState.OBSERVING)
        return await self.run()

    async def _handle_continue(self, command: AgentCommand) -> Dict[str, Any]:
        return await self.run()

    async def _handle_pause(self, command: AgentCommand) -> Dict[str, Any]:
        self._paused = True
        self._advance(AgentRunState.PAUSED)
        await self.emit("agent.run.paused", {"reason": str(command.payload.get("reason") or "operator_paused")})
        return {"status": "paused", "run_id": self.run_id}

    async def _handle_resume(self, command: AgentCommand) -> Dict[str, Any]:
        self.engine.resume(self.run_id)
        self._cancelled = False
        self._paused = False
        await self._publish("agent.run.resumed", {"from_state": AgentRunState.PAUSED.value})
        return {"status": "resumed", "run_id": self.run_id}

    async def _handle_cancel(self, command: AgentCommand) -> Dict[str, Any]:
        """Request cancellation; the run loop finalizes once the turn returns.

        This mirrors the durable contract used by the HTTP control plane: the
        run enters ``cancelling`` immediately, then becomes ``cancelled`` when
        the in-flight turn observes the request.
        """
        self._cancelled = True
        reason = str(command.payload.get("reason") or "operator_cancelled")
        result = await self.engine.cancel(self.run_id, reason)
        await self._publish("agent.run.cancellation_requested", {"reason": reason})
        return {
            "status": "cancelling",
            "run_id": self.run_id,
            "execution": result.get("execution") or {},
        }

    async def _handle_approve(self, command: AgentCommand) -> Dict[str, Any]:
        approval_id = str(command.payload.get("approval_id") or "")
        return await self._resolve_approval(approval_id, approved=True)

    async def _handle_deny(self, command: AgentCommand) -> Dict[str, Any]:
        approval_id = str(command.payload.get("approval_id") or "")
        return await self._resolve_approval(approval_id, approved=False)

    async def _resolve_approval(self, approval_id: str, *, approved: bool) -> Dict[str, Any]:
        if not approval_id:
            raise EffectAgentError("approval_id is required")
        if self.engine.store.get_approval(self.run_id, approval_id) is None:
            raise EffectAgentError(f"unknown approval: {approval_id}")
        resolved = self.engine.store.resolve_approval(
            self.run_id,
            approval_id,
            {
                "approved": approved,
                "status": "approved" if approved else "denied",
                "resolved_by": "effect_agent_runtime",
                "resolved_at": time.time(),
            },
        )
        await self.emit(
            "agent.approval.granted" if approved else "agent.approval.denied",
            {"approval_id": approval_id, "status": resolved.get("status")},
        )
        return {"approval_id": approval_id, "status": resolved.get("status"), "approval": resolved}

    async def _handle_checkpoint(self, command: AgentCommand) -> Dict[str, Any]:
        snapshot = {
            "effect_agent_turn": self.context.turn,
            "state": self.context.state,
            "objective": self.context.objective,
            "observations": [obs.as_dict() if hasattr(obs, "as_dict") else obs for obs in self.context.observations],
        }
        self.engine.merge_checkpoint(self.run_id, {"effect_agent": snapshot})
        await self.emit("agent.checkpoint.saved", snapshot)
        return {"status": "checkpointed", "checkpoint": snapshot}

    async def _handle_restore(self, command: AgentCommand) -> Dict[str, Any]:
        run = self.engine.store.get_run(self.run_id) or {}
        checkpoint = run.get("checkpoint") if isinstance(run.get("checkpoint"), dict) else {}
        snapshot = checkpoint.get("effect_agent") if isinstance(checkpoint.get("effect_agent"), dict) else {}
        if not snapshot:
            raise EffectAgentError("no effect_agent checkpoint to restore")
        self.context.turn = int(snapshot.get("effect_agent_turn") or 0)
        await self.emit("agent.checkpoint.restored", {"turn": self.context.turn})
        return {"status": "restored", "checkpoint": snapshot}

    # -- agent loop (Effect program) --------------------------------------

    async def run(self) -> Dict[str, Any]:
        self._advance(AgentRunState.PLANNING)
        while not self._cancelled and not self._paused:
            self.sync_context()
            if self.context.turn >= self.max_turns:
                await self.emit("agent.planner.budget_exhausted", {"turns": self.context.turn})
                self._advance(AgentRunState.BUDGET_EXHAUSTED)
                return {"status": "budget_exhausted", "run_id": self.run_id}
            if self.engine.cancellation_requested(self.run_id):
                await self._finalize_cancellation("cancellation_requested")
                return {"status": "cancelled", "run_id": self.run_id}

            outcome = await self.run_turn()
            if self._cancelled or outcome.get("cancelled") or self.engine.cancellation_requested(self.run_id):
                await self._finalize_cancellation("cancellation_requested")
                return {"status": "cancelled", "run_id": self.run_id}
            if self._paused:
                return {"status": "paused", "run_id": self.run_id}
            if outcome.get("complete"):
                self._advance(AgentRunState.COMPLETED)
                return {"status": "completed", **outcome}
            if outcome.get("blocked"):
                self._advance(AgentRunState.PAUSED)
                return {"status": "blocked", **outcome}
            self.context.turn += 1
            self.engine.merge_checkpoint(self.run_id, {"effect_agent_turn": self.context.turn})

        return {"status": "cancelled", "run_id": self.run_id}

    async def _finalize_cancellation(self, reason: str) -> None:
        """Move a cancelling run to cancelled exactly once, then publish it."""
        run = self.engine.store.get_run(self.run_id) or {}
        current = normalize_state(str(run.get("state") or "created"))
        if current in TERMINAL_STATES:
            return
        self.engine.finalize_cancel(self.run_id, reason)
        await self._publish("agent.run.cancelled", {"reason": reason})

    async def run_turn(self) -> Dict[str, Any]:
        self.turn_started_at = time.time()
        turn = self.context.turn + 1
        await self.emit("agent.planner.turn.started", {"turn": turn})

        decision = await self._decide()
        if self._cancelled:
            return {"cancelled": True}
        await self.emit("agent.planner.decision", {"turn": turn, "decision": decision.as_dict()})

        if decision.decision_type == PlannerDecisionType.COMPLETE:
            if self._cancelled:
                return {"cancelled": True}
            await self.emit("agent.planner.completed", {"turn": turn, "summary": decision.summary})
            await self.emit("agent.run.completed", {"summary": decision.summary})
            return {"complete": True, "summary": decision.summary}

        if decision.decision_type == PlannerDecisionType.BLOCKED:
            await self.emit("agent.planner.blocked", {"turn": turn, "blocker": decision.blocker})
            return {"blocked": True, "blocker": decision.blocker}

        await self.emit(
            "agent.tool.started",
            {"turn": turn, "tool_id": decision.tool_id, "arguments": decision.arguments},
        )
        try:
            observation = await self._execute_tool(decision)
        except Exception as exc:  # noqa: BLE001 - failures become observations
            await self.emit(
                "agent.tool.failed",
                {
                    "turn": turn,
                    "tool_id": decision.tool_id,
                    "error": str(exc),
                    "error_tag": getattr(exc, "tag", type(exc).__name__),
                },
            )
            if self._cancelled:
                return {"cancelled": True}
            self.context.error = str(exc)
            self._advance(AgentRunState.DIAGNOSING)
            return {"failed": True, "tool_id": decision.tool_id, "error": str(exc), "exception": exc}

        if self._cancelled:
            return {"cancelled": True}
        self.context.observations.append(observation)
        await self.emit(
            "agent.tool.completed",
            {"turn": turn, "tool_id": decision.tool_id, "observation": observation},
        )
        self._advance(AgentRunState.UPDATING_PLAN)
        return {"turn": turn, "observation": observation}

    async def _decide(self) -> PlannerDecision:
        if self.decide is None:
            return PlannerDecision(
                decision_type=PlannerDecisionType.COMPLETE,
                summary="no planner configured",
            )
        return await self.decide(self.sync_context())

    async def _execute_tool(self, decision: PlannerDecision) -> Dict[str, Any]:
        if self.tool_executor is not None:
            result = self.tool_executor.execute(
                decision.tool_id,
                decision.arguments,
                **self.policy.as_kwargs(),
            )
            return {
                "tool_id": decision.tool_id,
                "status": "completed",
                "result": result.value,
                "duration_ms": result.elapsed_ms,
                "runtime": "effect_ts",
            }
        observation = await self.engine.execute_tool(
            self.run_id,
            decision.tool_id,
            decision.arguments,
            execution_target=decision.execution_target,
            approval_id=decision.approval_id,
        )
        return dict(observation)


def create_effect_agent_runtime(
    engine: AgentRunEngine,
    run_id: str,
    **kwargs: Any,
) -> EffectAgentRuntime:
    return EffectAgentRuntime(engine, run_id, **kwargs)

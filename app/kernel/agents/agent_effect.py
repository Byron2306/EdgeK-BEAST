"""
Effect-based Agent Runtime for BEAST.
Port of OpenCode's agent architecture:
- Commands as first-class Effects
- Context as Effect service
- Events as Effect streams
- Agent loop as Effect program
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, AsyncGenerator, Awaitable, Callable, Dict, List, Optional, Union
from functools import wraps

from app.kernel.agents.effect_runtime import (
    EffectError,
    TransientError,
    PermanentError,
    CancellationError,
    TimeoutError,
    ResourceError,
    RetryPolicy,
    DEFAULT_RETRY_POLICY,
    with_retry,
    with_timeout,
    span,
    SpanContext,
    get_span_context,
    CancellationToken,
    EffectMetrics,
    get_metrics,
    record_metrics,
)
from app.kernel.agents.zod_schemas import (
    ExecutionTarget,
    DecisionType,
    AgentDecision,
    AgentObservation,
)
from app.kernel.agents.tool_registry import (
    ToolRegistry,
    ToolContext,
    ToolExecutionError,
    ToolNotFoundError,
    ToolValidationError,
    ToolApprovalError,
    create_tool_registry,
)
from app.kernel.agents.planner_models import (
    PlannerDecision,
    PlannerDecisionType,
    PlannerState,
)
from app.kernel.agents.run_state import (
    AgentRunState as PlannerAgentRunState,
)


# =============================================================================
# Agent Events (OpenCode-style event streaming)
# =============================================================================

class EventType(str, Enum):
    """Agent event types for streaming to UI/integrations."""
    AGENT_STARTED = "agent.started"
    AGENT_COMPLETED = "agent.completed"
    AGENT_FAILED = "agent.failed"
    AGENT_CANCELLED = "agent.cancelled"
    TURN_STARTED = "turn.started"
    TURN_COMPLETED = "turn.completed"
    DECISION_MADE = "decision.made"
    TOOL_EXECUTING = "tool.executing"
    TOOL_COMPLETED = "tool.completed"
    TOOL_FAILED = "tool.failed"
    APPROVAL_REQUESTED = "approval.requested"
    APPROVAL_GRANTED = "approval.granted"
    APPROVAL_DENIED = "approval.denied"
    STATE_CHANGED = "state.changed"
    CHECKPOINT_SAVED = "checkpoint.saved"
    ERROR = "error"


@dataclass
class AgentEvent:
    """Streaming event for agent lifecycle."""
    event_type: EventType
    run_id: str
    session_id: str
    timestamp: float = field(default_factory=time.time)
    payload: Dict[str, Any] = field(default_factory=dict)
    correlation_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_type": self.event_type.value,
            "run_id": self.run_id,
            "session_id": self.session_id,
            "timestamp": self.timestamp,
            "payload": self.payload,
            "correlation_id": self.correlation_id,
        }


class EventStream:
    """Effect stream for agent events (OpenCode EventSource pattern)."""
    def __init__(self, run_id: str, session_id: str):
        self.run_id = run_id
        self.session_id = session_id
        self._queue: asyncio.Queue[AgentEvent] = asyncio.Queue()
        self._subscribers: List[asyncio.Queue[AgentEvent]] = []
        self._closed = False

    async def emit(self, event: AgentEvent) -> None:
        if self._closed:
            return
        await self._queue.put(event)
        # Broadcast to subscribers
        for sub in self._subscribers:
            try:
                sub.put_nowait(event)
            except asyncio.QueueFull:
                pass  # Drop if subscriber can't keep up

    @asynccontextmanager
    async def subscribe(self) -> AsyncGenerator[AsyncGenerator[AgentEvent, None], None]:
        """Subscribe to event stream."""
        queue: asyncio.Queue[AgentEvent] = asyncio.Queue(maxsize=1000)
        self._subscribers.append(queue)
        try:
            async def generator():
                while not self._closed:
                    try:
                        event = await asyncio.wait_for(queue.get(), timeout=1.0)
                        yield event
                    except asyncio.TimeoutError:
                        continue
                    except asyncio.CancelledError:
                        break
            yield generator()
        finally:
            if queue in self._subscribers:
                self._subscribers.remove(queue)

    async def close(self) -> None:
        self._closed = True
        # Drain queue
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except asyncio.QueueEmpty:
                break


# =============================================================================
# Agent Context (OpenCode Context as Effect Service)
# =============================================================================

@dataclass
class AgentContext:
    """Agent context - all state needed for agent operation."""
    run_id: str
    session_id: str
    workspace_root: str
    objective: str
    mode: str
    provider: str
    model: str
    execution_target: ExecutionTarget = ExecutionTarget.LOCAL
    execution_target_payload: Optional[Dict[str, Any]] = None
    budget: Dict[str, Any] = field(default_factory=dict)
    max_turns: int = 8
    cancellation_token: CancellationToken = field(default_factory=CancellationToken)
    event_stream: Optional[EventStream] = None
    tool_registry: Optional[ToolRegistry] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    # Runtime state
    turn: int = 0
    observations: List[AgentObservation] = field(default_factory=list)
    state: str = "created"
    error: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "session_id": self.session_id,
            "workspace_root": self.workspace_root,
            "objective": self.objective,
            "mode": self.mode,
            "provider": self.provider,
            "model": self.model,
            "execution_target": self.execution_target.value,
            "budget": self.budget,
            "max_turns": self.max_turns,
            "turn": self.turn,
            "state": self.state,
            "error": self.error,
            "observations": [obs.as_dict() if hasattr(obs, 'as_dict') else obs for obs in self.observations],
        }


# =============================================================================
# Agent Commands (OpenCode Command Pattern)
# =============================================================================

class AgentCommandType(str, Enum):
    """Types of agent commands."""
    START = "start"
    CONTINUE = "continue"
    PAUSE = "pause"
    RESUME = "resume"
    CANCEL = "cancel"
    APPROVE = "approve"
    DENY = "deny"
    CHECKPOINT = "checkpoint"
    RESTORE = "restore"


@dataclass
class AgentCommand:
    """Command to agent (first-class Effect)."""
    command_type: AgentCommandType
    run_id: str
    session_id: str
    payload: Dict[str, Any] = field(default_factory=dict)
    correlation_id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])


class CommandHandler:
    """Handles agent commands as Effects."""
    def __init__(self, agent: "EffectAgent"):
        self.agent = agent

    async def handle(self, command: AgentCommand) -> Dict[str, Any]:
        """Execute command as Effect."""
        async with span(f"command.{command.command_type.value}", {
            "command_type": command.command_type.value,
            "run_id": command.run_id,
            "correlation_id": command.correlation_id,
        }):
            handler_map = {
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

            handler = handler_map.get(command.command_type)
            if not handler:
                raise EffectError(f"Unknown command: {command.command_type}")

            return await handler(command)

    async def _handle_start(self, command: AgentCommand) -> Dict[str, Any]:
        return await self.agent.start()

    async def _handle_continue(self, command: AgentCommand) -> Dict[str, Any]:
        return await self.agent.continue_run()

    async def _handle_pause(self, command: AgentCommand) -> Dict[str, Any]:
        self.agent.context.cancellation_token.cancel()
        return {"status": "paused"}

    async def _handle_resume(self, command: AgentCommand) -> Dict[str, Any]:
        self.agent.context.cancellation_token = CancellationToken()
        return {"status": "resumed"}

    async def _handle_cancel(self, command: AgentCommand) -> Dict[str, Any]:
        self.agent.context.cancellation_token.cancel()
        return await self.agent.cancel()

    async def _handle_approve(self, command: AgentCommand) -> Dict[str, Any]:
        approval_id = command.payload.get("approval_id")
        return {"approved": True, "approval_id": approval_id}

    async def _handle_deny(self, command: AgentCommand) -> Dict[str, Any]:
        approval_id = command.payload.get("approval_id")
        return {"approved": False, "approval_id": approval_id}

    async def _handle_checkpoint(self, command: AgentCommand) -> Dict[str, Any]:
        return await self.agent.checkpoint()

    async def _handle_restore(self, command: AgentCommand) -> Dict[str, Any]:
        checkpoint_id = command.payload.get("checkpoint_id")
        return await self.agent.restore(checkpoint_id)


# =============================================================================
# Effect Agent (OpenCode Agent Loop as Effect Program)
# =============================================================================

class EffectAgent:
    """
    Effect-based Agent Runtime.
    
    OpenCode patterns:
    - Agent loop as Effect program
    - Commands as first-class Effects
    - Context as Effect service
    - Events as Effect streams
    - Tool execution with Effect runtime
    """

    def __init__(
        self,
        context: AgentContext,
        tool_registry: Optional[ToolRegistry] = None,
        planner_provider: Any = None,
        max_turns: int = 8,
        retry_policy: Optional[RetryPolicy] = None,
    ):
        self.context = context
        self.tool_registry = tool_registry or create_tool_registry(context.workspace_root)
        context.tool_registry = self.tool_registry
        # Register MCP tools
        try:
            register_mcp_tools(self.tool_registry, context.workspace_root)
        except Exception as e:
            print(f"Warning: Failed to register MCP tools: {e}")
        self.planner_provider = planner_provider
        self.max_turns = max_turns
        self.retry_policy = retry_policy or DEFAULT_RETRY_POLICY
        self.event_stream = EventStream(context.run_id, context.session_id)
        context.event_stream = self.event_stream

        # Command handler
        self.command_handler = CommandHandler(self)

        # State
        self._running = False
        self._cancelled = False
        self._current_turn_task: Optional[asyncio.Task] = None

        # Metrics
        self.metrics = EffectMetrics()

    @classmethod
    async def create(
        cls,
        session_id: str,
        workspace_root: str,
        objective: str,
        mode: str = "agent",
        provider: str = "ollama",
        model: str = "qwen2.5-coder:7b",
        max_turns: int = 8,
        execution_target: ExecutionTarget = ExecutionTarget.LOCAL,
        execution_target_payload: Optional[Dict[str, Any]] = None,
        budget: Optional[Dict[str, Any]] = None,
        planner_provider: Any = None,
    ) -> "EffectAgent":
        """Factory to create agent with full context."""
        run_id = f"run_{uuid.uuid4().hex[:16]}"

        context = AgentContext(
            run_id=run_id,
            session_id=session_id,
            workspace_root=workspace_root,
            objective=objective,
            mode=mode,
            provider=provider,
            model=model,
            execution_target=execution_target,
            execution_target_payload=execution_target_payload,
            budget=budget or {"tokens": 120000, "seconds": 3600, "cost_usd": 0.0},
            max_turns=max_turns,
        )

        tool_registry = create_tool_registry(workspace_root)

        agent = cls(
            context=context,
            tool_registry=tool_registry,
            planner_provider=planner_provider,
            max_turns=max_turns,
        )

        return agent

    # -------------------------------------------------------------------------
    # Public API (Commands as Effects)
    # -------------------------------------------------------------------------

    async def start(self) -> Dict[str, Any]:
        """Start agent run (Command: START)."""
        if self._running:
            return {"status": "already_running", "run_id": self.context.run_id}

        self._running = True
        self._cancelled = False

        await self._emit(EventType.AGENT_STARTED, {
            "run_id": self.context.run_id,
            "objective": self.context.objective,
            "mode": self.context.mode,
        })

        try:
            result = await self._run_loop()
            return result
        except asyncio.CancelledError:
            await self._emit(EventType.AGENT_CANCELLED, {"reason": "cancelled"})
            raise
        except Exception as e:
            await self._emit(EventType.AGENT_FAILED, {"error": str(e)})
            raise

    async def continue_run(self) -> Dict[str, Any]:
        """Continue paused run (Command: CONTINUE)."""
        if not self._running:
            return await self.start()
        return {"status": "already_running"}

    async def cancel(self) -> Dict[str, Any]:
        """Cancel run (Command: CANCEL)."""
        self._cancelled = True
        self.context.cancellation_token.cancel()
        if self._current_turn_task:
            self._current_turn_task.cancel()
        await self._emit(EventType.AGENT_CANCELLED, {"reason": "user_cancelled"})
        return {"status": "cancelled", "run_id": self.context.run_id}

    async def checkpoint(self) -> Dict[str, Any]:
        """Save checkpoint (Command: CHECKPOINT)."""
        checkpoint = {
            "run_id": self.context.run_id,
            "session_id": self.context.session_id,
            "turn": self.context.turn,
            "observations": self.context.observations,
            "state": self.context.state,
            "budget": self.context.budget,
            "timestamp": time.time(),
        }
        await self._emit(EventType.CHECKPOINT_SAVED, checkpoint)
        return {"checkpoint": checkpoint}

    async def restore(self, checkpoint_id: str) -> Dict[str, Any]:
        """Restore from checkpoint (Command: RESTORE)."""
        # Implementation depends on checkpoint storage
        return {"status": "restored", "checkpoint_id": checkpoint_id}

    async def execute_command(self, command: AgentCommand) -> Dict[str, Any]:
        """Execute command as Effect."""
        return await self.command_handler.handle(command)

    # -------------------------------------------------------------------------
    # Event Streaming
    # -------------------------------------------------------------------------

    async def _emit(self, event_type: EventType, payload: Dict[str, Any]) -> None:
        event = AgentEvent(
            event_type=event_type,
            run_id=self.context.run_id,
            session_id=self.context.session_id,
            payload=payload,
        )
        await self.event_stream.emit(event)
        self.context.updated_at = time.time()

    @asynccontextmanager
    async def subscribe_events(self) -> AsyncGenerator[AsyncGenerator[AgentEvent, None], None]:
        """Subscribe to agent events (for UI/IDE)."""
        async with self.event_stream.subscribe() as gen:
            yield gen

    # -------------------------------------------------------------------------
    # Agent Loop (Effect Program)
    # -------------------------------------------------------------------------

    async def _run_loop(self) -> Dict[str, Any]:
        """Main agent loop as Effect program."""
        self.context.state = "planning"
        self.context.turn = 0

        while self.context.turn < self.max_turns and not self._cancelled:
            # Check cancellation
            self.context.cancellation_token.throw_if_cancelled()

            # Turn start
            turn_num = self.context.turn + 1
            await self._emit(EventType.TURN_STARTED, {"turn": turn_num})

            # Execute turn as Effect
            turn_task = asyncio.create_task(self._execute_turn(turn_num))
            self._current_turn_task = turn_task

            try:
                turn_result = await turn_task
            except asyncio.CancelledError:
                await self._emit(EventType.AGENT_CANCELLED, {"turn": turn_num})
                raise

            # Check turn result
            if turn_result.get("complete"):
                self.context.state = "completed"
                await self._emit(EventType.AGENT_COMPLETED, {
                    "turns": self.context.turn,
                    "summary": turn_result.get("summary"),
                })
                return {"status": "completed", "run_id": self.context.run_id, **turn_result}

            if turn_result.get("blocked"):
                self.context.state = "blocked"
                await self._emit(EventType.STATE_CHANGED, {"state": "blocked", "reason": turn_result.get("blocker")})
                return {"status": "blocked", "run_id": self.context.run_id, **turn_result}

            # Continue to next turn
            self.context.turn += 1

        # Max turns reached
        self.context.state = "max_turns_reached"
        await self._emit(EventType.AGENT_COMPLETED, {"reason": "max_turns_reached"})
        return {"status": "max_turns_reached", "run_id": self.context.run_id}

    async def _execute_turn(self, turn_num: int) -> Dict[str, Any]:
        """Execute single turn as Effect."""
        async with span(f"turn.{turn_num}", {"turn": turn_num}) as s:
            start_time = time.time()

            # Get planner decision
            decision = await self._get_decision()

            if decision.decision_type == PlannerDecisionType.COMPLETE:
                return {"complete": True, "summary": decision.summary}

            if decision.decision_type == PlannerDecisionType.BLOCKED:
                return {"blocked": True, "blocker": decision.blocker}

            # Execute tool decision
            if decision.decision_type == PlannerDecisionType.TOOL:
                return await self._execute_tool_decision(decision)

            return {"blocked": True, "blocker": f"Unknown decision type: {decision.decision_type}"}

    async def _get_decision(self) -> PlannerDecision:
        """Get planner decision (with retry, timeout, metrics)."""
        if self.planner_provider:
            # Use provided planner provider
            return await self._get_provider_decision()

        # Fallback: simple decision logic
        return await self._fallback_decision()

    async def _get_provider_decision(self) -> PlannerDecision:
        """Get decision from planner provider with Effect runtime."""
        async with span("planner.decision", {"turn": self.context.turn + 1}) as s:
            prompt = self._build_prompt()

            try:
                decision = await with_timeout(
                    lambda: with_retry(
                        lambda: self.planner_provider.next_decision(
                            prompt=prompt,
                            run=self._get_run_dict(),
                            turn=self.context.turn + 1,
                        ),
                        policy=self.retry_policy,
                    ),
                    timeout_seconds=60.0,
                )
                s.add_attribute("decision_type", decision.decision_type.value)
                return decision
            except TimeoutError as e:
                s.add_attribute("timeout", True)
                raise

    async def _fallback_decision(self) -> PlannerDecision:
        """Fallback decision when no provider available."""
        # Simple logic: if we have observations, try to complete
        if self.context.observations:
            return PlannerDecision(
                decision_type=PlannerDecisionType.COMPLETE,
                summary="Completed based on observations",
            )
        return PlannerDecision(
            decision_type=PlannerDecisionType.BLOCKED,
            blocker="No planner provider configured",
        )

    def _build_prompt(self) -> str:
        """Build prompt for planner."""
        obs_str = json.dumps([obs.as_dict() if hasattr(obs, 'as_dict') else obs
                              for obs in self.context.observations[-5:]], indent=2)

        return f"""BEAST ACTION PLANNER.
Objective: {self.context.objective}
Mode: {self.context.mode}
Turn: {self.context.turn + 1}/{self.max_turns}

Observations:
{obs_str}

Return ONE JSON decision: tool, complete, or blocked."""

    def _get_run_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.context.run_id,
            "session_id": self.context.session_id,
            "objective": self.context.objective,
            "mode": self.context.mode,
            "provider": self.context.provider,
            "model": self.context.model,
            "request": {
                "context_files": [],
                "max_tokens": 2048,
            },
            "checkpoint": {
                "planner": {
                    "turn": self.context.turn,
                    "observations": [
                        obs.as_dict() if hasattr(obs, 'as_dict') else obs
                        for obs in self.context.observations
                    ],
                }
            },
        }

    async def _execute_tool_decision(self, decision: PlannerDecision) -> Dict[str, Any]:
        """Execute tool decision with Effect runtime."""
        if not decision.tool_id:
            return {"blocked": True, "blocker": "No tool_id in decision"}

        # Create tool context
        tool_context = ToolContext(
            run_id=self.context.run_id,
            session_id=self.context.session_id,
            workspace_root=self.context.workspace_root,
            execution_target=self.context.execution_target.value,
            execution_target_payload=self.context.execution_target_payload,
            approval_id=decision.approval_id,
            cancellation_token=self.context.cancellation_token,
        )

        # Emit tool executing event
        await self._emit(EventType.TOOL_EXECUTING, {
            "tool_id": decision.tool_id,
            "arguments": decision.arguments,
        })

        try:
            # Execute with tool registry (includes retry, timeout, metrics)
            result = await self.tool_registry.execute_decision(decision, tool_context)

            # Create observation
            observation = AgentObservation(
                observation_id=f"obs_{uuid.uuid4().hex[:12]}",
                tool_id=decision.tool_id,
                status="completed",
                duration_ms=0,  # Will be filled by tool registry
                result=result,
                arguments=decision.arguments,
            )
            self.context.observations.append(observation)

            # Emit completion event
            await self._emit(EventType.TOOL_COMPLETED, {
                "tool_id": decision.tool_id,
                "observation_id": observation.observation_id,
            })

            return {"complete": False}

        except ToolApprovalError as e:
            await self._emit(EventType.APPROVAL_REQUESTED, {
                "tool_id": e.context.get("tool_id"),
                "arguments": e.context.get("arguments"),
            })
            return {"blocked": True, "blocker": "approval_required", "approval": e.context}

        except Exception as e:
            await self._emit(EventType.TOOL_FAILED, {
                "tool_id": decision.tool_id,
                "error": str(e),
            })
            return {"blocked": True, "blocker": str(e)}

    # -------------------------------------------------------------------------
    # Checkpoint/Restore
    # -------------------------------------------------------------------------

    def get_state(self) -> Dict[str, Any]:
        return {
            "run_id": self.context.run_id,
            "session_id": self.context.session_id,
            "turn": self.context.turn,
            "state": self.context.state,
            "objective": self.context.objective,
            "mode": self.context.mode,
            "provider": self.context.provider,
            "model": self.context.model,
            "budget": self.context.budget,
            "observations": [obs.as_dict() if hasattr(obs, 'as_dict') else obs
                           for obs in self.context.observations],
            "error": self.context.error,
        }

    def get_metrics(self) -> EffectMetrics:
        return self.metrics


# =============================================================================
# Agent Factory
# =============================================================================

async def create_effect_agent(
    session_id: str,
    workspace_root: str,
    objective: str,
    mode: str = "agent",
    provider: str = "ollama",
    model: str = "qwen2.5-coder:7b",
    max_turns: int = 8,
    execution_target: ExecutionTarget = ExecutionTarget.LOCAL,
    execution_target_payload: Optional[Dict[str, Any]] = None,
    budget: Optional[Dict[str, Any]] = None,
    planner_provider: Any = None,
) -> EffectAgent:
    """Factory function to create and initialize EffectAgent."""
    return await EffectAgent.create(
        session_id=session_id,
        workspace_root=workspace_root,
        objective=objective,
        mode=mode,
        provider=provider,
        model=model,
        max_turns=max_turns,
        execution_target=execution_target,
        execution_target_payload=execution_target_payload,
        budget=budget,
        planner_provider=planner_provider,
    )


# =============================================================================
# Example Usage
# =============================================================================

if __name__ == "__main__":
    async def example():
        # Create agent
        agent = await create_effect_agent(
            session_id="test-session",
            workspace_root="/tmp/test",
            objective="Create a hello world Python file",
            mode="agent",
            provider="ollama",
            model="qwen2.5-coder:7b",
        )

        # Subscribe to events
        async with agent.subscribe_events() as events:
            async for event in events:
                print(f"Event: {event.event_type.value} - {event.payload}")

        # Start agent
        result = await agent.start()
        print(f"Result: {result}")

    asyncio.run(example())
"""Phase 3: commands as effects, context as service, events as streams."""

from __future__ import annotations

import asyncio
import time

import pytest

from app.kernel.agents.agent_effect import AgentCommandType
from app.kernel.agents.effect_agent_runtime import (
    AgentRunState,
    EffectAgentRuntime,
    InvalidTransition,
    TurnPolicy,
)
from app.kernel.agents.effect_tool_executor import EffectToolExecutor
from app.kernel.agents.effect_ts_bridge import EffectTSBridge
from app.kernel.agents.planner_models import PlannerDecision, PlannerDecisionType
from app.kernel.agents.run_engine import AgentRunEngine
from app.kernel.agents.run_state import normalize_state
from app.kernel.agents.tool_models import ToolEffect, ToolRisk, ToolSpec
from app.kernel.agents.tool_registry import ToolRegistry


@pytest.fixture(scope="module")
def bridge():
    b = EffectTSBridge()
    with b:
        yield b
    b.close()


def make_run(engine: AgentRunEngine) -> str:
    return engine.create_run(
        session_id="sess-effect",
        objective="add a health check",
        mode="agent",
        provider="test",
        model="test-model",
    )["run_id"]


def make_spec(tool_id: str, handler=None) -> ToolSpec:
    return ToolSpec(
        tool_id=tool_id,
        version="1.0",
        title=tool_id,
        description="test tool",
        category="test",
        risk=ToolRisk.LOW,
        effect=ToolEffect.READ,
        input_schema={"type": "object", "required": []},
        handler=handler,
    )


def scripted(*decisions):
    calls = {"n": 0}

    async def decide(_context):
        index = min(calls["n"], len(decisions) - 1)
        calls["n"] += 1
        return decisions[index]

    return decide


def tool_decision(tool_id: str, **arguments) -> PlannerDecision:
    return PlannerDecision(decision_type=PlannerDecisionType.TOOL, tool_id=tool_id, arguments=arguments)


def complete_decision(summary: str = "done") -> PlannerDecision:
    return PlannerDecision(decision_type=PlannerDecisionType.COMPLETE, summary=summary)


def event_types(engine: AgentRunEngine, run_id: str) -> list[str]:
    return [str(event.get("event_type")) for event in engine.store.events(run_id)]


async def test_start_command_completes_run(engine_and_runtime):
    engine, runtime = engine_and_runtime
    result = await runtime.execute_command(runtime.command(AgentCommandType.START))

    assert result["status"] == "completed"
    run = engine.store.get_run(runtime.run_id)
    assert run["state"] == AgentRunState.COMPLETED.value
    names = event_types(engine, runtime.run_id)
    assert names[0] == "agent.run.created"  # durable registration from create_run
    assert names[1] == "agent.run.started"  # first command effect
    assert "agent.planner.turn.started" in names
    assert names[-1] == "agent.run.completed"


async def test_tool_decision_executes_through_effect_ts(bridge, engine_and_runtime):
    engine, runtime = engine_and_runtime
    registry = ToolRegistry(workspace_root=str(engine.workspace_root))

    async def handler(args, ctx):
        return {"echo": args.get("path"), "via": "effect"}

    registry.register(make_spec("test.echo", handler))
    runtime.tool_executor = EffectToolExecutor(registry, bridge)
    runtime.decide = scripted(tool_decision("test.echo", path="src/app.py"), complete_decision("echoed"))

    result = await runtime.execute_command(runtime.command(AgentCommandType.START))

    assert result["status"] == "completed"
    assert len(runtime.context.observations) == 1
    observation = runtime.context.observations[0]
    assert observation["runtime"] == "effect_ts"
    assert observation["result"] == {"echo": "src/app.py", "via": "effect"}
    names = event_types(engine, runtime.run_id)
    assert "agent.tool.started" in names and "agent.tool.completed" in names


async def test_retry_policy_applies_to_agent_tools(bridge, engine_and_runtime):
    engine, runtime = engine_and_runtime
    registry = ToolRegistry(workspace_root=str(engine.workspace_root))
    attempts = {"n": 0}

    async def flaky(args, ctx):
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise RuntimeError("transient")
        return {"attempt": attempts["n"]}

    registry.register(make_spec("test.flaky", flaky))
    runtime.tool_executor = EffectToolExecutor(registry, bridge)
    runtime.policy = TurnPolicy(retry_attempts=4, retry_base_ms=10)
    runtime.decide = scripted(tool_decision("test.flaky"), complete_decision())

    result = await runtime.execute_command(runtime.command(AgentCommandType.START))

    assert result["status"] == "completed"
    assert attempts["n"] == 3
    assert "agent.tool.failed" not in event_types(engine, runtime.run_id)


async def test_timeout_policy_marks_tool_failure(bridge, engine_and_runtime):
    engine, runtime = engine_and_runtime
    registry = ToolRegistry(workspace_root=str(engine.workspace_root))

    async def slow(args, ctx):
        time.sleep(1.0)
        return {"late": True}

    registry.register(make_spec("test.slow", slow))
    runtime.tool_executor = EffectToolExecutor(registry, bridge)
    runtime.policy = TurnPolicy(timeout_ms=120)
    runtime.decide = scripted(tool_decision("test.slow"), complete_decision())

    result = await runtime.execute_command(runtime.command(AgentCommandType.START))

    failures = [event for event in engine.store.events(runtime.run_id) if event["event_type"] == "agent.tool.failed"]
    assert failures, "the timeout must surface as a durable tool failure"
    assert failures[0]["payload"]["error_tag"] == "TimeoutError"
    # The failure is a diagnosis input, not a stop: the next turn still runs,
    # and the scripted planner then completes the run.
    assert result["status"] == "completed"
    assert engine.store.get_run(runtime.run_id)["state"] == AgentRunState.COMPLETED.value
    assert runtime.context.observations == []


async def test_cancel_command_stops_the_run(engine_and_runtime):
    engine, runtime = engine_and_runtime
    started = asyncio.Event()
    release = asyncio.Event()

    async def decide(_context):
        started.set()
        await release.wait()
        return complete_decision("late")

    runtime.decide = decide

    task = asyncio.create_task(runtime.execute_command(runtime.command(AgentCommandType.START)))
    await asyncio.wait_for(started.wait(), timeout=5)

    cancel_result = await runtime.execute_command(
        runtime.command(AgentCommandType.CANCEL, reason="operator_stop")
    )
    release.set()
    result = await asyncio.wait_for(task, timeout=5)

    assert cancel_result["status"] == "cancelling"
    assert result["status"] == "cancelled"
    assert engine.store.get_run(runtime.run_id)["state"] == AgentRunState.CANCELLED.value
    names = event_types(engine, runtime.run_id)
    assert "agent.run.completed" not in names
    assert names.count("agent.run.cancelled") == 1


async def test_pause_and_resume_move_the_run(engine_and_runtime):
    engine, runtime = engine_and_runtime

    paused = await runtime.execute_command(runtime.command(AgentCommandType.PAUSE))
    assert paused["status"] == "paused"
    assert engine.store.get_run(runtime.run_id)["state"] == AgentRunState.PAUSED.value

    resumed = await runtime.execute_command(runtime.command(AgentCommandType.RESUME))
    assert resumed["status"] == "resumed"
    assert engine.store.get_run(runtime.run_id)["state"] == AgentRunState.SCOPING.value


async def test_checkpoint_and_restore_keep_other_checkpoint_keys(engine_and_runtime):
    engine, runtime = engine_and_runtime
    engine.merge_checkpoint(runtime.run_id, {"planner": {"observations": [1, 2]}})
    runtime.context.turn = 2

    await runtime.execute_command(runtime.command(AgentCommandType.CHECKPOINT))
    run = engine.store.get_run(runtime.run_id)
    assert run["checkpoint"]["effect_agent"]["effect_agent_turn"] == 2
    assert run["checkpoint"]["planner"]["observations"] == [1, 2]

    runtime.context.turn = 0
    restored = await runtime.execute_command(runtime.command(AgentCommandType.RESTORE))
    assert restored["status"] == "restored"
    assert runtime.context.turn == 2


async def test_approval_commands_resolve_durable_approvals(engine_and_runtime):
    engine, runtime = engine_and_runtime
    approval = engine.store.create_approval(
        runtime.run_id, {"approval_id": "appr-1", "tool_id": "test.echo", "reason": "write"}
    )
    assert approval["status"] == "pending"

    granted = await runtime.execute_command(
        runtime.command(AgentCommandType.APPROVE, approval_id="appr-1")
    )
    assert granted["approval"]["status"] == "approved"

    denied = await runtime.execute_command(runtime.command(AgentCommandType.DENY, approval_id="appr-1"))
    assert denied["approval"]["status"] == "rejected"


async def test_context_is_projected_from_the_durable_run(engine_and_runtime):
    engine, runtime = engine_and_runtime
    run = engine.store.get_run(runtime.run_id)

    assert runtime.context.run_id == run["run_id"]
    assert runtime.context.session_id == run["session_id"]
    assert runtime.context.objective == run["objective"]
    assert runtime.context.workspace_root == str(engine.workspace_root)

    engine.store.transition(runtime.run_id, AgentRunState.PLANNING)
    runtime.sync_context()
    assert runtime.context.state == AgentRunState.PLANNING.value


async def test_events_are_published_on_the_effect_stream(engine_and_runtime):
    engine, runtime = engine_and_runtime
    received: list[str] = []

    async with runtime.event_stream.subscribe() as subscription:
        subscriber = asyncio.create_task(_collect(subscription, received, limit=3))
        await runtime.execute_command(runtime.command(AgentCommandType.START))
        await asyncio.wait_for(subscriber, timeout=5)

    assert received[:3] == ["agent.run.started", "agent.planner.turn.started", "agent.planner.decision"]
    # The same events exist in the durable ledger, in order. The ledger starts
    # with the run registration that happened before the stream subscription.
    durable = event_types(engine, runtime.run_id)
    assert durable[0] == "agent.run.created"
    assert durable[1:4] == received[:3]


async def test_engine_builds_the_effect_runtime(tmp_path, bridge):
    engine = AgentRunEngine(tmp_path)
    run_id = make_run(engine)

    runtime = engine.effect_agent(run_id, max_turns=2)

    assert isinstance(runtime, EffectAgentRuntime)
    assert runtime.context.run_id == run_id
    assert runtime.context.session_id == "sess-effect"


async def test_invalid_transition_is_rejected(engine_and_runtime):
    engine, runtime = engine_and_runtime
    engine.store.transition(runtime.run_id, AgentRunState.COMPLETED)
    with pytest.raises(InvalidTransition):
        runtime._advance(AgentRunState.PLANNING)


async def _collect(subscription, sink: list[str], *, limit: int) -> None:
    async for event in subscription:
        sink.append(str(event.payload.get("event_type")))
        if len(sink) >= limit:
            return


@pytest.fixture()
def engine_and_runtime(tmp_path, bridge):
    engine = AgentRunEngine(tmp_path)
    run_id = make_run(engine)
    runtime = EffectAgentRuntime(engine, run_id, decide=scripted(complete_decision()), max_turns=4)
    return engine, runtime

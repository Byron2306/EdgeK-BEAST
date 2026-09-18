"""Opt-in Phase 3 proof that a real local model selects a governed BEAST tool."""

from __future__ import annotations

import asyncio
import os

import pytest

from app.kernel.agents.ollama_planner_provider import OllamaPlannerProvider
from app.kernel.agents.planner_models import PlannerDecisionType
from app.kernel.agents.run_engine import AgentRunEngine


@pytest.mark.skipif(
    os.environ.get("BEAST_PHASE3_LIVE_OLLAMA") != "1",
    reason="live Phase 3 Ollama opt-in",
)
def test_real_ollama_tool_decision_executes_through_phase3_gates(tmp_path):
    (tmp_path / "sample.py").write_text("VALUE = 1\n", encoding="utf-8")
    engine = AgentRunEngine(tmp_path)
    run_id = engine.create_run(
        session_id="phase3-live-ollama-tool",
        objective="List the workspace through the governed BEAST tool plane.",
        mode="agent",
        provider="ollama",
        model=os.environ.get("BEAST_PHASE3_LIVE_OLLAMA_MODEL", "qwen2.5:0.5b"),
        budget={"profile": "compact", "max_tool_calls": 4},
    )["run_id"]
    run = engine.store.get_run(run_id) or {}

    tokens: list[str] = []
    provider = OllamaPlannerProvider(
        model=str(run["model"]),
        timeout_seconds=150,
        max_retries=1,
        on_token=tokens.append,
    )

    async def exchange():
        probe = await provider.probe()
        assert probe["ok"] is True
        return await provider.next_decision(
            'Return exactly one JSON object and nothing else: '
            '{"decision_type":"tool","tool_id":"workspace.list","arguments":{}}',
            run=run,
            turn=1,
        )

    decision = asyncio.run(exchange())
    assert decision.decision_type is PlannerDecisionType.TOOL
    assert decision.tool_id == "workspace.list"
    assert decision.arguments == {}
    assert tokens
    assert provider.last_usage.get("completion_eval_count", 0) > 0
    assert provider.last_route.get("route_kind") == "direct_generate"

    observation = asyncio.run(
        engine.execute_tool(
            run_id,
            decision.tool_id,
            decision.arguments,
            execution_target=decision.execution_target,
        )
    )
    assert observation["status"] == "completed"
    assert observation["tool_id"] == "workspace.list"

    events = engine.store.events(run_id, limit=200)
    authority = [
        event["payload"]["authority_receipt"]
        for event in events
        if event["event_type"] == "agent.tool.authorized"
    ]
    budgets = [
        event["payload"]["budget_receipt"]
        for event in events
        if event["event_type"] == "agent.budget.authorized"
    ]
    assert authority
    assert authority[-1]["authority_class"] == "A_READ_AUTOMATIC"
    assert authority[-1]["allowed"] is True
    assert budgets
    assert budgets[-1]["allowed"] is True
    assert budgets[-1]["action"] == "tool:workspace.list"
    assert engine.store.verify_chain(run_id)["head_matches"] is True

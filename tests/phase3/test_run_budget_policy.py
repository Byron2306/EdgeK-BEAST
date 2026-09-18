from __future__ import annotations

import asyncio

import pytest

from app.kernel.agents.planner_provider import ScriptedPlannerProvider
from app.kernel.agents.planner_runtime import AgentPlannerRuntime
from app.kernel.agents.run_budget import (
    PROFILE_LIMITS,
    RunBudgetExceeded,
    post_model_usage_receipt,
    resolve_budget_policy,
    tool_budget_receipt,
)
from app.kernel.agents.run_engine import AgentRunEngine
from app.kernel.agents.tool_models import ToolEffect, ToolRisk, ToolSpec


async def _noop(_arguments, _context):
    return {"ok": True}


def _mutation_spec() -> ToolSpec:
    return ToolSpec(
        tool_id="worktree.replace_exact",
        version="1",
        title="mutation",
        description="fixture",
        category="worktree",
        risk=ToolRisk.HIGH,
        effect=ToolEffect.ISOLATED_MUTATION,
        input_schema={"type": "object"},
        requires_approval=True,
        requires_worktree=True,
        handler=_noop,
    )


def test_balanced_profile_matches_phase3_master_plan():
    policy = resolve_budget_policy({"budget": {}})
    assert policy["profile"] == "balanced"
    assert policy["limits"] == PROFILE_LIMITS["balanced"]
    assert policy["limits"]["max_model_turns"] == 24
    assert policy["limits"]["max_tool_calls"] == 60
    assert policy["limits"]["max_mutating_tool_calls"] == 20
    assert policy["limits"]["max_verification_cycles"] == 5
    assert policy["limits"]["max_files_changed"] == 20
    assert policy["limits"]["max_lines_changed"] == 2000
    assert policy["limits"]["max_wall_seconds"] == 1800
    assert policy["limits"]["max_input_tokens"] == 180000
    assert policy["limits"]["max_output_tokens"] == 40000
    assert policy["limits"]["max_cloud_cost"] == 5.0
    assert policy["limits"]["max_parallel_subagents"] == 3


def test_explicit_budget_override_is_bounded_and_alias_compatible():
    policy = resolve_budget_policy({
        "budget": {
            "profile": "compact",
            "max_turns": 3,
            "max_tool_calls": 2,
            "max_cloud_cost": 0.25,
        }
    })
    assert policy["profile"] == "compact"
    assert policy["limits"]["max_model_turns"] == 3
    assert policy["limits"]["max_tool_calls"] == 2
    assert policy["limits"]["max_cloud_cost"] == 0.25


def test_tool_runtime_exhausts_before_second_handler_call(tmp_path):
    engine = AgentRunEngine(tmp_path)
    run_id = engine.create_run(
        session_id="phase3-budget-tools",
        objective="Prove tool budget",
        mode="analysis",
        provider="simulated",
        model="budget-test",
        budget={"max_tool_calls": 1},
    )["run_id"]

    first = asyncio.run(engine.execute_tool(run_id, "workspace.list", {}))
    assert first["status"] == "completed"

    with pytest.raises(RunBudgetExceeded, match="tool_calls budget would be exceeded"):
        asyncio.run(engine.execute_tool(run_id, "workspace.list", {}))

    run = engine.store.get_run(run_id)
    assert run["state"] == "budget_exhausted"
    events = engine.store.events(run_id, limit=200)
    exhausted = [event for event in events if event["event_type"] == "agent.budget.exhausted"]
    assert exhausted
    receipt = exhausted[-1]["payload"]["budget_receipt"]
    assert receipt["allowed"] is False
    assert receipt["violations"][0]["metric"] == "tool_calls"


def test_mutation_budget_projects_files_and_lines_before_execution():
    run = {
        "run_id": "run-phase3-budget-mutation",
        "created_at": 1e20,
        "budget": {
            "max_files_changed": 1,
            "max_lines_changed": 2,
        },
    }
    receipt = tool_budget_receipt(
        run,
        [],
        _mutation_spec(),
        {
            "path": "src/example.py",
            "old_text": "A\n",
            "new_text": "A\nB\nC\n",
        },
    )
    assert receipt["allowed"] is False
    metrics = {item["metric"] for item in receipt["violations"]}
    assert "lines_changed" in metrics
    assert receipt["prospective"]["files_changed"] == 1
    assert receipt["prospective"]["lines_changed"] == 3


def test_model_token_budget_is_ledger_derived():
    run = {
        "run_id": "run-phase3-model-budget",
        "created_at": 1e20,
        "budget": {"max_input_tokens": 100, "max_output_tokens": 50},
    }
    events = [
        {
            "event_type": "agent.model.usage",
            "payload": {"input_tokens": 120, "output_tokens": 10, "cloud_cost": 0.0},
        }
    ]
    receipt = post_model_usage_receipt(run, events)
    assert receipt["allowed"] is False
    violation = next(item for item in receipt["violations"] if item["metric"] == "input_tokens")
    assert violation["used"] == 120
    assert violation["limit"] == 100


def test_planner_turn_profile_caps_runtime(tmp_path):
    engine = AgentRunEngine(tmp_path)
    run_id = engine.create_run(
        session_id="phase3-budget-turns",
        objective="Inspect twice then exhaust the policy turn budget",
        mode="analysis",
        provider="simulated",
        model="budget-test",
        budget={"max_model_turns": 2, "max_tool_calls": 10},
    )["run_id"]
    provider = ScriptedPlannerProvider([
        {"decision_type": "tool", "tool_id": "workspace.list", "arguments": {}},
        {"decision_type": "tool", "tool_id": "workspace.list", "arguments": {}},
        {"decision_type": "complete", "summary": "should not reach third model turn"},
    ])
    final = asyncio.run(AgentPlannerRuntime(engine, provider, max_turns=8).run(run_id))
    assert final["state"] == "budget_exhausted"
    planner = final["checkpoint"]["planner"]
    assert planner["max_turns"] == 2
    turn_events = [
        event for event in engine.store.events(run_id, limit=200)
        if event["event_type"] == "agent.planner.turn.started"
    ]
    assert len(turn_events) == 2

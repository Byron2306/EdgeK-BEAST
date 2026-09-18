from __future__ import annotations

import asyncio

import pytest

from app.kernel.agents.least_authority import (
    A_READ_AUTOMATIC,
    B_READ_SENSITIVE,
    C_ISOLATED_MUTATION,
    D_CONSEQUENTIAL_EXECUTION,
    E_NEVER_MODEL_AUTHORIZED,
    authority_class_for,
    authorize_agent_tool,
)
from app.kernel.agents.run_engine import AgentRunEngine
from app.kernel.agents.tool_models import ToolEffect, ToolRisk, ToolSpec


async def _noop(_arguments, _context):
    return {"ok": True}


def _spec(*, effect: ToolEffect, requires_approval: bool = False, requires_worktree: bool = False) -> ToolSpec:
    return ToolSpec(
        tool_id=f"phase3.{effect.value}",
        version="1",
        title="Phase 3 fixture",
        description="Least-authority fixture",
        category="phase3",
        risk=ToolRisk.HIGH if effect is not ToolEffect.READ else ToolRisk.LOW,
        effect=effect,
        input_schema={"type": "object", "properties": {}, "additionalProperties": False},
        requires_approval=requires_approval,
        requires_worktree=requires_worktree,
        handler=_noop,
    )


def test_phase3_authority_classes_are_deterministic():
    assert authority_class_for(_spec(effect=ToolEffect.READ)) == A_READ_AUTOMATIC
    assert authority_class_for(_spec(effect=ToolEffect.READ, requires_approval=True)) == B_READ_SENSITIVE
    assert authority_class_for(_spec(effect=ToolEffect.ISOLATED_MUTATION, requires_approval=True)) == C_ISOLATED_MUTATION
    assert authority_class_for(_spec(effect=ToolEffect.EXECUTION)) == D_CONSEQUENTIAL_EXECUTION
    assert authority_class_for(_spec(effect=ToolEffect.PROMOTION)) == E_NEVER_MODEL_AUTHORIZED


def test_class_e_is_never_model_authorized_even_with_approval_and_worktree():
    receipt = authorize_agent_tool(
        _spec(effect=ToolEffect.PROMOTION, requires_approval=True, requires_worktree=True),
        run_id="run-phase3",
        execution_target="local",
        approval_status="approved",
        approval_id="approval-phase3",
        worktree_bound=True,
    )
    assert receipt["allowed"] is False
    assert receipt["authority_class"] == E_NEVER_MODEL_AUTHORIZED
    assert "never model-authorized" in receipt["reason"]


def test_class_c_requires_request_bound_approval():
    spec = _spec(effect=ToolEffect.ISOLATED_MUTATION, requires_approval=True, requires_worktree=True)
    refused = authorize_agent_tool(
        spec,
        run_id="run-phase3",
        execution_target="local",
        worktree_bound=True,
    )
    allowed = authorize_agent_tool(
        spec,
        run_id="run-phase3",
        execution_target="local",
        approval_status="approved",
        approval_id="approval-phase3",
        worktree_bound=True,
    )
    assert refused["allowed"] is False
    assert "request-bound approval" in refused["reason"]
    assert allowed["allowed"] is True


def test_tool_registry_publishes_phase3_authority_contract(tmp_path):
    engine = AgentRunEngine(tmp_path)
    tools = {row["tool_id"]: row for row in engine.list_tools()}
    assert tools["workspace.list"]["authority_class"] == A_READ_AUTOMATIC
    assert tools["worktree.write_file"]["authority_class"] == C_ISOLATED_MUTATION
    assert tools["worktree.verify"]["authority_class"] == D_CONSEQUENTIAL_EXECUTION
    assert tools["workspace.list"]["redaction_policy"] == "source"
    assert tools["workspace.list"]["evidence_level"] == "summary"


def test_runtime_emits_authority_receipt_before_read_execution(tmp_path):
    (tmp_path / "sample.py").write_text("VALUE = 1\n", encoding="utf-8")
    engine = AgentRunEngine(tmp_path)
    run_id = engine.create_run(
        session_id="phase3-read",
        objective="Inspect the workspace",
        mode="agent",
        provider="simulated",
        model="phase3-test",
    )["run_id"]

    observation = asyncio.run(engine.execute_tool(run_id, "workspace.list", {}))
    assert observation["status"] == "completed"

    events = engine.store.events(run_id, limit=100)
    authorized = [event for event in events if event["event_type"] == "agent.tool.authorized"]
    started = [event for event in events if event["event_type"] == "agent.tool.started"]
    assert authorized
    receipt = authorized[-1]["payload"]["authority_receipt"]
    assert receipt["allowed"] is True
    assert receipt["authority_class"] == A_READ_AUTOMATIC
    assert receipt["receipt_hash"].startswith("sha256:")
    assert started[-1]["payload"]["authority_receipt"]["receipt_id"] == receipt["receipt_id"]


def test_runtime_refuses_isolated_mutation_without_capability_before_handler(tmp_path):
    engine = AgentRunEngine(tmp_path)
    run_id = engine.create_run(
        session_id="phase3-mutation-refusal",
        objective="Attempt an unapproved isolated mutation",
        mode="agent",
        provider="simulated",
        model="phase3-test",
    )["run_id"]

    with pytest.raises(PermissionError, match="request-bound approval"):
        asyncio.run(engine.execute_tool(
            run_id,
            "worktree.write_file",
            {"path": "blocked.py", "content": "VALUE = 2\n"},
        ))

    assert not (tmp_path / "blocked.py").exists()
    events = engine.store.events(run_id, limit=100)
    refused = [event for event in events if event["event_type"] == "agent.tool.refused"]
    assert refused
    receipt = refused[-1]["payload"]["authority_receipt"]
    assert receipt["allowed"] is False
    assert receipt["authority_class"] == C_ISOLATED_MUTATION

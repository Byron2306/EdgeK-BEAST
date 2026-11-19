from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from app.kernel.agents.planner_models import (
    PlannerDecision,
    PlannerDecisionType,
)
from app.kernel.agents.planner_provider import PlannerProvider
from app.kernel.agents.planner_runtime import AgentPlannerRuntime
from app.kernel.agents.run_engine import AgentRunEngine


class ScriptedEditor(PlannerProvider):
    """A deterministic stand-in for a model that reads, binds, edits, verifies, then claims done."""

    def __init__(self) -> None:
        self.calls = 0
        self.last_usage: dict | None = None

    async def next_decision(self, prompt: str, *, run: dict, turn: int) -> PlannerDecision:
        self.calls += 1
        if self.calls == 1:
            return PlannerDecision(
                decision_type=PlannerDecisionType.TOOL,
                tool_id="workspace.read_range",
                arguments={"path": "answer.py", "start_line": 1, "line_count": 40},
                rationale="Inspect the target file before editing.",
            )
        if self.calls == 2:
            return PlannerDecision(
                decision_type=PlannerDecisionType.TOOL,
                tool_id="worktree.bind",
                arguments={"objective": "Edit answer.py"},
                rationale="Create isolated worktree before editing.",
            )
        if self.calls == 3:
            return PlannerDecision(
                decision_type=PlannerDecisionType.TOOL,
                tool_id="worktree.replace_exact",
                arguments={"path": "answer.py", "old_text": "VALUE = 1", "new_text": "VALUE = 2"},
                rationale="Make the requested bounded edit.",
            )
        if self.calls == 4:
            return PlannerDecision(
                decision_type=PlannerDecisionType.TOOL,
                tool_id="worktree.verify",
                arguments={"command": ["python", "-m", "py_compile", "answer.py"]},
                rationale="Verify the edit compiles.",
            )
        if self.calls == 5:
            return PlannerDecision(
                decision_type=PlannerDecisionType.TOOL,
                tool_id="worktree.sourceplan_draft",
                arguments={},
                rationale="Materialize the verified diff as a SourcePlan handoff.",
            )
        return PlannerDecision(
            decision_type=PlannerDecisionType.COMPLETE,
            arguments={},
            summary="Changed VALUE to 2.",
            rationale="The edit is verified and the SourcePlan handoff is ready.",
        )


def _repo(root: Path) -> None:
    (root / "answer.py").write_text("VALUE = 1\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "beast@example.test"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "BEAST Test"], cwd=root, check=True)
    subprocess.run(["git", "add", "answer.py"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-qm", "initial"], cwd=root, check=True)


@pytest.mark.asyncio
async def test_autopilot_runs_edit_verify_and_finish_without_approval_prompts(tmp_path: Path):
    _repo(tmp_path)
    engine = AgentRunEngine(tmp_path)
    run = engine.create_run(
        session_id="autopilot-session",
        objective="Change VALUE to 2 in answer.py",
        mode="agent",
        provider="scripted",
        model="scripted",
        request={
            "autonomy": "autopilot",
            "context_files": ["answer.py"],
            "implementation_target": "answer.py",
            "execution_target": "local",
            "transport": "beast_coder_tli_v1",
        },
    )
    run_id = run["run_id"]
    runtime = AgentPlannerRuntime(engine, ScriptedEditor(), max_turns=12)

    states: list[str] = []
    for _ in range(12):
        result = await runtime.run_one_turn(run_id)
        state = str(result.get("state") or "")
        states.append(state)
        if state in {
            "completed", "failed", "blocked", "budget_exhausted",
            "policy_blocked", "cancelled", "rejected", "rolled_back",
        }:
            break

    assert "waiting_for_approval" not in states, states
    assert states[-1] == "completed", states

    observations = runtime._load_state(run_id).observations
    tool_ids = [str(item.get("tool_id") or "") for item in observations]
    assert "worktree.bind" in tool_ids
    assert "worktree.replace_exact" in tool_ids
    assert "worktree.verify" in tool_ids

    approvals = engine.store.approvals(run_id)
    assert approvals, "autopilot must still leave an auditable approval record"
    assert all(item.get("status") == "approved" for item in approvals)
    assert all(
        (item.get("resolution") or {}).get("operator") == "autopilot"
        for item in approvals
        if isinstance(item.get("resolution"), dict)
    ), approvals

    events = engine.store.events(run_id, after=0, limit=1000)
    granted = [
        event for event in events
        if event.get("event_type") == "agent.approval.autopilot_granted"
    ]
    assert granted, "autopilot grants must be visible in the durable event stream"


@pytest.mark.asyncio
async def test_autopilot_apply_writes_the_verified_diff_into_the_workspace(tmp_path: Path):
    _repo(tmp_path)
    engine = AgentRunEngine(tmp_path)
    run = engine.create_run(
        session_id="autopilot-apply",
        objective="Change VALUE to 2 in answer.py",
        mode="agent",
        provider="scripted",
        model="scripted",
        request={
            "autonomy": "autopilot",
            "apply_on_completion": True,
            "context_files": ["answer.py"],
            "implementation_target": "answer.py",
            "execution_target": "local",
            "transport": "beast_coder_tli_v1",
        },
    )
    run_id = run["run_id"]
    runtime = AgentPlannerRuntime(engine, ScriptedEditor(), max_turns=12)

    states: list[str] = []
    for _ in range(12):
        result = await runtime.run_one_turn(run_id)
        states.append(str(result.get("state") or ""))
        if states[-1] in {
            "completed", "failed", "blocked", "budget_exhausted",
            "policy_blocked", "cancelled", "rejected", "rolled_back",
        }:
            break

    assert states[-1] == "completed", states
    assert (tmp_path / "answer.py").read_text(encoding="utf-8") == "VALUE = 2\n"

    events = engine.store.events(run_id, after=0, limit=1000)
    assert any(event.get("event_type") == "agent.worktree.applied" for event in events)
    completed = [
        event for event in events
        if event.get("event_type") == "agent.planner.completed"
    ]
    assert completed and completed[-1]["payload"]["completion_mode"] == "applied_to_workspace"
    assert completed[-1]["payload"]["promotion_authorized"] is True


class ConflictingEditor(ScriptedEditor):
    """Simulates the operator editing the same file while the agent works."""

    def __init__(self, workspace: Path) -> None:
        super().__init__()
        self.workspace = workspace

    async def next_decision(self, prompt: str, *, run: dict, turn: int) -> PlannerDecision:
        decision = await super().next_decision(prompt, run=run, turn=turn)
        if self.calls == 2:
            # The human saves their own change after bind but before completion.
            (self.workspace / "answer.py").write_text("VALUE = 99\n", encoding="utf-8")
        return decision


@pytest.mark.asyncio
async def test_autopilot_apply_refuses_to_clobber_a_concurrent_operator_edit(tmp_path: Path):
    _repo(tmp_path)
    engine = AgentRunEngine(tmp_path)
    run = engine.create_run(
        session_id="autopilot-conflict",
        objective="Change VALUE to 2 in answer.py",
        mode="agent",
        provider="scripted",
        model="scripted",
        request={
            "autonomy": "autopilot",
            "apply_on_completion": True,
            "context_files": ["answer.py"],
            "implementation_target": "answer.py",
            "execution_target": "local",
            "transport": "beast_coder_tli_v1",
        },
    )
    run_id = run["run_id"]
    runtime = AgentPlannerRuntime(engine, ConflictingEditor(tmp_path), max_turns=12)

    states: list[str] = []
    for _ in range(12):
        result = await runtime.run_one_turn(run_id)
        states.append(str(result.get("state") or ""))
        if states[-1] in {
            "completed", "failed", "blocked", "budget_exhausted",
            "policy_blocked", "cancelled", "rejected", "rolled_back",
        }:
            break

    assert states[-1] == "completed", states
    # The human edit survives; the agent's version stays in the worktree.
    assert (tmp_path / "answer.py").read_text(encoding="utf-8") == "VALUE = 99\n"

    events = engine.store.events(run_id, after=0, limit=1000)
    blocked = [
        event for event in events
        if event.get("event_type") == "agent.worktree.apply_blocked"
    ]
    assert blocked, "the unsafe apply must leave a durable refusal record"
    assert "changed in the operator workspace" in blocked[-1]["payload"]["reason"]
    completed = [
        event for event in events
        if event.get("event_type") == "agent.planner.completed"
    ]
    assert completed and completed[-1]["payload"]["completion_mode"] == "isolated_review"

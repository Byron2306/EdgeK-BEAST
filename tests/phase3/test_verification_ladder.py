from __future__ import annotations

from app.kernel.agents.planner_models import PlannerState
from app.kernel.agents.planner_runtime import AgentPlannerRuntime
from app.kernel.agents.verification_ladder import (
    build_verification_ladder,
    next_verification_stage,
    verification_ladder_receipt,
)


def _mutation(path: str = "app/example.py") -> dict:
    return {
        "tool_id": "worktree.replace_exact",
        "status": "completed",
        "result": {"path": path, "mutation_epoch": 1},
        "arguments": {"path": path, "old_text": "VALUE = 1", "new_text": "VALUE = 2"},
    }


def _verify(command: list[str], epoch: int) -> dict:
    return {
        "tool_id": "worktree.verify",
        "status": "completed",
        "result": {
            "command": list(command),
            "returncode": 0,
            "ok": True,
            "mutation_epoch": epoch,
        },
        "arguments": {"command": list(command)},
    }


def _run(observations: list[dict], *, epoch: int = 1) -> dict:
    return {
        "run_id": "phase3-ladder",
        "objective": "Repair VALUE",
        "mode": "agent",
        "provider": "simulated",
        "request": {
            "verification_ladder": True,
            "context_files": ["app/example.py"],
        },
        "checkpoint": {
            "worktree_mutation_epoch": epoch,
            "planner": {"observations": observations},
        },
    }


def test_ladder_orders_diff_safety_before_python_syntax():
    run = _run([_mutation()])
    ladder = build_verification_ladder(run)
    assert [stage["stage"] for stage in ladder] == ["content_safety", "syntax"]
    assert ladder[0]["command"] == ["git", "diff", "--check"]
    assert ladder[1]["command"] == ["python", "-m", "py_compile", "app/example.py"]


def test_ladder_advances_only_after_current_epoch_receipt():
    mutation = _mutation()
    run = _run([mutation])
    first = next_verification_stage(run)
    assert first["stage"] == "content_safety"

    diff = _verify(["git", "diff", "--check"], 1)
    run = _run([mutation, diff])
    second = next_verification_stage(run)
    assert second["stage"] == "syntax"

    syntax = _verify(["python", "-m", "py_compile", "app/example.py"], 1)
    run = _run([mutation, diff, syntax])
    receipt = verification_ladder_receipt(run)
    assert receipt["complete"] is True
    assert receipt["remaining_stage_ids"] == []


def test_repair_mutation_invalidates_prior_ladder_epoch():
    mutation = _mutation()
    diff = _verify(["git", "diff", "--check"], 1)
    syntax = _verify(["python", "-m", "py_compile", "app/example.py"], 1)

    repaired = {
        "tool_id": "worktree.replace_exact",
        "status": "completed",
        "result": {"path": "app/example.py", "mutation_epoch": 2},
        "arguments": {"path": "app/example.py", "old_text": "VALUE = 2", "new_text": "VALUE = 3"},
    }
    run = _run([mutation, diff, syntax, repaired], epoch=2)
    receipt = verification_ladder_receipt(run)
    assert receipt["complete"] is False
    assert receipt["completed_stage_ids"] == []
    assert next_verification_stage(run)["stage"] == "content_safety"


def test_required_phase_uses_ladder_before_sourceplan():
    observations = [
        {"tool_id": "workspace.index", "status": "completed", "result": {"ok": True}},
        {"tool_id": "worktree.bind", "status": "completed", "result": {"task_id": "wt-1"}},
        {
            "tool_id": "workspace.read_range",
            "status": "completed",
            "result": {"path": "app/example.py", "content": "VALUE = 1\n"},
        },
        _mutation(),
    ]
    state = PlannerState(run_id="phase3-required", observations=list(observations))
    run = _run(observations)

    required = AgentPlannerRuntime._required_phase_decision(run, state)
    assert required is not None
    assert required.tool_id == "worktree.verify"
    assert required.arguments["command"] == ["git", "diff", "--check"]

    diff = _verify(["git", "diff", "--check"], 1)
    state.observations.append(diff)
    run = _run(state.observations)
    required = AgentPlannerRuntime._required_phase_decision(run, state)
    assert required is not None
    assert required.tool_id == "worktree.verify"
    assert required.arguments["command"] == ["python", "-m", "py_compile", "app/example.py"]

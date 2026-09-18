from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path

from app.kernel.agents.planner_provider import ScriptedPlannerProvider
from app.kernel.agents.planner_runtime import AgentPlannerRuntime
from app.kernel.agents.run_engine import AgentRunEngine


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True)


def _repo(tmp_path: Path) -> Path:
    root = tmp_path / "phase3-repo"
    root.mkdir()
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "beast@example.test")
    _git(root, "config", "user.name", "BEAST Phase3")
    (root / "values.py").write_text("VALUE = 1\n", encoding="utf-8")
    (root / "consumer.py").write_text(
        "from values import VALUE\nRESULT = VALUE + 0\n",
        encoding="utf-8",
    )
    tests = root / "tests"
    tests.mkdir()
    (tests / "test_behavior.py").write_text(
        "from values import VALUE\n"
        "from consumer import RESULT\n\n"
        "def test_behavior():\n"
        "    assert VALUE == 2\n"
        "    assert RESULT == 3\n",
        encoding="utf-8",
    )
    _git(root, "add", ".")
    _git(root, "commit", "-qm", "seed phase3 defect")
    return root


def test_phase3_seeded_multifile_defect_repairs_then_hands_off_sourceplan(tmp_path):
    root = _repo(tmp_path)
    engine = AgentRunEngine(root)
    run_id = engine.create_run(
        session_id="phase3-seeded-defect",
        objective="Repair the VALUE flow so VALUE is 2 and RESULT is 3, with fresh verification before SourcePlan.",
        mode="agent",
        provider="simulated",
        model="phase3-gauntlet",
        request={
            "context_files": ["values.py", "consumer.py"],
            "semantic_context": {
                "active_file": "values.py",
                "open_files": ["values.py", "consumer.py"],
            },
            "test_catalog": [
                {"id": "python:pytest", "framework": "pytest", "command": "python -m pytest -q"}
            ],
            "verification_ladder": True,
        },
        budget={
            "profile": "balanced",
            "max_model_turns": 20,
            "max_tool_calls": 30,
            "max_verification_cycles": 8,
        },
    )["run_id"]

    approval_id = "phase3-worktree-capability"
    engine.store.create_approval(run_id, {
        "request_id": approval_id,
        "capabilities": [{"id": "worktree_mutation"}],
    })
    engine.store.resolve_approval(run_id, approval_id, {
        "approved": True,
        "scope": "run",
    })

    scripted = ScriptedPlannerProvider([
        {"decision_type": "complete", "summary": "inspect"},
        {"decision_type": "complete", "summary": "bind"},
        {"decision_type": "complete", "summary": "read values"},
        {
            "decision_type": "tool",
            "tool_id": "worktree.replace_exact",
            "arguments": {
                "path": "values.py",
                "old_text": "VALUE = 1",
                "new_text": "VALUE = 2",
            },
        },
        {"decision_type": "complete", "summary": "verify diff"},
        {"decision_type": "complete", "summary": "verify syntax"},
        {"decision_type": "complete", "summary": "verify focused tests"},
        {
            "decision_type": "tool",
            "tool_id": "workspace.read_range",
            "arguments": {"path": "consumer.py", "start_line": 1, "line_count": 20},
        },
        {
            "decision_type": "tool",
            "tool_id": "worktree.replace_exact",
            "arguments": {
                "path": "consumer.py",
                "old_text": "RESULT = VALUE + 0",
                "new_text": "RESULT = VALUE + 1",
            },
        },
        {"decision_type": "complete", "summary": "reverify diff"},
        {"decision_type": "complete", "summary": "reverify syntax"},
        {"decision_type": "complete", "summary": "reverify focused tests"},
        {"decision_type": "complete", "summary": "prepare SourcePlan"},
        {"decision_type": "complete", "summary": "Phase 3 defect repaired with verified SourcePlan."},
    ])

    final = asyncio.run(
        AgentPlannerRuntime(
            engine,
            scripted,
            max_turns=20,
            observation_limit=50,
            max_repair_cycles=4,
        ).run(run_id)
    )

    assert final["state"] == "completed"
    checkpoint = final["checkpoint"]
    planner = checkpoint["planner"]
    assert planner["repair_cycles"] >= 1
    assert checkpoint["sourceplan"]["plan_id"]
    assert checkpoint["sourceplan"]["verification_ladder_complete"] is True
    assert checkpoint["sourceplan"]["verification_ladder_receipt_hash"].startswith("sha256:")

    worktree_root = Path(checkpoint["worktree_root"])
    assert worktree_root != root
    assert (worktree_root / "values.py").read_text(encoding="utf-8") == "VALUE = 2\n"
    assert (worktree_root / "consumer.py").read_text(encoding="utf-8") == (
        "from values import VALUE\nRESULT = VALUE + 1\n"
    )

    # Operator workspace remains untouched until a separate promotion action.
    assert (root / "values.py").read_text(encoding="utf-8") == "VALUE = 1\n"
    assert (root / "consumer.py").read_text(encoding="utf-8") == (
        "from values import VALUE\nRESULT = VALUE + 0\n"
    )

    events = engine.store.events(run_id, limit=1000)
    event_types = [event["event_type"] for event in events]
    assert "agent.verification.failed" in event_types
    assert "agent.verification.passed" in event_types
    assert "agent.repair.required" in event_types
    assert "agent.sourceplan.ready" in event_types
    assert "agent.budget.exhausted" not in event_types

    sourceplan_event = next(
        event for event in reversed(events)
        if event["event_type"] == "agent.sourceplan.ready"
    )
    ladder = sourceplan_event["payload"]["verification_ladder_receipt"]
    assert ladder["complete"] is True
    assert len(ladder["completed_stage_ids"]) >= 3

    authority = [
        event["payload"]["authority_receipt"]
        for event in events
        if event["event_type"] == "agent.tool.authorized"
    ]
    assert any(item["authority_class"] == "C_ISOLATED_MUTATION" for item in authority)
    assert any(item["authority_class"] == "D_CONSEQUENTIAL_EXECUTION" for item in authority)

    chain = engine.store.verify_chain(run_id)
    assert chain["ok"] is True
    assert chain["head_matches"] is True

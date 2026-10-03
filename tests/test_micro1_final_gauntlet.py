from __future__ import annotations

import asyncio
import subprocess

from app.kernel.agents.planner_provider import ScriptedPlannerProvider
from app.kernel.agents.planner_runtime import AgentPlannerRuntime
from app.kernel.agents.run_engine import AgentRunEngine


def test_micro1_final_no_provider_gauntlet(tmp_path):
    root = tmp_path / "micro1"
    root.mkdir()

    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(
        ["git", "config", "user.email", "beast@example.test"],
        cwd=root,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "BEAST Test"],
        cwd=root,
        check=True,
    )

    calculator = (
        'def safe_average(values):\n'
        '    """Return the arithmetic mean, or 0.0 for an empty iterable."""\n'
        '    values = list(values)\n'
        '    return sum(values) / len(values)\n'
    )

    tests = (
        'from calculator import safe_average\n\n'
        'def test_average():\n'
        '    assert safe_average([2, 4, 6]) == 4\n\n'
        'def test_empty():\n'
        '    assert safe_average([]) == 0.0\n\n'
        'def test_generator():\n'
        '    assert safe_average(x for x in [3, 6, 9]) == 6\n'
    )

    (root / "calculator.py").write_text(calculator, encoding="utf-8")
    (root / "test_calculator.py").write_text(tests, encoding="utf-8")

    subprocess.run(["git", "add", "."], cwd=root, check=True)
    subprocess.run(
        ["git", "commit", "-qm", "broken micro1 fixture"],
        cwd=root,
        check=True,
    )

    engine = AgentRunEngine(root)

    objective = (
        "Fix safe_average so an empty iterable returns 0.0 while preserving "
        "correct behavior for lists and generators. Inspect the existing code "
        "and tests, make the smallest maintainable change, run the relevant "
        "verification, and do not weaken or remove tests."
    )

    run_id = engine.create_run(
        session_id="session-micro1-final-gauntlet",
        objective=objective,
        mode="agent",
        provider="ollama",
        model="scripted-residual",
        request={
            "context_files": [
                "calculator.py",
                "test_calculator.py",
            ],
            "semantic_context": {
                "active_file": "calculator.py",
                "open_files": [
                    "calculator.py",
                    "test_calculator.py",
                ],
            },
            "test_catalog": [
                {
                    "id": "python:pytest",
                    "framework": "pytest",
                }
            ],
        },
    )["run_id"]

    approval_id = "micro1-run-scope"

    engine.store.create_approval(
        run_id,
        {
            "request_id": approval_id,
            "capabilities": [
                {"id": "worktree_mutation"},
                {"id": "run_isolated_verifier"},
            ],
        },
    )

    engine.store.resolve_approval(
        run_id,
        approval_id,
        {
            "approved": True,
            "scope": "run",
        },
    )

    good_residual = (
        'def safe_average(values):\n'
        '    """Return the arithmetic mean, or 0.0 for an empty iterable."""\n'
        '    values = list(values)\n'
        '    if not values:\n'
        '        return 0.0\n'
        '    return sum(values) / len(values)\n'
    )

    provider = ScriptedPlannerProvider([
        {
            "decision_type": "tool",
            "tool_id": "workspace.index",
            "arguments": {
                "limit": 1200,
                "include_symbols": True,
            },
        },
        {
            "decision_type": "tool",
            "tool_id": "worktree.bind",
            "approval_id": approval_id,
            "arguments": {
                "objective": objective,
                "risk": "high",
            },
        },
        {
            "decision_type": "tool",
            "tool_id": "workspace.read_range",
            "arguments": {
                "path": "calculator.py",
                "start_line": 1,
                "line_count": 80,
            },
        },

        # Deliberately malformed residual.
        {
            "decision_type": "tool",
            "tool_id": "worktree.replace_exact",
            "approval_id": approval_id,
            "arguments": {
                "new_text": (
                    'def safe_average(values):\n'
                    '    """broken'
                ),
            },
        },

        # Critic-driven revision.
        {
            "decision_type": "tool",
            "tool_id": "worktree.replace_exact",
            "approval_id": approval_id,
            "arguments": {
                "new_text": good_residual,
            },
        },

        # BEAST must refuse premature completion and force verification.
        {
            "decision_type": "complete",
            "summary": "candidate repaired; verify it",
        },

        # BEAST must then force SourcePlan.
        {
            "decision_type": "complete",
            "summary": "verified; prepare SourcePlan",
        },

        {
            "decision_type": "complete",
            "summary": "Micro-1 repaired, tested, and handed off.",
        },
    ])

    final = asyncio.run(
        AgentPlannerRuntime(
            engine,
            provider,
            max_turns=8,
            max_repair_cycles=3,
        ).run(run_id)
    )

    assert final["state"] == "completed"

    planner = final["checkpoint"]["planner"]
    observations = planner["observations"]

    mutation = next(
        item
        for item in observations
        if item.get("tool_id") == "worktree.replace_exact"
        and item.get("status") == "completed"
    )

    assert (
        mutation["result"]["before_sha256"]
        != mutation["result"]["after_sha256"]
    )
    assert mutation["result"]["path"] == "calculator.py"

    verify = next(
        item
        for item in observations
        if item.get("tool_id") == "worktree.verify"
    )

    assert verify["status"] == "completed"
    assert verify["result"]["ok"] is True
    assert verify["result"]["returncode"] == 0
    assert "pytest" in verify["result"]["command"]
    assert "test_calculator.py" in verify["result"]["command"]
    assert "3 passed" in verify["result"]["stdout"]

    sourceplan = next(
        item
        for item in observations
        if item.get("tool_id") == "worktree.sourceplan_draft"
    )

    assert sourceplan["status"] == "completed"
    assert sourceplan["result"]["ok"] is True

    events = engine.store.events(run_id, limit=400)

    assert any(
        e["event_type"] == "agent.mutation.revision_requested"
        for e in events
    )
    revision_requests = [
        e
        for e in events
        if e["event_type"] == "agent.mutation.revision_requested"
    ]
    assert revision_requests
    assert any(
        "residual critic before approval"
        in str(e.get("payload", {}).get("reason", "")).lower()
        for e in revision_requests
    )
    assert any(
        e["event_type"] == "agent.mutation.revision_accepted"
        for e in events
    )
    assert any(
        e["event_type"] == "agent.verification.passed"
        for e in events
    )
    assert any(
        e["event_type"] == "agent.sourceplan.ready"
        for e in events
    )

    # The rejected candidate must not have created a second approval.
    approvals = engine.store.approvals(run_id)
    assert len(approvals) == 1
    assert approvals[0]["status"] == "approved"

    checkpoint = final["checkpoint"]

    assert checkpoint["verification"]["ok"] is True
    assert checkpoint["verification"]["stale"] is False

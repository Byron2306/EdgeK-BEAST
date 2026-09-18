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
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "beast@example.test")
    _git(root, "config", "user.name", "BEAST Recovery Phase 4")
    (root / "pricing.py").write_text(
        "def calculate_total(subtotal, discount):\n"
        "    return subtotal\n",
        encoding="utf-8",
    )
    (root / "checkout.py").write_text(
        "from pricing import calculate_total\n\n"
        "def checkout(subtotal, discount):\n"
        "    return calculate_total(subtotal, discount)\n",
        encoding="utf-8",
    )
    tests = root / "tests"
    tests.mkdir()
    (tests / "test_checkout.py").write_text(
        "from checkout import checkout\n\n"
        "def test_discounted_checkout():\n"
        "    assert checkout(10, 3) == 7\n",
        encoding="utf-8",
    )
    _git(root, "add", ".")
    _git(root, "commit", "-qm", "seed cross-file pricing defect")
    return root


def _run(engine: AgentRunEngine, *, objective: str) -> str:
    run_id = engine.create_run(
        session_id="recovery-phase4",
        objective=objective,
        mode="agent",
        provider="simulated",
        model="planner-test",
        request={"long_horizon": True},
    )["run_id"]
    approval_id = "phase4-worktree"
    engine.store.create_approval(
        run_id,
        {
            "request_id": approval_id,
            "capabilities": [{"id": "worktree_mutation"}],
        },
    )
    engine.store.resolve_approval(
        run_id,
        approval_id,
        {"approved": True, "scope": "run"},
    )
    return run_id


def test_repository_perception_discovers_definition_and_dependent_without_attachments(tmp_path):
    root = _repo(tmp_path)
    engine = AgentRunEngine(root)
    run_id = _run(
        engine,
        objective="Repair calculate_total and ensure checkout uses the corrected discounted result.",
    )

    observation = asyncio.run(
        engine.execute_tool(
            run_id,
            "workspace.discover_context",
            {
                "query": "Repair calculate_total and ensure checkout uses the corrected discounted result.",
                "limit": 16,
            },
        )
    )

    result = observation["result"]
    assert result["authority"] == "advisory_discovery_only"
    assert result["exact_source_required_before_mutation"] is True
    assert result["code_cortex"]["owner"] == "Code Cortex"
    assert result["structural_index"]["summary"]["file_count"] >= 3
    assert result["sensorium"]["owner"] == "WorkspaceInvalidationBus"
    paths = result["candidate_paths"]
    assert "pricing.py" in paths
    assert "checkout.py" in paths
    assert any(
        row["source_path"] == "pricing.py" and row["path"] == "checkout.py"
        for row in result["dependents"]
    )
    assert result["perception_digest"].startswith("sha256:")


def test_sensorium_change_state_is_bound_into_later_repository_perception(tmp_path):
    root = _repo(tmp_path)
    engine = AgentRunEngine(root)
    run_id = _run(engine, objective="Inspect calculate_total repository state.")

    asyncio.run(
        engine.execute_tool(
            run_id,
            "workspace.discover_context",
            {"query": "calculate_total", "limit": 12},
        )
    )
    (root / "pricing.py").write_text(
        "def calculate_total(subtotal, discount):\n"
        "    # changed after perception baseline\n"
        "    return subtotal\n",
        encoding="utf-8",
    )
    second = asyncio.run(
        engine.execute_tool(
            run_id,
            "workspace.discover_context",
            {"query": "calculate_total", "limit": 12},
        )
    )
    changes = second["result"]["sensorium"]["changes"]
    assert any(row["path"] == "pricing.py" and row["kind"] == "modified" for row in changes)


def test_cross_file_agent_repairs_two_files_without_manual_context_attachments(tmp_path):
    root = _repo(tmp_path)
    engine = AgentRunEngine(root)
    objective = (
        "Cross-cutting repair: fix calculate_total to subtract discount and "
        "make checkout clamp the returned total at zero."
    )
    run_id = _run(engine, objective=objective)

    provider = ScriptedPlannerProvider([
        {"decision_type": "complete", "summary": "discover repository"},
        {"decision_type": "complete", "summary": "bind worktree"},
        {"decision_type": "complete", "summary": "read discovered definition"},
        {
            "decision_type": "tool",
            "tool_id": "workspace.read_range",
            "arguments": {"path": "checkout.py", "start_line": 1, "line_count": 80},
        },
        {
            "decision_type": "tool",
            "tool_id": "worktree.replace_exact",
            "arguments": {
                "path": "pricing.py",
                "old_text": "    return subtotal",
                "new_text": "    return subtotal - discount",
            },
        },
        {
            "decision_type": "tool",
            "tool_id": "worktree.replace_exact",
            "arguments": {
                "path": "checkout.py",
                "old_text": "    return calculate_total(subtotal, discount)",
                "new_text": "    return max(0, calculate_total(subtotal, discount))",
            },
        },
        {"decision_type": "complete", "summary": "verify"},
        {"decision_type": "complete", "summary": "handoff"},
        {"decision_type": "complete", "summary": "done"},
    ])

    final = asyncio.run(
        AgentPlannerRuntime(
            engine,
            provider,
            max_turns=10,
            observation_limit=30,
        ).run(run_id)
    )

    assert final["state"] == "completed"
    observations = final["checkpoint"]["planner"]["observations"]
    assert observations[0]["tool_id"] == "workspace.discover_context"
    discovery = observations[0]["result"]
    assert "pricing.py" in discovery["candidate_paths"], discovery
    assert "checkout.py" in discovery["candidate_paths"], discovery

    reads = [
        item["result"]["path"]
        for item in observations
        if item["tool_id"] == "workspace.read_range" and item["status"] == "completed"
    ]
    assert "pricing.py" in reads
    assert "checkout.py" in reads

    changed = [
        item["result"]["path"]
        for item in observations
        if item["tool_id"] == "worktree.replace_exact" and item["status"] == "completed"
    ]
    assert changed == ["pricing.py", "checkout.py"]

    worktree = Path(final["checkpoint"]["worktree_root"])
    assert "return subtotal - discount" in (worktree / "pricing.py").read_text(encoding="utf-8")
    assert "return max(0, calculate_total" in (worktree / "checkout.py").read_text(encoding="utf-8")

    # Exact source remains untouched until the later SourcePlan promotion boundary.
    assert "return subtotal\n" in (root / "pricing.py").read_text(encoding="utf-8")
    assert "return calculate_total" in (root / "checkout.py").read_text(encoding="utf-8")

    assert final["checkpoint"]["sourceplan"]["plan_id"]
    assert engine.store.verify_chain(run_id)["head_matches"] is True

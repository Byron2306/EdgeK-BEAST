from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path

from app.kernel.agents.planner_provider import ScriptedPlannerProvider
from app.kernel.agents.planner_runtime import AgentPlannerRuntime
from app.kernel.agents.run_engine import AgentRunEngine


def _repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "beast@example.test"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "BEAST Test"], cwd=root, check=True)
    (root / "answer.py").write_text("VALUE = 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    subprocess.run(["git", "commit", "-qm", "initial"], cwd=root, check=True)
    return root


def _approval(engine: AgentRunEngine, run_id: str) -> str:
    approval_id = "repair-tools"
    engine.store.create_approval(run_id, {"request_id": approval_id, "capabilities": [{"id": "worktree_mutation"}]})
    engine.store.resolve_approval(run_id, approval_id, {"approved": True, "scope": "run"})
    return approval_id


def test_failed_verification_returns_structured_observation_and_repairs(tmp_path):
    async def scenario():
        root = _repo(tmp_path)
        engine = AgentRunEngine(root)
        run_id = engine.create_run(session_id="session", objective="make VALUE equal 2")["run_id"]
        approval = _approval(engine, run_id)
        provider = ScriptedPlannerProvider([
            {"decision_type": "tool", "tool_id": "worktree.bind", "approval_id": approval, "arguments": {"objective": "repair VALUE"}},
            {"decision_type": "tool", "tool_id": "worktree.replace_exact", "approval_id": approval, "arguments": {"path": "answer.py", "old_text": "VALUE = 1", "new_text": "VALUE = 3"}},
            {"decision_type": "tool", "tool_id": "worktree.verify", "approval_id": approval, "arguments": {"command": ["python", "-c", "from answer import VALUE; assert VALUE == 2"]}},
            {"decision_type": "tool", "tool_id": "worktree.replace_exact", "approval_id": approval, "arguments": {"path": "answer.py", "old_text": "VALUE = 3", "new_text": "VALUE = 2"}},
            {"decision_type": "tool", "tool_id": "worktree.verify", "approval_id": approval, "arguments": {"command": ["python", "-c", "from answer import VALUE; assert VALUE == 2"]}},
            {"decision_type": "tool", "tool_id": "worktree.sourceplan_draft", "arguments": {}},
            {"decision_type": "complete", "summary": "VALUE repaired and verified."},
        ])
        final = await AgentPlannerRuntime(engine, provider, max_turns=8, max_repair_cycles=2).run(run_id)
        planner = final["checkpoint"]["planner"]
        assert final["state"] == "completed"
        assert planner["repair_cycles"] == 1
        failed = [item for item in planner["observations"] if item["tool_id"] == "worktree.verify" and item["status"] == "failed"]
        assert len(failed) == 1
        assert failed[0]["observation_id"].startswith("obs_")
        assert failed[0]["result"]["returncode"] != 0
        checkpoint = final["checkpoint"]
        assert checkpoint["verification"]["ok"] is True
        assert checkpoint["verification"]["mutation_epoch"] == checkpoint["worktree_mutation_epoch"] == 2
        assert checkpoint["sourceplan"]["plan_id"]
        event_types = [e["event_type"] for e in engine.store.events(run_id, limit=500)]
        assert "agent.verification.failed" in event_types
        assert "agent.repair.required" in event_types
        assert "agent.verification.passed" in event_types
        assert engine.store.verify_chain(run_id)["ok"] is True
    asyncio.run(scenario())


def test_mutation_invalidates_old_verification_receipt(tmp_path):
    async def scenario():
        root = _repo(tmp_path)
        engine = AgentRunEngine(root)
        run_id = engine.create_run(session_id="session", objective="stale proof refusal")["run_id"]
        approval = _approval(engine, run_id)
        await engine.execute_tool(run_id, "worktree.bind", {"objective": "stale proof"}, approval_id=approval)
        await engine.execute_tool(run_id, "worktree.verify", {"command": ["python", "-c", "from answer import VALUE; assert VALUE == 1"]}, approval_id=approval)
        await engine.execute_tool(run_id, "worktree.replace_exact", {"path": "answer.py", "old_text": "VALUE = 1", "new_text": "VALUE = 2"}, approval_id=approval)
        checkpoint = engine.store.get_run(run_id)["checkpoint"]
        assert checkpoint["verification"]["ok"] is False
        assert checkpoint["verification"]["stale"] is True
        try:
            await engine.execute_tool(run_id, "worktree.sourceplan_draft", {})
        except Exception as exc:
            assert "latest mutation epoch" in str(exc)
        else:
            raise AssertionError("SourcePlan accepted a stale verification receipt")
    asyncio.run(scenario())


def test_repair_budget_exhaustion_is_terminal(tmp_path):
    async def scenario():
        root = _repo(tmp_path)
        engine = AgentRunEngine(root)
        run_id = engine.create_run(session_id="session", objective="bounded failure")["run_id"]
        approval = _approval(engine, run_id)
        provider = ScriptedPlannerProvider([
            {"decision_type": "tool", "tool_id": "worktree.bind", "approval_id": approval, "arguments": {"objective": "bounded failure"}},
            {"decision_type": "tool", "tool_id": "worktree.verify", "approval_id": approval, "arguments": {"command": ["python", "-c", "raise SystemExit(1)"]}},
            {"decision_type": "tool", "tool_id": "worktree.verify", "approval_id": approval, "arguments": {"command": ["python", "-c", "raise SystemExit(1)"]}},
        ])
        final = await AgentPlannerRuntime(engine, provider, max_turns=5, max_repair_cycles=1).run(run_id)
        assert final["state"] == "budget_exhausted"
        assert final["checkpoint"]["planner"]["status"] == "repair_exhausted"
        assert final["checkpoint"]["planner"]["repair_cycles"] == 2
        assert any(e["event_type"] == "agent.repair.budget_exhausted" for e in engine.store.events(run_id, limit=200))
    asyncio.run(scenario())

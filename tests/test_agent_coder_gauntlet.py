"""Agentic Coding Gauntlet - End-to-end autonomous coding with crystal/lattice promotion.

This test suite proves that BEAST's TLI performs fully autonomous multi-file coding
with crystal reuse and lattice promotion happening naturally as part of the agent loop,
not as a separate governance step.

The gauntlet:
1. Sets up a multi-file Python project
2. Runs an autonomous agent that edits multiple files, writes tests, verifies
3. Crystal/lattice promotion fires automatically after verified apply
4. All workspace changes are actually applied (not just isolated)
5. No per-step approval prompts (autopilot mode)
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from app.kernel.agents.planner_models import PlannerDecision, PlannerDecisionType
from app.kernel.agents.planner_provider import PlannerProvider
from app.kernel.agents.planner_runtime import AgentPlannerRuntime
from app.kernel.agents.run_engine import AgentRunEngine


class GauntletAgent(PlannerProvider):
    """Deterministic agent that performs multi-file autonomous coding:

    1. Inspects the workspace (workspace.index)
    2. Binds an isolated worktree (worktree.bind)
    3. Edits multiple files (worktree.replace_exact)
    4. Writes new test files (worktree.write_file)
    5. Verifies compilation (worktree.verify)
    6. Drafts a SourcePlan handoff (worktree.sourceplan_draft)
    7. Completes — triggering autopromotion into the crystal lattice
    """

    def __init__(self) -> None:
        self.calls = 0
        self.last_usage: dict | None = None
        self.decisions: list[PlannerDecision] = []

    async def next_decision(self, prompt: str, *, run: dict, turn: int) -> PlannerDecision:
        self.calls += 1
        decision: PlannerDecision

        if self.calls == 1:
            decision = PlannerDecision(
                decision_type=PlannerDecisionType.TOOL,
                tool_id="workspace.index",
                arguments={"limit": 200, "include_symbols": True},
                rationale="Index the workspace before editing.",
            )
        elif self.calls == 2:
            decision = PlannerDecision(
                decision_type=PlannerDecisionType.TOOL,
                tool_id="worktree.bind",
                arguments={"objective": "Multi-file refactor and test coverage"},
                rationale="Create isolated worktree before editing.",
            )
        elif self.calls == 3:
            decision = PlannerDecision(
                decision_type=PlannerDecisionType.TOOL,
                tool_id="worktree.replace_exact",
                arguments={
                    "path": "lib/math.py",
                    "old_text": "def add(a, b):\n    return a + b",
                    "new_text": 'def add(a, b):\n    """Add two numbers."""\n    return a + b',
                },
                rationale="Add docstring to lib/math.py.",
            )
        elif self.calls == 4:
            decision = PlannerDecision(
                decision_type=PlannerDecisionType.TOOL,
                tool_id="worktree.replace_exact",
                arguments={
                    "path": "lib/string_utils.py",
                    "old_text": "def capitalize(text):\n    return text.upper()",
                    "new_text": 'def capitalize(text):\n    """Capitalize text."""\n    return text.upper()',
                },
                rationale="Add docstring to lib/string_utils.py.",
            )
        elif self.calls == 5:
            decision = PlannerDecision(
                decision_type=PlannerDecisionType.TOOL,
                tool_id="worktree.replace_exact",
                arguments={
                    "path": "lib/calculator.py",
                    "old_text": "def multiply(a, b):\n    return a * b",
                    "new_text": 'def multiply(a, b):\n    """Multiply two numbers."""\n    return a * b',
                },
                rationale="Add docstring to lib/calculator.py.",
            )
        elif self.calls == 6:
            decision = PlannerDecision(
                decision_type=PlannerDecisionType.TOOL,
                tool_id="worktree.write_file",
                arguments={
                    "path": "tests/test_math.py",
                    "content": "from lib.math import add\n\ndef test_add():\n    assert add(2, 3) == 5\n    assert add(-1, 1) == 0\n    assert add(0, 0) == 0\n",
                },
                rationale="Write unit tests for lib/math.py.",
            )
        elif self.calls == 7:
            decision = PlannerDecision(
                decision_type=PlannerDecisionType.TOOL,
                tool_id="worktree.write_file",
                arguments={
                    "path": "tests/test_string_utils.py",
                    "content": "from lib.string_utils import capitalize\n\ndef test_capitalize():\n    assert capitalize(\"hello\") == \"HELLO\"\n    assert capitalize(\"world\") == \"WORLD\"\n",
                },
                rationale="Write unit tests for lib/string_utils.py.",
            )
        elif self.calls == 8:
            decision = PlannerDecision(
                decision_type=PlannerDecisionType.TOOL,
                tool_id="worktree.verify",
                arguments={"command": ["python", "-m", "py_compile", "lib/math.py", "lib/string_utils.py", "lib/calculator.py", "tests/test_math.py", "tests/test_string_utils.py"]},
                rationale="Verify all edited files compile.",
            )
        elif self.calls == 9:
            decision = PlannerDecision(
                decision_type=PlannerDecisionType.TOOL,
                tool_id="worktree.sourceplan_draft",
                arguments={},
                rationale="Materialize the verified diff as a SourcePlan handoff.",
            )
        else:
            decision = PlannerDecision(
                decision_type=PlannerDecisionType.COMPLETE,
                arguments={},
                summary="Multi-file refactor with docstrings and tests, verified and applied.",
                rationale="All edits verified, tests present, SourcePlan ready for lattice promotion.",
            )

        self.decisions.append(decision)
        return decision


def _gauntlet_repo(root: Path) -> None:
    """Create a git repo with multiple files for multi-file editing tests."""
    (root / "lib").mkdir()
    (root / "tests").mkdir()
    (root / "lib" / "math.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    (root / "lib" / "string_utils.py").write_text("def capitalize(text):\n    return text.upper()\n", encoding="utf-8")
    (root / "lib" / "calculator.py").write_text("def multiply(a, b):\n    return a * b\n", encoding="utf-8")
    (root / "tests" / "__init__.py").write_text("", encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "beast@example.test"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "BEAST Test"], cwd=root, check=True)
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    subprocess.run(["git", "commit", "-qm", "initial"], cwd=root, check=True)


@pytest.mark.asyncio
async def test_agent_gauntlet_multi_file_with_crystal_lattice(tmp_path: Path):
    """Full agentic coding gauntlet: multi-file edits with crystal/lattice promotion.

    The agent autonomously:
    1. Indexes the workspace
    2. Binds an isolated worktree
    3. Edits 3 files (adds docstrings)
    4. Writes 2 test files
    5. Verifies compilation
    6. Drafts a SourcePlan
    7. Completes — triggering autopromotion into the crystal lattice

    All workspace changes are actually applied (not just isolated).
    No per-step approval prompts (autopilot mode).
    """
    _gauntlet_repo(tmp_path)
    engine = AgentRunEngine(tmp_path)
    run = engine.create_run(
        session_id="crystal-lattice-gauntlet",
        objective="Add docstrings and tests to lib modules",
        mode="agent",
        provider="scripted",
        model="scripted",
        request={
            "autonomy": "autopilot",
            "apply_on_completion": True,
            "context_files": ["lib/math.py", "lib/string_utils.py", "lib/calculator.py"],
            "implementation_target": "lib/math.py",
            "execution_target": "local",
            "transport": "beast_coder_tli_v1",
        },
    )
    run_id = run["run_id"]
    runtime = AgentPlannerRuntime(
        engine,
        GauntletAgent(),
        max_turns=12,
    )
    result = await runtime.run(run_id)

    # The run should complete (not block or fail)
    assert result["state"] == "completed", f"Run did not complete: {result.get('state')} error={result.get('error')}"

    # Verify all workspace files were actually modified
    math_file = tmp_path / "lib" / "math.py"
    content = math_file.read_text(encoding="utf-8")
    assert '"""Add two numbers."""' in content, f"Expected docstring in math.py, got: {content}"

    string_file = tmp_path / "lib" / "string_utils.py"
    content = string_file.read_text(encoding="utf-8")
    assert '"""Capitalize text."""' in content, f"Expected docstring in string_utils.py, got: {content}"

    calc_file = tmp_path / "lib" / "calculator.py"
    content = calc_file.read_text(encoding="utf-8")
    assert '"""Multiply two numbers."""' in content, f"Expected docstring in calculator.py, got: {content}"

    # Test files should have been created
    test_math = tmp_path / "tests" / "test_math.py"
    assert test_math.exists(), "test_math.py was not created"
    test_content = test_math.read_text(encoding="utf-8")
    assert "def test_add" in test_content, f"Expected test_add in test file, got: {test_content}"

    test_string = tmp_path / "tests" / "test_string_utils.py"
    assert test_string.exists(), "test_string_utils.py was not created"
    test_content = test_string.read_text(encoding="utf-8")
    assert "def test_capitalize" in test_content, f"Expected test_capitalize in test file, got: {test_content}"

    # Crystal reuse/reduction events should have been emitted
    events = engine.store.events(run_id, limit=500)
    crystal_events = [e for e in events if str(e.get("event_type", "")).startswith("agent.crystal")]
    assert len(crystal_events) > 0, f"No crystal events emitted. Events: {[e.get('event_type') for e in events]}"

    # Check for applied worktree event (workspace was modified - not just isolated)
    applied_events = [e for e in events if e.get("event_type") == "agent.worktree.applied"]
    assert len(applied_events) > 0, "No worktree.apply event emitted — workspace was not modified"

    # A multi-file docstring edit is outside the reviewed crystal recipe.  It
    # must not receive synthetic reduction credit merely because apply passed.
    reduction_events = [e for e in events if e.get("event_type") == "agent.crystal.reduction_receipt"]
    assert reduction_events == [], f"Unsupported episode received false crystal credit: {reduction_events}"

    # Verify the diff_ready event was emitted (live diff panel)
    diff_events = [e for e in events if e.get("event_type") == "agent.worktree.diff_ready"]
    assert len(diff_events) > 0, "No worktree.diff_ready event — live diff panel not populated"

    # Verify all 5 tool decisions were made (bind, 3x replace_exact, 2x write_file, verify, sourceplan)
    tool_events = [e for e in events if e.get("event_type") in ("agent.tool.started", "agent.tool.completed")]
    tool_ids = {e.get("payload", {}).get("observation", {}).get("tool_id") for e in tool_events if e.get("payload", {}).get("observation")}
    assert "worktree.bind" in tool_ids, f"worktree.bind not in tool events: {tool_ids}"
    assert "worktree.replace_exact" in tool_ids, f"worktree.replace_exact not in tool events: {tool_ids}"
    assert "worktree.write_file" in tool_ids, f"worktree.write_file not in tool events: {tool_ids}"
    assert "worktree.verify" in tool_ids, f"worktree.verify not in tool events: {tool_ids}"
    assert "worktree.sourceplan_draft" in tool_ids, f"worktree.sourceplan_draft not in tool events: {tool_ids}"


@pytest.mark.asyncio
async def test_agent_gauntlet_no_approval_prompts(tmp_path: Path):
    """Verify that autopilot mode does not produce per-step approval prompts.

    All workspace-bounded tools should be auto-granted in autopilot mode.
    """
    _gauntlet_repo(tmp_path)
    engine = AgentRunEngine(tmp_path)
    run = engine.create_run(
        session_id="no-approval-gauntlet",
        objective="Add docstrings to lib modules",
        mode="agent",
        provider="scripted",
        model="scripted",
        request={
            "autonomy": "autopilot",
            "apply_on_completion": True,
            "context_files": ["lib/math.py"],
            "implementation_target": "lib/math.py",
            "execution_target": "local",
            "transport": "beast_coder_tli_v1",
        },
    )
    run_id = run["run_id"]
    runtime = AgentPlannerRuntime(
        engine,
        GauntletAgent(),
        max_turns=12,
    )
    result = await runtime.run(run_id)

    assert result["state"] == "completed", f"Run did not complete: {result.get('state')}"

    # Verify no approval cards were created (autopilot auto-grants)
    approvals = engine.store.approvals(run_id)
    approval_cards = [a for a in approvals if a.get("status") == "pending"]
    assert len(approval_cards) == 0, f"Expected no pending approvals, got {len(approval_cards)}: {approval_cards}"

    # But audit records should exist (autopilot grants are audited)
    all_approvals = engine.store.approvals(run_id)
    assert len(all_approvals) > 0, "Expected autopilot approval records for auditability"

    # All approvals should be approved (autopilot granted them)
    for a in all_approvals:
        assert a.get("status") == "approved", f"Expected approved approval, got: {a}"

    # Verify the workspace was actually changed
    math_file = tmp_path / "lib" / "math.py"
    content = math_file.read_text(encoding="utf-8")
    assert '"""Add two numbers."""' in content, f"Expected docstring in math.py, got: {content}"


@pytest.mark.asyncio
async def test_agent_gauntlet_crystal_lattice_full_flow(tmp_path: Path):
    """Complete gauntlet: multi-file edits → verify → sourceplan → complete → crystal lattice.

    This is the full integration test that proves the entire agentic coding loop
    works end-to-end with crystal reuse and lattice compounding.
    """
    _gauntlet_repo(tmp_path)
    engine = AgentRunEngine(tmp_path)
    run = engine.create_run(
        session_id="full-gauntlet",
        objective="Complete refactor of lib modules with tests and verification",
        mode="agent",
        provider="scripted",
        model="scripted",
        request={
            "autonomy": "autopilot",
            "apply_on_completion": True,
            "context_files": ["lib/math.py", "lib/string_utils.py", "lib/calculator.py"],
            "implementation_target": "lib/math.py",
            "execution_target": "local",
            "transport": "beast_coder_tli_v1",
        },
    )
    run_id = run["run_id"]
    runtime = AgentPlannerRuntime(
        engine,
        GauntletAgent(),
        max_turns=14,
    )
    result = await runtime.run(run_id)

    # Run should complete successfully
    assert result["state"] == "completed", f"Run did not complete: {result.get('state')} error={result.get('error')}"

    # Verify all files were changed in the workspace
    assert '"""Add two numbers."""' in (tmp_path / "lib" / "math.py").read_text(encoding="utf-8")
    assert '"""Capitalize text."""' in (tmp_path / "lib" / "string_utils.py").read_text(encoding="utf-8")
    assert '"""Multiply two numbers."""' in (tmp_path / "lib" / "calculator.py").read_text(encoding="utf-8")

    # Test files exist
    assert (tmp_path / "tests" / "test_math.py").exists()
    assert (tmp_path / "tests" / "test_string_utils.py").exists()

    # Full event trace verification
    events = engine.store.events(run_id, limit=1000)
    event_types = {str(e.get("event_type", "")) for e in events}

    # Core lifecycle events - tool events use agent.tool.started/completed with
    # the actual tool_id in the payload
    tool_event_types = {e.get("event_type", "") for e in events if e.get("event_type", "").startswith("agent.tool")}
    tool_payloads = [e.get("payload", {}) for e in events if e.get("event_type", "") == "agent.tool.completed"]
    tool_ids = {p.get("observation", {}).get("tool_id") for p in tool_payloads if isinstance(p.get("observation"), dict)}
    assert "worktree.bind" in tool_ids, f"worktree.bind not in tool events: {tool_ids}"
    assert "worktree.replace_exact" in tool_ids, f"worktree.replace_exact not in tool events: {tool_ids}"
    assert "worktree.write_file" in tool_ids, f"worktree.write_file not in tool events: {tool_ids}"
    assert "worktree.verify" in tool_ids, f"worktree.verify not in tool events: {tool_ids}"
    assert "worktree.sourceplan_draft" in tool_ids, f"worktree.sourceplan_draft not in tool events: {tool_ids}"

    # worktree.applied is a separate event type
    assert any("agent.worktree.applied" == et for et in event_types), f"No worktree.applied event: {event_types}"

    # The scan is observable, but unsupported work is not credited.
    assert any("agent.crystal.autopromotion" == et for et in event_types), \
        f"No crystal.autopromotion. Types: {event_types}"

    # A credited receipt is reserved for an actual durable formation/reuse.
    reduction_events = [e for e in events if e.get("event_type") == "agent.crystal.reduction_receipt"]
    assert reduction_events == []

    # Verify diff panel would have data
    diff_events = [e for e in events if e.get("event_type") == "agent.worktree.diff_ready"]
    assert len(diff_events) > 0
    for ev in diff_events:
        payload = ev.get("payload", {})
        assert "diff" in payload or "files" in payload, f"Diff event missing diff/files: {payload}"

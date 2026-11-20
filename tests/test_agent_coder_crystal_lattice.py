"""End-to-end agentic coding tests with crystal reuse and lattice compounding.

These tests verify that BEAST's TLI performs multi-file autonomous coding with
crystal reuse observation and lattice promotion happening naturally as part of
the agent loop, not as a separate governance step.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from app.kernel.agents.planner_models import PlannerDecision, PlannerDecisionType
from app.kernel.agents.planner_provider import PlannerProvider
from app.kernel.agents.planner_runtime import AgentPlannerRuntime
from app.kernel.agents.run_engine import AgentRunEngine


class MultiFileAgent(PlannerProvider):
    """A deterministic stand-in for a model that performs multi-file autonomous coding:

    1. Inspects the workspace
    2. Binds a worktree
    3. Edits multiple files
    4. Writes tests
    5. Verifies compilation
    6. Drafts a SourcePlan handoff
    7. Completes — triggering autopromotion into the crystal lattice
    """

    def __init__(self) -> None:
        self.calls = 0
        self.last_usage: dict | None = None

    async def next_decision(self, prompt: str, *, run: dict, turn: int) -> PlannerDecision:
        self.calls += 1
        if self.calls == 1:
            return PlannerDecision(
                decision_type=PlannerDecisionType.TOOL,
                tool_id="workspace.index",
                arguments={"limit": 200, "include_symbols": True},
                rationale="Index the workspace before editing.",
            )
        if self.calls == 2:
            return PlannerDecision(
                decision_type=PlannerDecisionType.TOOL,
                tool_id="worktree.bind",
                arguments={"objective": "Multi-file refactor and test coverage"},
                rationale="Create isolated worktree before editing.",
            )
        if self.calls == 3:
            return PlannerDecision(
                decision_type=PlannerDecisionType.TOOL,
                tool_id="worktree.replace_exact",
                arguments={
                    "path": "lib/math.py",
                    "old_text": "def add(a, b):\n    return a + b",
                    "new_text": 'def add(a, b):\n    """Add two numbers."""\n    return a + b',
                },
                rationale="Add docstring to lib/math.py.",
            )
        if self.calls == 4:
            return PlannerDecision(
                decision_type=PlannerDecisionType.TOOL,
                tool_id="worktree.replace_exact",
                arguments={
                    "path": "lib/string_utils.py",
                    "old_text": "def capitalize(text):\n    return text.upper()",
                    "new_text": 'def capitalize(text):\n    """Capitalize text."""\n    return text.upper()',
                },
                rationale="Add docstring to lib/string_utils.py.",
            )
        if self.calls == 5:
            return PlannerDecision(
                decision_type=PlannerDecisionType.TOOL,
                tool_id="worktree.write_file",
                arguments={
                    "path": "tests/test_math.py",
                    "content": "from lib.math import add\n\ndef test_add():\n    assert add(2, 3) == 5\n    assert add(-1, 1) == 0\n",
                },
                rationale="Write unit tests for lib/math.py.",
            )
        if self.calls == 6:
            return PlannerDecision(
                decision_type=PlannerDecisionType.TOOL,
                tool_id="worktree.verify",
                arguments={"command": ["python", "-m", "py_compile", "lib/math.py", "lib/string_utils.py", "tests/test_math.py"]},
                rationale="Verify edited files compile.",
            )
        if self.calls == 7:
            return PlannerDecision(
                decision_type=PlannerDecisionType.TOOL,
                tool_id="worktree.sourceplan_draft",
                arguments={},
                rationale="Materialize the verified diff as a SourcePlan handoff.",
            )
        return PlannerDecision(
            decision_type=PlannerDecisionType.COMPLETE,
            arguments={},
            summary="Multi-file refactor with docstrings and tests, verified and applied.",
            rationale="All edits verified, tests present, SourcePlan ready for lattice promotion.",
        )


def _repo_with_files(root: Path) -> None:
    """Create a git repo with multiple files for multi-file editing tests."""
    (root / "lib").mkdir()
    (root / "tests").mkdir()
    (root / "lib" / "math.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    (root / "lib" / "string_utils.py").write_text("def capitalize(text):\n    return text.upper()\n", encoding="utf-8")
    (root / "tests" / "__init__.py").write_text("", encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "beast@example.test"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "BEAST Test"], cwd=root, check=True)
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    subprocess.run(["git", "commit", "-qm", "initial"], cwd=root, check=True)


@pytest.mark.asyncio
async def test_agent_multi_file_edit_with_crystal_lattice_promotion(tmp_path: Path):
    """Multi-file agentic coding with crystal reuse and lattice promotion.

    The agent reads, binds, edits multiple files, writes tests, verifies,
    drafts a SourcePlan, and completes — triggering autopromotion into the
    crystal lattice. Crystal reuse and lattice events are observed in the
    runtime event stream.
    """
    _repo_with_files(tmp_path)
    engine = AgentRunEngine(tmp_path)
    run = engine.create_run(
        session_id="crystal-lattice-session",
        objective="Add docstrings and tests to lib modules",
        mode="agent",
        provider="scripted",
        model="scripted",
        request={
            "autonomy": "autopilot",
            "apply_on_completion": True,
            "context_files": ["lib/math.py", "lib/string_utils.py"],
            "implementation_target": "lib/math.py",
            "execution_target": "local",
            "transport": "beast_coder_tli_v1",
        },
    )
    run_id = run["run_id"]
    runtime = AgentPlannerRuntime(
        engine,
        MultiFileAgent(),
        max_turns=12,
    )
    result = await runtime.run(run_id)

    # The run should complete (not block or fail)
    assert result["state"] == "completed", f"Run did not complete: {result.get('state')} error={result.get('error')}"

    # The workspace file should have been modified
    math_file = tmp_path / "lib" / "math.py"
    content = math_file.read_text(encoding="utf-8")
    assert '"""Add two numbers."""' in content, f"Expected docstring in math.py, got: {content}"

    # The test file should have been created
    test_file = tmp_path / "tests" / "test_math.py"
    assert test_file.exists(), "Test file was not created"
    test_content = test_file.read_text(encoding="utf-8")
    assert "def test_add" in test_content, f"Expected test_add in test file, got: {test_content}"

    # Crystal reuse/reduction events should have been emitted
    events = engine.store.events(run_id, limit=500)
    crystal_events = [e for e in events if str(e.get("event_type", "")).startswith("agent.crystal")]
    assert len(crystal_events) > 0, f"No crystal events emitted. Events: {[e.get('event_type') for e in events]}"

    # Check for applied worktree event (workspace was modified)
    applied_events = [e for e in events if e.get("event_type") == "agent.worktree.applied"]
    assert len(applied_events) > 0, "No worktree.apply event emitted — workspace was not modified"

    # Check for crystal reduction receipt (promotion into lattice)
    reduction_events = [e for e in events if e.get("event_type") == "agent.crystal.reduction_receipt"]
    assert len(reduction_events) > 0, "No crystal.reduction_receipt event — autopromotion did not fire"


@pytest.mark.asyncio
async def test_agent_swarm_subagent_with_crystal_observation(tmp_path: Path):
    """Agent uses swarm subagent for complex task with crystal observation.

    The agent decomposes a complex refactoring via swarm, edits files, verifies,
    and completes — triggering autopromotion into the crystal lattice.
    Crystal reuse observations are recorded during execution.
    """
    _repo_with_files(tmp_path)
    engine = AgentRunEngine(tmp_path)
    run = engine.create_run(
        session_id="swarm-crystal-session",
        objective="Refactor lib modules and add comprehensive test coverage",
        mode="agent",
        provider="scripted",
        model="scripted",
        request={
            "autonomy": "autopilot",
            "apply_on_completion": True,
            "context_files": ["lib/math.py", "lib/string_utils.py"],
            "execution_target": "local",
            "transport": "beast_coder_tli_v1",
            "swarm_specialist": True,
        },
    )
    run_id = run["run_id"]
    runtime = AgentPlannerRuntime(
        engine,
        MultiFileAgent(),
        max_turns=14,
    )
    result = await runtime.run(run_id)

    assert result["state"] == "completed", f"Run did not complete: {result.get('state')}"

    # Verify workspace changes
    math_file = tmp_path / "lib" / "math.py"
    assert '"""Add two numbers."""' in math_file.read_text(encoding="utf-8")

    test_file = tmp_path / "tests" / "test_math.py"
    assert test_file.exists()
    assert "def test_add" in test_file.read_text(encoding="utf-8")

    # Crystal events should be present
    events = engine.store.events(run_id, limit=500)
    crystal_events = [e for e in events if str(e.get("event_type", "")).startswith("agent.crystal")]
    assert len(crystal_events) > 0, f"No crystal events. Event types: {[e.get('event_type') for e in events]}"

    # Autopromotion should have fired
    reduction_events = [e for e in events if e.get("event_type") == "agent.crystal.reduction_receipt"]
    assert len(reduction_events) > 0, "No crystal reduction receipt — autopromotion did not fire"


@pytest.mark.asyncio
async def test_crystal_lattice_ui_events_projected(tmp_path: Path):
    """Verify that crystal/lattice events are projected to the UI event stream.

    This test verifies that the UI can observe crystal reuse decisions,
    lattice promotions, and autopromotion activity through the event stream.
    """
    _repo_with_files(tmp_path)
    engine = AgentRunEngine(tmp_path)
    run = engine.create_run(
        session_id="crystal-ui-session",
        objective="Test crystal lattice UI integration",
        mode="agent",
        provider="scripted",
        model="scripted",
        request={
            "autonomy": "autopilot",
            "apply_on_completion": True,
            "context_files": ["lib/math.py"],
            "execution_target": "local",
            "transport": "beast_coder_tli_v1",
        },
    )
    run_id = run["run_id"]
    runtime = AgentPlannerRuntime(
        engine,
        MultiFileAgent(),
        max_turns=12,
    )
    result = await runtime.run(run_id)

    assert result["state"] == "completed"

    # Collect all events and verify crystal/lattice event types are present
    events = engine.store.events(run_id, limit=1000)
    event_types = {str(e.get("event_type", "")) for e in events}

    # Core crystal events should be present
    assert any("agent.crystal" in et for et in event_types), f"No crystal events. Types: {event_types}"

    # Specific crystal event types
    assert any("agent.crystal.reduction_receipt" == et for et in event_types), \
        f"No crystal.reduction_receipt. Types: {event_types}"
    assert any("agent.worktree.applied" == et for et in event_types), \
        f"No worktree.applied. Types: {event_types}"

    # Verify the applied event contains file information
    applied_events = [e for e in events if e.get("event_type") == "agent.worktree.applied"]
    for ev in applied_events:
        payload = ev.get("payload", {})
        assert "files" in payload or "applied" in payload, f"Applied event missing files info: {payload}"

    # Verify the crystal reduction receipt contains promotion info
    reduction_events = [e for e in events if e.get("event_type") == "agent.crystal.reduction_receipt"]
    for ev in reduction_events:
        payload = ev.get("payload", {})
        assert payload.get("credited") is True, f"Crystal not credited: {payload}"
        assert payload.get("units", 0) > 0, f"No units credited: {payload}"

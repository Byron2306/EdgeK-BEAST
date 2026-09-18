from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path

from app.kernel.agents.planner_provider import ScriptedPlannerProvider
from app.kernel.agents.planner_runtime import AgentPlannerRuntime
from app.kernel.agents.run_engine import AgentRunEngine
from app.kernel.data_processing.code_cortex import CodeCortexRouter, LocalCodeCortexAdapter
from app.kernel.data_processing.context_packet import ContextPacketBuilder


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True)


def _repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "beast@example.test")
    _git(root, "config", "user.name", "BEAST Recovery Phase 4")
    (root / "producer.py").write_text("VALUE = 1\n", encoding="utf-8")
    (root / "consumer.py").write_text(
        "from producer import VALUE\nRESULT = VALUE + 0\n",
        encoding="utf-8",
    )
    _git(root, "add", ".")
    _git(root, "commit", "-qm", "seed cross-file fixture")
    return root


def _builder() -> ContextPacketBuilder:
    return ContextPacketBuilder(
        code_cortex=CodeCortexRouter(adapters=[LocalCodeCortexAdapter()]),
        max_file_chars=240,
    )


def test_code_cortex_discovers_dependent_without_manual_attachment(tmp_path):
    root = _repo(tmp_path)
    engine = AgentRunEngine(root)
    run_id = engine.create_run(
        session_id="recovery-phase4-discovery",
        objective="Change producer VALUE to 2 and update its dependent consumer RESULT to VALUE + 1.",
        mode="agent",
        provider="simulated",
        model="phase4-test",
        request={
            # Deliberately only one operator-supplied file.
            "context_files": ["producer.py"],
            "semantic_context": {
                "active_file": "producer.py",
                "open_files": ["producer.py"],
            },
        },
    )["run_id"]
    approval_id = "phase4-cross-file-mutation"
    engine.store.create_approval(
        run_id,
        {"request_id": approval_id, "capabilities": [{"id": "worktree_mutation"}]},
    )
    engine.store.resolve_approval(
        run_id,
        approval_id,
        {"approved": True, "scope": "run"},
    )

    provider = ScriptedPlannerProvider([
        {
            "decision_type": "tool",
            "tool_id": "worktree.bind",
            "approval_id": approval_id,
            "arguments": {
                "objective": "Update producer and discovered dependent consumer",
                "provider": "simulated",
                "risk": "high",
            },
        },
        # Recovery Phase 4 guard consumes this turn by forcing the
        # discovered direct dependent to be read first.
        {
            "decision_type": "tool",
            "tool_id": "workspace.read_range",
            "arguments": {"path": "producer.py", "start_line": 1, "line_count": 40},
        },
        # This first producer mutation proposal is consumed by the exact-source
        # guard, which reads producer.py before permitting mutation.
        {
            "decision_type": "tool",
            "tool_id": "worktree.replace_exact",
            "approval_id": approval_id,
            "arguments": {
                "path": "producer.py",
                "old_text": "VALUE = 1",
                "new_text": "VALUE = 2",
            },
        },
        # Now the same bounded producer mutation can execute.
        {
            "decision_type": "tool",
            "tool_id": "worktree.replace_exact",
            "approval_id": approval_id,
            "arguments": {
                "path": "producer.py",
                "old_text": "VALUE = 1",
                "new_text": "VALUE = 2",
            },
        },
        {
            "decision_type": "tool",
            "tool_id": "worktree.replace_exact",
            "approval_id": approval_id,
            "arguments": {
                "path": "consumer.py",
                "old_text": "RESULT = VALUE + 0",
                "new_text": "RESULT = VALUE + 1",
            },
        },
        {
            "decision_type": "tool",
            "tool_id": "worktree.verify",
            "approval_id": approval_id,
            "arguments": {"command": ["python", "-m", "py_compile", "producer.py", "consumer.py"]},
        },
        {
            "decision_type": "tool",
            "tool_id": "worktree.sourceplan_draft",
            "arguments": {},
        },
        {
            "decision_type": "complete",
            "summary": "Cross-file change discovered, verified, and handed off.",
        },
    ])

    final = asyncio.run(
        AgentPlannerRuntime(
            engine,
            provider,
            max_turns=10,
            observation_limit=30,
            context_packet_builder=_builder(),
        ).run(run_id)
    )

    assert final["state"] == "completed"
    checkpoint = final["checkpoint"]
    discovery = checkpoint["repository_discovery"]

    assert discovery["canonical_owner"] == "code_cortex"
    assert discovery["authority"] == "advisory_discovery_only"
    assert discovery["mutation_authority"] is False
    assert discovery["hint_paths"] == ["producer.py"]
    assert "consumer.py" in discovery["discovered_paths"]
    assert discovery["required_evidence_paths"] == ["consumer.py"]
    assert discovery["required_evidence_policy"]["authority"] == "inspection_required_only"
    assert discovery["required_evidence_policy"]["mutation_authority"] is False
    assert "dependent_of:producer.py" in discovery["path_reasons"]["consumer.py"]
    assert discovery["sensorium_world_state"]["authority"] == "observation_only"
    assert discovery["sensorium_world_state"]["admitted"] is True, discovery["sensorium_world_state"]

    planner = checkpoint["planner"]
    observations = planner["observations"]
    discovery_observation = next(item for item in observations if item["tool_id"] == "code_cortex.discover")
    consumer_read = next(
        item for item in observations
        if item["tool_id"] == "workspace.read_range"
        and item.get("result", {}).get("path") == "consumer.py"
    )
    producer_read = next(
        item for item in observations
        if item["tool_id"] == "workspace.read_range"
        and item.get("result", {}).get("path") == "producer.py"
    )
    consumer_mutation = next(
        item for item in observations
        if item["tool_id"] == "worktree.replace_exact"
        and item.get("result", {}).get("path") == "consumer.py"
    )
    producer_mutation = next(
        item for item in observations
        if item["tool_id"] == "worktree.replace_exact"
        and item.get("result", {}).get("path") == "producer.py"
    )
    verification = next(
        item for item in observations
        if item["tool_id"] == "worktree.verify"
        and item.get("status") == "completed"
    )
    assert observations.index(discovery_observation) < observations.index(consumer_read)
    assert observations.index(producer_read) < observations.index(producer_mutation)
    assert observations.index(consumer_read) < observations.index(consumer_mutation)
    assert observations.index(producer_mutation) < observations.index(verification)
    assert observations.index(consumer_mutation) < observations.index(verification)

    worktree = Path(checkpoint["worktree_root"])
    assert (root / "producer.py").read_text(encoding="utf-8") == "VALUE = 1\n"
    assert (root / "consumer.py").read_text(encoding="utf-8") == "from producer import VALUE\nRESULT = VALUE + 0\n"
    assert (worktree / "producer.py").read_text(encoding="utf-8") == "VALUE = 2\n"
    assert (worktree / "consumer.py").read_text(encoding="utf-8") == "from producer import VALUE\nRESULT = VALUE + 1\n"
    assert checkpoint["sourceplan"]["plan_id"]

    events = engine.store.events(run_id, limit=500)
    repository_events = [event for event in events if event["event_type"] == "agent.repository.discovery"]
    assert repository_events
    assert repository_events[-1]["payload"]["discovered_paths"] == discovery["discovered_paths"]
    assert engine.store.verify_chain(run_id)["head_matches"] is True


def test_discovered_file_requires_exact_read_before_replace(tmp_path):
    root = _repo(tmp_path)
    engine = AgentRunEngine(root)
    run_id = engine.create_run(
        session_id="recovery-phase4-read-boundary",
        objective="Update producer and dependent consumer.",
        mode="agent",
        provider="simulated",
        model="phase4-test",
        request={
            "context_files": ["producer.py"],
            "semantic_context": {"active_file": "producer.py"},
        },
    )["run_id"]
    state = AgentPlannerRuntime(
        engine,
        ScriptedPlannerProvider([]),
        context_packet_builder=_builder(),
    )._load_state(run_id)
    run = engine.store.get_run(run_id) or {}
    runtime = AgentPlannerRuntime(engine, ScriptedPlannerProvider([]), context_packet_builder=_builder())
    state = runtime._admit_repository_discovery(run, state)

    state.observations.extend([
        {
            "tool_id": "worktree.bind",
            "status": "completed",
            "result": {"worktree_root": str(root / ".beast-worktree")},
        },
        {
            "tool_id": "workspace.read_range",
            "status": "completed",
            "result": {"path": "producer.py", "content": "VALUE = 1\n"},
        },
    ])
    from app.kernel.agents.planner_models import PlannerDecision, PlannerDecisionType

    attempted = PlannerDecision(
        decision_type=PlannerDecisionType.TOOL,
        tool_id="worktree.replace_exact",
        arguments={
            "path": "consumer.py",
            "old_text": "RESULT = VALUE + 0",
            "new_text": "RESULT = VALUE + 1",
        },
    )
    required = AgentPlannerRuntime._required_phase_decision(run, state, attempted)
    assert required is not None
    assert required.tool_id == "workspace.read_range"
    assert required.arguments["path"] == "consumer.py"


def test_cross_file_direct_dependency_must_be_exact_read_before_verification(tmp_path):
    root = _repo(tmp_path)
    engine = AgentRunEngine(root)
    run_id = engine.create_run(
        session_id="recovery-phase4-required-evidence",
        objective="Cross-file task: update producer and its dependent consumer, then verify.",
        mode="agent",
        provider="simulated",
        model="phase4-test",
        request={
            "context_files": ["producer.py"],
            "semantic_context": {"active_file": "producer.py"},
        },
    )["run_id"]
    runtime = AgentPlannerRuntime(
        engine,
        ScriptedPlannerProvider([]),
        context_packet_builder=_builder(),
    )
    run = engine.store.get_run(run_id) or {}
    state = runtime._admit_repository_discovery(run, runtime._load_state(run_id))

    state.observations.extend([
        {
            "tool_id": "worktree.bind",
            "status": "completed",
            "result": {"worktree_root": str(root / ".beast-worktree")},
        },
        {
            "tool_id": "workspace.read_range",
            "status": "completed",
            "result": {"path": "producer.py", "content": "VALUE = 1\n"},
        },
        {
            "tool_id": "worktree.replace_exact",
            "status": "completed",
            "result": {"path": "producer.py"},
            "arguments": {
                "path": "producer.py",
                "old_text": "VALUE = 1",
                "new_text": "VALUE = 2",
            },
        },
    ])

    from app.kernel.agents.planner_models import PlannerDecision, PlannerDecisionType

    attempted_verify = PlannerDecision(
        decision_type=PlannerDecisionType.TOOL,
        tool_id="worktree.verify",
        arguments={"command": ["python", "-m", "py_compile", "producer.py"]},
    )
    required = AgentPlannerRuntime._required_phase_decision(run, state, attempted_verify)
    assert required is not None
    assert required.tool_id == "workspace.read_range"
    assert required.arguments["path"] == "consumer.py"
    assert "exact inspection" in required.rationale


def test_retry_recovery_allows_scoped_unread_path_then_forces_exact_read(tmp_path):
    root = _repo(tmp_path)
    engine = AgentRunEngine(root)
    run_id = engine.create_run(
        session_id="recovery-phase4-retry-scope",
        objective="Cross-file task: update producer and its dependent consumer.",
        mode="agent",
        provider="ollama",
        model="qwen2.5:0.5b",
        request={
            "context_files": ["producer.py"],
            "semantic_context": {"active_file": "producer.py"},
        },
    )["run_id"]
    runtime = AgentPlannerRuntime(
        engine,
        ScriptedPlannerProvider([]),
        context_packet_builder=_builder(),
    )
    run = engine.store.get_run(run_id) or {}
    state = runtime._admit_repository_discovery(run, runtime._load_state(run_id))
    state.observations.extend([
        {
            "tool_id": "worktree.bind",
            "status": "completed",
            "result": {"worktree_root": str(root / ".beast-worktree")},
        },
        {
            "tool_id": "workspace.read_range",
            "status": "completed",
            "result": {
                "path": "consumer.py",
                "content": "from producer import VALUE\nRESULT = VALUE + 0\n",
            },
        },
    ])

    from app.kernel.agents.planner_models import PlannerDecision, PlannerDecisionType

    repaired = PlannerDecision(
        decision_type=PlannerDecisionType.TOOL,
        tool_id="worktree.replace_exact",
        arguments={
            "path": "producer.py",
            "old_text": "VALUE = 1",
            "new_text": "VALUE = 2",
        },
    )
    assert AgentPlannerRuntime._invalid_retry_recovery_reason(repaired, state, run) == ""

    required = AgentPlannerRuntime._required_phase_decision(run, state, repaired)
    assert required is not None
    assert required.tool_id == "workspace.read_range"
    assert required.arguments["path"] == "producer.py"
    assert "exact source bytes" in required.rationale

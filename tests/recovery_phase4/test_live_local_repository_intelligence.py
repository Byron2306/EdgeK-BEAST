"""Recovery Phase 4 live local-model repository-intelligence acceptance."""

from __future__ import annotations

import asyncio
import os
import subprocess
from pathlib import Path

import pytest

from app.kernel.agents.ollama_planner_provider import OllamaPlannerProvider
from app.kernel.agents.planner_runtime import AgentPlannerRuntime
from app.kernel.agents.run_engine import AgentRunEngine
from app.kernel.data_processing.code_cortex import CodeCortexRouter, LocalCodeCortexAdapter
from app.kernel.data_processing.context_packet import ContextPacketBuilder


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True)


@pytest.mark.skipif(
    os.environ.get("BEAST_RECOVERY_PHASE4_LIVE_OLLAMA") != "1",
    reason="Recovery Phase 4 live Ollama opt-in",
)
def test_real_local_model_consumes_discovered_cross_file_evidence_without_manual_attachment(tmp_path):
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
    _git(root, "commit", "-qm", "seed recovery phase4 cross-file fixture")

    model = os.environ.get("BEAST_RECOVERY_PHASE4_MODEL", "qwen2.5:0.5b")
    engine = AgentRunEngine(root)
    run_id = engine.create_run(
        session_id="recovery-phase4-live",
        objective=(
            "Cross-file task. Change producer.py exactly from VALUE = 1 to VALUE = 2. "
            "A dependent file exists but is NOT manually attached. Use BEAST repository discovery "
            "to find it, read its exact bytes, and update RESULT = VALUE + 0 to RESULT = VALUE + 1. "
            "Both files must be changed before verification. Use only the governed isolated worktree, "
            "then verify, create SourcePlan, and complete."
        ),
        mode="agent",
        provider="ollama",
        model=model,
        request={
            # Deliberately only one operator-supplied file. consumer.py must
            # enter scope through Code Cortex evidence.
            "context_files": ["producer.py"],
            "semantic_context": {
                "active_file": "producer.py",
                "open_files": ["producer.py"],
            },
        },
    )["run_id"]

    approval_id = "recovery-phase4-live-mutation"
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

    builder = ContextPacketBuilder(
        code_cortex=CodeCortexRouter(adapters=[LocalCodeCortexAdapter()]),
        max_file_chars=320,
    )
    streamed: list[str] = []
    provider = OllamaPlannerProvider(
        model=model,
        timeout_seconds=180,
        max_retries=2,
        default_approval_id=approval_id,
        on_token=streamed.append,
    )
    final = asyncio.run(
        AgentPlannerRuntime(
            engine,
            provider,
            max_turns=18,
            observation_limit=40,
            max_repair_cycles=4,
            context_packet_builder=builder,
        ).run(run_id)
    )

    assert final["state"] == "completed", final
    checkpoint = final["checkpoint"]
    discovery = checkpoint["repository_discovery"]
    assert discovery["canonical_owner"] == "code_cortex"
    assert discovery["mutation_authority"] is False
    assert discovery["hint_paths"] == ["producer.py"]
    assert "consumer.py" in discovery["discovered_paths"]
    assert "dependent_of:producer.py" in discovery["path_reasons"]["consumer.py"]
    assert discovery["sensorium_world_state"]["admitted"] is True, discovery["sensorium_world_state"]
    assert discovery["sensorium_world_state"]["authority"] == "observation_only"

    observations = checkpoint["planner"]["observations"]
    discovery_index = next(
        index for index, item in enumerate(observations)
        if item.get("tool_id") == "code_cortex.discover"
    )
    consumer_read_index = next(
        index for index, item in enumerate(observations)
        if item.get("tool_id") == "workspace.read_range"
        and (item.get("result") or {}).get("path") == "consumer.py"
    )
    consumer_mutation_index = next(
        index for index, item in enumerate(observations)
        if item.get("tool_id") == "worktree.replace_exact"
        and (item.get("result") or {}).get("path") == "consumer.py"
    )
    assert discovery_index < consumer_read_index < consumer_mutation_index

    worktree = Path(checkpoint["worktree_root"])
    assert worktree != root
    assert (root / "producer.py").read_text(encoding="utf-8") == "VALUE = 1\n"
    assert (root / "consumer.py").read_text(encoding="utf-8") == (
        "from producer import VALUE\nRESULT = VALUE + 0\n"
    )
    assert (worktree / "producer.py").read_text(encoding="utf-8") == "VALUE = 2\n"
    assert (worktree / "consumer.py").read_text(encoding="utf-8") == (
        "from producer import VALUE\nRESULT = VALUE + 1\n"
    )
    assert checkpoint.get("sourceplan", {}).get("plan_id")
    assert streamed

    events = engine.store.events(run_id, limit=1200)
    event_types = [event["event_type"] for event in events]
    assert "agent.repository.discovery" in event_types
    assert "agent.verification.passed" in event_types
    assert "agent.sourceplan.ready" in event_types
    assert "agent.planner.completed" in event_types

    chain = engine.store.verify_chain(run_id)
    assert chain["ok"] is True
    assert chain["head_matches"] is True

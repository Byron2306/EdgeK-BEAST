"""Recovery Phase 3 live local-model mutation acceptance."""

from __future__ import annotations

import asyncio
import os
import subprocess
from pathlib import Path

import pytest

from app.kernel.agents.ollama_planner_provider import OllamaPlannerProvider
from app.kernel.agents.planner_runtime import AgentPlannerRuntime
from app.kernel.agents.run_engine import AgentRunEngine


@pytest.mark.skipif(
    os.environ.get("BEAST_RECOVERY_PHASE3_LIVE_OLLAMA") != "1",
    reason="Recovery Phase 3 live Ollama opt-in",
)
def test_real_local_model_completes_governed_simple_mutation_with_truthful_telemetry(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "beast@example.test"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "BEAST Recovery Phase 3"], cwd=root, check=True)
    (root / "answer.py").write_text("VALUE = 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    subprocess.run(["git", "commit", "-qm", "seed simple mutation"], cwd=root, check=True)

    model = os.environ.get("BEAST_RECOVERY_PHASE3_MODEL", "qwen2.5:0.5b")
    engine = AgentRunEngine(root)
    run_id = engine.create_run(
        session_id="recovery-phase3-live",
        objective=(
            "In answer.py change exactly VALUE = 1 to VALUE = 2 and nothing else. "
            "Use the governed lifecycle: inspect, isolated worktree, exact replacement, "
            "verification, SourcePlan, then complete."
        ),
        mode="agent",
        provider="ollama",
        model=model,
        request={
            "context_files": ["answer.py"],
            "semantic_context": {
                "active_file": "answer.py",
                "open_files": ["answer.py"],
            },
        },
    )["run_id"]

    approval_id = "recovery-phase3-mutation"
    engine.store.create_approval(
        run_id,
        {
            "request_id": approval_id,
            "capabilities": [
                {"id": "worktree_mutation", "paths": ["answer.py"]},
            ],
        },
    )
    engine.store.resolve_approval(
        run_id,
        approval_id,
        {"approved": True, "scope": "run"},
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
            max_turns=12,
            observation_limit=30,
            max_repair_cycles=3,
        ).run(run_id)
    )

    assert final["state"] == "completed", final
    checkpoint = final["checkpoint"]
    worktree_root = Path(checkpoint["worktree_root"])
    assert worktree_root != root
    assert (root / "answer.py").read_text(encoding="utf-8") == "VALUE = 1\n"
    assert (worktree_root / "answer.py").read_text(encoding="utf-8") == "VALUE = 2\n"
    assert checkpoint.get("sourceplan", {}).get("plan_id")
    assert streamed

    events = engine.store.events(run_id, limit=1000)
    event_types = [event["event_type"] for event in events]
    assert "agent.verification.passed" in event_types
    assert "agent.sourceplan.ready" in event_types
    assert "agent.planner.completed" in event_types

    usage_events = [
        event["payload"]
        for event in events
        if event["event_type"] == "agent.model.usage"
    ]
    assert usage_events
    truthful = [
        payload for payload in usage_events
        if payload.get("num_ctx") is not None and payload.get("num_predict") is not None
    ]
    assert truthful, usage_events
    assert all(int(payload["num_ctx"]) == 2048 for payload in truthful)
    assert all(int(payload["num_predict"]) == 128 for payload in truthful)
    assert any(int(payload.get("completion_eval_count") or 0) > 0 for payload in truthful)

    chain = engine.store.verify_chain(run_id)
    assert chain["ok"] is True
    assert chain["head_matches"] is True

"""Recovery Phase 4 live local-model repository discovery acceptance."""

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
    os.environ.get("BEAST_RECOVERY_PHASE4_LIVE_OLLAMA") != "1",
    reason="Recovery Phase 4 live Ollama opt-in",
)
def test_real_local_model_discovers_cross_file_context_without_attachments_then_repairs_source(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "beast@example.test"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "BEAST Recovery Phase 4"], cwd=root, check=True)

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
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    subprocess.run(["git", "commit", "-qm", "seed cross-file pricing repository"], cwd=root, check=True)

    model = os.environ.get("BEAST_RECOVERY_PHASE4_MODEL", "qwen2.5:0.5b")
    engine = AgentRunEngine(root)
    run_id = engine.create_run(
        session_id="recovery-phase4-live",
        objective=(
            "Find the definition of calculate_total in this repository and repair it. "
            "Change exactly 'return subtotal' to 'return subtotal - discount' in the defining source file. "
            "Do not edit checkout.py. Discover relevant repository evidence first, use an isolated worktree, "
            "verify, produce SourcePlan, then complete."
        ),
        mode="agent",
        provider="ollama",
        model=model,
        # Deliberately no context_files, active_file, selected_file or target_file.
        request={},
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
    observations = final["checkpoint"]["planner"]["observations"]
    assert observations[0]["tool_id"] == "workspace.discover_context"
    perception = observations[0]["result"]
    assert perception["authority"] == "advisory_discovery_only"
    assert perception["exact_source_required_before_mutation"] is True
    assert perception["code_cortex"]["owner"] == "Code Cortex"
    assert "pricing.py" in perception["candidate_paths"], perception
    assert "checkout.py" in perception["candidate_paths"], perception
    assert any(
        row.get("source_path") == "pricing.py" and row.get("path") == "checkout.py"
        for row in perception.get("dependents", [])
    ), perception

    exact_reads = [
        item["result"]["path"]
        for item in observations
        if item.get("tool_id") == "workspace.read_range"
        and item.get("status") == "completed"
    ]
    assert "pricing.py" in exact_reads

    changed = [
        item["result"]["path"]
        for item in observations
        if item.get("tool_id") in {"worktree.replace_exact", "worktree.write_file"}
        and item.get("status") == "completed"
    ]
    assert changed == ["pricing.py"], changed

    worktree_root = Path(final["checkpoint"]["worktree_root"])
    assert (root / "pricing.py").read_text(encoding="utf-8") == (
        "def calculate_total(subtotal, discount):\n"
        "    return subtotal\n"
    )
    assert (worktree_root / "pricing.py").read_text(encoding="utf-8") == (
        "def calculate_total(subtotal, discount):\n"
        "    return subtotal - discount\n"
    )
    assert (root / "checkout.py").read_text(encoding="utf-8") == (
        "from pricing import calculate_total\n\n"
        "def checkout(subtotal, discount):\n"
        "    return calculate_total(subtotal, discount)\n"
    )
    assert final["checkpoint"].get("sourceplan", {}).get("plan_id")
    assert streamed

    events = engine.store.events(run_id, limit=1000)
    event_types = [event["event_type"] for event in events]
    assert "agent.verification.passed" in event_types
    assert "agent.sourceplan.ready" in event_types
    assert "agent.planner.completed" in event_types

    usage = [
        event["payload"]
        for event in events
        if event["event_type"] == "agent.model.usage"
    ]
    assert usage
    assert any(int(row.get("completion_eval_count") or 0) > 0 for row in usage)
    assert any(int(row.get("num_ctx") or 0) == 2048 for row in usage)
    assert any(int(row.get("num_predict") or 0) == 128 for row in usage)

    chain = engine.store.verify_chain(run_id)
    assert chain["ok"] is True
    assert chain["head_matches"] is True

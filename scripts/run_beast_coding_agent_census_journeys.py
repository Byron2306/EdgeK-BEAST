#!/usr/bin/env python3
"""Run evidence-producing Phase 0 coding-agent journeys through production backend code.

These journeys deliberately use ScriptedPlannerProvider so they prove the
AgentRun/planner/tool backend lifecycle without making any claim that the
renderer, Ollama/NIM, or Sensorium mirror participated.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
import subprocess
import tempfile
from typing import Any

from app.kernel.agents.planner_provider import ScriptedPlannerProvider
from app.kernel.agents.planner_runtime import AgentPlannerRuntime
from app.kernel.agents.run_engine import AgentRunEngine
from scripts.trace_beast_coding_agent_runtime import trace_records_from_agent_run_events

EVIDENCE_CLASS = "observed_production_backend_scripted_provider"


def _init_repo(root: Path, files: dict[str, str]) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "beast-phase0@example.test"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "BEAST Phase 0"], cwd=root, check=True)
    for relative, content in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    subprocess.run(["git", "commit", "-qm", "phase0 fixture"], cwd=root, check=True)
    return root


def _approve(engine: AgentRunEngine, run_id: str, approval_id: str = "phase0-mutation") -> str:
    engine.store.create_approval(
        run_id,
        {"request_id": approval_id, "capabilities": [{"id": "worktree_mutation"}]},
    )
    engine.store.resolve_approval(
        run_id,
        approval_id,
        {"approved": True, "scope": "run", "phase0_census": True},
    )
    return approval_id


def _tool_observations(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    observations: list[dict[str, Any]] = []
    for event in events:
        if str(event.get("event_type") or "") not in {"agent.tool.completed", "agent.tool.failed"}:
            continue
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        observation = payload.get("observation") if isinstance(payload.get("observation"), dict) else {}
        if observation:
            observations.append(
                {
                    "observation_id": str(observation.get("observation_id") or ""),
                    "tool_id": str(observation.get("tool_id") or ""),
                    "status": str(observation.get("status") or ""),
                    "error": str(observation.get("error") or ""),
                    "evidence_digest": str(observation.get("evidence_digest") or ""),
                    "duration_ms": observation.get("duration_ms"),
                }
            )
    return observations


def _read_final_source(final: dict[str, Any], workspace_root: Path, paths: list[str]) -> dict[str, str]:
    checkpoint = final.get("checkpoint") if isinstance(final.get("checkpoint"), dict) else {}
    worktree_root = str(checkpoint.get("worktree_root") or "").strip()
    root = Path(worktree_root).resolve() if worktree_root else workspace_root.resolve()
    result: dict[str, str] = {}
    for relative in paths:
        path = root / relative
        if path.exists():
            result[relative] = path.read_text(encoding="utf-8")
    return result


def _finalize_journey(
    journey_id: str,
    engine: AgentRunEngine,
    run_id: str,
    final: dict[str, Any],
    *,
    source_paths: list[str],
) -> dict[str, Any]:
    events = engine.store.events(run_id, after=0, limit=10000)
    chain = engine.store.verify_chain(run_id)
    traces = trace_records_from_agent_run_events(events, request_id=f"phase0:{journey_id}")
    return {
        "journey_id": journey_id,
        "evidence_class": EVIDENCE_CLASS,
        "run_id": run_id,
        "final_state": str(final.get("state") or ""),
        "chain_verification": chain,
        "event_count": len(events),
        "event_types": [str(event.get("event_type") or "") for event in events],
        "tool_observations": _tool_observations(events),
        "trace_records": traces,
        "final_source": _read_final_source(final, engine.workspace_root, source_paths),
        "proof_boundaries": {
            "production_backend_classes": True,
            "scripted_provider": True,
            "desktop_renderer_ingress": False,
            "real_ollama_or_nim_provider": False,
            "sensorium_mirror_receipt": False,
        },
    }


def run_analysis_journey(root: Path) -> dict[str, Any]:
    root.mkdir(parents=True, exist_ok=True)
    (root / "sample.py").write_text("def answer():\n    return 42\n", encoding="utf-8")
    engine = AgentRunEngine(root)
    run_id = engine.create_run(
        session_id="phase0-analysis",
        objective="Find the answer function and report what it returns",
        mode="analysis",
        provider="simulated",
        model="phase0-scripted",
    )["run_id"]
    provider = ScriptedPlannerProvider(
        [
            {"decision_type": "tool", "tool_id": "workspace.search_text", "arguments": {"query": "def answer", "path": "."}},
            {"decision_type": "tool", "tool_id": "workspace.read_range", "arguments": {"path": "sample.py", "start_line": 1, "line_count": 10}},
            {"decision_type": "complete", "summary": "sample.py defines answer() and returns 42."},
        ]
    )
    final = asyncio.run(AgentPlannerRuntime(engine, provider, max_turns=5).run(run_id))
    return _finalize_journey("analysis_only", engine, run_id, final, source_paths=["sample.py"])


def run_single_file_mutation_journey(root: Path) -> dict[str, Any]:
    _init_repo(root, {"answer.py": "VALUE = 1\n"})
    engine = AgentRunEngine(root)
    run_id = engine.create_run(
        session_id="phase0-single-mutation",
        objective="Change VALUE to 2 and verify it",
        mode="agent",
        provider="simulated",
        model="phase0-scripted",
        request={"context_files": ["answer.py"]},
    )["run_id"]
    approval_id = _approve(engine, run_id)
    provider = ScriptedPlannerProvider(
        [
            {"decision_type": "tool", "tool_id": "workspace.index", "arguments": {"limit": 1200, "include_symbols": True}},
            {"decision_type": "tool", "tool_id": "worktree.bind", "approval_id": approval_id, "arguments": {"objective": "Change VALUE to 2 and verify it", "provider": "simulated", "risk": "high"}},
            {"decision_type": "tool", "tool_id": "workspace.read_range", "arguments": {"path": "answer.py", "start_line": 1, "line_count": 40}},
            {"decision_type": "tool", "tool_id": "worktree.replace_exact", "approval_id": approval_id, "arguments": {"path": "answer.py", "old_text": "VALUE = 1", "new_text": "VALUE = 2"}},
            {"decision_type": "tool", "tool_id": "worktree.verify", "approval_id": approval_id, "arguments": {"command": ["python", "-m", "py_compile", "answer.py"]}},
            {"decision_type": "tool", "tool_id": "worktree.sourceplan_draft", "arguments": {}},
        ]
    )
    final = asyncio.run(AgentPlannerRuntime(engine, provider, max_turns=6).run(run_id))
    return _finalize_journey("single_file_mutation", engine, run_id, final, source_paths=["answer.py"])


def run_cross_file_mutation_journey(root: Path) -> dict[str, Any]:
    _init_repo(
        root,
        {
            "values.py": "VALUE = 1\n",
            "consumer.py": "from values import VALUE\nRESULT = VALUE\n",
        },
    )
    engine = AgentRunEngine(root)
    run_id = engine.create_run(
        session_id="phase0-cross-file",
        objective="Change VALUE to 2 and make consumer RESULT equal VALUE plus one, then verify both files",
        mode="agent",
        provider="simulated",
        model="phase0-scripted",
        request={"context_files": ["values.py", "consumer.py"]},
    )["run_id"]
    approval_id = _approve(engine, run_id, "phase0-cross-mutation")
    provider = ScriptedPlannerProvider(
        [
            {"decision_type": "tool", "tool_id": "workspace.index", "arguments": {"limit": 1200, "include_symbols": True}},
            {"decision_type": "tool", "tool_id": "worktree.bind", "approval_id": approval_id, "arguments": {"objective": "Cross-file mutation census", "provider": "simulated", "risk": "high"}},
            {"decision_type": "tool", "tool_id": "workspace.read_range", "arguments": {"path": "values.py", "start_line": 1, "line_count": 20}},
            {"decision_type": "tool", "tool_id": "workspace.read_range", "arguments": {"path": "consumer.py", "start_line": 1, "line_count": 20}},
            {"decision_type": "tool", "tool_id": "worktree.replace_exact", "approval_id": approval_id, "arguments": {"path": "values.py", "old_text": "VALUE = 1", "new_text": "VALUE = 2"}},
            {"decision_type": "tool", "tool_id": "worktree.replace_exact", "approval_id": approval_id, "arguments": {"path": "consumer.py", "old_text": "RESULT = VALUE", "new_text": "RESULT = VALUE + 1"}},
            {"decision_type": "tool", "tool_id": "worktree.verify", "approval_id": approval_id, "arguments": {"command": ["python", "-m", "py_compile", "values.py", "consumer.py"]}},
            {"decision_type": "tool", "tool_id": "worktree.sourceplan_draft", "arguments": {}},
        ]
    )
    final = asyncio.run(AgentPlannerRuntime(engine, provider, max_turns=8).run(run_id))
    journey = _finalize_journey(
        "cross_file_mutation",
        engine,
        run_id,
        final,
        source_paths=["values.py", "consumer.py"],
    )
    expected_source = {
        "values.py": "VALUE = 2\n",
        "consumer.py": "from values import VALUE\nRESULT = VALUE + 1\n",
    }
    unresolved = [
        path for path, expected in expected_source.items()
        if journey["final_source"].get(path) != expected
    ]
    journey["objective_assessment"] = {
        "satisfied": not unresolved,
        "unresolved_paths": unresolved,
        "finding": "" if not unresolved else "completed_with_unresolved_cross_file_objective",
        "assessment_basis": "exact_final_source_comparison",
        "expected_source": expected_source,
    }
    return journey


def run_failed_verification_repair_journey(root: Path) -> dict[str, Any]:
    _init_repo(root, {"answer.py": "VALUE = 1\n"})
    engine = AgentRunEngine(root)
    run_id = engine.create_run(
        session_id="phase0-repair",
        objective="Set VALUE to 2, detect an incorrect first edit, repair it, and verify",
        mode="agent",
        provider="simulated",
        model="phase0-scripted",
        request={"context_files": ["answer.py"]},
    )["run_id"]
    approval_id = _approve(engine, run_id, "phase0-repair-mutation")
    check = ["python", "-c", "import answer; assert answer.VALUE == 2"]
    provider = ScriptedPlannerProvider(
        [
            {"decision_type": "tool", "tool_id": "workspace.index", "arguments": {"limit": 1200, "include_symbols": True}},
            {"decision_type": "tool", "tool_id": "worktree.bind", "approval_id": approval_id, "arguments": {"objective": "Repair census", "provider": "simulated", "risk": "high"}},
            {"decision_type": "tool", "tool_id": "workspace.read_range", "arguments": {"path": "answer.py", "start_line": 1, "line_count": 20}},
            {"decision_type": "tool", "tool_id": "worktree.replace_exact", "approval_id": approval_id, "arguments": {"path": "answer.py", "old_text": "VALUE = 1", "new_text": "VALUE = 3"}},
            {"decision_type": "tool", "tool_id": "worktree.verify", "approval_id": approval_id, "arguments": {"command": check}},
            {"decision_type": "tool", "tool_id": "worktree.replace_exact", "approval_id": approval_id, "arguments": {"path": "answer.py", "old_text": "VALUE = 3", "new_text": "VALUE = 2"}},
            {"decision_type": "tool", "tool_id": "worktree.verify", "approval_id": approval_id, "arguments": {"command": check}},
            {"decision_type": "tool", "tool_id": "worktree.sourceplan_draft", "arguments": {}},
        ]
    )
    final = asyncio.run(
        AgentPlannerRuntime(engine, provider, max_turns=8, max_repair_cycles=3).run(run_id)
    )
    return _finalize_journey("verification_failure_repair", engine, run_id, final, source_paths=["answer.py"])


def render_runtime_map(journeys: list[dict[str, Any]]) -> str:
    observed_components = sorted(
        {
            str(record.get("component_path") or "")
            for journey in journeys
            for record in journey.get("trace_records") or []
            if record.get("component_path")
        }
    )
    gaps = [
        journey.get("objective_assessment")
        for journey in journeys
        if isinstance(journey.get("objective_assessment"), dict)
        and journey["objective_assessment"].get("satisfied") is False
    ]
    lines = [
        "# BEAST Coding Agent Runtime Map",
        "",
        "## Evidence boundary",
        "",
        "### Observed production backend path (scripted provider)",
        "",
        "These journeys execute the real `AgentRunEngine`, `AgentPlannerRuntime`, typed tool runtime, worktree lifecycle and durable AgentRun ledger. The model-decision source is deliberately scripted so this evidence proves backend composition and lifecycle behavior without pretending to prove a real model/provider or desktop ingress.",
        "",
        "- Desktop renderer / Pair Programmer ingress: **not proven by this harness**",
        "- Real Ollama/NIM provider execution: **not proven by this harness**",
        "- Sensorium mirror receipt: **not proven by AgentRun ledger events alone**",
        "",
        "## Observed component producers",
        "",
    ]
    for component in observed_components:
        lines.append(f"- `{component}`")
    lines.extend(
        [
            "",
            "## Journey results",
            "",
            "| Journey | Final state | Durable events | Tool observations |",
            "|---|---|---:|---:|",
        ]
    )
    for journey in journeys:
        lines.append(
            f"| `{journey['journey_id']}` | `{journey['final_state']}` | "
            f"{journey['event_count']} | {len(journey.get('tool_observations') or [])} |"
        )
    if gaps:
        lines.extend(["", "## Observed gaps", ""])
        for gap in gaps:
            lines.append(
                f"- `{gap.get('finding')}`: unresolved paths "
                f"{', '.join(f'`{path}`' for path in gap.get('unresolved_paths') or [])}."
            )
        lines.extend(
            [
                "",
                "The cross-file finding is an observation of current behavior, not a Phase 0 repair. The planner can satisfy its latest-mutation verification and SourcePlan guard while part of the original multi-file objective remains unresolved.",
            ]
        )
    lines.extend(
        [
            "",
            "## Observed backend route",
            "",
            "`AgentRunStore` → `AgentPlannerRuntime` → `AgentToolRuntime` → typed workspace/worktree tools → verification / SourcePlan → durable hash-chained AgentRun evidence.",
            "",
            "Sensorium mirroring is intentionally not promoted from these events because the current AgentRun engine treats that mirror as best-effort. A distinct Sensorium receipt is required before that edge becomes observed.",
            "",
        ]
    )
    return "\n".join(lines)


def run_all_journeys(root: Path) -> list[dict[str, Any]]:
    root.mkdir(parents=True, exist_ok=True)
    return [
        run_analysis_journey(root / "analysis"),
        run_single_file_mutation_journey(root / "single"),
        run_cross_file_mutation_journey(root / "cross"),
        run_failed_verification_repair_journey(root / "repair"),
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json-out", type=Path, required=True)
    parser.add_argument("--map-out", type=Path, required=True)
    args = parser.parse_args()

    with tempfile.TemporaryDirectory(prefix="beast-phase0-journeys-") as temporary:
        journeys = run_all_journeys(Path(temporary))
    bundle = {
        "beast_object_type": "beast_coding_agent_phase0_runtime_journeys",
        "version": "1.0",
        "evidence_class": EVIDENCE_CLASS,
        "journeys": journeys,
        "proof_boundaries": {
            "production_backend_classes": True,
            "scripted_provider": True,
            "desktop_renderer_ingress": False,
            "real_ollama_or_nim_provider": False,
            "sensorium_mirror_receipt": False,
        },
    }
    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.map_out.parent.mkdir(parents=True, exist_ok=True)
    args.json_out.write_text(json.dumps(bundle, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    args.map_out.write_text(render_runtime_map(journeys), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

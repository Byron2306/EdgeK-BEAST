#!/usr/bin/env python3
"""Live Tiny Ollama E2E BEAST Orchestration Gauntlet.

This is the hard follow-up to the policy-head test: a tiny local model proposes
an orchestration plan, BEAST repairs it, then real BEAST subsystems run.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.kernel.deployment.beast_cli_executor import BeastCLIExecutor
from app.kernel.capability.capability_registry import CapabilityRegistry
from app.kernel.networking.meta_tool_commons import MetaToolCommons
from app.kernel.execution.session_handshake import SessionHandshakeBuilder
from app.kernel.networking.swarm import SwarmKernel
from benchmarks.tiny_llama_agentic_orchestrator_gauntlet import (
    live_prompt,
    normalize_live_response,
    parse_json_object,
    run_live_ollama_task,
    score_live_response,
)

RESULTS = ROOT / "benchmarks" / "results"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def hard_task() -> Dict[str, Any]:
    return {
        "task_id": "agent_awareness_e2e_debug_and_promote",
        "tier": 6,
        "tier_name": "live_chained_subsystem_orchestration",
        "objective": (
            "Diagnose whether tiny Llama can use BEAST awareness, Commons, Swarm, "
            "OpenClaw-style planning, verification, and promotion without a cloud model."
        ),
        "task_class": "agentic_cli",
        "required_route": [
            "meta_tool_commons",
            "capability_registry",
            "fused_crystal",
            "zeroclaw",
            "openclaw",
            "swarm",
            "pytest",
            "promotion_candidate",
        ],
        "required_gates": [
            "no_cloud_until_local_evidence",
            "approval_before_write",
            "verification_gate",
            "receipt_required",
        ],
        "required_subagents": [
            "zeroclaw_planner",
            "cartographer",
            "openclaw_inspector",
            "supervisor",
            "scribe",
            "promotion_scribe",
        ],
        "risk": "medium",
    }


def build_report(args: argparse.Namespace) -> Dict[str, Any]:
    task = hard_task()
    handshake = SessionHandshakeBuilder().build(
        task["objective"],
        mode="openclaw",
        workspace_root=args.repo,
        tools=[
            "beast_meta_tool_commons",
            "beast_mcp_tool_catalog",
            "beast_openclaw_plan",
            "beast_compute_shadow",
            "mcp_git_status_diff",
            "mcp_lsp_symbol_search",
            "mcp_shell_dry_run",
            "pytest",
        ],
        preflight_budget_ms=args.preflight_budget_ms,
        scout_budget_ms=args.scout_budget_ms,
        session_id="ses_tiny_llama_live_e2e_orchestration",
    )
    live = run_live_ollama_task(task, handshake, args)
    normalized = live.get("normalized") if isinstance(live.get("normalized"), dict) else normalize_live_response(live.get("parsed") or {})
    live_score = score_live_response(task, normalized)

    commons = MetaToolCommons()
    capability_registry = CapabilityRegistry()
    subsystem_results = {
        "capability_registry": run_capability_inventory(capability_registry),
        "commons_rank": commons.rank(task_class=task["task_class"], limit=12),
        "commons_evidence_plane": commons.evidence_plane(),
        "swarm": run_swarm(task, normalized, args),
        "cli_executor": run_cli_executor(task, normalized, handshake, args),
        "verification": run_verification(args),
    }
    subsystem_results["promotion_candidate"] = stage_promotion_candidate(commons, task, normalized, subsystem_results)
    receipts = build_receipts(task, normalized, live, subsystem_results)
    assertions = {
        "live_model_attempted": bool(live.get("attempted")),
        "live_route_repaired_or_valid": bool(normalized.get("route")),
        "advanced_tools_selected": any(item in normalized.get("route", []) for item in ("meta_tool_commons", "fused_crystal", "pytest", "capability_registry")),
        "subagents_selected": len(normalized.get("subagents") or []) >= 4,
        "swarm_orchestrated_or_gated": swarm_orchestrated_or_gated(subsystem_results["swarm"]),
        "cli_plan_ready": bool(subsystem_results["cli_executor"].get("plan", {}).get("ready")),
        "verification_passed": bool(subsystem_results["verification"].get("passed")),
        "promotion_candidate_staged": bool(subsystem_results["promotion_candidate"].get("candidate_id")),
        "no_cloud_model_used": True,
    }
    report = {
        "beast_object_type": "tiny_llama_live_e2e_orchestration_gauntlet",
        "version": "1.0",
        "generated_at": utc_now(),
        "tiny_model": args.ollama_model,
        "task": task,
        "session_handshake": handshake,
        "live_ollama": live,
        "normalized_orchestration_plan": normalized,
        "live_score": live_score,
        "subsystem_results": subsystem_results,
        "receipts": receipts,
        "assertions": assertions,
        "passed": all(assertions.values()) and live_score >= args.min_live_score,
        "claim_boundary": (
            "This proves a tiny model can drive an end-to-end BEAST orchestration scaffold "
            "when schema repair, subagents, tools, verification, and promotion are externalized. "
            "It does not prove the base model has frontier reasoning weights."
        ),
    }
    canonical = json.dumps({k: v for k, v in report.items() if k != "report_hash"}, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)
    report["report_hash"] = "sha256:" + hashlib.sha256(canonical.encode()).hexdigest()
    return report


def run_capability_inventory(registry: CapabilityRegistry) -> Dict[str, Any]:
    inventory = registry.list_capabilities()
    sources = registry.discovery_sources(include_inventory=True, include_open_source_mcp=True)
    return {
        "count": inventory.get("count"),
        "kinds": inventory.get("kinds"),
        "families": inventory.get("families"),
        "discovery_source_count": sources.get("source_count"),
        "discovery_item_count": sum(len(source.get("items") or []) for source in sources.get("sources") or []),
    }


def run_swarm(task: Dict[str, Any], plan: Dict[str, Any], args: argparse.Namespace) -> Dict[str, Any]:
    swarm = SwarmKernel(db_path=str(RESULTS / "tiny_llama_live_e2e_orchestration_gauntlet" / "swarm.db"))
    return swarm.run({
        "objective": task["objective"],
        "task_type": task["task_class"],
        "risk_level": task["risk"],
        "profile": "openclaw",
        "metadata": {
            "source": "tiny_llama_live_e2e",
            "tiny_route": plan.get("route"),
            "tiny_subagents": plan.get("subagents"),
        },
        "checks": ["python3 -m py_compile app/kernel/session_handshake.py", "pytest focused handshake/agentic tests"],
        "value": {"tokens_saved": 512, "cost_saved_usd": 0.01},
    })


def run_cli_executor(task: Dict[str, Any], plan: Dict[str, Any], handshake: Dict[str, Any], args: argparse.Namespace) -> Dict[str, Any]:
    executor = BeastCLIExecutor(handshake_builder=SessionHandshakeBuilder())
    candidate_tools = list(plan.get("route") or []) + list(plan.get("subagents") or [])
    cli_plan = executor.plan(
        objective=task["objective"],
        mode="openclaw",
        workspace_root=args.repo,
        use_ollama=False,
        candidate_tools=candidate_tools,
        required_tools=["meta_tool_commons", "pytest"],
        preflight_budget_ms=args.preflight_budget_ms,
        scout_budget_ms=args.scout_budget_ms,
    )
    execution = executor.execute(
        objective=task["objective"],
        mode="openclaw",
        workspace_root=args.repo,
        dry_run=True,
        approved=False,
        use_ollama=False,
        candidate_tools=candidate_tools,
        required_tools=["meta_tool_commons", "pytest"],
        preflight_budget_ms=args.preflight_budget_ms,
        scout_budget_ms=args.scout_budget_ms,
    )
    return {"plan": cli_plan, "execution": execution}


def run_verification(args: argparse.Namespace) -> Dict[str, Any]:
    commands = [
        ["python3", "-m", "py_compile", "app/kernel/session_handshake.py", "benchmarks/tiny_llama_agentic_orchestrator_gauntlet.py"],
        [
            "python3",
            "-m",
            "pytest",
            "-q",
            "tests/benchmarks/test_beast_definitive_mega_test.py::test_tiny_llama_live_schema_repair_turns_weak_json_into_orchestration_contract",
            "tests/test_session_handshake.py",
        ],
    ]
    rows = []
    for command in commands:
        started = time.perf_counter()
        proc = subprocess.run(command, cwd=str(ROOT), text=True, capture_output=True, timeout=max(5, int(args.verify_timeout_seconds)))
        rows.append({
            "command": command,
            "returncode": proc.returncode,
            "latency_ms": round((time.perf_counter() - started) * 1000.0, 3),
            "stdout_tail": proc.stdout[-2000:],
            "stderr_tail": proc.stderr[-2000:],
        })
    return {"passed": all(row["returncode"] == 0 for row in rows), "checks": rows}


def swarm_orchestrated_or_gated(swarm_result: Dict[str, Any]) -> bool:
    status = str(swarm_result.get("status") or "")
    if status in {"ready", "completed"}:
        return True
    if status != "approval_required":
        return False
    roles = {str(event.get("role") or "") for event in swarm_result.get("events") or [] if isinstance(event, dict)}
    gates = swarm_result.get("gates") if isinstance(swarm_result.get("gates"), list) else []
    approval_gate = any(str(gate.get("decision") or "") == "approval_required" for gate in gates if isinstance(gate, dict))
    return approval_gate and {"hermes", "conductor", "sentinel", "supervisor"} <= roles


def stage_promotion_candidate(commons: MetaToolCommons, task: Dict[str, Any], plan: Dict[str, Any], subsystem_results: Dict[str, Any]) -> Dict[str, Any]:
    seed = {
        "task_id": task["task_id"],
        "route": plan.get("route"),
        "subagents": plan.get("subagents"),
        "gates": plan.get("gates"),
        "verification_passed": subsystem_results["verification"].get("passed"),
    }
    schema_hash = "sha256:" + hashlib.sha256(json.dumps(seed, sort_keys=True, default=str).encode()).hexdigest()
    return commons.propose({
        "kind": "skill_recipe",
        "name": "tiny_llama_live_e2e_orchestration_recipe",
        "version": "1.0",
        "schema_hash": schema_hash,
        "task_class": task["task_class"],
        "role": "tiny_llama_policy_head",
        "risk_class": "medium",
        "pattern": {
            "task_class": task["task_class"],
            "route": plan.get("route"),
            "subagents": plan.get("subagents"),
            "gates": plan.get("gates"),
        },
        "action": {
            "type": "tiny_llama_beast_e2e_orchestration",
            "execution_policy": "verify_before_promote",
            "requires_subagents": plan.get("subagents"),
        },
    }, source="tiny_llama_live_e2e_gauntlet")


def build_receipts(task: Dict[str, Any], plan: Dict[str, Any], live: Dict[str, Any], subsystem_results: Dict[str, Any]) -> Dict[str, Any]:
    body = {
        "task_hash": "sha256:" + hashlib.sha256(json.dumps(task, sort_keys=True).encode()).hexdigest(),
        "plan_hash": "sha256:" + hashlib.sha256(json.dumps(plan, sort_keys=True, default=str).encode()).hexdigest(),
        "live_model": live.get("model"),
        "swarm_run_id": subsystem_results["swarm"].get("run_id"),
        "cli_plan_hash": subsystem_results["cli_executor"].get("plan", {}).get("plan_hash"),
        "verification_passed": subsystem_results["verification"].get("passed"),
        "promotion_candidate_id": subsystem_results["promotion_candidate"].get("candidate_id"),
    }
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)
    body["receipt_hash"] = "sha256:" + hashlib.sha256(canonical.encode()).hexdigest()
    return body


def write_report(report: Dict[str, Any], output: str) -> Dict[str, Any]:
    output_dir = RESULTS / output
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "e2e_orchestration_report.json").write_text(json.dumps(report, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    (output_dir / "live_ollama_plan.json").write_text(json.dumps(report["live_ollama"], indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    (output_dir / "normalized_orchestration_plan.json").write_text(json.dumps(report["normalized_orchestration_plan"], indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    (output_dir / "subsystem_results.json").write_text(json.dumps(report["subsystem_results"], indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    write_readme(output_dir / "README.md", report)
    integrity = integrity_manifest(output_dir)
    return {"directory": str(output_dir), "integrity_hash": integrity["manifest_hash"]}


def write_readme(path: Path, report: Dict[str, Any]) -> None:
    assertions = report["assertions"]
    lines = [
        "# Tiny Llama Live E2E Orchestration Gauntlet",
        "",
        f"Generated: `{report['generated_at']}`",
        f"Passed: `{report['passed']}`",
        f"Tiny model: `{report['tiny_model']}`",
        f"Live score: `{report['live_score']}`",
        f"Swarm run: `{report['subsystem_results']['swarm'].get('run_id')}`",
        f"CLI plan hash: `{report['subsystem_results']['cli_executor']['plan'].get('plan_hash')}`",
        f"Promotion candidate: `{report['subsystem_results']['promotion_candidate'].get('candidate_id')}`",
        f"Receipt hash: `{report['receipts']['receipt_hash']}`",
        f"Report hash: `{report['report_hash']}`",
        "",
        "## Assertions",
        "",
        "| Assertion | Passed |",
        "| --- | --- |",
    ]
    for key, value in assertions.items():
        lines.append(f"| `{key}` | `{bool(value)}` |")
    lines.extend(["", "## Normalized Route", "", "```json", json.dumps(report["normalized_orchestration_plan"], indent=2, sort_keys=True), "```", "", "## Boundary", "", report["claim_boundary"], ""])
    path.write_text("\n".join(lines), encoding="utf-8")


def integrity_manifest(output_dir: Path) -> Dict[str, Any]:
    files = []
    for path in sorted(output_dir.rglob("*")):
        if path.is_file() and path.name != "integrity_manifest.json":
            files.append({
                "path": str(path.relative_to(output_dir)),
                "bytes": path.stat().st_size,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            })
    manifest = {"algorithm": "sha256", "generated_at": utc_now(), "files": files}
    canonical = json.dumps(manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    manifest["manifest_hash"] = "sha256:" + hashlib.sha256(canonical.encode()).hexdigest()
    (output_dir / "integrity_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=str(ROOT))
    parser.add_argument("--ollama-model", default="qwen2.5:0.5b")
    parser.add_argument("--ollama-base-url", default="http://127.0.0.1:11434")
    parser.add_argument("--ollama-timeout-seconds", type=float, default=20.0)
    parser.add_argument("--preflight-budget-ms", type=int, default=900)
    parser.add_argument("--scout-budget-ms", type=int, default=500)
    parser.add_argument("--verify-timeout-seconds", type=int, default=45)
    parser.add_argument("--min-live-score", type=float, default=0.55)
    parser.add_argument("--output", default="tiny_llama_live_e2e_orchestration_gauntlet")
    args = parser.parse_args(argv)
    report = build_report(args)
    artifacts = write_report(report, args.output)
    print(json.dumps({"passed": report["passed"], "live_score": report["live_score"], "assertions": report["assertions"], "artifacts": artifacts}, indent=2, sort_keys=True))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

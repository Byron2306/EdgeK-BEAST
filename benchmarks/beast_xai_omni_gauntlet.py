#!/usr/bin/env python3
"""The BEAST xAI omni-gauntlet: live coding, ablations, and system evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import time
from dataclasses import replace
from pathlib import Path
from typing import Any, Dict, Iterable, List

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.kernel.networking.network_chronicle import NetworkChronicleConnector
from app.kernel.security.secret_vault import SecretVault
from benchmarks.beast_systems_benchmark import (
    LIVE_PROVIDER_PRESETS,
    LaneResult,
    live_failure_buckets,
    live_provider_fitness,
    run_systems_benchmark,
    summarize_live_efficiency,
    summarize_live_results,
    write_live_gauntlet_artifacts,
    write_markdown,
)
from benchmarks.xai_omni_tasks import OMNI_TASK_CLASSES, omni_tasks


RESULTS = ROOT / "benchmarks" / "results"
DEFAULT_OUTPUT = "beast_xai_omni_gauntlet"
ABLATION_TASKS = [
    "multi_file_hidden_decimal_fix",
    "ui_state_collapse_selection",
    "output_governance_malformed_json",
    "commons_local_approval_gate",
]

LOCAL_PROBE_GROUPS: Dict[str, List[str]] = {
    "coding_and_hidden_tests": [
        "tests/test_sourceplan_bridge.py", "tests/test_tui_output_governance.py",
        "tests/test_quality_cascade.py",
    ],
    "input_governance": [
        "tests/test_task_envelope.py", "tests/test_context_packet.py", "tests/test_context_economizer.py",
        "tests/test_compression_pipeline.py", "tests/test_workspace_reasoning.py",
    ],
    "output_governance": [
        "tests/test_output_governor.py", "tests/test_provider_handoff.py", "tests/test_sourceplan_bridge.py",
    ],
    "agent_awareness_preflight": [
        "tests/test_session_handshake.py", "tests/test_openclaw_preflight.py", "tests/test_ollama_scout.py",
        "tests/test_beast_cli_executor.py",
    ],
    "provider_economics_and_routing": [
        "tests/test_provider_economist.py", "tests/test_provider_registry.py", "tests/test_deployment_manager.py",
        "tests/test_budget_governance.py",
    ],
    "tool_bus_and_laziness": [
        "tests/test_mcp_broker.py", "tests/test_mcp_runtime_v2.py", "tests/test_tool_laziness.py",
        "tests/test_tool_laziness_plugin.py", "tests/test_tool_integrations.py",
    ],
    "commons_skills_and_promotion": [
        "tests/test_capability_exchange.py", "tests/test_meta_tool_commons.py", "tests/test_skill_tree.py",
        "tests/test_promotion_loop.py", "tests/test_capability_registry.py",
    ],
    "chronicle_memory_and_prec": [
        "tests/test_prec_lifecycle.py", "tests/test_forensic_memory.py", "tests/test_memory_stack.py",
        "tests/test_insight_compiler.py", "tests/test_evidence_scoring.py", "tests/test_canon_registry.py",
    ],
    "connectors_observability_and_network": [
        "tests/test_connectors.py", "tests/test_otel_connector.py", "tests/test_os_bypass.py",
    ],
    "marketplace_security_and_enterprise": [
        "tests/test_plugin_marketplace.py", "tests/test_runtime_governance.py", "tests/test_secret_vault.py",
        "tests/test_enterprise_mode.py", "tests/test_isolation_forest.py",
    ],
    "quality_forge_and_packaging": [
        "tests/test_quality_cascade.py", "tests/test_forge_scorecard.py", "tests/test_ast_compressor.py",
    ],
    "tui_and_operator_surface": [
        "tests/test_tui_intelligence.py", "tests/test_tui_output_governance.py",
    ],
    "gateway_swarm_and_workflows": [
        "tests/test_gateway.py", "tests/test_conductor_workflow.py", "tests/test_swarm_kernel.py",
        "tests/test_interception_events.py",
    ],
}


def utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _run_probe(name: str, files: Iterable[str]) -> Dict[str, Any]:
    command = [sys.executable, "-m", "pytest", "-q", *files]
    started = time.perf_counter()
    proc = subprocess.run(command, cwd=str(ROOT), text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    elapsed = round((time.perf_counter() - started) * 1000.0, 3)
    return {
        "name": name,
        "passed": proc.returncode == 0,
        "returncode": proc.returncode,
        "latency_ms": elapsed,
        "test_files": list(files),
        "stdout_tail": (proc.stdout or "")[-1500:],
        "stderr_tail": (proc.stderr or "")[-1500:],
    }


def run_local_probes() -> Dict[str, Any]:
    groups = [_run_probe(name, files) for name, files in LOCAL_PROBE_GROUPS.items()]
    return {
        "beast_object_type": "xai_omni_local_probe_matrix",
        "generated_at": utc_now(),
        "group_count": len(groups),
        "passed_groups": sum(1 for item in groups if item["passed"]),
        "all_passed": all(item["passed"] for item in groups),
        "groups": groups,
    }


def _lane_result(item: Dict[str, Any]) -> LaneResult:
    fields = LaneResult.__dataclass_fields__
    return LaneResult(**{key: value for key, value in item.items() if key in fields})


def _recompute_live(report: Dict[str, Any], tasks: List[Any]) -> None:
    results = [_lane_result(item) for item in report.get("live_results") or []]
    report["live_summary"] = summarize_live_results(results, tasks)
    report["live_efficiency_summary"] = summarize_live_efficiency(results)
    report["live_provider_fitness"] = live_provider_fitness(results, tasks)
    report["live_failures_by_bucket"] = live_failure_buckets(results)


def _ablation_summary(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    by_lane: Dict[str, Dict[str, Any]] = {}
    for item in results:
        lane = str(item.get("lane") or "unknown")
        row = by_lane.setdefault(lane, {"tasks": 0, "completed": 0, "tokens": [], "latencies": []})
        row["tasks"] += 1
        row["completed"] += int(bool(item.get("completed")))
        usage = item.get("usage") or {}
        tokens = int(usage.get("prompt_tokens") or 0) + int(usage.get("completion_tokens") or 0)
        if tokens:
            row["tokens"].append(tokens)
        if item.get("latency_ms") is not None:
            row["latencies"].append(float(item["latency_ms"]))
    for row in by_lane.values():
        row["completion_rate"] = round(row["completed"] / row["tasks"], 6) if row["tasks"] else 0.0
        row["average_tokens"] = round(sum(row.pop("tokens")) / row["tasks"], 3) if row["tasks"] else None
        latencies = row.pop("latencies")
        row["average_latency_ms"] = round(sum(latencies) / len(latencies), 3) if latencies else None
    return by_lane


def _integrity_manifest(output_dir: Path) -> Dict[str, Any]:
    files = []
    for path in sorted(output_dir.rglob("*")):
        if not path.is_file() or path.name == "integrity_manifest.json":
            continue
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


def _write_omni_summary(report: Dict[str, Any], path: Path) -> None:
    provider_key = str(report.get("omni_provider") or "xai")
    provider_label = provider_key.replace("_", " ").title()
    live = report.get("governed_summary", {}).get(provider_key, {})
    raw = report.get("raw_summary", {}).get(provider_key, {})
    fitness = report.get("governed_provider_fitness", {}).get(provider_key, {})
    probes = report.get("local_probe_matrix") or {}
    coverage = report.get("coverage") or {}
    governed_rows = [item for item in report.get("live_results", []) if str(item.get("lane") or "").endswith("_full_beast")]
    clean_tasks = []
    rescued_tasks = []
    for item in governed_rows:
        evidence = item.get("output_evidence") or {}
        rescued = any(evidence.get(key) for key in ("canonicalized", "repair_attempted", "local_verifier_repair"))
        (rescued_tasks if rescued else clean_tasks).append(str(item.get("task")))
    lines = [
        f"# BEAST {provider_label} Omni-Gauntlet",
        "",
        f"Generated: `{report.get('generated_at')}`",
        "",
        f"This run evaluates {provider_label} as one governed component inside BEAST. Provider-clean and BEAST-rescued outcomes are reported separately.",
        "",
        "## Headline",
        "",
        f"- Full-BEAST completions: `{live.get('completed', 0)}/{live.get('tasks', 0)}`",
        f"- Clean provider completions: `{live.get('clean_completed', 0)}`",
        f"- BEAST-rescued completions: `{live.get('rescued_completed', 0)}`",
        f"- Hidden clean: `{live.get('hidden_clean_completed', 0)}/{live.get('hidden_task_count', 0)}`",
        f"- Raw baseline completions: `{raw.get('completed', 0)}/{raw.get('tasks', 0)}`",
        f"- Local subsystem probe groups: `{probes.get('passed_groups', 0)}/{probes.get('group_count', 0)}`",
        f"- Fitness: `{fitness.get('score')}`; role: `{fitness.get('recommended_role')}`",
        f"- Evidence coverage: `{coverage.get('covered_layers', 0)}/{coverage.get('total_layers', 0)}`",
        "",
        "## Layer Coverage",
        "",
        "| Layer | Live Tasks | Local Probe | Status |",
        "| --- | ---: | --- | --- |",
    ]
    for layer in coverage.get("layers", []):
        lines.append(f"| {layer['layer']} | {layer['live_tasks']} | {layer['local_probe']} | {layer['status']} |")
    lines.extend([
        "", "## Ablation", "",
        "| Lane | Tasks | Completed | Completion | Avg Tokens | Avg Latency ms |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ])
    for lane, row in (report.get("omni_ablation_summary") or {}).items():
        lines.append(f"| {lane} | {row['tasks']} | {row['completed']} | {row['completion_rate']:.2%} | {row['average_tokens']} | {row['average_latency_ms']} |")
    comparison = report.get("historical_xai_10task_comparison") or {}
    if comparison:
        lines.extend([
            "", "## Matched Historical Comparison", "",
            "| Run | Tasks | Completed | Clean | Avg Latency ms | Avg Tokens |",
            "| --- | ---: | ---: | ---: | ---: | ---: |",
            f"| Previous xAI 10-task | {comparison['previous']['tasks']} | {comparison['previous']['completed']} | {comparison['previous']['clean']} | {comparison['previous']['average_latency_ms']} | {comparison['previous']['average_tokens']} |",
            f"| Omni first 10 | {comparison['current']['tasks']} | {comparison['current']['completed']} | {comparison['current']['clean']} | {comparison['current']['average_latency_ms']} | {comparison['current']['average_tokens']} |",
            "",
            f"Observed average-latency change: `{comparison['latency_change_percent']}%`; token change: `{comparison['token_change_percent']}%`. Provider load may affect latency.",
        ])
    lines.extend([
        "", "## Provider Outcome Classes", "",
        "**Clean governed tasks:** " + ", ".join(f"`{name}`" for name in clean_tasks) + ".",
        "",
        "**BEAST-rescued tasks:** " + ", ".join(f"`{name}`" for name in rescued_tasks) + ".",
    ])
    lines.extend(["", "## Local System Probes", ""])
    for item in probes.get("groups", []):
        lines.append(f"- **{item['name']}**: {'PASS' if item['passed'] else 'FAIL'} in `{item['latency_ms']} ms` ({len(item['test_files'])} test files).")
    lines.extend([
        "", "## Interpretation", "",
        f"A live completion proves the BEAST system reached a verified fix. A clean completion additionally proves {provider_label}'s governed output passed without canonicalization, schema repair, or local verifier repair. Local probes test BEAST itself and are not credited to the provider.",
        "",
        "Cost rankings remain excluded when the provider does not return first-party request cost observations.",
    ])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _row_stats(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    completed = [item for item in rows if item.get("completed")]
    clean = []
    for item in completed:
        evidence = item.get("output_evidence") or {}
        if not any(evidence.get(key) for key in ("canonicalized", "repair_attempted", "local_verifier_repair")):
            clean.append(item)
    latencies = [float(item["latency_ms"]) for item in rows if item.get("latency_ms") is not None]
    tokens = [
        int((item.get("usage") or {}).get("prompt_tokens") or 0)
        + int((item.get("usage") or {}).get("completion_tokens") or 0)
        for item in rows
    ]
    return {
        "tasks": len(rows), "completed": len(completed), "clean": len(clean),
        "average_latency_ms": round(sum(latencies) / len(latencies), 3) if latencies else None,
        "average_tokens": round(sum(tokens) / len(tokens), 3) if tokens else None,
    }


def _historical_comparison(current_full_results: List[Dict[str, Any]]) -> Dict[str, Any]:
    path = RESULTS / "beast_systems_benchmark_live_xai_replicate_10task.json"
    if not path.exists():
        return {}
    try:
        previous_report = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    previous_rows = [item for item in previous_report.get("live_results", []) if item.get("provider") == "xai"][:10]
    current_rows = current_full_results[:10]
    if len(previous_rows) != 10 or len(current_rows) != 10:
        return {}
    previous = _row_stats(previous_rows)
    current = _row_stats(current_rows)
    latency_change = ((current["average_latency_ms"] / previous["average_latency_ms"]) - 1.0) * 100.0
    token_change = ((current["average_tokens"] / previous["average_tokens"]) - 1.0) * 100.0
    return {
        "previous": previous, "current": current,
        "latency_change_percent": round(latency_change, 2),
        "token_change_percent": round(token_change, 2),
        "comparison_scope": "same original ten tasks; separate live runs",
    }


def _coverage(tasks: List[Any], probes: Dict[str, Any]) -> Dict[str, Any]:
    live_classes = {OMNI_TASK_CLASSES.get(task.name, task.name) for task in tasks}
    probe_names = {item["name"] for item in probes.get("groups", []) if item.get("passed")}
    layers = [
        ("input_governance", {"config_governance", "parsing", "vector_context_deduplication"}),
        ("output_governance", {"output_governance", "refs_only_action_ir", "stale_file_hash_rejection"}),
        ("coding_and_hidden_tests", {"multi_file_hidden", "async_streaming", "tui_state"}),
        ("agent_awareness_preflight", {"session_latency_budget_clamp"}),
        ("provider_economics_and_routing", {"provider_routing", "provider_economist_role_route", "deployment_route_resolution"}),
        ("tool_bus_and_laziness", {"tool_laziness_required_override", "mcp_tool_schema_pinning"}),
        ("commons_skills_and_promotion", {"commons_local_approval_gate"}),
        ("chronicle_memory_and_prec", {"chronicle_provider_evidence_record"}),
        ("connectors_observability_and_network", {"otel_attribute_secret_redaction", "network_probe_failure_classification", "github_pr_task_envelope"}),
        ("marketplace_security_and_enterprise", {"plugin_permission_risk_gate", "secret_redaction"}),
        ("quality_forge_and_packaging", {"quality_cascade_language_matrix"}),
        ("tui_and_operator_surface", {"tui_state"}),
        ("gateway_swarm_and_workflows", {"rollback"}),
    ]
    rows = []
    for layer, classes in layers:
        live_count = sum(1 for task in tasks if OMNI_TASK_CLASSES.get(task.name, task.name) in classes)
        probe = layer in probe_names
        rows.append({"layer": layer, "live_tasks": live_count, "local_probe": "PASS" if probe else "FAIL", "status": "covered" if live_count and probe else "partial"})
    return {"total_layers": len(rows), "covered_layers": sum(1 for row in rows if row["status"] == "covered"), "live_task_classes": sorted(live_classes), "layers": rows}


def run(*, live: bool, output_name: str, max_tokens: int, timeout: float, skip_local: bool = False, provider_name: str = "xai") -> Dict[str, Any]:
    SecretVault().load()
    tasks = omni_tasks()
    provider_key = str(provider_name or "xai").strip().lower().replace("-", "_")
    if provider_key not in LIVE_PROVIDER_PRESETS:
        raise ValueError(f"unknown live provider preset: {provider_name}")
    provider = replace(LIVE_PROVIDER_PRESETS[provider_key], timeout=float(timeout))
    local_probes = {"group_count": 0, "passed_groups": 0, "all_passed": False, "groups": []} if skip_local else run_local_probes()

    report = run_systems_benchmark(
        live=live,
        live_providers=[provider],
        live_max_tasks=len(tasks),
        live_lanes=["full_beast"],
        live_max_tokens=max_tokens,
        live_prompt_mode="compact",
        live_json_mode=True,
        live_only=True,
        tasks_override=tasks,
    )
    full_results = list(report.get("live_results") or [])
    ablation_report = run_systems_benchmark(
        live=live,
        live_providers=[provider],
        live_max_tasks=len(ABLATION_TASKS),
        live_lanes=["raw"],
        live_max_tokens=max_tokens,
        live_prompt_mode="compact",
        live_json_mode=True,
        live_only=True,
        task_names=ABLATION_TASKS,
        tasks_override=tasks,
    )
    ablation_raw = list(ablation_report.get("live_results") or [])
    matched_full = [item for item in full_results if item.get("task") in ABLATION_TASKS]
    report["live_results"] = full_results + ablation_raw
    _recompute_live(report, tasks)
    full_lane_results = [_lane_result(item) for item in full_results]
    raw_lane_results = [_lane_result(item) for item in ablation_raw]
    report["governed_summary"] = summarize_live_results(full_lane_results, tasks)
    report["raw_summary"] = summarize_live_results(raw_lane_results, tasks)
    report["governed_provider_fitness"] = live_provider_fitness(full_lane_results, tasks)
    report["raw_provider_fitness"] = live_provider_fitness(raw_lane_results, tasks)
    report["generated_at"] = utc_now()
    report["beast_object_type"] = "beast_xai_omni_gauntlet"
    report["omni_version"] = "1.0"
    report["omni_provider"] = provider_key
    report["mode"] = "live" if live else "dry_run"
    report["local_probe_matrix"] = local_probes
    report["omni_ablation_summary"] = _ablation_summary(matched_full + ablation_raw)
    report["historical_xai_10task_comparison"] = _historical_comparison(full_results)
    report["coverage"] = _coverage(tasks, local_probes)
    report["host"] = {"python": platform.python_version(), "platform": platform.platform()}
    report["claim_boundary"] = {
        "system_completion": "Provider output plus BEAST governance reached passing visible and hidden tests.",
        "provider_clean": "No canonicalization, schema repair, or local verifier repair was used.",
        "provider_rescued": "BEAST repaired or replaced imperfect provider output before verification.",
        "local_probes": "Validate BEAST subsystems and are not provider capability credit.",
    }
    report = NetworkChronicleConnector().attach_benchmark_report(
        report,
        {"mode": "omni_gauntlet_metadata_probe", "opened": True, "captured": True, "packets": len(report["live_results"]), "drops": 0},
        source="benchmark_orchestration",
    )

    output_dir = RESULTS / output_name
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)
    write_live_gauntlet_artifacts(report, output_dir)
    (output_dir / "local_probe_matrix.json").write_text(json.dumps(local_probes, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (output_dir / "coverage_matrix.json").write_text(json.dumps(report["coverage"], indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (output_dir / "omni_report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_markdown(report, output_dir / "systems_report.md")
    _write_omni_summary(report, output_dir / "README.md")
    integrity = _integrity_manifest(output_dir)
    archive = shutil.make_archive(str(output_dir), "zip", root_dir=str(output_dir))
    report["artifacts"] = {"directory": str(output_dir), "archive": archive, "integrity_hash": integrity["manifest_hash"]}
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the BEAST provider omni-gauntlet")
    parser.add_argument("--live", action="store_true", help="Make live provider calls; without this flag the provider lanes fail closed")
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    parser.add_argument("--provider", default="xai", help="Live provider preset, for example xai or nvidia_nim")
    parser.add_argument("--max-tokens", type=int, default=1400)
    parser.add_argument("--timeout", type=float, default=240.0)
    parser.add_argument("--skip-local", action="store_true")
    args = parser.parse_args()
    os.environ["XAI_TIMEOUT"] = str(args.timeout)
    report = run(live=args.live, output_name=args.output, max_tokens=max(400, args.max_tokens), timeout=args.timeout, skip_local=args.skip_local, provider_name=args.provider)
    provider_key = str(args.provider).strip().lower().replace("-", "_")
    summary = report.get("governed_summary", {}).get(provider_key, {})
    print(json.dumps({
        "mode": report["mode"], "tasks": summary.get("tasks"), "completed": summary.get("completed"),
        "clean": summary.get("clean_completed"), "rescued": summary.get("rescued_completed"),
        "local_probes": report["local_probe_matrix"].get("passed_groups"),
        "coverage": report["coverage"].get("covered_layers"), "artifacts": report.get("artifacts"),
    }, indent=2))
    return 0 if (not args.live or summary.get("completed") == summary.get("tasks")) else 1


if __name__ == "__main__":
    raise SystemExit(main())

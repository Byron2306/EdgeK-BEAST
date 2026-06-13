#!/usr/bin/env python3
"""Full BEAST live gauntlet.

Combines local edge metrics, deterministic governance/CIPC metrics, live
provider raw-vs-BEAST comparisons, enterprise controls, and host telemetry into
one evidence artifact.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import resource
import socket
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List

from app.kernel.benchmark import MegaGauntlet
from app.kernel.enterprise import EnterpriseManager
from app.kernel.ollama_scout import OllamaScout
from app.kernel.workspace_graph import WorkspaceGraph

from benchmarks import edge_metrics_benchmark, provider_edge_compare


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "benchmarks" / "results"


def utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def host_telemetry() -> Dict[str, Any]:
    usage = resource.getrusage(resource.RUSAGE_SELF)
    load_avg = os.getloadavg() if hasattr(os, "getloadavg") else (0.0, 0.0, 0.0)
    disk = shutil_disk(ROOT)
    return {
        "hostname": socket.gethostname(),
        "platform": platform.platform(),
        "python": platform.python_version(),
        "cpu_count": os.cpu_count(),
        "load_average_1m_5m_15m": [round(item, 4) for item in load_avg],
        "process_max_rss_kb": usage.ru_maxrss,
        "process_user_cpu_seconds": round(usage.ru_utime, 4),
        "process_system_cpu_seconds": round(usage.ru_stime, 4),
        "workspace_disk": disk,
        "tool_versions": {
            "ollama": command_version(["ollama", "--version"]),
            "rtk": command_version(["rtk", "--version"]),
            "longcodezip": command_version(["longcodezip", "--help"], first_line_only=True),
            "reporelay": command_version(["reporelay", "--help"], first_line_only=True),
        },
    }


def shutil_disk(path: Path) -> Dict[str, int]:
    import shutil

    usage = shutil.disk_usage(path)
    return {"total_bytes": usage.total, "used_bytes": usage.used, "free_bytes": usage.free}


def command_version(command: List[str], first_line_only: bool = False) -> str:
    try:
        completed = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=5)
    except Exception as exc:
        return f"unavailable: {exc}"
    output = (completed.stdout or "").strip()
    if first_line_only:
        output = output.splitlines()[0] if output.splitlines() else ""
    return output[:500] or f"exit_{completed.returncode}"


def enterprise_benchmark(live_provider_report: Dict[str, Any]) -> Dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="beast-enterprise-gauntlet-") as temp_dir:
        manager = EnterpriseManager(
            policies={
                "enterprise": {
                    "enabled": True,
                    "trace_encryption_secret": "full-live-gauntlet-local-secret",
                    "default_daily_request_limit": 100,
                    "default_daily_cost_limit_usd": 5.0,
                }
            },
            db_path=str(Path(temp_dir) / "enterprise.db"),
        )
        team = manager.create_team("CIPC Live Gauntlet", daily_request_limit=100, daily_cost_limit_usd=5.0)
        user = manager.create_user(team["team_id"], "cipc-gauntlet@example.local", role="admin")
        key = manager.issue_virtual_key(team["team_id"], user["user_id"], scopes=["gateway:use", "benchmarks:run"])
        auth = manager.authenticate_virtual_key(key["virtual_key"], required_scope="gateway:use")
        pack = manager.register_policy_pack(
            "Industrial Safety Live Benchmark",
            {
                "meta_rules": {
                    "circuit_breaker_enabled": True,
                    "semantic_risk_governance_enabled": True,
                    "max_tool_calls_per_request": 8,
                },
                "enterprise": {"sealed_trace_required": True},
            },
        )
        manager.assign_policy_pack(team["team_id"], pack["pack_id"])

        live_runs = live_provider_report.get("runs", [])
        for run in live_runs:
            if run.get("ok"):
                manager.record_team_usage(
                    team_id=team["team_id"],
                    user_id=user["user_id"],
                    key_id=auth.key_id,
                    provider=run.get("provider", ""),
                    model=run.get("model", ""),
                    request_count=1,
                    estimated_cost_usd=safe_float(run.get("estimated_cost_usd")),
                    total_tokens=int(run.get("usage", {}).get("total_tokens", 0)),
                )
            manager.record_observability_event(
                team_id=team["team_id"],
                user_id=user["user_id"],
                event_type="live_provider_call" if run.get("ok") else "live_provider_failure",
                severity="info" if run.get("ok") else "warning",
                payload={
                    "provider": run.get("provider"),
                    "scenario": run.get("scenario"),
                    "mode": run.get("mode"),
                    "latency_ms": run.get("latency_ms"),
                    "tokens": run.get("usage", {}).get("total_tokens", 0),
                    "error": run.get("error", ""),
                },
                trace_id=f"gauntlet-{run.get('provider', 'none')}-{run.get('scenario', 'none')}-{run.get('mode', 'none')}",
            )

        budget = manager.team_budget_summary(team["team_id"])
        stored = manager.store_encrypted_trace(
            team["team_id"],
            {
                "trace_id": "full-live-gauntlet",
                "summary": live_provider_report.get("summary", {}),
                "configured_providers": live_provider_report.get("configured_providers", []),
            },
            user_id=user["user_id"],
            metadata={"source": "benchmarks/full_live_gauntlet.py"},
        )
        retrieved = manager.retrieve_encrypted_trace(team["team_id"], stored["trace_id"])
        effective = manager.effective_policy(team["team_id"])

        return {
            "team": {key: value for key, value in team.items() if key != "metadata"},
            "user": {key: value for key, value in user.items() if key != "metadata"},
            "virtual_key": {"key_id": key["key_id"], "scopes": key["scopes"], "authenticated": auth.team_id == team["team_id"]},
            "budget": budget,
            "policy_pack": pack,
            "effective_policy_excerpt": {
                "circuit_breaker_enabled": effective.get("meta_rules", {}).get("circuit_breaker_enabled"),
                "semantic_risk_governance_enabled": effective.get("meta_rules", {}).get("semantic_risk_governance_enabled"),
                "sealed_trace_required": effective.get("enterprise", {}).get("sealed_trace_required"),
            },
            "sealed_trace": {
                "stored": {key: value for key, value in stored.items() if key != "digest"},
                "round_trip_ok": retrieved["trace"]["trace_id"] == "full-live-gauntlet",
            },
            "otel_resource_span_count": len(manager.otel_export(team_id=team["team_id"]).get("resourceSpans", [])),
            "state": manager.state(),
        }


def ollama_scout_benchmark(live: bool) -> Dict[str, Any]:
    graph = WorkspaceGraph()
    scout = OllamaScout(
        graph,
        policies={
            "ollama_scout": {
                "max_prompt_chars": int(os.environ.get("OLLAMA_SCOUT_MAX_PROMPT_CHARS", "7000")),
                "max_chunk_chars": int(os.environ.get("OLLAMA_SCOUT_MAX_CHUNK_CHARS", "420")),
                "max_exact_chars": int(os.environ.get("OLLAMA_SCOUT_MAX_EXACT_CHARS", "520")),
                "num_ctx": int(os.environ.get("OLLAMA_SCOUT_NUM_CTX", "2048")),
                "timeout_seconds": float(os.environ.get("OLLAMA_SCOUT_TIMEOUT_SECONDS", "20")),
            }
        },
    )
    tasks = [
        "Debug BEAST auth refresh loop using cached workspace graph and schema state.",
        "Prepare cloud handoff for provider comparison without rereading full repo context.",
    ]
    runs = []
    for task in tasks:
        started = time.perf_counter()
        result = scout.scout(
            {
                "task": task,
                "context_limit": 5,
                "tool_limit": 5,
                "use_ollama": live,
                "model": os.environ.get("OLLAMA_SCOUT_MODEL", "qwen2.5:0.5b"),
            },
            workspace_root=str(ROOT),
        )
        packet = result["packet"]
        runs.append({
            "task": task,
            "latency_ms": round((time.perf_counter() - started) * 1000.0, 3),
            "used_ollama": packet["local_analysis"].get("source") == "ollama",
            "ready_for_cloud": result["ready_for_cloud"],
            "selected_tools": result["selected_tools"],
            "memory_state": packet.get("memory_state", {}),
            "packet_stats": packet.get("packet_stats", {}),
            "model": packet.get("model"),
        })
    return {
        "mode": "bounded_local_scout",
        "live_ollama_calls": live,
        "status": scout.status(),
        "runs": runs,
    }


def cross_suite_summary(report: Dict[str, Any]) -> Dict[str, Any]:
    edge = report["edge_metrics"]
    provider = report["live_provider_compare"]
    cipc = report["mega_gauntlet"].get("cipc_metrics", {})
    return {
        "live_api_calls": report["live_api_calls"],
        "providers": provider.get("configured_providers", []),
        "edge_latency_reduction_percent": edge["latency"]["median_latency_reduction_percent"],
        "edge_bandwidth_reduction_percent": edge["bandwidth"]["industrial_telemetry"]["schema_rows_reduction_percent"],
        "edge_cost_token_reduction_percent": edge["cost_efficiency"]["combined_token_reduction_percent"],
        "cipc_handoff_token_reduction_percent": cipc.get("context_quality_measurement", {}).get("token_reduction_percent"),
        "cipc_postgres_circuit_opened": cipc.get("stateful_safety", {}).get("circuit_opened"),
        "ollama_scout_used_live_model": any(run.get("used_ollama") for run in report["ollama_scout"].get("runs", [])),
        "ollama_scout_prompt_limits": [
            run.get("packet_stats", {}).get("ollama_prompt_char_limit")
            for run in report["ollama_scout"].get("runs", [])
        ],
        "enterprise_budget_within_limit": report["enterprise"]["budget"]["within_budget"],
        "provider_summary": provider.get("summary", {}),
    }


def run_full_gauntlet(live: bool, repeats: int, timeout: float) -> Dict[str, Any]:
    edge_report = {
        "generated_at": utc_now(),
        "latency": edge_metrics_benchmark.benchmark_latency(),
        "bandwidth": edge_metrics_benchmark.benchmark_bandwidth(),
        "loop_protection": edge_metrics_benchmark.benchmark_loop_protection(),
        "cost_efficiency": edge_metrics_benchmark.benchmark_cost_efficiency(),
        "tool_laziness": edge_metrics_benchmark.benchmark_tool_laziness(),
        "swarm": edge_metrics_benchmark.benchmark_swarm(),
    }
    mega_report = MegaGauntlet().run(session_id="full-live-gauntlet")
    provider_report = provider_edge_compare.run_compare(timeout=timeout, repeats=max(1, repeats), dry_run=not live)
    scout_report = ollama_scout_benchmark(live=live)
    enterprise_report = enterprise_benchmark(provider_report)
    report = {
        "generated_at": utc_now(),
        "mode": "full_live_end_to_end_gauntlet" if live else "full_gauntlet_dry_run",
        "live_api_calls": live,
        "host_telemetry": host_telemetry(),
        "edge_metrics": edge_report,
        "mega_gauntlet": mega_report,
        "live_provider_compare": provider_report,
        "ollama_scout": scout_report,
        "enterprise": enterprise_report,
    }
    report["summary"] = cross_suite_summary(report)
    return report


def write_markdown(report: Dict[str, Any], path: Path) -> None:
    summary = report["summary"]
    lines = [
        "# EdgeK BEAST Full Live Gauntlet",
        "",
        f"Generated at: `{report['generated_at']}`",
        f"Mode: `{report['mode']}`",
        f"Live API calls: `{report['live_api_calls']}`",
        "",
        "## Executive Metrics",
        "",
        f"- Providers: `{', '.join(summary['providers']) or 'none configured'}`",
        f"- Edge latency reduction: `{summary['edge_latency_reduction_percent']}%`",
        f"- Edge bandwidth reduction: `{summary['edge_bandwidth_reduction_percent']}%`",
        f"- Edge cost/token reduction: `{summary['edge_cost_token_reduction_percent']}%`",
        f"- CIPC handoff token reduction: `{summary['cipc_handoff_token_reduction_percent']}%`",
        f"- CIPC Postgres circuit opened: `{summary['cipc_postgres_circuit_opened']}`",
        f"- Ollama scout used live model: `{summary['ollama_scout_used_live_model']}`",
        f"- Ollama scout prompt limits: `{summary['ollama_scout_prompt_limits']}`",
        f"- Enterprise budget within limit: `{summary['enterprise_budget_within_limit']}`",
        "",
        "## Provider Summary",
        "",
    ]
    for provider, provider_summary in summary.get("provider_summary", {}).items():
        if provider == "note":
            lines.append(f"- {provider_summary}")
            continue
        lines.extend([
            f"### {provider}",
            f"- Raw: `{provider_summary['raw']['successes']}/{provider_summary['raw']['attempts']}` successes, `{provider_summary['raw']['total_tokens']}` tokens, median `{provider_summary['raw']['median_latency_ms']} ms`",
            f"- BEAST: `{provider_summary['beast']['successes']}/{provider_summary['beast']['attempts']}` successes, `{provider_summary['beast']['total_tokens']}` tokens, median `{provider_summary['beast']['median_latency_ms']} ms`",
            f"- Observed token reduction: `{provider_summary['observed_total_token_reduction_percent']}%`",
            f"- Observed cost reduction: `{provider_summary['observed_cost_reduction_percent']}%`",
            "",
        ])
    lines.extend([
        "## Artifacts",
        "",
        "- JSON includes full local edge metrics, CIPC/mega-gauntlet metrics, live provider records, enterprise sealed-trace status, and host telemetry.",
    ])
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the full BEAST live end-to-end gauntlet.")
    parser.add_argument("--live", action="store_true", help="Execute live provider API calls.")
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--timeout", type=float, default=90.0)
    parser.add_argument("--out-prefix", default="full_live_gauntlet")
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    report = run_full_gauntlet(live=args.live, repeats=args.repeats, timeout=args.timeout)
    json_path = OUT_DIR / f"{args.out_prefix}.json"
    md_path = OUT_DIR / f"{args.out_prefix}.md"
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    write_markdown(report, md_path)
    print(json.dumps({"json_report": str(json_path), "markdown_report": str(md_path), "summary": report["summary"]}, indent=2))


if __name__ == "__main__":
    main()

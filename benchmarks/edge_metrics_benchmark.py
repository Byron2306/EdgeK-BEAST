#!/usr/bin/env python3
"""
EdgeK BEAST empirical metrics benchmark.

This runner separates implemented gateway mechanisms from local prototypes.
It does not claim kernel OS-bypass, production AST compression, or production
Isolation Forest support unless those mechanisms exist in the codebase.
"""

import json
import mmap
import os
import random
import statistics
import tempfile
import time
import zlib
from pathlib import Path
from typing import Any, Dict, List

from app.kernel.ast_compressor import ASTCompressor
from app.kernel.isolation_forest import IsolationForest
from app.kernel.os_bypass import capabilities as os_bypass_capabilities
from app.kernel.tool_laziness import ToolLazinessLearner
from app.context.economizer import ContextEconomizer
from app.kernel.perceive import EdgeKIR
from app.kernel.runtime import RuntimeGovernor
from app.kernel.swarm import SwarmKernel


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "benchmarks" / "results"


def percentile(values: List[float], pct: float) -> float:
    values = sorted(values)
    if not values:
        return 0.0
    index = min(len(values) - 1, max(0, int(round((pct / 100.0) * (len(values) - 1)))))
    return values[index]


def summarize(values: List[float]) -> Dict[str, float]:
    return {
        "min": round(min(values), 6),
        "median": round(statistics.median(values), 6),
        "mean": round(statistics.mean(values), 6),
        "p95": round(percentile(values, 95), 6),
        "max": round(max(values), 6),
    }


def pct_reduction(before: float, after: float) -> float:
    if before == 0:
        return 0.0
    return round(((before - after) / before) * 100.0, 4)


def estimate_tokens(text_or_messages: Any) -> int:
    if isinstance(text_or_messages, list):
        chars = sum(len(str(item.get("content", ""))) for item in text_or_messages)
    else:
        chars = len(str(text_or_messages))
    return max(1, chars // 4)


def benchmark_latency() -> Dict[str, Any]:
    """Compare Python copy-heavy file processing with mmap-backed processing."""
    host_capabilities = os_bypass_capabilities()
    payload_size = 8 * 1024 * 1024
    iterations = 80
    pattern = (b"BEAST-telemetry-frame:" + bytes(range(64))) * (payload_size // 85)
    fd, path = tempfile.mkstemp(prefix="beast-latency-", suffix=".bin")
    os.close(fd)
    Path(path).write_bytes(pattern[:payload_size])

    def copy_proxy() -> int:
        with open(path, "rb") as handle:
            data = handle.read()
        copied = bytes(data)
        return zlib.crc32(copied)

    def mmap_proxy() -> int:
        with open(path, "rb") as handle:
            with mmap.mmap(handle.fileno(), 0, access=mmap.ACCESS_READ) as mapped:
                return zlib.crc32(mapped)

    copy_ms = []
    mmap_ms = []
    for _ in range(5):
        copy_proxy()
        mmap_proxy()
    for _ in range(iterations):
        start = time.perf_counter()
        copy_proxy()
        copy_ms.append((time.perf_counter() - start) * 1000.0)
        start = time.perf_counter()
        mmap_proxy()
        mmap_ms.append((time.perf_counter() - start) * 1000.0)

    Path(path).unlink(missing_ok=True)
    copy_summary = summarize(copy_ms)
    mmap_summary = summarize(mmap_ms)
    return {
        "claim_scope": "Measured local Python read/copy versus mmap-backed read path. Native AF_PACKET mmap, DPDK, and AF_XDP capability probes are reported separately from packet-forwarding throughput.",
        "host_capabilities": host_capabilities,
        "payload_bytes": payload_size,
        "iterations": iterations,
        "traditional_application_proxy_ms": copy_summary,
        "mmap_zero_copy_like_ms": mmap_summary,
        "median_latency_reduction_percent": pct_reduction(copy_summary["median"], mmap_summary["median"]),
        "p95_latency_reduction_percent": pct_reduction(copy_summary["p95"], mmap_summary["p95"]),
        "os_bypass_status": os_bypass_status(host_capabilities),
    }


def os_bypass_status(host_capabilities: Dict[str, Any]) -> Dict[str, Any]:
    dpdk = host_capabilities.get("dpdk", {})
    af_xdp = host_capabilities.get("af_xdp", {})
    missing_dpdk = [
        name for name, path in dpdk.get("libraries", {}).items()
        if path is None and name in {"rte_eal", "rte_ethdev"}
    ]
    missing_af_xdp = [
        name for name, path in af_xdp.get("libraries", {}).items()
        if path is None
    ]
    if dpdk.get("available") and af_xdp.get("available"):
        status = "native_backends_available"
    elif missing_dpdk or missing_af_xdp:
        status = "native_libraries_missing"
    else:
        status = "native_backends_not_ready"
    return {
        "status": status,
        "af_packet_ready": host_capabilities.get("supported_modes", {}).get("af_packet_tpacket_v3_mmap", False),
        "dpdk_ready": bool(dpdk.get("available")),
        "af_xdp_ready": bool(af_xdp.get("available")),
        "missing_dpdk_libraries": missing_dpdk,
        "missing_af_xdp_libraries": missing_af_xdp,
        "install_hint_debian": "sudo apt-get update && sudo apt-get install -y dpdk libdpdk-dev libxdp1 libxdp-dev libbpf-dev",
    }


def generate_telemetry_events(count: int = 12000) -> List[Dict[str, Any]]:
    random.seed(7)
    events = []
    for index in range(count):
        outlier = index % 97 == 0
        events.append({
            "site": "plant-a",
            "line": "extruder-7",
            "asset": f"motor-{index % 24:02d}",
            "ts": 1_783_900_000 + index,
            "temperature_c": round(71.0 + random.random() * 4 + (35 if outlier else 0), 3),
            "vibration_mm_s": round(1.2 + random.random() * 0.3 + (8 if outlier else 0), 4),
            "pressure_bar": round(12.0 + random.random() * 0.4, 4),
            "status": "alarm" if outlier else "nominal",
            "operator_note": "steady state telemetry frame with repeated structure",
        })
    return events


def benchmark_bandwidth() -> Dict[str, Any]:
    compressor = ASTCompressor()
    telemetry = generate_telemetry_events()
    raw_telemetry = json.dumps(telemetry, separators=(",", ":")).encode()
    telemetry_result = compressor.compress_json(telemetry)
    schema_payload = zlib.decompress(__import__("base64").b64decode(telemetry_result.payload.encode("ascii")))

    tool_block = "\n".join(
        f"def tool_{i}(payload):\n    return {{'tool': 'tool_{i}', 'status': 'ok', 'payload': payload}}\n"
        for i in range(600)
    )
    raw_agentic = tool_block.encode()
    ast_result = compressor.compress_python_summary(tool_block)
    ast_payload = zlib.decompress(__import__("base64").b64decode(ast_result.payload.encode("ascii")))

    return {
        "claim_scope": "Implemented ASTCompressor measured for lossless JSON schema-row telemetry and semantic Python AST compression.",
        "industrial_telemetry": {
            "records": len(telemetry),
            "raw_bytes": len(raw_telemetry),
            "schema_rows_bytes": len(schema_payload),
            "compressed_bytes": telemetry_result.compressed_bytes,
            "raw_gzip_bytes": len(zlib.compress(raw_telemetry, 6)),
            "schema_rows_gzip_bytes": telemetry_result.compressed_bytes,
            "schema_rows_reduction_percent": pct_reduction(len(raw_telemetry), len(schema_payload)),
            "schema_rows_gzip_reduction_percent": pct_reduction(len(zlib.compress(raw_telemetry, 6)), telemetry_result.compressed_bytes),
        },
        "complex_agentic_payload": {
            "raw_bytes": len(raw_agentic),
            "ast_semantic_summary_bytes": len(ast_payload),
            "raw_gzip_bytes": len(zlib.compress(raw_agentic, 6)),
            "ast_compressed_bytes": ast_result.compressed_bytes,
            "ast_semantic_summary_reduction_percent": pct_reduction(len(raw_agentic), len(ast_payload)),
            "ast_compressed_reduction_percent": pct_reduction(len(zlib.compress(raw_agentic, 6)), ast_result.compressed_bytes),
        },
    }


def benchmark_loop_protection() -> Dict[str, Any]:
    policies = {
        "meta_rules": {
            "circuit_breaker_enabled": True,
            "circuit_breaker_failure_threshold": 5,
            "circuit_breaker_timeout_seconds": 60,
            "stasis_wall_enabled": False,
            "runtime_provider_timeout_seconds": 10,
        }
    }
    with tempfile.TemporaryDirectory(prefix="beast-runtime-") as temp_dir:
        governor = RuntimeGovernor(policies=policies, db_path=str(Path(temp_dir) / "runtime.db"))
        start = time.perf_counter()
        accepted = 0
        rejected_at = None
        while True:
            admission = governor.begin_execution("recursive_agent", "loop-test", session_id="loop-bench")
            if not admission.allowed:
                rejected_at = time.perf_counter()
                break
            accepted += 1
            governor.complete_execution(admission.attempt_id, "recursive_agent", success=False, error_type="recursive_state", error_message="same state repeated")
        protected_elapsed_ms = (rejected_at - start) * 1000.0

    uncontrolled_start = time.perf_counter()
    uncontrolled_iterations = 0
    while (time.perf_counter() - uncontrolled_start) < 0.25:
        uncontrolled_iterations += 1
    uncontrolled_elapsed = time.perf_counter() - uncontrolled_start
    uncontrolled_rate = uncontrolled_iterations / uncontrolled_elapsed

    return {
        "claim_scope": "Implemented RuntimeGovernor circuit breaker measured against an uncontrolled tight recursive loop baseline.",
        "failure_threshold": 5,
        "accepted_failures_before_interrupt": accepted,
        "time_to_interruption_ms": round(protected_elapsed_ms, 6),
        "uncontrolled_iterations_per_second": round(uncontrolled_rate, 2),
        "uncontrolled_iterations_during_protected_window_estimate": round(uncontrolled_rate * (protected_elapsed_ms / 1000.0), 2),
        "interruption_result": "blocked_by_circuit_breaker",
    }


def benchmark_cost_efficiency() -> Dict[str, Any]:
    compressor = ASTCompressor()
    telemetry = generate_telemetry_events()
    forest = IsolationForest(n_trees=100, sample_size=256, contamination=0.011, random_state=19)
    forest.fit(telemetry, features=["temperature_c", "vibration_mm_s", "pressure_bar"])
    predictions = forest.predict(telemetry)
    filtered = [record for record, prediction in zip(telemetry, predictions) if not prediction["is_outlier"]]
    raw_telemetry = json.dumps(telemetry, separators=(",", ":"))
    filtered_telemetry_result = compressor.compress_json(filtered)
    filtered_telemetry = zlib.decompress(__import__("base64").b64decode(filtered_telemetry_result.payload.encode("ascii"))).decode("utf-8")

    repeated_messages = [
        {"role": "system", "content": "Preserve safety and budget governance."},
        {"role": "user", "content": "redundant diagnostic context " * 9000},
        {"role": "assistant", "content": "ack " * 4000},
        {"role": "user", "content": "Give the next actionable anomaly summary only."},
    ]
    policies = {
        "meta_rules": {
            "context_economizer_enabled": True,
            "max_input_tokens_per_request": 8000,
            "context_compression_trigger_ratio": 0.85,
            "context_compression_ratio_target": 0.3,
            "context_economizer_min_recent_messages": 2,
            "context_economizer_max_message_chars": 12000,
            "context_economizer_preserve_system": True,
        }
    }
    economy = ContextEconomizer(policies).economize(EdgeKIR(messages=repeated_messages, model="cost-bench", max_tokens=128))

    raw_tokens = estimate_tokens(raw_telemetry) + estimate_tokens(repeated_messages)
    filtered_tokens = estimate_tokens(filtered_telemetry) + economy.final_tokens
    pricing = {
        "openrouter_llama_3_1_8b_observed_usd_per_1k_total_tokens": 0.0000265,
        "nvidia_nim_smoke_observed_usd_per_1k_total_tokens": 0.0,
    }
    openrouter_before = (raw_tokens / 1000.0) * pricing["openrouter_llama_3_1_8b_observed_usd_per_1k_total_tokens"]
    openrouter_after = (filtered_tokens / 1000.0) * pricing["openrouter_llama_3_1_8b_observed_usd_per_1k_total_tokens"]

    return {
        "claim_scope": "ContextEconomizer, ASTCompressor, and IsolationForest are implemented and measured locally.",
        "telemetry_records_raw": len(telemetry),
        "telemetry_records_after_outlier_filter": len(filtered),
        "outlier_records_filtered": len(telemetry) - len(filtered),
        "isolation_forest": forest.state(),
        "context_economizer": {
            "original_tokens": economy.original_tokens,
            "final_tokens": economy.final_tokens,
            "token_reduction_percent": pct_reduction(economy.original_tokens, economy.final_tokens),
            "chars_removed": economy.chars_removed,
        },
        "combined_raw_estimated_tokens": raw_tokens,
        "combined_filtered_estimated_tokens": filtered_tokens,
        "combined_token_reduction_percent": pct_reduction(raw_tokens, filtered_tokens),
        "estimated_transaction_fee_before_usd": round(openrouter_before, 8),
        "estimated_transaction_fee_after_usd": round(openrouter_after, 8),
        "estimated_transaction_fee_reduction_usd": round(openrouter_before - openrouter_after, 8),
        "estimated_transaction_fee_reduction_percent": pct_reduction(openrouter_before, openrouter_after),
        "pricing_basis": pricing,
    }


def benchmark_tool_laziness() -> Dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="beast-tool-laziness-") as temp_dir:
        learner = ToolLazinessLearner(db_path=str(Path(temp_dir) / "tool_laziness.db"))
        basic = learner.benchmark_learning()
        return {
            **basic,
            "high_token_schema_laziness": learner.benchmark_schema_laziness(
                tool_count=96,
                turns=64,
                relevant_tools_per_turn=6,
            ),
        }


def benchmark_swarm() -> Dict[str, Any]:
    scenarios = []
    for index in range(48):
        if index % 12 == 0:
            scenarios.append({
                "objective": "Deploy to production and delete stale migration data",
                "context": "release checklist " * 5000,
                "target_context_tokens": 1800,
            })
        elif index % 8 == 0:
            scenarios.append({
                "objective": "Fix failing pytest import loop",
                "context": "traceback import failure " * 6000,
                "target_context_tokens": 2200,
                "execution_result": {"success": False, "error": "ImportError loop"},
                "model_based_critic": True,
            })
        elif index % 5 == 0:
            scenarios.append({
                "objective": "Refactor module and run targeted tests",
                "context": "code context " * 9000,
                "target_context_tokens": 2600,
                "files": ["app/kernel/reason.py", "app/kernel/tool_laziness.py"],
                "execution_result": {"success": True},
            })
        else:
            scenarios.append({
                "objective": "Update documentation and summarize gateway state",
                "context": "docs context " * 3500,
                "target_context_tokens": 1600,
                "execution_result": {"success": True},
            })

    with tempfile.TemporaryDirectory(prefix="beast-swarm-") as temp_dir:
        kernel = SwarmKernel(
            policies={"swarm": {"enabled": True}},
            db_path=str(Path(temp_dir) / "swarm.db"),
        )
        runs = [kernel.run(scenario) for scenario in scenarios]
        status_counts: Dict[str, int] = {}
        role_counts: Dict[str, int] = {}
        for run in runs:
            status_counts[run["status"]] = status_counts.get(run["status"], 0) + 1
            for event in run["events"]:
                role_counts[event["role"]] = role_counts.get(event["role"], 0) + 1
        total_tokens_saved = sum(float(run["value"].get("estimated_tokens_saved", 0)) for run in runs)
        avoided_model_calls = sum(float(run["value"].get("avoided_model_calls", 0)) for run in runs)
        blocked_risk_events = sum(float(run["value"].get("blocked_risk_events", 0)) for run in runs)
        return {
            "claim_scope": "SwarmKernel is deterministic orchestration, not a multi-model call multiplier.",
            "runs": len(runs),
            "status_counts": status_counts,
            "role_event_counts": role_counts,
            "estimated_tokens_saved": round(total_tokens_saved, 2),
            "avoided_model_calls": round(avoided_model_calls, 2),
            "blocked_risk_events": round(blocked_risk_events, 2),
            "average_expected_value_score": round(
                sum(float(run["value"].get("expected_value_score", 0)) for run in runs) / max(1, len(runs)),
                4,
            ),
            "state": kernel.state(),
        }


def write_markdown(report: Dict[str, Any], md_path: Path) -> None:
    lines = [
        "# EdgeK BEAST Metrics Benchmark",
        "",
        f"Generated at: `{report['generated_at']}`",
        "",
        "## Implementation Boundary",
        "",
        "- Runtime circuit breaker: implemented and measured.",
        "- Context economizer / semantic compression: implemented and measured.",
        "- Zero-copy memory mapping: local `mmap`, AF_PACKET mmap, and native DPDK/AF_XDP probes are implemented.",
        "- AST compression engine: implemented for lossless JSON schema rows, reconstructive Python AST canonicalization, and semantic Python AST summaries.",
        "- Isolation Forest: implemented as a deterministic pure-Python edge outlier filter.",
        "",
        "## Latency",
        "",
        f"- Traditional median: `{report['latency']['traditional_application_proxy_ms']['median']} ms`",
        f"- mmap median: `{report['latency']['mmap_zero_copy_like_ms']['median']} ms`",
        f"- Median reduction: `{report['latency']['median_latency_reduction_percent']}%`",
        f"- OS-bypass status: `{report['latency']['os_bypass_status']['status']}`",
        f"- DPDK ready: `{report['latency']['os_bypass_status']['dpdk_ready']}`",
        f"- AF_XDP ready: `{report['latency']['os_bypass_status']['af_xdp_ready']}`",
        f"- Missing DPDK libs: `{', '.join(report['latency']['os_bypass_status']['missing_dpdk_libraries']) or 'none'}`",
        f"- Missing AF_XDP libs: `{', '.join(report['latency']['os_bypass_status']['missing_af_xdp_libraries']) or 'none'}`",
        "",
        "## Bandwidth",
        "",
        f"- Telemetry raw bytes: `{report['bandwidth']['industrial_telemetry']['raw_bytes']}`",
        f"- Telemetry schema bytes: `{report['bandwidth']['industrial_telemetry']['schema_rows_bytes']}`",
        f"- Telemetry reduction: `{report['bandwidth']['industrial_telemetry']['schema_rows_reduction_percent']}%`",
        f"- Agentic raw bytes: `{report['bandwidth']['complex_agentic_payload']['raw_bytes']}`",
        f"- Agentic AST semantic-summary bytes: `{report['bandwidth']['complex_agentic_payload']['ast_semantic_summary_bytes']}`",
        f"- Agentic reduction: `{report['bandwidth']['complex_agentic_payload']['ast_semantic_summary_reduction_percent']}%`",
        "",
        "## Loop Protection",
        "",
        f"- Time to interruption: `{report['loop_protection']['time_to_interruption_ms']} ms`",
        f"- Accepted failures before interrupt: `{report['loop_protection']['accepted_failures_before_interrupt']}`",
        f"- Uncontrolled loop rate: `{report['loop_protection']['uncontrolled_iterations_per_second']} iterations/s`",
        "",
        "## Cost Efficiency",
        "",
        f"- Raw estimated tokens: `{report['cost_efficiency']['combined_raw_estimated_tokens']}`",
        f"- Filtered/compressed estimated tokens: `{report['cost_efficiency']['combined_filtered_estimated_tokens']}`",
        f"- Token reduction: `{report['cost_efficiency']['combined_token_reduction_percent']}%`",
        f"- Estimated OpenRouter fee before: `${report['cost_efficiency']['estimated_transaction_fee_before_usd']}`",
        f"- Estimated OpenRouter fee after: `${report['cost_efficiency']['estimated_transaction_fee_after_usd']}`",
        f"- Fee reduction: `${report['cost_efficiency']['estimated_transaction_fee_reduction_usd']}` / `{report['cost_efficiency']['estimated_transaction_fee_reduction_percent']}%`",
        "",
        "## Tool Laziness Learning",
        "",
        f"- Final decision: `{report['tool_laziness']['final_recommendation']['decision']}`",
        f"- Final reason: `{report['tool_laziness']['final_recommendation']['reason']}`",
        f"- Rare critical decision: `{report['tool_laziness']['critical_final_recommendation']['decision']}`",
        f"- Rare critical reason: `{report['tool_laziness']['critical_final_recommendation']['reason']}`",
        f"- Projected 100-call tokens avoided: `{report['tool_laziness']['projected_100_redundant_calls']['tokens_avoided']}`",
        f"- Projected 100-call cost avoided: `${report['tool_laziness']['projected_100_redundant_calls']['cost_avoided_usd']}`",
        f"- High-token static total: `{report['tool_laziness']['high_token_schema_laziness']['static_total_tokens']}`",
        f"- High-token lazy total: `{report['tool_laziness']['high_token_schema_laziness']['lazy_total_tokens']}`",
        f"- High-token reduction: `{report['tool_laziness']['high_token_schema_laziness']['token_reduction_percent']}%`",
        f"- High-token skipped calls: `{report['tool_laziness']['high_token_schema_laziness']['skipped_calls']}`",
        f"- High-token latency avoided: `{report['tool_laziness']['high_token_schema_laziness']['latency_avoided_ms']} ms`",
        "",
        "## Swarm",
        "",
        f"- Runs: `{report['swarm']['runs']}`",
        f"- Status counts: `{report['swarm']['status_counts']}`",
        f"- Role event counts: `{report['swarm']['role_event_counts']}`",
        f"- Estimated tokens saved: `{report['swarm']['estimated_tokens_saved']}`",
        f"- Avoided model calls: `{report['swarm']['avoided_model_calls']}`",
        f"- Blocked risk events: `{report['swarm']['blocked_risk_events']}`",
        f"- Average expected value score: `{report['swarm']['average_expected_value_score']}`",
        "",
    ]
    md_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    report = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "latency": benchmark_latency(),
        "bandwidth": benchmark_bandwidth(),
        "loop_protection": benchmark_loop_protection(),
        "cost_efficiency": benchmark_cost_efficiency(),
        "tool_laziness": benchmark_tool_laziness(),
        "swarm": benchmark_swarm(),
    }
    json_path = OUT_DIR / "edge_metrics_benchmark.json"
    md_path = OUT_DIR / "edge_metrics_benchmark.md"
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    write_markdown(report, md_path)
    print(json.dumps({
        "json_report": str(json_path),
        "markdown_report": str(md_path),
        "latency_median_reduction_percent": report["latency"]["median_latency_reduction_percent"],
        "telemetry_wan_reduction_percent": report["bandwidth"]["industrial_telemetry"]["schema_rows_reduction_percent"],
        "loop_time_to_interruption_ms": report["loop_protection"]["time_to_interruption_ms"],
        "cost_token_reduction_percent": report["cost_efficiency"]["combined_token_reduction_percent"],
        "tool_laziness_decision": report["tool_laziness"]["final_recommendation"]["decision"],
        "tool_laziness_high_token_reduction_percent": report["tool_laziness"]["high_token_schema_laziness"]["token_reduction_percent"],
        "swarm_runs": report["swarm"]["runs"],
    }, indent=2))


if __name__ == "__main__":
    main()

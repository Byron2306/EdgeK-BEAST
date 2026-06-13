#!/usr/bin/env python3
"""Compare cloud APIs and local NIM with and without BEAST edge governance.

The runner treats NVIDIA hosted NIM, OpenRouter, and local NIM as
OpenAI-compatible chat endpoints. For each configured provider it executes the
same scenarios twice:

* raw: payload sent as a normal application would send it.
* beast: telemetry is outlier-filtered, structurally compressed, and long
  context is economized before the provider call.

The local NIM leg is intentionally a standard NIM endpoint. The value being
measured is what BEAST adds around it: governance, AST/structural payload
management, token shaping, and forensic accounting.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import statistics
import time
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import httpx

from app.context.economizer import ContextEconomizer
from app.kernel.ast_compressor import ASTCompressor
from app.kernel.isolation_forest import IsolationForest
from app.kernel.perceive import EdgeKIR


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "benchmarks" / "results"


@dataclass
class ProviderConfig:
    name: str
    base_url: str
    model: str
    api_key: Optional[str] = None
    extra_headers: Optional[Dict[str, str]] = None
    nominal_cost_per_1k_tokens: float = 0.0


def estimate_tokens(messages: List[Dict[str, Any]]) -> int:
    chars = 0
    for message in messages:
        content = message.get("content", "")
        chars += len(content if isinstance(content, str) else json.dumps(content, separators=(",", ":")))
    return max(1, chars // 4)


def pct_reduction(before: float, after: float) -> float:
    if before == 0:
        return 0.0
    return round(((before - after) / before) * 100.0, 4)


def generate_telemetry(count: int = 640) -> List[Dict[str, Any]]:
    rows = []
    for index in range(count):
        outlier = index % 89 == 0
        rows.append({
            "site": "edge-plant-a",
            "line": "extruder-7",
            "asset": f"motor-{index % 32:02d}",
            "ts": 1_783_900_000 + index,
            "temperature_c": round(71.5 + ((index * 17) % 40) / 10.0 + (38.0 if outlier else 0.0), 3),
            "vibration_mm_s": round(1.1 + ((index * 13) % 20) / 100.0 + (7.5 if outlier else 0.0), 4),
            "pressure_bar": round(12.0 + ((index * 19) % 18) / 100.0, 4),
            "status": "alarm" if outlier else "nominal",
            "operator_note": "high-frequency telemetry frame with repeated schema",
        })
    return rows


def build_scenarios() -> List[Dict[str, Any]]:
    telemetry_count = int(os.environ.get("PROVIDER_COMPARE_TELEMETRY_COUNT", "640"))
    context_repeats = int(os.environ.get("PROVIDER_COMPARE_CONTEXT_REPEATS", "900"))
    tool_count = int(os.environ.get("PROVIDER_COMPARE_TOOL_COUNT", "180"))
    telemetry = generate_telemetry(count=max(12, telemetry_count))
    repeated_context = " ".join([
        "historical diagnostic context says the equipment is nominal unless vibration and temperature spike together"
        for _ in range(max(12, context_repeats))
    ])
    tool_catalog = "\n".join(
        f"def tool_{i}(payload): return {{'name': 'tool_{i}', 'ok': True, 'payload': payload}}"
        for i in range(max(12, tool_count))
    )
    return [
        {
            "name": "industrial_telemetry_anomaly_triage",
            "kind": "telemetry",
            "telemetry": telemetry,
            "prompt": (
                "Identify the top operational anomaly, cite the asset id, and return exactly "
                "three concise remediation steps."
            ),
        },
        {
            "name": "long_context_redundant_agent_state",
            "kind": "context",
            "context": repeated_context,
            "prompt": "From this history, give only the next best action and one risk.",
        },
        {
            "name": "agentic_tool_surface_summary",
            "kind": "python_tools",
            "source": tool_catalog,
            "prompt": "Summarize the tool surface by capability families and identify redundant tools.",
        },
    ]


def raw_messages(scenario: Dict[str, Any]) -> List[Dict[str, Any]]:
    if scenario["kind"] == "telemetry":
        body = json.dumps(scenario["telemetry"], separators=(",", ":"))
    elif scenario["kind"] == "context":
        body = scenario["context"]
    else:
        body = scenario["source"]
    return [
        {"role": "system", "content": "You are a terse industrial edge AI operator."},
        {"role": "user", "content": f"{scenario['prompt']}\n\nPayload:\n{body}"},
    ]


def beast_messages(scenario: Dict[str, Any]) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
    compressor = ASTCompressor()
    metadata: Dict[str, Any] = {"governance": "edgek_beast_preprocessed"}

    if scenario["kind"] == "telemetry":
        telemetry = scenario["telemetry"]
        forest = IsolationForest(n_trees=80, sample_size=128, contamination=0.02, random_state=23)
        forest.fit(telemetry, features=["temperature_c", "vibration_mm_s", "pressure_bar"])
        predictions = forest.predict(telemetry)
        kept = [row for row, prediction in zip(telemetry, predictions) if not prediction["is_outlier"]]
        anomalous = [row for row, prediction in zip(telemetry, predictions) if prediction["is_outlier"]][:12]
        compressed = compressor.compress_json(kept)
        structural = zlib.decompress(base64.b64decode(compressed.payload.encode("ascii"))).decode("utf-8")
        body = {
            "filtered_record_count": len(kept),
            "outlier_count": len(telemetry) - len(kept),
            "top_outlier_examples": anomalous,
            "lossless_schema_rows_for_nominal_context": json.loads(structural),
        }
        metadata.update({
            "isolation_forest": forest.state(),
            "ast_compression": compressed.to_dict() | {"payload": "<omitted>"},
        })
        messages = [
            {"role": "system", "content": "You are a governed BEAST edge AI operator. Prefer anomaly evidence over raw volume."},
            {"role": "user", "content": f"{scenario['prompt']}\n\nBEAST-managed payload:\n{json.dumps(body, separators=(',', ':'))}"},
        ]
    elif scenario["kind"] == "context":
        original = [
            {"role": "system", "content": "You are a governed BEAST edge AI operator."},
            {"role": "user", "content": scenario["context"]},
            {"role": "user", "content": scenario["prompt"]},
        ]
        policies = {
            "meta_rules": {
                "context_economizer_enabled": True,
                "max_input_tokens_per_request": 4500,
                "context_compression_trigger_ratio": 0.5,
                "context_compression_ratio_target": 0.55,
                "context_economizer_min_recent_messages": 1,
                "context_economizer_max_message_chars": 7000,
                "context_economizer_preserve_system": True,
            }
        }
        economy = ContextEconomizer(policies).economize(EdgeKIR(messages=original, model="provider-edge-compare", max_tokens=128))
        messages = economy.ir.messages
        metadata["context_economy"] = {
            "changed": economy.changed,
            "original_tokens": economy.original_tokens,
            "final_tokens": economy.final_tokens,
            "chars_removed": economy.chars_removed,
            "strategy": economy.strategy,
        }
    else:
        summary = compressor.compress_python_summary(scenario["source"])
        body = zlib.decompress(base64.b64decode(summary.payload.encode("ascii"))).decode("utf-8")
        metadata["ast_compression"] = summary.to_dict() | {"payload": "<omitted>"}
        messages = [
            {"role": "system", "content": "You are a governed BEAST edge AI operator. Interpret AST summaries directly."},
            {"role": "user", "content": f"{scenario['prompt']}\n\nPython AST summary:\n{body}"},
        ]

    return messages, metadata


def configured_providers() -> List[ProviderConfig]:
    providers: List[ProviderConfig] = []
    if os.environ.get("NVIDIA_API_KEY"):
        providers.append(ProviderConfig(
            name="nvidia_cloud_nim",
            base_url=os.environ.get("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1").rstrip("/"),
            model=os.environ.get("NVIDIA_MODEL", "meta/llama-3.1-8b-instruct"),
            api_key=os.environ["NVIDIA_API_KEY"],
            nominal_cost_per_1k_tokens=float(os.environ.get("NVIDIA_COST_PER_1K_TOKENS", "0")),
        ))
    if os.environ.get("OPENROUTER_API_KEY"):
        providers.append(ProviderConfig(
            name="openrouter",
            base_url=os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1").rstrip("/"),
            model=os.environ.get("OPENROUTER_MODEL", "meta-llama/llama-3.1-8b-instruct"),
            api_key=os.environ["OPENROUTER_API_KEY"],
            extra_headers={
                "HTTP-Referer": os.environ.get("OPENROUTER_SITE_URL", "http://localhost"),
                "X-Title": os.environ.get("OPENROUTER_APP_NAME", "EdgeK BEAST Gateway"),
            },
            nominal_cost_per_1k_tokens=float(os.environ.get("OPENROUTER_COST_PER_1K_TOKENS", "0.0000265")),
        ))
    if os.environ.get("LOCAL_NIM_BASE_URL") and os.environ.get("LOCAL_NIM_SCOUT_ONLY", "0") != "1":
        providers.append(ProviderConfig(
            name=os.environ.get("LOCAL_NIM_NAME", "local_nim_edge_gpu"),
            base_url=os.environ["LOCAL_NIM_BASE_URL"].rstrip("/"),
            model=os.environ.get("LOCAL_NIM_MODEL", "local-nim-model"),
            api_key=os.environ.get("LOCAL_NIM_API_KEY"),
            nominal_cost_per_1k_tokens=float(os.environ.get("LOCAL_NIM_COST_PER_1K_TOKENS", "0")),
        ))
    return providers


def provider_headers(provider: ProviderConfig) -> Dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if provider.api_key:
        headers["Authorization"] = f"Bearer {provider.api_key}"
    if provider.extra_headers:
        headers.update(provider.extra_headers)
    return headers


def usage_tokens(response: Dict[str, Any], fallback_messages: List[Dict[str, Any]]) -> Dict[str, int]:
    usage = response.get("usage") or {}
    prompt = int(usage.get("prompt_tokens") or usage.get("input_tokens") or estimate_tokens(fallback_messages))
    completion = int(usage.get("completion_tokens") or usage.get("output_tokens") or 0)
    total = int(usage.get("total_tokens") or prompt + completion)
    return {"prompt_tokens": prompt, "completion_tokens": completion, "total_tokens": total}


def call_provider(client: httpx.Client, provider: ProviderConfig, messages: List[Dict[str, Any]], timeout: float) -> Dict[str, Any]:
    payload = {
        "model": provider.model,
        "messages": messages,
        "max_tokens": int(os.environ.get("PROVIDER_COMPARE_MAX_TOKENS", "160")),
        "temperature": float(os.environ.get("PROVIDER_COMPARE_TEMPERATURE", "0")),
    }
    started = time.perf_counter()
    response = client.post(
        f"{provider.base_url}/chat/completions",
        headers=provider_headers(provider),
        json=payload,
        timeout=timeout,
    )
    latency_ms = (time.perf_counter() - started) * 1000.0
    response.raise_for_status()
    body = response.json()
    usage = usage_tokens(body, messages)
    return {
        "ok": True,
        "latency_ms": round(latency_ms, 3),
        "usage": usage,
        "estimated_cost_usd": round((usage["total_tokens"] / 1000.0) * provider.nominal_cost_per_1k_tokens, 8),
        "response_id": body.get("id"),
        "finish_reason": (((body.get("choices") or [{}])[0]).get("finish_reason")),
    }


def summarize_runs(runs: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    items = list(runs)
    successes = [item for item in items if item.get("ok")]
    latencies = [item["latency_ms"] for item in successes]
    total_tokens = sum(item.get("usage", {}).get("total_tokens", 0) for item in successes)
    total_cost = sum(item.get("estimated_cost_usd", 0.0) for item in successes)
    return {
        "attempts": len(items),
        "successes": len(successes),
        "failures": len(items) - len(successes),
        "median_latency_ms": round(statistics.median(latencies), 3) if latencies else None,
        "mean_latency_ms": round(statistics.mean(latencies), 3) if latencies else None,
        "total_tokens": total_tokens,
        "estimated_cost_usd": round(total_cost, 8),
    }


def run_compare(timeout: float = 90.0, repeats: int = 1, dry_run: bool = False) -> Dict[str, Any]:
    scenarios = build_scenarios()
    providers = configured_providers()
    report: Dict[str, Any] = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "claim_scope": "Cloud APIs and local NIM are compared as OpenAI-compatible inference endpoints; BEAST impact is measured as edge preprocessing/governance around those endpoints.",
        "configured_providers": [provider.name for provider in providers],
        "scenarios": [],
        "summary": {},
    }

    for scenario in scenarios:
        raw = raw_messages(scenario)
        beast, metadata = beast_messages(scenario)
        report["scenarios"].append({
            "name": scenario["name"],
            "raw_estimated_prompt_tokens": estimate_tokens(raw),
            "beast_estimated_prompt_tokens": estimate_tokens(beast),
            "estimated_prompt_token_reduction_percent": pct_reduction(estimate_tokens(raw), estimate_tokens(beast)),
            "beast_metadata": metadata,
        })

    if dry_run or not providers:
        report["summary"]["note"] = "No provider calls executed. Set API env vars or remove --dry-run."
        return report

    runs: List[Dict[str, Any]] = []
    with httpx.Client() as client:
        for provider in providers:
            for scenario in scenarios:
                for mode in ("raw", "beast"):
                    messages = raw_messages(scenario) if mode == "raw" else beast_messages(scenario)[0]
                    for iteration in range(repeats):
                        record = {
                            "provider": provider.name,
                            "model": provider.model,
                            "scenario": scenario["name"],
                            "mode": mode,
                            "iteration": iteration,
                            "estimated_prompt_tokens": estimate_tokens(messages),
                        }
                        try:
                            record.update(call_provider(client, provider, messages, timeout))
                        except Exception as exc:  # pragma: no cover - exercised in live runs
                            record.update({"ok": False, "error": str(exc)[:1000]})
                        runs.append(record)

    report["runs"] = runs
    for provider in providers:
        provider_runs = [run for run in runs if run["provider"] == provider.name]
        raw_runs = [run for run in provider_runs if run["mode"] == "raw"]
        beast_runs = [run for run in provider_runs if run["mode"] == "beast"]
        raw_summary = summarize_runs(raw_runs)
        beast_summary = summarize_runs(beast_runs)
        report["summary"][provider.name] = {
            "raw": raw_summary,
            "beast": beast_summary,
            "observed_total_token_reduction_percent": pct_reduction(raw_summary["total_tokens"], beast_summary["total_tokens"]),
            "observed_cost_reduction_percent": pct_reduction(raw_summary["estimated_cost_usd"], beast_summary["estimated_cost_usd"]),
            "observed_median_latency_delta_ms": (
                round((beast_summary["median_latency_ms"] or 0) - (raw_summary["median_latency_ms"] or 0), 3)
                if raw_summary["median_latency_ms"] is not None and beast_summary["median_latency_ms"] is not None
                else None
            ),
        }
    return report


def write_markdown(report: Dict[str, Any], path: Path) -> None:
    lines = [
        "# Provider Edge Compare",
        "",
        f"Generated at: `{report['generated_at']}`",
        "",
        report["claim_scope"],
        "",
        "## Scenario Token Shaping",
        "",
    ]
    for scenario in report["scenarios"]:
        lines.extend([
            f"- `{scenario['name']}` raw `{scenario['raw_estimated_prompt_tokens']}` tokens, BEAST `{scenario['beast_estimated_prompt_tokens']}` tokens, reduction `{scenario['estimated_prompt_token_reduction_percent']}%`",
        ])
    lines.extend(["", "## Provider Summary", ""])
    for provider, summary in report.get("summary", {}).items():
        if provider == "note":
            lines.append(f"- {summary}")
            continue
        lines.extend([
            f"### {provider}",
            f"- Raw successes: `{summary['raw']['successes']}/{summary['raw']['attempts']}`; median latency `{summary['raw']['median_latency_ms']} ms`; tokens `{summary['raw']['total_tokens']}`; cost `${summary['raw']['estimated_cost_usd']}`",
            f"- BEAST successes: `{summary['beast']['successes']}/{summary['beast']['attempts']}`; median latency `{summary['beast']['median_latency_ms']} ms`; tokens `{summary['beast']['total_tokens']}`; cost `${summary['beast']['estimated_cost_usd']}`",
            f"- Observed token reduction: `{summary['observed_total_token_reduction_percent']}%`",
            f"- Observed cost reduction: `{summary['observed_cost_reduction_percent']}%`",
            f"- Median latency delta: `{summary['observed_median_latency_delta_ms']} ms`",
            "",
        ])
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare cloud APIs and local NIM through BEAST payload management.")
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--timeout", type=float, default=90.0)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--out-prefix", default="provider_edge_compare")
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    report = run_compare(timeout=args.timeout, repeats=max(1, args.repeats), dry_run=args.dry_run)
    json_path = OUT_DIR / f"{args.out_prefix}.json"
    md_path = OUT_DIR / f"{args.out_prefix}.md"
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    write_markdown(report, md_path)
    print(json.dumps({"json_report": str(json_path), "markdown_report": str(md_path), "summary": report.get("summary", {})}, indent=2))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Measure how much work each BEAST assistance layer leaves for a small model.

The default run is offline and deterministic: it measures exact packet size and
provider-call decisions without pretending that a fake provider is model uplift.
Use ``--live`` to send the baseline and compact lanes to Ollama.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.kernel.agents.ollama_planner_provider import OllamaPlannerProvider
from app.kernel.agents.residual_solver import ResidualSolverBoundary


TASKS = [
    {
        "id": "invoice_percentage_discount",
        "file": "pricing.py",
        "symbol": "apply_discount",
        "current_body": "def apply_discount(amount, percent):\n    return amount - percent\n",
        "failure": "pytest:percentage_discount:subtracts_percent_as_value expected 170 got 185",
        "guidance": ["verified pattern: return amount - (amount * percent / 100)"],
    },
    {
        "id": "provider_registry_default",
        "file": "app/kernel/registry/provider_registry.py",
        "symbol": "ProviderRegistry.records",
        "current_body": "return [ProviderRecord(provider_id=name, backend=config.get('backend', 'litellm')) for name, config in sorted(self.DEFAULTS.items())]",
        "failure": "test_codex_is_routable expected codex default model gpt-5-codex",
        "guidance": ["verified pattern: preserve explicit provider defaults when constructing records"],
    },
    {
        "id": "api_model_resolution",
        "file": "app/cli/api.py",
        "symbol": "BeastApiClient._chat_model_for_provider",
        "current_body": "if model and model != 'beast-auto': return model\nreturn ''",
        "failure": "test_beast_auto_resolves_concrete_models expected a concrete local model",
        "guidance": ["verified pattern: resolve provider aliases through the typed registry"],
    },
]


class MeasuringProvider:
    model = "offline-measuring-provider"

    def __init__(self) -> None:
        self.calls = 0
        self.payloads: list[dict[str, Any]] = []

    async def solve_residual(self, payload: dict[str, Any], *, run: dict[str, Any] | None = None) -> dict[str, Any]:
        self.calls += 1
        self.payloads.append(payload)
        return {"status": "solved", "fields": {"new": "<measured-residual>"}, "usage": {"offline": True}}


class PermitInterceptor:
    class Gate:
        reason = "benchmark provider permitted"

    class Interception:
        def __init__(self) -> None:
            self.gate = PermitInterceptor.Gate()

    def begin(self, request: Any, provider: str) -> Any:
        return self.Interception()

    def execution_route(self, interception: Any) -> str:
        return "provider"

    class Receipt:
        def to_dict(self) -> dict[str, Any]:
            return {"status": "completed", "provider_execution_requested": True}

    def complete(self, *args: Any, **kwargs: Any) -> Any:
        return self.Receipt()


def _full_payload(task: dict[str, Any]) -> dict[str, Any]:
    return {
        "objective": f"Repair {task['id']} in the IDE workspace",
        "target": {"path": task["file"], "symbol": task["symbol"]},
        "current_code": task["current_body"],
        "failure": task["failure"],
        "repository_graph": {"files": [f"file_{i}.py" for i in range(40)], "edges": ["imports", "calls", "tests"] * 30},
        "forge_assistance": {"fingerprint": "sha256:fixture", "selected_files": [task["file"]], "policy": "local_first"},
        "crystal_assistance": {"mode": "scaffolded", "compatible": [], "history": task["guidance"] * 8},
        "action_ir": {"actions": [{"operation": "replace_exact", "target": task["file"], "approval": "operator"}]},
        "unresolved_fields": ["new"],
        "allowed_output": {"new": "complete replacement source"},
    }


async def measure_task(task: dict[str, Any], *, live: bool, model: str, base_url: str, repeats: int, timeout: float) -> dict[str, Any]:
    lanes: dict[str, list[dict[str, Any]]] = {"baseline": [], "compact": [], "crystal": []}
    for iteration in range(repeats):
        full = _full_payload(task)
        baseline_prompt = json.dumps(full, sort_keys=True, default=str)
        baseline_provider = OllamaPlannerProvider(model=model, base_url=base_url, timeout_seconds=timeout, max_retries=0) if live else MeasuringProvider()
        started = time.perf_counter()
        baseline_error = ""
        try:
            if live:
                baseline_result = await baseline_provider.solve_residual(full, run={"benchmark": "baseline"})
            else:
                baseline_result = {"status": "solved", "usage": {"offline": True}}
        except Exception as exc:
            baseline_result = {"status": "error", "usage": getattr(baseline_provider, "last_usage", {})}
            baseline_error = f"{type(exc).__name__}: {exc}"
        lanes["baseline"].append({"iteration": iteration, "prompt_chars": len(baseline_prompt), "provider_called": True, "elapsed_ms": round((time.perf_counter() - started) * 1000, 2), "usage": baseline_result.get("usage", {}), "error": baseline_error})

        compact_provider = OllamaPlannerProvider(model=model, base_url=base_url, timeout_seconds=timeout, max_retries=0) if live else MeasuringProvider()
        started = time.perf_counter()
        compact_error = ""
        try:
            compact_result = await ResidualSolverBoundary(provider=compact_provider, interceptor=PermitInterceptor()).solve({**full, "crystal_guidance": task["guidance"]}, run_id=f"benchmark-{task['id']}-{iteration}")
        except Exception as exc:
            compact_result = {"model_packet": "", "provider_called": True, "usage": getattr(compact_provider, "last_usage", {})}
            compact_error = f"{type(exc).__name__}: {exc}"
        lanes["compact"].append({"iteration": iteration, "prompt_chars": len(compact_result.get("model_packet", "")), "provider_called": compact_result.get("provider_called", False), "elapsed_ms": round((time.perf_counter() - started) * 1000, 2), "usage": compact_result.get("usage", {}), "error": compact_error})

        crystal_provider = MeasuringProvider()
        started = time.perf_counter()
        crystal_result = await ResidualSolverBoundary(provider=crystal_provider, interceptor=PermitInterceptor()).solve({
            "unresolved_fields": [],
            "model_call_required": False,
            "action_template": {"new": "<verified crystal replacement>"},
        }, run_id=f"benchmark-crystal-{task['id']}-{iteration}")
        lanes["crystal"].append({"iteration": iteration, "prompt_chars": 0, "provider_called": crystal_result.get("provider_called", True), "elapsed_ms": round((time.perf_counter() - started) * 1000, 2), "usage": crystal_result.get("usage", {})})
    return {"task": task["id"], "lanes": lanes}


async def main_async(args: argparse.Namespace) -> dict[str, Any]:
    reports = [await measure_task(task, live=args.live, model=args.model, base_url=args.base_url, repeats=args.repeats, timeout=args.timeout) for task in TASKS]
    aggregate: dict[str, Any] = {}
    for lane in ("baseline", "compact", "crystal"):
        samples = [sample for report in reports for sample in report["lanes"][lane]]
        aggregate[lane] = {
            "samples": len(samples),
            "avg_prompt_chars": round(sum(int(s["prompt_chars"]) for s in samples) / len(samples), 2),
            "provider_calls": sum(bool(s["provider_called"]) for s in samples),
            "avg_elapsed_ms": round(sum(float(s["elapsed_ms"]) for s in samples) / len(samples), 2),
        }
    baseline_chars = aggregate["baseline"]["avg_prompt_chars"]
    aggregate["compact"]["prompt_reduction_pct_vs_baseline"] = round((1 - aggregate["compact"]["avg_prompt_chars"] / baseline_chars) * 100, 2) if baseline_chars else 0.0
    return {"beast_object_type": "small_model_layer_benchmark", "version": "1.0", "live_model": args.live, "model": args.model, "repeats": args.repeats, "tasks": reports, "aggregate": aggregate, "claim_boundary": "This proves prompt and call reduction; model quality uplift requires live verified completion metrics."}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--model", default=os.environ.get("BEAST_OLLAMA_MODEL", "qwen2.5-coder:1.5b"))
    parser.add_argument("--base-url", default=os.environ.get("BEAST_OLLAMA_BASE_URL", "http://127.0.0.1:11434"))
    parser.add_argument("--output", default="build/proof/small_model_layer_benchmark.json")
    args = parser.parse_args()
    report = asyncio.run(main_async(args))
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    print(f"PROOF_BUNDLE={output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

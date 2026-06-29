#!/usr/bin/env python3
"""Live xAI observation window for Phase 1 Compute Governor closure."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.kernel.governance.compute_governor import ComputeGovernor
from app.kernel.compute.compute_ledger import ComputeLedger
from app.kernel.compute.inference_interceptor import InferenceComputeInterceptor
from app.kernel.compute.perceive import EdgeKIR
from app.kernel.security.secret_vault import SecretVault
from benchmarks.beast_systems_benchmark import (
    LIVE_PROVIDER_PRESETS,
    call_openai_compatible_agent,
    run_live_tasks,
)
from benchmarks.xai_omni_tasks import OMNI_TASK_CLASSES, omni_tasks


RESULTS = ROOT / "benchmarks" / "results"


def _summarize(results: List[Any], ledger: ComputeLedger, provider_calls: int) -> Dict[str, Any]:
    receipts = ledger.recent_receipts(2000)
    metrics = ledger.metrics(2000)
    completed = sum(bool(item.completed) for item in results)
    task_count = len(results)
    task_classes = sorted({OMNI_TASK_CLASSES.get(item.task, item.task) for item in results})
    receipt_coverage = len(receipts) / provider_calls if provider_calls else 0.0
    return {
        "beast_object_type": "compute_governor_phase1_xai_live",
        "version": "1.0",
        "phase": 1,
        "mode": "live_shadow_observation",
        "provider": "xai",
        "model": LIVE_PROVIDER_PRESETS["xai"].model,
        "tasks": task_count,
        "task_classes": task_classes,
        "task_class_count": len(task_classes),
        "verified_tasks": completed,
        "verified_task_rate": round(completed / task_count, 6) if task_count else 0.0,
        "actual_provider_calls": provider_calls,
        "compute_receipts": len(receipts),
        "receipt_coverage_rate": round(receipt_coverage, 6),
        "observed_total_tokens": metrics["observed_total_tokens"],
        "observed_cost_usd": metrics["observed_cost_usd"],
        "candidate_avoidable_tokens_counterfactual": metrics["estimated_avoidable_total_tokens"],
        "predicted_savings_usd_counterfactual": metrics["predicted_savings_usd_observed"],
        "cost_coverage_rate": metrics["cost_coverage_rate"],
        "enforced_suppression_count": metrics["enforced_suppression_count"],
        "false_suppression_rate": metrics["false_suppression_rate"],
        "false_suppression_redline": metrics["false_suppression_redline"],
        "phase1_live_observation_passed": bool(
            task_count > 0
            and completed == task_count
            and receipt_coverage >= 0.95
            and metrics["enforced_suppression_count"] == 0
            and metrics["false_suppression_rate"] == 0.0
        ),
        "task_results": [
            {
                "task": item.task,
                "task_class": OMNI_TASK_CLASSES.get(item.task, item.task),
                "completed": bool(item.completed),
                "latency_ms": item.latency_ms,
                "usage": item.usage or {},
                "reason": item.reason,
            }
            for item in results
        ],
        "claim_boundary": (
            "This live run proves shadow receipt coverage and observed behavior on xAI. Avoidable-token and "
            "USD values remain counterfactual; no provider call was suppressed or displaced."
        ),
    }


def run(max_tasks: int = 24, max_tokens: int = 1200, timeout: float = 240.0) -> Dict[str, Any]:
    SecretVault().load()
    provider = LIVE_PROVIDER_PRESETS["xai"]
    tasks = omni_tasks()[: max(1, int(max_tasks))]
    with tempfile.TemporaryDirectory(prefix="beast-compute-xai-live-") as temp:
        ledger = ComputeLedger(str(Path(temp) / "compute.db"))
        interceptor = InferenceComputeInterceptor(ComputeGovernor(), ledger)
        call_count = 0

        def observed_caller(prompt: str) -> Dict[str, Any]:
            nonlocal call_count
            call_count += 1
            ir = EdgeKIR(
                messages=[{"role": "user", "content": prompt}],
                model=provider.model,
                max_tokens=max_tokens,
                metadata={"task_class": "live_governed_code_patch", "observation_window": "phase1_xai"},
            )
            active = interceptor.begin(ir, "xai")
            try:
                response = call_openai_compatible_agent(
                    prompt,
                    provider.base_url,
                    provider.model,
                    __import__("os").environ.get(provider.api_key_env, ""),
                    timeout,
                    max_tokens=max_tokens,
                    json_mode=True,
                )
            except Exception as exc:
                interceptor.complete(
                    active,
                    runtime_attempt_id=f"xai-live-{call_count}",
                    status="provider_error",
                    provider_execution_requested=True,
                    error_type=type(exc).__name__,
                )
                raise
            interceptor.complete(
                active,
                response=response,
                runtime_attempt_id=f"xai-live-{call_count}",
                status="succeeded",
                provider_execution_requested=True,
            )
            return response

        started = time.perf_counter()
        results = run_live_tasks(
            tasks,
            provider.base_url,
            provider.model,
            provider.api_key_env,
            timeout,
            ["full_beast"],
            max_tokens=max_tokens,
            prompt_mode="compact",
            json_mode=True,
            caller=observed_caller,
            provider_name="xai",
        )
        report = _summarize(results, ledger, call_count)
        report["wall_time_ms"] = round((time.perf_counter() - started) * 1000.0, 3)
        return report


def write_report(report: Dict[str, Any]) -> List[Path]:
    RESULTS.mkdir(parents=True, exist_ok=True)
    json_path = RESULTS / "compute_governor_phase1_xai_live.json"
    md_path = RESULTS / "compute_governor_phase1_xai_live.md"
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    lines = [
        "# Compute Governor Phase 1 xAI Live Observation",
        "",
        f"- Model: `{report['model']}`",
        f"- Tasks/classes: `{report['tasks']}/{report['task_class_count']}`",
        f"- Verified tasks: `{report['verified_tasks']}/{report['tasks']}` (`{report['verified_task_rate']:.1%}`)",
        f"- Actual provider calls: `{report['actual_provider_calls']}`",
        f"- Compute receipts: `{report['compute_receipts']}`",
        f"- Receipt coverage: `{report['receipt_coverage_rate']:.1%}`",
        f"- Observed tokens: `{report['observed_total_tokens']}`",
        f"- Observed first-party cost: `${report['observed_cost_usd']:.6f}`" if report["observed_cost_usd"] is not None else "- Observed first-party cost: unavailable",
        f"- Candidate avoidable tokens: `{report['candidate_avoidable_tokens_counterfactual']}` (counterfactual)",
        f"- Predicted savings USD: `{report['predicted_savings_usd_counterfactual']}` (counterfactual)",
        f"- Cost coverage: `{report['cost_coverage_rate']:.1%}`",
        f"- Enforced suppressions: `{report['enforced_suppression_count']}`",
        f"- False suppression rate: `{report['false_suppression_rate']:.1%}`",
        f"- Live observation: `{'PASS' if report['phase1_live_observation_passed'] else 'FAIL'}`",
        "",
        "## Tasks",
        "",
        "| Task | Class | Verified | Latency ms | Tokens |",
        "| --- | --- | --- | ---: | ---: |",
    ]
    for item in report["task_results"]:
        usage = item.get("usage") or {}
        tokens = int(usage.get("prompt_tokens") or 0) + int(usage.get("completion_tokens") or 0)
        lines.append(
            f"| `{item['task']}` | `{item['task_class']}` | {'PASS' if item['completed'] else 'FAIL'} | "
            f"{item['latency_ms']} | {tokens} |"
        )
    lines.extend(["", "## Claim Boundary", "", report["claim_boundary"], ""])
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return [json_path, md_path]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-tasks", type=int, default=24)
    parser.add_argument("--max-tokens", type=int, default=1200)
    parser.add_argument("--timeout", type=float, default=240.0)
    args = parser.parse_args()
    report = run(args.max_tasks, args.max_tokens, args.timeout)
    files = write_report(report)
    print(json.dumps({"report": report, "files": [str(path) for path in files]}, indent=2))
    return 0 if report["phase1_live_observation_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

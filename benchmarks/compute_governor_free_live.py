#!/usr/bin/env python3
"""Free-provider live evidence window for Compute Governor Phases 1 and 2."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.kernel.compute_governor import ComputeGovernor
from app.kernel.compute_ledger import ComputeLedger
from app.kernel.inference_interceptor import InferenceComputeInterceptor
from app.kernel.perceive import EdgeKIR
from app.kernel.secret_vault import SecretVault
from benchmarks.beast_systems_benchmark import LIVE_PROVIDER_PRESETS, _first_env_value
from benchmarks.coding_task_completion_harness import call_openai_compatible_agent
from benchmarks.compute_governor_phase2_calibration import _hash


OUT = ROOT / "benchmarks" / "results"


FREE_PROVIDER_ORDER = [
    "huggingface",
    "groq",
    "cerebras",
    "gemini",
    "openrouter_gptoss",
]


def _scenarios(root: Path) -> List[Dict[str, Any]]:
    (root / "test_sample.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    source = "VALUE = 1\n"
    source_digest = __import__("hashlib").sha256(source.encode()).hexdigest()
    return [
        {
            "task_class": "schema_validation",
            "prompt": "Return JSON: {\"ok\": true, \"task\": \"schema_validation\"}",
            "candidate": "schema_validation",
            "work": {
                "schema_validation": {
                    "instance": {"ok": True},
                    "schema": {"type": "object", "required": ["ok"]},
                    "expect_valid": True,
                    "expected_output_sha256": _hash({"valid": True, "error_paths": []}),
                }
            },
        },
        {
            "task_class": "syntax_check",
            "prompt": "Return JSON: {\"ok\": true, \"task\": \"syntax_check\"}",
            "candidate": "syntax_check",
            "work": {
                "syntax_check": {
                    "files": {"example.py": source},
                    "expected_sha256": {"example.py": source_digest},
                    "expected_output_sha256": _hash({"sha256": {"example.py": source_digest}}),
                }
            },
        },
        {
            "task_class": "test_execution",
            "prompt": "Return JSON: {\"ok\": true, \"task\": \"test_execution\"}",
            "candidate": "test_execution",
            "work": {
                "test_execution": {
                    "root": str(root),
                    "minimum_count": 1,
                    "expected_output_sha256": _hash({"tests": ["test_sample.py"], "count": 1}),
                }
            },
        },
    ]


def _configured_free_providers(names: Iterable[str]) -> List[Any]:
    providers = []
    for name in names:
        provider = LIVE_PROVIDER_PRESETS[name]
        api_key = _first_env_value(provider.api_key_env)
        if api_key:
            providers.append(provider)
    return providers


def _call_provider(provider: Any, prompt: str, *, timeout: float, max_tokens: int) -> Dict[str, Any]:
    return call_openai_compatible_agent(
        prompt,
        provider.base_url,
        os.environ.get(f"{provider.name.upper()}_MODEL", provider.model),
        _first_env_value(provider.api_key_env),
        timeout=timeout,
        max_tokens=max_tokens,
        json_mode=True,
    )


def run(
    providers: str = ",".join(FREE_PROVIDER_ORDER),
    max_providers: int = 2,
    repeats: int = 1,
    max_tokens: int = 96,
    timeout: float = 90.0,
) -> Dict[str, Any]:
    SecretVault().load()
    requested = [item.strip().lower().replace("-", "_") for item in providers.split(",") if item.strip()]
    selected = _configured_free_providers(requested)[: max(1, int(max_providers))]
    started = time.perf_counter()

    with tempfile.TemporaryDirectory(prefix="beast-compute-free-live-") as temp:
        root = Path(temp)
        ledger = ComputeLedger(str(root / "compute.db"))
        interceptor = InferenceComputeInterceptor(ComputeGovernor(mode="phase2_shadow"), ledger)
        rows: List[Dict[str, Any]] = []
        provider_calls = 0
        errors: List[Dict[str, Any]] = []

        scenarios = _scenarios(root)
        for provider in selected:
            for repeat in range(max(1, int(repeats))):
                for scenario in scenarios:
                    ir = EdgeKIR(
                        messages=[{"role": "user", "content": scenario["prompt"]}],
                        model=provider.model,
                        max_tokens=max_tokens,
                        metadata={
                            "task_class": scenario["task_class"],
                            "deterministic_candidates": [scenario["candidate"]],
                            "deterministic_work": scenario["work"],
                            "live_provider": provider.name,
                            "observation_window": "phase1_phase2_free_live",
                        },
                    )
                    active = interceptor.begin(ir, provider.name)
                    provider_calls += 1
                    runtime_attempt_id = f"free-live-{provider.name}-{repeat}-{scenario['task_class']}"
                    try:
                        response = _call_provider(provider, scenario["prompt"], timeout=timeout, max_tokens=max_tokens)
                        receipt = interceptor.complete(
                            active,
                            response=response,
                            runtime_attempt_id=runtime_attempt_id,
                            status="succeeded",
                            provider_execution_requested=True,
                            behavior_preserved=True,
                        )
                        rows.append({
                            "provider": provider.name,
                            "task_class": scenario["task_class"],
                            "status": "succeeded",
                            "provider_called": receipt.provider_execution_requested,
                            "deterministic_verified": receipt.deterministic_shadow_verified == 1,
                            "deterministic_agreement": receipt.deterministic_shadow_agreements == 1,
                            "usage": response.get("usage") or {},
                            "latency_ms": response.get("latency_ms"),
                        })
                    except Exception as exc:
                        interceptor.complete(
                            active,
                            runtime_attempt_id=runtime_attempt_id,
                            status="provider_error",
                            provider_execution_requested=True,
                            error_type=type(exc).__name__,
                        )
                        errors.append({
                            "provider": provider.name,
                            "task_class": scenario["task_class"],
                            "error_type": type(exc).__name__,
                            "error": str(exc)[:500],
                        })

        receipts = ledger.recent_receipts(2000)
        metrics = ledger.metrics(2000)
        succeeded = [row for row in rows if row["status"] == "succeeded"]
        receipt_coverage = len(receipts) / provider_calls if provider_calls else 0.0
        phase1_passed = bool(
            provider_calls > 0
            and len(succeeded) > 0
            and receipt_coverage >= 0.95
            and metrics["enforced_suppression_count"] == 0
            and metrics["false_suppression_rate"] == 0.0
        )
        phase2_passed = bool(
            phase1_passed
            and metrics["deterministic_shadow_verification_rate"] == 1.0
            and metrics["deterministic_shadow_agreement_rate"] == 1.0
        )
        return {
            "beast_object_type": "compute_governor_free_provider_live",
            "version": "1.0",
            "mode": "phase2_shadow_live_free_provider_observation",
            "requested_providers": requested,
            "selected_providers": [provider.name for provider in selected],
            "provider_calls": provider_calls,
            "successful_provider_calls": len(succeeded),
            "compute_receipts": len(receipts),
            "receipt_coverage_rate": round(receipt_coverage, 6),
            "observed_total_tokens": metrics["observed_total_tokens"],
            "observed_cost_usd": metrics["observed_cost_usd"],
            "cost_coverage_rate": metrics["cost_coverage_rate"],
            "candidate_avoidable_tokens_counterfactual": metrics["estimated_avoidable_total_tokens"],
            "predicted_savings_usd_counterfactual": metrics["predicted_savings_usd_observed"],
            "deterministic_shadow_verification_rate": metrics["deterministic_shadow_verification_rate"],
            "deterministic_shadow_agreement_rate": metrics["deterministic_shadow_agreement_rate"],
            "enforced_suppression_count": metrics["enforced_suppression_count"],
            "false_suppression_rate": metrics["false_suppression_rate"],
            "phase1_free_live_passed": phase1_passed,
            "phase2_free_live_shadow_passed": phase2_passed,
            "rows": rows,
            "errors": errors,
            "wall_time_ms": round((time.perf_counter() - started) * 1000.0, 3),
            "claim_boundary": (
                "Free-provider live evidence proves receipt coverage and Phase 2 shadow transform agreement "
                "beside real provider calls. It does not claim deterministic displacement of live calls."
            ),
        }


def write_report(report: Dict[str, Any]) -> List[Path]:
    OUT.mkdir(parents=True, exist_ok=True)
    json_path = OUT / "compute_governor_free_live.json"
    md_path = OUT / "compute_governor_free_live.md"
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    lines = [
        "# Compute Governor Free-Provider Live Evidence",
        "",
        f"- Selected providers: `{', '.join(report['selected_providers']) or 'none'}`",
        f"- Provider calls: `{report['provider_calls']}`",
        f"- Successful calls: `{report['successful_provider_calls']}`",
        f"- Compute receipts: `{report['compute_receipts']}`",
        f"- Receipt coverage: `{report['receipt_coverage_rate']:.1%}`",
        f"- Observed tokens: `{report['observed_total_tokens']}`",
        f"- Candidate avoidable tokens: `{report['candidate_avoidable_tokens_counterfactual']}` (counterfactual)",
        f"- Phase 1 free live: `{'PASS' if report['phase1_free_live_passed'] else 'FAIL'}`",
        f"- Phase 2 free live shadow: `{'PASS' if report['phase2_free_live_shadow_passed'] else 'FAIL'}`",
        "",
        "## Rows",
        "",
        "| Provider | Task class | Status | Verified | Agreement | Tokens | Latency ms |",
        "| --- | --- | --- | --- | --- | ---: | ---: |",
    ]
    for row in report["rows"]:
        usage = row.get("usage") or {}
        tokens = int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0) + int(
            usage.get("completion_tokens") or usage.get("output_tokens") or 0
        )
        lines.append(
            f"| `{row['provider']}` | `{row['task_class']}` | `{row['status']}` | "
            f"{row['deterministic_verified']} | {row['deterministic_agreement']} | {tokens} | {row.get('latency_ms')} |"
        )
    if report["errors"]:
        lines.extend(["", "## Errors", ""])
        for item in report["errors"]:
            lines.append(f"- `{item['provider']}` / `{item['task_class']}`: `{item['error_type']}` {item['error']}")
    lines.extend(["", "## Claim Boundary", "", report["claim_boundary"], ""])
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return [json_path, md_path]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--providers", default=",".join(FREE_PROVIDER_ORDER))
    parser.add_argument("--max-providers", type=int, default=2)
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--max-tokens", type=int, default=96)
    parser.add_argument("--timeout", type=float, default=90.0)
    args = parser.parse_args()
    report = run(args.providers, args.max_providers, args.repeats, args.max_tokens, args.timeout)
    files = write_report(report)
    print(json.dumps({"report": report, "files": [str(path) for path in files]}, indent=2))
    return 0 if report["phase1_free_live_passed"] and report["phase2_free_live_shadow_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

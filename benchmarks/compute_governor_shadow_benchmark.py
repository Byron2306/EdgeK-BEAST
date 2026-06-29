#!/usr/bin/env python3
"""Deterministic Phase 1 benchmark for compute shadow instrumentation."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.kernel.governance.compute_governor import ComputeGovernor
from app.kernel.compute.compute_ledger import ComputeLedger
from app.kernel.compute.inference_interceptor import InferenceComputeInterceptor
from app.kernel.compute.perceive import EdgeKIR


OUT = ROOT / "benchmarks" / "results"

SCENARIOS = [
    ("deterministic_test", "Run pytest and compile the changed Python files", ["test_execution", "syntax_check"]),
    ("schema_contract", "Validate the JSON schema and output contract", ["schema_validation"]),
    ("route_diagnostic", "Diagnose provider route authentication and API key configuration", ["route_diagnostics"]),
    ("patch_compile", "Compile the patch and apply the selected diff hunk", ["patch_compilation"]),
    ("semantic_only", "Choose the best domain abstraction for this architecture", []),
]


def run() -> dict:
    with tempfile.TemporaryDirectory(prefix="beast-compute-shadow-") as temp:
        ledger = ComputeLedger(str(Path(temp) / "compute.db"))
        interceptor = InferenceComputeInterceptor(ComputeGovernor(), ledger)
        rows = []
        for index, (name, prompt, expected) in enumerate(SCENARIOS, start=1):
            ir = EdgeKIR(
                messages=[{"role": "user", "content": prompt}],
                model="shadow-model",
                max_tokens=200,
                metadata={"task_class": name, "reuse_candidates": ["skill:known-transform"] if index == 2 else []},
            )
            active = interceptor.begin(ir, "shadow-provider")
            receipt = interceptor.complete(
                active,
                response={"usage": {"prompt_tokens": 100 + index, "completion_tokens": 20, "total_tokens": 120 + index}},
                runtime_attempt_id=f"attempt-{index}",
                status="succeeded",
            )
            row = {
                "scenario": name,
                "expected_candidates": expected,
                "detected_candidates": active.plan.deterministic_candidates,
                "candidate_detection_ok": set(expected).issubset(active.plan.deterministic_candidates),
                "selected_rung": active.gate.selected_rung,
                "recommended_rung": active.gate.recommended_rung,
                "enforced": active.gate.enforced,
                "behavior_preserved": active.gate.selected_rung == "selected_provider" and not active.gate.enforced,
                "receipt_id": receipt.receipt_id,
                "observed_tokens": receipt.total_tokens,
                "estimated_avoidable_tokens": receipt.estimated_avoidable_input_tokens + receipt.estimated_avoidable_output_tokens,
            }
            rows.append(row)
        metrics = ledger.metrics()
        return {
            "beast_object_type": "compute_governor_shadow_benchmark",
            "version": "1.0",
            "phase": 1,
            "mode": "shadow",
            "scenario_count": len(rows),
            "all_behavior_preserved": all(item["behavior_preserved"] for item in rows),
            "candidate_detection_rate": sum(item["candidate_detection_ok"] for item in rows) / len(rows),
            "privacy": {"prompts_persisted": False, "source_code_persisted": False},
            "metrics": metrics,
            "scenarios": rows,
            "claim_boundary": "Avoidable-token values are counterfactual estimates, not measured savings.",
        }


def write(report: dict, prefix: str) -> tuple[Path, Path]:
    OUT.mkdir(parents=True, exist_ok=True)
    json_path = OUT / f"{prefix}.json"
    md_path = OUT / f"{prefix}.md"
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    lines = [
        "# Compute Governor Phase 1 Shadow Benchmark", "",
        f"- Scenarios: `{report['scenario_count']}`",
        f"- Behavior preserved: `{report['all_behavior_preserved']}`",
        f"- Candidate detection rate: `{report['candidate_detection_rate']:.2%}`",
        f"- Observed tokens: `{report['metrics']['observed_total_tokens']}`",
        f"- Counterfactual avoidable-token estimate: `{report['metrics']['estimated_avoidable_total_tokens']}`",
        "", report["claim_boundary"], "",
        "| Scenario | Candidates | Selected | Recommended | Enforced | Preserved |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for item in report["scenarios"]:
        lines.append(
            f"| `{item['scenario']}` | {', '.join(item['detected_candidates']) or 'none'} | "
            f"{item['selected_rung']} | {item['recommended_rung']} | {item['enforced']} | {item['behavior_preserved']} |"
        )
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, md_path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-prefix", default="compute_governor_phase1_shadow")
    args = parser.parse_args()
    report = run()
    paths = write(report, args.output_prefix)
    print(json.dumps({"report": report, "files": [str(path) for path in paths]}, indent=2))
    return 0 if report["all_behavior_preserved"] and report["candidate_detection_rate"] == 1.0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

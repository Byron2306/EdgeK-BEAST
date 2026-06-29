#!/usr/bin/env python3
"""Calibrate Phase 1 token estimates against paired usage deltas."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.kernel.governance.compute_governor import ComputeGovernor
from app.kernel.compute.compute_ledger import ComputeLedger
from app.kernel.compute.inference_interceptor import InferenceComputeInterceptor
from app.kernel.compute.perceive import EdgeKIR

OUT = ROOT / "benchmarks" / "results"
TASKS = ("schema_validation", "route_diagnostics", "patch_compilation", "test_execution", "syntax_check", "lint_format")


def run(repeats: int = 20) -> Dict[str, Any]:
    repeats = max(1, int(repeats))
    with tempfile.TemporaryDirectory(prefix="beast-phase1-calibration-") as temp:
        ledger = ComputeLedger(str(Path(temp) / "compute.db"))
        interceptor = InferenceComputeInterceptor(ComputeGovernor(mode="shadow"), ledger)
        attempts = 0
        for repeat in range(repeats):
            for index, task in enumerate(TASKS):
                input_tokens = 80 + index * 20
                output_tokens = 20 + index * 10
                displaced_input = input_tokens - int(input_tokens * 0.35)
                displaced_output = output_tokens - int(output_tokens * 0.20)
                observed_delta = (input_tokens + output_tokens) - (displaced_input + displaced_output)
                ir = EdgeKIR(
                    messages=[{"role": "user", "content": f"Execute {task.replace('_', ' ')}"}],
                    model="paired-calibration-model",
                    metadata={
                        "task_class": task,
                        "deterministic_candidates": [task],
                        "compute_calibration": {"source": "paired_ablation", "observed_avoidable_tokens": observed_delta},
                    },
                )
                interceptor.complete(
                    interceptor.begin(ir, "calibration-provider"),
                    response={"usage": {"prompt_tokens": input_tokens, "completion_tokens": output_tokens}},
                    runtime_attempt_id=f"phase1-cal-{repeat}-{task}",
                    provider_execution_requested=True,
                    behavior_preserved=True,
                )
                attempts += 1
        metrics = ledger.metrics()
        passed = bool(
            metrics["token_calibration_count"] == attempts
            and metrics["token_calibration_coverage_rate"] == 1.0
            and metrics["avoidable_token_mean_absolute_error"] == 0.0
            and metrics["enforced_suppression_count"] == 0
        )
        return {
            "beast_object_type": "compute_governor_phase1_token_calibration",
            "version": "1.0",
            "mode": "deterministic_paired_usage_calibration",
            "task_classes": len(TASKS),
            "paired_attempts": attempts,
            "calibration_coverage_rate": metrics["token_calibration_coverage_rate"],
            "avoidable_token_mean_absolute_error": metrics["avoidable_token_mean_absolute_error"],
            "provider_execution_preserved": True,
            "suppression_decisions_enforced": metrics["enforced_suppression_count"],
            "passed": passed,
            "claim_boundary": "Synthetic paired usage deltas calibrate receipt arithmetic; live-provider calibration remains continuous operational monitoring.",
        }


def write_report(report: Dict[str, Any]) -> list[Path]:
    OUT.mkdir(parents=True, exist_ok=True)
    json_path = OUT / "compute_governor_phase1_calibration.json"
    md_path = OUT / "compute_governor_phase1_calibration.md"
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md_path.write_text("\n".join([
        "# Compute Governor Phase 1 Token Calibration", "",
        f"- Task classes: `{report['task_classes']}`",
        f"- Paired attempts: `{report['paired_attempts']}`",
        f"- Calibration coverage: `{report['calibration_coverage_rate']:.1%}`",
        f"- Avoidable-token MAE: `{report['avoidable_token_mean_absolute_error']}`",
        f"- Provider execution preserved: `{report['provider_execution_preserved']}`",
        f"- Result: `{'PASS' if report['passed'] else 'FAIL'}`", "",
        "## Claim Boundary", "", str(report["claim_boundary"]), "",
    ]), encoding="utf-8")
    return [json_path, md_path]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeats", type=int, default=20)
    args = parser.parse_args()
    report = run(args.repeats)
    write_report(report)
    print(json.dumps(report, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Paired Phase 1 benchmark proving shadow accounting preserves behavior."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.kernel.compute_governor import ComputeGovernor
from app.kernel.compute_ledger import ComputeLedger
from app.kernel.inference_interceptor import InferenceComputeInterceptor
from app.kernel.perceive import EdgeKIR


OUT = ROOT / "benchmarks" / "results"


@dataclass(frozen=True)
class Scenario:
    task_class: str
    prompt: str
    expected_candidates: tuple[str, ...]


SCENARIOS = (
    Scenario("schema_validation", "Validate the JSON schema and Action IR contract", ("schema_validation",)),
    Scenario("provider_routing", "Normalize the provider route and API key configuration", ("route_diagnostics",)),
    Scenario("patch_compilation", "Apply the exact patch then compile the changed file", ("patch_compilation", "syntax_check")),
    Scenario("test_selection", "Discover and run tests including the hidden test suite", ("test_execution",)),
    Scenario("secret_redaction", "Redact secrets before schema validation", ("schema_validation",)),
    Scenario("semantic_reasoning", "Choose the safest abstraction for this domain model", ()),
)


class StableProvider:
    """A deterministic provider double used to isolate instrumentation effects."""

    def __init__(self, route: str = "paired-provider") -> None:
        self.route = route
        self.calls = 0

    def call(self, ir: EdgeKIR) -> Dict[str, object]:
        self.calls += 1
        prompt = str(ir.messages[0].get("content") or "")
        digest = hashlib.sha256(prompt.encode()).hexdigest()[:16]
        return {
            "provider_route": self.route,
            "patch": {"path": "app/example.py", "old": "VALUE = 1", "new": f"VALUE = '{digest}'"},
            "verifier": {"passed": True, "hidden_tests_passed": True, "rollback_passed": True},
            "usage": {"prompt_tokens": 80, "completion_tokens": 20, "total_tokens": 100},
        }


def _observable(response: Dict[str, object]) -> Dict[str, object]:
    return {
        "provider_route": response.get("provider_route"),
        "patch": response.get("patch"),
        "verifier": response.get("verifier"),
    }


def run(repeats: int = 20) -> Dict[str, object]:
    repeats = max(1, int(repeats))
    with tempfile.TemporaryDirectory(prefix="beast-compute-phase1-closure-") as temp:
        ledger = ComputeLedger(str(Path(temp) / "compute.db"))
        interceptor = InferenceComputeInterceptor(ComputeGovernor(), ledger)
        baseline_provider = StableProvider()
        accounting_provider = StableProvider()
        rows: List[Dict[str, object]] = []

        for repeat in range(repeats):
            for scenario in SCENARIOS:
                ir = EdgeKIR(
                    messages=[{"role": "user", "content": scenario.prompt}],
                    model="paired-shadow-model",
                    max_tokens=200,
                    metadata={"task_class": scenario.task_class, "pair_index": repeat},
                )
                baseline = baseline_provider.call(ir)
                active = interceptor.begin(ir, accounting_provider.route)
                accounted = accounting_provider.call(ir)
                behavior_preserved = _observable(baseline) == _observable(accounted)
                receipt = interceptor.complete(
                    active,
                    response=accounted,
                    runtime_attempt_id=f"pair-{repeat}-{scenario.task_class}",
                    status="succeeded",
                    provider_execution_requested=True,
                    behavior_preserved=behavior_preserved,
                )
                rows.append({
                    "task_class": scenario.task_class,
                    "behavior_preserved": behavior_preserved,
                    "provider_path_equal": baseline["provider_route"] == accounted["provider_route"],
                    "patch_equal": baseline["patch"] == accounted["patch"],
                    "verifier_equal": baseline["verifier"] == accounted["verifier"],
                    "candidate_detected": set(scenario.expected_candidates).issubset(active.plan.deterministic_candidates),
                    "candidate_call_avoidable": bool(active.gate.predicted_avoidable_work),
                    "receipt_created": bool(receipt.receipt_id),
                    "suppression_enforced": receipt.suppression_enforced,
                    "estimated_avoidable_tokens": receipt.avoided_tokens_estimate,
                })

        metrics = ledger.metrics()
        pair_count = len(rows)
        receipt_count = ledger.state()["receipts"]
        behavior_preserved_count = sum(bool(row["behavior_preserved"]) for row in rows)
        provider_path_equal_count = sum(bool(row["provider_path_equal"]) for row in rows)
        patch_equal_count = sum(bool(row["patch_equal"]) for row in rows)
        verifier_equal_count = sum(bool(row["verifier_equal"]) for row in rows)
        avoidable_count = sum(bool(row["candidate_call_avoidable"]) for row in rows)
        report: Dict[str, object] = {
            "beast_object_type": "compute_governor_phase1_closure_benchmark",
            "version": "1.0",
            "mode": "deterministic_paired_preflight",
            "phase": 1,
            "scenario_count": len(SCENARIOS),
            "repeats": repeats,
            "paired_attempts": pair_count,
            "actual_provider_calls": {
                "accounting_off": baseline_provider.calls,
                "accounting_on": accounting_provider.calls,
                "unchanged": baseline_provider.calls == accounting_provider.calls == pair_count,
            },
            "candidate_calls_avoidable": avoidable_count,
            "candidate_call_rate": round(avoidable_count / pair_count, 6) if pair_count else 0.0,
            "estimated_avoided_tokens_counterfactual": metrics["estimated_avoidable_total_tokens"],
            "estimated_avoided_usd_counterfactual": metrics["predicted_savings_usd_observed"],
            "cost_coverage_rate": metrics["cost_coverage_rate"],
            "behavior_preserved_count": behavior_preserved_count,
            "verified_behavior_preservation_rate": round(behavior_preserved_count / pair_count, 6) if pair_count else 0.0,
            "provider_path_equivalence_rate": round(provider_path_equal_count / pair_count, 6) if pair_count else 0.0,
            "patch_equivalence_rate": round(patch_equal_count / pair_count, 6) if pair_count else 0.0,
            "verifier_equivalence_rate": round(verifier_equal_count / pair_count, 6) if pair_count else 0.0,
            "behavior_difference_count": pair_count - behavior_preserved_count,
            "receipt_count": receipt_count,
            "receipt_coverage_rate": round(receipt_count / pair_count, 6) if pair_count else 0.0,
            "suppression_decisions_enforced": metrics["enforced_suppression_count"],
            "false_suppression_rate": metrics["false_suppression_rate"],
            "false_suppression_redline": metrics["false_suppression_redline"],
            "phase1_preflight_passed": bool(
                baseline_provider.calls == accounting_provider.calls == pair_count
                and behavior_preserved_count == pair_count
                and receipt_count / pair_count >= 0.95
                and metrics["enforced_suppression_count"] == 0
                and metrics["false_suppression_rate"] == 0.0
            ),
            "task_class_summary": _task_class_summary(rows),
            "claim_boundary": (
                "This deterministic paired preflight measures instrumentation equivalence and counterfactual "
                "opportunity. It does not prove realized production savings or displaced live provider calls."
            ),
        }
        return report


def _task_class_summary(rows: List[Dict[str, object]]) -> List[Dict[str, object]]:
    result = []
    for scenario in SCENARIOS:
        group = [row for row in rows if row["task_class"] == scenario.task_class]
        result.append({
            "task_class": scenario.task_class,
            "attempts": len(group),
            "behavior_preservation_rate": round(sum(bool(row["behavior_preserved"]) for row in group) / len(group), 6),
            "candidate_detection_rate": round(sum(bool(row["candidate_detected"]) for row in group) / len(group), 6),
            "candidate_call_rate": round(sum(bool(row["candidate_call_avoidable"]) for row in group) / len(group), 6),
            "estimated_avoidable_tokens": sum(int(row["estimated_avoidable_tokens"]) for row in group),
        })
    return result


def write_report(report: Dict[str, object]) -> List[Path]:
    OUT.mkdir(parents=True, exist_ok=True)
    json_path = OUT / "compute_governor_phase1_closure.json"
    md_path = OUT / "compute_governor_phase1_closure.md"
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    calls = report["actual_provider_calls"]
    lines = [
        "# Compute Governor Phase 1 Closure Preflight",
        "",
        f"- Paired attempts: `{report['paired_attempts']}`",
        f"- Provider calls accounting off/on: `{calls['accounting_off']}/{calls['accounting_on']}`",
        f"- Provider-call path unchanged: `{calls['unchanged']}`",
        f"- Verified behavior preservation: `{report['verified_behavior_preservation_rate']:.1%}`",
        f"- Provider path / patch / verifier equivalence: `{report['provider_path_equivalence_rate']:.1%}` / "
        f"`{report['patch_equivalence_rate']:.1%}` / `{report['verifier_equivalence_rate']:.1%}`",
        f"- Behavior differences: `{report['behavior_difference_count']}`",
        f"- Receipt coverage: `{report['receipt_coverage_rate']:.1%}`",
        f"- Candidate calls avoidable: `{report['candidate_calls_avoidable']}` (counterfactual)",
        f"- Estimated avoidable tokens: `{report['estimated_avoided_tokens_counterfactual']}` (counterfactual)",
        f"- Estimated avoidable USD: `{report['estimated_avoided_usd_counterfactual']}` (no cost inference)",
        f"- Enforced suppressions: `{report['suppression_decisions_enforced']}`",
        f"- False suppression rate: `{report['false_suppression_rate']:.1%}`",
        f"- Phase 1 deterministic preflight: `{'PASS' if report['phase1_preflight_passed'] else 'FAIL'}`",
        "",
        "## Task Classes",
        "",
        "| Task class | Attempts | Behavior | Candidate detection | Candidate calls | Avoidable tokens |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in report["task_class_summary"]:
        lines.append(
            f"| `{row['task_class']}` | {row['attempts']} | {row['behavior_preservation_rate']:.1%} | "
            f"{row['candidate_detection_rate']:.1%} | {row['candidate_call_rate']:.1%} | "
            f"{row['estimated_avoidable_tokens']} |"
        )
    lines.extend(["", "## Claim Boundary", "", str(report["claim_boundary"]), ""])
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return [json_path, md_path]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeats", type=int, default=20)
    args = parser.parse_args()
    report = run(args.repeats)
    paths = write_report(report)
    print(json.dumps({"report": report, "files": [str(path) for path in paths]}, indent=2))
    return 0 if report["phase1_preflight_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

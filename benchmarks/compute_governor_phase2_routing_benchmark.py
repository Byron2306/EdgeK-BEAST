#!/usr/bin/env python3
"""Paired Phase 2 friction-routing benchmark.

The benchmark compares the current Provider Economist route with the
friction-penalized shadow route for the same candidate set. It never enables
friction enforcement during the paired measurement.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.kernel.adapters.provider_economist import EconomistPolicy, ProviderEconomist

OUT = ROOT / "benchmarks" / "results"


def _paired_cases() -> List[Dict[str, Any]]:
    return [
        {
            "case_id": "clean_winner_high_friction",
            "task_class": "code_generation",
            "candidates": [
                {
                    "provider": "nim", "model": "nemotron", "recommended_role": "clean_patch_candidate",
                    "auth_confidence": 1.0, "hidden_clean_per_usd": 110, "hidden_clean_rate": 0.42,
                    "avg_latency_ms": 2400, "rescued_completed": 1, "sample_size": 10,
                },
                {
                    "provider": "groq", "model": "llama", "recommended_role": "clean_patch_candidate",
                    "auth_confidence": 1.0, "hidden_clean_per_usd": 96, "hidden_clean_rate": 0.40,
                    "avg_latency_ms": 1800, "rescued_completed": 1, "sample_size": 10,
                },
            ],
            "friction": [
                {
                    "profile_id": "friction_nim", "capability_id": "provider:nim",
                    "task_class": "code_generation", "scope": {"provider": "nim", "model": "nemotron"},
                    "friction_score": 0.95, "confidence": 1.0, "samples": 8,
                }
            ],
            "expected_change": True,
        },
        {
            "case_id": "clean_winner_low_confidence_friction",
            "task_class": "code_generation",
            "candidates": [
                {
                    "provider": "xai", "model": "grok-code", "recommended_role": "clean_patch_candidate",
                    "auth_confidence": 0.95, "hidden_clean_per_usd": 180, "hidden_clean_rate": 0.50,
                    "avg_latency_ms": 2600, "rescued_completed": 0, "sample_size": 10,
                },
                {
                    "provider": "cohere", "model": "command", "recommended_role": "clean_patch_candidate",
                    "auth_confidence": 0.95, "hidden_clean_per_usd": 104, "hidden_clean_rate": 0.38,
                    "avg_latency_ms": 2300, "rescued_completed": 0, "sample_size": 10,
                },
            ],
            "friction": [
                {
                    "profile_id": "friction_xai", "capability_id": "provider:xai",
                    "task_class": "code_generation", "scope": {"provider": "xai", "model": "grok-code"},
                    "friction_score": 0.80, "confidence": 0.20, "samples": 1,
                }
            ],
            "expected_change": False,
        },
        {
            "case_id": "no_matching_friction",
            "task_class": "route_diagnostics",
            "candidates": [
                {
                    "provider": "gemini", "model": "flash", "recommended_role": "clean_patch_candidate",
                    "auth_confidence": 1.0, "hidden_clean_per_usd": 90, "hidden_clean_rate": 0.35,
                    "avg_latency_ms": 1200, "rescued_completed": 1, "sample_size": 10,
                },
                {
                    "provider": "mistral", "model": "small", "recommended_role": "clean_patch_candidate",
                    "auth_confidence": 1.0, "hidden_clean_per_usd": 75, "hidden_clean_rate": 0.35,
                    "avg_latency_ms": 1100, "rescued_completed": 1, "sample_size": 10,
                },
            ],
            "friction": [],
            "expected_change": False,
        },
    ]


def run(repeats: int = 10) -> Dict[str, Any]:
    repeats = max(1, int(repeats))
    economist = ProviderEconomist()
    rows: List[Dict[str, Any]] = []
    for repeat in range(repeats):
        for case in _paired_cases():
            policy = EconomistPolicy(task_class=case["task_class"], friction_mode="shadow")
            shadow = economist.select(case["candidates"], policy, friction_profiles=case["friction"])
            enforced = economist.select(
                case["candidates"],
                EconomistPolicy(task_class=case["task_class"], friction_mode="enforce"),
                friction_profiles=case["friction"],
            )
            phase2 = shadow["phase2_friction"]
            rows.append({
                "repeat": repeat,
                "case_id": case["case_id"],
                "base_selected_provider": phase2["base_selected_provider"],
                "friction_selected_provider": phase2["friction_selected_provider"],
                "shadow_selected_provider": shadow["selected"]["provider"],
                "enforced_selected_provider": enforced["selected"]["provider"],
                "selection_would_change": phase2["selection_would_change"],
                "expected_change": case["expected_change"],
                "shadow_preserved_current_route": (
                    shadow["selected"]["provider"] == phase2["base_selected_provider"]
                ),
            })
    paired_attempts = len(rows)
    changed = sum(1 for row in rows if row["selection_would_change"])
    expected_matches = sum(1 for row in rows if row["selection_would_change"] == row["expected_change"])
    shadow_preserved = sum(1 for row in rows if row["shadow_preserved_current_route"])
    passed = bool(
        paired_attempts
        and expected_matches == paired_attempts
        and shadow_preserved == paired_attempts
    )
    return {
        "beast_object_type": "compute_governor_phase2_routing_benchmark",
        "version": "1.0",
        "mode": "paired_friction_shadow_routing",
        "case_count": len(_paired_cases()),
        "repeats": repeats,
        "paired_attempts": paired_attempts,
        "shadow_preserved_current_route_rate": round(shadow_preserved / paired_attempts, 6),
        "friction_selection_change_count": changed,
        "friction_selection_change_rate": round(changed / paired_attempts, 6),
        "expected_change_match_rate": round(expected_matches / paired_attempts, 6),
        "passed": passed,
        "rows": rows,
        "claim_boundary": "Paired shadow routing measures route displacement pressure only; enforcement remains disabled.",
    }


def write_report(report: Dict[str, Any]) -> List[Path]:
    OUT.mkdir(parents=True, exist_ok=True)
    json_path = OUT / "compute_governor_phase2_routing_benchmark.json"
    md_path = OUT / "compute_governor_phase2_routing_benchmark.md"
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md_path.write_text("\n".join([
        "# Compute Governor Phase 2 Routing Benchmark",
        "",
        f"- Paired attempts: `{report['paired_attempts']}`",
        f"- Shadow preserved current route: `{report['shadow_preserved_current_route_rate']:.1%}`",
        f"- Friction would change selected route: `{report['friction_selection_change_rate']:.1%}`",
        f"- Expected-change match: `{report['expected_change_match_rate']:.1%}`",
        f"- Result: `{'PASS' if report['passed'] else 'FAIL'}`",
        "",
        "## Claim Boundary",
        "",
        str(report["claim_boundary"]),
        "",
    ]), encoding="utf-8")
    return [json_path, md_path]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeats", type=int, default=10)
    args = parser.parse_args()
    report = run(args.repeats)
    write_report(report)
    print(json.dumps(report, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

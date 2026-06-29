#!/usr/bin/env python3
"""Local Phase 3 counterfactual-crystal benchmark."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.kernel.governance.compute_governor import ComputeGovernor
from app.kernel.compute.compute_ledger import ComputeLedger
from app.kernel.compute.inference_interceptor import InferenceComputeInterceptor
from app.kernel.compute.perceive import EdgeKIR

OUT = ROOT / "benchmarks" / "results"


def run(repeats: int = 3) -> Dict[str, Any]:
    repeats = max(1, int(repeats))
    candidates = [
        {
            "provider": "nim", "model": "nemotron", "recommended_role": "clean_patch_candidate",
            "auth_confidence": 1.0, "hidden_clean_per_usd": 100, "avg_latency_ms": 3000,
        },
        {
            "provider": "groq", "model": "llama", "recommended_role": "clean_patch_candidate",
            "auth_confidence": 0.9, "hidden_clean_per_usd": 80, "avg_latency_ms": 45_000,
        },
    ]
    rows: List[Dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="beast-phase3-counterfactuals-") as temp:
        ledger = ComputeLedger(str(Path(temp) / "compute.db"))
        interceptor = InferenceComputeInterceptor(ComputeGovernor(mode="phase4_enforce"), ledger)
        for index in range(repeats):
            first = interceptor.begin(
                EdgeKIR(messages=[{"role": "user", "content": "Answer"}], model="m", metadata={
                    "task_class": "code_generation",
                    "provider_candidates": candidates,
                }),
                "nim",
            )
            interceptor.complete(first, response={"usage": {"total_tokens": 20}}, status="completed", behavior_preserved=True)
            second_candidates = [
                {**candidates[1], "hidden_clean_per_usd": 130, "avg_latency_ms": 2500},
                {**candidates[0], "hidden_clean_per_usd": 70},
            ]
            second = interceptor.begin(
                EdgeKIR(messages=[{"role": "user", "content": "Answer"}], model="m", metadata={
                    "task_class": "code_generation",
                    "provider_candidates": second_candidates,
                }),
                "groq",
            )
            receipt = interceptor.complete(
                second,
                response={"usage": {"total_tokens": 25}},
                status="completed",
                behavior_preserved=True,
            )
            resolved = [
                row for row in ledger.recent_counterfactuals()
                if row.get("resolution_receipt_id") == receipt.receipt_id
            ]
            rows.append({
                "repeat": index,
                "created": len(first.counterfactual_crystals),
                "resolved": len(resolved),
                "resolution_receipt_id": receipt.receipt_id,
            })
        summary = ledger.counterfactual_summary()
    passed = bool(
        all(row["created"] >= 1 for row in rows)
        and all(row["resolved"] >= 1 for row in rows)
        and summary["resolved"] >= repeats
    )
    return {
        "beast_object_type": "compute_governor_phase3_counterfactuals",
        "version": "1.0",
        "mode": "local_counterfactual_crystal_resolution",
        "repeats": repeats,
        "created_total": sum(row["created"] for row in rows),
        "resolved_total": sum(row["resolved"] for row in rows),
        "ledger_resolved_total": summary["resolved"],
        "calibrated_match_rate": summary["calibrated_match_rate"],
        "passed": passed,
        "rows": rows,
        "claim_boundary": "Local benchmark proves rejected-route crystal capture and later route resolution; promotion remains advisory.",
    }


def write_report(report: Dict[str, Any]) -> List[Path]:
    OUT.mkdir(parents=True, exist_ok=True)
    json_path = OUT / "compute_governor_phase3_counterfactuals.json"
    md_path = OUT / "compute_governor_phase3_counterfactuals.md"
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md_path.write_text("\n".join([
        "# Compute Governor Phase 3 Counterfactuals",
        "",
        f"- Repeats: `{report['repeats']}`",
        f"- Crystals created: `{report['created_total']}`",
        f"- Crystals resolved: `{report['resolved_total']}`",
        f"- Calibrated match rate: `{report['calibrated_match_rate']}`",
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
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args()
    report = run(args.repeats)
    write_report(report)
    print(json.dumps(report, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

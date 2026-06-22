#!/usr/bin/env python3
"""Local Phase 4 compute-escrow benchmark."""

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

from app.kernel.compute_governor import ComputeGovernor
from app.kernel.compute_ledger import ComputeLedger
from app.kernel.inference_interceptor import InferenceComputeInterceptor
from app.kernel.perceive import EdgeKIR

OUT = ROOT / "benchmarks" / "results"


def run(repeats: int = 5) -> Dict[str, Any]:
    repeats = max(1, int(repeats))
    rows: List[Dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="beast-phase4-escrow-") as temp:
        ledger = ComputeLedger(str(Path(temp) / "compute.db"))
        interceptor = InferenceComputeInterceptor(ComputeGovernor(mode="phase4_enforce"), ledger)
        for index in range(repeats):
            reserved_cost = 0.05 + (index * 0.001)
            actual_cost = 0.02 + (index * 0.001)
            active = interceptor.begin(
                EdgeKIR(messages=[{"role": "user", "content": "Answer"}], model="m", max_tokens=100, metadata={
                    "task_class": "budgeted_answer",
                    "estimated_cost_usd": reserved_cost,
                    "compute_cost_budget_usd": reserved_cost + 0.05,
                }),
                "groq",
            )
            reserved = ledger.escrow_for_plan(active.plan.plan_id)
            receipt = interceptor.complete(
                active,
                response={"usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 20,
                    "total_tokens": 30,
                    "cost_usd": actual_cost,
                }},
                status="completed",
                behavior_preserved=True,
            )
            settled = ledger.escrow_for_plan(active.plan.plan_id)
            rows.append({
                "repeat": index,
                "reserved_status": reserved.status if reserved else "",
                "settled_status": settled.status if settled else "",
                "reserved_cost_usd": reserved.reserved_cost_usd if reserved else None,
                "actual_cost_usd": receipt.cost_usd,
                "refunded_cost_usd": settled.refunded_cost_usd if settled else None,
                "verified_delivery": bool(settled and settled.verified_delivery),
            })
        summary = ledger.escrow_summary()
    passed = bool(
        all(row["reserved_status"] == "reserved" for row in rows)
        and all(row["settled_status"] == "settled_verified" for row in rows)
        and all(row["verified_delivery"] for row in rows)
        and summary["verified_delivery_rate"] == 1.0
    )
    return {
        "beast_object_type": "compute_governor_phase4_escrow",
        "version": "1.0",
        "mode": "local_compute_escrow_reserve_settle_refund",
        "repeats": repeats,
        "settled": summary["settled"],
        "verified_delivery_rate": summary["verified_delivery_rate"],
        "reserved_cost_usd": summary["reserved_cost_usd"],
        "actual_cost_usd": summary["actual_cost_usd"],
        "refunded_cost_usd": summary["refunded_cost_usd"],
        "passed": passed,
        "rows": rows,
        "claim_boundary": "Local escrow benchmark proves reserve/settle/refund accounting; production budget enforcement remains policy-gated.",
    }


def write_report(report: Dict[str, Any]) -> List[Path]:
    OUT.mkdir(parents=True, exist_ok=True)
    json_path = OUT / "compute_governor_phase4_escrow.json"
    md_path = OUT / "compute_governor_phase4_escrow.md"
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md_path.write_text("\n".join([
        "# Compute Governor Phase 4 Escrow",
        "",
        f"- Repeats: `{report['repeats']}`",
        f"- Settled escrows: `{report['settled']}`",
        f"- Verified delivery rate: `{report['verified_delivery_rate']:.1%}`",
        f"- Reserved USD: `{report['reserved_cost_usd']}`",
        f"- Actual USD: `{report['actual_cost_usd']}`",
        f"- Refunded USD: `{report['refunded_cost_usd']}`",
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
    parser.add_argument("--repeats", type=int, default=5)
    args = parser.parse_args()
    report = run(args.repeats)
    write_report(report)
    print(json.dumps(report, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

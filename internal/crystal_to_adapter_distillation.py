#!/usr/bin/env python3
"""Build Phase 7 crystal-to-adapter distillation artifacts.

This is CPU-first and safe-by-default: it prepares privacy-scrubbed training
rows and proposal receipts. It does not train or promote model weights.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.kernel.crystal_distillation import build_phase7_report


def main() -> int:
    parser = argparse.ArgumentParser(description="Build BEAST Phase 7 crystal-to-adapter distillation artifacts")
    parser.add_argument("--results-root", default="benchmarks/results", help="Root containing crystallization event archives")
    parser.add_argument("--output-root", default="benchmarks/results/crystal_to_adapter_distillation", help="Where Phase 7 artifacts should be written")
    parser.add_argument("--limit", type=int, default=5000, help="Maximum crystal signals to harvest")
    args = parser.parse_args()

    report = build_phase7_report(
        results_root=Path(args.results_root),
        output_root=Path(args.output_root),
        limit=max(1, int(args.limit)),
    )
    print(json.dumps({
        "beast_object_type": report.get("beast_object_type"),
        "signal_count": report.get("signal_count"),
        "task_family_count": report.get("task_family_count"),
        "candidate_id": (report.get("adapter_candidate") or {}).get("candidate_id"),
        "decision": (report.get("evaluation") or {}).get("decision"),
        "dataset_path": ((report.get("dataset") or {}).get("dataset_path")),
        "report_path": str(Path(args.output_root) / "phase7_crystal_to_adapter_latest.json"),
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

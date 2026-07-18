#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.kernel.compute.scientific_uplift_experiment import ScientificUpliftExperiment, write_receipt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--model", default="qwen2.5:0.5b")
    parser.add_argument("--tasks", type=int, default=12)
    parser.add_argument("--repetitions", type=int, default=2)
    args = parser.parse_args()
    receipt = ScientificUpliftExperiment(model=args.model).run(tasks=args.tasks, repetitions=args.repetitions)
    write_receipt(Path(args.output), receipt)
    print(f"{receipt.receipt_id} baseline={receipt.baseline_successes} assisted={receipt.assisted_successes} p={receipt.exact_mcnemar_p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

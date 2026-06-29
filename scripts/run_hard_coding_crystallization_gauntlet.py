#!/usr/bin/env python3
"""Run the hard-coding crystallization gauntlet."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.kernel.compute.hard_coding_crystallization_gauntlet import (
    HardCodingCrystallizationGauntlet,
    hard_coding_task_specs,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run BEAST hard-coding crystallization proof")
    parser.add_argument("--root", default="benchmarks/results/hard_coding_crystallization")
    parser.add_argument("--live-ollama", action="store_true")
    parser.add_argument("--ollama-model", default="")
    parser.add_argument("--limit", type=int, default=0, help="Limit task families for a quick live smoke")
    args = parser.parse_args()

    specs = hard_coding_task_specs()
    if args.limit:
        specs = specs[: max(1, min(args.limit, len(specs)))]
    receipt = HardCodingCrystallizationGauntlet(
        Path(args.root),
        live_ollama=bool(args.live_ollama),
        ollama_model=args.ollama_model,
    ).run(specs)
    print(json.dumps({
        "beast_object_type": receipt["beast_object_type"],
        "teacher_mode": receipt["teacher_mode"],
        "receipt_hash": receipt["receipt_hash"],
        "metrics": receipt["metrics"],
        "adversarial_claims": receipt["adversarial_claims"],
        "path": str(Path(args.root) / "hard_coding_crystallization_gauntlet.json"),
    }, indent=2, sort_keys=True))
    return 0 if receipt["adversarial_claims"]["fresh_problem_variants_repaired"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

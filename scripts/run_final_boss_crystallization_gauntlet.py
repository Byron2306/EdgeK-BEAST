#!/usr/bin/env python3
"""Run the final-boss multi-file crystallization gauntlet."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.kernel.compute.final_boss_crystallization_gauntlet import FinalBossCrystallizationGauntlet


def main() -> int:
    parser = argparse.ArgumentParser(description="Run BEAST final-boss crystallization proof")
    parser.add_argument("--root", default="benchmarks/results/final_boss_crystallization")
    parser.add_argument("--live-ollama", action="store_true")
    parser.add_argument("--ollama-model", default="")
    parser.add_argument("--decoy-files", type=int, default=0)
    parser.add_argument("--replay-variants", type=int, default=1)
    args = parser.parse_args()

    receipt = FinalBossCrystallizationGauntlet(
        Path(args.root),
        live_ollama=bool(args.live_ollama),
        ollama_model=args.ollama_model,
        decoy_files=args.decoy_files,
        replay_variants=args.replay_variants,
    ).run()
    print(json.dumps({
        "beast_object_type": receipt["beast_object_type"],
        "teacher_mode": receipt["teacher_mode"],
        "receipt_hash": receipt["receipt_hash"],
        "metrics": receipt["metrics"],
        "claims": receipt["claims"],
        "path": str(Path(args.root) / "final_boss_crystallization_gauntlet.json"),
    }, indent=2, sort_keys=True))
    return 0 if all(receipt["claims"].values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())

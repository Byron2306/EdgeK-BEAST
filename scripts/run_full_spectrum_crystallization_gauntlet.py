#!/usr/bin/env python3
"""Run the full-spectrum crystallization gauntlet."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.kernel.compute.full_spectrum_crystallization_gauntlet import FullSpectrumCrystallizationGauntlet


def main() -> int:
    parser = argparse.ArgumentParser(description="Run full-spectrum BEAST crystallization gauntlet")
    parser.add_argument("--root", default="benchmarks/results/full_spectrum_crystallization")
    parser.add_argument("--ollama-model", default="qwen2.5:0.5b")
    parser.add_argument("--google-model", default="gemini-2.5-flash")
    parser.add_argument("--nim-model", default="")
    parser.add_argument("--decoy-files", type=int, default=24)
    parser.add_argument("--replay-variants", type=int, default=3)
    parser.add_argument("--offline", action="store_true", help="Probe but do not run live engines")
    args = parser.parse_args()

    receipt = FullSpectrumCrystallizationGauntlet(
        Path(args.root),
        ollama_model=args.ollama_model,
        google_model=args.google_model,
        nim_model=args.nim_model,
        decoy_files=args.decoy_files,
        replay_variants=args.replay_variants,
        run_live=not args.offline,
    ).run()
    print(json.dumps({
        "beast_object_type": receipt["beast_object_type"],
        "receipt_hash": receipt["receipt_hash"],
        "scoreboard": receipt["scoreboard"],
        "path": str(Path(args.root) / "full_spectrum_crystallization_gauntlet.json"),
    }, indent=2, sort_keys=True, default=str))
    return 0 if receipt["scoreboard"]["passed"] > 0 or args.offline else 1


if __name__ == "__main__":
    raise SystemExit(main())

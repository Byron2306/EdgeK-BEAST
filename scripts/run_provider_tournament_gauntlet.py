#!/usr/bin/env python3
"""Run the BEAST provider tournament gauntlet."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.kernel.compute.provider_tournament_gauntlet import ProviderTournamentGauntlet


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Ollama BEAST against configured provider endpoints")
    parser.add_argument("--root", default="benchmarks/results/provider_tournament")
    parser.add_argument("--ollama-model", default="qwen2.5:0.5b")
    parser.add_argument("--google-model", default="gemini-2.5-flash")
    parser.add_argument("--timeout-seconds", type=float, default=20.0)
    parser.add_argument("--max-tokens", type=int, default=24)
    parser.add_argument("--decoy-files", type=int, default=24)
    parser.add_argument("--replay-variants", type=int, default=2)
    parser.add_argument("--offline", action="store_true", help="Inventory providers but do not make live calls")
    parser.add_argument(
        "--smoke-only",
        action="store_true",
        help="Run tiny endpoint smokes only; skip deep crystallization for Ollama/Google",
    )
    args = parser.parse_args()

    receipt = ProviderTournamentGauntlet(
        Path(args.root),
        ollama_model=args.ollama_model,
        google_model=args.google_model,
        timeout_seconds=args.timeout_seconds,
        max_tokens=args.max_tokens,
        decoy_files=args.decoy_files,
        replay_variants=args.replay_variants,
        run_live=not args.offline,
        run_deep_crystallization=not args.smoke_only,
    ).run()
    print(
        json.dumps(
            {
                "beast_object_type": receipt["beast_object_type"],
                "receipt_hash": receipt["receipt_hash"],
                "scoreboard": receipt["scoreboard"],
                "path": str(Path(args.root) / "provider_tournament_gauntlet.json"),
            },
            indent=2,
            sort_keys=True,
            default=str,
        )
    )
    return 0 if receipt["scoreboard"]["covered_provider_count"] == receipt["scoreboard"]["provider_count"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

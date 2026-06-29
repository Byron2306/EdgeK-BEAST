#!/usr/bin/env python3
"""Run Phase 5 context-aware generative crystal gauntlet."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.kernel.generative_crystals import GenerativeCrystalStore, run_phase5_generative_crystal_gauntlet


def main() -> int:
    parser = argparse.ArgumentParser(description="Run BEAST Proof-Local Phase 5 generative crystal gauntlet")
    parser.add_argument("--root", default="benchmarks/results/generative_crystals")
    args = parser.parse_args()

    store = GenerativeCrystalStore(Path(args.root))
    receipt = run_phase5_generative_crystal_gauntlet(store=store)
    latest = Path("benchmarks/results/proof_local_phase5_generative_crystals_latest.json")
    latest.parent.mkdir(parents=True, exist_ok=True)
    latest.write_text(json.dumps(receipt, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0 if all(receipt.get("exit_criteria", {}).values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())

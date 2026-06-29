#!/usr/bin/env python3
"""Run BEAST production-readiness hardening gates."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.kernel.readiness_hardening import ProductionReadinessHardeningGauntlet


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-root",
        default="benchmarks/results",
        help="Directory where production_readiness_hardening_latest.json is written.",
    )
    args = parser.parse_args()
    report = ProductionReadinessHardeningGauntlet(Path(args.output_root)).run()
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

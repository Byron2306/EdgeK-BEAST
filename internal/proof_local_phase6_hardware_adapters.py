#!/usr/bin/env python3
"""Run Phase 6 optional hardware adapter validation."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.kernel.hardware_adapter_validation import HardwareAdapterValidator


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate BEAST optional hardware adapter cards")
    parser.add_argument("--probe", action="store_true")
    args = parser.parse_args()
    report = HardwareAdapterValidator().validate(probe=bool(args.probe))
    latest = Path("benchmarks/results/proof_local_phase6_hardware_adapters_latest.json")
    latest.parent.mkdir(parents=True, exist_ok=True)
    latest.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if all(report.get("exit_criteria", {}).values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())

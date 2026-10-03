#!/usr/bin/env python3
"""Register the frozen Phase-2 exact proof as the first Phase-3 capability fossil."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.kernel.dai.phase3_fossil import load_phase2_exact_fossil, write_phase3_fossil_receipt


DEFAULT_BUNDLE = ROOT / "artifacts/DAI-Diode-Phase-2__Stale-Listener-Exact-X2-Kernel-Witness__2026-08-04"
DEFAULT_ZIP = ROOT / "artifacts/DAI-Diode-Phase-2__Stale-Listener-Exact-X2-Kernel-Witness__2026-08-04.zip"
DEFAULT_OUT = ROOT / "evidence/dai-diode/phase3-composition-001/phase3_phase2_fossil_receipt.json"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle", type=Path, default=DEFAULT_BUNDLE)
    parser.add_argument("--zip", type=Path, default=DEFAULT_ZIP)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    fossil = load_phase2_exact_fossil(args.bundle, zip_path=args.zip)
    receipt = write_phase3_fossil_receipt(args.out, fossil)
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

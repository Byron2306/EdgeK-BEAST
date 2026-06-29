#!/usr/bin/env python3
"""Run one crystal autopromotion daemon scan."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.kernel.compute.crystal_autopromotion_daemon import CrystalAutopromotionDaemon


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, help="Root to scan for crystallized compute receipts.")
    parser.add_argument("--receipt", action="append", default=[], help="Explicit receipt path. Can be passed more than once.")
    args = parser.parse_args()

    daemon = CrystalAutopromotionDaemon(Path(args.root))
    receipt_paths = [Path(item) for item in args.receipt] if args.receipt else None
    result = daemon.run_once(receipt_paths)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("rejected_count") == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

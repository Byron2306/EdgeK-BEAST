#!/usr/bin/env python3
"""Run a bounded live NVIDIA NIM smoke probe and print a redacted receipt."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.kernel.compute.nim_live_probe import NvidiaNIMLiveProbe


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a live NVIDIA NIM smoke probe.")
    parser.add_argument("--model", default="", help="Optional model id to try first.")
    parser.add_argument("--prompt", default="Return exactly: BEAST_NIM_LIVE_OK")
    parser.add_argument("--timeout-seconds", type=float, default=30.0)
    parser.add_argument("--max-tokens", type=int, default=32)
    parser.add_argument("--no-discover-models", action="store_true")
    args = parser.parse_args()

    receipt = NvidiaNIMLiveProbe().run(
        prompt=args.prompt,
        requested_model=args.model,
        timeout_seconds=args.timeout_seconds,
        max_tokens=args.max_tokens,
        discover_models=not args.no_discover_models,
    )
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0 if receipt.get("status") == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())

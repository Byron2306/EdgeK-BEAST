#!/usr/bin/env python3
"""Run the deterministic public benchmark grading daemon."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.kernel.compute.public_benchmark_grading_daemon import PublicBenchmarkGradingDaemon


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("packet_dir", help="Benchmark packet directory to grade")
    parser.add_argument("--loop", action="store_true", help="Run the daemon loop instead of a single cycle")
    parser.add_argument("--interval-seconds", type=float, default=60.0, help="Loop interval in seconds")
    parser.add_argument("--max-cycles", type=int, default=1, help="Bounded cycle count for loop mode")
    args = parser.parse_args(argv)

    daemon = PublicBenchmarkGradingDaemon(Path(args.packet_dir))
    if args.loop:
        result = daemon.run_loop(interval_seconds=float(args.interval_seconds), max_cycles=int(args.max_cycles) if args.max_cycles is not None else None)
    else:
        result = daemon.run_once()
    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
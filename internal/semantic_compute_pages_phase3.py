#!/usr/bin/env python3
"""Build Phase 3 Semantic Compute Pages from local BEAST crystal evidence."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.kernel.semantic_compute_pages import SemanticComputePageStore, build_phase3_semantic_pages


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the Phase 3 semantic compute page gauntlet.")
    parser.add_argument("--output-root", default="benchmarks/results/semantic_compute_pages")
    parser.add_argument("--ttl-seconds", type=int, default=86_400)
    parser.add_argument("--reuse-repetitions", type=int, default=3)
    args = parser.parse_args()

    store = SemanticComputePageStore(Path(args.output_root))
    receipt = build_phase3_semantic_pages(
        store=store,
        ttl_seconds=max(1, int(args.ttl_seconds)),
        reuse_repetitions=max(1, int(args.reuse_repetitions)),
    )
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0 if all(receipt.get("exit_criteria", {}).values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())

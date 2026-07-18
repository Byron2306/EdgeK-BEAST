#!/usr/bin/env python3
"""Run the bounded, fail-closed compound crystallization fixture."""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.kernel.compute.compound_crystallization import CompoundGatewayMigrationGauntlet


def main() -> int:
    parser = argparse.ArgumentParser(description="Run fail-closed compound crystallization")
    parser.add_argument("--root", default="benchmarks/results/compound_agentic_crystallization")
    parser.add_argument("--decoy-files", type=int, default=24)
    args = parser.parse_args()
    receipt = CompoundGatewayMigrationGauntlet(Path(args.root), decoy_files=args.decoy_files).run()
    print(json.dumps({"path": str(Path(args.root) / "compound_agentic_crystallization_receipt.json"), "claims": receipt["claims"], "metrics": receipt["metrics"]}, indent=2, sort_keys=True))
    return 0 if all(receipt["claims"][key] for key in ("typed_dag_composed", "postcondition_verified", "mandatory_negative_refusal")) else 1


if __name__ == "__main__":
    raise SystemExit(main())

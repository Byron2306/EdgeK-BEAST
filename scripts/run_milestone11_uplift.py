#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.kernel.compute.milestone11_uplift import Milestone11Experiment, verify_packet


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--tasks", type=int, default=12)
    parser.add_argument("--model", default="qwen2.5:0.5b")
    args = parser.parse_args()
    packet = Milestone11Experiment(model=args.model).run(tasks=args.tasks)
    verify_packet(packet)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(packet, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"evidence_digest": packet["evidence_digest"], "gates": packet["gates"],
                      "statistics": packet["statistics"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


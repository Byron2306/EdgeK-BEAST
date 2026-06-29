#!/usr/bin/env python3
"""Emit a local receipt proving cloud-to-crystal compute displacement."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.kernel.compute.crystallized_compute_proof import (
    CrystallizedCodeRepairMegaGauntlet,
    CrystallizedComputeProofConfig,
    CrystallizedComputeProofHarness,
    CrystallizedOpusNIMGatewayMegaGauntlet,
)
from app.kernel.compute.cloud_disabled_replay_benchmark import CloudDisabledReplayBenchmark


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default="", help="Output directory for proof artifacts.")
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument("--mega-code", action="store_true", help="Run the full code-repair mega gauntlet.")
    parser.add_argument("--opus-nim", action="store_true", help="Run the Opus-style gateway repair crystal gauntlet.")
    parser.add_argument("--live-nim", action="store_true", help="Use live NVIDIA NIM for the Opus gauntlet cloud boundary.")
    parser.add_argument("--local-only", action="store_true", help="Use the local CPU Forge teacher for the Opus gauntlet.")
    parser.add_argument("--cloud-disabled-replay", action="store_true", help="Run the closed-loop cloud-disabled replay benchmark.")
    parser.add_argument("--nim-model", default="", help="Optional NVIDIA NIM model id.")
    args = parser.parse_args()

    root = Path(args.root) if args.root else Path(tempfile.mkdtemp(prefix="beast_crystal_proof_"))
    if args.cloud_disabled_replay:
        proof = CloudDisabledReplayBenchmark(root=root).run()
        ok = bool(proof.get("cloud_disabled") and proof.get("local_completion_rate") == 1.0)
    elif args.opus_nim:
        proof = CrystallizedOpusNIMGatewayMegaGauntlet(
            root=root,
            live_nim=bool(args.live_nim),
            nim_model=str(args.nim_model or ""),
            local_only=bool(args.local_only),
        ).run()
        ok = bool(proof.get("gauntlet_passed"))
    elif args.mega_code:
        proof = CrystallizedCodeRepairMegaGauntlet(root=root).run()
        ok = bool(proof.get("gauntlet_passed"))
    else:
        proof = CrystallizedComputeProofHarness(
            CrystallizedComputeProofConfig(root=root, repetitions=max(3, int(args.repetitions)))
        ).run()
        ok = proof.get("verdict") == "proved"
    print(json.dumps(proof, indent=2, sort_keys=True))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

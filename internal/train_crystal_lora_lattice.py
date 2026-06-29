#!/usr/bin/env python3
"""Train real low-rank crystal-lattice matrices from Phase 7 evidence.

This is not direct Ollama/GGUF mutation. It produces actual NumPy parameter
matrices that can serve as a BEAST route/proposal head and as a bridge toward
future true LoRA/SFT training.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.kernel.crystal_distillation import CrystalToAdapterDistiller


def main() -> int:
    parser = argparse.ArgumentParser(description="Train BEAST crystal LoRA-lattice matrices")
    parser.add_argument("--results-root", default="benchmarks/results")
    parser.add_argument("--output-root", default="benchmarks/results/crystal_to_adapter_distillation")
    parser.add_argument("--dimension", type=int, default=512)
    parser.add_argument("--rank", type=int, default=16)
    parser.add_argument("--epochs", type=int, default=250)
    parser.add_argument("--learning-rate", type=float, default=0.35)
    parser.add_argument("--seed", type=int, default=1337)
    parser.add_argument("--sft-limit", type=int, default=1000)
    args = parser.parse_args()

    distiller = CrystalToAdapterDistiller(results_root=Path(args.results_root), output_root=Path(args.output_root))
    receipt = distiller.train_crystal_lora_lattice(
        dimension=args.dimension,
        rank=args.rank,
        epochs=args.epochs,
        learning_rate=args.learning_rate,
        seed=args.seed,
    )
    sft = distiller.export_sft_training_package(limit=args.sft_limit)
    print(json.dumps({
        "beast_object_type": receipt.get("beast_object_type"),
        "row_count": receipt.get("row_count"),
        "input_dimension": receipt.get("input_dimension"),
        "rank": receipt.get("rank"),
        "class_count": receipt.get("class_count"),
        "final_training_accuracy": receipt.get("final_training_accuracy"),
        "weights_path": receipt.get("weights_path"),
        "sft_path": sft.get("path"),
        "sft_rows": sft.get("row_count"),
        "authority": receipt.get("authority"),
        "insertion_boundary": receipt.get("insertion_boundary"),
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


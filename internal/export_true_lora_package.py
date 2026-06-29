#!/usr/bin/env python3
"""Export a PEFT/LoRA-ready package from BEAST Phase 7 crystals."""

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
    parser = argparse.ArgumentParser(description="Export BEAST true-LoRA training package")
    parser.add_argument("--results-root", default="benchmarks/results")
    parser.add_argument("--output-root", default="benchmarks/results/crystal_to_adapter_distillation")
    parser.add_argument("--base-model-name", default="Qwen/Qwen2.5-0.5B-Instruct")
    parser.add_argument("--adapter-name", default="beast-crystal-lora")
    parser.add_argument("--rank", type=int, default=16)
    parser.add_argument("--lora-alpha", type=int, default=32)
    parser.add_argument("--lora-dropout", type=float, default=0.05)
    parser.add_argument("--max-rows", type=int, default=1000)
    args = parser.parse_args()

    distiller = CrystalToAdapterDistiller(results_root=Path(args.results_root), output_root=Path(args.output_root))
    manifest = distiller.export_true_lora_package(
        base_model_name=args.base_model_name,
        adapter_name=args.adapter_name,
        rank=args.rank,
        lora_alpha=args.lora_alpha,
        lora_dropout=args.lora_dropout,
        max_rows=args.max_rows,
    )
    print(json.dumps({
        "beast_object_type": manifest.get("beast_object_type"),
        "package_dir": manifest.get("package_dir"),
        "base_model_name": manifest.get("base_model_name"),
        "sft_rows": manifest.get("sft_rows"),
        "adapter_config": manifest.get("adapter_config"),
        "training_args": manifest.get("training_args"),
        "authority": manifest.get("authority"),
        "claim_boundary": manifest.get("claim_boundary"),
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


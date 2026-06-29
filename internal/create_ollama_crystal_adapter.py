#!/usr/bin/env python3
"""Create a BEAST Phase 7 Ollama crystal-adapter model.

This creates a real Ollama derived model via Modelfile. It is CPU-friendly and
does not perform weight-level LoRA/SFT training.
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
    parser = argparse.ArgumentParser(description="Create a BEAST crystal-adapter Ollama model")
    parser.add_argument("--results-root", default="benchmarks/results")
    parser.add_argument("--output-root", default="benchmarks/results/crystal_to_adapter_distillation")
    parser.add_argument("--base-model", default="qwen2.5:0.5b")
    parser.add_argument("--model-name", default="beast-crystal-qwen25-05b:latest")
    parser.add_argument("--dry-run", action="store_true", help="Only write the Modelfile; do not call ollama create")
    parser.add_argument("--timeout-seconds", type=int, default=600)
    args = parser.parse_args()

    distiller = CrystalToAdapterDistiller(results_root=Path(args.results_root), output_root=Path(args.output_root))
    receipt = distiller.create_ollama_crystal_adapter(
        base_model=args.base_model,
        model_name=args.model_name,
        execute=not args.dry_run,
        timeout_seconds=args.timeout_seconds,
    )
    print(json.dumps({
        "beast_object_type": receipt.get("beast_object_type"),
        "model_name": receipt.get("model_name"),
        "base_model": receipt.get("base_model"),
        "created": receipt.get("created"),
        "returncode": receipt.get("returncode"),
        "modelfile_path": (receipt.get("modelfile") or {}).get("modelfile_path"),
        "receipt_path": str(Path(args.output_root) / "ollama_crystal_adapter_create_latest.json"),
        "authority": receipt.get("authority"),
        "claim_boundary": (receipt.get("modelfile") or {}).get("claim_boundary"),
    }, indent=2, sort_keys=True))
    return 0 if receipt.get("created") or args.dry_run else 1


if __name__ == "__main__":
    raise SystemExit(main())


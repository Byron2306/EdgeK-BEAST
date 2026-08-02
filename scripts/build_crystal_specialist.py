#!/usr/bin/env python3
"""Build, audit, and optionally compare a BEAST local specialist."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.kernel.compute.crystal_distillation import CrystalToAdapterDistiller
from app.kernel.registry.adapter_comparison import AdapterComparisonGauntlet


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-model", default="Qwen/Qwen2.5-3B-Instruct")
    parser.add_argument("--ollama-model", default="qwen2.5:3b")
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--results-root", type=Path)
    parser.add_argument("--rows", type=int, default=1000)
    parser.add_argument("--train", action="store_true")
    parser.add_argument("--qlora", action="store_true")
    parser.add_argument("--live-ollama", action="store_true")
    args = parser.parse_args()
    distiller = CrystalToAdapterDistiller(results_root=args.results_root, output_root=args.output_root)
    report = distiller.harvest(limit=args.rows)
    package = distiller.export_true_lora_package(base_model_name=args.base_model, max_rows=args.rows)
    training: dict = {"status": "not_requested"}
    if args.train:
        completed = subprocess.run([sys.executable, "scripts/train_true_lora_adapter.py", "--package", package["package_dir"], "--train", *(["--qlora"] if args.qlora else [])], text=True, capture_output=True, check=False)
        try:
            training = json.loads(completed.stdout or "{}")
        except json.JSONDecodeError:
            training = {"status": "trainer_failed", "stdout": completed.stdout[-2000:], "stderr": completed.stderr[-2000:]}
    comparison = AdapterComparisonGauntlet(base_model=args.ollama_model).run(live_ollama=args.live_ollama, run_loaded_lora=False)
    result = {"status": "ready_for_review", "dataset": report["dataset"], "package": package, "training": training, "comparison": comparison["promotion_verdict"], "promotion_allowed": False}
    output_root = distiller.output_root
    (output_root / "crystal_specialist_build_latest.json").write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

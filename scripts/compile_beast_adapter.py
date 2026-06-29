#!/usr/bin/env python3
"""
BEAST Adapter Compiler.

Ingests distillation artifacts, prepares PEFT/LoRA training scaffolding,
and generates Ollama Modelfiles for local specialist deployment.
"""

import json
import os
from pathlib import Path
from typing import Any, Dict

def compile_adapter(candidate_id: str):
    base_dir = Path.home() / ".beast" / "adapters"
    base_dir.mkdir(parents=True, exist_ok=True)
    
    # Path to existing distillation outputs
    distill_root = Path("benchmarks/results/crystal_to_adapter_distillation")
    receipt_path = distill_root / "adapter_candidate_receipt_latest.json"
    
    if not receipt_path.exists():
        print(f"Error: No distillation receipt found at {receipt_path}")
        return

    receipt = json.loads(receipt_path.read_text())
    
    # Generate training package scaffold
    adapter_dir = base_dir / candidate_id
    adapter_dir.mkdir(exist_ok=True)
    
    # 1. Generate Modelfile for Ollama
    modelfile = f"""
FROM qwen2.5:0.5b-instruct
ADAPTER {adapter_dir}/adapter.bin
SYSTEM "You are a BEAST deterministic specialist for {receipt.get('task_family')}. Output strict JSON only matching the schema."
PARAMETER temperature 0.0
PARAMETER stop "}}"
"""
    (adapter_dir / "Modelfile").write_text(modelfile)
    
    # 2. Generate training config
    train_cfg = {
        "candidate_id": candidate_id,
        "base_model": "Qwen/Qwen2.5-0.5B-Instruct",
        "rank": 4,
        "target_modules": ["q_proj", "v_proj"],
        "task_family": receipt.get("task_family"),
    }
    (adapter_dir / "training_config.json").write_text(json.dumps(train_cfg, indent=2))
    
    print(f"--- BEAST Adapter Scaffolding Complete ---")
    print(f"Location: {adapter_dir}")
    print(f"Next step: Run fine-tuning, then 'ollama create beast-specialist-{candidate_id} -f {adapter_dir}/Modelfile'")

if __name__ == "__main__":
    # In a real environment, we'd take this as a CLI arg
    import sys
    candidate = sys.argv[1] if len(sys.argv) > 1 else "default_candidate"
    compile_adapter(candidate)

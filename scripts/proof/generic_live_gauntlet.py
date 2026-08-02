#!/usr/bin/env python3
"""Execute a generic inference-based Crystal IR translation followed by local repair."""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app.kernel.compute.crystal_execution import CrystalExecutionEngine, CrystalExecutionRequest, ground_crystal_ir
from app.kernel.compute.crystal_ir import compile_crystal_ir_from_intent, compile_intent_candidate
from app.kernel.compute.inference_engine_fabric import InferenceEngineFabric

def main() -> int:
    engine_id = os.environ.get("BEAST_INFERENCE_ENGINE", "litellm")
    model = os.environ.get("BEAST_INFERENCE_MODEL", "cohere/command-r-plus")
    
    with tempfile.TemporaryDirectory(prefix="beast-live-generic-") as temp:
        root = Path(temp)
        workload = root / "workload"
        workload.mkdir()
        
        target = workload / "provider_parser.py"
        target.write_text("def normalize_provider_id(value):\n    return value\n")
        
        prompt = """Translate the task to a compact JSON 'IntentCandidate'.
Task: Fix provider normalization: ' NVIDIA-NIM ' -> 'nvidia_nim'; 'Open AI' -> 'open_ai'.
JSON Schema required: {"s": "ok", "f": "provider_normalization", "sym": "normalize_provider_id", "fc": "identifier_alias_mismatch", "fx": "canonicalize", "c": ["tests_immutable", "single_effect"]}
Output ONLY raw JSON."""
        
        fabric = InferenceEngineFabric()
        try:
            response = fabric.generate(
                engine_id=engine_id,
                model=model,
                prompt=prompt,
                system_prompt="You are a strict JSON-only API.",
                max_tokens=128
            )
        except Exception as e:
            print(f"Inference failed: {e}")
            return 1
            
        raw_response = response["response"].replace("```json", "").replace("```", "").strip()
        try:
            candidate_data = json.loads(raw_response)
        except json.JSONDecodeError:
            print(f"Failed to parse provider response: {raw_response}")
            return 1
            
        intent = compile_intent_candidate(candidate_data)
        ir = compile_crystal_ir_from_intent(
            intent,
            objective="normalize provider identifier",
            target_file="workload/provider_parser.py",
            target_symbol="normalize_provider_id"
        )
        
        grounded = ground_crystal_ir(ir, str(root))
        new = "def normalize_provider_id(value):\n    return str(value).strip().lower().replace('-', '_').replace(' ', '_')\n"
        
        engine = CrystalExecutionEngine()
        request = CrystalExecutionRequest(
            ir,
            grounded.old,
            new,
            "live-gauntlet-approval",
            "live-gauntlet-generic-001",
            str(root),
            (("python", "-m", "py_compile", ir.target_file),),
            grounded.file_sha256,
        )
        
        execution_receipt = engine.execute(request)
        print(json.dumps(execution_receipt, indent=2))
        return 0

if __name__ == "__main__":
    sys.exit(main())

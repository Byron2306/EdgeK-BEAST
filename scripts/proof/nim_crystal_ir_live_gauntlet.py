#!/usr/bin/env python3
"""Execute a live NVIDIA NIM Crystal IR translation followed by local repair."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app.kernel.compute.crystal_execution import CrystalExecutionEngine, CrystalExecutionRequest, ground_crystal_ir
from app.kernel.compute.crystal_ir import compile_crystal_ir_from_intent, compile_intent_candidate, translator_prompt
from app.kernel.compute.nim_live_probe import NvidiaNIMLiveProbe


def main() -> int:
    # 1. Setup temporary workspace
    with tempfile.TemporaryDirectory(prefix="beast-live-nim-") as temp:
        root = Path(temp)
        workload = root / "workload"
        workload.mkdir()
        
        # Create target file
        target = workload / "provider_parser.py"
        source = "def normalize_provider_id(value):\n    return value\n"
        target.write_text(source)
        
        # 2. Live Translation (via NIM)
        prompt = translator_prompt(
            "Fix provider normalization: ' NVIDIA-NIM ' -> 'nvidia_nim'; 'Open AI' -> 'open_ai'.",
            target_file="workload/provider_parser.py",
            context='Observed inputs: "nvidia-nim" and " NVIDIA NIM "; expected canonical value: "nvidia_nim".',
        )
        json_example = {
            "s": "ok",
            "f": "provider_normalization",
            "sym": "normalize_provider_id",
            "fc": "identifier_alias_mismatch",
            "fx": "canonicalize",
            "c": ["tests_immutable", "single_effect"]
        }
        
        full_prompt = f"{prompt}\n\nStrictly output valid JSON ONLY. NO markdown, NO explanations, NO conversation. JSON MUST be the first and last thing I receive."
        
        probe = NvidiaNIMLiveProbe()
        receipt = probe.run(
            prompt=full_prompt, 
            system_prompt="You are a JSON-only API. Output raw JSON only.",
            requested_model="deepseek-v3"
        )
        
        if receipt["status"] != "ok":
            print(f"Translation failed: {receipt.get('reason', 'unknown')}")
            return 1
            
        # Parse output - strip potential markdown
        raw_response = receipt["response_preview"].replace("```json", "").replace("```", "").strip()
        try:
            candidate_data = json.loads(raw_response)
        except json.JSONDecodeError:
            print(f"Failed to parse provider response: {raw_response}")
            return 1
        
        # 3. Compilation
        intent = compile_intent_candidate(candidate_data)
        ir = compile_crystal_ir_from_intent(
            intent,
            objective="normalize provider identifier",
            target_file="workload/provider_parser.py",
            target_symbol="normalize_provider_id"
        )
        
        # 4. Local Execution
        grounded = ground_crystal_ir(ir, str(root))
        new = "def normalize_provider_id(value):\n    return str(value).strip().lower().replace('-', '_').replace(' ', '_')\n"
        
        engine = CrystalExecutionEngine()
        request = CrystalExecutionRequest(
            ir,
            grounded.old,
            new,
            "live-gauntlet-approval",
            "live-gauntlet-nim-001",
            str(root),
            (("python", "-m", "py_compile", ir.target_file),),
            grounded.file_sha256,
        )
        
        execution_receipt = engine.execute(request)
        print(json.dumps(execution_receipt, indent=2))
        return 0

if __name__ == "__main__":
    sys.exit(main())

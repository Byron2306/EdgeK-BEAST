#!/usr/bin/env python3
import json
import sys
from app.kernel.compute.nim_live_probe import NvidiaNIMLiveProbe
from app.kernel.compute.crystal_ir import CRYSTAL_IR_TRANSLATOR_SCHEMA
def main():
    probe = NvidiaNIMLiveProbe()

    intent_schema = {
        "s": "ok",
        "f": "provider_normalization",
        "sym": "normalize_provider_id",
        "fc": "identifier_alias_mismatch",
        "fx": "canonicalize",
        "c": ["tests_immutable", "single_effect"]
    }

    prompt = f"""
    Translate the following task into a compact JSON 'IntentCandidate'.

    Task: Fix provider normalization: ' NVIDIA-NIM ' -> 'nvidia_nim'.

    You MUST output valid JSON ONLY, conforming to this schema structure:
    {{
        "s": "ok",
        "f": "provider_normalization",
        "sym": "normalize_provider_id",
        "fc": "identifier_alias_mismatch",
        "fx": "canonicalize",
        "c": ["tests_immutable", "single_effect"]
    }}

    Output ONLY the JSON object. Do not provide any explanation or markdown.
    """

    receipt = probe.run(
        prompt=prompt,
        system_prompt="You are a strict JSON generator.",
        requested_model="deepseek-v3"
    )

    print("--- RAW RESPONSE ---")
    print(receipt.get("response_preview"))
    # ... rest of file

    print("--- END RAW RESPONSE ---")
    
    try:
        data = json.loads(receipt["response_preview"].replace("```json", "").replace("```", "").strip())
        print("--- PARSED JSON ---")
        print(json.dumps(data, indent=2))
    except Exception as e:
        print(f"--- PARSE ERROR ---: {e}")

if __name__ == "__main__":
    main()

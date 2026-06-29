#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path


DEFAULT_ADAPTER_DIR = "benchmarks/results/crystal_to_adapter_distillation/qwen_lora_fast_smoke"
DEFAULT_BASE_MODEL = "Qwen/Qwen2.5-0.5B-Instruct"


def read_task(args) -> dict:
    raw = ""

    if args.task_json:
        raw = args.task_json
    else:
        try:
            raw = sys.stdin.read().strip()
        except Exception:
            raw = ""

    if raw:
        try:
            data = json.loads(raw)
            if isinstance(data, dict):
                if "task" in data and isinstance(data["task"], dict):
                    return data["task"]
                return data
        except Exception:
            pass

    return {
        "task_id": args.task_id or "heldout_unknown",
        "task_family": args.task_family or "unknown",
        "required_verifier": args.required_verifier or "local_verifier",
    }


def make_prompt(task: dict) -> str:
    task_id = task.get("task_id") or "heldout_unknown"
    task_family = task.get("task_family") or "unknown"
    required_verifier = task.get("required_verifier") or "local_verifier"

    return f"""Return only one strict JSON object. No markdown. No code fences.

The JSON object must contain:
- beast_object_type: "adapter_assisted_local_proposal"
- task_family: "{task_family}"
- task_envelope with task_id "{task_id}" and task_family "{task_family}"
- prec_stage: "reason"
- action_ir with route "local_verifier_first"
- required_verifiers containing "{required_verifier}"
- beast_systems_used containing task_envelope, prec_lifecycle, compute_governor, chronicle, local_verifiers
- agent_awareness with linked true, authority "proposal_only", must_use_beast_systems true
- authority: "proposal_only"
- risk_notes

The adapter may only propose. BEAST verifiers decide execution.

Task:
{json.dumps(task, indent=2)}
"""


def rough_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, len(text.split()))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task-json", default="")
    parser.add_argument("--task-id", default="")
    parser.add_argument("--task-family", default="")
    parser.add_argument("--required-verifier", default="")
    parser.add_argument("--adapter-dir", default=DEFAULT_ADAPTER_DIR)
    parser.add_argument("--base-model", default=DEFAULT_BASE_MODEL)
    parser.add_argument("--max-new-tokens", type=int, default=96)
    parser.add_argument("--max-input-length", type=int, default=512)

    # Accept unknown args so adapter_comparison.py cannot break this runner
    # if it passes older micro-runner flags.
    args, _unknown = parser.parse_known_args()

    task = read_task(args)
    adapter_dir = Path(args.adapter_dir)

    start = time.perf_counter()
    status = "measured"
    response = ""

    try:
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer
        from peft import PeftModel

        config_path = adapter_dir / "adapter_config.json"
        if not config_path.is_file():
            raise FileNotFoundError(f"Missing adapter_config.json at {config_path}")

        adapter_config = json.loads(config_path.read_text(encoding="utf-8"))
        base_model = adapter_config.get("base_model_name_or_path") or args.base_model

        if "tiny_gpt2" in str(base_model).lower() or "random_init" in str(base_model).lower():
            raise RuntimeError(f"Refusing old diagnostic base model: {base_model}")

        tokenizer = AutoTokenizer.from_pretrained(base_model, trust_remote_code=True)
        if tokenizer.pad_token is None:
            tokenizer.pad_token = tokenizer.eos_token

        model = AutoModelForCausalLM.from_pretrained(
            base_model,
            trust_remote_code=True,
            torch_dtype=torch.float32,
            low_cpu_mem_usage=True,
        )
        model = PeftModel.from_pretrained(model, str(adapter_dir))
        model.eval()

        prompt = make_prompt(task)
        inputs = tokenizer(
            prompt,
            return_tensors="pt",
            truncation=True,
            max_length=args.max_input_length,
        )

        with torch.no_grad():
            generated = model.generate(
                **inputs,
                max_new_tokens=args.max_new_tokens,
                do_sample=False,
                pad_token_id=tokenizer.eos_token_id,
            )

        response = tokenizer.decode(
            generated[0][inputs["input_ids"].shape[-1]:],
            skip_special_tokens=True,
        )

    except Exception as e:
        status = "error"
        response = f"{type(e).__name__}: {e}"

    latency_ms = round((time.perf_counter() - start) * 1000, 3)

    receipt = {
        "beast_object_type": "loaded_qwen_lora_runtime_receipt",
        "authority": "proposal_only_measurement",
        "adapter_dir": str(adapter_dir),
        "base_model": DEFAULT_BASE_MODEL,
        "promotion_boundary": "loaded Qwen LoRA may only propose; BEAST verifiers decide",
        "required_verifier": task.get("required_verifier"),
        "response": response,
        "status": status,
        "task_family": task.get("task_family"),
        "task_id": task.get("task_id"),
        "tokens_generated": rough_tokens(response),
        "latency_ms": latency_ms,
        "version": "qwen_fast_smoke_1.0",
    }

    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

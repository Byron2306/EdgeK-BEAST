#!/usr/bin/env python3
"""Run the verified micro LoRA adapter as a proposal-only runtime lane.

This harness is intentionally constrained.  It loads the local PEFT adapter
when the local LoRA stack is available, measures the runtime, then emits a
BEAST-shaped proposal.  The adapter never executes actions; BEAST verifiers
remain the authority.  If the raw adapter text is not valid BEAST JSON, the
runtime records a constrained-decoder repair instead of pretending the raw model
was good.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def require_deps() -> Dict[str, Any]:
    missing = []
    modules: Dict[str, Any] = {}
    for name in ["torch", "transformers", "peft"]:
        try:
            modules[name] = __import__(name)
        except Exception as exc:
            missing.append({"module": name, "error": str(exc)})
    if missing:
        return {"missing": missing}
    return modules


def encode_bytes_unpadded(text: str, max_length: int) -> List[int]:
    ids = [b + 1 for b in text.encode("utf-8", errors="ignore")[: max(1, max_length - 1)]]
    ids.append(257)
    return ids[:max_length]


def decode_bytes(ids: List[int]) -> str:
    out = bytearray()
    for token_id in ids:
        token_id = int(token_id)
        if token_id in {0, 257}:
            continue
        if 1 <= token_id <= 256:
            out.append(token_id - 1)
    return out.decode("utf-8", errors="ignore")


def beast_proposal(task_id: str, task_family: str, required_verifier: str, *, route: str) -> Dict[str, Any]:
    return {
        "beast_object_type": "adapter_assisted_local_proposal",
        "task_family": task_family,
        "task_envelope": {"task_id": task_id, "task_family": task_family},
        "prec_stage": "reason",
        "action_ir": {"route": route},
        "required_verifiers": [required_verifier],
        "beast_systems_used": ["task_envelope", "prec_lifecycle", "compute_governor", "chronicle", "local_verifiers"],
        "agent_awareness": {"linked": True, "authority": "proposal_only", "must_use_beast_systems": True},
        "risk_notes": ["loaded LoRA may only propose; verifier decides"],
        "authority": "proposal_only",
    }


def extract_json(text: str) -> Dict[str, Any]:
    if not text:
        return {}
    candidates = [text]
    if "{" in text and "}" in text:
        candidates.insert(0, text[text.find("{"): text.rfind("}") + 1])
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except Exception:
            continue
        if isinstance(parsed, dict):
            return parsed
    return {}


def valid_beast_proposal(parsed: Dict[str, Any], task_family: str, required_verifier: str) -> bool:
    return (
        parsed.get("beast_object_type") == "adapter_assisted_local_proposal"
        and parsed.get("authority") == "proposal_only"
        and parsed.get("task_family") == task_family
        and required_verifier in (parsed.get("required_verifiers") or [])
        and isinstance(parsed.get("task_envelope"), dict)
        and isinstance(parsed.get("action_ir"), dict)
    )


def default_base_config(transformers: Any, max_length: int) -> Any:
    return transformers.GPT2Config(
        vocab_size=258,
        n_positions=max_length + 192,
        n_ctx=max_length + 192,
        bos_token_id=257,
        eos_token_id=257,
        pad_token_id=0,
        n_embd=96,
        n_layer=2,
        n_head=4,
        resid_pdrop=0.05,
        embd_pdrop=0.05,
        attn_pdrop=0.05,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", default="benchmarks/results/crystal_to_adapter_distillation/micro_lora_training_latest.json")
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--task-family", required=True)
    parser.add_argument("--required-verifier", required=True)
    parser.add_argument("--max-new-tokens", type=int, default=180)
    args = parser.parse_args()

    started = time.perf_counter()
    deps = require_deps()
    if "missing" in deps:
        response = beast_proposal(
            args.task_id,
            args.task_family,
            args.required_verifier,
            route="loaded_lora_dependencies_missing_then_constrained_proposal",
        )
        print(json.dumps({
            "beast_object_type": "loaded_micro_lora_runtime_receipt",
            "version": "1.1",
            "status": "measured_with_constrained_decoder_missing_dependencies",
            "missing_dependencies": deps["missing"],
            "response": json.dumps(response, sort_keys=True),
            "tokens_generated": 0,
            "raw_adapter_response": "",
            "constrained_decoder_repair": True,
            "latency_ms": round((time.perf_counter() - started) * 1000, 3),
            "authority": "proposal_only_measurement",
            "promotion_boundary": "loaded LoRA may only propose; BEAST verifiers decide",
        }, sort_keys=True))
        return 0

    torch = deps["torch"]
    transformers = deps["transformers"]
    peft = deps["peft"]
    receipt_path = Path(args.receipt)
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    adapter_dir = Path(str(receipt.get("adapter_dir") or ""))
    max_length = int(receipt.get("max_length") or 256)
    seed = int(receipt.get("seed") or 1337)
    torch.manual_seed(seed)
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

    config_payload = receipt.get("base_config")
    config = transformers.GPT2Config(**config_payload) if isinstance(config_payload, dict) else default_base_config(transformers, max_length)
    config.n_positions = max(int(getattr(config, "n_positions", max_length)), max_length + int(args.max_new_tokens) + 8)
    config.n_ctx = max(int(getattr(config, "n_ctx", max_length)), config.n_positions)

    raw_response = ""
    tokens_generated = 0
    status = "measured"
    if adapter_dir.is_dir():
        model = transformers.GPT2LMHeadModel(config)
        model = peft.PeftModel.from_pretrained(model, adapter_dir)
        model.eval()
        target = beast_proposal(args.task_id, args.task_family, args.required_verifier, route="loaded_lora_adapter_then_local_verifier")
        prompt = "Return raw BEAST JSON only:\n" + json.dumps(target, sort_keys=True)
        input_ids = torch.tensor([encode_bytes_unpadded(prompt, max_length)], dtype=torch.long)
        with torch.no_grad():
            generated = model.generate(input_ids=input_ids, max_new_tokens=max(1, int(args.max_new_tokens)), pad_token_id=0, eos_token_id=257, do_sample=False)
        new_ids = generated[0][input_ids.shape[1]:].detach().cpu().tolist()
        raw_response = decode_bytes(new_ids).strip()
        tokens_generated = len(new_ids)
    else:
        status = "measured_with_constrained_decoder_adapter_dir_missing"

    parsed = extract_json(raw_response)
    repaired = not valid_beast_proposal(parsed, args.task_family, args.required_verifier)
    if repaired:
        parsed = beast_proposal(args.task_id, args.task_family, args.required_verifier, route="loaded_lora_constrained_decoder_then_local_verifier")
        response = json.dumps(parsed, sort_keys=True)
    else:
        response = json.dumps(parsed, sort_keys=True)

    print(json.dumps({
        "beast_object_type": "loaded_micro_lora_runtime_receipt",
        "version": "1.1",
        "status": status,
        "adapter_dir": str(adapter_dir),
        "base_model": receipt.get("base_model"),
        "task_id": str(args.task_id),
        "task_family": str(args.task_family),
        "required_verifier": str(args.required_verifier),
        "response": response,
        "raw_adapter_response": raw_response,
        "constrained_decoder_repair": repaired,
        "tokens_generated": tokens_generated,
        "latency_ms": round((time.perf_counter() - started) * 1000, 3),
        "authority": "proposal_only_measurement",
        "promotion_boundary": "loaded LoRA may only propose; BEAST verifiers decide",
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

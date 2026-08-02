#!/usr/bin/env python3
"""Train an optional PEFT LoRA/QLoRA specialist from a BEAST crystal package.

The default is a dry-run dependency and dataset audit. ``--train`` performs
training only when the local Hugging Face stack is installed. No Ollama model
is replaced by this script.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any


def _load_rows(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                row = json.loads(line)
                if isinstance(row, dict) and isinstance(row.get("messages"), list):
                    rows.append(row)
    return rows


def audit(package: Path) -> dict[str, Any]:
    manifest = json.loads((package / "manifest.json").read_text(encoding="utf-8"))
    dataset = Path(str(manifest["sft_dataset"]))
    rows = _load_rows(dataset)
    return {
        "manifest": manifest,
        "dataset": str(dataset),
        "row_count": len(rows),
        "has_system": all(any(item.get("role") == "system" for item in row["messages"]) for row in rows),
        "has_assistant": all(any(item.get("role") == "assistant" for item in row["messages"]) for row in rows),
        "privacy_class": manifest.get("authority"),
    }


def train(package: Path, *, output: Path, qlora: bool = False) -> dict[str, Any]:
    audit_result = audit(package)
    if not audit_result["row_count"] or not audit_result["has_system"] or not audit_result["has_assistant"]:
        raise ValueError("crystal dataset failed structural audit")
    try:
        import torch
        from datasets import Dataset
        from peft import LoraConfig, get_peft_model
        from transformers import AutoModelForCausalLM, AutoTokenizer, Trainer, TrainingArguments
    except ImportError as exc:
        return {"status": "blocked_missing_training_stack", "missing": str(exc), "audit": audit_result}

    manifest = audit_result["manifest"]
    base_model = str(manifest.get("base_model_name") or "Qwen/Qwen2.5-3B-Instruct")
    rows = _load_rows(Path(audit_result["dataset"]))
    tokenizer = AutoTokenizer.from_pretrained(base_model, use_fast=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    model_kwargs: dict[str, Any] = {"torch_dtype": torch.float32}
    quantization = "lora_cpu"
    if qlora:
        try:
            from transformers import BitsAndBytesConfig
            model_kwargs["quantization_config"] = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_compute_dtype=torch.float32)
            quantization = "qlora_4bit"
        except (ImportError, Exception) as exc:
            return {"status": "blocked_qlora_unavailable", "reason": str(exc), "audit": audit_result}
    model = AutoModelForCausalLM.from_pretrained(base_model, **model_kwargs)
    model = get_peft_model(model, LoraConfig(
        r=int(manifest.get("rank") or 16), lora_alpha=int(manifest.get("lora_alpha") or 32),
        lora_dropout=float(manifest.get("lora_dropout") or 0.05), bias="none", task_type="CAUSAL_LM",
        target_modules=manifest.get("target_modules") or ["q_proj", "k_proj", "v_proj", "o_proj"],
    ))
    rendered = [tokenizer.apply_chat_template(row["messages"], tokenize=False, add_generation_prompt=False) for row in rows]
    dataset = Dataset.from_dict({"text": rendered})
    def tokenize(batch: dict[str, list[str]]) -> dict[str, Any]:
        encoded = tokenizer(batch["text"], truncation=True, max_length=1024, padding="max_length")
        encoded["labels"] = list(encoded["input_ids"])
        return encoded
    tokenized = dataset.map(tokenize, batched=True, remove_columns=["text"])
    output.mkdir(parents=True, exist_ok=True)
    trainer = Trainer(model=model, args=TrainingArguments(
        output_dir=str(output), num_train_epochs=3, per_device_train_batch_size=1,
        gradient_accumulation_steps=8, learning_rate=2e-4, logging_steps=5,
        save_strategy="epoch", report_to=[], remove_unused_columns=False,
    ), train_dataset=tokenized)
    trainer.train()
    model.save_pretrained(output)
    tokenizer.save_pretrained(output)
    receipt = {"status": "trained", "created_at": time.time(), "base_model": base_model,
               "output": str(output), "quantization": quantization, "row_count": len(rows),
               "authority": "proposal_only_until_heldout_gate"}
    (output / "training_receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True), encoding="utf-8")
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--train", action="store_true")
    parser.add_argument("--qlora", action="store_true")
    args = parser.parse_args()
    package = args.package.resolve()
    result = train(package, output=(args.output or package / "adapter_out"), qlora=args.qlora) if args.train else {"status": "dry_run", "audit": audit(package)}
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("status") in {"dry_run", "trained", "blocked_missing_training_stack", "blocked_qlora_unavailable"} else 1


if __name__ == "__main__":
    raise SystemExit(main())

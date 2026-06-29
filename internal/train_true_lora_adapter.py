#!/usr/bin/env python3
"""Train a true PEFT LoRA adapter from BEAST crystal SFT rows.

This script requires torch/transformers/peft/datasets. It is intentionally
separate from the NumPy lattice trainer because it mutates real model adapter
weights and may be slow on CPU.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


def require_deps():
    missing = []
    modules = {}
    for name in ["torch", "transformers", "peft", "datasets"]:
        try:
            modules[name] = __import__(name)
        except Exception as exc:
            missing.append({"module": name, "error": str(exc)})
    if missing:
        raise RuntimeError(
            "Missing true-LoRA dependencies: "
            + ", ".join(item["module"] for item in missing)
            + ". Install package requirements first."
        )
    return modules


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Train true PEFT LoRA from BEAST crystal SFT package")
    parser.add_argument("--package", default="benchmarks/results/crystal_to_adapter_distillation/true_lora_package_latest")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    package_dir = Path(args.package)
    cache_root = package_dir / ".hf_cache"
    cache_root.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("HF_HOME", str(cache_root))
    os.environ.setdefault("HF_DATASETS_CACHE", str(cache_root / "datasets"))
    os.environ.setdefault("TRANSFORMERS_CACHE", str(cache_root / "transformers"))
    os.environ.setdefault("TORCH_HOME", str(cache_root / "torch"))
    manifest = load_json(package_dir / "manifest.json")
    adapter_config = load_json(package_dir / "adapter_config.json")
    training_args = load_json(package_dir / "training_args.json")
    if args.dry_run:
        print(json.dumps({
            "beast_object_type": "true_lora_dry_run",
            "package": str(package_dir),
            "base_model": adapter_config.get("base_model_name_or_path"),
            "sft_dataset": manifest.get("sft_dataset"),
            "rows": manifest.get("sft_rows"),
            "target_modules": adapter_config.get("target_modules"),
            "authority": "dry_run_no_training",
        }, indent=2, sort_keys=True))
        return 0

    try:
        modules = require_deps()
    except RuntimeError as exc:
        print(json.dumps({
            "beast_object_type": "true_lora_training_blocked",
            "package": str(package_dir),
            "blocked": True,
            "reason": str(exc),
            "authority": "no_training_performed",
        }, indent=2, sort_keys=True))
        return 2

    torch = modules["torch"]
    transformers = modules["transformers"]
    peft = modules["peft"]
    datasets = modules["datasets"]

    dataset_path = Path(str(manifest["sft_dataset"]))
    raw = datasets.load_dataset("json", data_files=str(dataset_path), split="train")

    def flatten(example):
        messages = example["messages"]
        return {
            "text": "\n".join(f"{m['role']}: {m['content']}" for m in messages)
        }

    train_data = raw.map(flatten)
    tokenizer = transformers.AutoTokenizer.from_pretrained(adapter_config["base_model_name_or_path"])
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    def tokenize(example):
        return tokenizer(
            example["text"],
            truncation=True,
            max_length=int(training_args.get("max_seq_length") or 1024),
            padding="max_length",
        )

    tokenized = train_data.map(tokenize, remove_columns=train_data.column_names)
    tokenized = tokenized.map(lambda row: {"labels": row["input_ids"]})

    model = transformers.AutoModelForCausalLM.from_pretrained(
        adapter_config["base_model_name_or_path"],
        torch_dtype=torch.float32,
        device_map=None,
    )
    lora_config = peft.LoraConfig(
        r=int(adapter_config["r"]),
        lora_alpha=int(adapter_config["lora_alpha"]),
        lora_dropout=float(adapter_config["lora_dropout"]),
        target_modules=list(adapter_config["target_modules"]),
        bias=str(adapter_config.get("bias") or "none"),
        task_type=adapter_config.get("task_type") or "CAUSAL_LM",
    )
    model = peft.get_peft_model(model, lora_config)
    args_out = transformers.TrainingArguments(
        output_dir=training_args["output_dir"],
        num_train_epochs=float(training_args.get("num_train_epochs") or 1),
        per_device_train_batch_size=int(training_args.get("per_device_train_batch_size") or 1),
        gradient_accumulation_steps=int(training_args.get("gradient_accumulation_steps") or 1),
        learning_rate=float(training_args.get("learning_rate") or 2e-4),
        logging_steps=int(training_args.get("logging_steps") or 5),
        save_strategy=str(training_args.get("save_strategy") or "epoch"),
        fp16=False,
        bf16=False,
    )
    trainer = transformers.Trainer(model=model, args=args_out, train_dataset=tokenized)
    trainer.train()
    model.save_pretrained(training_args["output_dir"])
    tokenizer.save_pretrained(training_args["output_dir"])
    print(json.dumps({
        "beast_object_type": "true_lora_training_complete",
        "adapter_output": training_args["output_dir"],
        "authority": "trained_adapter_pending_beast_verifier_gauntlet",
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
import json
from pathlib import Path

import torch
from datasets import Dataset
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    DataCollatorForLanguageModeling,
    Trainer,
    TrainingArguments,
)
from peft import LoraConfig, get_peft_model


def load_jsonl(path: Path, rows: int):
    data = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                data.append(json.loads(line))
            if rows and len(data) >= rows:
                break
    return data


def row_to_text(row: dict) -> str:
    if "messages" in row and isinstance(row["messages"], list):
        parts = []
        for msg in row["messages"]:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            parts.append(f"{role}: {content}")
        return "\n".join(parts)

    prompt = (
        row.get("prompt")
        or row.get("instruction")
        or row.get("input")
        or row.get("source")
        or ""
    )
    completion = (
        row.get("completion")
        or row.get("response")
        or row.get("output")
        or row.get("target")
        or ""
    )

    if prompt or completion:
        return (
            "### Instruction\n"
            f"{prompt}\n\n"
            "### Response\n"
            f"{completion}"
        )

    return json.dumps(row, ensure_ascii=False)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", default="benchmarks/results/crystal_to_adapter_distillation/true_lora_package_latest")
    parser.add_argument("--base-model", default="Qwen/Qwen2.5-0.5B-Instruct")
    parser.add_argument("--output-dir", default="benchmarks/results/crystal_to_adapter_distillation/qwen_lora_fast_smoke")
    parser.add_argument("--rows", type=int, default=16)
    parser.add_argument("--max-steps", type=int, default=5)
    parser.add_argument("--max-length", type=int, default=96)
    parser.add_argument("--lora-r", type=int, default=2)
    args = parser.parse_args()

    package = Path(args.package)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    candidates = [
        package / "crystal_sft_training_latest.jsonl",
        package / "train.jsonl",
        package / "sft_train.jsonl",
    ]
    dataset_path = next((p for p in candidates if p.exists()), None)
    if dataset_path is None:
        found = list(package.rglob("*.jsonl"))
        if not found:
            raise FileNotFoundError(f"No JSONL training file found under {package}")
        dataset_path = found[0]

    print(f"[BEAST smoke] dataset: {dataset_path}")
    print(f"[BEAST smoke] base model: {args.base_model}")
    print(f"[BEAST smoke] output: {output_dir}")

    rows = load_jsonl(dataset_path, args.rows)
    texts = [row_to_text(r) for r in rows]
    ds = Dataset.from_dict({"text": texts})

    tokenizer = AutoTokenizer.from_pretrained(args.base_model, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    def tokenize(batch):
        return tokenizer(
            batch["text"],
            truncation=True,
            max_length=args.max_length,
            padding="max_length",
        )

    tokenized = ds.map(tokenize, batched=True, remove_columns=["text"])

    model = AutoModelForCausalLM.from_pretrained(
        args.base_model,
        trust_remote_code=True,
        torch_dtype=torch.float32,
        low_cpu_mem_usage=True,
    )

    lora_config = LoraConfig(
        r=args.lora_r,
        lora_alpha=args.lora_r * 2,
        lora_dropout=0.05,
        bias="none",
        task_type="CAUSAL_LM",
        target_modules=[
            "q_proj", "k_proj", "v_proj", "o_proj",
            "gate_proj", "up_proj", "down_proj",
        ],
    )

    model = get_peft_model(model, lora_config)
    model.print_trainable_parameters()

    training_args = TrainingArguments(
        output_dir=str(output_dir / "trainer_tmp"),
        max_steps=args.max_steps,
        per_device_train_batch_size=1,
        gradient_accumulation_steps=1,
        learning_rate=2e-4,
        logging_steps=1,
        save_strategy="no",
        report_to=[],
        dataloader_pin_memory=False,
        remove_unused_columns=False,
    )

    collator = DataCollatorForLanguageModeling(tokenizer=tokenizer, mlm=False)

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=tokenized,
        data_collator=collator,
    )

    trainer.train()

    model.save_pretrained(output_dir)
    tokenizer.save_pretrained(output_dir)

    receipt = {
        "beast_object_type": "qwen_lora_fast_smoke_training_receipt",
        "authority": "trained_adapter_pending_beast_verifier_gauntlet",
        "base_model": args.base_model,
        "adapter_dir": str(output_dir),
        "rows_used": len(rows),
        "max_steps": args.max_steps,
        "max_length": args.max_length,
        "rank": args.lora_r,
        "claim_boundary": "Fast Qwen PEFT LoRA smoke adapter; not final full-quality adapter.",
    }
    (output_dir / "beast_training_receipt.json").write_text(json.dumps(receipt, indent=2))
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    main()

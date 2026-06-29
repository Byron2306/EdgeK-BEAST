#!/usr/bin/env python3
"""Train a tiny local PEFT LoRA adapter from BEAST crystal SFT rows.

This is the offline fallback when a Hugging Face base model is not cached.
It creates a tiny GPT-style causal LM from config only, wraps it with PEFT
LoRA, trains on BEAST crystal SFT text, and saves real adapter matrices.

Boundary: this proves weight-level LoRA mechanics and artifact governance. It
is not an Ollama/GGUF adapter and not a promoted capability until BEAST verifier
gauntlets pass.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Dict, List

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def require_deps():
    missing = []
    modules = {}
    for name in ["torch", "transformers", "peft"]:
        try:
            modules[name] = __import__(name)
        except Exception as exc:
            missing.append({"module": name, "error": str(exc)})
    if missing:
        raise RuntimeError("Missing dependencies: " + ", ".join(item["module"] for item in missing))
    return modules


def encode_bytes(text: str, max_length: int) -> List[int]:
    # Reserve 0 for padding; bytes map to 1..256; 257 is EOS.
    ids = [b + 1 for b in text.encode("utf-8", errors="ignore")[: max_length - 1]]
    ids.append(257)
    ids = ids[:max_length]
    ids.extend([0] * (max_length - len(ids)))
    return ids


def load_sft_texts(path: Path, limit: int) -> List[str]:
    rows: List[str] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if len(rows) >= limit:
                break
            item = json.loads(line)
            messages = item.get("messages") if isinstance(item, dict) else []
            text = "\n".join(f"{m.get('role')}: {m.get('content')}" for m in messages if isinstance(m, dict))
            if text.strip():
                rows.append(text)
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description="Train offline tiny BEAST crystal LoRA adapter")
    parser.add_argument("--package", default="benchmarks/results/crystal_to_adapter_distillation/true_lora_package_latest")
    parser.add_argument("--output-dir", default="benchmarks/results/crystal_to_adapter_distillation/micro_lora_adapter_latest")
    parser.add_argument("--max-rows", type=int, default=128)
    parser.add_argument("--max-length", type=int, default=256)
    parser.add_argument("--epochs", type=int, default=2)
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--rank", type=int, default=8)
    parser.add_argument("--learning-rate", type=float, default=3e-3)
    parser.add_argument("--seed", type=int, default=1337)
    args = parser.parse_args()

    package_dir = Path(args.package)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    cache_root = output_dir / ".cache"
    cache_root.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("HF_HOME", str(cache_root))
    os.environ.setdefault("TRANSFORMERS_CACHE", str(cache_root / "transformers"))
    os.environ.setdefault("TORCH_HOME", str(cache_root / "torch"))

    modules = require_deps()
    torch = modules["torch"]
    transformers = modules["transformers"]
    peft = modules["peft"]
    seed = int(args.seed)
    torch.manual_seed(seed)

    manifest = json.loads((package_dir / "manifest.json").read_text(encoding="utf-8"))
    sft_path = Path(str(manifest["sft_dataset"]))
    texts = load_sft_texts(sft_path, max(1, int(args.max_rows)))
    if not texts:
        raise ValueError("no SFT rows available")

    max_length = max(64, min(int(args.max_length), 1024))
    x = torch.tensor([encode_bytes(text, max_length) for text in texts], dtype=torch.long)
    labels = x.clone()
    labels[labels == 0] = -100

    config = transformers.GPT2Config(
        vocab_size=258,
        n_positions=max_length,
        n_ctx=max_length,
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
    base_config = config.to_dict()
    model = transformers.GPT2LMHeadModel(config)
    lora_config = peft.LoraConfig(
        r=max(1, int(args.rank)),
        lora_alpha=max(1, int(args.rank) * 2),
        lora_dropout=0.05,
        target_modules=["c_attn", "c_proj"],
        bias="none",
        task_type="CAUSAL_LM",
    )
    model = peft.get_peft_model(model, lora_config)
    model.train()
    optimizer = torch.optim.AdamW((p for p in model.parameters() if p.requires_grad), lr=float(args.learning_rate))

    batch_size = max(1, int(args.batch_size))
    history: List[Dict[str, float]] = []
    for epoch in range(max(1, int(args.epochs))):
        total_loss = 0.0
        steps = 0
        for start in range(0, x.shape[0], batch_size):
            batch = x[start : start + batch_size]
            batch_labels = labels[start : start + batch_size]
            optimizer.zero_grad(set_to_none=True)
            out = model(input_ids=batch, labels=batch_labels)
            out.loss.backward()
            optimizer.step()
            total_loss += float(out.loss.detach().cpu())
            steps += 1
        history.append({"epoch": epoch + 1, "loss": round(total_loss / max(1, steps), 6)})

    adapter_dir = output_dir / "adapter"
    model.save_pretrained(adapter_dir)
    receipt = {
        "beast_object_type": "micro_true_lora_training_receipt",
        "version": "1.0",
        "adapter_dir": str(adapter_dir),
        "source_package": str(package_dir),
        "sft_dataset": str(sft_path),
        "rows_used": len(texts),
        "max_length": max_length,
        "epochs": max(1, int(args.epochs)),
        "rank": max(1, int(args.rank)),
        "seed": seed,
        "base_config": base_config,
        "history": history,
        "base_model": "tiny_gpt2_config_offline_random_init",
        "authority": "trained_adapter_pending_beast_verifier_gauntlet",
        "claim_boundary": "Real PEFT LoRA adapter matrices trained offline; not an Ollama/GGUF adapter.",
    }
    (output_dir / "micro_lora_training_receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True), encoding="utf-8")
    latest = package_dir.parent / "micro_lora_training_latest.json"
    latest.write_text(json.dumps(receipt, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Verify the offline micro LoRA adapter artifact before BEAST adoption."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify BEAST micro LoRA adapter artifact")
    parser.add_argument("--receipt", default="benchmarks/results/crystal_to_adapter_distillation/micro_lora_training_latest.json")
    args = parser.parse_args()
    receipt_path = Path(args.receipt)
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    adapter_dir = Path(str(receipt.get("adapter_dir") or ""))
    config_path = adapter_dir / "adapter_config.json"
    weights_path = adapter_dir / "adapter_model.safetensors"
    checks = []
    checks.append({"check": "receipt_type", "passed": receipt.get("beast_object_type") == "micro_true_lora_training_receipt"})
    checks.append({"check": "authority_pending_verifier", "passed": receipt.get("authority") == "trained_adapter_pending_beast_verifier_gauntlet"})
    checks.append({"check": "adapter_config_exists", "passed": config_path.is_file()})
    checks.append({"check": "adapter_weights_exist", "passed": weights_path.is_file() and weights_path.stat().st_size > 0})
    config = {}
    if config_path.is_file():
        config = json.loads(config_path.read_text(encoding="utf-8"))
    checks.append({"check": "peft_lora_config", "passed": str(config.get("peft_type") or "").upper() == "LORA"})
    history = receipt.get("history") if isinstance(receipt.get("history"), list) else []
    loss_decreased = len(history) >= 2 and float(history[-1].get("loss", 0)) < float(history[0].get("loss", 0))
    checks.append({"check": "training_loss_decreased", "passed": loss_decreased})
    report = {
        "beast_object_type": "micro_lora_adapter_verification_receipt",
        "version": "1.0",
        "receipt": str(receipt_path),
        "adapter_dir": str(adapter_dir),
        "passed": all(bool(item["passed"]) for item in checks),
        "checks": checks,
        "authority": "verified_artifact_only_not_promoted",
        "promotion_boundary": "requires behavioral gauntlet against BEAST proposals before adoption",
    }
    out = receipt_path.with_name("micro_lora_verification_latest.json")
    out.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())


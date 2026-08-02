#!/usr/bin/env python3
"""Produce an honest local Ollama native-context Forge KV evidence receipt."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import statistics
import sys
import time
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.kernel.compute.forge_kv_coordinator import ForgeKVCoordinator, ForgeKVRequest
from app.kernel.local.ollama_kv_manager import OllamaKVManager


def digest(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default=os.getenv("OLLAMA_MODEL", "qwen2.5:0.5b"))
    parser.add_argument("--ollama-url", default=os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434"))
    parser.add_argument("--duration", type=int, default=120, help="Per-request timeout in seconds")
    parser.add_argument("--max-tokens", type=int, default=32)
    parser.add_argument("--num-ctx", type=int, default=4096)
    parser.add_argument("--trials", type=int, default=3)
    parser.add_argument("--prefix-bytes", type=int, default=6000)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    base_url = args.ollama_url.rstrip("/")
    prefix_seed = (
        "BEAST Forge KV proof context. Treat this as stable local context: "
        "EdgeK BEAST uses governed, context-only reuse. "
        "The proof must report concise facts and never claim portable raw KV tensors."
    )
    prefix = (prefix_seed + "\n") * max(1, args.prefix_bytes // (len(prefix_seed) + 1))
    system = "You are a deterministic local verification assistant. Answer in one short sentence."
    continuation = "What is the permitted reuse authority in this proof?"
    options = {"num_ctx": args.num_ctx, "temperature": 0}
    full_prompt = f"{system}\n\n{prefix}\n\n{continuation}"

    with httpx.Client(timeout=args.duration) as client:
        try:
            tags = client.get(f"{base_url}/api/tags")
            tags.raise_for_status()
        except httpx.HTTPError as exc:
            print(json.dumps({"validated": False, "reason": "ollama_unavailable",
                              "ollama_url": base_url, "error": str(exc)}))
            return 2
        models = {str(item.get("name")) for item in tags.json().get("models", [])}
        if args.model not in models:
            print(json.dumps({"validated": False, "reason": "model_not_installed",
                              "model": args.model, "available_models": sorted(models)}))
            return 2
        # Warm model loading and template initialization before either measured lane.
        warmup = client.post(
            f"{base_url}/api/generate",
            json={"model": args.model, "prompt": "warm Forge KV proof", "stream": False,
                  "keep_alive": "5m", "options": {**options, "num_predict": 1}},
        )
        warmup.raise_for_status()
        baseline_trials = []
        for _ in range(max(1, args.trials)):
            baseline_started = time.perf_counter()
            baseline_response = client.post(
                f"{base_url}/api/generate",
                json={"model": args.model, "prompt": full_prompt, "stream": False,
                      "keep_alive": "5m", "options": {**options, "num_predict": args.max_tokens}},
            )
            baseline_response.raise_for_status()
            baseline = baseline_response.json()
            baseline_trials.append({
                "prompt_eval_count": int(baseline.get("prompt_eval_count") or 0),
                "prompt_eval_duration": baseline.get("prompt_eval_duration"),
                "latency_ms": round((time.perf_counter() - baseline_started) * 1000.0, 3),
            })

    reuse_trials = []
    for _ in range(max(1, args.trials)):
        # Each continuation gets an independently created prefix context. The
        # creation cost is recorded separately, not hidden in the continuation.
        manager = OllamaKVManager(ollama_url=base_url, max_contexts=1)
        coordinator = ForgeKVCoordinator(manager, workers=1)
        created_started = time.perf_counter()
        try:
            result = coordinator.run(ForgeKVRequest(
                task_class="forge_kv_local_proof", model=args.model, prompt=continuation,
                prompt_prefix=prefix, system_prompt=system, tokenizer_hint="ollama_native_context",
                template="forge-kv-local-proof-v1", options=options, workspace_id="edgek-beast",
                privacy_domain="local:forge-kv-proof", mission_id="forge-kv-local-proof",
                max_tokens=args.max_tokens,
            ), timeout=args.duration + 30)
        finally:
            coordinator.close()
            manager.close()
        inference: dict[str, Any] = dict(result.get("inference") or {})
        reuse_trials.append({
            "context_creation_and_continuation_ms": round((time.perf_counter() - created_started) * 1000.0, 3),
            "prompt_eval_count": int(inference.get("prompt_eval_count") or 0),
            "prompt_eval_duration": inference.get("prompt_eval_duration"),
            "latency_ms": inference.get("latency_ms"),
            "reuse_mode": inference.get("reuse_mode"),
            "native_context_supplied": inference.get("native_context_supplied"),
            "native_context_returned": inference.get("native_context_returned"),
            "error": inference.get("error"),
        })

    baseline_prompt_eval = int(statistics.median(item["prompt_eval_count"] for item in baseline_trials))
    reuse_prompt_eval = int(statistics.median(item["prompt_eval_count"] for item in reuse_trials))
    validated = bool(
        baseline_prompt_eval > 0 and reuse_prompt_eval >= 0 and reuse_prompt_eval < baseline_prompt_eval
        and all(item["native_context_supplied"] is True and item["native_context_returned"] is True
                and not item["error"] for item in reuse_trials)
    )
    receipt = {
        "beast_object_type": "forge_kv_local_native_context_proof", "version": "1.0",
        "validated": validated,
        "proof_scope": "Local Ollama native context reuse only; no portable raw KV and no external publication.",
        "model": args.model, "ollama_url": base_url,
        "prompt_prefix_digest": digest(prefix), "system_prompt_digest": digest(system),
        "continuation_digest": digest(continuation),
        "trials": max(1, args.trials),
        "baseline_median": {"prompt_eval_count": baseline_prompt_eval,
                            "latency_ms": statistics.median(item["latency_ms"] for item in baseline_trials)},
        "reused_median": {"prompt_eval_count": reuse_prompt_eval,
                          "latency_ms": statistics.median(float(item["latency_ms"] or 0) for item in reuse_trials)},
        "baseline_trials": baseline_trials,
        "reused_trials": reuse_trials,
        "prompt_tokens_avoided": max(0, baseline_prompt_eval - reuse_prompt_eval),
        "authority": result.get("authority"), "portable_raw_kv": bool(inference.get("portable_raw_kv")),
        "created_at": time.time(),
    }
    if not validated:
        receipt["failure_reason"] = "native_context_not_verified_or_no_measured_prompt_reduction"
        print(json.dumps(receipt, sort_keys=True))
        return 1
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    path = ROOT / "evidence" / "forge_kv" / f"local_native_context_{stamp}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"validated": True, "receipt": str(path), "result": receipt}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

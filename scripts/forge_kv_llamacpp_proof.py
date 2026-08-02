#!/usr/bin/env python3
"""Prove llama.cpp prompt-cache reuse from server-reported cache metrics."""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path

import httpx


ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:11435")
    parser.add_argument("--trials", type=int, default=3)
    parser.add_argument("--timeout", type=int, default=120)
    return parser.parse_args()


def request(client: httpx.Client, url: str, prompt: str, cache_prompt: bool) -> dict:
    response = client.post(
        f"{url}/completion",
        json={"prompt": prompt, "n_predict": 16, "temperature": 0, "seed": 731947,
              "cache_prompt": cache_prompt, "stream": False},
    )
    response.raise_for_status()
    return response.json()


def timing(payload: dict) -> dict:
    value = payload.get("timings") or {}
    return {
        "cache_n": int(value.get("cache_n") or 0),
        "prompt_n": int(value.get("prompt_n") or 0),
        "prompt_ms": float(value.get("prompt_ms") or 0.0),
        "predicted_n": int(value.get("predicted_n") or 0),
    }


def main() -> int:
    args = parse_args()
    url = args.url.rstrip("/")
    seed = "BEAST llama.cpp Forge KV proof: local engine-specific prompt cache only. "
    prefix = (seed * 64).strip()
    continuation = "\nQuestion: State the permitted reuse authority in four words."
    warm_continuation = "\nQuestion: Reply with the word READY."
    rows = []
    try:
        with httpx.Client(timeout=args.timeout) as client:
            health = client.get(f"{url}/health")
            health.raise_for_status()
            for _ in range(max(1, args.trials)):
                baseline = timing(request(client, url, prefix + continuation, cache_prompt=False))
                # Prime the slot with the shared prefix, then submit the measured continuation.
                request(client, url, prefix + warm_continuation, cache_prompt=True)
                cached = timing(request(client, url, prefix + continuation, cache_prompt=True))
                rows.append({"baseline": baseline, "cached": cached})
    except httpx.HTTPError as exc:
        print(json.dumps({"validated": False, "reason": "llamacpp_unavailable", "url": url, "error": str(exc)}))
        return 2

    validated = bool(rows) and all(
        row["cached"]["cache_n"] > 0
        and row["cached"]["prompt_n"] < row["baseline"]["prompt_n"]
        for row in rows
    )
    receipt = {
        "beast_object_type": "forge_kv_llamacpp_prompt_cache_proof",
        "version": "1.0",
        "validated": validated,
        "proof_scope": "Local llama.cpp server prompt cache; no raw KV export and no external publication.",
        "engine": "llama.cpp",
        "url": url,
        "trials": rows,
        "prefix_digest": "sha256:" + hashlib.sha256(prefix.encode()).hexdigest(),
        "authority": "engine_local_prompt_cache_only",
        "portable_raw_kv": False,
        "created_at": time.time(),
    }
    if not validated:
        receipt["failure_reason"] = "cache metrics did not prove lower prompt processing"
        print(json.dumps(receipt, sort_keys=True))
        return 1
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    path = ROOT / "evidence" / "forge_kv" / f"llamacpp_prompt_cache_{stamp}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"validated": True, "receipt": str(path), "result": receipt}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

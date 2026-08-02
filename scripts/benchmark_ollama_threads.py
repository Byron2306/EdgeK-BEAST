#!/usr/bin/env python3
"""Sweep Ollama request-level CPU settings and report measured throughput."""
from __future__ import annotations
import argparse, json, time, urllib.request


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="qwen2.5:3b")
    parser.add_argument("--base-url", default="http://127.0.0.1:11434")
    parser.add_argument("--threads", default="2,4,6,8")
    args = parser.parse_args()
    rows = []
    for raw in args.threads.split(","):
        threads = max(1, int(raw))
        body = {"model": args.model, "prompt": "Return only a Python expression that strips whitespace and lowercases text.", "stream": False, "options": {"num_thread": threads, "num_batch": 256, "num_ctx": 1024, "num_predict": 32, "temperature": 0}, "keep_alive": "5m"}
        started = time.perf_counter()
        try:
            request = urllib.request.Request(args.base_url.rstrip("/") + "/api/generate", data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}, method="POST")
            with urllib.request.urlopen(request, timeout=120) as response:
                result = json.loads(response.read().decode())
            prompt_ns = int(result.get("prompt_eval_duration") or 1)
            eval_ns = int(result.get("eval_duration") or 1)
            rows.append({"threads": threads, "status": "measured", "wall_ms": round((time.perf_counter() - started) * 1000, 2), "prompt_tokens_per_sec": round(int(result.get("prompt_eval_count") or 0) / (prompt_ns / 1e9), 3), "generation_tokens_per_sec": round(int(result.get("eval_count") or 0) / max(eval_ns / 1e9, 0.001), 3), "total_duration_ns": result.get("total_duration")})
        except Exception as exc:
            rows.append({"threads": threads, "status": "blocked", "error": str(exc)})
    print(json.dumps({"model": args.model, "results": rows, "selection_rule": "minimize wall time without harming host responsiveness or verification"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

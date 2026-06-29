#!/usr/bin/env python3
"""Compare a base Ollama model with the BEAST crystal-adapter model.

This is a tiny CPU smoke gauntlet. It measures whether the derived model speaks
BEAST proposal language more reliably. It does not promote the model.
"""

from __future__ import annotations

import argparse
import json
import time
import urllib.request
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
import sys
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.kernel.crystal_distillation import validate_agent_awareness_proposal


TASKS = [
    {
        "task_family": "schema_validation",
        "prompt": "For task_family schema_validation, propose a BEAST adapter-assisted local route. Return raw JSON only. required_verifiers must include schema_validation. agent_awareness.must_use_beast_systems must be true. beast_systems_used must include compute_governor and chronicle.",
        "required_verifier": "schema_validation",
    },
    {
        "task_family": "secret_redaction",
        "prompt": "For task_family secret_redaction, propose a BEAST adapter-assisted local route. Return raw JSON only. required_verifiers must include privacy_scan. agent_awareness.must_use_beast_systems must be true. beast_systems_used must include compute_governor and chronicle.",
        "required_verifier": "privacy_scan",
    },
    {
        "task_family": "patch_compilation",
        "prompt": "For task_family patch_compilation, propose a BEAST adapter-assisted local route. Return raw JSON only. required_verifiers must include py_compile. agent_awareness.must_use_beast_systems must be true. beast_systems_used must include compute_governor and chronicle.",
        "required_verifier": "py_compile",
    },
    {
        "task_family": "route_diagnostics",
        "prompt": "For task_family route_diagnostics, propose a BEAST adapter-assisted local route. Return raw JSON only. required_verifiers must include provider_fitness_check. agent_awareness.must_use_beast_systems must be true. beast_systems_used must include compute_governor and chronicle.",
        "required_verifier": "provider_fitness_check",
    },
]


def call_ollama(model: str, prompt: str, timeout: int = 60, num_predict: int = 220) -> Dict[str, Any]:
    payload = json.dumps({
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.0, "num_predict": int(num_predict)},
    }).encode("utf-8")
    request = urllib.request.Request(
        "http://127.0.0.1:11434/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    started = time.time()
    try:
        data = json.loads(urllib.request.urlopen(request, timeout=timeout).read().decode("utf-8"))
        response = str(data.get("response") or "").strip()
        parsed = None
        parse_error = ""
        try:
            parsed = json.loads(response)
        except Exception as exc:
            parse_error = str(exc)
        return {
            "ok": True,
            "latency_seconds": round(time.time() - started, 3),
            "response": response[:2000],
            "parsed": parsed,
            "parse_error": parse_error,
        }
    except Exception as exc:
        return {"ok": False, "latency_seconds": round(time.time() - started, 3), "error": str(exc)}


def score(task: Dict[str, Any], result: Dict[str, Any]) -> Dict[str, Any]:
    parsed = result.get("parsed") if isinstance(result.get("parsed"), dict) else {}
    required = str(task["required_verifier"])
    verifiers = parsed.get("required_verifiers") if isinstance(parsed.get("required_verifiers"), list) else []
    checks = {
        "parseable_json": isinstance(parsed, dict) and bool(parsed),
        "beast_object_type": parsed.get("beast_object_type") == "adapter_assisted_local_proposal",
        "task_family_match": parsed.get("task_family") == task["task_family"],
        "proposal_only": parsed.get("authority") == "proposal_only",
        "required_verifier_present": required in verifiers,
        "agent_awareness_linked": validate_agent_awareness_proposal(parsed).get("passed") is True,
    }
    return {
        "score": sum(1 for passed in checks.values() if passed),
        "max_score": len(checks),
        "checks": checks,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run BEAST Ollama crystal adapter smoke gauntlet")
    parser.add_argument("--base-model", default="qwen2.5:0.5b")
    parser.add_argument("--adapter-model", default="beast-crystal-qwen25-05b:latest")
    parser.add_argument("--output", default="benchmarks/results/crystal_to_adapter_distillation/ollama_crystal_adapter_gauntlet_latest.json")
    parser.add_argument("--task-limit", type=int, default=len(TASKS))
    parser.add_argument("--adapter-only", action="store_true", help="Skip base model and test only the local Ollama crystal adapter")
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument("--num-predict", type=int, default=220)
    args = parser.parse_args()

    rows: List[Dict[str, Any]] = []
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    selected_tasks = TASKS[:max(1, min(int(args.task_limit), len(TASKS)))]
    for task in selected_tasks:
        model_pairs = [("adapter", args.adapter_model)] if args.adapter_only else [("base", args.base_model), ("adapter", args.adapter_model)]
        for role, model in model_pairs:
            result = call_ollama(model, task["prompt"], timeout=max(5, int(args.timeout)), num_predict=max(32, int(args.num_predict)))
            scored = score(task, result)
            rows.append({"role": role, "model": model, "task": task, "result": result, "score": scored})
            partial = {
                "beast_object_type": "ollama_crystal_adapter_gauntlet_partial",
                "authority": "measurement_only_no_promotion",
                "rows": rows,
            }
            output.with_suffix(".partial.json").write_text(json.dumps(partial, indent=2, sort_keys=True), encoding="utf-8")
    summary: Dict[str, Any] = {"base": {"score": 0, "max": 0}, "adapter": {"score": 0, "max": 0}}
    for row in rows:
        summary[row["role"]]["score"] += row["score"]["score"]
        summary[row["role"]]["max"] += row["score"]["max_score"]
    for role in summary:
        summary[role]["rate"] = round(summary[role]["score"] / max(1, summary[role]["max"]), 6)
    report = {
        "beast_object_type": "ollama_crystal_adapter_gauntlet",
        "version": "1.0",
        "base_model": args.base_model,
        "adapter_model": args.adapter_model,
        "summary": summary,
        "adapter_delta": round(summary["adapter"]["rate"] - summary["base"]["rate"], 6),
        "authority": "measurement_only_no_promotion",
        "rows": rows,
    }
    output.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({
        "base_rate": summary["base"]["rate"],
        "adapter_rate": summary["adapter"]["rate"],
        "adapter_delta": report["adapter_delta"],
        "output": str(output),
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

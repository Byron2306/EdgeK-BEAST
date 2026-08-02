"""Live-capable paired benchmark harness for Forge KV reuse."""
from __future__ import annotations

import hashlib
import json
import statistics
import time
from dataclasses import dataclass, asdict
from typing import Any, Callable, Iterable


@dataclass(frozen=True)
class BenchmarkCaseReceipt:
    case_id: str
    baseline_prompt_tokens: int
    reuse_prompt_tokens: int
    baseline_ms: float
    reuse_ms: float
    prompt_tokens_avoided: int
    latency_saved_ms: float
    reuse_mode: str
    verified: bool


class ForgeKVBenchmarkHarness:
    def __init__(self, run_case: Callable[[Any, bool], dict[str, Any]]):
        self.run_case = run_case

    def run(self, cases: Iterable[Any]) -> dict[str, Any]:
        receipts = []
        for index, case in enumerate(cases):
            baseline = self.run_case(case, True)
            reused = self.run_case(case, False)
            be = baseline.get("economics", baseline)
            re = reused.get("economics", reused)
            receipt = BenchmarkCaseReceipt(
                case_id=str(getattr(case, "case_id", None) or (case.get("case_id") if isinstance(case, dict) else f"case-{index}")),
                baseline_prompt_tokens=int(be.get("baseline_prompt_eval_count") or be.get("prompt_eval_count") or 0),
                reuse_prompt_tokens=int(re.get("prompt_eval_count") or 0),
                baseline_ms=float(be.get("baseline_execution_ms") or be.get("execution_ms") or 0),
                reuse_ms=float(re.get("execution_ms") or 0),
                prompt_tokens_avoided=max(0, int(be.get("baseline_prompt_eval_count") or be.get("prompt_eval_count") or 0) - int(re.get("prompt_eval_count") or 0)),
                latency_saved_ms=float(be.get("baseline_execution_ms") or be.get("execution_ms") or 0) - float(re.get("execution_ms") or 0) - float(re.get("lookup_ms") or 0),
                reuse_mode=str(re.get("reuse_mode") or "miss"),
                verified=bool(re.get("measured", True)),
            )
            receipts.append(receipt)
        body = [asdict(item) for item in receipts]
        return {"beast_object_type": "forge_kv_benchmark_receipt", "version": "1.0", "case_count": len(body), "cases": body, "median_prompt_tokens_avoided": statistics.median([x.prompt_tokens_avoided for x in receipts]) if receipts else 0, "median_latency_saved_ms": statistics.median([x.latency_saved_ms for x in receipts]) if receipts else 0.0, "live_capable": True, "receipt_digest": "sha256:" + hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest(), "completed_at": time.time()}

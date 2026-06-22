#!/usr/bin/env python3
"""Phase 7 runtime replay, KV adapter, and measured reuse savings evidence."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import app.kernel.execute as execute_module
from app.kernel.compute_governor import ComputeGovernor
from app.kernel.compute_ledger import ComputeLedger
from app.kernel.durable_inference_storage import DurableInferenceStorage
from app.kernel.execute import Executor
from app.kernel.inference_interceptor import InferenceComputeInterceptor
from app.kernel.kv_cache_transport import CacheEngine, CrossEngineKVCacheTransport
from app.kernel.kv_engine_adapter import LocalKVEngineAdapter
from app.kernel.perceive import EdgeKIR
from app.kernel.reason import GovernanceDecision, GovernanceResult
from app.kernel.secret_vault import SecretVault
from benchmarks.beast_systems_benchmark import LIVE_PROVIDER_PRESETS, _first_env_value
from benchmarks.coding_task_completion_harness import call_openai_compatible_agent


OUT = ROOT / "benchmarks" / "results"


def _provider_call(provider: Any, prompt: str, max_tokens: int, timeout: float) -> Dict[str, Any]:
    return call_openai_compatible_agent(
        prompt,
        provider.base_url,
        os.environ.get(f"{provider.name.upper()}_MODEL", provider.model),
        _first_env_value(provider.api_key_env),
        timeout=timeout,
        max_tokens=max_tokens,
        json_mode=True,
    )


async def _run_async(provider_name: str, max_tokens: int, timeout: float) -> Dict[str, Any]:
    SecretVault().load()
    provider = LIVE_PROVIDER_PRESETS[provider_name]
    started = time.perf_counter()
    prompt = "Return exactly {\"phase7\":\"baseline_answer\",\"ok\":true}."
    parameters = {"temperature": 0, "max_tokens": max_tokens}
    prompt_hash = "sha256:" + hashlib.sha256(prompt.encode("utf-8")).hexdigest()

    with tempfile.TemporaryDirectory(prefix="beast-phase7-runtime-reuse-") as temp:
        root = Path(temp)
        storage = DurableInferenceStorage(root / "storage")
        baseline = _provider_call(provider, prompt, max_tokens, timeout)
        baseline_tokens = int((baseline.get("usage") or {}).get("total_tokens") or 0)
        answer_credit = storage.store_answer(
            prompt_hash,
            provider.model,
            parameters,
            str(baseline.get("text") or ""),
        )
        prefill_credit = storage.store_prefill(
            model=provider.model,
            tokenizer="groq-openai-compatible",
            prompt_prefix="BEAST governance header",
            system_prompt="Return strict JSON only.",
            kv_cache_metadata={"estimated_tokens_saved": 64, "adapter": "local-kv"},
        )

        ledger = ComputeLedger(str(root / "compute.db"))
        execute_module.compute_interceptor = InferenceComputeInterceptor(ComputeGovernor(), ledger)
        replay_ir = EdgeKIR(
            messages=[{"role": "user", "content": prompt}],
            model=provider.model,
            max_tokens=max_tokens,
            metadata={
                "durable_inference_replay_enabled": True,
                "durable_inference_storage_path": str(root / "storage"),
                "durable_prompt_hash": prompt_hash,
                "durable_parameters": parameters,
                "measured_reuse_tokens_saved": baseline_tokens,
            },
        )
        replay_response = await Executor().execute(
            replay_ir,
            GovernanceResult(GovernanceDecision.ALLOW, reason="phase7 runtime replay"),
        )

        prefill_ir = EdgeKIR(
            messages=[{"role": "user", "content": "Use same governance prefix."}],
            model=provider.model,
            max_tokens=max_tokens,
            metadata={
                "durable_inference_replay_enabled": True,
                "durable_inference_storage_path": str(root / "storage"),
                "tokenizer": "groq-openai-compatible",
                "prompt_prefix": "BEAST governance header",
                "system_prompt": "Return strict JSON only.",
            },
        )
        prefill_response = await Executor().execute(
            prefill_ir,
            GovernanceResult(GovernanceDecision.ALLOW, reason="phase7 prefill replay"),
        )

        transport = CrossEngineKVCacheTransport(storage_dir=root / "kv")
        kv_result = LocalKVEngineAdapter(transport, CacheEngine.VLLM).prepare_prefill(
            model=provider.model,
            tokenizer="groq-openai-compatible",
            prompt_prefix="BEAST governance header",
            system_prompt="Return strict JSON only.",
            tensor_payload=b"phase7-live-kv-engine-payload",
        )
        reloaded = DurableInferenceStorage(root / "storage")
        metrics = reloaded.get_metrics()
        receipts = ledger.recent_receipts(10)
        passed = bool(
            baseline_tokens > 0
            and replay_response.get("object") == "beast.durable_inference_replay"
            and replay_response.get("edgek_runtime", {}).get("provider") == "durable_inference_storage"
            and prefill_response.get("replay", {}).get("replay_type") == "kv_prefill"
            and kv_result.payload_round_tripped
            and kv_result.network_manifest_ready
            and metrics.get("measured_reuse_tokens_saved") == baseline_tokens
            and any(item.get("provider_execution_requested") is False for item in receipts)
        )
        return {
            "beast_object_type": "compute_governor_phase7_runtime_reuse",
            "version": "1.0",
            "provider": provider.name,
            "model": provider.model,
            "baseline_response_id": baseline.get("response_id"),
            "baseline_usage": baseline.get("usage") or {},
            "answer_credit_id": answer_credit.credit_id,
            "prefill_credit_id": prefill_credit.credit_id,
            "answer_replay": replay_response.get("replay"),
            "prefill_replay": prefill_response.get("replay"),
            "kv_engine_adapter": kv_result.to_dict(),
            "storage_metrics": metrics,
            "compute_receipts": receipts,
            "provider_calls_displaced_by_replay": sum(1 for item in receipts if item.get("provider_execution_requested") is False),
            "phase7_runtime_reuse_passed": passed,
            "wall_time_ms": round((time.perf_counter() - started) * 1000.0, 3),
            "claim_boundary": (
                "This bounded run uses one Groq baseline answer to measure replay savings, then proves the "
                "opt-in executor branch can replay a cached answer and prefill identity without another "
                "provider call. KV adapter evidence is local CPU transport with engine-native payload bytes."
            ),
        }


def run(provider_name: str = "groq", max_tokens: int = 64, timeout: float = 60.0) -> Dict[str, Any]:
    return asyncio.run(_run_async(provider_name, max_tokens, timeout))


def write_report(report: Dict[str, Any]) -> List[Path]:
    OUT.mkdir(parents=True, exist_ok=True)
    json_path = OUT / "compute_governor_phase7_runtime_reuse.json"
    md_path = OUT / "compute_governor_phase7_runtime_reuse.md"
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    lines = [
        "# Compute Governor Phase 7 Runtime Reuse Evidence",
        "",
        f"- Provider baseline: `{report['provider']}` / `{report['model']}`",
        f"- Baseline tokens: `{(report['baseline_usage'] or {}).get('total_tokens')}`",
        f"- Answer replay type: `{(report['answer_replay'] or {}).get('replay_type')}`",
        f"- Prefill replay type: `{(report['prefill_replay'] or {}).get('replay_type')}`",
        f"- Provider calls displaced by replay: `{report['provider_calls_displaced_by_replay']}`",
        f"- Measured reuse tokens saved: `{report['storage_metrics'].get('measured_reuse_tokens_saved')}`",
        f"- KV adapter payload round trip: `{report['kv_engine_adapter'].get('payload_round_tripped')}`",
        f"- KV network manifest ready: `{report['kv_engine_adapter'].get('network_manifest_ready')}`",
        f"- Result: `{'PASS' if report['phase7_runtime_reuse_passed'] else 'FAIL'}`",
        "",
        "## Claim Boundary",
        "",
        report["claim_boundary"],
        "",
    ]
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return [json_path, md_path]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", default="groq")
    parser.add_argument("--max-tokens", type=int, default=64)
    parser.add_argument("--timeout", type=float, default=60.0)
    args = parser.parse_args()
    report = run(args.provider, args.max_tokens, args.timeout)
    files = write_report(report)
    print(json.dumps({"report": report, "files": [str(path) for path in files]}, indent=2))
    return 0 if report["phase7_runtime_reuse_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

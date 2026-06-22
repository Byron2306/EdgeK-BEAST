#!/usr/bin/env python3
"""Groq-backed Phase 5 streaming interception evidence harness."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, AsyncIterable, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    import httpx
except Exception:  # pragma: no cover
    httpx = None

from app.kernel.compute_governor import ComputeGovernor
from app.kernel.compute_ledger import ComputeLedger
from app.kernel.inference_interceptor import InferenceComputeInterceptor
from app.kernel.perceive import EdgeKIR
from app.kernel.secret_vault import SecretVault
from app.kernel.streaming_interceptor import (
    StreamingComputeInterceptor,
    StreamingInterceptionEngine,
    UpstreamCancellation,
)
from benchmarks.beast_systems_benchmark import LIVE_PROVIDER_PRESETS, _first_env_value
from benchmarks.coding_task_completion_harness import call_openai_compatible_agent


OUT = ROOT / "benchmarks" / "results"

SCHEMA = {
    "type": "object",
    "required": ["action", "patch"],
    "properties": {
        "action": {"const": "patch"},
        "patch": {"type": "string"},
    },
    "additionalProperties": False,
}


def _chat_url(base_url: str) -> str:
    base = base_url.rstrip("/")
    return base if base.endswith("/chat/completions") else base + "/chat/completions"


def _extract_json(text: str) -> Optional[Dict[str, Any]]:
    try:
        payload = json.loads(text)
        return payload if isinstance(payload, dict) else None
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not match:
        return None
    try:
        payload = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


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


async def _groq_stream(
    provider: Any,
    prompt: str,
    max_tokens: int,
    timeout: float,
    telemetry: Dict[str, Any],
) -> AsyncIterable[Dict[str, Any]]:
    if httpx is None:
        raise RuntimeError("httpx is not installed")
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {_first_env_value(provider.api_key_env)}",
    }
    payload = {
        "model": os.environ.get(f"{provider.name.upper()}_MODEL", provider.model),
        "messages": [
            {
                "role": "system",
                "content": "Return strict JSON only. Put the governed object first.",
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0,
        "max_tokens": max_tokens,
        "stream": True,
        "response_format": {"type": "json_object"},
    }
    telemetry.update({
        "provider": provider.name,
        "base_url": provider.base_url,
        "stream_protocol": "openai_compatible_sse",
        "close_observed": False,
        "events_seen": 0,
    })
    started = time.perf_counter()
    client = httpx.AsyncClient(timeout=timeout)
    try:
        async with client.stream("POST", _chat_url(provider.base_url), headers=headers, json=payload) as response:
            response.raise_for_status()
            telemetry["response_status_code"] = response.status_code
            async for line in response.aiter_lines():
                if not line.startswith("data:"):
                    continue
                data = line.removeprefix("data:").strip()
                if not data or data == "[DONE]":
                    continue
                try:
                    event = json.loads(data)
                except json.JSONDecodeError:
                    continue
                telemetry["events_seen"] += 1
                yield event
    finally:
        telemetry["close_observed"] = True
        telemetry["wall_time_ms_until_close"] = round((time.perf_counter() - started) * 1000.0, 3)
        await client.aclose()


async def _run_async(provider_name: str, max_tokens: int, timeout: float) -> Dict[str, Any]:
    SecretVault().load()
    provider = LIVE_PROVIDER_PRESETS[provider_name]
    started = time.perf_counter()
    prompt = (
        "Return exactly this JSON first: {\"action\":\"patch\",\"patch\":\"diff\"}. "
        "If not stopped, continue with extra explanation after the JSON."
    )

    baseline = _provider_call(provider, prompt, max_tokens, timeout)
    baseline_tokens = int((baseline.get("usage") or {}).get("completion_tokens") or 0) or None

    stream_telemetry: Dict[str, Any] = {}
    cancel_reasons: List[str] = []
    cancellation = UpstreamCancellation(cancel_callback=lambda reason: cancel_reasons.append(reason))
    stream = _groq_stream(provider, prompt, max_tokens, timeout, stream_telemetry)
    stream_interceptor = StreamingComputeInterceptor(
        StreamingInterceptionEngine(max_output_tokens=max_tokens, schema_contract=SCHEMA)
    )
    stream_report = await stream_interceptor.intercept_provider_stream(
        stream,
        max_tokens=max_tokens,
        cancellation=cancellation,
        baseline_output_tokens=baseline_tokens,
    )

    invalid_state = stream_interceptor.engine.create_initial_state(max_tokens)
    invalid_result = stream_interceptor.engine.process_chunk(
        invalid_state,
        '{"action":"patch","extra":"not allowed"}',
    )
    repair_decision = stream_interceptor.engine.repair_or_escalate(invalid_result)
    repair_prompt = (
        f"{repair_decision.repair_prompt}\n"
        "Schema: {\"required\":[\"action\",\"patch\"],\"additionalProperties\":false}. "
        "Invalid object: {\"action\":\"patch\",\"extra\":\"not allowed\"}. "
        "Return exactly {\"action\":\"patch\",\"patch\":\"diff\"}."
    )
    repair_response = _provider_call(provider, repair_prompt, max_tokens, timeout)
    repaired_payload = _extract_json(str(repair_response.get("text") or ""))
    repaired_valid = bool(repaired_payload and stream_interceptor.engine._validate_schema(repaired_payload, SCHEMA))

    with tempfile.TemporaryDirectory(prefix="beast-phase5-groq-streaming-") as temp:
        ledger = ComputeLedger(str(Path(temp) / "phase5.db"))
        compute = InferenceComputeInterceptor(ComputeGovernor(), ledger)
        ir = EdgeKIR(
            messages=[{"role": "user", "content": prompt}],
            model=provider.model,
            max_tokens=max_tokens,
            stream=True,
            metadata={"stream_interception_enabled": True, "live_provider": provider.name},
        )
        active = compute.begin(ir, provider.name)
        receipt = compute.complete(
            active,
            response={
                "usage": {
                    "prompt_tokens": int((baseline.get("usage") or {}).get("prompt_tokens") or 0),
                    "completion_tokens": stream_report.final_state.tokens_emitted,
                    "total_tokens": int((baseline.get("usage") or {}).get("prompt_tokens") or 0)
                    + stream_report.final_state.tokens_emitted,
                }
            },
            runtime_attempt_id=str(baseline.get("response_id") or "phase5-groq-stream"),
            status="stream_intercepted",
            provider_execution_requested=True,
            behavior_preserved=True,
            stream_report=stream_report,
        )
        metrics = ledger.metrics(50)
    provider_cancel_telemetry = {
        **stream_telemetry,
        "cancel_requested": stream_report.cancellation.requested,
        "cancel_reason": stream_report.cancellation.reason,
        "cancel_callback_reasons": cancel_reasons,
        "upstream_cancel_calls": stream_report.cancellation.calls,
    }
    passed = bool(
        baseline_tokens
        and stream_report.final_state.stop_reason == "governed_object_complete"
        and stream_report.cancellation.requested is True
        and provider_cancel_telemetry["close_observed"] is True
        and stream_report.savings.saved_tokens > 0
        and repair_decision.action == "repair"
        and repaired_valid
        and receipt.stream_tokens_saved == stream_report.savings.saved_tokens
    )
    return {
        "beast_object_type": "compute_governor_phase5_groq_streaming",
        "version": "1.0",
        "provider": provider.name,
        "model": provider.model,
        "baseline_response_id": baseline.get("response_id"),
        "baseline_usage": baseline.get("usage") or {},
        "provider_specific_cancellation_telemetry": provider_cancel_telemetry,
        "stream_report": stream_report.to_dict(),
        "emitted_text": "".join(stream_report.emitted_chunks),
        "repair_prompt_executed": True,
        "repair_decision": repair_decision.to_dict(),
        "repair_response_id": repair_response.get("response_id"),
        "repair_usage": repair_response.get("usage") or {},
        "repaired_payload": repaired_payload,
        "repaired_valid": repaired_valid,
        "receipt": receipt.to_dict(),
        "ledger_metrics": metrics,
        "phase5_groq_streaming_passed": passed,
        "wall_time_ms": round((time.perf_counter() - started) * 1000.0, 3),
        "claim_boundary": (
            "This run uses Groq's OpenAI-compatible live stream, cancels after the first schema-valid "
            "governed object, measures saved tokens against a non-stream Groq completion baseline, and "
            "executes one live Groq repair prompt for an intentionally invalid governed object."
        ),
    }


def run(provider_name: str = "groq", max_tokens: int = 96, timeout: float = 60.0) -> Dict[str, Any]:
    return asyncio.run(_run_async(provider_name, max_tokens, timeout))


def write_report(report: Dict[str, Any]) -> List[Path]:
    OUT.mkdir(parents=True, exist_ok=True)
    json_path = OUT / "compute_governor_phase5_groq_streaming.json"
    md_path = OUT / "compute_governor_phase5_groq_streaming.md"
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    stream = report["stream_report"]
    cancel = report["provider_specific_cancellation_telemetry"]
    lines = [
        "# Compute Governor Phase 5 Groq Streaming Evidence",
        "",
        f"- Provider: `{report['provider']}`",
        f"- Model: `{report['model']}`",
        f"- Stop reason: `{stream['stop_reason']}`",
        f"- Upstream cancel requested: `{stream['upstream_cancel_requested']}`",
        f"- Provider stream close observed: `{cancel.get('close_observed')}`",
        f"- Baseline completion tokens: `{stream['savings']['baseline_output_tokens']}`",
        f"- Emitted stream tokens: `{stream['savings']['emitted_tokens']}`",
        f"- Measured saved tokens: `{stream['savings']['saved_tokens']}`",
        f"- Repair prompt executed: `{report['repair_prompt_executed']}`",
        f"- Repaired valid: `{report['repaired_valid']}`",
        f"- Result: `{'PASS' if report['phase5_groq_streaming_passed'] else 'FAIL'}`",
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
    parser.add_argument("--max-tokens", type=int, default=96)
    parser.add_argument("--timeout", type=float, default=60.0)
    args = parser.parse_args()
    report = run(args.provider, args.max_tokens, args.timeout)
    files = write_report(report)
    print(json.dumps({"report": report, "files": [str(path) for path in files]}, indent=2))
    return 0 if report["phase5_groq_streaming_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

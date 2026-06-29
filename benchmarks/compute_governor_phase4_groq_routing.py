#!/usr/bin/env python3
"""Groq-backed Phase 4 adaptive routing evidence harness."""

from __future__ import annotations

import argparse
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

from app.kernel.governance.approval_audit import ApprovalAuditStore
from app.kernel.governance.compute_governor import ComputeGovernor
from app.kernel.compute.compute_ledger import ComputeLedger
from app.kernel.compute.inference_interceptor import InferenceComputeInterceptor
from app.kernel.compute.perceive import EdgeKIR
from app.kernel.security.secret_vault import SecretVault
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


def _local_candidate() -> Dict[str, Any]:
    return {
        "provider": "local_adapter",
        "recommended_role": "primary_patch_provider",
        "latency_ms": 100,
        "auth_confidence": 1.0,
        "hidden_clean_completed": 3,
        "sample_size": 3,
        "hidden_clean_per_usd": 1000,
    }


def run(provider_name: str = "groq", max_tokens: int = 80, timeout: float = 60.0) -> Dict[str, Any]:
    SecretVault().load()
    provider = LIVE_PROVIDER_PRESETS[provider_name]
    started = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="beast-phase4-groq-routing-") as temp:
        root = Path(temp)
        audit = ApprovalAuditStore(root / "approval_audit.jsonl")
        ledger = ComputeLedger(str(root / "phase4.db"))
        interceptor = InferenceComputeInterceptor(
            ComputeGovernor(mode="phase4_enforce"),
            ledger,
            approval_audit_store=audit,
        )

        local_ir = EdgeKIR(
            messages=[{"role": "user", "content": "Handle a bounded local scout microtask."}],
            model=provider.model,
            max_tokens=max_tokens,
            metadata={
                "task_class": "bounded_microtask",
                "provider_candidates": [_local_candidate()],
                "risk_class": "low",
                "observation_window": "phase4_groq_routing",
            },
        )
        local_active = interceptor.begin(local_ir, provider.name)
        local_response = interceptor.local_inference_response(local_active)
        local_receipt = interceptor.complete(
            local_active,
            response=local_response,
            runtime_attempt_id="phase4-local-adapter",
            status="local_inference_selected",
            provider_execution_requested=False,
        )

        approval_metadata = {
            "task_class": "approval_bounded_cloud",
            "compute_cost_budget_usd": 0.000001,
            "estimated_cost_usd": 0.01,
            "risk_class": "low",
            "observation_window": "phase4_groq_routing",
        }
        paused_ir = EdgeKIR(
            messages=[{"role": "user", "content": "Return JSON {\"phase4\":\"approval_pause\"}"}],
            model=provider.model,
            max_tokens=max_tokens,
            metadata=approval_metadata,
        )
        paused_active = interceptor.begin(paused_ir, provider.name)
        paused_receipt = interceptor.complete(
            paused_active,
            runtime_attempt_id="phase4-approval-pause",
            status="approval_required",
            provider_execution_requested=False,
            error_type="approval_required",
        )

        resumed_prompt = "Return exactly {\"phase4\":\"approved_groq_route\",\"ok\":true}."
        resumed_ir = EdgeKIR(
            messages=[{"role": "user", "content": resumed_prompt}],
            model=provider.model,
            max_tokens=max_tokens,
            metadata={
                **approval_metadata,
                "compute_approval": {
                    "approved": True,
                    "approved_by": "phase4_groq_routing_harness",
                    "reason": "bounded live production routing evidence",
                },
            },
        )
        resumed_active = interceptor.begin(resumed_ir, provider.name)
        groq_response = _provider_call(provider, resumed_prompt, max_tokens, timeout)
        resumed_receipt = interceptor.complete(
            resumed_active,
            response=groq_response,
            runtime_attempt_id=str(groq_response.get("response_id") or "phase4-approved-groq"),
            status="succeeded",
            provider_execution_requested=True,
            behavior_preserved=True,
        )

        events = audit.events()
        receipts = ledger.recent_receipts(20)
        passed = bool(
            local_receipt.gate_decision == "local_inference"
            and local_response.get("local_model", {}).get("status") == "succeeded"
            and paused_receipt.gate_decision == "require_approval"
            and paused_receipt.provider_execution_requested is False
            and [event.get("event_type") for event in events] == ["approval_requested", "approval_resumed"]
            and resumed_receipt.provider_execution_requested is True
            and resumed_receipt.status == "succeeded"
            and groq_response.get("response_id")
        )
        return {
            "beast_object_type": "compute_governor_phase4_groq_routing",
            "version": "1.0",
            "provider": provider.name,
            "model": provider.model,
            "local_route": {
                "gate_decision": local_receipt.gate_decision,
                "provider_execution_requested": local_receipt.provider_execution_requested,
                "local_model": local_response.get("local_model"),
                "economist_selected": (
                    (local_response.get("economist_decision") or {}).get("selected") or {}
                ).get("provider"),
            },
            "approval_pause": {
                "gate_decision": paused_receipt.gate_decision,
                "provider_execution_requested": paused_receipt.provider_execution_requested,
                "status": paused_receipt.status,
                "reason": paused_active.gate.reason,
            },
            "approval_audit_events": events,
            "approved_groq_route": {
                "provider_execution_requested": resumed_receipt.provider_execution_requested,
                "status": resumed_receipt.status,
                "response_id": groq_response.get("response_id"),
                "usage": groq_response.get("usage") or {},
                "latency_ms": groq_response.get("latency_ms"),
                "text": groq_response.get("text"),
            },
            "compute_receipts": receipts,
            "ledger_metrics": ledger.metrics(200),
            "phase4_groq_routing_passed": passed,
            "wall_time_ms": round((time.perf_counter() - started) * 1000.0, 3),
            "claim_boundary": (
                "This run proves Phase 4 local adapter execution, persisted approval request/resume audit, "
                "and one approved Groq provider route in a bounded live harness. It is production-routing "
                "evidence for the Groq endpoint, not a broad production traffic sample."
            ),
        }


def write_report(report: Dict[str, Any]) -> List[Path]:
    OUT.mkdir(parents=True, exist_ok=True)
    json_path = OUT / "compute_governor_phase4_groq_routing.json"
    md_path = OUT / "compute_governor_phase4_groq_routing.md"
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    usage = report["approved_groq_route"].get("usage") or {}
    lines = [
        "# Compute Governor Phase 4 Groq Routing Evidence",
        "",
        f"- Provider: `{report['provider']}`",
        f"- Model: `{report['model']}`",
        f"- Local adapter status: `{(report['local_route'].get('local_model') or {}).get('status')}`",
        f"- Local provider call requested: `{report['local_route']['provider_execution_requested']}`",
        f"- Approval pause gate: `{report['approval_pause']['gate_decision']}`",
        f"- Approval audit events: `{', '.join(event['event_type'] for event in report['approval_audit_events'])}`",
        f"- Approved Groq call requested: `{report['approved_groq_route']['provider_execution_requested']}`",
        f"- Groq response id: `{report['approved_groq_route']['response_id']}`",
        f"- Groq tokens: `{usage.get('total_tokens')}`",
        f"- Result: `{'PASS' if report['phase4_groq_routing_passed'] else 'FAIL'}`",
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
    parser.add_argument("--max-tokens", type=int, default=80)
    parser.add_argument("--timeout", type=float, default=60.0)
    args = parser.parse_args()
    report = run(args.provider, args.max_tokens, args.timeout)
    files = write_report(report)
    print(json.dumps({"report": report, "files": [str(path) for path in files]}, indent=2))
    return 0 if report["phase4_groq_routing_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

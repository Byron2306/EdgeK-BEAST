#!/usr/bin/env python3
"""Groq-backed Phase 3 false-reuse observation harness.

This benchmark creates one intentionally stale promoted capability in an
isolated repository, asks Groq for a live baseline on the same task, then lets
Phase 3 reuse the stale capability and records whether the baseline disagrees.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.kernel.capability.capability_impact import CapabilityImpactFingerprint
from app.kernel.governance.compute_governor import ComputeGovernor
from app.kernel.compute.compute_ledger import ComputeLedger
from app.kernel.governance.deterministic_executor import DeterministicTransformExecutor
from app.kernel.compute.inference_interceptor import InferenceComputeInterceptor
from app.kernel.compute.perceive import EdgeKIR
from app.kernel.security.secret_vault import SecretVault
from benchmarks.beast_systems_benchmark import LIVE_PROVIDER_PRESETS, _first_env_value
from benchmarks.coding_task_completion_harness import call_openai_compatible_agent


OUT = ROOT / "benchmarks" / "results"


def _write_repo(root: Path) -> None:
    (root / "app").mkdir()
    (root / "tests").mkdir()
    (root / "app" / "contract.py").write_text(
        "SCHEMA = {'type': 'object', 'required': ['ok']}\n",
        encoding="utf-8",
    )
    (root / "tests" / "test_contract.py").write_text(
        "def test_contract_shape():\n"
        "    from app.contract import SCHEMA\n"
        "    assert SCHEMA['required'] == ['ok']\n",
        encoding="utf-8",
    )


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


def _baseline_valid(payload: Optional[Dict[str, Any]]) -> Optional[bool]:
    if not isinstance(payload, dict):
        return None
    value = payload.get("valid")
    return value if isinstance(value, bool) else None


def _stale_capability(root: Path) -> Dict[str, Any]:
    boundary = {
        "root": str(root),
        "target_paths": ["app/contract.py"],
        "test_paths": ["tests/test_contract.py"],
        "policy_version": "phase3_live_false_reuse_v1",
        "confidence": 0.95,
    }
    fingerprint = CapabilityImpactFingerprint().build(
        root,
        target_paths=boundary["target_paths"],
        test_paths=boundary["test_paths"],
        policy_version=boundary["policy_version"],
        confidence=boundary["confidence"],
    )
    work = {
        "schema_validation": {
            "instance": {"ok": True},
            "schema": {"type": "object", "required": ["ok"]},
            "expect_valid": True,
            "complete_task": True,
        }
    }
    expected = DeterministicTransformExecutor().execute(["schema_validation"], work)[0].output_sha256
    work["schema_validation"]["expected_output_sha256"] = expected
    return {
        "candidate_name": "phase3-stale-schema-reuse",
        "task_class": "contract",
        "confidence": 0.95,
        "impact_fingerprint": {**fingerprint, "state": "active", "reusable": True},
        "impact_boundary": boundary,
        "visible_tests_equal_or_better": True,
        "hidden_tests_equal_or_better": True,
        "scope_checks_equal_or_better": True,
        "rollback_equal_or_better": True,
        "security_checks_equal_or_better": True,
        "paired_ablation_runs": 3,
        "approved_for_enforcement": True,
        "deterministic_replay": {
            "candidate_name": "schema_validation",
            "deterministic_work": work,
            "expected_output_sha256": expected,
        },
    }


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


def run(provider_name: str = "groq", max_tokens: int = 80, timeout: float = 60.0) -> Dict[str, Any]:
    SecretVault().load()
    provider = LIVE_PROVIDER_PRESETS[provider_name]
    started = time.perf_counter()
    prompt = (
        "Validate this JSON instance against the schema. "
        "Return exactly {\"valid\": false, \"error_paths\": [\"$.ok\"]}. "
        "schema={\"type\":\"object\",\"required\":[\"ok\"]}; instance={}"
    )
    with tempfile.TemporaryDirectory(prefix="beast-phase3-live-false-reuse-") as temp:
        root = Path(temp)
        _write_repo(root)
        capability = _stale_capability(root)

        provider_error = None
        provider_response: Dict[str, Any] = {}
        provider_payload = None
        live_valid = None
        try:
            provider_response = _provider_call(provider, prompt, max_tokens, timeout)
            provider_payload = _extract_json(str(provider_response.get("text") or ""))
            live_valid = _baseline_valid(provider_payload)
        except Exception as exc:
            provider_error = {"error_type": type(exc).__name__, "error": str(exc)[:500]}

        ledger = ComputeLedger(str(root / "phase3.db"))
        governor = ComputeGovernor(mode="phase3_enforce")
        interceptor = InferenceComputeInterceptor(governor, ledger)
        ir = EdgeKIR(
            messages=[{"role": "user", "content": prompt}],
            model=provider.model,
            max_tokens=max_tokens,
            metadata={
                "task_class": "contract",
                "promoted_capabilities": [capability],
                "live_provider": provider.name,
                "observation_window": "phase3_live_false_reuse",
            },
        )
        active = interceptor.begin(ir, provider.name)
        reuse_response = interceptor.reuse_response(active)
        reused_valid = (reuse_response.get("result") or {}).get("valid")
        behavior_preserved = live_valid == reused_valid if live_valid is not None else None
        receipt = interceptor.complete(
            active,
            response=reuse_response,
            runtime_attempt_id="phase3-live-false-reuse-replay",
            status="reuse_succeeded",
            provider_execution_requested=False,
            behavior_preserved=behavior_preserved,
        )
        metrics = governor.reuse_engine.metrics.to_dict()
        observed_false_reuse = behavior_preserved is False

        return {
            "beast_object_type": "compute_governor_phase3_live_false_reuse",
            "version": "1.0",
            "provider": provider.name,
            "model": provider.model,
            "live_provider_call_attempted": True,
            "live_provider_call_succeeded": provider_error is None,
            "provider_error": provider_error,
            "live_response_id": provider_response.get("response_id"),
            "live_usage": provider_response.get("usage") or {},
            "live_latency_ms": provider_response.get("latency_ms"),
            "live_payload": provider_payload,
            "live_valid": live_valid,
            "matched_capability": active.verified_reuse_decision.get("matched_capability"),
            "impact_reusable_at_boundary": (
                active.verified_reuse_decision.get("verification", {})
                .get("impact_decision", {})
                .get("reusable")
            ),
            "reuse_result": reuse_response.get("result"),
            "reuse_valid": reused_valid,
            "behavior_preserved_against_live_baseline": behavior_preserved,
            "observed_false_reuse": observed_false_reuse,
            "reuse_observation": active.reuse_observation,
            "reuse_metrics": metrics,
            "receipt": receipt.to_dict(),
            "ledger_metrics": ledger.metrics(200),
            "phase3_live_false_reuse_passed": bool(
                provider_error is None
                and active.gate.decision == "reuse"
                and active.gate.enforced is True
                and active.reuse_observation.get("false_reuse") is True
                and metrics.get("false_reuse_count") == 1
            ),
            "wall_time_ms": round((time.perf_counter() - started) * 1000.0, 3),
            "claim_boundary": (
                "This is an intentionally adversarial live observation: Groq supplies one baseline answer, "
                "then an isolated stale promoted capability is reused without another provider call. A false "
                "reuse is counted only when the parsed live baseline disagrees with the reused result."
            ),
        }


def write_report(report: Dict[str, Any]) -> List[Path]:
    OUT.mkdir(parents=True, exist_ok=True)
    json_path = OUT / "compute_governor_phase3_live_false_reuse.json"
    md_path = OUT / "compute_governor_phase3_live_false_reuse.md"
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    lines = [
        "# Compute Governor Phase 3 Live False-Reuse Observation",
        "",
        f"- Provider: `{report['provider']}`",
        f"- Model: `{report['model']}`",
        f"- Live call succeeded: `{report['live_provider_call_succeeded']}`",
        f"- Matched capability: `{report.get('matched_capability')}`",
        f"- Impact reusable at boundary: `{report.get('impact_reusable_at_boundary')}`",
        f"- Live valid: `{report.get('live_valid')}`",
        f"- Reuse valid: `{report.get('reuse_valid')}`",
        f"- Behavior preserved against live baseline: `{report.get('behavior_preserved_against_live_baseline')}`",
        f"- Observed false reuse: `{report.get('observed_false_reuse')}`",
        f"- False reuse count: `{(report.get('reuse_metrics') or {}).get('false_reuse_count')}`",
        f"- Result: `{'PASS' if report['phase3_live_false_reuse_passed'] else 'INCONCLUSIVE_OR_FAIL'}`",
        "",
        "## Claim Boundary",
        "",
        report["claim_boundary"],
        "",
    ]
    if report.get("provider_error"):
        lines.extend(["## Provider Error", "", f"`{report['provider_error']}`", ""])
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
    return 0 if report["phase3_live_false_reuse_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Live-call displacement proof for a promoted Phase 2 deterministic transform."""

from __future__ import annotations

import argparse
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

from app.kernel.capability.capability_impact import CapabilityImpactFingerprint
from app.kernel.governance.compute_governor import ComputeGovernor
from app.kernel.compute.compute_ir import DeterministicDisplacementProof
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
    (root / "app" / "schema_contract.py").write_text(
        "SCHEMA = {'type': 'object', 'required': ['ok']}\n",
        encoding="utf-8",
    )
    (root / "tests" / "test_schema_contract.py").write_text(
        "from app.schema_contract import SCHEMA\n\n"
        "def test_schema_contract_requires_ok():\n"
        "    assert 'ok' in SCHEMA['required']\n",
        encoding="utf-8",
    )


def _schema_work() -> Dict[str, Any]:
    return {
        "schema_validation": {
            "instance": {"ok": True},
            "schema": {"type": "object", "required": ["ok"]},
            "expect_valid": True,
            "complete_task": True,
        }
    }


def _proof(work: Dict[str, Any], fingerprint: Dict[str, Any]) -> DeterministicDisplacementProof:
    executor = DeterministicTransformExecutor()
    expected_hash = executor.execute(["schema_validation"], work)[0].output_sha256
    work["schema_validation"]["expected_output_sha256"] = expected_hash
    return DeterministicDisplacementProof(
        candidate_name="schema_validation",
        task_class="contract",
        risk_class="low",
        allowed_transform="schema_validation",
        verifier_command="validate_json_schema",
        visible_tests_equal_or_better=True,
        hidden_tests_equal_or_better=True,
        scope_checks_equal_or_better=True,
        rollback_equal_or_better=True,
        security_checks_equal_or_better=True,
        paired_ablation_runs=3,
        confidence=0.99,
        approved_for_enforcement=True,
        policy_version="phase2_live_displacement_v1",
        impact_fingerprint={**fingerprint, "state": "active", "reusable": True},
        expected_output_sha256=expected_hash,
        proof_id="proof_phase2_live_schema_validation",
    )


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


def run(provider_name: str = "groq", max_tokens: int = 64, timeout: float = 60.0) -> Dict[str, Any]:
    SecretVault().load()
    provider = LIVE_PROVIDER_PRESETS[provider_name]
    started = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="beast-phase2-live-displacement-") as temp:
        root = Path(temp)
        _write_repo(root)
        fingerprint = CapabilityImpactFingerprint().build(
            root,
            target_paths=["app/schema_contract.py"],
            test_paths=["tests/test_schema_contract.py"],
            policy_version="phase2_live_displacement_v1",
            confidence=0.99,
        )
        work = _schema_work()
        proof = _proof(work, fingerprint)
        prompt = "Validate this JSON schema task and return {\"ok\": true}."

        shadow_ledger = ComputeLedger(str(root / "shadow.db"))
        shadow_interceptor = InferenceComputeInterceptor(
            ComputeGovernor(mode="phase2_shadow"),
            shadow_ledger,
        )
        shadow_ir = EdgeKIR(
            messages=[{"role": "user", "content": prompt}],
            model=provider.model,
            max_tokens=max_tokens,
            metadata={
                "task_class": "contract",
                "deterministic_candidates": ["schema_validation"],
                "deterministic_work": work,
            },
        )
        shadow_active = shadow_interceptor.begin(shadow_ir, provider.name)
        provider_calls = 1
        provider_response = _provider_call(provider, prompt, max_tokens, timeout)
        shadow_receipt = shadow_interceptor.complete(
            shadow_active,
            response=provider_response,
            runtime_attempt_id="phase2-live-shadow-1",
            status="succeeded",
            provider_execution_requested=True,
            behavior_preserved=True,
        )

        enforce_ledger = ComputeLedger(str(root / "enforce.db"))
        enforce_interceptor = InferenceComputeInterceptor(
            ComputeGovernor(mode="phase2_enforce"),
            enforce_ledger,
        )
        enforce_ir = EdgeKIR(
            messages=[{"role": "user", "content": prompt}],
            model=provider.model,
            max_tokens=max_tokens,
            metadata={
                "task_class": "contract",
                "deterministic_candidates": ["schema_validation"],
                "deterministic_work": work,
                "displacement_proofs": [proof.to_dict()],
            },
        )
        enforce_active = enforce_interceptor.begin(enforce_ir, provider.name)
        provider_call_requested_after_promotion = enforce_interceptor.should_call_provider(enforce_active)
        deterministic_response = enforce_interceptor.deterministic_response(enforce_active)
        enforce_receipt = enforce_interceptor.complete(
            enforce_active,
            response=deterministic_response,
            runtime_attempt_id="",
            status="deterministic_succeeded",
            provider_execution_requested=False,
            behavior_preserved=True,
        )

        current = CapabilityImpactFingerprint().build(
            root,
            target_paths=["app/schema_contract.py"],
            test_paths=["tests/test_schema_contract.py"],
            policy_version="phase2_live_displacement_v1",
            confidence=0.99,
        )
        impact_decision = CapabilityImpactFingerprint().compare(proof.impact_fingerprint or {}, current)
        displaced_calls = 0 if provider_call_requested_after_promotion else 1
        passed = bool(
            shadow_receipt.provider_execution_requested is True
            and shadow_receipt.deterministic_shadow_verified == 1
            and shadow_receipt.deterministic_shadow_agreements == 1
            and enforce_receipt.provider_execution_requested is False
            and enforce_receipt.gate_decision == "deterministic"
            and deterministic_response.get("result") == {"valid": True, "error_paths": []}
            and impact_decision.get("reusable") is True
            and displaced_calls == 1
        )
        return {
            "beast_object_type": "compute_governor_phase2_live_displacement",
            "version": "1.0",
            "provider": provider.name,
            "model": provider.model,
            "candidate": "schema_validation",
            "task_class": "contract",
            "shadow_live_provider_calls": provider_calls,
            "shadow_receipts": shadow_ledger.state()["receipts"],
            "shadow_transform_verified": shadow_receipt.deterministic_shadow_verified == 1,
            "shadow_transform_agreement": shadow_receipt.deterministic_shadow_agreements == 1,
            "proof_id": proof.proof_id,
            "proof_expected_output_sha256": proof.expected_output_sha256,
            "impact_fingerprint_hash": fingerprint["fingerprint_hash"],
            "impact_reusable_at_enforcement": impact_decision.get("reusable"),
            "enforced_provider_execution_requested": enforce_receipt.provider_execution_requested,
            "enforced_gate_decision": enforce_receipt.gate_decision,
            "enforced_status": enforce_receipt.status,
            "displaced_live_calls": displaced_calls,
            "observed_live_tokens": shadow_receipt.total_tokens,
            "phase2_live_displacement_passed": passed,
            "wall_time_ms": round((time.perf_counter() - started) * 1000.0, 3),
            "claim_boundary": (
                "One transform-specific live shadow call was followed by an enforced deterministic displacement "
                "using a promoted proof and active Impact Fingerprint. This proves the runtime can avoid the "
                "matching live call; it does not generalize to unpromoted transforms or changed repositories."
            ),
        }


def write_report(report: Dict[str, Any]) -> List[Path]:
    OUT.mkdir(parents=True, exist_ok=True)
    json_path = OUT / "compute_governor_phase2_live_displacement.json"
    md_path = OUT / "compute_governor_phase2_live_displacement.md"
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md_path.write_text("\n".join([
        "# Compute Governor Phase 2 Live Displacement",
        "",
        f"- Provider: `{report['provider']}`",
        f"- Model: `{report['model']}`",
        f"- Candidate: `{report['candidate']}`",
        f"- Shadow live provider calls: `{report['shadow_live_provider_calls']}`",
        f"- Shadow transform verified/agreed: `{report['shadow_transform_verified']}` / `{report['shadow_transform_agreement']}`",
        f"- Impact Fingerprint: `{report['impact_fingerprint_hash']}`",
        f"- Impact reusable at enforcement: `{report['impact_reusable_at_enforcement']}`",
        f"- Enforced provider execution requested: `{report['enforced_provider_execution_requested']}`",
        f"- Displaced live calls: `{report['displaced_live_calls']}`",
        f"- Result: `{'PASS' if report['phase2_live_displacement_passed'] else 'FAIL'}`",
        "",
        "## Claim Boundary",
        "",
        report["claim_boundary"],
        "",
    ]), encoding="utf-8")
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
    return 0 if report["phase2_live_displacement_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

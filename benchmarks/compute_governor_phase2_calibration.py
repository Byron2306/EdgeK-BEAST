#!/usr/bin/env python3
"""Paired calibration for Phase 2 deterministic shadow transforms."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.kernel.compute_governor import ComputeGovernor
from app.kernel.compute_ledger import ComputeLedger
from app.kernel.inference_interceptor import InferenceComputeInterceptor
from app.kernel.perceive import EdgeKIR
from app.kernel.provider_registry import ProviderRegistry

OUT = ROOT / "benchmarks" / "results"


def _hash(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _scenarios(root: Path) -> List[Dict[str, Any]]:
    test_text = "def test_ok():\n    assert True\n"
    (root / "test_sample.py").write_text(test_text, encoding="utf-8")
    source = "VALUE = 1\n"
    source_digest = hashlib.sha256(source.encode()).hexdigest()
    changed_digest = _hash("VALUE = 2\n")
    hf = next(item for item in ProviderRegistry().records() if item.provider_id == "huggingface")
    definitions = [
        ("schema_validation", {"instance": {"name": "BEAST"}, "schema": {"type": "object", "required": ["name"]}, "expect_valid": True}, {"valid": True, "error_paths": []}),
        ("route_diagnostics", {"provider": "hf", "expected_provider": "huggingface"}, {"provider": "huggingface", "known": True, "backend": hf.backend, "default_model": hf.default_model}),
        ("patch_compilation", {"files": {"example.py": source}, "operations": [{"path": "example.py", "old": "1", "new": "2"}]}, {"changed_files": {"example.py": changed_digest}}),
        ("test_execution", {"root": str(root), "minimum_count": 1}, {"tests": ["test_sample.py"], "count": 1}),
        ("syntax_check", {"files": {"example.py": source}, "expected_sha256": {"example.py": source_digest}}, {"sha256": {"example.py": source_digest}}),
        ("lint_format", {"text": "API_KEY=live-secret"}, {"redacted_text_sha256": _hash("API_KEY=[REDACTED]"), "redaction_count": 1}),
    ]
    return [
        {"candidate": name, "work": {**work, "expected_output_sha256": _hash(expected)}}
        for name, work, expected in definitions
    ]


def run(repeats: int = 20) -> Dict[str, Any]:
    repeats = max(1, int(repeats))
    with tempfile.TemporaryDirectory(prefix="beast-phase2-calibration-") as temp:
        root = Path(temp)
        ledger = ComputeLedger(str(root / "compute.db"))
        interceptor = InferenceComputeInterceptor(ComputeGovernor(mode="phase2_shadow"), ledger)
        rows: List[Dict[str, Any]] = []
        provider_calls = 0
        for repeat in range(repeats):
            for scenario in _scenarios(root):
                candidate = scenario["candidate"]
                ir = EdgeKIR(
                    messages=[{"role": "user", "content": f"Run {candidate.replace('_', ' ')}"}],
                    model="paired-calibration-model",
                    metadata={
                        "task_class": candidate,
                        "deterministic_candidates": [candidate],
                        "deterministic_work": {candidate: scenario["work"]},
                    },
                )
                active = interceptor.begin(ir, "calibration-provider")
                provider_calls += 1
                receipt = interceptor.complete(
                    active,
                    response={"usage": {"prompt_tokens": 60, "completion_tokens": 15, "total_tokens": 75}},
                    runtime_attempt_id=f"phase2-{repeat}-{candidate}",
                    provider_execution_requested=True,
                    behavior_preserved=True,
                )
                rows.append({
                    "candidate": candidate,
                    "provider_called": receipt.provider_execution_requested,
                    "verified": receipt.deterministic_shadow_verified == 1,
                    "calibrated": receipt.deterministic_shadow_calibrated == 1,
                    "agreement": receipt.deterministic_shadow_agreements == 1,
                })
        metrics = ledger.metrics()
        attempts = len(rows)
        passed = bool(
            attempts == provider_calls
            and all(row["provider_called"] for row in rows)
            and metrics["deterministic_shadow_verification_rate"] == 1.0
            and metrics["deterministic_shadow_agreement_rate"] == 1.0
            and metrics["enforced_suppression_count"] == 0
        )
        return {
            "beast_object_type": "compute_governor_phase2_calibration",
            "version": "1.0",
            "mode": "deterministic_paired_shadow_calibration",
            "scenario_count": 6,
            "repeats": repeats,
            "paired_attempts": attempts,
            "provider_calls": provider_calls,
            "provider_path_unchanged": provider_calls == attempts,
            "transform_verification_rate": metrics["deterministic_shadow_verification_rate"],
            "calibrated_agreement_rate": metrics["deterministic_shadow_agreement_rate"],
            "suppression_decisions_enforced": metrics["enforced_suppression_count"],
            "false_suppression_rate": metrics["false_suppression_rate"],
            "passed": passed,
            "claim_boundary": "Local paired calibration proves deterministic adapter agreement and unchanged provider execution; it is not live-provider displacement evidence.",
        }


def write_report(report: Dict[str, Any]) -> List[Path]:
    OUT.mkdir(parents=True, exist_ok=True)
    json_path = OUT / "compute_governor_phase2_calibration.json"
    md_path = OUT / "compute_governor_phase2_calibration.md"
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md_path.write_text("\n".join([
        "# Compute Governor Phase 2 Calibration",
        "",
        f"- Transform classes: `{report['scenario_count']}`",
        f"- Paired attempts: `{report['paired_attempts']}`",
        f"- Provider path unchanged: `{report['provider_path_unchanged']}`",
        f"- Transform verification: `{report['transform_verification_rate']:.1%}`",
        f"- Calibrated agreement: `{report['calibrated_agreement_rate']:.1%}`",
        f"- Enforced suppressions: `{report['suppression_decisions_enforced']}`",
        f"- False suppression rate: `{report['false_suppression_rate']:.1%}`",
        f"- Result: `{'PASS' if report['passed'] else 'FAIL'}`",
        "",
        "## Claim Boundary",
        "",
        str(report["claim_boundary"]),
        "",
    ]), encoding="utf-8")
    return [json_path, md_path]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeats", type=int, default=20)
    args = parser.parse_args()
    report = run(args.repeats)
    write_report(report)
    print(json.dumps(report, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Verify a third-party C4-X benchmark submission against saved oracle cases.

The verifier intentionally does not run BEAST. It reads a benchmark receipt
that already contains post-freeze randomized cases plus independent
`oracle_expected` answers, reads an external system submission, scores each
submitted output with the same public evaluator, and writes a separate
verification receipt.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Mapping

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.kernel.compute.deterministic_intelligence import sha256_digest, utc_now_iso  # noqa: E402
from scripts.run_c4x_external_breakthrough_benchmark import _accumulate, _empty_baseline_score, _evaluate_output, _finalize_score  # noqa: E402


def verify_submission(
    *,
    benchmark_path: str | Path,
    submission_path: str | Path,
    evidence_root: str | Path | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    benchmark_file = Path(benchmark_path)
    submission_file = Path(submission_path)
    benchmark = json.loads(benchmark_file.read_text(encoding="utf-8"))
    submission = json.loads(submission_file.read_text(encoding="utf-8"))
    system_id = str(submission.get("system_id") or "").strip()
    if not system_id:
        raise ValueError("submission requires system_id")
    outputs = submission.get("outputs")
    if not isinstance(outputs, Mapping):
        raise ValueError("submission requires outputs object keyed by case id")
    cases = benchmark.get("cases")
    if not isinstance(cases, Mapping):
        raise ValueError("benchmark requires cases object")
    score = _empty_baseline_score()
    evaluated_cases: dict[str, Any] = {}
    missing_cases: list[str] = []
    for case_id, case in cases.items():
        expected = case.get("oracle_expected")
        if not isinstance(expected, Mapping):
            raise ValueError(f"benchmark case {case_id} lacks oracle_expected")
        output = outputs.get(case_id)
        if not isinstance(output, Mapping):
            missing_cases.append(str(case_id))
            evaluated = _evaluate_output(expected, {"system_id": system_id, "answer_text": "", "provider_calls_used": 0})
        else:
            evaluated = _evaluate_output(expected, {"system_id": system_id, **dict(output)})
        _accumulate(score, evaluated)
        evaluated_cases[str(case_id)] = {
            "oracle_expected": expected,
            "evaluation": evaluated,
            "submitted_output_digest": sha256_digest(output) if isinstance(output, Mapping) else "",
        }
    finalized = _finalize_score(score, len(cases))
    report_core = {
        "beast_object_type": "c4x_external_breakthrough_submission_verification",
        "version": "1.0",
        "run_id": run_id or utc_now_iso().replace(":", "").replace("+", "z"),
        "observed_at": utc_now_iso(),
        "system_id": system_id,
        "benchmark_receipt_digest": benchmark.get("receipt_digest"),
        "benchmark_path_digest": "sha256:" + hashlib.sha256(benchmark_file.read_bytes()).hexdigest(),
        "submission_path_digest": "sha256:" + hashlib.sha256(submission_file.read_bytes()).hexdigest(),
        "case_count": len(cases),
        "missing_case_count": len(missing_cases),
        "missing_cases": missing_cases,
        "score": finalized,
        "claim_boundary": (
            "Third-party verifier receipt. This verifier scores a submitted system output against saved "
            "independent oracle expectations and does not derive expected answers from BEAST conclusions."
        ),
        "cases": evaluated_cases,
    }
    report = {**report_core, "receipt_digest": sha256_digest(report_core)}
    if evidence_root is not None:
        root = Path(evidence_root)
        run_root = root / report["run_id"]
        run_root.mkdir(parents=True, exist_ok=True)
        (run_root / "verification.json").write_text(json.dumps(report, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        (run_root / "verification.md").write_text(_markdown(report), encoding="utf-8")
        _write_checksums(run_root)
    return report


def _write_checksums(root: Path) -> None:
    rows = []
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.name != "SHA256SUMS.txt":
            rows.append(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.relative_to(root)}")
    (root / "SHA256SUMS.txt").write_text("\n".join(rows) + "\n", encoding="utf-8")


def _markdown(report: Mapping[str, Any]) -> str:
    score = report["score"]
    return "\n".join([
        f"# C4-X third-party submission verification · {report['run_id']}",
        "",
        f"- Receipt: `{report['receipt_digest']}`",
        f"- System: `{report['system_id']}`",
        f"- Benchmark receipt: `{report['benchmark_receipt_digest']}`",
        f"- Cases: `{report['case_count']}`",
        f"- Missing cases: `{report['missing_case_count']}`",
        f"- Semantic correct: `{score['semantic_correct']}/{score['case_count']}`",
        f"- Artifact custody valid: `{score['artifact_custody_valid']}/{score['case_count']}`",
        f"- Provider calls used: `{score['provider_calls_used']}`",
        f"- Total score: `{score['total_score']}`",
        "",
        "## Boundary",
        "",
        str(report["claim_boundary"]),
        "",
    ])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark", required=True, help="Path to benchmark.json containing oracle_expected cases.")
    parser.add_argument("--submission", required=True, help="Path to third-party submission JSON.")
    parser.add_argument("--evidence-root", default=str(REPO_ROOT / "evidence" / "c4x-external-breakthrough-verifications"))
    parser.add_argument("--run-id", default=None)
    args = parser.parse_args(argv)
    report = verify_submission(
        benchmark_path=args.benchmark,
        submission_path=args.submission,
        evidence_root=args.evidence_root,
        run_id=args.run_id,
    )
    print(json.dumps({
        "receipt_digest": report["receipt_digest"],
        "system_id": report["system_id"],
        "score": report["score"],
    }, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

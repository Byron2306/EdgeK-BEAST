"""Phase 12 evidence-backed Agent Gauntlet promotion decision.

This module deliberately does not execute the coding agent. It evaluates
machine-readable case receipts produced by the integrated gauntlet and refuses
promotion when required authority/evidence properties are absent.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

REQUIRED_CASES = ("simple_mutation", "cross_file_reasoning", "repair", "large_repo_navigation", "remote_target")


def _digest(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return "sha256:" + hashlib.sha256(raw.encode()).hexdigest()


def evaluate_agent_gauntlet(cases: list[dict[str, Any]]) -> dict[str, Any]:
    by_id = {str(case.get("case_id") or ""): case for case in cases if isinstance(case, dict)}
    results: list[dict[str, Any]] = []
    for case_id in REQUIRED_CASES:
        case = by_id.get(case_id, {})
        checks = {
            "present": bool(case),
            "completed": bool(case.get("completed")),
            "exact_source_grounded": bool(case.get("exact_source_grounded")),
            "governed_mutation": bool(case.get("governed_mutation")),
            "fresh_verification": bool(case.get("fresh_verification")),
            "event_chain_valid": bool(case.get("event_chain_valid")),
            "no_unsupported_completion": not bool(case.get("unsupported_completion")),
        }
        if case_id == "repair":
            checks["repair_observed"] = bool(case.get("repair_observed"))
            checks["repair_bounded"] = bool(case.get("repair_bounded"))
        if case_id == "remote_target":
            checks["target_evidence_preserved"] = bool(case.get("target_evidence_preserved"))
            checks["same_authority_model"] = bool(case.get("same_authority_model"))
        if case_id == "cross_file_reasoning":
            checks["cross_file_evidence"] = int(case.get("relevant_files_used") or 0) >= 2
        if case_id == "large_repo_navigation":
            checks["repository_discovery_used"] = bool(case.get("repository_discovery_used"))
            checks["manual_attachment_dependency"] = not bool(case.get("manual_attachment_dependency"))
        passed = all(checks.values())
        results.append({"case_id": case_id, "passed": passed, "checks": checks, "evidence": case.get("evidence", {})})

    required_pass = all(item["passed"] for item in results)
    baseline = {
        "before_programme": "thin_llm_wrapper_with_fragmented_organs",
        "after_programme": "governed_integrated_agent_vertical_slice",
        "comparison_type": "architectural_and_case_receipt_baseline",
        "performance_claimed": False,
    }
    decision = {
        "beast_object_type": "beast_agent_phase12_promotion_decision",
        "version": "1.0",
        "required_cases": list(REQUIRED_CASES),
        "results": results,
        "passed_cases": sum(1 for item in results if item["passed"]),
        "required_case_count": len(REQUIRED_CASES),
        "promotion_decision": "PROMOTE" if required_pass else "REFUSE",
        "promotion_scope": "coding_agent_recovery_programme" if required_pass else "none",
        "baseline": baseline,
        "authority": "evidence_evaluation_only",
        "grants_source_authority": False,
        "grants_mutation_authority": False,
        "grants_promotion_authority": False,
    }
    decision["decision_digest"] = _digest(decision)
    return decision

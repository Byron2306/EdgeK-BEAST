"""Phase 9 verifier-driven repair and learning projection.

This composes existing BEAST failure analysis, Quality Cascade semantics and
Phase-E learning without creating a second repair executor.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

from app.kernel.agents.failure_analyst import analyze_failure
from app.kernel.agents.phase_e_learning import Scribe


def _digest(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return "sha256:" + hashlib.sha256(raw.encode()).hexdigest()


def repair_projection(observation: dict[str, Any], *, repair_cycle: int, max_repair_cycles: int) -> dict[str, Any]:
    result = observation.get("result") if isinstance(observation.get("result"), dict) else {}
    diagnostic = "\n".join(filter(None, [
        str(observation.get("error") or ""),
        str(result.get("stderr") or ""),
        str(result.get("stdout") or ""),
    ]))
    analysis = analyze_failure(diagnostic)
    budget_remaining = max(0, int(max_repair_cycles) - int(repair_cycle))
    retry_without_mutation = bool(analysis.get("retryable_without_code_change"))
    projection = {
        "beast_object_type": "beast_agent_repair_projection",
        "version": "1.0",
        "failure_analysis": analysis,
        "repair_cycle": int(repair_cycle),
        "max_repair_cycles": int(max_repair_cycles),
        "budget_remaining": budget_remaining,
        "next_mode": "retry_verification" if retry_without_mutation else "bounded_code_repair",
        "quality_cascade_role": "deterministic_diagnostic_evidence",
        "requires_exact_source_before_mutation": not retry_without_mutation,
        "requires_fresh_verification_after_mutation": True,
        "learning_authority": "evidence_only",
        "mutation_authority": "none",
    }
    projection["projection_digest"] = _digest(projection)
    return projection


def learning_episode(*, run: dict[str, Any], state: Any, observation: dict[str, Any], passed: bool) -> dict[str, Any]:
    result = observation.get("result") if isinstance(observation.get("result"), dict) else {}
    event = {
        "decision": "verification_passed" if passed else "verification_failed",
        "details": {
            "receipt_id": str(observation.get("evidence_digest") or ""),
            "tool_id": str(observation.get("tool_id") or ""),
            "returncode": result.get("returncode"),
        },
    }
    episode = Scribe().compile_episode(
        task_class="coding_agent_repair",
        events=[event],
        execution={"status": "completed" if passed else "blocked"},
        verification={"status": "passed" if passed else "failed"},
        critic={"status": "passed" if passed else "not_run"},
    )
    episode["run_id"] = str(run.get("run_id") or getattr(state, "run_id", "") or "")
    episode["authority"] = "learning_evidence_never_mutation_authority"
    episode["episode_digest"] = _digest(episode)
    return episode


def repair_budget_gate(*, repair_cycle: int, max_repair_cycles: int, source_current: bool) -> dict[str, Any]:
    cycle = max(0, int(repair_cycle))
    maximum = max(0, int(max_repair_cycles))
    within_budget = cycle <= maximum
    allowed = within_budget and bool(source_current)
    receipt = {
        "beast_object_type": "beast_agent_repair_budget_gate",
        "version": "1.0",
        "allowed": allowed,
        "repair_cycle": cycle,
        "max_repair_cycles": maximum,
        "within_budget": within_budget,
        "source_current": bool(source_current),
        "reason": "repair_allowed" if allowed else ("repair_budget_exhausted" if not within_budget else "fresh_exact_source_required"),
        "mutation_authority": "none",
    }
    receipt["gate_digest"] = _digest(receipt)
    return receipt

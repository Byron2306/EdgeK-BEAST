"""Phase 3 stagnation and oscillation detection for the AgentRun planner."""

from __future__ import annotations

import hashlib
import json
import time
from typing import Any

from app.kernel.agents.planner_models import PlannerDecision, PlannerDecisionType, PlannerState


def _canonical_hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def decision_fingerprint(decision: PlannerDecision | dict[str, Any]) -> str:
    if isinstance(decision, PlannerDecision):
        payload = decision.as_dict()
    else:
        payload = dict(decision or {})
    kind = str(payload.get("decision_type") or "")
    if kind != PlannerDecisionType.TOOL.value:
        return ""
    body = {
        "decision_type": kind,
        "tool_id": str(payload.get("tool_id") or ""),
        "arguments": payload.get("arguments") if isinstance(payload.get("arguments"), dict) else {},
        "execution_target": str(payload.get("execution_target") or "local"),
    }
    return "sha256:" + _canonical_hash(body)


def _event_decision_fingerprints(events: list[dict[str, Any]]) -> list[str]:
    values: list[str] = []
    for event in events:
        if str(event.get("event_type") or "") != "agent.planner.decision":
            continue
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        raw = payload.get("decision") if isinstance(payload.get("decision"), dict) else {}
        fingerprint = decision_fingerprint(raw)
        if fingerprint:
            values.append(fingerprint)
    return values


def _observation_evidence_key(observation: dict[str, Any]) -> str:
    tool_id = str(observation.get("tool_id") or "")
    status = str(observation.get("status") or "")
    evidence = str(observation.get("evidence_digest") or "")
    if evidence:
        return f"{tool_id}|{status}|{evidence}"
    result = observation.get("result") if isinstance(observation.get("result"), dict) else {}
    error = str(observation.get("error") or "")
    return f"{tool_id}|{status}|{_canonical_hash({'result': result, 'error': error})}"


def _verification_failure_key(failure: dict[str, Any]) -> str:
    result = failure.get("result") if isinstance(failure.get("result"), dict) else {}
    analysis = failure.get("analysis") if isinstance(failure.get("analysis"), dict) else {}
    body = {
        "command": failure.get("command") or result.get("command") or [],
        "returncode": result.get("returncode"),
        "error": str(failure.get("error") or ""),
        "failure_class": str(analysis.get("failure_class") or analysis.get("category") or ""),
        "root_cause": str(analysis.get("root_cause") or ""),
    }
    return _canonical_hash(body)


def _latest_replan_for(events: list[dict[str, Any]], fingerprint: str) -> bool:
    for event in reversed(events):
        event_type = str(event.get("event_type") or "")
        if event_type == "agent.stagnation.detected":
            payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
            receipt = payload.get("stagnation_receipt") if isinstance(payload.get("stagnation_receipt"), dict) else {}
            return (
                str(receipt.get("decision_fingerprint") or "") == fingerprint
                and str(receipt.get("action") or "") == "replan"
            )
        if event_type in {"agent.tool.started", "agent.tool.completed", "agent.tool.failed"}:
            return False
    return False


def _receipt(
    *,
    run_id: str,
    decision_fingerprint_value: str,
    detected: bool,
    signal: str = "",
    reason: str = "",
    action: str = "continue",
    evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    body = {
        "run_id": str(run_id or ""),
        "decision_fingerprint": decision_fingerprint_value,
        "detected": bool(detected),
        "signal": signal,
        "reason": reason,
        "action": action,
        "evidence": dict(evidence or {}),
    }
    digest = _canonical_hash(body)
    return {
        "beast_object_type": "agent_stagnation_receipt",
        "version": "1.0",
        "receipt_id": f"stagnation_{digest[:20]}",
        "receipt_hash": f"sha256:{digest}",
        "issued_at": time.time(),
        **body,
    }


def evaluate_stagnation(
    run: dict[str, Any],
    state: PlannerState,
    decision: PlannerDecision,
    events: list[dict[str, Any]],
) -> dict[str, Any]:
    fingerprint = decision_fingerprint(decision)
    run_id = str(run.get("run_id") or state.run_id or "")
    if not fingerprint:
        return _receipt(
            run_id=run_id,
            decision_fingerprint_value="",
            detected=False,
        )

    if _latest_replan_for(events, fingerprint):
        return _receipt(
            run_id=run_id,
            decision_fingerprint_value=fingerprint,
            detected=True,
            signal="replan_ignored",
            reason="the planner repeated the same bounded action after an explicit stagnation replan",
            action="stop",
        )

    previous = _event_decision_fingerprints(events)
    real_observations = [
        item for item in state.observations
        if isinstance(item, dict)
        and str(item.get("tool_id") or "") != "planner.stagnation_guard"
    ]

    if len(previous) >= 2 and previous[-2:] == [fingerprint, fingerprint] and len(real_observations) >= 2:
        last_two = real_observations[-2:]
        current_tool = str(decision.tool_id or "")
        if (
            all(str(item.get("tool_id") or "") == current_tool for item in last_two)
            and _observation_evidence_key(last_two[0]) == _observation_evidence_key(last_two[1])
        ):
            return _receipt(
                run_id=run_id,
                decision_fingerprint_value=fingerprint,
                detected=True,
                signal="equivalent_tool_no_new_evidence",
                reason="the same tool call produced equivalent evidence across consecutive turns",
                action="replan",
                evidence={"prior_decisions": previous[-2:], "tool_id": current_tool},
            )

    if len(previous) >= 3:
        sequence = previous[-3:] + [fingerprint]
        if sequence[0] == sequence[2] and sequence[1] == sequence[3] and sequence[0] != sequence[1]:
            return _receipt(
                run_id=run_id,
                decision_fingerprint_value=fingerprint,
                detected=True,
                signal="planner_oscillation",
                reason="planner decisions are oscillating between two equivalent actions",
                action="replan",
                evidence={"decision_sequence": sequence},
            )

    failures = [
        item for item in state.verification_failures
        if isinstance(item, dict)
    ]
    if decision.tool_id == "worktree.verify" and len(failures) >= 2:
        keys = [_verification_failure_key(item) for item in failures[-2:]]
        if keys[0] == keys[1]:
            return _receipt(
                run_id=run_id,
                decision_fingerprint_value=fingerprint,
                detected=True,
                signal="repeated_verifier_failure",
                reason="the same verifier failure repeated without new repair evidence",
                action="replan",
                evidence={"failure_fingerprint": keys[0]},
            )

    truncated = [
        item for item in real_observations[-2:]
        if bool(item.get("truncated"))
    ]
    if (
        len(truncated) == 2
        and all(str(item.get("tool_id") or "") == str(decision.tool_id or "") for item in truncated)
    ):
        return _receipt(
            run_id=run_id,
            decision_fingerprint_value=fingerprint,
            detected=True,
            signal="repeated_truncated_output",
            reason="repeated truncated tool output requires a narrower request",
            action="replan",
            evidence={"tool_id": str(decision.tool_id or "")},
        )

    return _receipt(
        run_id=run_id,
        decision_fingerprint_value=fingerprint,
        detected=False,
    )

from __future__ import annotations

import asyncio

from app.kernel.agents.planner_models import PlannerDecision, PlannerDecisionType, PlannerState
from app.kernel.agents.planner_provider import ScriptedPlannerProvider
from app.kernel.agents.planner_runtime import AgentPlannerRuntime
from app.kernel.agents.planner_stagnation import decision_fingerprint, evaluate_stagnation
from app.kernel.agents.run_engine import AgentRunEngine


def _tool(tool_id: str, arguments: dict | None = None) -> PlannerDecision:
    return PlannerDecision(
        decision_type=PlannerDecisionType.TOOL,
        tool_id=tool_id,
        arguments=arguments or {},
    )


def _decision_event(turn: int, decision: PlannerDecision) -> dict:
    return {
        "event_type": "agent.planner.decision",
        "payload": {"turn": turn, "decision": decision.as_dict()},
    }


def test_equivalent_tool_without_new_evidence_requires_replan():
    decision = _tool("workspace.list", {})
    fingerprint = decision_fingerprint(decision)
    state = PlannerState(
        run_id="run-stagnation",
        observations=[
            {"tool_id": "workspace.list", "status": "completed", "evidence_digest": "same"},
            {"tool_id": "workspace.list", "status": "completed", "evidence_digest": "same"},
        ],
    )
    events = [_decision_event(1, decision), _decision_event(2, decision)]
    receipt = evaluate_stagnation(
        {"run_id": state.run_id},
        state,
        decision,
        events,
    )
    assert receipt["detected"] is True
    assert receipt["action"] == "replan"
    assert receipt["signal"] == "equivalent_tool_no_new_evidence"
    assert receipt["decision_fingerprint"] == fingerprint


def test_repeating_same_action_after_replan_stops():
    decision = _tool("workspace.list", {})
    fingerprint = decision_fingerprint(decision)
    state = PlannerState(run_id="run-stop")
    events = [
        {
            "event_type": "agent.stagnation.detected",
            "payload": {
                "stagnation_receipt": {
                    "decision_fingerprint": fingerprint,
                    "action": "replan",
                }
            },
        }
    ]
    receipt = evaluate_stagnation(
        {"run_id": state.run_id},
        state,
        decision,
        events,
    )
    assert receipt["detected"] is True
    assert receipt["action"] == "stop"
    assert receipt["signal"] == "replan_ignored"


def test_abab_decision_oscillation_requires_replan():
    a = _tool("workspace.list", {"path": "."})
    b = _tool("workspace.search_text", {"query": "VALUE"})
    state = PlannerState(run_id="run-oscillation")
    events = [
        _decision_event(1, a),
        _decision_event(2, b),
        _decision_event(3, a),
    ]
    receipt = evaluate_stagnation(
        {"run_id": state.run_id},
        state,
        b,
        events,
    )
    assert receipt["detected"] is True
    assert receipt["action"] == "replan"
    assert receipt["signal"] == "planner_oscillation"


def test_repeated_verifier_failure_requires_replan():
    verify = _tool("worktree.verify", {"command": ["python", "-m", "pytest", "-q"]})
    failure = {
        "error": "verification failed",
        "command": ["python", "-m", "pytest", "-q"],
        "result": {"returncode": 1},
        "analysis": {"failure_class": "test_failure", "root_cause": "same assertion"},
    }
    state = PlannerState(
        run_id="run-verify-loop",
        verification_failures=[dict(failure), dict(failure)],
    )
    receipt = evaluate_stagnation(
        {"run_id": state.run_id},
        state,
        verify,
        [],
    )
    assert receipt["detected"] is True
    assert receipt["signal"] == "repeated_verifier_failure"


def test_runtime_replans_once_then_blocks_identical_dead_end(tmp_path):
    engine = AgentRunEngine(tmp_path)
    run_id = engine.create_run(
        session_id="phase3-stagnation-runtime",
        objective="Demonstrate bounded stagnation control",
        mode="analysis",
        provider="simulated",
        model="stagnation-test",
        budget={"max_model_turns": 8, "max_tool_calls": 8},
    )["run_id"]

    repeated = {"decision_type": "tool", "tool_id": "workspace.list", "arguments": {}}
    provider = ScriptedPlannerProvider([repeated, repeated, repeated, repeated, repeated])
    final = asyncio.run(AgentPlannerRuntime(engine, provider, max_turns=8).run(run_id))

    assert final["state"] == "policy_blocked"
    events = engine.store.events(run_id, limit=300)
    started = [
        event for event in events
        if event["event_type"] == "agent.tool.started"
        and event["payload"].get("tool_id") == "workspace.list"
    ]
    stagnation = [
        event["payload"]["stagnation_receipt"]
        for event in events
        if event["event_type"] == "agent.stagnation.detected"
    ]
    assert len(started) == 2
    assert [item["action"] for item in stagnation[-2:]] == ["replan", "stop"]
    assert stagnation[-1]["signal"] == "replan_ignored"

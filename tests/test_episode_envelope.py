from __future__ import annotations

import dataclasses
import json
import sys
from pathlib import Path

import pytest

from app.kernel.agents.planner_models import PlannerDecision, PlannerDecisionType
from app.kernel.agents.run_store import AgentRunStore
from app.kernel.sensorium.episode_envelope import (
    EpisodeEnvelopeBuilder,
    EpisodeEnvelopeStore,
    RunBudgetTracker,
    envelope_from_swarm_episode,
)

sys.path.insert(0, str(Path(__file__).resolve().parent))

SECRET = "password=hunter2-very-secret"


def _store_with_run(tmp_path, *, objective="Fix calc.py so the rate test passes"):
    store = AgentRunStore(tmp_path)
    run = store.create_run(
        session_id="s", objective=objective, mode="agent", provider="simulated", model="m",
        request={"task_family": "fix-failing-assertion", "implementation_target": "calc.py",
                 "post_session_test_runner": "unittest"},
    )
    return store, run["run_id"]


def _observation(tool_id, status="completed", arguments=None, result=None, digest="d"):
    return {"observation_id": f"obs-{tool_id}-{digest}", "tool_id": tool_id, "status": status,
            "arguments": arguments or {}, "result": result or {}, "evidence_digest": digest,
            "duration_ms": 5, "error": ""}


def _seed(store, run_id, tracker):
    observations = [
        _observation("workspace.search_text", arguments={"query": SECRET, "path": "."}, digest="a"),
        _observation("workspace.read_range", arguments={"path": "calc.py", "start_line": 1, "line_count": 20},
                     result={"content": "RATE = 3  # " + SECRET}, digest="b"),
        _observation("worktree.verify", arguments={"command": ["python3", "-m", "unittest"]},
                     result={"returncode": 1, "ok": False, "stdout": SECRET}, digest="c"),
        _observation("worktree.replace_exact", arguments={"path": "calc.py", "old_text": "RATE = 3", "new_text": "RATE = 4"},
                     digest="d"),
        _observation("worktree.verify", arguments={"command": ["python3", "-m", "unittest"]},
                     result={"returncode": 0, "ok": True}, digest="e"),
    ]
    sources = ["model", "model", "crystal", "crystal", "runtime"]
    for item, source in zip(observations, sources):
        tracker.record_tool_call(run_id, tool_id=item["tool_id"], status=item["status"], source=source)
    store.checkpoint(run_id, {"planner": {"observations": observations, "turn": 3}})
    return observations


def test_budget_tracker_accumulates_turns_tokens_tools_and_wall(tmp_path):
    store, run_id = _store_with_run(tmp_path)
    clock = iter([100.0, 100.25, 101.0])
    tracker = RunBudgetTracker(store, clock=lambda: next(clock))
    tracker.start(run_id)
    decision = PlannerDecision(decision_type=PlannerDecisionType.TOOL, tool_id="workspace.list")
    tracker.record_model_turn(run_id, prompt="x" * 400, decision=decision, usage=None)
    tracker.record_model_turn(run_id, prompt="ignored", decision=decision,
                              usage={"prompt_tokens": 50, "completion_tokens": 7})
    tracker.record_tool_call(run_id, tool_id="workspace.list", status="completed", source="model")
    tracker.record_tool_call(run_id, tool_id="worktree.verify", status="failed", source="runtime")
    tracker.mark_wall(run_id)
    tracker.mark_wall(run_id)
    budget = store.get_run(run_id)["budget"]
    assert budget["model_turns"] == 2
    assert budget["tokens_prompt"] >= 150 and budget["tokens_completion"] >= 7
    assert budget["tokens_total"] == budget["tokens_prompt"] + budget["tokens_completion"]
    assert budget["tokens_estimated_turns"] == 1
    assert budget["tool_calls"] == 2
    assert budget["tool_calls_model"] == 1 and budget["tool_calls_runtime"] == 1
    assert budget["tool_failures"] == 1
    assert budget["wall_ms"] == pytest.approx(1000.0)
    events = [e for e in store.events(run_id) if e["event_type"] == "agent.budget.recorded"]
    assert [e["payload"]["source"] for e in events] == ["model", "runtime"]


def test_envelope_is_privacy_filtered_and_records_negative_evidence(tmp_path):
    store, run_id = _store_with_run(tmp_path, objective="Fix it; " + SECRET)
    tracker = RunBudgetTracker(store)
    _seed(store, run_id, tracker)
    envelope = EpisodeEnvelopeBuilder().build(store, run_id)
    encoded = json.dumps(dataclasses.asdict(envelope), sort_keys=True)
    assert "hunter2" not in encoded
    assert "Fix it" not in encoded
    assert envelope.task_family == "fix-failing-assertion"
    assert envelope.implementation_target == "calc.py"
    assert [step["source"] for step in envelope.steps] == ["model", "model", "crystal", "crystal", "runtime"]
    assert envelope.steps[1]["safe_arguments"] == {"path": "calc.py", "start_line": 1, "line_count": 20}
    assert "query" not in envelope.steps[0]["safe_arguments"]
    assert envelope.steps[2]["returncode"] == 1
    assert envelope.verification == {"present": True, "passed": True, "failures_before_pass": 1,
                                     "final_returncode": 0, "verify_steps": 2}
    assert envelope.negative_evidence == ({"index": 2, "tool_id": "worktree.verify",
                                           "kind": "verification_failed", "result_digest": "c"},)
    assert envelope.budget["tool_calls"] == 5
    assert envelope.event_chain_head == store.get_run(run_id)["head_hash"]
    envelope.validate()


def test_envelope_digest_is_deterministic_and_tamper_evident(tmp_path):
    store, run_id = _store_with_run(tmp_path)
    _seed(store, run_id, RunBudgetTracker(store))
    first = EpisodeEnvelopeBuilder().build(store, run_id)
    second = EpisodeEnvelopeBuilder().build(store, run_id)
    assert first.envelope_digest == second.envelope_digest
    tampered = dataclasses.replace(first, budget={**first.budget, "tool_calls": 1})
    with pytest.raises(ValueError):
        tampered.validate()


def test_envelope_store_round_trips_and_refuses_tampering(tmp_path):
    store, run_id = _store_with_run(tmp_path)
    _seed(store, run_id, RunBudgetTracker(store))
    envelope = EpisodeEnvelopeBuilder().build(store, run_id)
    envelopes = EpisodeEnvelopeStore(tmp_path / "envelopes.sqlite3")
    envelopes.put(envelope)
    assert envelopes.get(run_id) == envelope
    assert [item.run_id for item in envelopes.list(task_family="fix-failing-assertion")] == [run_id]
    with pytest.raises(ValueError):
        envelopes.put(dataclasses.replace(envelope, state="completed-forged"))


def test_swarm_episode_adapter_uses_the_same_contract():
    episode = {
        "task_class": "repair",
        "episode_status": "verified",
        "events": [{"decision": "inspect", "details": {"receipt_id": "r1", "secret": SECRET}},
                   {"decision": "verify", "details": {"receipt_id": "r2"}}],
        "classifications": ["repair_pattern"],
    }
    envelope = envelope_from_swarm_episode(episode, run_id="swarm-1")
    envelope.validate()
    assert envelope.task_family == "repair"
    assert [step["source"] for step in envelope.steps] == ["swarm", "swarm"]
    assert envelope.verification["passed"] is True
    assert "hunter2" not in json.dumps(dataclasses.asdict(envelope))


# --- Task 2: planner runtime wiring -------------------------------------------------------------

def _run_learn(tmp_path, **runtime_kwargs):
    import asyncio

    from crystal_fabric_support import create_assertion_run, learn_script, make_assertion_repo

    from app.kernel.agents.planner_provider import ScriptedPlannerProvider
    from app.kernel.agents.planner_runtime import AgentPlannerRuntime

    root = make_assertion_repo(tmp_path / "repo")
    engine, run_id = create_assertion_run(root)
    script = learn_script()
    provider = ScriptedPlannerProvider(script)
    final = asyncio.run(AgentPlannerRuntime(engine, provider, max_turns=14, **runtime_kwargs).run(run_id))
    consumed = len(script) - len(provider._decisions)
    return engine, run_id, final, consumed


def test_runtime_meters_model_turns_tool_calls_and_wall_time(tmp_path):
    envelopes = EpisodeEnvelopeStore(tmp_path / "env.sqlite3")
    engine, run_id, final, consumed = _run_learn(tmp_path, envelope_store=envelopes)
    assert final["state"] == "completed"
    budget = final["budget"]
    observations = final["checkpoint"]["planner"]["observations"]
    assert budget["model_turns"] == consumed
    assert budget["tool_calls"] == len(observations)
    assert budget["tool_calls"] == budget.get("tool_calls_model", 0) + budget.get("tool_calls_runtime", 0) + budget.get("tool_calls_crystal", 0)
    assert budget.get("tool_calls_runtime", 0) >= 1, "runtime-injected steps must be attributed to the runtime"
    assert budget["tokens_total"] > 0 and budget["wall_ms"] > 0
    assert budget["tool_failures"] >= 1  # the deliberate red verify


def test_runtime_seals_and_stores_an_envelope_at_run_end(tmp_path):
    envelopes = EpisodeEnvelopeStore(tmp_path / "env.sqlite3")
    engine, run_id, final, _ = _run_learn(tmp_path, envelope_store=envelopes)
    envelope = envelopes.get(run_id)
    envelope.validate()
    assert envelope.task_family == "fix-failing-assertion"
    assert envelope.verification["passed"] is True and envelope.verification["failures_before_pass"] >= 1
    assert len(envelope.steps) == len(final["checkpoint"]["planner"]["observations"])
    assert {step["source"] for step in envelope.steps} <= {"model", "runtime", "crystal"}
    sealed = [e for e in engine.store.events(run_id, limit=500) if e["event_type"] == "agent.episode.sealed"]
    assert len(sealed) == 1
    assert sealed[0]["payload"]["envelope_digest"] == envelope.envelope_digest
    assert sealed[0]["payload"]["budget"]["model_turns"] == final["budget"]["model_turns"]
    assert "Fix the failing assertion" not in json.dumps(envelope.to_dict())


def test_runtime_meters_budget_without_an_envelope_store(tmp_path):
    engine, run_id, final, consumed = _run_learn(tmp_path)
    assert final["budget"]["model_turns"] == consumed
    assert [e for e in engine.store.events(run_id, limit=500) if e["event_type"] == "agent.episode.sealed"]

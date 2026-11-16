from __future__ import annotations

import hashlib
import json
from copy import deepcopy

import pytest

from scripts.trace_beast_coding_agent_runtime import (
    merge_trace_records,
    trace_records_from_agent_run_events,
    verify_agent_run_event_chain,
)


def _component(path: str) -> dict:
    return {
        "path": path,
        "language": "python",
        "layer": "agency_planning",
        "imports": [],
        "runtime": {
            "constructed": "unverified",
            "invoked": "unverified",
            "evidence_producing": "unverified",
        },
        "authority": "unverified",
        "disposition": "unclassified",
        "agent_relevance": "direct",
        "composition_roots": [],
        "claimed_responsibilities": [],
        "overlap_candidates": [],
        "notes": [],
    }


def _report(*paths: str) -> dict:
    return {
        "beast_object_type": "beast_full_system_census",
        "version": "0.2",
        "summary": {},
        "components": [_component(path) for path in paths],
    }


def _canonical(value) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    ).encode("utf-8")


def _event(run_id: str, sequence: int, event_type: str, payload: dict, previous_hash: str = "") -> dict:
    created_at = float(1700000000 + sequence)
    body = {
        "run_id": run_id,
        "sequence": sequence,
        "event_type": event_type,
        "legacy_type": "",
        "created_at": created_at,
        "payload": payload,
    }
    event_hash = "sha256:" + hashlib.sha256(previous_hash.encode("utf-8") + _canonical(body)).hexdigest()
    return {
        **body,
        "event_id": f"evt-{sequence}",
        "previous_hash": previous_hash,
        "event_hash": event_hash,
    }


def test_static_census_alone_cannot_promote_runtime_truth():
    report = _report("app/kernel/agents/planner_runtime.py")

    merged = merge_trace_records(report, [])

    item = merged["components"][0]
    assert item["runtime"] == {
        "constructed": "unverified",
        "invoked": "unverified",
        "evidence_producing": "unverified",
    }
    assert item["authority"] == "unverified"


def test_explicit_trace_promotes_only_the_observed_runtime_fact():
    path = "app/kernel/agents/planner_runtime.py"
    report = _report(path)
    trace = {
        "request_id": "req-1",
        "run_id": "run-1",
        "component_path": path,
        "event": "constructed",
        "evidence_ref": "agent_run:run-1:event:1:sha256:abc",
        "timestamp": 1700000001.0,
        "source": "agent_run_event_chain",
    }

    merged = merge_trace_records(report, [trace])

    item = merged["components"][0]
    assert item["runtime"]["constructed"] == "observed"
    assert item["runtime"]["invoked"] == "unverified"
    assert item["runtime"]["evidence_producing"] == "unverified"
    assert item["authority"] == "unverified"
    assert item["runtime_evidence"] == [trace]


def test_trace_events_promote_invocation_evidence_and_authority_independently():
    path = "app/kernel/agents/tool_runtime.py"
    report = _report(path)
    traces = [
        {
            "request_id": "req-2",
            "run_id": "run-2",
            "component_path": path,
            "event": "invoked",
            "evidence_ref": "agent_run:run-2:event:3:sha256:def",
            "timestamp": 1700000003.0,
            "source": "agent_run_event_chain",
        },
        {
            "request_id": "req-2",
            "run_id": "run-2",
            "component_path": path,
            "event": "authority_exercised",
            "evidence_ref": "tool_observation:obs-1:sha256:123",
            "timestamp": 1700000004.0,
            "source": "explicit_runtime_trace",
        },
    ]

    merged = merge_trace_records(report, traces)

    item = merged["components"][0]
    assert item["runtime"]["invoked"] == "observed"
    assert item["authority"] == "observed"
    assert item["runtime"]["constructed"] == "unverified"


def test_trace_merge_rejects_unknown_components_and_unbacked_claims():
    report = _report("app/kernel/agents/planner_runtime.py")
    unknown = {
        "request_id": "req-3",
        "run_id": "run-3",
        "component_path": "app/kernel/agents/not_real.py",
        "event": "invoked",
        "evidence_ref": "agent_run:run-3:event:1:sha256:abc",
        "timestamp": 1700000001.0,
        "source": "agent_run_event_chain",
    }
    no_evidence = {
        **unknown,
        "component_path": "app/kernel/agents/planner_runtime.py",
        "evidence_ref": "",
    }

    with pytest.raises(ValueError, match="unknown component"):
        merge_trace_records(report, [unknown])
    with pytest.raises(ValueError, match="evidence_ref"):
        merge_trace_records(report, [no_evidence])


def test_agent_run_event_chain_maps_only_uniquely_proven_producers():
    paths = (
        "app/kernel/agents/run_store.py",
        "app/kernel/agents/planner_runtime.py",
        "app/kernel/agents/tool_runtime.py",
        "app/kernel/sensorium/runtime.py",
    )
    report = _report(*paths)
    first = _event("run-4", 1, "agent.planner.started", {"turn": 0, "max_turns": 8})
    second = _event(
        "run-4",
        2,
        "agent.tool.started",
        {"tool_id": "workspace.index", "risk": "low", "effect": "read"},
        previous_hash=first["event_hash"],
    )

    chain = [first, second]
    verification = verify_agent_run_event_chain(chain)
    traces = trace_records_from_agent_run_events(chain, request_id="req-4")
    merged = merge_trace_records(deepcopy(report), traces)
    by_path = {item["path"]: item for item in merged["components"]}

    assert verification == {"valid": True, "event_count": 2, "run_id": "run-4", "head_hash": second["event_hash"]}
    assert by_path["app/kernel/agents/run_store.py"]["runtime"]["evidence_producing"] == "observed"
    assert by_path["app/kernel/agents/planner_runtime.py"]["runtime"]["invoked"] == "observed"
    assert by_path["app/kernel/agents/tool_runtime.py"]["runtime"]["invoked"] == "observed"
    # AgentRunEngine mirrors to Sensorium best-effort and swallows mirror errors;
    # an AgentRun ledger event therefore does not prove Sensorium participation.
    assert by_path["app/kernel/sensorium/runtime.py"]["runtime"]["invoked"] == "unverified"


def test_tampered_agent_run_chain_is_refused_as_runtime_evidence():
    first = _event("run-5", 1, "agent.planner.started", {"turn": 0})
    second = _event("run-5", 2, "agent.planner.completed", {"turns": 1}, previous_hash=first["event_hash"])
    second["payload"] = {"turns": 99}

    with pytest.raises(ValueError, match="event hash mismatch"):
        verify_agent_run_event_chain([first, second])
    with pytest.raises(ValueError, match="event hash mismatch"):
        trace_records_from_agent_run_events([first, second], request_id="req-5")

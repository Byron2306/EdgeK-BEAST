from pathlib import Path
import pytest
from app.kernel.agents.run_store import AgentRunStore
from app.kernel.operations_console.timeline_console import LiveRunTimelineConsole


def seed(root: Path):
    store = AgentRunStore(root)
    run = store.create_run(session_id="s57", objective="Repair parser", run_id="run-57")
    rid = run["run_id"]
    store.append_event(rid, "agent.context.packet.built", {"summary":"Context packet built", "status":"succeeded"})
    store.append_event(rid, "agent.tool.started", {"summary":"Read failing test", "tool_id":"workspace.read_range", "step_id":"inspect"})
    store.append_event(rid, "agent.verify.completed", {"summary":"Focused test failed", "status":"failed", "step_id":"verify", "evidence_digest":"sha256:test"})
    store.append_event(rid, "agent.plan.updated", {"summary":"Plan updated", "step_id":"repair"})
    store.create_approval(rid, {"approval_id":"approval-57", "tool_id":"workspace.apply_patch"})
    return rid


def test_builds_grouped_operator_timeline(tmp_path):
    rid=seed(tmp_path); view=LiveRunTimelineConsole(tmp_path).build(rid, now=1000)
    assert view["beast_object_type"] == "beast_live_run_timeline_console"
    assert view["summary"]["visible_count"] >= 5
    assert any(g["step_group"] == "verify" for g in view["groups"])
    assert view["projection_chain"]["ok"] is True


def test_category_severity_step_and_query_filters(tmp_path):
    rid=seed(tmp_path); console=LiveRunTimelineConsole(tmp_path)
    assert console.build(rid,categories="verification")["summary"]["visible_count"] == 1
    assert console.build(rid,severities="error")["summary"]["visible_count"] == 1
    assert console.build(rid,step_id="inspect")["events"][0]["tool_id"] == "workspace.read_range"
    assert console.build(rid,query="approval")["summary"]["visible_count"] >= 1


def test_event_cards_are_expandable_and_evidence_bound(tmp_path):
    rid=seed(tmp_path); events=LiveRunTimelineConsole(tmp_path).build(rid)["events"]
    failed=next(e for e in events if e["category"]=="verification")
    assert failed["expandable"] is True
    assert failed["evidence_digest"] == "sha256:test"


def test_cursor_refresh_is_reconnect_safe(tmp_path):
    rid=seed(tmp_path); console=LiveRunTimelineConsole(tmp_path)
    first=console.build(rid,limit=2)
    assert first["has_more"] is True and first["refresh"]["reconnect_safe"] is True
    second=console.build(rid,cursor=first["next_cursor"],limit=100)
    ids=[e["projection_event_id"] for e in first["events"]+second["events"]]
    assert len(ids)==len(set(ids))


def test_restart_projection_is_stable(tmp_path):
    rid=seed(tmp_path)
    first=LiveRunTimelineConsole(tmp_path).build(rid,now=1234)
    second=LiveRunTimelineConsole(tmp_path).build(rid,now=1234)
    assert first["console_digest"] == second["console_digest"]


def test_tampering_is_detected(tmp_path):
    rid=seed(tmp_path); console=LiveRunTimelineConsole(tmp_path); view=console.build(rid,now=1)
    assert console.verify(view)
    view["events"][0]["summary"]="forged"
    assert not console.verify(view)


def test_invalid_filters_fail_closed(tmp_path):
    rid=seed(tmp_path)
    with pytest.raises(ValueError,match="unsupported timeline filter"):
        LiveRunTimelineConsole(tmp_path).build(rid,categories="telepathy")


def test_unknown_run_fails_closed(tmp_path):
    with pytest.raises(KeyError,match="unknown agent run"):
        LiveRunTimelineConsole(tmp_path).build("missing")


def test_console_grants_no_authority(tmp_path):
    rid=seed(tmp_path); view=LiveRunTimelineConsole(tmp_path).build(rid)
    assert view["grants_execution_authority"] is False
    assert view["grants_workspace_mutation"] is False
    assert view["grants_promotion_authority"] is False


def test_frontend_contains_live_timeline_workspace():
    html=Path("app/frontend/index.html").read_text()
    assert 'id="timelineRunId"' in html
    assert 'id="liveTimelineEvents"' in html
    assert "/console/timeline" in html
    assert "Reconnect-safe cursor polling" in html

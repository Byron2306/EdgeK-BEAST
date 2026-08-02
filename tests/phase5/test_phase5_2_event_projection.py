from pathlib import Path

import pytest

from app.kernel.agents.run_store import AgentRunStore
from app.kernel.operations_console import AgentOperationsConsoleViewModel, DurableConsoleEventProjection


def _seed(root: Path, *, count: int = 5) -> str:
    store = AgentRunStore(root)
    run = store.create_run(session_id="s52", objective="Project console events", run_id="run-52")
    run_id = run["run_id"]
    kinds = [
        ("agent.context.packet.built", {"summary": "Context packet built", "status": "succeeded"}),
        ("agent.tool.started", {"summary": "Read failing test", "tool_id": "workspace.read_range", "step_id": "step-1"}),
        ("agent.verify.completed", {"summary": "Focused test failed", "status": "failed", "evidence_digest": "sha256:test"}),
        ("agent.plan.updated", {"summary": "Plan updated", "step_id": "step-2"}),
        ("agent.sourceplan.ready", {"summary": "SourcePlan ready", "status": "ready"}),
    ]
    for event_type, payload in kinds[:count]:
        store.append_event(run_id, event_type, payload)
    store.create_approval(run_id, {"approval_id": "approval-52", "tool_id": "workspace.apply_patch"})
    return run_id


def test_projects_ordered_canonical_events(tmp_path: Path):
    run_id = _seed(tmp_path)
    page = DurableConsoleEventProjection(tmp_path).page(run_id, limit=100, view="expanded")
    assert page["beast_object_type"] == "beast_console_event_projection_page"
    assert page["chain"]["ok"] is True
    assert [event["ordinal"] for event in page["events"]] == list(range(1, page["count"] + 1))
    assert any(event["category"] == "verification" and event["severity"] == "error" for event in page["events"])
    assert any(event["category"] == "approval" for event in page["events"])
    assert page["grants_execution_authority"] is False


def test_synchronization_is_idempotent_and_suppresses_duplicates(tmp_path: Path):
    run_id = _seed(tmp_path)
    projection = DurableConsoleEventProjection(tmp_path)
    first = projection.synchronize(run_id)
    second = projection.synchronize(run_id)
    assert second["inserted"] == 0
    assert second["event_count"] == first["event_count"]
    page = projection.page(run_id, limit=100)
    ids = [event["projection_event_id"] for event in page["events"]]
    assert len(ids) == len(set(ids))


def test_projection_is_restart_stable(tmp_path: Path):
    run_id = _seed(tmp_path)
    first = DurableConsoleEventProjection(tmp_path).page(run_id, limit=100, view="expanded")
    second = DurableConsoleEventProjection(tmp_path).page(run_id, limit=100, view="expanded")
    assert first == second
    assert first["projection_head_digest"] == second["projection_head_digest"]


def test_cursor_pagination_has_no_duplicates_or_gaps(tmp_path: Path):
    run_id = _seed(tmp_path)
    projection = DurableConsoleEventProjection(tmp_path)
    first = projection.page(run_id, limit=3)
    assert first["has_more"] is True
    second = projection.page(run_id, cursor=first["next_cursor"], limit=100)
    ordinals = [item["ordinal"] for item in first["events"] + second["events"]]
    assert ordinals == list(range(1, first["projection_event_count"] + 1))


def test_cursor_is_bound_to_run(tmp_path: Path):
    run_id = _seed(tmp_path)
    projection = DurableConsoleEventProjection(tmp_path)
    cursor = projection.page(run_id, limit=1)["next_cursor"]
    store = AgentRunStore(tmp_path)
    store.create_run(session_id="other", objective="other", run_id="other-run")
    with pytest.raises(ValueError, match="does not belong"):
        projection.page("other-run", cursor=cursor)


def test_compact_and_expanded_views_share_identity(tmp_path: Path):
    run_id = _seed(tmp_path)
    projection = DurableConsoleEventProjection(tmp_path)
    compact = projection.page(run_id, limit=100, view="compact")
    expanded = projection.page(run_id, limit=100, view="expanded")
    assert [item["projection_digest"] for item in compact["events"]] == [item["projection_digest"] for item in expanded["events"]]
    assert "detail" not in compact["events"][0]
    assert "detail" in expanded["events"][0]


def test_page_digest_detects_tampering(tmp_path: Path):
    run_id = _seed(tmp_path)
    projection = DurableConsoleEventProjection(tmp_path)
    page = projection.page(run_id, limit=100)
    assert projection.verify_page(page)
    page["events"][0]["summary"] = "forged"
    assert not projection.verify_page(page)


def test_console_snapshot_consumes_projection(tmp_path: Path):
    run_id = _seed(tmp_path)
    snapshot = AgentOperationsConsoleViewModel(tmp_path).build(run_id)
    assert snapshot["timeline"]["projection_version"] == "5.2"
    assert snapshot["timeline"]["chain"]["ok"] is True
    assert snapshot["timeline"]["event_count"] >= 6


def test_new_source_event_appends_without_rewriting_existing_projection(tmp_path: Path):
    run_id = _seed(tmp_path)
    projection = DurableConsoleEventProjection(tmp_path)
    before = projection.page(run_id, limit=100, view="expanded")
    AgentRunStore(tmp_path).append_event(run_id, "agent.tool.completed", {"tool_id": "workspace.read_range", "status": "succeeded"})
    after = projection.page(run_id, limit=100, view="expanded")
    assert after["projection_event_count"] == before["projection_event_count"] + 1
    assert [e["projection_digest"] for e in after["events"][: before["count"]]] == [e["projection_digest"] for e in before["events"]]


def test_unknown_run_fails_closed(tmp_path: Path):
    with pytest.raises(KeyError, match="unknown agent run"):
        DurableConsoleEventProjection(tmp_path).page("missing")

from pathlib import Path

import pytest

from app.kernel.agents.run_store import AgentRunStore
from app.kernel.operations_console import AgentOperationsConsoleViewModel


def _seed(root: Path) -> tuple[AgentRunStore, str]:
    store = AgentRunStore(root)
    run = store.create_run(
        session_id="session-51",
        objective="Repair failing parser",
        mode="agent",
        provider="ollama",
        model="qwen-test",
        request={"success_criteria": ["focused tests pass"], "context_files": ["app/parser.py"]},
        budget={"turns": 4, "tool_calls": 8},
        run_id="run-51",
    )
    run_id = run["run_id"]
    store.checkpoint(run_id, {
        "step_id": "step-2",
        "plan": {"version": 2, "status": "active", "active_step_id": "step-2", "steps": [{"id": "step-1", "status": "done"}, {"id": "step-2", "status": "active"}]},
        "worktree": {"status": "active", "path": str(root / ".beast/worktrees/run-51"), "base_commit": "abc", "changed_files": ["app/parser.py"]},
        "verification": {"status": "failed"},
        "sourceplan": {"status": "not_created"},
    })
    store.append_event(run_id, "agent.context.packet.built", {"context_manifest": {"status": "available", "items": [{"path": "app/parser.py", "status": "accepted", "content_hash": "sha256:x"}]}})
    store.append_event(run_id, "agent.tool.completed", {"tool_id": "workspace.read_range", "status": "succeeded", "receipt_digest": "sha256:tool"})
    store.append_event(run_id, "agent.verify.completed", {"status": "failed", "command": "pytest -q", "evidence_digest": "sha256:test"})
    store.create_approval(run_id, {"approval_id": "approval-51", "tool_id": "workspace.apply_patch"})
    return store, run_id


def test_builds_complete_canonical_snapshot(tmp_path: Path):
    _, run_id = _seed(tmp_path)
    snapshot = AgentOperationsConsoleViewModel(tmp_path).build(run_id)
    assert snapshot["beast_object_type"] == "beast_agent_operations_console_snapshot"
    assert snapshot["run"]["objective"] == "Repair failing parser"
    assert snapshot["plan"]["active_step_id"] == "step-2"
    assert snapshot["context_manifest"]["item_count"] == 1
    assert snapshot["tool_activity"]["count"] == 1
    assert snapshot["approvals"]["pending"] == 1
    assert snapshot["worktree"]["changed_files"] == ["app/parser.py"]
    assert snapshot["verification"]["status"] == "failed"
    assert snapshot["budget"]["limits"]["turns"] == 4
    assert snapshot["provider_route"]["provider"] == "ollama"
    assert snapshot["authority"] == "console_projection_read_only"
    assert snapshot["grants_execution_authority"] is False


def test_snapshot_is_deterministic_across_fresh_view_model_instance(tmp_path: Path):
    _, run_id = _seed(tmp_path)
    first = AgentOperationsConsoleViewModel(tmp_path).build(run_id)
    second = AgentOperationsConsoleViewModel(tmp_path).build(run_id)
    assert first == second
    assert first["snapshot_digest"] == second["snapshot_digest"]


def test_snapshot_digest_detects_tampering(tmp_path: Path):
    _, run_id = _seed(tmp_path)
    model = AgentOperationsConsoleViewModel(tmp_path)
    snapshot = model.build(run_id)
    assert model.verify(snapshot)
    snapshot["run"]["objective"] = "widened mission"
    assert not model.verify(snapshot)


def test_unknown_run_fails_closed(tmp_path: Path):
    with pytest.raises(KeyError, match="unknown agent run"):
        AgentOperationsConsoleViewModel(tmp_path).build("missing")


def test_context_suggestions_are_not_implicitly_accepted(tmp_path: Path):
    store = AgentRunStore(tmp_path)
    run = store.create_run(session_id="s", objective="x", run_id="run-suggested")
    store.append_event(run["run_id"], "agent.context.packet.built", {"context_manifest": {"items": [{"path": "a.py", "status": "suggested_unselected"}]}})
    snapshot = AgentOperationsConsoleViewModel(tmp_path).build(run["run_id"])
    assert snapshot["context_manifest"]["accepted_count"] == 0
    assert snapshot["context_manifest"]["items"][0]["status"] == "suggested_unselected"


def test_timeline_chain_is_reported_and_verified(tmp_path: Path):
    _, run_id = _seed(tmp_path)
    snapshot = AgentOperationsConsoleViewModel(tmp_path).build(run_id)
    assert snapshot["timeline"]["chain"]["ok"] is True
    assert snapshot["timeline"]["chain"]["head_matches"] is True


def test_no_hidden_conversation_reconstruction_is_claimed(tmp_path: Path):
    _, run_id = _seed(tmp_path)
    snapshot = AgentOperationsConsoleViewModel(tmp_path).build(run_id)
    assert snapshot["recovery"]["restart_safe"] is True
    assert snapshot["recovery"]["reconstruction_from_conversation_required"] is False


def test_sourceplan_and_promotion_authority_remain_separate(tmp_path: Path):
    store, run_id = _seed(tmp_path)
    run = store.get_run(run_id)
    checkpoint = dict(run["checkpoint"])
    checkpoint["sourceplan"] = {"status": "ready", "sourceplan_id": "sp-1", "digest": "sha256:sp", "promotion_ready": True, "promotion_authorized": False}
    store.checkpoint(run_id, checkpoint)
    snapshot = AgentOperationsConsoleViewModel(tmp_path).build(run_id)
    assert snapshot["sourceplan"]["promotion_ready"] is True
    assert snapshot["sourceplan"]["promotion_authorized"] is False
    assert snapshot["grants_promotion_authority"] is False

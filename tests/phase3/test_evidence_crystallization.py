from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from app.kernel.agents.run_engine import AgentRunEngine
from app.kernel.evidence.evidence_builder import EvidenceBuilder
from app.kernel.evidence.evidence_store import EvidenceStore


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, check=True)
    return result.stdout.strip()


def _promoted_run(tmp_path: Path) -> tuple[Path, str]:
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init")
    _git(root, "config", "user.email", "test@example.com")
    _git(root, "config", "user.name", "Test")
    (root / "app.py").write_text("VALUE = 1\n", encoding="utf-8")
    _git(root, "add", ".")
    _git(root, "commit", "-m", "base")
    engine = AgentRunEngine(root)
    run = engine.create_run(session_id="s1", objective="Change VALUE safely", mode="agent")
    run_id = run["run_id"]
    # Build a self-contained valid event history before binding final checkpoint.
    engine.emit(run_id, "agent.tool.completed", {"tool_id": "workspace.read_range", "status": "completed"})
    engine.emit(run_id, "agent.verification.passed", {"returncode": 0, "mutation_epoch": 1})
    chain = engine.store.verify_chain(run_id)
    assert chain["ok"] and chain["head_matches"]
    engine.merge_checkpoint(run_id, {
        "planner": {"turn": 3, "repair_cycles": 0},
        "verification": {"ok": True, "stale": False, "mutation_epoch": 1, "command": ["python", "-m", "pytest"]},
        "sourceplan": {"plan_id": "plan-1", "status": "draft", "operations": [{"kind": "replace", "path": "app.py"}]},
        "worktree_task_id": "task-1",
        "worktree_branch": "beast/test",
        "worktree_base_commit": _git(root, "rev-parse", "HEAD~0"),
        "worktree_mutation_epoch": 1,
        "promotion": {"status": "promoted", "eligible": True, "receipt_id": "receipt-1", "receipt_digest": "sha256:receipt"},
        "commit_candidate": {
            "candidate_id": "candidate-1", "commit": _git(root, "rev-parse", "HEAD"), "approval_id": "approval-1",
            "approved_by": "Human Operator", "receipt_digest": "sha256:receipt", "applied_to_operator_workspace": False,
        },
    })
    return root, run_id


def test_crystallizes_promoted_run_and_verifies(tmp_path: Path):
    root, run_id = _promoted_run(tmp_path)
    builder = EvidenceBuilder(root)
    evidence = builder.crystallize(run_id)
    assert evidence["beast_object_type"] == "beast_evidence_crystal"
    assert evidence["reuse_constraints"]["fresh_verification_required"] is True
    result = builder.verify(evidence["evidence_id"])
    assert result["ok"] is True
    assert result["digest_ok"] is True
    assert result["event_chain"]["head_matches"] is True


def test_crystallization_is_idempotent_per_run(tmp_path: Path):
    root, run_id = _promoted_run(tmp_path)
    builder = EvidenceBuilder(root)
    first = builder.crystallize(run_id)
    second = builder.crystallize(run_id)
    assert second["evidence_id"] == first["evidence_id"]
    assert second["evidence_digest"] == first["evidence_digest"]


def test_rejects_unpromoted_run(tmp_path: Path):
    root = tmp_path / "repo"
    root.mkdir()
    engine = AgentRunEngine(root)
    run = engine.create_run(session_id="s", objective="not promoted")
    with pytest.raises(PermissionError):
        EvidenceBuilder(root).crystallize(run["run_id"])


def test_tampered_object_fails_verification(tmp_path: Path):
    root, run_id = _promoted_run(tmp_path)
    builder = EvidenceBuilder(root)
    evidence = builder.crystallize(run_id)
    store = EvidenceStore(root)
    import sqlite3
    with sqlite3.connect(store.db_path) as connection:
        path = Path(connection.execute("SELECT object_path FROM evidence_objects WHERE evidence_id=?", (evidence["evidence_id"],)).fetchone()[0])
    value = json.loads(path.read_text())
    value["task"]["objective"] = "tampered"
    path.write_text(json.dumps(value), encoding="utf-8")
    result = builder.verify(evidence["evidence_id"])
    assert result["ok"] is False
    assert result["digest_ok"] is False

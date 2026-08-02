from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from app.kernel.agents.promotion_engine import PromotionEngine
from app.kernel.agents.run_engine import AgentRunEngine


def git(root: Path, *args: str) -> str:
    result = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, check=True)
    return result.stdout.strip()


def prepared_run(tmp_path: Path) -> tuple[PromotionEngine, str, Path]:
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init")
    git(root, "config", "user.name", "Test Operator")
    git(root, "config", "user.email", "test@example.invalid")
    (root / "value.py").write_text("VALUE = 1\n", encoding="utf-8")
    git(root, "add", "value.py")
    git(root, "commit", "-m", "base")
    base = git(root, "rev-parse", "HEAD")

    worktree = tmp_path / "worktree"
    git(root, "worktree", "add", "-b", "beast/test-promotion", str(worktree), base)
    (worktree / "value.py").write_text("VALUE = 2\n", encoding="utf-8")

    engine = AgentRunEngine(root)
    run = engine.create_run(session_id="session-test", objective="Change VALUE", mode="agent")
    run_id = str(run["run_id"])
    engine.emit(run_id, "agent.worktree.mutated", {"mutation_epoch": 1})
    engine.emit(run_id, "agent.verification.passed", {"mutation_epoch": 1, "returncode": 0})
    engine.merge_checkpoint(run_id, {
        "worktree_task_id": "task-test",
        "worktree_root": str(worktree),
        "worktree_branch": "beast/test-promotion",
        "worktree_base_commit": base,
        "worktree_mutation_epoch": 1,
        "verification": {"ok": True, "stale": False, "mutation_epoch": 1, "returncode": 0},
        "sourceplan": {"plan_id": "plan-test", "status": "draft", "requires_operator_translation": False},
        "planner": {"status": "completed", "turn": 4, "repair_cycles": 1, "max_repair_cycles": 3},
    })
    return PromotionEngine(root), run_id, worktree


def test_evaluate_creates_digest_bound_pending_approval(tmp_path: Path):
    promotion, run_id, _ = prepared_run(tmp_path)
    result = promotion.evaluate(run_id, requested_by="Byron")
    assert result["eligible"] is True
    receipt = result["receipt"]
    approval = result["approval"]
    assert len(receipt["receipt_digest"]) == 64
    assert approval["status"] == "pending"
    assert approval["request"]["receipt_digest"] == receipt["receipt_digest"]
    assert approval["request"]["requires_human_operator"] is True


def test_commit_candidate_requires_human_identity_and_does_not_touch_main(tmp_path: Path):
    promotion, run_id, worktree = prepared_run(tmp_path)
    evaluated = promotion.evaluate(run_id)
    approval_id = evaluated["approval"]["approval_id"]
    promotion.engine.store.resolve_approval(run_id, approval_id, {"approved": True})
    with pytest.raises(PermissionError, match="identify the human operator"):
        promotion.promote(run_id, approval_id=approval_id)

    # Re-resolve with identity, then create the candidate.
    promotion.engine.store.resolve_approval(run_id, approval_id, {"approved": True, "resolved_by": "Byron Bunt"})
    result = promotion.promote(run_id, approval_id=approval_id, commit_message="Promote verified VALUE repair")
    candidate = result["candidate"]
    assert candidate["status"] == "commit_candidate"
    assert candidate["approved_by"] == "Byron Bunt"
    assert candidate["applied_to_operator_workspace"] is False
    assert git(worktree, "rev-parse", "HEAD") == candidate["commit"]
    assert (promotion.workspace_root / "value.py").read_text(encoding="utf-8") == "VALUE = 1\n"


def test_receipt_becomes_stale_after_mutation_epoch_changes(tmp_path: Path):
    promotion, run_id, _ = prepared_run(tmp_path)
    evaluated = promotion.evaluate(run_id)
    approval_id = evaluated["approval"]["approval_id"]
    promotion.engine.store.resolve_approval(run_id, approval_id, {"approved": True, "resolved_by": "Operator"})
    promotion.engine.merge_checkpoint(run_id, {
        **(promotion.engine.store.get_run(run_id)["checkpoint"]),
        "worktree_mutation_epoch": 2,
        "verification": {"ok": False, "stale": True, "mutation_epoch": 1},
    })
    with pytest.raises(PermissionError, match="no longer eligible|stale"):
        promotion.promote(run_id, approval_id=approval_id)


def test_approval_from_another_receipt_is_rejected(tmp_path: Path):
    promotion, run_id, _ = prepared_run(tmp_path)
    first = promotion.evaluate(run_id)
    second = promotion.evaluate(run_id)
    first_id = first["approval"]["approval_id"]
    promotion.engine.store.resolve_approval(run_id, first_id, {"approved": True, "resolved_by": "Operator"})
    with pytest.raises(PermissionError, match="not bound to the current promotion receipt"):
        promotion.promote(run_id, approval_id=first_id)


def test_blocked_policy_does_not_create_approval(tmp_path: Path):
    promotion, run_id, _ = prepared_run(tmp_path)
    run = promotion.engine.store.get_run(run_id)
    checkpoint = dict(run["checkpoint"])
    checkpoint["sourceplan"] = {"plan_id": "plan-test", "status": "draft", "requires_operator_translation": True}
    promotion.engine.checkpoint(run_id, checkpoint)
    result = promotion.evaluate(run_id)
    assert result["eligible"] is False
    assert result["approval"] is None
    failed = {p["policy_id"] for p in result["receipt"]["policies"] if not p["passed"]}
    assert "NO_OPERATOR_TRANSLATION_REQUIRED" in failed


def test_remote_promotion_creates_target_side_commit_candidate(tmp_path: Path, monkeypatch):
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init")
    engine = AgentRunEngine(root)
    run = engine.create_run(session_id="session-test", objective="Remote change", mode="agent", run_id="remote-promotion")
    run_id = str(run["run_id"])
    engine.emit(run_id, "agent.worktree.mutated", {"mutation_epoch": 1})
    engine.emit(run_id, "agent.verification.passed", {"mutation_epoch": 1, "returncode": 0})
    target_payload = {"kind": "ssh", "host": "devbox", "remoteRoot": "/repo"}
    engine.merge_checkpoint(run_id, {
        "worktree_task_id": "remote-task",
        "worktree_root": "/repo/.beast/agent-worktrees/remote-promotion",
        "worktree_branch": "beast-agent-remote-promotion",
        "worktree_base_commit": "abc123",
        "worktree_mutation_epoch": 1,
        "worktree_remote": True,
        "worktree_execution_target": "ssh",
        "worktree_execution_target_payload": target_payload,
        "verification": {"ok": True, "stale": False, "mutation_epoch": 1, "returncode": 0, "target_execution": "remote_ssh"},
        "sourceplan": {
            "plan_id": "remote-plan",
            "status": "draft",
            "requires_operator_translation": True,
            "execution_target": "ssh",
            "execution_target_payload": target_payload,
            "target_execution": "remote_ssh",
        },
        "planner": {"status": "completed", "turn": 4, "repair_cycles": 1, "max_repair_cycles": 3},
    })
    promotion = PromotionEngine(root)
    calls = []

    def fake_remote_shell(self, run_id_arg, checkpoint, script, *, timeout=30.0, output_limit=512000):
        calls.append(script)
        if "BEAST_FINAL_APPLY_BEFORE" in script:
            return {
                "ok": True,
                "returncode": 0,
                "stdout": (
                    "BEAST_FINAL_APPLY_BEFORE\n"
                    f"{'a' * 40}\n"
                    "BEAST_FINAL_APPLY_AFTER\n"
                    f"{'f' * 40}\n"
                    "BEAST_FINAL_APPLY_BRANCH\n"
                    "main\n"
                    "BEAST_FINAL_APPLY_ROLLBACK\n"
                    "refs/beast/rollback/remote-promotion-12345\n"
                ),
                "stderr": "",
                "target_execution": "remote_ssh",
            }
        if "rev-parse --git-dir" in script:
            return {"ok": True, "returncode": 0, "stdout": ".git\n", "stderr": "", "target_execution": "remote_ssh"}
        if "BEAST_REMOTE_PROMOTION_STATUS" in script:
            return {
                "ok": True,
                "returncode": 0,
                "stdout": (
                    "BEAST_REMOTE_PROMOTION_STATUS\n"
                    " M value.py\n"
                    "BEAST_REMOTE_PROMOTION_HEAD\n"
                    f"{'f' * 40}\n"
                    "BEAST_REMOTE_PROMOTION_BRANCH\n"
                    "beast-agent-remote-promotion\n"
                    "BEAST_REMOTE_PROMOTION_COMMIT_OUT\n"
                    "[beast-agent-remote-promotion ffffffff] Promote remote VALUE repair\n"
                ),
                "stderr": "",
                "target_execution": "remote_ssh",
            }
        return {"ok": False, "returncode": 2, "stdout": "", "stderr": f"unexpected script: {script}", "target_execution": "remote_ssh"}

    monkeypatch.setattr(PromotionEngine, "_run_remote_shell", fake_remote_shell)
    evaluated = promotion.evaluate(run_id, requested_by="Byron")
    assert evaluated["eligible"] is True
    approval_id = evaluated["approval"]["approval_id"]
    promotion.engine.store.resolve_approval(run_id, approval_id, {"approved": True, "resolved_by": "Byron Bunt"})
    result = promotion.promote(run_id, approval_id=approval_id, commit_message="Promote remote VALUE repair")
    candidate = result["candidate"]
    assert candidate["status"] == "remote_commit_candidate"
    assert candidate["target_execution"] == "remote_ssh"
    assert candidate["commit"] == "f" * 40
    assert candidate["approved_by"] == "Byron Bunt"
    assert result["receipt"]["status"] == "remote_promoted"
    assert any("git add --all" in call for call in calls)

    final_eval = promotion.evaluate_final_apply(run_id, requested_by="Byron")
    assert final_eval["eligible"] is True
    final_approval_id = final_eval["approval"]["approval_id"]
    promotion.engine.store.resolve_approval(run_id, final_approval_id, {"approved": True, "resolved_by": "Byron Bunt"})
    finalized = promotion.finalize(run_id, approval_id=final_approval_id, target_branch="main")
    final_apply = finalized["final_apply"]
    assert final_apply["status"] == "finalized"
    assert final_apply["applied_to_remote_target"] is True
    assert final_apply["target_branch"] == "main"
    assert final_apply["before"] == "a" * 40
    assert final_apply["after"] == "f" * 40
    assert final_apply["rollback_ref"] == "refs/beast/rollback/remote-promotion-12345"
    assert finalized["candidate"]["status"] == "remote_finalized"
    assert any("git merge --ff-only" in call for call in calls)

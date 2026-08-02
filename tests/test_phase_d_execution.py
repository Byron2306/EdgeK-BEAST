from app.kernel.agents.phase_d_execution import GovernedForgeExecutor, PhaseDCritic, PhaseDVerifier


def action_ir(new="return amount / 100"):
    return {"kind": "beast.action_intent.v1", "actions": [{
        "type": "replace_anchor",
        "target": {"path": "pricing.py"},
        "old": "return amount - percent",
        "new": new,
    }]}


def test_forge_executor_fails_closed_without_authority():
    result = GovernedForgeExecutor().execute(
        action_ir(), approval_id="", worktree_task_id="", worktree_root="", approved=False,
    )
    assert result["status"] == "blocked"
    assert result["mutation_applied"] is False


def test_forge_executor_requires_residual_resolution():
    result = GovernedForgeExecutor(lambda *_: {}).execute(
        action_ir("<RESIDUAL>"), approval_id="approval-1", worktree_task_id="wt-1",
        worktree_root="/tmp/worktree", approved=True,
    )
    assert result["status"] == "blocked"
    assert "residual" in result["reason"]


def test_phase_d_verifier_and_critic_require_fresh_scoped_proof():
    executor = GovernedForgeExecutor(lambda *_: {"ok": True}).execute(
        action_ir(), approval_id="approval-1", worktree_task_id="wt-1",
        worktree_root="/tmp/worktree", approved=True,
    )
    verification = PhaseDVerifier().verify([{"name": "targeted_test", "passed": True}], mutation_epoch=2, verified_epoch=2)
    critique = PhaseDCritic().review(executor, verification, allowed_paths=["pricing.py"])
    assert verification["passed"] is True
    assert critique["passed"] is True

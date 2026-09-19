from types import SimpleNamespace

from app.kernel.agents.execution_architecture import current_epoch_receipt, execution_authority_contract, execution_gate


def test_execution_contract_keeps_intent_and_authority_separate():
    contract = execution_authority_contract()
    assert contract["authorities"]["planner_output"] == "intent_only"
    assert contract["authorities"]["crystal_reuse"] == "advisory_or_compute_reuse_only"
    assert contract["authorities"]["mutation"] == "worktree_tools"
    assert contract["authorities"]["verification"] == "worktree.verify"


def test_mutation_requires_live_bound_worktree():
    decision = SimpleNamespace(tool_id="worktree.replace_exact", approval_id="old-or-new")
    denied = execution_gate(decision, SimpleNamespace(worktree_root=""))
    allowed = execution_gate(decision, SimpleNamespace(worktree_root="/tmp/live-worktree"))
    assert denied["allowed"] is False
    assert denied["reason"] == "isolated_worktree_required"
    assert allowed["allowed"] is True
    assert allowed["authority_source"] == "live_tool_context"
    assert allowed["inherited_authority_accepted"] is False


def test_verification_requires_same_live_worktree_boundary():
    decision = SimpleNamespace(tool_id="worktree.verify", approval_id="")
    assert execution_gate(decision, SimpleNamespace(worktree_root=""))["allowed"] is False
    gate = execution_gate(decision, SimpleNamespace(worktree_root="/tmp/wt"))
    assert gate["allowed"] is True
    assert gate["reason"] == "fresh_worktree_verification"


def test_current_epoch_receipt_rejects_stale_or_prior_verification():
    stale = current_epoch_receipt({
        "worktree_mutation_epoch": 3,
        "verification": {"ok": True, "stale": False, "mutation_epoch": 2},
    })
    assert stale["current"] is False
    current = current_epoch_receipt({
        "worktree_mutation_epoch": 3,
        "verification": {"ok": True, "stale": False, "mutation_epoch": 3, "execution_target": "local"},
    })
    assert current["current"] is True
    assert current["authority"] == "evidence_only_no_future_mutation_authority"

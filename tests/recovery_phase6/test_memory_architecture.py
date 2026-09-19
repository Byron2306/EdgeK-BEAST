from types import SimpleNamespace

from app.kernel.agents.memory_architecture import (
    build_memory_context,
    memory_authority_contract,
)


def test_memory_roles_have_one_owner_and_non_mutating_authority():
    contract = memory_authority_contract()
    assert set(contract["roles"]) == {"working", "episodic", "durable", "evidence", "forensic"}
    assert all(role["owner"] for role in contract["roles"].values())
    assert contract["prohibited_implicit_promotions"]["exact_source"] == "workspace.read_range"
    assert contract["prohibited_implicit_promotions"]["mutation"] == "worktree_tools"


def test_retrieved_memory_cannot_silently_become_source_or_mutation_authority():
    run = {"run_id": "phase6"}
    state = SimpleNamespace(
        run_id="phase6",
        observations=[{"tool_id": "workspace.read_range", "status": "completed", "evidence_digest": "sha256:x"}],
    )
    packet = build_memory_context(
        run,
        state,
        episodic=[{"text": "old source bytes"}],
        durable=[{"text": "promoted pattern"}],
        evidence=[{"receipt": "evidence:1"}],
        forensic=[{"failure": "old failure"}],
    )

    for role in ("episodic", "durable", "evidence", "forensic"):
        assert packet[role][0]["grants_mutation_authority"] is False
        assert packet[role][0]["grants_exact_source_authority"] is False
    assert packet["working"]["authority"] == "advisory_continuity_only"


def test_memory_context_is_bounded_and_deterministic():
    run = {"run_id": "phase6"}
    state = SimpleNamespace(run_id="phase6", observations=[])
    items = [{"id": i} for i in range(20)]
    one = build_memory_context(run, state, episodic=items, per_role_limit=3)
    two = build_memory_context(run, state, episodic=items, per_role_limit=3)
    assert len(one["episodic"]) == 3
    assert one["context_digest"] == two["context_digest"]

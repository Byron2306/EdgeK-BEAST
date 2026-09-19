from types import SimpleNamespace

from app.kernel.agents.reuse_runtime import AgentReuseRuntime, render_reuse_proposal


class Lattice:
    def __init__(self, payload):
        self.payload = payload

    def lookup(self, plan, scorecard=None, limit=3):
        return dict(self.payload)


def runtime(payload):
    item = AgentReuseRuntime.__new__(AgentReuseRuntime)
    item.lattice = Lattice(payload)
    return item


def test_strong_verified_match_can_propose_replay_but_never_source_or_mutation_authority():
    item = runtime({
        "match_strength": 0.94,
        "reuse_mode": "sourceplan_replay_candidate",
        "best_match": {"cell_id": "c1", "verification_ok": True, "evidence_hash": "sha256:e"},
        "blockers": [],
        "advisory_only": True,
    })
    packet = item.propose({"run_id": "r1", "objective": "repair planner"}, SimpleNamespace(run_id="r1"))
    assert packet["allowed_use"] == "strategy_and_replay_candidate"
    assert packet["compute_savings"]["may_reduce_planner_inference"] is True
    assert packet["compute_savings"]["may_skip_fresh_source_read"] is False
    assert packet["compute_savings"]["may_skip_fresh_verification"] is False
    assert packet["authority"]["grants_mutation_authority"] is False
    assert packet["authority"]["grants_exact_source_authority"] is False


def test_unverified_or_blocked_match_cannot_become_replay_candidate():
    item = runtime({
        "match_strength": 0.96,
        "reuse_mode": "sourceplan_replay_candidate",
        "best_match": {"cell_id": "c2", "verification_ok": False},
        "blockers": ["repo_fingerprint_changed"],
        "advisory_only": True,
    })
    packet = item.propose({"run_id": "r2", "objective": "repair planner"}, SimpleNamespace(run_id="r2"))
    assert packet["allowed_use"] == "strategy_scaffold"
    assert packet["staleness_or_compatibility_blockers"] == ["repo_fingerprint_changed"]


def test_compaction_preserves_reuse_authority_membrane():
    item = runtime({
        "match_strength": 0.9,
        "reuse_mode": "sourceplan_replay_candidate",
        "best_match": {"cell_id": "c3", "verification_ok": True},
        "matches": [{"blob": "x" * 5000}],
        "blockers": [],
        "advisory_only": True,
    })
    packet = item.propose({"run_id": "r3", "objective": "x"}, SimpleNamespace(run_id="r3"))
    rendered = render_reuse_proposal(packet, char_limit=700)
    assert "CRYSTAL_REUSE:" in rendered
    assert "grants_mutation_authority" in rendered
    assert "may_skip_fresh_source_read" in rendered

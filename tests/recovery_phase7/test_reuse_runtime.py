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


class FeedbackLattice(Lattice):
    def __init__(self):
        super().__init__({"match_strength": 0.0, "best_match": {}, "blockers": [], "advisory_only": True})
        self.recorded = []

    def record_from_packet(self, packet):
        self.recorded.append(packet)
        return {"cell_id": "fresh-cell", "verification_ok": packet["verification"]["ok"]}


def test_fresh_verification_strengthens_lattice_only_with_fresh_evidence():
    item = AgentReuseRuntime.__new__(AgentReuseRuntime)
    item.lattice = FeedbackLattice()
    state = SimpleNamespace(run_id="r4")
    feedback = item.feedback(
        {"run_id": "r4", "objective": "repair", "provider": "ollama"},
        state,
        {"status": "completed", "evidence_digest": "sha256:fresh", "result": {"returncode": 0}},
    )
    assert feedback["outcome"] == "fresh_verification_strengthened_lattice"
    assert item.lattice.recorded[0]["verification"]["fresh"] is True
    assert item.lattice.recorded[0]["evidence_hash"] == "sha256:fresh"
    assert feedback["authority_escalated"] is False


def test_failed_verification_never_promotes_crystal():
    item = AgentReuseRuntime.__new__(AgentReuseRuntime)
    item.lattice = FeedbackLattice()
    feedback = item.feedback(
        {"run_id": "r5", "objective": "repair"},
        SimpleNamespace(run_id="r5"),
        {"status": "failed", "evidence_digest": "sha256:bad", "result": {"returncode": 1}},
    )
    assert feedback["outcome"] == "verification_failure_blocks_promotion"
    assert feedback["promotion_written"] is False
    assert item.lattice.recorded == []

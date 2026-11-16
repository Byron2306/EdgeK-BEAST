"""Compute Governor spine (PREC): one arbiter, typed inputs, receipts, default-off enforcement."""

from __future__ import annotations

import pytest

from app.kernel.compute.adaptive_router import AdaptiveRouter
from app.kernel.governance import governor_spine as gs
from app.kernel.governance.governor_spine import (
    ADMIT,
    DEFER,
    ESCALATE,
    REFUSE,
    REVALIDATE,
    ComputeGovernorSpine,
    Episode,
    GovernorReceiptLog,
    Proposal,
)
from app.kernel.governance.psi_governor import PsiSample


def crystal_route(crystal_id="coding-crystal:a", similarity=0.97, compatible=True):
    fp = {"opcode_catalog_digest": "o", "crystal_digest": "c", "source_envelope_digest": "s"}
    req = dict(fp) if compatible else {**fp, "crystal_digest": "other"}
    return AdaptiveRouter().route(similarity=similarity, crystal_id=crystal_id, crystal_fingerprints=fp,
                                  request_fingerprints=req).to_dict()


def spine(tmp_path, **kw):
    kw.setdefault("receipts", GovernorReceiptLog(tmp_path / "receipts.jsonl"))
    kw.setdefault("enforce", True)
    return ComputeGovernorSpine(**kw)


def ep(**kw):
    kw.setdefault("run_id", "run-1")
    kw.setdefault("limits", {"tokens_total": 10_000, "cloud_calls": 5})
    return Episode(**kw)


CASCADE_OK = {"passed": True}


class FakeLattice:
    def __init__(self, nodes):
        self.nodes_ = nodes

    def node(self, node_id):
        if node_id not in self.nodes_:
            raise LookupError(node_id)
        return self.nodes_[node_id]


# --- admit / refuse matrix -------------------------------------------------------------------------

@pytest.mark.parametrize("proposal,expected", [
    (Proposal(kind="crystal", crystal_id="coding-crystal:a", route_decision=None), REVALIDATE),
    (Proposal(kind="cloud", provider="nvidia", quality_cascade=CASCADE_OK), ADMIT),
    (Proposal(kind="deterministic_tool", tool_id="ruff"), ADMIT),
    (Proposal(kind="command", command="rm -rf /", safety={"decision": "block"}), REFUSE),
    (Proposal(kind="command", command="make x", safety={"decision": "require_approval"}), ESCALATE),
    (Proposal(kind="command", command="make x", safety={"decision": "require_approval"}, approved=True), ADMIT),
    (Proposal(kind="command", command="ls", safety={"decision": "allow"}), ADMIT),
    (Proposal(kind="command", command="ls"), REFUSE),  # no safety classification: fail closed
    (Proposal(kind="deterministic_tool", tool_id="x", mcp_tool="vault.read"), REFUSE),
    (Proposal(kind="teleport"), REFUSE),
])
def test_admit_refuse_matrix(tmp_path, proposal, expected):
    decision = spine(tmp_path, mcp_allowed=frozenset({"fs.read"})).admit(ep(), proposal)
    assert decision.outcome == expected, decision.reasons


def test_crystal_with_valid_route_admits_and_mcp_allowed_tool_admits(tmp_path):
    g = spine(tmp_path, mcp_allowed=frozenset({"fs.read"}))
    assert g.admit(ep(), Proposal(kind="crystal", crystal_id="coding-crystal:a",
                                  route_decision=crystal_route())).outcome == ADMIT
    assert g.admit(ep(), Proposal(kind="deterministic_tool", tool_id="x", mcp_tool="fs.read")).outcome == ADMIT


def test_forged_route_decision_and_fingerprint_mismatch_never_admit(tmp_path):
    g = spine(tmp_path)
    forged = dict(crystal_route(), route="crystal_replay", crystal_id="coding-crystal:b")
    assert g.admit(ep(), Proposal(kind="crystal", crystal_id="coding-crystal:b",
                                  route_decision=forged)).outcome == REVALIDATE
    mismatch = crystal_route(compatible=False)
    assert g.admit(ep(), Proposal(kind="crystal", crystal_id="coding-crystal:a",
                                  route_decision=mismatch)).outcome != ADMIT


# --- ambiguity never suppresses ------------------------------------------------------------------

def test_ambiguity_escalates_never_refuses(tmp_path):
    g = spine(tmp_path)
    for proposal in (Proposal(kind="cloud", provider="p", quality_cascade=CASCADE_OK, ambiguous=True),
                     Proposal(kind="crystal", crystal_id="coding-crystal:a", route_decision=crystal_route(similarity=0.85))):
        decision = g.admit(ep(), proposal)
        assert decision.outcome == ESCALATE
        assert decision.gate_decision() == "escalate"


# --- pressure can only shrink the budget ---------------------------------------------------------

def test_pressure_cannot_deny_on_its_own(tmp_path):
    full = {"memory": PsiSample("memory", some_avg10=90.0, full_avg10=90.0)}
    g = spine(tmp_path)
    decision = g.admit(ep(psi_samples=full, limits={"tokens_total": 10_000}),
                       Proposal(kind="cloud", provider="p", quality_cascade=CASCADE_OK, estimate={"tokens_total": 100}))
    assert decision.outcome == ADMIT
    assert 0 < decision.pressure_factor < 1
    assert decision.effective_limits["tokens_total"] < 10_000
    # Pressure plus a large estimate can only defer, never refuse.
    big = g.admit(ep(psi_samples=full, limits={"tokens_total": 10_000}),
                  Proposal(kind="cloud", provider="p", quality_cascade=CASCADE_OK, estimate={"tokens_total": 9_000}))
    assert big.outcome == DEFER
    # Protected lanes keep the full budget.
    op = g.admit(ep(psi_samples=full), Proposal(kind="deterministic_tool", tool_id="t", lane="operator"))
    assert op.pressure_factor == 1.0


# --- a proposal cannot run without admit ---------------------------------------------------------

def test_proposal_cannot_run_without_admit(tmp_path):
    g = spine(tmp_path)
    ran = []
    refused = Proposal(kind="command", command="rm -rf /", safety={"decision": "block"})
    with pytest.raises(PermissionError):
        g.execute(ep(), refused, lambda: ran.append(1))
    assert ran == []
    ok = Proposal(kind="deterministic_tool", tool_id="ruff")
    decision = g.admit(ep(), ok)
    other = Proposal(kind="deterministic_tool", tool_id="rm")
    with pytest.raises(PermissionError):
        g.run_admitted(decision, other, lambda: ran.append(2))
    assert g.run_admitted(decision, ok, lambda: "done") == "done"
    with pytest.raises(PermissionError):  # an admit token is single use
        g.run_admitted(decision, ok, lambda: "again")


def test_shadow_mode_records_but_never_blocks(tmp_path):
    g = spine(tmp_path, enforce=False)
    refused = Proposal(kind="command", command="rm -rf /", safety={"decision": "block"})
    assert g.execute(ep(), refused, lambda: "ran") == "ran"
    assert g.receipts.verify()["valid"] and g.receipts.verify()["count"] == 1


# --- lattice ------------------------------------------------------------------------------------

def test_failed_lattice_part_refuses_composite(tmp_path):
    lattice = FakeLattice({
        "coding-crystal:L": {"status": "admitted", "component_ids": ["coding-crystal:x", "coding-crystal:y"]},
        "coding-crystal:x": {"status": "admitted", "component_ids": []},
        "coding-crystal:y": {"status": "demoted", "component_ids": []},
    })
    g = spine(tmp_path, lattice=lattice)
    decision = g.admit(ep(), Proposal(kind="crystal", crystal_id="coding-crystal:L",
                                      route_decision=crystal_route("coding-crystal:L")))
    assert decision.outcome == REFUSE
    assert "lattice_component_not_admitted:coding-crystal:y" in decision.reasons
    lattice.nodes_["coding-crystal:y"]["status"] = "admitted"
    assert g.admit(ep(), Proposal(kind="crystal", crystal_id="coding-crystal:L",
                                  route_decision=crystal_route("coding-crystal:L"))).outcome == ADMIT


def test_composite_without_lattice_revalidates(tmp_path):
    decision = spine(tmp_path).admit(ep(), Proposal(kind="crystal", crystal_id="coding-crystal:L",
                                                     component_ids=("a", "b"),
                                                     route_decision=crystal_route("coding-crystal:L")))
    assert decision.outcome == REVALIDATE


# --- budget -----------------------------------------------------------------------------------

def test_budget_exhaustion_defers(tmp_path):
    g = spine(tmp_path)
    used = ep(run_budget_used={"tokens_total": 9_950}, limits={"tokens_total": 10_000})
    decision = g.admit(used, Proposal(kind="deterministic_tool", tool_id="t", estimate={"tokens_total": 100}))
    assert decision.outcome == DEFER
    assert "budget_exhausted:tokens_total" in decision.reasons
    session = ep(session_used={"requests": 5}, limits={"cloud_calls": 5})
    assert g.admit(session, Proposal(kind="cloud", provider="p", quality_cascade=CASCADE_OK,
                                     estimate={"cloud_calls": 1})).outcome == DEFER


def test_unified_budget_merges_compute_budget_minimum(tmp_path):
    from app.kernel.compute.compute_ir import ComputeBudget

    limits = gs.unified_limits(ComputeBudget(cloud_calls=1, input_tokens=100, output_tokens=50, latency_ms=1000),
                               {"tokens_total": 10_000, "cloud_calls": 3})
    assert limits["tokens_total"] == 150 and limits["cloud_calls"] == 1 and limits["wall_ms"] == 1000


def test_open_circuit_defers(tmp_path):
    g = spine(tmp_path, circuits=lambda provider: {"state": "open"})
    assert g.admit(ep(), Proposal(kind="cloud", provider="p", quality_cascade=CASCADE_OK)).outcome == DEFER


# --- quality cascade gates cloud; cost ladder ------------------------------------------------------

def test_quality_cascade_gates_cloud(tmp_path):
    g = spine(tmp_path)
    assert g.admit(ep(), Proposal(kind="cloud", provider="p")).outcome == REVALIDATE
    assert g.admit(ep(), Proposal(kind="cloud", provider="p", quality_cascade={"passed": False})).outcome == ESCALATE
    assert g.admit(ep(), Proposal(kind="cloud", provider="p", quality_cascade={"skipped": ""})).outcome == REVALIDATE
    assert g.admit(ep(), Proposal(kind="cloud", provider="p",
                                  quality_cascade={"skipped": "operator_override"})).outcome == ADMIT


def test_cost_ladder_prefers_cheaper_rung_then_falls_back(tmp_path):
    g = spine(tmp_path)
    cloud = Proposal(kind="cloud", provider="p", quality_cascade=CASCADE_OK)
    decision = g.admit(ep(available_rungs=("crystal", "cloud")), cloud)
    assert decision.outcome == REVALIDATE and decision.recommended_rung == "crystal"
    after = g.admit(ep(available_rungs=("crystal", "cloud"), attempted_rungs=("crystal",)), cloud)
    assert after.outcome == ADMIT and after.rung == "cloud"


# --- loop detection ----------------------------------------------------------------------------

def test_loop_detection_becomes_negative_evidence(tmp_path):
    negatives = []
    g = spine(tmp_path, negative_evidence=negatives.append, loop_threshold=3)
    p = Proposal(kind="deterministic_tool", tool_id="pytest", signature_material={"args": "-k x"})
    history = (p.signature(),) * 3
    decision = g.admit(ep(signatures=history), p)
    assert decision.outcome == REFUSE and "loop_detected" in decision.reasons
    assert negatives and negatives[0]["kind"] == "governor_loop_detected"
    assert negatives[0]["signature"] == p.signature()
    assert g.admit(ep(signatures=history[:2]), p).outcome == ADMIT


# --- false-suppression redline -----------------------------------------------------------------

def test_false_suppression_redline(tmp_path):
    """Nothing but a hard rule (L0, lattice failure, loop) may REFUSE; everything else defers/escalates/revalidates."""
    g = spine(tmp_path)
    soft_cases = [
        (ep(), Proposal(kind="cloud", provider="p", quality_cascade=CASCADE_OK, ambiguous=True)),
        (ep(), Proposal(kind="cloud", provider="p")),
        (ep(available_rungs=("crystal",)), Proposal(kind="cloud", provider="p", quality_cascade=CASCADE_OK)),
        (ep(run_budget_used={"tokens_total": 10_000}), Proposal(kind="cloud", provider="p", quality_cascade=CASCADE_OK,
                                                               estimate={"tokens_total": 1})),
        (ep(psi_samples={"cpu": PsiSample("cpu", 99.0, 99.0)}), Proposal(kind="cloud", provider="p",
                                                                         quality_cascade=CASCADE_OK)),
        (ep(), Proposal(kind="crystal", crystal_id="coding-crystal:a", route_decision=crystal_route(similarity=0.5))),
    ]
    for episode, proposal in soft_cases:
        decision = g.admit(episode, proposal)
        assert decision.outcome != REFUSE, (proposal, decision.reasons)
        assert decision.suppressed is False
    summary = g.receipts.summary()
    assert summary["false_suppression"] == 0


def test_shadow_gate_decision_never_suppresses(tmp_path):
    g = spine(tmp_path, enforce=False)
    d = g.admit(ep(), Proposal(kind="command", command="rm -rf /", safety={"decision": "block"}))
    assert d.outcome == REFUSE and d.permits() is True and d.enforced is False


# --- receipts, sinks, D5 seal, D6/L3, D7, evictions ---------------------------------------------

def test_receipts_are_hash_chained_and_sinks_receive_them(tmp_path):
    seen = []
    log = GovernorReceiptLog(tmp_path / "r.jsonl", sinks=[seen.append, lambda r: 1 / 0])
    g = spine(tmp_path, receipts=log)
    g.admit(ep(), Proposal(kind="deterministic_tool", tool_id="t"))
    g.admit(ep(), Proposal(kind="deterministic_tool", tool_id="u"))
    assert len(seen) == 2 and log.verify() == {"valid": True, "count": 2, "errors": []}
    lines = (tmp_path / "r.jsonl").read_text().splitlines()
    (tmp_path / "r.jsonl").write_text("\n".join([lines[0].replace('"t"', '"z"'), lines[1]]) + "\n")
    assert log.verify()["valid"] is False


def test_forensic_and_chronicle_sinks(tmp_path):
    log = GovernorReceiptLog(tmp_path / "r.jsonl", sinks=[gs.forensic_sink(tmp_path / "l4"),
                                                          gs.chronicle_sink(tmp_path / "chronicles")])
    spine(tmp_path, receipts=log).admit(ep(run_id="run-9"), Proposal(kind="deterministic_tool", tool_id="t"))
    assert (tmp_path / "l4" / "governor_receipts.jsonl").read_text().count("receipt_hash") == 1
    assert (tmp_path / "chronicles" / "governor-run-9.jsonl").exists()


def test_task_envelope_seals_into_verified_episode(tmp_path):
    from app.kernel.sensorium.episode_envelope import envelope_from_swarm_episode

    task = {"task_id": "t1", "task_class": "fix", "context_budget": {"max_tokens": 100}}
    verified = envelope_from_swarm_episode({"episode_status": "verified", "task_class": "fix", "events": []},
                                           run_id="run-1")
    sealed = gs.seal_task_envelope(task, verified)
    assert sealed["task_envelope"] == task and sealed["episode_envelope"]["envelope_digest"] == verified.envelope_digest
    assert sealed["binding_digest"].startswith("sha256:")
    unverified = envelope_from_swarm_episode({"episode_status": "failed", "task_class": "fix", "events": []},
                                             run_id="run-2")
    with pytest.raises(ValueError):
        gs.seal_task_envelope(task, unverified)


def test_skill_tree_promotion_requires_d6_promotion(tmp_path):
    class Tree:
        promoted = []

        def promote_candidate(self, candidate_id, approved_by="user", require_validation=True):
            self.promoted.append(candidate_id)
            return {"promoted": True}

    class Registry:
        def __init__(self, status):
            self.status = status

        def get(self, crystal_id):
            return {"status": self.status, "receipt": {"promoted": self.status == "promoted"}}

    tree = Tree()
    with pytest.raises(PermissionError):
        gs.promote_skill_via_d6(tree, "cand", registry=Registry("candidate"), crystal_id="c", approved_by="byron")
    with pytest.raises(PermissionError):
        gs.promote_skill_via_d6(tree, "cand", registry=Registry("promoted"), crystal_id="c", approved_by="")
    result = gs.promote_skill_via_d6(tree, "cand", registry=Registry("promoted"), crystal_id="c", approved_by="byron")
    assert result["promoted"] and result["d6_crystal_id"] == "c" and tree.promoted == ["cand"]


def test_skill_tree_enforced_mode_requires_d6(monkeypatch):
    from app.kernel.capability.skill_tree import SkillTree

    monkeypatch.setenv(gs.ENFORCE_ENV, "1")
    tree = SkillTree.__new__(SkillTree)
    with pytest.raises(ValueError, match="d6_crystal_promotion_required"):
        tree.promote_candidate("cand")


def test_d7_settles_only_from_governor_receipts(tmp_path):
    g = spine(tmp_path)
    assert g.receipts.settle("coding-crystal:a") == ""
    g.admit(ep(), Proposal(kind="crystal", crystal_id="coding-crystal:a", route_decision=crystal_route()))
    rid = g.receipts.settle("coding-crystal:a")
    assert rid
    assert g.receipts.settle("coding-crystal:a") == ""  # one settlement per admit receipt
    assert g.receipts.verify()["valid"]


def test_d7_ledger_refuses_without_governor_receipt(tmp_path):
    from app.kernel.compute.crystal_economy import CrystalShadowLedger

    calls = []
    ledger = CrystalShadowLedger(tmp_path / "shadow.sqlite", local_node_id="n",
                                 governor_settlement=lambda crystal_id: calls.append(crystal_id) or "")
    entry = ledger.account_reuse({"provenance": {"crystal_id": "coding-crystal:a"}}, crystal_status="promoted")
    assert entry["credited"] is False
    # receipt validation fails first for this malformed receipt; the governor gate still never credits.
    assert entry["reason"] in {"receipt_invalid", "governor_receipt_missing"}


def test_evictions_are_dry_run_through_admit(tmp_path):
    from app.kernel.compute.capsule_lifecycle_governor import CapsuleLifecycleGovernor

    class Entry:
        def __init__(self, cid):
            self.capsule_id, self.workspace_id, self.privacy_domain = cid, "w", "p"

    class Registry:
        closed = []

        def entries(self):
            return [Entry("a"), Entry("b")]

        def close(self, cid):
            self.closed.append(cid)
            return True

    class Policy:
        def choose(self, entries, pressure_level, pin_registry):
            return ["a", "b"]

    g = spine(tmp_path)
    registry = Registry()
    receipt = CapsuleLifecycleGovernor(registry=registry, eviction_policy=Policy(), governor=g).apply("high")
    assert registry.closed == [] and receipt.evicted_capsules == ()
    last = g.receipts.records()[-1]
    assert last["proposal"]["kind"] == "eviction" and last["proposal"]["dry_run"] is True
    assert last["proposal"]["targets"] == ["a", "b"]
    wrapped = gs.GovernedEvictor(type("P", (), {"evict_cold": lambda self, **k: 7})(), governor=g, kind="prism")
    assert wrapped.evict_cold(preserve_ids=set(), maximum=3) == 0
    assert g.receipts.records()[-1]["proposal"]["kind"] == "eviction"


def test_compute_governor_evaluate_derives_allowed_from_admit(tmp_path, monkeypatch):
    from app.kernel.governance.compute_governor import ComputeGovernor

    plan_gov = ComputeGovernor(mode="shadow")
    ir = type("IR", (), {"messages": [{"role": "user", "content": "hello"}], "model": "m", "metadata": {},
                         "tools": None})()
    plan = plan_gov.build_plan(ir, "p")
    monkeypatch.delenv(gs.ENFORCE_ENV, raising=False)
    shadow = plan_gov.evaluate(plan)
    assert shadow.allowed is True and shadow.governor["outcome"] == REVALIDATE  # no cascade yet, shadow only
    monkeypatch.setenv(gs.ENFORCE_ENV, "1")
    enforced = ComputeGovernor(mode="shadow", spine=spine(tmp_path)).evaluate(plan)
    assert enforced.allowed is False and enforced.decision == "escalate"
    ok = ComputeGovernor(mode="shadow", spine=spine(tmp_path)).evaluate(plan, quality_cascade=CASCADE_OK)
    assert ok.allowed is True and ok.governor["outcome"] == ADMIT


def test_execute_command_route_runs_only_behind_admit(tmp_path, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.routes.policy import build_policy_router

    monkeypatch.setenv(gs.ENFORCE_ENV, "1")
    app = FastAPI()
    app.include_router(build_policy_router(tmp_path, None))
    client = TestClient(app)
    ok = client.post("/edgek/safety-governor/execute-command", json={"command": "echo hi"}).json()
    assert ok["ok"] is True and ok["governor"]["outcome"] == ADMIT
    log = GovernorReceiptLog(tmp_path / ".beast" / "governor" / "receipts.jsonl")
    assert log.verify()["valid"] and log.records()[-1]["proposal"]["kind"] == "command"

    def refuse(self, episode, proposal):
        return gs.GovernorDecision(outcome=REFUSE, reasons=("l0:test",), rung="command", recommended_rung="",
                                   enforced=True, pressure_factor=1.0, effective_limits={},
                                   proposal_digest=proposal.digest(), receipt_id="gov_x")

    monkeypatch.setattr(ComputeGovernorSpine, "admit", refuse)
    marker = tmp_path / "ran.txt"
    blocked = client.post("/edgek/safety-governor/execute-command",
                          json={"command": f"touch {marker}"}).json()
    assert blocked["ok"] is False and blocked["error"] == "governor_refuse" and not marker.exists()


def test_planner_crystal_activation_requires_governor_admit(tmp_path):
    from app.kernel.agents.planner_runtime import AgentPlannerRuntime
    from app.kernel.compute.adaptive_router import AdaptiveRouter

    events = []

    class Engine:
        def emit(self, run_id, kind, payload):
            events.append((kind, payload))

    fp = {"opcode_catalog_digest": "o", "crystal_digest": "c", "source_envelope_digest": "s"}

    class Router:
        def __init__(self, similarity):
            self.similarity = similarity

        def route_run(self, run):
            return AdaptiveRouter().route(similarity=self.similarity, crystal_id="coding-crystal:a",
                                          crystal_fingerprints=fp, request_fingerprints=fp)

    def runtime(router, governor):
        rt = AgentPlannerRuntime.__new__(AgentPlannerRuntime)
        rt.engine, rt.adaptive_router, rt.governor, rt._crystal_nominations = Engine(), router, governor, {}
        return rt

    allowed = runtime(Router(0.97), spine(tmp_path))
    assert allowed._route_allows_crystal("run-1", {}) is True
    assert any(kind == "agent.governor.decision" and p["outcome"] == ADMIT for kind, p in events)
    # Enforced governor + no router: no route, no admit, no crystal.
    assert runtime(None, spine(tmp_path))._route_allows_crystal("run-2", {}) is False
    # Governor refusal (loop) blocks even an exact route.
    looping = spine(tmp_path, loop_threshold=2)
    rt = runtime(Router(0.97), looping)
    assert rt._route_allows_crystal("run-3", {}) is True
    assert rt._route_allows_crystal("run-3", {}) is True
    assert rt._route_allows_crystal("run-3", {}) is False and "run-3" not in rt._crystal_nominations
    # No governor keeps the D9 behaviour.
    assert runtime(None, None)._route_allows_crystal("run-4", {}) is True


def test_runtime_extras_bind_governor_only_when_enforced(tmp_path, monkeypatch):
    from app.kernel.compute import coding_crystal_runtime as runtime

    monkeypatch.setattr(runtime, "_load_key", lambda env: (__import__(
        "cryptography.hazmat.primitives.asymmetric.ed25519", fromlist=["x"]).Ed25519PrivateKey.generate(), "ready"))
    env = {"BEAST_CODING_CRYSTALS": "1", "BEAST_ADAPTIVE_ROUTER": "1"}
    off = runtime.planner_runtime_extras(tmp_path, env=env)
    assert "governor" not in off and off["crystal_planner"].economy.ledger.governor_settlement is None
    on = runtime.planner_runtime_extras(tmp_path, env={**env, gs.ENFORCE_ENV: "1"})
    governor = on["governor"]
    assert governor.enforce is True
    assert on["crystal_planner"].economy.ledger.governor_settlement == governor.receipts.settle
    assert governor.receipts.path == tmp_path.resolve() / ".beast" / "governor" / "receipts.jsonl"


def test_prism_workload_governor_wraps_eviction_as_dry_run(tmp_path):
    from app.kernel.compute.prism_r5_workload_governor import PRISMR5WorkloadGovernor

    class Evictor:
        calls = 0

        def evict_cold(self, *, preserve_ids, maximum):
            Evictor.calls += 1
            return 5

    g = spine(tmp_path)
    prism = PRISMR5WorkloadGovernor(eviction=Evictor(), governor=g)
    assert isinstance(prism.eviction, gs.GovernedEvictor)
    assert prism.eviction.evict_cold(preserve_ids=set(), maximum=16) == 0 and Evictor.calls == 0
    assert PRISMR5WorkloadGovernor(eviction=Evictor()).eviction.__class__.__name__ == "Evictor"

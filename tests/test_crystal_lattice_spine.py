"""Lattice Spine: governed, fail-closed composition graph (PGEC eq.2-3, §2.4, §8.1(4); IEI v0.9 §7.13.1)."""
from __future__ import annotations

import dataclasses
import sys
from pathlib import Path

import pytest

from app.kernel.compute.coding_crystals import (
    CODING_OPCODE_TOOLS,
    CRYSTAL_PARAMETERS,
    CodingCrystalCandidate,
    CodingCrystalRegistry,
    coding_catalog_digest,
)
from app.kernel.compute.heldout_replay import ReplayReceipt

sys.path.insert(0, str(Path(__file__).resolve().parent))  # crystal_fabric_support, independent of run order

STEPS = (
    {"opcode": "worktree.inspect", "tool_id": "workspace.read_range", "expect": ""},
    {"opcode": "worktree.bind", "tool_id": "worktree.bind", "expect": ""},
    {"opcode": "worktree.verify", "tool_id": "worktree.verify", "expect": "fail"},
    {"opcode": "repair.resolve_constant", "tool_id": "", "expect": ""},
    {"opcode": "worktree.replace_exact", "tool_id": "worktree.replace_exact", "expect": ""},
    {"opcode": "worktree.verify", "tool_id": "worktree.verify", "expect": "pass"},
    {"opcode": "crystal.complete", "tool_id": "", "expect": ""},
)
BASELINE = {"model_turns": 7.0, "tool_calls": 9.0, "tokens_total": 8400.0, "tokens_estimated_turns": 7.0, "wall_ms": 1100.0}


def crystal(run_id: str, *, steps=STEPS, family="fix-failing-assertion", budget=BASELINE) -> CodingCrystalCandidate:
    return CodingCrystalCandidate(crystal_id="", task_family=family, steps=tuple(dict(s) for s in steps),
                                  parameters=CRYSTAL_PARAMETERS, opcode_catalog_digest=coding_catalog_digest(),
                                  source_run_id=run_id, source_envelope_digest="sha256:" + run_id.ljust(64, "0")[:64],
                                  learned_budget=dict(budget)).sealed()


def passing(crystal_id: str) -> ReplayReceipt:
    return ReplayReceipt(crystal_id, 3, 3, True, "held-out replay passed")


@pytest.fixture
def spine(tmp_path):
    from app.kernel.compute.crystal_lattice_spine import CrystalLattice
    from app.kernel.security.crystal_chain import CrystalChainLedger
    from app.kernel.security.crystal_lattice_ledger import CrystalLatticeLedger

    registry = CodingCrystalRegistry(tmp_path / "registry.sqlite3")
    lattice = CrystalLattice(tmp_path / "lattice.sqlite3", registry=registry,
                             lattice_ledger=CrystalLatticeLedger(tmp_path / "lattice_ledger"),
                             chain=CrystalChainLedger(tmp_path / "chain" / "blocks.jsonl", node_id="test"))
    children = []
    for run_id, publisher in (("run-a", "pub-a"), ("run-b", "pub-b")):
        child = crystal(run_id)
        registry.add_candidate(child)
        registry.promote(child.crystal_id, passing(child.crystal_id))
        lattice.add_crystal(child.crystal_id, publisher_id=publisher)
        children.append(child)
    return {"registry": registry, "lattice": lattice, "children": children, "tmp": tmp_path}


def compose(children, run_id="run-composite"):
    from app.kernel.compute.crystal_lattice_spine import compose_candidates

    return compose_candidates(children, task_family="fix-two-assertions", source_run_id=run_id,
                              source_envelope_digest="sha256:" + "c" * 64, learned_budget={
                                  "model_turns": 15.0, "tool_calls": 20.0, "tokens_total": 0.0, "wall_ms": 2400.0})


# --- Task 1: contracts -----------------------------------------------------------------------------------------

def test_existing_crystal_and_envelope_digests_are_unchanged_by_new_fields():
    child = crystal("run-a")
    body = dataclasses.asdict(child)
    for key in ("component_ids", "authority", "composite_verification", "digest", "crystal_id"):
        body.pop(key, None)
    import hashlib
    import json
    legacy = "sha256:" + hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()
    assert child.digest == legacy

    from app.kernel.sensorium.episode_envelope import EpisodeEnvelope
    env = EpisodeEnvelope(schema="beast.episode_envelope.v1", run_id="r", origin="agent_run", workspace_digest="w",
                          objective_digest="o", task_family="f", mode="agent", provider="p", model="m", state="completed",
                          implementation_target="", steps=(), verification={"passed": True}, negative_evidence=(),
                          budget={}, event_chain_head="h")
    sealed = env.sealed()
    assert "component_ids" not in sealed._body()
    composite_env = dataclasses.replace(env, component_ids=("a", "b"), authority=("worktree.verify",),
                                        composite_verification={"passed": True}).sealed()
    assert composite_env.envelope_digest != sealed.envelope_digest
    composite_env.validate()
    assert EpisodeEnvelope.from_dict(composite_env.to_dict()).component_ids == ("a", "b")


def test_authority_is_the_intersection_of_children():
    from app.kernel.compute.crystal_lattice_spine import authority_of, compose_candidates

    full = crystal("run-a")
    narrow = crystal("run-n", steps=STEPS[1:])  # no workspace.read_range
    assert "workspace.read_range" in authority_of(full) and "workspace.read_range" not in authority_of(narrow)
    composite = compose_candidates([narrow, crystal("run-n2", steps=STEPS[1:])], task_family="t", source_run_id="x",
                                   source_envelope_digest="sha256:" + "d" * 64, learned_budget={})
    assert set(composite.authority) == authority_of(narrow)
    assert composite.component_ids == (narrow.crystal_id, composite.component_ids[1])
    composite.validate()
    with pytest.raises(ValueError, match="authority"):
        compose_candidates([full, narrow], task_family="t", source_run_id="x",
                           source_envelope_digest="sha256:" + "d" * 64, learned_budget={})
    shrunk = dataclasses.replace(composite, authority=("worktree.bind",)).sealed()  # steps now exceed A_L
    with pytest.raises(ValueError, match="exceed"):
        CodingCrystalCandidate.from_dict(shrunk.to_dict())


def test_widened_authority_is_refused_at_admission(spine):
    narrow = []
    for run_id in ("run-n1", "run-n2"):
        child = crystal(run_id, steps=STEPS[1:])  # A_C lacks workspace.read_range
        spine["registry"].add_candidate(child)
        spine["registry"].promote(child.crystal_id, passing(child.crystal_id))
        spine["lattice"].add_crystal(child.crystal_id, publisher_id="pub-n")
        narrow.append(child)
    composite = compose(narrow)
    assert "workspace.read_range" not in composite.authority
    widened = dataclasses.replace(composite, authority=tuple(sorted(set(CODING_OPCODE_TOOLS.values()) - {""}))).sealed()
    widened.validate()  # self-consistent on its own; only the lattice knows the children's envelopes
    result = spine["lattice"].admit_composite(widened, verifier=passing(widened.crystal_id), publisher_id="pub-l",
                                              approved_by="byron")
    assert result["outcome"] == "REFUSE" and result["reason"] == "authority_not_intersection"


# --- Task 2: admission -----------------------------------------------------------------------------------------

def test_two_child_composite_admitted_only_when_children_and_composite_pass(spine):
    lattice, registry, (a, b) = spine["lattice"], spine["registry"], spine["children"]
    composite = compose([a, b])
    failed = lattice.admit_composite(composite, verifier=ReplayReceipt(composite.crystal_id, 3, 2, False, "1 fail"),
                                     publisher_id="pub-l", approved_by="byron")
    assert failed["outcome"] == "REFUSE" and failed["reason"] == "composite_verifier_failed"
    assert lattice.admit_composite(composite, verifier=None, publisher_id="pub-l",
                                   approved_by="byron")["outcome"] == "ESCALATE"
    assert lattice.admit_composite(composite, verifier=passing(composite.crystal_id), publisher_id="pub-l",
                                   approved_by="")["reason"] == "operator_promotion_required"
    registry.demote(b.crystal_id, reason="drift")
    lattice.demote(b.crystal_id, reason="drift")
    refused = lattice.admit_composite(composite, verifier=passing(composite.crystal_id), publisher_id="pub-l",
                                      approved_by="byron")
    assert refused["outcome"] == "REFUSE" and refused["reason"].startswith("child_not_verified")


def test_admission_succeeds_and_is_witnessed(spine):
    lattice, registry, (a, b) = spine["lattice"], spine["registry"], spine["children"]
    composite = compose([a, b])
    result = lattice.admit_composite(composite, verifier=passing(composite.crystal_id), publisher_id="pub-l",
                                     approved_by="byron")
    assert result["outcome"] == "ADMIT"
    node = lattice.node(composite.crystal_id)
    assert node["status"] == "admitted" and node["component_ids"] == [a.crystal_id, b.crystal_id]
    assert node["authority"] == sorted(composite.authority)
    assert registry.get(composite.crystal_id)["status"] == "promoted"
    edges = {(e["edge_type"], tuple(e["source_ids"]), e["target_id"]) for e in lattice.edges()}
    assert ("COMPOSES_WITH", (a.crystal_id, b.crystal_id), composite.crystal_id) in edges
    assert lattice.verify()["valid"] is True
    events = [blk["event_type"] for blk in lattice.chain.blocks()]
    assert "crystal_lattice_spine_admit" in events and events.count("crystal_lattice_spine_add") == 2
    assert lattice.lattice_ledger.verify().valid and lattice.lattice_ledger.verify().checkpoint_count == len(events)


def test_one_child_wrapper_and_duplicate_children_are_refused(spine):
    from app.kernel.compute.crystal_lattice_spine import compose_candidates

    a = spine["children"][0]
    with pytest.raises(ValueError, match="two distinct"):
        compose_candidates([a], task_family="t", source_run_id="x", source_envelope_digest="sha256:" + "e" * 64,
                           learned_budget={})
    with pytest.raises(ValueError, match="two distinct"):
        compose_candidates([a, a], task_family="t", source_run_id="x", source_envelope_digest="sha256:" + "e" * 64,
                           learned_budget={})
    wrapper = dataclasses.replace(compose(spine["children"]), component_ids=(a.crystal_id,))
    result = spine["lattice"].admit_composite(wrapper, verifier=passing(wrapper.crystal_id), publisher_id="pub-l",
                                              approved_by="byron")
    assert result["outcome"] == "REFUSE"


def test_tampered_lattice_record_requires_revalidation(spine):
    import sqlite3

    lattice, (a, b) = spine["lattice"], spine["children"]
    with sqlite3.connect(spine["tmp"] / "lattice.sqlite3") as c:
        c.execute("UPDATE nodes SET publisher_id='mallory' WHERE node_id=?", (a.crystal_id,))
    composite = compose([a, b])
    result = lattice.admit_composite(composite, verifier=passing(composite.crystal_id), publisher_id="pub-l",
                                     approved_by="byron")
    assert result["outcome"] == "REVALIDATE"


def test_child_demotion_cascades_upward(spine):
    lattice, registry, (a, b) = spine["lattice"], spine["registry"], spine["children"]
    composite = compose([a, b])
    lattice.admit_composite(composite, verifier=passing(composite.crystal_id), publisher_id="pub-l", approved_by="byron")
    c = crystal("run-c")
    registry.add_candidate(c)
    registry.promote(c.crystal_id, passing(c.crystal_id))
    lattice.add_crystal(c.crystal_id, publisher_id="pub-c")
    top = compose([composite, c], run_id="run-top")
    assert lattice.admit_composite(top, verifier=passing(top.crystal_id), publisher_id="pub-t",
                                   approved_by="byron")["outcome"] == "ADMIT"
    demoted = lattice.demote(a.crystal_id, reason="postcondition_failed")
    assert demoted["demoted"] == [a.crystal_id, composite.crystal_id, top.crystal_id]
    assert lattice.node(top.crystal_id)["status"] == "demoted"
    assert registry.get(composite.crystal_id)["status"] == "demoted"
    assert lattice.node(b.crystal_id)["status"] == "admitted"  # siblings are not demoted
    assert lattice.best_for_family("fix-two-assertions") is None


# --- Task 3: D7 shadow-ledger credits for composites ------------------------------------------------------------

from types import SimpleNamespace  # noqa: E402

COMPOSITE_BASELINE = {"model_turns": 15.0, "tool_calls": 20.0, "tokens_total": 0.0, "wall_ms": 2400.0}
REUSE = {"model_turns": 0.0, "tool_calls": 8.0, "tokens_total": 0.0, "wall_ms": 400.0}
CONTROLLERS = {"pub-a": "alice", "pub-b": "bob", "pub-l": "lena", "node-consumer": "carol", "carol": "carol",
               "pub-self": "alice"}


def _ledger(tmp_path, *, local_publisher_id=""):
    from app.kernel.compute.crystal_economy import CrystalShadowLedger

    return CrystalShadowLedger(tmp_path / "shadow.sqlite3", local_node_id="node-consumer",
                               local_publisher_id=local_publisher_id,
                               controller_of=lambda identity: CONTROLLERS.get(identity, identity))


def _receipt(composite, children, *, lattice_publisher="pub-l", child_baseline=BASELINE, consumer_user="carol",
             run_id="reuse-1"):
    from app.kernel.compute.crystal_economy import composite_reuse_receipt

    envelope = SimpleNamespace(budget=dict(REUSE), verification={"passed": True}, run_id=run_id,
                               envelope_digest="sha256:" + run_id.ljust(64, "f")[:64])
    components = [{"crystal_id": child.crystal_id, "publisher_id": publisher, "space_id": f"space-{publisher}",
                   "baseline_budget": dict(child_baseline), "steps": len(child.steps) - 1}
                  for child, publisher in children]
    return composite_reuse_receipt(
        composite_baseline=COMPOSITE_BASELINE, composite_baseline_digest="sha256:" + "c" * 64, reuse_envelope=envelope,
        composite_id=composite.crystal_id, space_id="space-l", space_manifest_hash="sha256:" + "a" * 64,
        lattice_publisher_id=lattice_publisher, consumer={"node_id": "node-consumer", "user_id": consumer_user},
        components=components, local_reproduction_verified=True, promotion_verified=True)


def _admitted(spine):
    a, b = spine["children"]
    composite = compose([a, b])
    assert spine["lattice"].admit_composite(composite, verifier=passing(composite.crystal_id), publisher_id="pub-l",
                                            approved_by="byron")["outcome"] == "ADMIT"
    return composite, a, b


def _units(ledger, publisher):
    return round(sum(e["units"] for e in ledger.entries() if e["publisher_id"] == publisher), 6)


def test_composite_receipt_is_schema_valid_and_credits_children_plus_surplus(spine):
    from app.kernel.compute.crystal_economy import validate_receipt

    composite, a, b = _admitted(spine)
    ledger = _ledger(spine["tmp"])
    receipt = _receipt(composite, [(a, "pub-a"), (b, "pub-b")])
    assert validate_receipt(receipt)["valid"] is True
    value = receipt["resource_deltas"]["recurrence_value"]
    result = ledger.account_composite_reuse(receipt, lattice_status="admitted",
                                            child_status={a.crystal_id: "promoted", b.crystal_id: "promoted"})
    v_l = value["v_k"]
    v_children = [c["recurrence_value"]["v_k"] for c in receipt["provenance"]["components"]]
    assert result["credited"] is True
    assert _units(ledger, "pub-a") == pytest.approx(max(0, v_children[0]), abs=1e-6)
    assert result["premium"] == pytest.approx(v_l - sum(max(0, v) for v in v_children), abs=1e-5)
    assert _units(ledger, "pub-l") == pytest.approx(result["premium"], abs=1e-6)
    assert result["total"] <= v_l + 1e-9
    again = ledger.account_composite_reuse(receipt, lattice_status="admitted",
                                           child_status={a.crystal_id: "promoted", b.crystal_id: "promoted"})
    assert again["reason"] == "duplicate_reuse"
    assert ledger.verify_chain()["valid"] is True


def test_credits_never_exceed_measured_v_l_children_scaled_no_premium(spine):
    composite, a, b = _admitted(spine)
    ledger = _ledger(spine["tmp"])
    rich = {"model_turns": 14.0, "tool_calls": 18.0, "tokens_total": 0.0, "wall_ms": 2000.0}
    receipt = _receipt(composite, [(a, "pub-a"), (b, "pub-b")], child_baseline=rich)
    v_l = receipt["resource_deltas"]["recurrence_value"]["v_k"]
    result = ledger.account_composite_reuse(receipt, lattice_status="admitted",
                                            child_status={a.crystal_id: "promoted", b.crystal_id: "promoted"})
    assert result["premium"] == 0 and result["scaled"] is True
    assert result["total"] == pytest.approx(v_l, abs=1e-5)
    assert _units(ledger, "pub-a") + _units(ledger, "pub-b") <= v_l + 1e-6
    rating = ledger.rate_composite(receipt["receipt_id"], rater_node="node-consumer", rater_user="carol", stars=5)
    assert rating["units"] == 0  # already at V_L: the multiplier cannot lift credits above the measurement
    assert _units(ledger, "pub-a") + _units(ledger, "pub-b") + _units(ledger, "pub-l") <= v_l + 1e-6


def test_rating_multiplies_children_but_total_stays_within_v_l(spine):
    composite, a, b = _admitted(spine)
    ledger = _ledger(spine["tmp"])
    receipt = _receipt(composite, [(a, "pub-a"), (b, "pub-b")])
    v_l = receipt["resource_deltas"]["recurrence_value"]["v_k"]
    first = ledger.account_composite_reuse(receipt, lattice_status="admitted",
                                           child_status={a.crystal_id: "promoted", b.crystal_id: "promoted"})
    with pytest.raises(PermissionError):
        ledger.rate_composite(receipt["receipt_id"], rater_node="node-consumer", rater_user="mallory", stars=5)
    ledger.rate_composite(receipt["receipt_id"], rater_node="node-consumer", rater_user="carol", stars=5)
    with pytest.raises(PermissionError):
        ledger.rate_composite(receipt["receipt_id"], rater_node="node-consumer", rater_user="carol", stars=5)
    total = _units(ledger, "pub-a") + _units(ledger, "pub-b") + _units(ledger, "pub-l")
    assert total <= v_l + 1e-6
    assert _units(ledger, "pub-l") < first["premium"]  # overflow came out of the premium first
    low = _ledger(spine["tmp"] / "low")
    low.account_composite_reuse(_receipt(composite, [(a, "pub-a"), (b, "pub-b")], run_id="reuse-2"),
                                lattice_status="admitted",
                                child_status={a.crystal_id: "promoted", b.crystal_id: "promoted"})
    rid = [e for e in low.entries() if e["kind"] == "composite_reuse"][0]["receipt_id"]
    before = _units(low, "pub-a")
    low.rate_composite(rid, rater_node="node-consumer", rater_user="carol", stars=1)
    assert _units(low, "pub-a") == pytest.approx(before * 0.5, abs=1e-6)


def test_self_composition_and_consumer_collusion_earn_no_premium(spine):
    composite, a, b = _admitted(spine)
    ledger = _ledger(spine["tmp"])
    own = _receipt(composite, [(a, "pub-a"), (b, "pub-a")], lattice_publisher="pub-self")  # alice owns everything
    result = ledger.account_composite_reuse(own, lattice_status="admitted",
                                            child_status={a.crystal_id: "promoted", b.crystal_id: "promoted"})
    assert result["premium"] == 0 and result["premium_reason"] == "lattice_publisher_controls_every_child"
    assert _units(ledger, "pub-self") == 0
    collusion = _ledger(spine["tmp"] / "collusion")
    colluding = _receipt(composite, [(a, "pub-a"), (b, "pub-b")], lattice_publisher="carol", run_id="reuse-3")
    result = collusion.account_composite_reuse(colluding, lattice_status="admitted",
                                               child_status={a.crystal_id: "promoted", b.crystal_id: "promoted"})
    assert result["premium"] == 0 and result["premium_reason"] == "consumer_shares_lattice_publisher_controller"
    assert _units(collusion, "pub-a") > 0  # independent children are still credited


def test_unadmitted_or_remote_composite_reuse_earns_nothing(spine):
    composite, a, b = _admitted(spine)
    ledger = _ledger(spine["tmp"])
    receipt = _receipt(composite, [(a, "pub-a"), (b, "pub-b")])
    refused = ledger.account_composite_reuse(receipt, lattice_status="demoted",
                                             child_status={a.crystal_id: "promoted", b.crystal_id: "promoted"})
    assert refused["credited"] is False and refused["total"] == 0
    remote = dict(receipt, provenance={**receipt["provenance"], "consumer": {"node_id": "elsewhere", "user_id": "x"}})
    assert ledger.account_composite_reuse(remote, lattice_status="admitted", child_status={})["credited"] is False


def test_child_demotion_claws_back_child_and_parent_premiums_but_not_siblings(spine):
    from app.kernel.compute.crystal_lattice_spine import demote_with_clawback

    composite, a, b = _admitted(spine)
    ledger = _ledger(spine["tmp"])
    ledger.account_composite_reuse(_receipt(composite, [(a, "pub-a"), (b, "pub-b")]), lattice_status="admitted",
                                   child_status={a.crystal_id: "promoted", b.crystal_id: "promoted"})
    sibling = _units(ledger, "pub-b")
    assert _units(ledger, "pub-a") > 0 and _units(ledger, "pub-l") > 0
    result = demote_with_clawback(spine["lattice"], ledger, a.crystal_id, reason="postcondition_failed")
    assert result["demoted"] == [a.crystal_id, composite.crystal_id]
    assert _units(ledger, "pub-a") == pytest.approx(0, abs=1e-6)
    assert _units(ledger, "pub-l") == pytest.approx(0, abs=1e-6)
    assert _units(ledger, "pub-b") == pytest.approx(sibling, abs=1e-6)
    assert ledger.verify_chain()["valid"] is True


def test_demoting_the_composite_claws_back_only_its_premium(spine):
    from app.kernel.compute.crystal_lattice_spine import demote_with_clawback

    composite, a, b = _admitted(spine)
    ledger = _ledger(spine["tmp"])
    ledger.account_composite_reuse(_receipt(composite, [(a, "pub-a"), (b, "pub-b")]), lattice_status="admitted",
                                   child_status={a.crystal_id: "promoted", b.crystal_id: "promoted"})
    children_before = _units(ledger, "pub-a"), _units(ledger, "pub-b")
    demote_with_clawback(spine["lattice"], ledger, composite.crystal_id, reason="composite_postcondition_failed")
    assert _units(ledger, "pub-l") == pytest.approx(0, abs=1e-6)
    assert (_units(ledger, "pub-a"), _units(ledger, "pub-b")) == pytest.approx(children_before, abs=1e-6)
    assert spine["lattice"].node(a.crystal_id)["status"] == "admitted"


def test_d6_false_reuse_hook_cascades_through_the_lattice(spine):
    from crystal_fabric_support import crystal_stack

    from app.kernel.compute.coding_crystals import CodingCrystalPlanner
    from app.kernel.compute.crystal_economy import CrystalReuseEconomy

    composite, a, b = _admitted(spine)
    ledger = _ledger(spine["tmp"])
    ledger.account_composite_reuse(_receipt(composite, [(a, "pub-a"), (b, "pub-b")]), lattice_status="admitted",
                                   child_status={a.crystal_id: "promoted", b.crystal_id: "promoted"})
    stack = crystal_stack(spine["tmp"] / "stack")
    planner = CodingCrystalPlanner(spine["registry"], stack["authority"], stack["ledger"],
                                   economy=CrystalReuseEconomy(ledger), lattice=spine["lattice"])
    planner.on_postcondition_failed(SimpleNamespace(candidate=a), "sha256:" + "9" * 64)
    assert spine["lattice"].node(composite.crystal_id)["status"] == "demoted"
    assert spine["registry"].get(composite.crystal_id)["status"] == "demoted"
    assert _units(ledger, "pub-l") == pytest.approx(0, abs=1e-6)
    assert _units(ledger, "pub-a") == pytest.approx(0, abs=1e-6)


# --- Task 4: the D9 router points at the spine ------------------------------------------------------------------

def test_router_nominates_only_admitted_lattice_nodes_and_prefers_composites(spine):
    from app.kernel.compute.adaptive_router import CodingCrystalRouter

    composite, a, b = _admitted(spine)

    class Envelopes:  # every source envelope present and verified
        def get(self, run_id):
            raise LookupError(run_id)

    router = CodingCrystalRouter(spine["registry"], None, lattice=spine["lattice"], require_source_envelope=False)
    leaf = router.route_run({"request": {"task_family": "fix-failing-assertion"}})
    assert leaf.route.value == "crystal_replay" and leaf.crystal_id in {a.crystal_id, b.crystal_id}
    top = router.route_run({"request": {"task_family": "fix-two-assertions"}})
    assert top.route.value == "crystal_replay" and top.crystal_id == composite.crystal_id
    weak = router.route_run({"request": {"task_family": "fix-two-assertions", "route_similarity": 0.9}})
    assert weak.route.value == "provider_fallback"  # similarity only nominates
    spine["lattice"].demote(composite.crystal_id, reason="drift")
    assert router.route_run({"request": {"task_family": "fix-two-assertions"}}).route.value == "provider_fallback"
    strict = CodingCrystalRouter(spine["registry"], Envelopes(), lattice=spine["lattice"])
    assert strict.route_run({"request": {"task_family": "fix-failing-assertion"}}).fingerprint_compatible is False


def test_router_refuses_tampered_lattice_node(spine):
    import sqlite3

    from app.kernel.compute.adaptive_router import CodingCrystalRouter

    a = spine["children"][0]
    with sqlite3.connect(spine["tmp"] / "lattice.sqlite3") as c:
        c.execute("UPDATE nodes SET status='admitted', publisher_id='mallory' WHERE node_id=?", (a.crystal_id,))
    router = CodingCrystalRouter(spine["registry"], None, lattice=spine["lattice"], require_source_envelope=False)
    decision = router.route_run({"request": {"task_family": "fix-failing-assertion"}})
    assert decision.crystal_id != a.crystal_id or decision.route.value != "crystal_replay"


def test_spine_state_is_read_only_until_a_lattice_exists(tmp_path):
    from app.kernel.compute.crystal_lattice_spine import spine_state

    state = spine_state(tmp_path)
    assert state["available"] is False and "emerging" in state["claim_boundary"]
    assert not (tmp_path / ".beast").exists()


def test_superseded_is_a_reversible_witnessed_lattice_state(spine):
    lattice, registry = spine["lattice"], spine["registry"]
    a, b = spine["children"]
    with pytest.raises(PermissionError):
        lattice.restore(b.crystal_id, reason="not superseded yet")
    with pytest.raises(PermissionError):
        lattice.supersede(b.crystal_id, by=b.crystal_id, reason="self")
    head = lattice.verify()["lattice_ledger_head"]
    out = lattice.supersede(b.crystal_id, by=a.crystal_id, reason="defrag:identical_program",
                            evidence_digest="sha256:" + "d" * 64)
    node = lattice.node(b.crystal_id)
    assert node["status"] == "superseded" and node["admission"]["superseded"]["by"] == a.crystal_id
    assert out["checkpoint_hash"] and lattice.verify()["valid"] and lattice.verify()["lattice_ledger_head"] != head
    assert registry.get(b.crystal_id)["status"] == "promoted"  # superseded is not a failure: no demotion, no clawback
    assert lattice.best_for_family("fix-failing-assertion") == a.crystal_id
    lattice.restore(b.crystal_id, reason="undo defrag")
    node = lattice.node(b.crystal_id)
    assert node["status"] == "admitted" and node["admission"]["supersede_history"][-1]["restored"] is True
    assert lattice.verify()["valid"]


def test_supersede_refuses_components_of_admitted_composites_and_cross_family(spine):
    composite, a, b = _admitted(spine)
    with pytest.raises(PermissionError):
        spine["lattice"].supersede(b.crystal_id, by=a.crystal_id, reason="would orphan the composite")
    with pytest.raises(PermissionError):
        spine["lattice"].supersede(composite.crystal_id, by=a.crystal_id, reason="cross family")

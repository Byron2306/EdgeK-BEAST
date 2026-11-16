"""D9 Task 4: router wired into the planner and AgentScheduler behind BEAST_ADAPTIVE_ROUTER (default off)."""
from __future__ import annotations

import asyncio
import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))  # crystal_fabric_support, independent of run order


@pytest.fixture(scope="module")
def learned(tmp_path_factory):
    from crystal_fabric_support import run_learn

    base = tmp_path_factory.mktemp("learn")
    result = run_learn(base / "repo", base / "envelopes.sqlite3")
    result["envelope_path"] = base / "envelopes.sqlite3"
    return result


def _stack(learned, base, *, with_source_envelope=True):
    from crystal_fabric_support import crystal_stack

    from app.kernel.compute.adaptive_router import CodingCrystalRouter
    from app.kernel.compute.coding_crystals import CodingCrystalExtractor, CodingCrystalPlanner
    from app.kernel.compute.heldout_replay import ReplayReceipt
    from app.kernel.sensorium.episode_envelope import EpisodeEnvelopeStore

    stack = crystal_stack(base)
    candidate = CodingCrystalExtractor().extract(learned["envelope"], learned["observations"])
    stack["registry"].add_candidate(candidate)
    stack["registry"].promote(candidate.crystal_id, ReplayReceipt(candidate.crystal_id, 3, 3, True, "held-out"))
    envelope_path = base / "router-envelopes.sqlite3"
    if with_source_envelope:
        shutil.copy(learned["envelope_path"], envelope_path)
    stack["candidate"] = candidate
    stack["planner"] = CodingCrystalPlanner(stack["registry"], stack["authority"], stack["ledger"])
    stack["router"] = CodingCrystalRouter(stack["registry"], EpisodeEnvelopeStore(envelope_path))
    return stack


def _run(root, stack, variant):
    from crystal_fabric_support import CountingProvider, create_assertion_run, make_assertion_repo

    from app.kernel.agents.planner_runtime import AgentPlannerRuntime

    make_assertion_repo(root, **variant)
    engine, run_id = create_assertion_run(root, module=variant["module"])
    provider = CountingProvider()
    final = asyncio.run(AgentPlannerRuntime(engine, provider, max_turns=14, crystal_planner=stack["planner"],
                                            adaptive_router=stack["router"]).run(run_id))
    events = engine.store.events(run_id, limit=1000)
    return final, provider, events


def _payloads(events, kind):
    return [e["payload"] for e in events if e["event_type"] == kind]


def test_exact_compatible_route_nominates_and_d6_still_decides(learned, tmp_path):
    from crystal_fabric_support import HELD_OUT_VARIANTS

    stack = _stack(learned, tmp_path / "s")
    final, provider, events = _run(tmp_path / "repo", stack, HELD_OUT_VARIANTS[0])
    route = _payloads(events, "agent.route.decision")[0]
    assert route["route"] == "crystal_replay" and route["execution_granted"] is False
    assert _payloads(events, "agent.crystal.activated")  # D6 gates ran and issued the one-use capability
    assert final["state"] == "completed" and provider.calls == 0


def test_missing_source_envelope_breaks_fingerprints_and_never_activates(learned, tmp_path):
    from crystal_fabric_support import HELD_OUT_VARIANTS

    stack = _stack(learned, tmp_path / "s", with_source_envelope=False)
    final, provider, events = _run(tmp_path / "repo", stack, HELD_OUT_VARIANTS[1])
    route = _payloads(events, "agent.route.decision")[0]
    assert route["route"] == "provider_fallback" and route["demotion_signal"] == "fingerprint_mismatch"
    assert not _payloads(events, "agent.crystal.activated")
    assert provider.calls >= 1


def test_structural_similarity_nominates_no_crystal(learned, tmp_path):
    stack = _stack(learned, tmp_path / "s")
    run = {"request": {"task_family": stack["candidate"].task_family, "route_similarity": 0.9}}
    decision = stack["router"].route_run(run)
    assert decision.route.value == "provider_fallback" and decision.band == "structural"
    run["request"]["route_similarity"] = 0.99
    assert stack["router"].route_run(run).route.value == "crystal_replay"
    assert stack["router"].route_run({"request": {"task_family": "unknown"}}).route.value == "provider_fallback"


def test_runtime_extras_add_router_only_when_flag_on(tmp_path, monkeypatch):
    from app.kernel.compute import coding_crystal_runtime as runtime

    monkeypatch.setattr(runtime, "_load_key", lambda env: (__import__(
        "cryptography.hazmat.primitives.asymmetric.ed25519", fromlist=["x"]).Ed25519PrivateKey.generate(), "ready"))
    off = runtime.planner_runtime_extras(tmp_path, env={"BEAST_CODING_CRYSTALS": "1"})
    on = runtime.planner_runtime_extras(tmp_path, env={"BEAST_CODING_CRYSTALS": "1", "BEAST_ADAPTIVE_ROUTER": "1"})
    assert "adaptive_router" not in off
    assert on["adaptive_router"].envelope_store is on["envelope_store"]


def test_scheduler_crystal_lane_follows_route_decision_when_flag_on(tmp_path, monkeypatch):
    from app.kernel.compute.adaptive_router import AdaptiveRouter
    from app.kernel.compute.agent_scheduler import AgentScheduler

    scheduler = AgentScheduler(tmp_path)
    monkeypatch.delenv("BEAST_ADAPTIVE_ROUTER", raising=False)
    legacy = scheduler.plan(objective="o", phase="scout", crystal_match=True, route_inputs={})
    assert "crystal_replay" in legacy["receipt"]["selected_lanes"]

    monkeypatch.setenv("BEAST_ADAPTIVE_ROUTER", "1")
    claim_only = scheduler.plan(objective="o", phase="scout", crystal_match=True, route_inputs={})
    assert "crystal_replay" not in claim_only["receipt"]["selected_lanes"]
    fp = {"opcode_catalog_digest": "a", "crystal_digest": "b", "source_envelope_digest": "c"}
    replay = AdaptiveRouter().route(similarity=0.99, crystal_id="coding-crystal:x", crystal_fingerprints=fp,
                                    request_fingerprints=fp)
    routed = scheduler.plan(objective="o", phase="scout", route_decision=replay.to_dict(), route_inputs={})
    assert routed["receipt"]["selected_lanes"][0] == "crystal_replay"
    assert routed["receipt"]["route_decision"]["execution_granted"] is False
    weak = AdaptiveRouter().route(similarity=0.5, crystal_id="coding-crystal:x", crystal_fingerprints=fp,
                                  request_fingerprints=fp)
    assert "crystal_replay" not in scheduler.plan(objective="o", phase="scout", route_decision=weak.to_dict(),
                                                  route_inputs={})["receipt"]["selected_lanes"]
    forged = {**replay.to_dict(), "execution_granted": True}
    assert "crystal_replay" not in scheduler.plan(objective="o", phase="scout", route_decision=forged,
                                                  route_inputs={})["receipt"]["selected_lanes"]


def test_runtime_extras_bind_lattice_only_when_lattice_flag_on(tmp_path, monkeypatch):
    from app.kernel.compute import coding_crystal_runtime as runtime
    from app.kernel.compute import crystal_lattice_spine as spine

    monkeypatch.setattr(runtime, "_load_key", lambda env: (__import__(
        "cryptography.hazmat.primitives.asymmetric.ed25519", fromlist=["x"]).Ed25519PrivateKey.generate(), "ready"))
    built = []
    monkeypatch.setattr(spine, "default_lattice", lambda workspace, registry: built.append(workspace) or "LATTICE")
    env = {"BEAST_CODING_CRYSTALS": "1", "BEAST_ADAPTIVE_ROUTER": "1"}
    assert runtime.planner_runtime_extras(tmp_path, env=env)["crystal_planner"].lattice is None
    on = runtime.planner_runtime_extras(tmp_path, env={**env, "BEAST_CRYSTAL_LATTICE": "1"})
    assert on["crystal_planner"].lattice == "LATTICE" and on["adaptive_router"].lattice == "LATTICE"
    assert built == [tmp_path]

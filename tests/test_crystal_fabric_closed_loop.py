"""Physical Crystal Fabric D5+D6 finish line: learn → extract → held-out replay → promote → reuse.

Offline and deterministic: a scripted planner plays the exploratory model; reuse must reach the same
verified outcome with at most 50% of the model turns and 70% of the tool calls, while misfits are
refused, failing recipes are demoted, reviewed-op boundaries hold and capabilities are one-use.
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from crystal_fabric_support import (  # noqa: E402
    HELD_OUT_VARIANTS,
    MISFIT_ALREADY_GREEN,
    SECOND_BUG_VARIANT,
    CountingProvider,
    create_assertion_run,
    crystal_stack,
    learn_script,
    make_assertion_repo,
    run_learn,
    run_with_planner,
)

from app.kernel.compute.coding_crystals import (  # noqa: E402
    CodingCrystalExtractor,
    CodingCrystalPlanner,
    replay_candidate,
)

FAMILY = "fix-failing-assertion"
REUSE_VARIANT = {"module": "billing", "constant": "FEE", "actual": 11, "expected": 13, "function": "fee"}


def _events(result, event_type):
    return [e["payload"] for e in result["events"] if e["event_type"] == event_type]


def _replay_succeeded(result) -> bool:
    observations = result["observations"]
    crystal_replace = any(o["tool_id"] == "worktree.replace_exact" for o in observations)
    return (result["final"]["state"] == "completed" and result["envelope"].verification["passed"] is True
            and result["provider"].calls == 0 and bool(_events(result, "agent.crystal.completed")) and crystal_replace)


@pytest.fixture(scope="module")
def fabric(tmp_path_factory):
    base = tmp_path_factory.mktemp("fabric")
    stack = crystal_stack(base / "stack")
    registry = stack["registry"]

    # B1: the exploratory model trajectory, metered and sealed into an Episode Envelope.
    learned = run_learn(base / "learn", base / "envelopes.sqlite3")
    assert learned["final"]["state"] == "completed"

    candidate = CodingCrystalExtractor().extract(learned["envelope"], learned["observations"], registry=registry)
    assert candidate is not None
    registry.add_candidate(candidate)

    replay_planner = CodingCrystalPlanner(registry, stack["authority"], stack["ledger"], replay_candidate_id=candidate.crystal_id)
    replays: dict[str, dict] = {}

    def run_variant(variant: dict) -> bool:
        result = run_with_planner(base / f"replay-{variant['module']}", replay_planner, variant=variant)
        replays[variant["module"]] = result
        return _replay_succeeded(result)

    receipt = replay_candidate(registry, candidate, list(HELD_OUT_VARIANTS), run_variant)
    misfit = run_with_planner(base / "replay-misfit", replay_planner, variant=MISFIT_ALREADY_GREEN)
    return {"base": base, "stack": stack, "registry": registry, "learned": learned, "candidate": candidate,
            "receipt": receipt, "replays": replays, "misfit": misfit}


def test_heldout_replay_on_three_variants_promotes(fabric):
    receipt = fabric["receipt"]
    assert receipt.promoted is True and receipt.attempts == 3 and receipt.successes == 3
    assert set(fabric["replays"]) == {v["module"] for v in HELD_OUT_VARIANTS}
    for result in fabric["replays"].values():
        assert result["final"]["budget"].get("model_turns", 0) == 0
    record = fabric["registry"].get(fabric["candidate"].crystal_id)
    assert record["status"] == "promoted"
    assert fabric["registry"].active_for_family(FAMILY).crystal_id == fabric["candidate"].crystal_id


def test_misfit_variant_is_refused_before_mutation(fabric):
    misfit = fabric["misfit"]
    assert _events(misfit, "agent.crystal.aborted")[0]["reason"] == "precondition_not_failing"
    assert "worktree.replace_exact" not in {o["tool_id"] for o in misfit["observations"]}
    assert not _replay_succeeded(misfit)


def test_reuse_reaches_same_verified_outcome_with_measured_gain(fabric, tmp_path):
    base = fabric["base"]
    stack = fabric["stack"]
    planner = CodingCrystalPlanner(stack["registry"], stack["authority"], stack["ledger"])
    script = learn_script(REUSE_VARIANT["module"], REUSE_VARIANT["constant"], REUSE_VARIANT["actual"], REUSE_VARIANT["expected"])

    # Baseline on the identical task without crystals: the model explores.
    baseline = run_with_planner(base / "reuse-baseline", None, variant=REUSE_VARIANT, provider=CountingProvider(script))
    # Reuse: the promoted crystal plans; the same scripted model is only a fallback.
    reuse = run_with_planner(base / "reuse-crystal", planner, variant=REUSE_VARIANT, provider=CountingProvider(script))

    for result in (baseline, reuse):
        assert result["final"]["state"] == "completed"
        assert result["envelope"].verification["passed"] is True
        assert (Path(result["engine"].workspace_root) / "billing.py").read_text().startswith("FEE = 11")  # main tree untouched
    b1, b2 = baseline["final"]["budget"], reuse["final"]["budget"]
    assert b2.get("model_turns", 0) <= 0.5 * b1["model_turns"]
    assert b2["tool_calls"] <= 0.7 * b1["tool_calls"]
    assert b2.get("tokens_total", 0) <= b1["tokens_total"]
    assert reuse["provider"].calls == 0
    assert _events(reuse, "agent.crystal.completed")
    assert fabric["registry"].get(fabric["candidate"].crystal_id)["reuse_count"] >= 1
    report = {
        "baseline": {k: b1.get(k, 0) for k in ("model_turns", "tool_calls", "tokens_total", "wall_ms")},
        "reuse": {k: b2.get(k, 0) for k in ("model_turns", "tool_calls", "tokens_total", "wall_ms")},
        "ratios": {"model_turns": b2.get("model_turns", 0) / b1["model_turns"], "tool_calls": b2["tool_calls"] / b1["tool_calls"]},
    }
    print("CRYSTAL_FABRIC_EFFICIENCY " + json.dumps(report, sort_keys=True))


def test_crystal_cannot_use_tools_outside_reviewed_ops(fabric, tmp_path):
    """Even a registry rewrite with recomputed digests cannot smuggle an unreviewed tool into a recipe."""
    from app.kernel.compute.coding_crystals import CodingCrystalRegistry, _digest

    registry = CodingCrystalRegistry(tmp_path / "copy.sqlite3")
    registry.add_candidate(fabric["candidate"])
    record = registry.get(fabric["candidate"].crystal_id)
    record.pop("candidate_object")
    steps = [dict(step) for step in record["candidate"]["steps"]]
    steps[4] = {"opcode": "worktree.replace_exact", "tool_id": "workspace.write_file", "expect": ""}
    record["candidate"]["steps"] = steps
    body = dict(record["candidate"])
    body.pop("digest")
    body.pop("crystal_id")
    record["candidate"]["digest"] = _digest(body)
    record["status"] = "promoted"
    record["record_digest"] = ""
    record["record_digest"] = _digest(record)
    with sqlite3.connect(registry.path) as connection:
        connection.execute("UPDATE coding_crystals SET status='promoted', payload=?, record_digest=?",
                           (json.dumps(record, sort_keys=True), record["record_digest"]))
    with pytest.raises(ValueError):
        registry.get(fabric["candidate"].crystal_id)
    assert registry.active_for_family(FAMILY) is None


def test_used_capability_cannot_be_replayed(fabric, tmp_path):
    stack = fabric["stack"]
    planner = CodingCrystalPlanner(stack["registry"], stack["authority"], stack["ledger"])
    root = make_assertion_repo(tmp_path / "repo", **HELD_OUT_VARIANTS[1])
    engine, run_id = create_assertion_run(root, module=HELD_OUT_VARIANTS[1]["module"])
    run = engine.store.get_run(run_id)
    session = planner.activate(run, run_id, engine=engine)
    assert session is not None
    assert planner.activate(run, run_id, engine=engine, capability=session.capability) is None
    reasons = [e["payload"]["reason"] for e in engine.store.events(run_id, limit=200) if e["event_type"] == "agent.crystal.refused"]
    assert any("already consumed" in reason for reason in reasons)


def test_failing_recipe_is_demoted_and_no_longer_served(fabric, tmp_path):
    # Runs last on purpose: it demotes the shared promoted crystal.
    stack = fabric["stack"]
    planner = CodingCrystalPlanner(stack["registry"], stack["authority"], stack["ledger"])
    failing = run_with_planner(tmp_path / "second-bug", planner, variant=SECOND_BUG_VARIANT)
    crystal_id = fabric["candidate"].crystal_id
    assert _events(failing, "agent.crystal.aborted")[-1]["reason"] == "postcondition_failed"
    assert fabric["registry"].get(crystal_id)["status"] == "demoted"
    assert fabric["registry"].active_for_family(FAMILY) is None
    after = run_with_planner(tmp_path / "after-demotion", planner, variant=HELD_OUT_VARIANTS[2])
    assert not _events(after, "agent.crystal.activated")
    assert after["provider"].calls >= 1

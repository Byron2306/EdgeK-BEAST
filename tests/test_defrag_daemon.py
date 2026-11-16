"""Experimental Task 3: Defragmentation Daemon (IEI v0.9 §7.12 Table 14) — dry-run first, reversible, receipted."""
from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

from app.kernel.compute.coding_crystals import CodingCrystalRegistry
from app.kernel.governance.governor_spine import ComputeGovernorSpine

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_crystal_lattice_spine import STEPS, crystal, passing  # noqa: E402

from app.kernel.compute.defrag_daemon import APPLY_ENV, DAEMON_ENV, DefragDaemon  # noqa: E402

ON = {DAEMON_ENV: "1"}
APPLY = {DAEMON_ENV: "1", APPLY_ENV: "1"}
NEAR_STEPS = STEPS[:1] + ({"opcode": "worktree.inspect", "tool_id": "workspace.read_range", "expect": ""},) + STEPS[1:]


@pytest.fixture
def reg(tmp_path):
    registry = CodingCrystalRegistry(tmp_path / "registry.sqlite3")
    ids = {}
    for name, steps in (("a", STEPS), ("a_dup", STEPS), ("near", NEAR_STEPS)):
        c = crystal(f"run-{name}", steps=steps)
        registry.add_candidate(c)
        registry.promote(c.crystal_id, passing(c.crystal_id))
        ids[name] = c.crystal_id
    registry.record_reuse(ids["a"], run_id="r1", outcome="verified")
    stale = crystal("run-stale", family="old-family")
    registry.add_candidate(stale)
    ids["stale"] = stale.crystal_id
    return registry, ids, tmp_path


def make(reg, env=ON, verifier=None, now=None, governor=None):
    registry, _ids, tmp = reg
    return DefragDaemon(registry=registry, ledger_path=tmp / "defrag" / "ledger.jsonl", env=env,
                        governor=governor or ComputeGovernorSpine(enforce=True), merge_verifier=verifier,
                        stale_after_s=3600, clock=(lambda: now) if now else time.time)


def test_flag_default_off(reg):
    with pytest.raises(PermissionError, match=DAEMON_ENV):
        make(reg, env={}).plan()


def test_plan_is_dry_run_and_mutates_nothing(reg):
    registry, ids, _ = reg
    plan = make(reg, now=time.time() + 7200).plan()
    assert plan["dry_run"] is True
    dupes = plan["exact_duplicates"]
    assert dupes == [{"keep": ids["a"], "supersede": ids["a_dup"], "reason": "identical_program"}]
    assert any(n["keep"] == ids["a"] and n["candidate"] == ids["near"] for n in plan["near_duplicate_nominations"])
    assert all(n["granted"] is False for n in plan["near_duplicate_nominations"])  # similarity nominates, never grants
    assert ids["stale"] in [s["crystal_id"] for s in plan["stale"]]
    assert registry.get(ids["a_dup"])["status"] == "promoted"
    assert registry.get(ids["stale"])["status"] == "candidate"


def test_apply_without_apply_flag_refuses(reg):
    with pytest.raises(PermissionError, match=APPLY_ENV):
        make(reg).apply()


def test_apply_is_receipted_and_reversible(reg):
    registry, ids, _ = reg
    daemon = make(reg, env=APPLY, now=time.time() + 7200)
    result = daemon.apply()
    assert result["governor"]["outcome"] == "admit"
    assert registry.get(ids["a_dup"])["status"] == "superseded"
    assert registry.get(ids["a_dup"])["receipt"]["promoted"] is True  # proof receipt never deleted
    assert registry.get(ids["stale"])["status"] == "retired_stale"
    assert registry.get(ids["near"])["status"] == "promoted"  # no proof → no merge
    assert registry.active_for_family("fix-failing-assertion").crystal_id in {ids["a"], ids["near"]}
    assert daemon.verify_ledger()["valid"] is True
    for receipt in result["receipts"]:
        daemon.undo(receipt["receipt_id"])
    assert registry.get(ids["a_dup"])["status"] == "promoted"
    assert registry.get(ids["stale"])["status"] == "candidate"
    ledger = daemon.ledger_entries()
    assert [e["op"] for e in ledger].count("undo") == len(result["receipts"])
    with pytest.raises(LookupError):
        daemon.undo(result["receipts"][0]["receipt_id"])  # already undone


def test_near_duplicate_merges_only_with_proof(reg):
    registry, ids, _ = reg
    calls = []

    def verifier(keep, candidate):
        calls.append((keep, candidate))
        return {"passed": True, "evidence_digest": "sha256:" + "f" * 64, "method": "held_out_replay_equivalence"}

    result = make(reg, env=APPLY, verifier=verifier).apply()
    assert (ids["a"], ids["near"]) in calls
    assert registry.get(ids["near"])["status"] == "superseded"
    merged = [r for r in result["receipts"] if r["crystal_id"] == ids["near"]][0]
    assert merged["proof"]["evidence_digest"].startswith("sha256:")


def test_failed_proof_keeps_both(reg):
    registry, ids, _ = reg
    make(reg, env=APPLY, verifier=lambda k, c: {"passed": False}).apply()
    assert registry.get(ids["near"])["status"] == "promoted"


def test_tampered_ledger_is_detected(reg):
    daemon = make(reg, env=APPLY, now=time.time() + 7200)
    daemon.apply()
    text = daemon.ledger_path.read_text().replace("superseded", "promoted", 1)
    daemon.ledger_path.write_text(text)
    assert daemon.verify_ledger()["valid"] is False


def test_compaction_vacuums_without_deleting_rows(reg):
    registry, ids, _ = reg
    out = make(reg, env=APPLY).compact()
    assert out["rows_before"] == out["rows_after"]
    assert out["bytes_after"] <= out["bytes_before"]
    assert {registry.get(i)["crystal_id"] for i in ids.values()} == set(ids.values())

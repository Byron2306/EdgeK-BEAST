"""Defrag daemon x Memory Hull (Addendum A §7.14.1): dry-run plan, governed reversible quarantine, never delete."""
from __future__ import annotations

import hashlib
import json
import time

import pytest

from app.kernel.compute.coding_crystals import CodingCrystalRegistry
from app.kernel.compute.defrag_daemon import APPLY_ENV, DAEMON_ENV, DefragDaemon
from app.kernel.governance.governor_spine import ComputeGovernorSpine
from app.kernel.security.residue_seal import ResidueSeal
from app.kernel.storage.memory_hull import MemoryHull

ON = {DAEMON_ENV: "1"}
APPLY = {DAEMON_ENV: "1", APPLY_ENV: "1"}


def _tree(root):
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*")) if p.is_file()}


@pytest.fixture
def hull(tmp_path):
    h = MemoryHull(tmp_path / "vault", seal=ResidueSeal(tmp_path / "keys"))
    first = h.write_residue(task="fix login", provider="local", decision="patched auth", section="tasks")
    time.sleep(0.002)
    dupe = h.write_residue(task="fix login", provider="local", decision="patched auth", section="tasks")
    other = h.write_residue(task="ship docs", provider="local", decision="wrote docs", section="decisions")
    return h, first, dupe, other


def daemon(tmp_path, h, env=ON):
    registry = CodingCrystalRegistry(tmp_path / "crystals.sqlite")
    return DefragDaemon(registry=registry, ledger_path=tmp_path / "defrag" / "ledger.jsonl", env=env,
                        governor=ComputeGovernorSpine(enforce=True), hull=h)


def test_hull_plan_flag_off_and_dry_run(tmp_path, hull):
    h, first, dupe, _ = hull
    with pytest.raises(PermissionError):
        daemon(tmp_path, h, env={}).plan_hull()
    before = _tree(h.root)
    plan = daemon(tmp_path, h).plan_hull()
    assert _tree(h.root) == before and plan["dry_run"] is True
    assert plan["exact_duplicates"] == [{"keep": first["residue_id"], "quarantine": dupe["residue_id"],
                                         "section": "tasks", "reason": "identical_residue_content"}]
    assert plan["verified"] == 3 and plan["review_failed"] == [] and plan["index_drift"]["unindexed"] == []


def test_hull_plan_reports_edits_and_index_drift_without_acting(tmp_path, hull):
    h, first, _, other = hull
    md = h.root / "decisions" / f"{other['residue_id']}.md"
    md.write_text(md.read_text() + "\noperator edit\n")  # vault is editable: report, never quarantine
    index_path = h.root / ".index" / "residue_index.json"
    index = json.loads(index_path.read_text())
    index["records"] = [r for r in index["records"] if r["residue_id"] != first["residue_id"]]
    index_path.write_text(json.dumps(index))
    plan = daemon(tmp_path, h).plan_hull()
    assert [f["residue_id"] for f in plan["review_failed"]] == [other["residue_id"]]
    assert plan["review_failed"][0]["action"] == "operator_review_or_reseal"
    assert plan["index_drift"]["unindexed"] == [first["residue_id"]]


def test_hull_apply_quarantines_reversibly_with_hash_chained_receipts(tmp_path, hull):
    h, first, dupe, _ = hull
    with pytest.raises(PermissionError):
        daemon(tmp_path, h).apply_hull()
    d = daemon(tmp_path, h, env=APPLY)
    files_before = _tree(h.root)
    out = d.apply_hull()
    assert out["governor"]["outcome"] == "admit"
    q = [r for r in out["receipts"] if r["op"] == "hull_quarantine"]
    assert len(q) == 1 and q[0]["residue_id"] == dupe["residue_id"]
    moved = {f["original"]: f for f in q[0]["files"]}
    assert set(moved) == {f"tasks/{dupe['residue_id']}.md", f"tasks/{dupe['residue_id']}.residue.json"}
    for rel, f in moved.items():
        assert not (h.root / rel).exists()
        assert hashlib.sha256((h.root / f["quarantined"]).read_bytes()).hexdigest() == files_before[rel] == f["sha256"][7:]
    ids = [r["residue_id"] for r in h.list_residue(limit=100)]
    assert dupe["residue_id"] not in ids and first["residue_id"] in ids
    assert h.inventory(verify=True)["verified_sidecars"] == 2
    assert d.verify_ledger()["valid"] is True
    undo = d.undo(q[0]["receipt_id"])
    assert undo["op"] == "undo" and _tree(h.root).keys() >= files_before.keys()
    assert {k: v for k, v in _tree(h.root).items() if k in files_before and not k.startswith(".index")} == \
        {k: v for k, v in files_before.items() if not k.startswith(".index")}
    assert dupe["residue_id"] in [r["residue_id"] for r in h.list_residue(limit=100)]
    with pytest.raises(LookupError):
        d.undo(q[0]["receipt_id"])
    assert d.verify_ledger()["valid"] is True


def test_hull_undo_refuses_tampered_quarantine(tmp_path, hull):
    h, _, dupe, _ = hull
    d = daemon(tmp_path, h, env=APPLY)
    receipt = next(r for r in d.apply_hull()["receipts"] if r["op"] == "hull_quarantine")
    md = next(f for f in receipt["files"] if f["original"].endswith(".md"))
    (h.root / md["quarantined"]).write_text("tampered")
    with pytest.raises(PermissionError):
        d.undo(receipt["receipt_id"])
    assert not (h.root / md["original"]).exists()

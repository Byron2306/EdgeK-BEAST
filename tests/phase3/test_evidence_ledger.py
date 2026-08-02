from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from app.kernel.evidence.evidence_ledger import EvidenceLedger
from app.kernel.evidence.evidence_store import EvidenceStore
from tests.phase3.test_evidence_crystallization import _promoted_run
from app.kernel.evidence.evidence_builder import EvidenceBuilder


def _crystal(tmp_path: Path, suffix: str = "a") -> tuple[Path, dict]:
    base = tmp_path / suffix
    base.mkdir(parents=True, exist_ok=True)
    root, run_id = _promoted_run(base)
    return root, EvidenceBuilder(root).crystallize(run_id)


def test_created_event_and_chain_verify(tmp_path: Path):
    root, crystal = _crystal(tmp_path)
    ledger = EvidenceLedger(root)
    events = ledger.events(crystal["evidence_id"])
    assert [item["kind"] for item in events] == ["created"]
    result = ledger.verify(crystal["evidence_id"])
    assert result["ok"] is True
    assert result["state"]["status"] == "active"


def test_usage_and_metrics_are_append_only(tmp_path: Path):
    root, crystal = _crystal(tmp_path)
    ledger = EvidenceLedger(root)
    ledger.record_use(crystal["evidence_id"], run_id="run-reuse-1", outcome="adapted")
    ledger.record_metric(crystal["evidence_id"], name="tokens_saved", value=1200, unit="tokens")
    state = ledger.state(crystal["evidence_id"])
    assert state["usage_count"] == 1
    assert state["metrics"]["tokens_saved"]["value"] == 1200.0
    assert len(ledger.events(crystal["evidence_id"])) == 3


def test_revocation_blocks_future_use_without_mutating_crystal(tmp_path: Path):
    root, crystal = _crystal(tmp_path)
    ledger = EvidenceLedger(root)
    before = EvidenceStore(root).get(crystal["evidence_id"])
    ledger.revoke(crystal["evidence_id"], reason="new vulnerability", actor="Human Operator")
    with pytest.raises(PermissionError):
        ledger.record_use(crystal["evidence_id"], run_id="run-2")
    after = EvidenceStore(root).get(crystal["evidence_id"])
    assert after == before
    assert ledger.state(crystal["evidence_id"])["status"] == "revoked"


def test_supersession_links_successor(tmp_path: Path):
    root1, first = _crystal(tmp_path, "one")
    # Put a second immutable object into the same ledger store to exercise linkage.
    store = EvidenceStore(root1)
    second = dict(first)
    second["evidence_id"] = "crystal-successor"
    second["run_id"] = "run-successor"
    from app.kernel.evidence.evidence_digest import sha256_digest
    second["evidence_digest"] = sha256_digest({k: v for k, v in second.items() if k != "evidence_digest"})
    store.put(second)
    ledger = EvidenceLedger(root1)
    ledger.append(second["evidence_id"], "created", {"run_id": "run-successor"}, actor="test")
    ledger.supersede(first["evidence_id"], successor_evidence_id=second["evidence_id"], reason="stronger proof", actor="Human Operator")
    state = ledger.state(first["evidence_id"])
    assert state["status"] == "superseded"
    assert state["successor_evidence_id"] == second["evidence_id"]


def test_tampered_ledger_event_is_detected(tmp_path: Path):
    root, crystal = _crystal(tmp_path)
    ledger = EvidenceLedger(root)
    ledger.record_metric(crystal["evidence_id"], name="latency_saved", value=3.5, unit="seconds")
    with sqlite3.connect(EvidenceStore(root).db_path) as connection:
        connection.execute("UPDATE evidence_ledger_events SET payload_json=? WHERE evidence_id=? AND sequence=2", ('{"name":"latency_saved","value":999,"unit":"seconds"}', crystal["evidence_id"]))
    result = ledger.verify(crystal["evidence_id"])
    assert result["ok"] is False
    assert result["reason"] == "ledger_chain_mismatch"

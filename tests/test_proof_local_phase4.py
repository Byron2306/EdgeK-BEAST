from __future__ import annotations

import json
from pathlib import Path

from app.kernel.security.crystal_chain import CrystalChainLedger
from app.kernel.security.crystal_chain_witness import CrystalChainWitnessStore
from app.kernel.security.crystal_lattice_ledger import CrystalLatticeLedger


def test_lattice_ledger_is_append_only_and_defrag_does_not_rewrite(tmp_path: Path) -> None:
    ledger = CrystalLatticeLedger(tmp_path / "lattice")
    first = ledger.append({
        "beast_object_type": "crystal_lattice_checkpoint_payload",
        "artifacts": {"capability_lattice_hash": "sha256:" + "1" * 64, "matrix_file_hash": "sha256:" + "2" * 64},
        "dimension": 64,
        "rank": 4,
    })
    second = ledger.append({
        "beast_object_type": "crystal_lattice_checkpoint_payload",
        "artifacts": {"capability_lattice_hash": "sha256:" + "1" * 64, "matrix_file_hash": "sha256:" + "3" * 64},
        "dimension": 64,
        "rank": 4,
    })
    assert second["previous_hash"] == first["checkpoint_hash"]
    assert ledger.verify().valid is True
    snapshot = ledger.defrag()
    assert snapshot["checkpoint_count"] == 2
    assert snapshot["claim_boundary"] == "defrag_snapshot_indexes_latest_heads_only_no_history_rewrite"
    assert len(ledger.checkpoints()) == 2

    rows = [json.loads(line) for line in ledger.ledger_path.read_text(encoding="utf-8").splitlines()]
    rows[0]["payload"]["dimension"] = 128
    ledger.ledger_path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
    verification = ledger.verify()
    assert verification.valid is False
    assert any(item["reason"] == "payload_hash_mismatch" for item in verification.errors)


def test_cross_signed_chain_heads_detect_rollback_and_fork(tmp_path: Path) -> None:
    chain_path = tmp_path / "chain.jsonl"
    chain = CrystalChainLedger(chain_path, node_id="node-a")
    chain.append("event_one", "a", {"safe": True})
    chain.append("event_two", "b", {"safe": True})

    witness = CrystalChainWitnessStore(tmp_path / "witness", node_id="node-b")
    attestation = witness.attest_chain_head(chain, lattice_head_hash="sha256:" + "4" * 64)
    record = witness.witness(attestation, peer_id="node-a")
    assert record["verification"]["verified"] is True
    clean = witness.audit_chain(chain)
    assert clean["verdict"] == "ok"
    assert clean["promotion_allowed"] is True

    rollback_path = tmp_path / "rollback.jsonl"
    rollback_path.write_text(chain_path.read_text(encoding="utf-8").splitlines()[0] + "\n", encoding="utf-8")
    rollback = CrystalChainLedger(rollback_path, node_id="node-a")
    rollback_audit = witness.audit_chain(rollback)
    assert rollback_audit["verdict"] == "quarantine"
    assert "rollback_detected" in rollback_audit["reasons"]
    assert rollback_audit["promotion_allowed"] is False

    fork_path = tmp_path / "fork.jsonl"
    rows = [json.loads(line) for line in chain_path.read_text(encoding="utf-8").splitlines()]
    rows[-1]["payload"]["safe"] = "tampered"
    fork_path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
    fork = CrystalChainLedger(fork_path, node_id="node-a")
    fork_audit = witness.audit_chain(fork)
    assert fork_audit["verdict"] == "quarantine"
    assert fork_audit["promotion_allowed"] is False


def test_attestation_tamper_fails_signature(tmp_path: Path) -> None:
    chain = CrystalChainLedger(tmp_path / "chain.jsonl", node_id="node-a")
    chain.append("event", "a", {"safe": True})
    witness = CrystalChainWitnessStore(tmp_path / "witness", node_id="node-b")
    attestation = witness.attest_chain_head(chain)
    assert witness.verify_attestation(attestation)["verified"] is True
    attestation["head_hash"] = "sha256:" + "f" * 64
    assert witness.verify_attestation(attestation)["verified"] is False

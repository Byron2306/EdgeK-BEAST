#!/usr/bin/env python3
"""Run Phase 4 cross-signed chain-head and append-only lattice gauntlet."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.kernel.crystal_chain import CrystalChainLedger
from app.kernel.crystal_chain_witness import CrystalChainWitnessStore
from app.kernel.crystal_lattice_ledger import CrystalLatticeLedger


def main() -> int:
    parser = argparse.ArgumentParser(description="Run BEAST Proof-Local Phase 4 witness gauntlet")
    parser.add_argument("--root", default="benchmarks/results/proof_local_phase4")
    parser.add_argument("--distillation-root", default="benchmarks/results/crystal_to_adapter_distillation")
    args = parser.parse_args()

    root = Path(args.root)
    root.mkdir(parents=True, exist_ok=True)
    chain_path = root / "node_a_chain.jsonl"
    chain = CrystalChainLedger(chain_path, node_id="phase4-node-a")
    lattice = CrystalLatticeLedger(root / "lattice")

    checkpoint = lattice.append_latest(distillation_root=Path(args.distillation_root))
    defrag = lattice.defrag()
    chain.append("lattice_checkpoint_appended", str(checkpoint["checkpoint_hash"]), {
        "checkpoint_hash": checkpoint["checkpoint_hash"],
        "lattice_head_hash": lattice.verify().head_hash,
        "private_payload_exported": False,
    })
    chain.append("lattice_defrag_snapshot", str(defrag["snapshot_hash"]), {
        "snapshot_hash": defrag["snapshot_hash"],
        "ledger_head_hash": defrag["ledger_head_hash"],
        "private_payload_exported": False,
    })

    witness_b = CrystalChainWitnessStore(root / "witness_b", node_id="phase4-node-b")
    witness_c = CrystalChainWitnessStore(root / "witness_c", node_id="phase4-node-c")
    attestation = witness_b.attest_chain_head(chain, lattice_head_hash=lattice.verify().head_hash)
    record_b = witness_b.witness(attestation, peer_id="phase4-node-a")
    record_c = witness_c.witness(attestation, peer_id="phase4-node-a")
    clean_audit = witness_b.audit_chain(chain)

    rollback_path = root / "node_a_chain_rollback.jsonl"
    lines = chain_path.read_text(encoding="utf-8").splitlines()
    rollback_path.write_text("\n".join(lines[:-1]) + ("\n" if len(lines) > 1 else ""), encoding="utf-8")
    rollback_chain = CrystalChainLedger(rollback_path, node_id="phase4-node-a")
    rollback_audit = witness_b.audit_chain(rollback_chain)

    fork_path = root / "node_a_chain_fork.jsonl"
    shutil.copyfile(chain_path, fork_path)
    fork_chain = CrystalChainLedger(fork_path, node_id="phase4-node-a")
    rows = [json.loads(line) for line in fork_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if rows:
        rows[-1]["payload"]["fork_marker"] = "silent_rewrite"
        fork_path.write_text("\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n", encoding="utf-8")
    fork_audit = witness_b.audit_chain(fork_chain)

    receipt = {
        "beast_object_type": "proof_local_phase4_chain_witness_receipt",
        "version": "1.0",
        "status": "implemented",
        "lattice": {
            "checkpoint_hash": checkpoint["checkpoint_hash"],
            "ledger_head_hash": lattice.verify().head_hash,
            "defrag_snapshot_hash": defrag["snapshot_hash"],
            "defrag_rewrites_history": False,
            "verification": lattice.verify().to_dict(),
        },
        "attestation": {
            "attestation_id": attestation["attestation_id"],
            "head_hash": attestation["head_hash"],
            "height": attestation["height"],
            "signature_algorithm": (attestation.get("signature") or {}).get("algorithm"),
            "verified_by_b": record_b["verification"]["verified"],
            "verified_by_c": record_c["verification"]["verified"],
            "private_payload_exported": attestation["private_payload_exported"],
        },
        "audits": {
            "clean": clean_audit,
            "rollback": rollback_audit,
            "fork": fork_audit,
        },
        "exit_criteria": {
            "node_head_signing": bool((attestation.get("signature") or {}).get("signature_b64")),
            "peer_witnessing": record_b["verification"]["verified"] and record_c["verification"]["verified"],
            "rollback_detected": rollback_audit["verdict"] == "quarantine" and "rollback_detected" in rollback_audit["reasons"],
            "fork_detected": fork_audit["verdict"] == "quarantine",
            "consensus_failure_cannot_promote": not rollback_audit["promotion_allowed"] and not fork_audit["promotion_allowed"],
            "private_payloads_remain_local": attestation["private_payload_exported"] is False,
            "append_only_lattice_defrag": defrag["claim_boundary"] == "defrag_snapshot_indexes_latest_heads_only_no_history_rewrite",
        },
    }
    out = root / "proof_local_phase4_chain_witness_latest.json"
    out.write_text(json.dumps(receipt, indent=2, sort_keys=True), encoding="utf-8")
    latest = Path("benchmarks/results/proof_local_phase4_chain_witness_latest.json")
    latest.parent.mkdir(parents=True, exist_ok=True)
    latest.write_text(json.dumps(receipt, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0 if all(receipt["exit_criteria"].values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())

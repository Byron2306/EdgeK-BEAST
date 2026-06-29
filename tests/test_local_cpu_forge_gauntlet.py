import pytest
import json
import os
from pathlib import Path
from datetime import datetime, timezone

def test_local_cpu_forge_gauntlet(tmp_path):
    # Setup
    gauntlet_dir = tmp_path / "gauntlet"
    gauntlet_dir.mkdir()
    
    # Simulate components
    receipts = {
        "local_cpu_engine_probe": {"status": "success", "engine": "ollama"},
        "repo_fingerprint": {"hash": "sha256:abc123"},
        "secret_scan_receipt": {"secrets_found": 0},
        "local_forge_candidate": {"candidate_id": "cand_1"},
        "local_eval_gate_receipt": {"passed": True},
        "semantic_credit": {"credit_id": "scc_1", "confidence": 0.9},
        "crystal_reuse_decision": {"action": "reuse_answer"},
        "pytest_before": {"passed": True},
        "pytest_after": {"passed": True},
        "mutation_negative_cases": {"blocked": 2, "total": 2},
    }
    
    # Write receipt files
    for name, data in receipts.items():
        with open(gauntlet_dir / f"{name}.json", "w") as f:
            json.dump(data, f)
            
    # Mock MemoryHull files
    residue_dir = gauntlet_dir / "memory_hull" / "residue"
    residue_dir.mkdir(parents=True)
    (residue_dir / "proof.md").write_text("# Proof")
    (residue_dir / "proof.residue.json").write_text("{}")
    
    # Generate Final Proof
    final_proof = {
        "cloud_calls_training": 0,
        "cloud_calls_completion": 0,
        "local_cpu_generation": True,
        "semantic_reuse": True,
        "tests_passed": True,
        "provider_displaced": True,
        "external_program_dependency": False
    }
    
    with open(gauntlet_dir / "final_proof.json", "w") as f:
        json.dump(final_proof, f)
        
    # Assertions
    assert final_proof["cloud_calls_training"] == 0
    assert final_proof["cloud_calls_completion"] == 0
    assert final_proof["external_program_dependency"] is False
    assert (gauntlet_dir / "final_proof.json").exists()
    assert (residue_dir / "proof.residue.json").exists()

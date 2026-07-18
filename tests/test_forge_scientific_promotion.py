from app.kernel.capability.capability_crystallization import CapabilityCrystallizationEngine
from app.kernel.compute.compute_forge import CentralForgePromotionCollector


def proposal(evidence=None):
    return {"candidate_proposals": [{
        "node_id": "forge-1", "candidate_name": "sha256_residual", "task_class": "digest",
        "transform_type": "deterministic", "shadow_runs": 3, "hidden_test_successes": 3,
        "rollback_successes": 3, "behavior_preserved_count": 3,
        "impact_fingerprint": {}, "scientific_evidence": evidence or {},
    }]}


def test_central_forge_promotion_blocks_benchmark_counts_without_scientific_receipts(tmp_path):
    collector = CentralForgePromotionCollector(CapabilityCrystallizationEngine(storage_path=tmp_path))
    result = collector.ingest_snapshot(proposal())
    assert result["promoted"] == []
    assert result["blocked"][0]["reason"] == "scientific_evidence_required"


def test_central_forge_accepts_bound_heldout_and_displacement_evidence(tmp_path):
    evidence = {
        "heldout_ablation": {"receipt_id": "ab:1", "verified": True, "held_out": True},
        "displacement": {"receipt_id": "disp:1", "verified": True, "provider_calls_avoided": 4},
    }
    collector = CentralForgePromotionCollector(CapabilityCrystallizationEngine(storage_path=tmp_path))
    result = collector.ingest_snapshot(proposal(evidence))
    assert not any(item.get("reason") == "scientific_evidence_required" for item in result["blocked"])

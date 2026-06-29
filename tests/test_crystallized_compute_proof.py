from app.kernel.compute.crystallized_compute_proof import (
    CrystallizedComputeProofConfig,
    CrystallizedComputeProofHarness,
)


def test_repeated_cloud_calls_become_local_crystallized_completion(tmp_path):
    proof = CrystallizedComputeProofHarness(
        CrystallizedComputeProofConfig(root=tmp_path, repetitions=3)
    ).run()

    completion = proof["completion"]

    assert proof["verdict"] == "proved"
    assert proof["training_observations"] == 3
    assert proof["training_cloud_calls"] == 3
    assert proof["execution_lineage"]["teacher_engine"] == "nvidia_nim_or_external_teacher"
    assert proof["execution_lineage"]["runtime_engine"] == "beast_local_semantic_cache"
    assert proof["execution_lineage"]["cloud_used_for_training"] is True
    assert proof["execution_lineage"]["cloud_used_for_completion"] is False
    assert completion["cloud_calls_during_completion"] == 0
    assert completion["provider_displaced"] is True
    assert completion["completed_locally"] is True
    assert completion["decision"]["action"] == "reuse_semantic_credit"
    assert completion["answer"].startswith("COMPLETE:")
    assert proof["lattice"]["signal_count"] == 3
    assert proof["lattice"]["top_node"]["positive_count"] == 3
    assert proof["capability"]["promotion_status"] == "promoted"
    assert proof["capability"]["fingerprint_boundary"]["valid"] is True
    assert all(page["lookup_hit"] for page in proof["semantic_pages"].values())
    assert proof["fused_crystal"]["seal_verified"] is True
    assert proof["fused_crystal"]["component_counts"]["meta_tools"] >= 1
    assert proof["fused_crystal"]["component_counts"]["skills"] >= 1
    assert proof["fused_crystal"]["component_counts"]["unique_crystals"] == 1
    assert proof["fused_crystal"]["component_counts"]["reuse_observations"] == 3
    assert proof["metrics"]["runtime_tokens_avoided"] > 0
    assert proof["metrics"]["capability_total_compute_displaced_tokens"] == proof["metrics"]["runtime_tokens_avoided"]
    assert proof["memory_hull"]["sections"]["residue"]["sidecars"] >= 3
    assert proof["memory_hull"]["failed_sidecars"] == 0
    assert proof["route_optimizer_choice"] == "beast_local_semantic_cache"
    assert proof["trace_ledger_bytes"] > 0

from app.kernel.compute.crystallized_compute_proof import (
    CrystallizedCodeRepairMegaGauntlet,
    CrystallizedOpusNIMGatewayMegaGauntlet,
)


def test_crystallized_code_repair_mega_gauntlet_repairs_actual_code(tmp_path):
    receipt = CrystallizedCodeRepairMegaGauntlet(tmp_path).run()
    proof = receipt["crystallized_compute_proof"]

    assert receipt["gauntlet_passed"] is True
    assert receipt["baseline_verification"]["tests_passed"] is False
    assert receipt["skill_verification"]["py_compile_passed"] is True
    assert receipt["skill_verification"]["tests_passed"] is True
    assert receipt["tool_receipt"]["tool"] == "python_ast_function_rewriter"
    assert proof["verdict"] == "proved"
    assert proof["training_cloud_calls"] == 3
    assert proof["training_observations"] == 3
    assert proof["execution_lineage"]["teacher_engine"] == "nvidia_nim_or_external_teacher"
    assert proof["execution_lineage"]["runtime_engine"] == "beast_local_semantic_cache"
    assert proof["execution_lineage"]["cloud_used_for_completion"] is False
    assert proof["completion"]["decision"]["action"] == "reuse_semantic_credit"
    assert proof["completion"]["cloud_calls_during_completion"] == 0
    assert proof["completion"]["completed_locally"] is True
    assert proof["fused_crystal"]["component_counts"]["meta_tools"] >= 3
    assert proof["fused_crystal"]["component_counts"]["skills"] >= 2
    assert proof["fused_crystal"]["component_counts"]["unique_crystals"] == 1
    assert proof["fused_crystal"]["component_counts"]["reuse_observations"] == 3
    assert proof["metrics"]["training_tokens_observed"] > 0
    assert proof["metrics"]["runtime_tokens_avoided"] > 0
    assert proof["metrics"]["capability_total_compute_displaced_tokens"] == proof["metrics"]["runtime_tokens_avoided"]
    assert proof["memory_hull"]["sections"]["residue"]["sidecars"] >= 3
    assert proof["memory_hull"]["failed_sidecars"] == 0
    assert proof["semantic_pages"]["route_card"]["lookup_hit"] is True
    assert "def calculate_discounted_total(price, percent):" in receipt["repaired_source_preview"]
    assert "clamped_percent = max(0.0, min(100.0, numeric_percent))" in receipt["repaired_source_preview"]


def test_crystallized_opus_nim_gateway_gauntlet_uses_tinyllama_case_shape(tmp_path):
    receipt = CrystallizedOpusNIMGatewayMegaGauntlet(tmp_path).run()
    proof = receipt["crystallized_compute_proof"]

    assert receipt["gauntlet_passed"] is True
    assert receipt["baseline_verification"]["tests_passed"] is False
    assert receipt["skill_verification"]["tests_passed"] is True
    assert receipt["tool_receipt"]["tool"] == "approved_patch_operations"
    assert receipt["tool_receipt"]["operation_count"] == 4
    assert receipt["reused_plan"]["beast_object_type"] == "OPUS_CASE_REPAIR_PLAN"
    assert receipt["approval_receipt"]["approved"] is True
    assert proof["verdict"] == "proved"
    assert proof["training_cloud_calls"] == 3
    assert proof["training_observations"] == 3
    assert proof["execution_lineage"]["teacher_engine"] == "nvidia_nim_or_external_teacher"
    assert proof["execution_lineage"]["runtime_engine"] == "beast_local_semantic_cache"
    assert proof["completion"]["cloud_calls_during_completion"] == 0
    assert proof["completion"]["decision"]["action"] == "reuse_semantic_credit"
    assert proof["fused_crystal"]["component_counts"]["meta_tools"] >= 4
    assert proof["fused_crystal"]["component_counts"]["unique_crystals"] == 1
    assert proof["fused_crystal"]["component_counts"]["reuse_observations"] == 3
    assert proof["metrics"]["training_tokens_observed"] > 0
    assert proof["metrics"]["runtime_tokens_avoided"] > 0
    assert proof["memory_hull"]["sections"]["residue"]["sidecars"] >= 3
    assert proof["memory_hull"]["failed_sidecars"] == 0
    assert {case["case_id"] for case in receipt["negative_cases"]} == {
        "wrong_provider_fingerprint",
        "changed_repo_fingerprint",
        "secret_present_in_response",
        "failed_pytest_not_promoted",
        "stale_lattice_hash",
        "same_task_different_risk_tier",
    }
    assert all(case["blocked"] is True for case in receipt["negative_cases"])
    assert "approval_gate" in [tool["name"] for tool in proof["completion"]["basis"]["tools"]]


def test_crystallized_opus_local_cpu_forge_gauntlet_needs_no_external_teacher(tmp_path, monkeypatch):
    monkeypatch.setenv("BEAST_LOCAL_ONLY", "1")
    monkeypatch.setenv("BEAST_FORGE_ENGINE", "deterministic_cpu_forge")
    monkeypatch.setenv("BEAST_DISABLE_CLOUD", "1")

    receipt = CrystallizedOpusNIMGatewayMegaGauntlet(tmp_path, local_only=True).run()
    proof = receipt["crystallized_compute_proof"]

    assert receipt["gauntlet_passed"] is True
    assert receipt["local_only"] is True
    assert receipt["cloud_disabled"] is True
    assert receipt["live_nim_receipts"] == []
    assert len(receipt["local_forge_receipts"]) == 3
    assert proof["training_observations"] == 3
    assert proof["training_cloud_calls"] == 0
    assert proof["cloud_calls_before"] == 0
    assert proof["cloud_calls_after"] == 0
    assert proof["execution_lineage"]["teacher_engine"] == "beast_local_cpu_forge"
    assert proof["execution_lineage"]["runtime_engine"] == "beast_local_semantic_cache"
    assert proof["execution_lineage"]["cloud_used_for_training"] is False
    assert proof["execution_lineage"]["cloud_used_for_completion"] is False
    assert proof["completion"]["decision"]["action"] == "reuse_semantic_credit"
    assert proof["completion"]["cloud_calls_during_completion"] == 0
    assert proof["metrics"]["cloud_calls_training"] == 0
    assert proof["metrics"]["cloud_calls_completion"] == 0
    assert proof["metrics"]["runtime_tokens_avoided"] > 0
    assert proof["fused_crystal"]["component_counts"]["unique_crystals"] == 1
    assert proof["fused_crystal"]["component_counts"]["reuse_observations"] == 3
    assert proof["memory_hull"]["sections"]["residue"]["sidecars"] >= 3
    assert all(case["blocked"] is True for case in receipt["negative_cases"])

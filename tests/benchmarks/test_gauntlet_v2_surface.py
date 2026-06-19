from pathlib import Path

from benchmarks import gauntlet_v2_surface as surface


def test_manifest_matches_planned_gauntlet_shape():
    manifest = surface.build_run_manifest(task_count=30, trials=3)

    assert manifest["benchmark"] == "BEAST Gauntlet v2"
    assert manifest["planned_run_count"] == 30 * 6 * 5 * 3
    assert "models_route_works" in manifest["infra_gate_steps"]
    assert "source_patch_plan_schema" in manifest["contract_tests"]
    assert manifest["provider_model_hints"]["nvidia-nim-nemotron-super"] == "nvidia/nemotron-3-super-120b-a12b"
    assert manifest["separation_rule"]["infra_failure"].startswith("Provider is excluded")


def test_smoke_preset_is_small_and_diagnostic():
    preset = surface.smoke_preset()
    manifest = surface.build_run_manifest(
        providers=preset["providers"],
        lanes=preset["lanes"],
        task_count=preset["task_count"],
        trials=preset["trials"],
    )

    assert manifest["planned_run_count"] == 90
    assert preset["providers"] == [
        "huggingface-best-coding",
        "openrouter-best-coding",
        "nvidia-nim-nemotron-super",
    ]
    assert preset["lanes"] == [
        "raw-small-with-tests",
        "full-beast",
        "full-beast-provider-fitness",
    ]


def test_provider_fitness_hard_gates_are_separate_from_score():
    metrics = surface.ProviderMetrics(
        verified_success_rate=0.8,
        schema_valid_rate=0.9,
        patch_apply_rate=0.9,
        hidden_test_pass_rate=0.75,
        latency_per_success_score=0.7,
        cost_per_success_score=0.6,
        out_of_scope_safety_score=1.0,
        rollback_cleanliness_score=1.0,
        json_validity_rate=0.89,
        out_of_scope_edit_rate=0.01,
        syntax_error_rate=0.01,
        timeout_rate=0.01,
        rollback_success_rate=1.0,
    )

    scorecard = surface.provider_fitness(metrics)

    assert scorecard["score"] > 0
    assert scorecard["eligible_for_source_patching"] is False
    assert scorecard["hard_gates"]["json_validity_ge_90"] is False


def test_provider_fitness_allows_source_patching_when_gates_pass():
    metrics = surface.ProviderMetrics(
        verified_success_rate=1.0,
        schema_valid_rate=1.0,
        patch_apply_rate=1.0,
        hidden_test_pass_rate=1.0,
        latency_per_success_score=1.0,
        cost_per_success_score=1.0,
        out_of_scope_safety_score=1.0,
        rollback_cleanliness_score=1.0,
        json_validity_rate=0.95,
        out_of_scope_edit_rate=0.0,
        syntax_error_rate=0.0,
        timeout_rate=0.0,
        rollback_success_rate=1.0,
    )

    scorecard = surface.provider_fitness(metrics)

    assert scorecard["score"] == 1.0
    assert scorecard["eligible_for_source_patching"] is True


def test_nim_failure_buckets_keep_infra_and_capability_distinct():
    assert surface.classify_failure("nvidia-nim-super", "401 unauthorized", stage="infra") == "nim_infra_auth_failure"
    assert surface.classify_failure("nvidia-nim-super", "model_not_found", stage="infra") == "nim_model_not_found"
    assert surface.classify_failure("nvidia-nim-super", "schema did not match SourcePatchPlan") == "nim_schema_invalid"
    assert surface.classify_failure("nvidia-nim-super", "pytest failed after edits") == "nim_tests_failed"
    assert surface.classify_failure("openrouter", "pytest failed after edits") == "capability_failure"


def test_prepare_artifact_surface_writes_expected_files(tmp_path: Path):
    result = surface.prepare_artifact_surface(tmp_path, providers=["nvidia-nim-super"], lanes=["full-beast"], task_count=2, trials=1)

    assert result["manifest"]["planned_run_count"] == 2
    assert (tmp_path / "run_manifest.json").is_file()
    assert (tmp_path / "provider_fitness.json").is_file()
    assert (tmp_path / "task_results.jsonl").is_file()
    assert (tmp_path / "failures_by_bucket.json").is_file()
    assert (tmp_path / "cost_latency_summary.md").is_file()
    assert (tmp_path / "evidence_cards").is_dir()
    assert (tmp_path / "patches").is_dir()
    assert (tmp_path / "rollback_snapshots").is_dir()

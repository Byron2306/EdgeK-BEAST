import os
from pathlib import Path

from scripts.run_generation_gauntlets import run_generation_gauntlets


def test_generation_gauntlet_runner_writes_receipts_and_reuses_stored_capabilities(tmp_path: Path):
    state_root = tmp_path / "state"
    evidence_root = tmp_path / "evidence"

    first = run_generation_gauntlets(state_root=state_root, evidence_root=evidence_root, run_id="gauntlet-test-1")
    second = run_generation_gauntlets(state_root=state_root, evidence_root=evidence_root, run_id="gauntlet-test-2")

    assert first["text"]["status"] == "passed"
    assert first["image"]["status"] == "passed"
    assert first["text"]["semantic_promotions_new"] == first["text"]["case_count"]
    assert first["image"]["provider_calls_used"] == first["image"]["case_count"] * 2
    assert first["provider_boundary"]["provider_mode"] == "stub"
    assert len(first["provider_boundary"]["provider_receipt_digests"]) == first["image"]["provider_calls_used"]
    assert first["generation_synthesis_plane"]["capsule_count"] == len(first["provider_boundary"]["provider_receipt_digests"])
    assert first["generation_synthesis_plane"]["raw_prompt_stored_count"] == 0
    assert first["generation_synthesis_plane"]["execution_mode_counts"]["local_reason"] == first["image"]["provider_calls_used"]
    assert first["generation_synthesis_plane"]["commons_capability_digests"]
    assert first["generation_synthesis_plane"]["socket_guardian_binding_digests"]
    if hasattr(os, "memfd_create"):
        assert first["generation_synthesis_plane"]["sealed_memfd_count"] == first["generation_synthesis_plane"]["capsule_count"]
        assert first["generation_synthesis_plane"]["capsule_verified_count"] == first["generation_synthesis_plane"]["capsule_count"]
    assert first["evidence_bounded_semantic_resolution"]["matrix_free_case_count"] == first["text"]["case_count"]
    assert first["evidence_bounded_semantic_resolution"]["exact_replay_case_count"] == first["text"]["case_count"]
    assert first["evidence_bounded_semantic_resolution"]["semantic_space_class_counts"]["provable"] == first["text"]["case_count"]
    assert first["evidence_bounded_semantic_resolution"]["meaning_resolution_state_counts"]["resolved"] == first["text"]["case_count"]
    assert all(case["meaning_resolution_state_after"] == "resolved" for case in first["text"]["cases"])
    assert all(case["semantic_space_class_after"] == "provable" for case in first["text"]["cases"])
    assert first["stored_capabilities"]["semantic_crystal_count"] >= first["text"]["case_count"]
    assert first["stored_capabilities"]["visual_asset_count"] >= first["image"]["case_count"]
    assert second["text"]["status"] == "passed"
    assert second["image"]["status"] == "passed"
    assert second["text"]["stored_reuse_hits"] == second["text"]["case_count"]
    assert second["image"]["stored_asset_reuse_hits"] == second["image"]["case_count"]
    assert second["image"]["provider_calls_used"] == 0
    assert second["generation_synthesis_plane"]["capsule_count"] == 0
    assert second["capability_learning"]["by_event_type"]["gauntlet_completed"] >= 1
    assert second["capability_learning"]["by_capability_type"]["generation_gauntlet"] >= 1
    assert second["receipt_digest"].startswith("sha256:")
    assert (evidence_root / "gauntlet-test-1.json").is_file()
    assert (evidence_root / "gauntlet-test-1.md").is_file()
    assert (evidence_root / "gauntlet-test-2.json").is_file()
    assert (evidence_root / "latest.json").is_file()

import json
from pathlib import Path

from app.kernel.compute.earth_shattering_proof_gauntlet import EarthShatteringProofGauntlet
from app.kernel.networking.commons_spaces import (
    MANIFEST_NAME,
    RECEIPT_NAME,
    validate_manifest,
    validate_reduction_receipt,
)


def test_earth_shattering_gauntlet_prepares_compute_space_and_swarm_commons(tmp_path):
    receipt = EarthShatteringProofGauntlet(tmp_path / "earth").run()

    assert receipt["beast_object_type"] == "earth_shattering_crystal_reuse_proof_gauntlet"
    assert receipt["status"] == "passed"
    assert receipt["readiness"]["passed"] is True
    assert receipt["cloud_disabled_replay"]["external_teacher_calls_after_promotion"] == 0
    assert receipt["cloud_disabled_replay"]["task_count"] >= 2
    assert receipt["cloud_disabled_replay"]["unsafe_reuse_block_rate"] == 1.0
    assert receipt["definitive_lanes"]["metrics"]["full_reuse_provider_calls"] == 0
    assert receipt["definitive_lanes"]["metrics"]["mutation_blocks"] >= 1
    assert receipt["hard_coding_gauntlet"]["metrics"]["fresh_replay_repairs_verified"] == 3
    assert receipt["hard_coding_gauntlet"]["adversarial_claims"]["no_live_provider_during_replay"] is True
    assert receipt["final_boss_gauntlet"]["claims"]["multi_file_architectural_migration"] is True
    assert receipt["final_boss_gauntlet"]["claims"]["fresh_far_transfer_repaired"] is True
    assert receipt["final_boss_gauntlet"]["metrics"]["live_provider_replay_calls"] == 0
    assert receipt["final_boss_gauntlet"]["metrics"]["decoy_files"] == 24
    assert receipt["final_boss_gauntlet"]["metrics"]["replay_variants"] == 3
    assert receipt["final_boss_gauntlet"]["claims"]["negative_controls_blocked"] is True
    assert receipt["devils_advocate"]["convincing_today"] is True
    assert "production repository migration" in " ".join(receipt["devils_advocate"]["limitations"])

    space = receipt["compute_space"]
    space_root = Path(space["path"])
    manifest = json.loads((space_root / MANIFEST_NAME).read_text(encoding="utf-8"))
    reduction = json.loads((space_root / RECEIPT_NAME).read_text(encoding="utf-8"))

    assert validate_manifest(space_root, manifest)["valid"] is True
    assert validate_reduction_receipt(reduction)["valid"] is True
    assert manifest["reduction_claims"]["cloud_calls_evidence"] == "observed_cloud_disabled_completion"
    assert any(item["artifact_type"] == "hard_coding_crystallization" for item in manifest["artifacts"])
    assert any(item["artifact_type"] == "final_boss_multifile_crystallization" for item in manifest["artifacts"])
    assert reduction["displacement"]["counterfactual"] is False
    assert Path(space["export"]["path"]).is_file()
    assert space["export"]["sha256"].startswith("sha256:")

    swarm = receipt["swarm_commons"]
    assert swarm["beast_object_type"] == "swarm_commons_crystal_reuse_evidence_plane"
    assert len(swarm["active_channels"]) >= 6
    assert swarm["promotion_score"] >= 0.75
    assert all(row["safe"] is True for row in swarm["evidence_rows"])


def test_earth_shattering_gauntlet_writes_top_level_artifacts(tmp_path):
    root = tmp_path / "proof"
    receipt = EarthShatteringProofGauntlet(root).run()

    assert (root / "earth_shattering_proof_gauntlet.json").is_file()
    assert (root / "swarm_commons_evidence_plane.json").is_file()
    assert (root / "earth_shattering_crystal_reuse.beast-space.zip").is_file()
    stored = json.loads((root / "earth_shattering_proof_gauntlet.json").read_text(encoding="utf-8"))

    assert stored["receipt_hash"] == receipt["receipt_hash"]
    assert stored["compute_space"]["manifest_validation"]["valid"] is True
    assert stored["compute_space"]["receipt_validation"]["valid"] is True

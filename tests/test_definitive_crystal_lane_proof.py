from app.kernel.compute.definitive_crystal_lane_proof import DefinitiveCrystalLaneProof


def test_definitive_crystal_lane_proof_matches_occurrence_semantics(tmp_path):
    receipt = DefinitiveCrystalLaneProof(tmp_path).run()

    assert receipt["beast_object_type"] == "definitive_crystal_lane_proof"
    assert receipt["lane_count"] == 3
    assert receipt["occurrence_count"] == 5
    assert receipt["row_count"] == 15
    assert receipt["metrics"]["raw_provider_calls"] == 5
    assert receipt["metrics"]["full_reuse_provider_calls"] == 0
    assert receipt["metrics"]["full_reuse_local_rows"] == 4
    assert receipt["metrics"]["mutation_blocks"] == 1
    assert receipt["metrics"]["total_runtime_tokens_avoided"] > 0

    full = receipt["lanes"]["full_beast_reuse"]
    by_occurrence = {row["occurrence"]: row for row in full}
    assert by_occurrence["o3_crystallized"]["local_reuse"] is True
    assert by_occurrence["o5_mature_reuse"]["local_reuse"] is True
    assert by_occurrence["o10_mutation"]["blocked"] is True
    assert all(row["packet_hashes"] for row in full)
    assert (tmp_path / "definitive_crystal_lane_proof.json").exists()

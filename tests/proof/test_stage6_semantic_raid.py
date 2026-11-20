from scripts.proof.run_stage6_semantic_raid import ARMS, run_block


def test_stage6_recovers_bound_payload_in_fresh_process_and_resumes(tmp_path):
    rows, preparation = run_block(tmp_path, size=8, repeat=1, seed=4327)
    cases = {row["arm"]: row for row in rows}
    assert set(cases) == set(ARMS)
    assert all(row["verified"] for row in rows)
    assert all(row["worker_pid"] != preparation["worker_pid"] for row in rows)
    assert cases["rebuild"]["context_source_reads"] == 8
    assert cases["raid_intact"]["repaired_refs"] == 0
    assert cases["raid_primary_corrupt"]["repaired_refs"] == 1
    assert cases["raid_one_survivor"]["repaired_refs"] == 2
    for name in ("raid_intact", "raid_primary_corrupt", "raid_one_survivor"):
        assert cases[name]["context_source_reads"] == 0
        assert cases[name]["packet_sha256"] == cases["rebuild"]["packet_sha256"]
        assert cases[name]["result_sha256"] == cases["rebuild"]["result_sha256"]
        assert cases[name]["task_resumed"]
    for name in ("raid_all_copies_lost", "raid_manifest_lost"):
        assert not cases[name]["task_resumed"]
        assert cases[name]["workspace_unchanged"]
        assert cases[name]["context_source_reads"] == 0


def test_stage6_checkpoint_cannot_apply_against_changed_contract(tmp_path):
    import pytest
    from scripts.proof.run_stage6_semantic_raid import (
        CONTRACT, ORIGINAL, TARGET, apply_task, build_packet, create_workspace, projected,
    )

    workspace = tmp_path / "workspace"
    create_workspace(workspace, 8)
    payload = projected(build_packet(workspace, 8))
    (workspace / CONTRACT).write_text('{"retry_limit": 9}\n')
    with pytest.raises(RuntimeError, match="contract.json no longer matches"):
        apply_task(payload, workspace)
    assert (workspace / TARGET).read_text() == ORIGINAL

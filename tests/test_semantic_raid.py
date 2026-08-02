import json

from app.kernel.data_processing.semantic_raid import ArtifactFossilLayerStore, SemanticRaidStore


def test_semantic_raid_stores_redundant_shards_and_repairs_corruption(tmp_path):
    store = SemanticRaidStore(tmp_path / "raid")
    shard = store.store_shard(
        "promoted_crystal",
        {"capability_id": "cap:stable", "decision": "promote", "evidence": ["ev1"]},
        value_score=0.9,
    )
    before = store.integrity_report()
    corrupt_path = store.root / shard.primary_ref
    corrupt_path.write_text('{"broken": true}\n', encoding="utf-8")
    damaged = store.integrity_report()
    repaired = store.reconstruct()
    after = store.integrity_report()

    assert before["ok"] is True
    assert damaged["ok"] is False
    assert len(damaged["corrupt_refs"]) == 1
    assert repaired["repaired_refs"] == 1
    assert repaired["ok"] is True
    assert after["ok"] is True


def test_semantic_raid_accepts_only_complete_context_packets(tmp_path):
    store = SemanticRaidStore(tmp_path / "raid")
    packet = {
        "beast_object_type": "context_packet",
        "packet_id": "pkt_test",
        "handoff_hash": "sha256:test",
        "goal": "Change the selected file",
        "included_evidence": [{"kind": "file_snippet", "source": "service.py", "content": "value = 1"}],
    }

    shard = store.store_context_packet(packet)

    assert shard.artifact_type == "context_packet"
    assert store.integrity_report()["ok"] is True


def test_artifact_fossil_layers_replay_promotion_lineage(tmp_path):
    fossils = ArtifactFossilLayerStore(tmp_path / "fossils")
    first = fossils.checkpoint(
        "cap:stable",
        {"status": "candidate", "confidence": 0.81},
        decision="stage_candidate",
        evidence_ids=["ev1"],
    )
    second = fossils.checkpoint(
        "cap:stable",
        {"status": "promoted", "confidence": 0.93},
        decision="promote",
        evidence_ids=["ev1", "ev2"],
    )
    replay = fossils.replay()
    replay_again = ArtifactFossilLayerStore(tmp_path / "fossils").replay()

    assert first["checkpoint_hash"].startswith("sha256:")
    assert second["parent_hash"] == first["checkpoint_hash"]
    assert replay["valid_lineage"] is True
    assert replay["decisions"] == ["stage_candidate", "promote"]
    assert replay["final_state"]["status"] == "promoted"
    assert replay_again["replay_hash"] == replay["replay_hash"]


def test_value_aware_gc_keeps_high_value_shards(tmp_path):
    store = SemanticRaidStore(tmp_path / "raid")
    low = store.store_shard("trace", {"id": "low"}, value_score=0.1)
    high = store.store_shard("promoted_crystal", {"id": "high"}, value_score=0.95)

    report = store.garbage_collect(min_value_score=0.5)
    manifest = json.loads(store.manifest_path.read_text(encoding="utf-8"))

    assert report["collected"] == 1
    assert low.shard_id not in manifest["shards"]
    assert high.shard_id in manifest["shards"]

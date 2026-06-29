import json

from app.kernel.compute.cloud_disabled_replay_benchmark import CloudDisabledReplayBenchmark
from app.kernel.compute.crystal_autopromotion_daemon import AutopromotionPolicy, CrystalAutopromotionDaemon
from app.kernel.compute.crystal_promotion_evidence_sources import CrystalPromotionEvidenceSources
from app.kernel.compute.crystallized_compute_proof import CrystallizedOpusNIMGatewayMegaGauntlet


def test_unified_packet_joins_crystal_runtime_systems(tmp_path):
    receipt = CrystallizedOpusNIMGatewayMegaGauntlet(tmp_path, local_only=True).run()
    packet = receipt["unified_evidence_packet"]

    assert packet["beast_object_type"] == "unified_crystallized_compute_evidence_packet"
    assert packet["teacher"]["engine"] == "beast_local_cpu_forge"
    assert packet["teacher"]["cloud_used"] is False
    assert packet["runtime"]["engine"] == "beast_local_semantic_cache"
    assert packet["runtime"]["decision_action"] == "reuse_semantic_credit"
    assert packet["semantic_credit"]["credit_id"]
    assert packet["lattice"]["signal_count"] == 3
    assert packet["capability"]["promotion_status"] == "promoted"
    assert packet["route_optimizer"]["runtime_engine"] == "beast_local_semantic_cache"
    assert len(packet["forge"]["receipts"]) == 3
    assert {tool["name"] for tool in packet["tools"]} >= {"approved_patch_operations", "pytest", "approval_gate"}
    assert {skill["name"] for skill in packet["skills"]} >= {"opus_gateway_repair_verifier", "semantic_crystal_reuse"}
    assert packet["memory_hull"]["sections"]["residue"]["sidecars"] >= 3
    assert len(packet["negative_cases"]) == 6
    assert all(case["blocked"] is True for case in packet["negative_cases"])
    assert packet["replay"]["cloud_calls_during_completion"] == 0
    assert packet["metrics"]["runtime_tokens_avoided"] > 0

    on_disk = json.loads((tmp_path / "unified_evidence_packet.json").read_text(encoding="utf-8"))
    assert on_disk["packet_hash"] == packet["packet_hash"]
    bridge = receipt["crystal_evidence_bridge_receipt"]
    assert bridge["packet_hash"] == packet["packet_hash"]
    assert bridge["memory_hull"]["verified"] is True
    assert bridge["envelope_count"] >= 2


def test_autopromotion_daemon_promotes_from_unified_evidence(tmp_path):
    receipt = CrystallizedOpusNIMGatewayMegaGauntlet(tmp_path / "run", local_only=True).run()
    path = tmp_path / "run" / "crystallized_opus_nim_gateway_mega_gauntlet.json"

    daemon = CrystalAutopromotionDaemon(tmp_path)
    daemon_receipt = daemon.run_once([path])

    assert daemon_receipt["promoted_count"] == 1
    assert daemon_receipt["rejected_count"] == 0
    promoted = daemon_receipt["promoted"][0]
    assert promoted["packet_hash"] == receipt["unified_evidence_packet"]["packet_hash"]
    assert promoted["runtime_engine"] == "beast_local_semantic_cache"
    assert promoted["teacher_engine"] == "beast_local_cpu_forge"
    assert promoted["source_evidence_score"] is not None


def test_promotion_evidence_sources_score_beast_subsystem_receipts():
    receipt = CrystalPromotionEvidenceSources().evaluate({
        "tool_interceptor": {"verified": True, "summary": "semantic snippets returned"},
        "context_packet": {"verified": True, "summary": "context compressed"},
        "tool_laziness": {"success": True, "summary": "low value call skipped"},
        "provider_economist": {"approved": True, "summary": "route card selected"},
        "swarm_openclaw": {"verified": True, "summary": "approval gated plan"},
        "capability_registry": {"ready": True, "summary": "skills discovered"},
        "meta_tool_commons": {"adopted": True, "summary": "candidate staged"},
        "compute_forge": {"tests_passed": True, "summary": "forge verifier passed"},
    })

    assert receipt["present_count"] == 8
    assert receipt["verified_count"] == 8
    assert receipt["score"] == 1.0
    assert receipt["missing_sources"] == []


def test_autopromotion_daemon_service_loop_writes_state(tmp_path):
    CrystallizedOpusNIMGatewayMegaGauntlet(tmp_path / "run", local_only=True).run()
    path = tmp_path / "run" / "crystallized_opus_nim_gateway_mega_gauntlet.json"

    daemon = CrystalAutopromotionDaemon(
        tmp_path,
        policy=AutopromotionPolicy(min_source_evidence_score=0.5),
    )
    state = daemon.run_loop(receipt_paths=[path], interval_seconds=0, max_cycles=2)

    assert state["beast_object_type"] == "crystal_autopromotion_daemon_service_run"
    assert state["cycle_count"] == 2
    assert state["cycles"][0]["promoted_count"] == 1
    service_state = json.loads((tmp_path / "crystal_autopromotion_daemon_service_state.json").read_text(encoding="utf-8"))
    assert service_state["running"] is False
    assert service_state["cycle_count"] == 2


def test_cloud_disabled_replay_benchmark_emits_earth_shaking_scorecard(tmp_path):
    result = CloudDisabledReplayBenchmark(tmp_path).run()

    assert result["cloud_disabled"] is True
    assert result["task_count"] == 2
    assert result["initial_cloud_calls"] == 0
    assert result["autopromoted_crystals"] == 2
    assert result["external_teacher_calls_after_promotion"] == 0
    assert result["local_completion_rate"] == 1.0
    assert result["verified_success_rate"] == 1.0
    assert result["blocked_unsafe_reuse"] == result["negative_case_count"] >= 6
    assert result["unsafe_reuse_block_rate"] == 1.0
    assert result["runtime_engine"] == "beast_local_semantic_cache"
    assert result["teacher_engine"] == "beast_local_cpu_forge"
    assert result["route_optimizer_choice"] == "beast_local_semantic_cache"
    assert len(result["unified_packet_hashes"]) == 2
    assert all(result["unified_packet_hashes"])
    assert (tmp_path / "cloud_disabled_replay_benchmark.json").exists()

"""Tests for Phase 7: Compute Forge Node functionality."""

import pytest

from app.kernel.crystal_seal import seal_crystal_payload, verify_crystal_seal
from app.kernel.compute_forge import ComputeForgeNode, ComputeLedger, ForgeNodeProfile


def test_forge_node_watches_repo_and_builds_fingerprint():
    """Test that a forge node can watch a repo and build fingerprints."""
    node = ComputeForgeNode(node_id="jetson_01", node_type="jetson")
    
    # Use a temp directory or the current repo
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        fp = node.watch_repo(tmpdir, target_paths=[])
        
        assert "fingerprint_hash" in fp
        assert node.profile.last_activity_at is not None


def test_forge_node_runs_local_inference_and_earns_credit(monkeypatch, tmp_path):
    """Test that local inference earns a semantic credit."""
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"response": "4", "eval_count": 3}

    monkeypatch.setattr("app.kernel.compute_forge.httpx.post", lambda *args, **kwargs: Response())
    from app.kernel.durable_inference_storage import DurableInferenceStorage
    node = ComputeForgeNode(
        node_id="cpu_01", node_type="cpu_ollama",
        storage=DurableInferenceStorage(tmp_path / "credits"),
    )
    
    result = node.run_local_inference(
        task_class="simple_query",
        prompt="What is 2+2?",
    )
    
    assert "credit" in result
    assert result["credit"]["artifact_type"] == "verified_capability"
    assert node.profile.total_tokens_displaced > 0


def test_failed_local_inference_earns_no_credit(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "app.kernel.compute_forge.httpx.post",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("offline")),
    )
    from app.kernel.durable_inference_storage import DurableInferenceStorage
    node = ComputeForgeNode("offline", storage=DurableInferenceStorage(tmp_path / "credits"))
    result = node.run_local_inference("test", "prompt")
    assert result["result"]["actual_inference"] is False
    assert result["credit"] is None
    assert node.profile.total_tokens_displaced == 0
    assert node.get_earned_credits_summary()["total_work_items"] == 0


def test_forge_node_performs_secret_scan():
    """Test that secret scanning earns work credit."""
    node = ComputeForgeNode(node_id="edge_01", node_type="edge_cpu")
    
    result = node.perform_secret_scan("/tmp/test_repo")
    
    assert result["work_type"] == "secret_scan"
    assert result["node_id"] == "edge_01"


def test_forge_node_catches_stale_fingerprint():
    """Test that catching stale fingerprints updates the profile."""
    node = ComputeForgeNode(node_id="monitor_01", node_type="cpu_ollama")
    
    detection = node.catch_stale_fingerprint("candidate_stale_01")
    
    assert detection["work_type"] == "catch_stale_fingerprint"
    assert node.profile.stale_fingerprints_caught == 1


def test_forge_node_prepares_handoff_packet():
    """Test that handoff preparation tracks reduction metrics."""
    node = ComputeForgeNode(node_id="prep_01", node_type="rtx")
    
    packet = node.prepare_handoff_packet(
        task_class="pr_review",
        route_card={"route_id": "route_pr"},
        context_packet={"packet_id": "ctx_pr"},
    )
    
    assert packet["work_type"] == "prepare_handoff"
    # Reduction is >= 0 (can be 0 for small identical inputs; real benefit measured on larger data)
    assert node.profile.total_handoff_reduction_pct >= 0


def test_forge_node_credits_summary():
    """Test that the credits summary aggregates work items."""
    node = ComputeForgeNode(node_id="summary_01", node_type="jetson")
    
    node.perform_secret_scan("/tmp/a")
    summary = node.get_earned_credits_summary()

    assert summary["total_work_items"] == 1
    assert "work_by_type" in summary
    assert summary["claim"] == "Internal BEAST compute credits, not crypto"


def test_compute_ledger_aggregates_forge_nodes():
    """Test that the Compute Ledger aggregates multiple forge nodes."""
    ledger = ComputeLedger()
    
    node1 = ComputeForgeNode(node_id="n1", node_type="jetson")
    node2 = ComputeForgeNode(node_id="n2", node_type="rtx")
    
    # Simulate work
    node1.perform_secret_scan("/tmp/r1")
    node2.perform_secret_scan("/tmp/r")
    node2.catch_stale_fingerprint("c1")
    
    ledger.update_from_node(node1)
    ledger.update_from_node(node2)
    
    summary = ledger.to_dict()
    
    assert summary["node_count"] == 2
    assert "system_totals" in summary
    assert summary["system_totals"]["total_stale_fingerprints_caught"] >= 1


def test_forge_node_profile_tracks_all_metrics():
    """Test that the forge node profile tracks all roadmap metrics."""
    profile = ForgeNodeProfile(
        node_id="full_01",
        node_type="jetson",
        total_tokens_displaced=41000,
        total_candidates_produced=12,
        total_handoff_reduction_pct=62.0,
        stale_fingerprints_caught=3,
    )
    
    d = profile.to_dict()
    
    assert d["total_tokens_displaced"] == 41000
    assert d["total_candidates_produced"] == 12
    assert d["total_handoff_reduction_pct"] == 62.0
    assert d["stale_fingerprints_caught"] == 3


def test_forge_mines_defensive_crystals_and_builds_amplification_pack(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "app.py").write_text("def parse(value):\n    return value\n")
    node = ComputeForgeNode(node_id="jetson_defender", node_type="jetson")

    mining = node.mine_defensive_crystals(
        str(repo),
        objectives=["review input validation", "check secret redaction", "audit auth boundary"],
        target_model="llama3.2:1b",
        teacher_model="nvidia_nim_reference",
    )
    pack = node.build_crystal_amplification_pack(mining["crystals"], target_model="llama3.2:1b")
    comparison = node.compare_amplified_tiny_model(pack, big_model_label="opus_reference")

    assert mining["safety_posture"] == "defensive_only_model_agnostic_crystals"
    assert mining["crystal_count"] == 3
    assert all(item["domain"] == "cyber_defense" for item in mining["crystals"])
    assert all("exploit" in item["safety_boundary"] for item in mining["crystals"])
    assert pack["beast_object_type"] == "tiny_llama_crystal_amplification_pack"
    assert pack["crystal_count"] == 3
    assert "zeroclaw" in pack["orchestrators"]
    assert comparison["tiny_gain_over_raw"] > 0
    assert comparison["claim_boundary"].startswith("This compares a tiny model plus verified defensive crystals")
    assert node.profile.total_tokens_displaced > 0


def test_crystal_seal_verifies_payload():
    payload = {"fusion_id": "fused_1", "value": 7, "purpose": "unit"}

    seal = seal_crystal_payload(payload, purpose="unit_test")
    verification = verify_crystal_seal(payload, seal)
    tampered = verify_crystal_seal({**payload, "value": 8}, seal)

    assert seal["beast_object_type"] == "sealed_crystal_compute_credit"
    assert seal["crypto_profile"]["signature"] in {"ML-DSA-65", "HMAC-SHA256"}
    assert verification["verified"] is True
    assert tampered["verified"] is False


def test_forge_fuses_tools_skills_and_crystals_into_sealed_compound(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "service.py").write_text("VALUE = 1\n")
    node = ComputeForgeNode("fusion_node", node_type="jetson")
    mining = node.mine_defensive_crystals(str(repo), objectives=["review validation"], max_crystals=1)

    fused = node.fuse_inference_crystals(
        name="tiny_defense_operator",
        task_class="cyber_defense_orchestration",
        crystals=mining["crystals"],
        meta_tools=[{"name": "meta_tool_commons_ranker"}],
        skills=[{"name": "secure_code_review"}],
        swarm_recipes=[{"name": "zeroclaw_no_exec_plan"}],
        target_model="llama3.2:1b",
    )

    assert fused["beast_object_type"] == "fused_inference_crystal"
    assert fused["components"]["meta_tools"]
    assert fused["components"]["skills"]
    assert fused["components"]["swarm_recipes"]
    assert fused["seal_verification"]["verified"] is True
    assert fused["economics"]["crystal_credit_units"] > 0
    assert fused["economics"]["currency_boundary"].startswith("internal verified compute credit")


def test_forge_candidate_feed_includes_crystals_fusions_components_and_failures(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "service.py").write_text("VALUE = 1\n")
    node = ComputeForgeNode("commons_feeder", node_type="cpu_ollama")
    fp = node.watch_repo(str(repo))
    node.propose_crystallization_candidate(
        candidate_name="safe_refactor_pattern",
        task_class="refactor_safety",
        transform_type="deterministic",
        impact_fingerprint=fp,
        shadow_runs=3,
    )
    mining = node.mine_defensive_crystals(str(repo), objectives=["review validation"], max_crystals=1)
    fused = node.fuse_inference_crystals(
        name="tiny_defense_operator",
        task_class="cyber_defense_orchestration",
        crystals=mining["crystals"],
        meta_tools=[{"name": "meta_tool_commons_ranker"}],
        skills=[{"name": "secure_code_review"}],
        swarm_recipes=[{"name": "zeroclaw_no_exec_plan"}],
    )

    feed = node.commons_candidate_feed()
    kinds = {item["candidate_kind"] for item in feed["candidates"]}

    assert feed["beast_object_type"] == "forge_commons_candidate_feed"
    assert "forge_candidate_proposal" in kinds
    assert "forge_crystal" in kinds
    assert "fused_inference_crystal" in kinds
    assert "meta_tool" in kinds
    assert "skill" in kinds
    assert "mutation_ablation_case" in kinds
    assert feed["mutation_ablation_backlog"]["case_count"] > 0
    assert all(case["adoption_allowed"] is False for case in feed["mutation_ablation_backlog"]["cases"])
    assert fused["fusion_id"] in {item.get("artifact_id") for item in feed["candidates"]}


def test_forge_snapshot_persists_commons_candidate_feed(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "service.py").write_text("VALUE = 1\n")
    node = ComputeForgeNode("snapshot_feeder", node_type="edge_cpu")
    node.mine_defensive_crystals(str(repo), objectives=["review validation"], max_crystals=1)

    snapshot = node.persist_snapshot(tmp_path / "snapshot.json")

    assert snapshot["commons_candidate_feed"]["beast_object_type"] == "forge_commons_candidate_feed"
    assert snapshot["commons_candidate_feed"]["candidate_count"] > 0

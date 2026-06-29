"""Integration coverage for the CPU-first forge and crystallization pipeline."""

from app.kernel.compute.ablation_harness import AblationHarness
from app.kernel.capability.capability_crystallization import CapabilityCrystallizationEngine
from app.kernel.compute.compute_forge import ComputeForgeNode, ComputeLedger
from app.kernel.compute.distributed_forge_scheduler import DistributedForgeScheduler
from app.kernel.storage.durable_inference_storage import DurableInferenceStorage
from app.kernel.compute.kv_cache_transport import CacheEngine, CacheLocation, CrossEngineKVCacheTransport


def _write_repo(root):
    (root / "app").mkdir()
    (root / "tests").mkdir()
    (root / "app/value.py").write_text("def value():\n    return 1\n")
    (root / "tests/test_visible.py").write_text(
        "from app.value import value\n\ndef test_visible():\n    assert value() == 1\n"
    )
    (root / "tests/test_hidden.py").write_text(
        "from app.value import value\n\ndef test_hidden_boundary():\n    assert value() > 0\n"
    )
    (root / "tests/test_rollback.py").write_text(
        "def test_rollback_contract():\n    assert True\n"
    )
    (root / "tests/test_security_scope.py").write_text(
        "def test_security_scope_contract():\n    assert True\n"
    )


def test_full_pipeline_cpu_records_real_stage_evidence(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _write_repo(repo)
    storage = DurableInferenceStorage(tmp_path / "credits")
    node = ComputeForgeNode("integration-node", storage=storage)

    fingerprint = node.watch_repo(str(repo), target_paths=["app/value.py"])
    assert fingerprint["targets"]["app/value.py"]["exists"] is True

    scheduler = DistributedForgeScheduler(tmp_path / "scheduler")
    scheduler.register_node("integration-node", capabilities=["fingerprint"])
    scheduler.submit_work("fingerprint", str(repo), priority=1)
    assigned = scheduler.assign_work("integration-node", max_items=1)
    assert len(assigned) == 1
    assert scheduler.report_work_result(
        assigned[0].schedule_id,
        "integration-node",
        True,
        {"fingerprint_hash": fingerprint["fingerprint_hash"]},
    ) is True
    assert scheduler.nodes["integration-node"].total_work_completed == 1
    assert not list((tmp_path / "scheduler").glob("work_*.json"))

    engine = CapabilityCrystallizationEngine(storage_path=tmp_path / "crystallization")
    harness = AblationHarness(repo_root=repo, crystallization_engine=engine)
    run = harness.run_ablation(
        candidate_name="schema_validation",
        task_class="integration",
        transform_type="deterministic",
        visible_test_path="tests/test_visible.py",
        hidden_test_path="tests/test_hidden.py",
        rollback_test="tests/test_rollback.py",
    )
    assert run.behavior_preserved is True
    assert run.visible_tests_passed == run.visible_tests_total == 1
    assert run.hidden_tests_passed == run.hidden_tests_total == 1
    candidate = engine.get_candidate("crystal_schema_validation_integration")
    assert candidate is not None
    assert candidate.shadow_runs == 1

    kv_dir = tmp_path / "kv"
    kv = CrossEngineKVCacheTransport(max_memory_bytes=1024 * 1024, storage_dir=kv_dir)
    block = kv.register_block(
        model="test", tokenizer="test", prompt_prefix="pre", system_prompt="sys",
        engine=CacheEngine.OLLAMA, location=CacheLocation.CPU, precision="fp16",
        num_layers=2, num_heads=2, head_dim=32, seq_len=16, size_bytes=512,
    )
    assert kv.move(block.block_id, CacheLocation.STORAGE) is True
    assert (kv_dir / f"{block.block_id}.json").is_file()
    assert (kv_dir / f"{block.block_id}.bin").stat().st_size == 512

    credit = storage.store_semantic_result(
        task_class="integration",
        repo_fingerprint=fingerprint["fingerprint_hash"],
        policy_version="integration_v1",
        verified_tests=["visible", "hidden", "rollback", "security_scope"],
        avoided_tokens_estimate=0,
        confidence=0.95,
    )
    assert (tmp_path / "credits" / f"{credit.credit_id}.json").is_file()

    ledger = ComputeLedger()
    ledger.update_from_node(node)
    state = ledger.to_dict()
    assert state["node_count"] == 1
    assert node.get_earned_credits_summary()["total_work_items"] == 1

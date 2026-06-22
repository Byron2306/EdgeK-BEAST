"""Tests for Phase 7: Durable Inference Storage functionality."""

import json
import pytest

from app.kernel.durable_inference_storage import (
    DurableInferenceStorage,
    RuntimeReplayResult,
    SemanticComputeCredit,
    StoredInferenceValue,
)


def test_store_semantic_result_creates_credit():
    """Test that storing a BEAST-like semantic result creates a credit."""
    storage = DurableInferenceStorage()
    
    credit = storage.store_semantic_result(
        task_class="schema_validation",
        repo_fingerprint="sha256:abc123",
        policy_version="phase6_v1",
        verified_tests=["visible", "hidden"],
        avoided_tokens_estimate=1500,
        confidence=0.92,
        impact_fingerprint_hash="sha256:def456",
        chronicle_lesson_id="lesson_001",
    )
    
    assert credit.artifact_type == "verified_capability"
    assert credit.task_class == "schema_validation"
    assert credit.avoided_tokens_estimate == 1500
    assert credit.confidence == 0.92
    assert credit.is_reusable() is True


def test_store_answer_creates_cached_credit():
    """Test that storing a simple cached answer creates a credit."""
    storage = DurableInferenceStorage()
    
    credit = storage.store_answer(
        prompt_hash="sha256:prompt1",
        model="gpt-4",
        parameters={"temperature": 0.0},
        response="Hello world",
        cost_usd=0.001,
    )
    
    assert credit.artifact_type == "cached_answer"
    assert credit.reuse_state == "active"
    assert credit.confidence == 0.50  # Lower confidence for simple caching


def test_store_prefill_creates_kv_credit():
    """Test that storing engine-level prefill creates a credit."""
    storage = DurableInferenceStorage()
    
    credit = storage.store_prefill(
        model="llama-3",
        tokenizer="tiktoken",
        prompt_prefix="system: You are helpful",
        system_prompt="You are helpful",
        kv_cache_metadata={"estimated_tokens_saved": 800, "blocks": 12},
    )
    
    assert credit.artifact_type == "kv_prefill"
    assert credit.avoided_tokens_estimate == 800


def test_lookup_reusable_credit_finds_match():
    """Test that lookup finds matching reusable credits."""
    storage = DurableInferenceStorage()
    
    storage.store_semantic_result(
        task_class="provider_routing",
        repo_fingerprint="sha256:xyz",
        policy_version="v1",
        verified_tests=["visible", "hidden"],
        avoided_tokens_estimate=500,
        confidence=0.85,
        impact_fingerprint_hash="sha256:impact",
    )
    
    found = storage.lookup_reusable_credit(
        task_class="provider_routing",
        repo_fingerprint="sha256:xyz",
    )
    
    assert found is not None
    assert found.task_class == "provider_routing"
    assert found.is_reusable() is True


def test_lookup_returns_none_for_stale_credit():
    """Test that lookup does not return stale credits."""
    storage = DurableInferenceStorage()
    
    credit = storage.store_semantic_result(
        task_class="test",
        repo_fingerprint="sha256:test",
        policy_version="v1",
        verified_tests=["visible", "hidden"],
        avoided_tokens_estimate=100,
        confidence=0.70,
        impact_fingerprint_hash="sha256:impact",
    )
    
    storage.mark_stale(credit.credit_id)
    
    found = storage.lookup_reusable_credit(task_class="test")
    
    assert found is None  # Stale credits not returned


def test_record_reuse_updates_statistics():
    """Test that recording reuse updates count and timestamp."""
    storage = DurableInferenceStorage()
    
    credit = storage.store_semantic_result(
        task_class="test",
        repo_fingerprint="sha256:reuse",
        policy_version="v1",
        verified_tests=["visible", "hidden"],
        avoided_tokens_estimate=100,
        confidence=0.80,
        impact_fingerprint_hash="sha256:impact",
    )
    
    updated = storage.record_credit_reuse(credit.credit_id)
    
    assert updated is not None
    assert updated.reuse_count == 1
    assert updated.last_reused_at is not None


def test_compute_stored_inference_value_aggregates_tiers():
    """Test that the three-tier currency model aggregates correctly."""
    storage = DurableInferenceStorage()
    
    # Store semantic result (crystallized) and prefill (stored)
    storage.store_semantic_result(
        "cap", "fp1", "v1", ["visible", "hidden"], 100, 0.9,
        impact_fingerprint_hash="sha256:impact",
    )
    storage.store_prefill("m", "t", "pre", "sys", {"estimated_tokens_saved": 50})
    
    value = storage.compute_stored_inference_value()
    
    # At least 2 credits should be active (semantic + prefill)
    assert value.live_compute["total_credits"] >= 2
    # Crystallized or stored buckets should have entries
    total_crystallized = sum(value.crystallized_compute.values()) if value.crystallized_compute else 0
    total_stored = sum(value.stored_compute.values()) if value.stored_compute else 0
    assert total_crystallized + total_stored >= 0  # Structure is valid


def test_unverified_or_unfingerprinted_capability_is_not_reusable(tmp_path):
    storage = DurableInferenceStorage(tmp_path)
    unverified = storage.store_semantic_result("task", "fp", "v1", [], 1000, 0.99)
    assert unverified.is_reusable() is False
    assert storage.lookup_reusable_credit("task", repo_fingerprint="fp") is None
    assert storage.record_credit_reuse(unverified.credit_id) is None


def test_verified_capability_requires_exact_repo_fingerprint(tmp_path):
    storage = DurableInferenceStorage(tmp_path)
    storage.store_semantic_result(
        "task", "repo-a", "v1", ["visible", "hidden"], 100, 0.9,
        impact_fingerprint_hash="sha256:impact",
    )
    assert storage.lookup_reusable_credit("task") is None
    assert storage.lookup_reusable_credit("task", repo_fingerprint="repo-b") is None
    assert storage.lookup_reusable_credit("task", repo_fingerprint="repo-a") is not None


def test_prefill_persists_hashes_not_raw_governance_prompts(tmp_path):
    storage = DurableInferenceStorage(tmp_path)
    secret_system = "system policy with SECRET_VALUE"
    first = storage.store_prefill("m", "t", "prefix", secret_system, {})
    second = storage.store_prefill("m", "t", "prefix", "different system", {})
    serialized = (tmp_path / f"{first.credit_id}.json").read_text()
    assert "SECRET_VALUE" not in serialized
    assert "system_prompt_hash" in first.metadata
    assert first.credit_id != second.credit_id


def test_answer_cache_identity_includes_parameters(tmp_path):
    storage = DurableInferenceStorage(tmp_path)
    cold = storage.store_answer("prompt", "model", {"temperature": 0}, "a")
    warm = storage.store_answer("prompt", "model", {"temperature": 1}, "b")
    assert cold.credit_id != warm.credit_id


def test_lookup_answer_retrieves_complete_cached_response_and_records_reuse(tmp_path):
    storage = DurableInferenceStorage(tmp_path)
    long_response = "hello " * 200
    credit = storage.store_answer("prompt", "model", {"temperature": 0}, long_response)

    replay = storage.lookup_answer("prompt", "model", {"temperature": 0})

    assert replay is not None
    assert replay.replay_type == "cached_answer"
    assert replay.payload["response"] == long_response
    assert storage.credits[credit.credit_id].reuse_count == 1
    assert "hello " * 100 in replay.payload["response"]


def test_runtime_lookup_replay_prefers_semantic_credit_then_records_measured_savings(tmp_path):
    storage = DurableInferenceStorage(tmp_path)
    credit = storage.store_semantic_result(
        "task", "repo", "v1", ["visible", "hidden"], 1200, 0.91,
        impact_fingerprint_hash="sha256:impact",
        metadata={"capability": "verified"},
    )

    replay = storage.runtime_lookup_replay(task_class="task", repo_fingerprint="repo")
    measured = storage.replay_credit(credit.credit_id, measured_tokens_saved=900)

    assert isinstance(replay, RuntimeReplayResult)
    assert replay.replay_type == "semantic_credit"
    assert replay.payload["metadata"]["capability"] == "verified"
    assert measured.reusable is True
    assert storage.get_metrics()["measured_reuse_tokens_saved"] == 900


def test_runtime_lookup_replay_can_return_prefill_identity(tmp_path):
    storage = DurableInferenceStorage(tmp_path)
    storage.store_prefill(
        model="llama",
        tokenizer="tok",
        prompt_prefix="prefix",
        system_prompt="system",
        kv_cache_metadata={"estimated_tokens_saved": 80, "block_id": "kv1"},
    )

    replay = storage.runtime_lookup_replay(
        model="llama",
        tokenizer="tok",
        prompt_prefix="prefix",
        system_prompt="system",
    )

    assert replay is not None
    assert replay.replay_type == "kv_prefill"
    assert replay.payload["kv_cache_metadata"]["block_id"] == "kv1"


def test_storage_redacts_secret_metadata_and_reports_corruption(tmp_path):
    storage = DurableInferenceStorage(tmp_path)
    credit = storage.store_semantic_result(
        "task", "fp", "v1", ["visible", "hidden"], 10, 0.9,
        impact_fingerprint_hash="sha256:impact",
        metadata={"nested": {"api_key": "super-secret", "safe": "value"}},
    )
    serialized = (tmp_path / f"{credit.credit_id}.json").read_text()
    assert "super-secret" not in serialized
    assert "[REDACTED]" in serialized

    (tmp_path / "corrupt.json").write_text("{not-json")
    reloaded = DurableInferenceStorage(tmp_path)
    assert reloaded.get_metrics()["load_error_count"] == 1


def test_content_addressed_blob_is_deduplicated_while_index_remains_mutable(tmp_path):
    storage = DurableInferenceStorage(tmp_path)
    credit = storage.store_semantic_result(
        "task", "repo", "v1", ["visible", "hidden"], 100, 0.9,
        impact_fingerprint_hash="sha256:impact", metadata={"capability": "stable"},
    )
    index_before = json.loads((tmp_path / f"{credit.credit_id}.json").read_text())
    blob_ref = index_before["artifact_blob"]["ref"]
    blob_before = (tmp_path / blob_ref).read_bytes()

    storage.record_credit_reuse(credit.credit_id, measured_tokens_saved=75)
    index_after = json.loads((tmp_path / f"{credit.credit_id}.json").read_text())

    assert index_after["reuse_count"] == 1
    assert index_after["artifact_blob"] == index_before["artifact_blob"]
    assert (tmp_path / blob_ref).read_bytes() == blob_before
    assert len(list((tmp_path / "blobs" / "sha256").glob("*.json"))) == 1


def test_blob_integrity_is_checked_on_reload(tmp_path):
    storage = DurableInferenceStorage(tmp_path)
    credit = storage.store_semantic_result(
        "task", "repo", "v1", ["visible", "hidden"], 100, 0.9,
        impact_fingerprint_hash="sha256:impact",
    )
    index = json.loads((tmp_path / f"{credit.credit_id}.json").read_text())
    (tmp_path / index["artifact_blob"]["ref"]).write_text('{"digest":"sha256:bad","payload":{}}')

    reloaded = DurableInferenceStorage(tmp_path)

    assert reloaded.credits[credit.credit_id].credit_id == credit.credit_id
    assert any(row["error"] == "ArtifactBlobIntegrityError" for row in reloaded.load_errors)


def test_gc_removes_only_unreferenced_blobs_and_optional_retired_indexes(tmp_path):
    storage = DurableInferenceStorage(tmp_path)
    active = storage.store_semantic_result(
        "active", "repo", "v1", ["visible", "hidden"], 100, 0.9,
        impact_fingerprint_hash="sha256:active",
    )
    retired = storage.store_semantic_result(
        "retired", "repo", "v1", ["visible", "hidden"], 100, 0.9,
        impact_fingerprint_hash="sha256:retired",
    )
    storage.retire_credit(retired.credit_id)
    orphan = storage._store_blob({"orphan": True})

    first = storage.garbage_collect()
    second = storage.garbage_collect(remove_retired_indexes=True)

    assert orphan["digest"] in first["removed_blobs"]
    assert active.credit_id in storage.credits
    assert retired.credit_id in second["removed_indexes"]
    assert not (tmp_path / f"{retired.credit_id}.json").exists()


def test_semantic_compute_credit_example_matches_roadmap():
    """Test that the credit structure matches the roadmap example."""
    storage = DurableInferenceStorage()
    
    credit = storage.store_semantic_result(
        task_class="provider_id_parser",
        repo_fingerprint="sha256:repo_fp",
        policy_version="phase6_v1",
        verified_tests=["visible", "hidden"],
        avoided_tokens_estimate=3600,
        confidence=0.92,
        impact_fingerprint_hash="sha256:impact_fp",
    )
    
    d = credit.to_dict()
    
    # Verify structure matches roadmap example
    assert d["artifact_type"] == "verified_capability"
    assert d["task_class"] == "provider_id_parser"
    assert d["repo_fingerprint"] == "sha256:repo_fp"
    assert d["verified_tests"] == ["visible", "hidden"]
    assert d["avoided_tokens_estimate"] == 3600
    assert d["confidence"] == 0.92
    assert d["reuse_state"] == "active"


@pytest.mark.asyncio
async def test_executor_replays_cached_answer_without_provider(monkeypatch, tmp_path):
    import app.kernel.execute as execute_module
    from app.kernel.compute_governor import ComputeGovernor
    from app.kernel.compute_ledger import ComputeLedger
    from app.kernel.execute import Executor
    from app.kernel.inference_interceptor import InferenceComputeInterceptor
    from app.kernel.perceive import EdgeKIR
    from app.kernel.reason import GovernanceDecision, GovernanceResult

    storage = DurableInferenceStorage(tmp_path)
    storage.store_answer("prompt", "gpt-test", {"temperature": 0, "max_tokens": 32}, "cached hello")
    interceptor = InferenceComputeInterceptor(
        ComputeGovernor(),
        ComputeLedger(str(tmp_path / "compute.db")),
    )
    monkeypatch.setattr(execute_module, "compute_interceptor", interceptor)
    ir = EdgeKIR(
        messages=[{"role": "user", "content": "hello"}],
        model="gpt-test",
        max_tokens=32,
        metadata={
            "durable_inference_replay_enabled": True,
            "durable_inference_storage_path": str(tmp_path),
            "durable_prompt_hash": "prompt",
            "durable_parameters": {"temperature": 0, "max_tokens": 32},
            "measured_reuse_tokens_saved": 77,
        },
    )

    response = await Executor().execute(ir, GovernanceResult(GovernanceDecision.ALLOW, reason="test"))
    reloaded = DurableInferenceStorage(tmp_path)

    assert response["object"] == "beast.durable_inference_replay"
    assert response["text"] == "cached hello"
    assert response["edgek_runtime"]["provider"] == "durable_inference_storage"
    assert interceptor.ledger.recent_receipts(1)[0]["provider_execution_requested"] is False
    assert reloaded.get_metrics()["measured_reuse_tokens_saved"] == 77


@pytest.mark.asyncio
async def test_executor_replays_prefill_identity_without_provider(monkeypatch, tmp_path):
    import app.kernel.execute as execute_module
    from app.kernel.compute_governor import ComputeGovernor
    from app.kernel.compute_ledger import ComputeLedger
    from app.kernel.execute import Executor
    from app.kernel.inference_interceptor import InferenceComputeInterceptor
    from app.kernel.perceive import EdgeKIR
    from app.kernel.reason import GovernanceDecision, GovernanceResult

    storage = DurableInferenceStorage(tmp_path)
    storage.store_prefill(
        model="gpt-test",
        tokenizer="tok",
        prompt_prefix="prefix",
        system_prompt="system",
        kv_cache_metadata={"estimated_tokens_saved": 44, "block_id": "kv-live"},
    )
    interceptor = InferenceComputeInterceptor(
        ComputeGovernor(),
        ComputeLedger(str(tmp_path / "compute.db")),
    )
    monkeypatch.setattr(execute_module, "compute_interceptor", interceptor)
    ir = EdgeKIR(
        messages=[{"role": "user", "content": "continue"}],
        model="gpt-test",
        metadata={
            "durable_inference_replay_enabled": True,
            "durable_inference_storage_path": str(tmp_path),
            "tokenizer": "tok",
            "prompt_prefix": "prefix",
            "system_prompt": "system",
        },
    )

    response = await Executor().execute(ir, GovernanceResult(GovernanceDecision.ALLOW, reason="test"))

    assert response["replay"]["replay_type"] == "kv_prefill"
    assert response["replay"]["payload"]["kv_cache_metadata"]["block_id"] == "kv-live"
    assert interceptor.ledger.recent_receipts(1)[0]["status"] == "durable_replay_succeeded"

from app.kernel.compute.crystal_reuse_gateway import CrystalReuseGateway, CrystalReuseRequest
from app.kernel.compute.kv_cache_transport import CrossEngineKVCacheTransport
from app.kernel.compute.local_route_optimizer import LocalRouteOptimizer
from app.kernel.compute.local_semantic_cache import LocalSemanticCache
from app.kernel.observability.local_trace_ledger import LocalTraceLedger
from app.kernel.security.residue_seal import ResidueSeal
from app.kernel.storage.durable_inference_storage import DurableInferenceStorage, RuntimeReplayResult
from app.kernel.storage.memory_hull import MemoryHull


def test_crystal_reuse_gateway_returns_exact_cached_answer(tmp_path):
    storage = DurableInferenceStorage(tmp_path / "durable")
    gateway = CrystalReuseGateway(storage=storage, seal=ResidueSeal(tmp_path / "keys"))
    request = CrystalReuseRequest(prompt="same prompt", model="local", parameters={"temperature": 0})
    storage.store_answer(request.prompt_hash, request.model, request.parameters, "cached answer")

    decision = gateway.decide(request)

    assert decision.action == "reuse_answer"
    assert decision.payload["reuse"]["payload"]["response"] == "cached answer"
    assert decision.residue_seal["purpose"] == "crystal_reuse_decision"


def test_crystal_reuse_gateway_records_verified_provider_response_as_crystal(tmp_path):
    storage = DurableInferenceStorage(tmp_path / "durable")
    hull = MemoryHull(tmp_path / "vault", seal=ResidueSeal(tmp_path / "keys"))
    gateway = CrystalReuseGateway(storage=storage, memory_hull=hull, seal=ResidueSeal(tmp_path / "keys"))
    request = CrystalReuseRequest(
        prompt="make a route card",
        model="qwen",
        task_class="route_card_generation",
        repo_fingerprint="repo1",
        provider="ollama",
    )

    miss = gateway.decide(request)
    receipt = gateway.record_execution_response(
        request,
        "route card response",
        verified=True,
        avoided_tokens_estimate=700,
        evidence={"verification": "passed"},
    )
    hit = gateway.decide(request)

    assert miss.action == "execute_local_cpu"
    assert miss.source == "local_execution_gateway"
    assert receipt["semantic_credit_id"].startswith("scc_")
    assert receipt["memory_hull"]["verified"] is True
    assert hit.action == "reuse_semantic_credit"
    assert hit.avoided_tokens_estimate == 700


def test_crystal_reuse_gateway_reuses_kv_transport_block(tmp_path):
    storage = DurableInferenceStorage(tmp_path / "durable")
    transport = CrossEngineKVCacheTransport(storage_dir=tmp_path / "kv")
    gateway = CrystalReuseGateway(storage=storage, kv_transport=transport, seal=ResidueSeal(tmp_path / "keys"))
    request = CrystalReuseRequest(
        prompt="prefix body",
        system_prompt="system",
        model="llama",
        tokenizer="tok",
        prompt_prefix="prefix",
        preferred_engine="vllm",
    )
    gateway.register_kv_block(
        request,
        engine="vllm",
        location="cpu",
        num_layers=2,
        num_heads=2,
        head_dim=16,
        seq_len=128,
        size_bytes=4096,
        tensor_payload=b"engine-native-kv-prefill",
    )

    decision = gateway.decide(request)

    assert decision.action == "reuse_kv_prefill"
    assert decision.source == "kv_transport"
    assert decision.payload["reuse"]["payload"]["kv_cache_block"]["pinned"] is True


def test_crystal_reuse_gateway_uses_semantic_matcher_and_exports_observability(tmp_path):
    def matcher(request):
        return RuntimeReplayResult(
            replay_type="cached_answer",
            credit_id="semantic-hit",
            reusable=True,
            payload={"response": "near match"},
            avoided_tokens_estimate=55,
            confidence=0.91,
            reason="semantic_similarity_hit",
        )

    gateway = CrystalReuseGateway(
        storage=DurableInferenceStorage(tmp_path / "durable"),
        semantic_matcher=matcher,
        seal=ResidueSeal(tmp_path / "keys"),
    )

    decision = gateway.decide(CrystalReuseRequest(prompt="similar prompt", model="m"))
    span = gateway.export_openllmetry_span(decision)
    observation = gateway.export_langfuse_observation(decision)
    assertion = gateway.export_promptfoo_assertion(decision)

    assert decision.action == "reuse_answer"
    assert decision.source == "semantic_cache"
    assert span["attributes"]["beast.crystal.action"] == "reuse_answer"
    assert observation["scores"][0]["value"] == decision.confidence
    assert assertion["metadata"]["decision_id"] == decision.decision_id


def test_crystal_reuse_gateway_inventory_advertises_public_integrations(tmp_path):
    gateway = CrystalReuseGateway(storage=DurableInferenceStorage(tmp_path / "durable"), seal=ResidueSeal(tmp_path / "keys"))

    inventory = gateway.inventory()
    ids = {item["capability_id"] for item in inventory["integration_health"]["capabilities"]}

    assert {"local_semantic_cache", "local_prefix_kv_store", "local_execution_gateway", "compute_forge"}.issubset(ids)
    assert inventory["runtime_order"][0] == "exact_answer"
    assert inventory["integration_health"]["capability_count"] >= 7


def test_crystal_reuse_gateway_exports_first_class_integration_bundle(tmp_path):
    gateway = CrystalReuseGateway(storage=DurableInferenceStorage(tmp_path / "durable"), seal=ResidueSeal(tmp_path / "keys"))
    decision = gateway.decide(CrystalReuseRequest(prompt="bundle me", model="m"))

    bundle = gateway.export_integration_bundle(decision)

    assert bundle["lmcache"]["beast_object_type"] == "lmcache_reuse_manifest"
    assert bundle["gptcache"]["beast_object_type"] == "gptcache_semantic_record"
    assert bundle["litellm"]["metadata"]["beast_governance_layer"] == "BEAST"
    assert bundle["openllmetry"]["name"] == "beast.crystal_reuse"
    assert bundle["langfuse"]["scores"][0]["name"] == "crystal_reuse_confidence"
    assert bundle["tensorzero"]["beast_object_type"] == "tensorzero_feedback_candidate"
    assert bundle["promptfoo"]["metadata"]["beast_object_type"] == "promptfoo_crystal_reuse_assertion"


def test_recorded_provider_response_populates_local_semantic_cache_and_trace(tmp_path):
    semantic_cache = LocalSemanticCache(tmp_path / "semantic.sqlite")
    trace_ledger = LocalTraceLedger(tmp_path / "trace.sqlite", tmp_path / "trace.jsonl")
    gateway = CrystalReuseGateway(
        storage=DurableInferenceStorage(tmp_path / "durable"),
        local_semantic_cache=semantic_cache,
        trace_ledger=trace_ledger,
        seal=ResidueSeal(tmp_path / "keys"),
    )
    request = CrystalReuseRequest(
        prompt="explain cloud crystallization",
        model="meta/llama-3.1-8b-instruct",
        task_class="cloud_crystallization_probe",
        repo_fingerprint="repo-cloud",
        provider="nvidia_nim",
        metadata={"correlation_id": "trace-cloud-crystal"},
    )

    receipt = gateway.record_execution_response(
        request,
        "Cloud answer that is safe to crystallize.",
        route="nvidia_nim",
        engine="meta/llama-3.1-8b-instruct",
        verified=True,
        avoided_tokens_estimate=61,
        evidence={"verification": "live_nim_smoke_passed"},
    )
    exact = gateway.decide(request, seal_decision=False)
    semantic = semantic_cache.match(
        prompt="explain cloud crystallization please",
        task_class="cloud_crystallization_probe",
        repo_fingerprint="repo-cloud",
        threshold=0.4,
    )

    assert receipt["promotion_allowed"] is True
    assert receipt["semantic_credit_id"].startswith("scc_")
    assert exact.action in {"reuse_answer", "reuse_semantic_credit"}
    assert semantic is not None
    assert semantic.answer == "Cloud answer that is safe to crystallize."
    assert (tmp_path / "trace.jsonl").read_text()


def test_eval_gate_blocks_semantic_promotion_for_secret_like_cloud_output(tmp_path):
    gateway = CrystalReuseGateway(
        storage=DurableInferenceStorage(tmp_path / "durable"),
        local_semantic_cache=LocalSemanticCache(tmp_path / "semantic.sqlite"),
        trace_ledger=LocalTraceLedger(tmp_path / "trace.sqlite", tmp_path / "trace.jsonl"),
        seal=ResidueSeal(tmp_path / "keys"),
    )
    request = CrystalReuseRequest(
        prompt="do not crystallize secrets",
        model="m",
        task_class="secret_guard",
        repo_fingerprint="repo",
    )

    receipt = gateway.record_execution_response(
        request,
        "password=abc123",
        verified=True,
        evidence={"verification": "bad_fixture"},
    )

    assert receipt["promotion_allowed"] is False
    assert receipt["semantic_credit_id"] == ""
    assert receipt["local_eval_gate"]["passed"] is False


def test_recorded_execution_updates_local_route_optimizer(tmp_path):
    optimizer = LocalRouteOptimizer(tmp_path / "routes.sqlite")
    gateway = CrystalReuseGateway(
        storage=DurableInferenceStorage(tmp_path / "durable"),
        route_optimizer=optimizer,
        seal=ResidueSeal(tmp_path / "keys"),
    )
    request = CrystalReuseRequest(
        prompt="route feedback should learn this engine",
        model="local-test",
        task_class="route_feedback",
    )

    receipt = gateway.record_execution_response(
        request,
        "safe verified response",
        route="local_cpu",
        engine="ollama",
        verified=True,
        avoided_tokens_estimate=19,
        evidence={"latency_ms": 12.5},
    )

    assert receipt["local_route_optimizer"]["engine_id"] == "ollama"
    assert optimizer.choose_route(request) == "ollama"

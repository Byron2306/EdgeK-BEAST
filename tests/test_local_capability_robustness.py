import json
import sqlite3
from types import SimpleNamespace

import pytest

from app.kernel.compute.crystal_reuse_gateway import CrystalReuseGateway, CrystalReuseRequest
from app.kernel.compute.kv_cache_transport import CrossEngineKVCacheTransport
from app.kernel.compute.local_capabilities import LocalCapabilityRegistry
from app.kernel.compute.local_execution_gateway import LocalExecutionGateway
from app.kernel.compute.local_prefix_kv_store import LocalPrefixKVStore
from app.kernel.compute.local_route_optimizer import LocalRouteOptimizer
from app.kernel.compute.local_semantic_cache import LocalSemanticCache
from app.kernel.evals.local_eval_gate import LocalEvalGate
from app.kernel.observability.local_trace_ledger import LocalTraceLedger
from app.kernel.security.residue_seal import ResidueSeal
from app.kernel.storage.durable_inference_storage import DurableInferenceStorage


def test_local_capability_health_probe_exercises_every_capability():
    health = LocalCapabilityRegistry().health(probe=True)

    assert health["beast_object_type"] == "beast_local_capability_health"
    assert health["capability_count"] == 7
    assert health["ready_count"] == 7
    assert {row["status"] for row in health["capabilities"]} == {"ready"}
    for row in health["capabilities"]:
        probe = row["live_probe"]
        assert probe["ready"] is True
        assert probe["checks"]


def test_local_semantic_cache_exact_semantic_scope_and_verified(tmp_path):
    cache = LocalSemanticCache(tmp_path / "semantic.db")
    cache.put(
        credit_id="verified",
        prompt="summarize route optimizer behavior",
        task_class="docs",
        repo_fingerprint="repo-a",
        answer="verified answer",
        confidence=1.4,
        verified=True,
        policy_version="v1",
        metadata={"receipt": "ok"},
    )
    cache.put(
        credit_id="unverified",
        prompt="summarize route optimizer behavior",
        task_class="docs",
        repo_fingerprint="repo-b",
        answer="unverified answer",
        confidence=0.9,
        verified=False,
        policy_version="v1",
        metadata={},
    )

    exact = cache.match(prompt="summarize route optimizer behavior", task_class="docs", repo_fingerprint="repo-a")
    near = cache.match(prompt="summarize route optimizer behavior please", task_class="docs", repo_fingerprint="repo-a", threshold=0.4)
    scoped_miss = cache.match(prompt="summarize route optimizer behavior", task_class="docs", repo_fingerprint="other")
    unverified_miss = cache.match(prompt="summarize route optimizer behavior", task_class="docs", repo_fingerprint="repo-b")
    unverified_hit = cache.match(
        prompt="summarize route optimizer behavior",
        task_class="docs",
        repo_fingerprint="repo-b",
        require_verified=False,
    )

    assert exact.credit_id == "verified"
    assert exact.confidence == 1.0
    assert near.reason == "local_token_overlap_semantic_match"
    assert scoped_miss is None
    assert unverified_miss is None
    assert unverified_hit.credit_id == "unverified"


def test_local_prefix_kv_store_round_trips_tensor_and_requires_exact_profile(tmp_path):
    transport = CrossEngineKVCacheTransport(storage_dir=tmp_path / "kv")
    gateway = CrystalReuseGateway(
        storage=DurableInferenceStorage(tmp_path / "durable"),
        kv_transport=transport,
        seal=ResidueSeal(tmp_path / "keys"),
    )
    store = LocalPrefixKVStore(gateway)
    request = CrystalReuseRequest(
        prompt="prefix body",
        model="m",
        tokenizer="tok",
        prompt_prefix="prefix",
        system_prompt="system",
        repo_fingerprint="repo",
    )

    prefill = store.register_prefill(request, engine="ollama", metadata={"case": "robust"})
    block = store.register_block(request, engine="ollama", tensor_payload=b"kv-bytes", metadata={"case": "robust"})
    decision = gateway.decide(request, seal_decision=False)
    mismatch = transport.lookup("m", "tok", "different-prefix", "system")

    assert prefill["credit_id"]
    assert block["block"]["pinned"] is True
    assert transport.export_tensor_payload(block["block"]["block_id"]) == b"kv-bytes"
    assert decision.action == "reuse_kv_prefill"
    assert mismatch is None


def test_local_execution_gateway_rejects_non_cpu_preferred_and_ignores_bad_optimizer():
    class Fabric:
        def cpu_candidates(self):
            return [SimpleNamespace(engine_id="ollama")]

        def generate(self, engine_id, **kwargs):
            return {"engine_id": engine_id, "response": "ok"}

    class BadOptimizer:
        def choose_route(self, request):
            return "vllm"

    gateway = LocalExecutionGateway(Fabric(), route_optimizer=BadOptimizer())
    request = SimpleNamespace(model="m", prompt="p", system_prompt="", parameters={}, task_class="probe", preferred_engine=None)

    assert gateway.select_engine(request) == "ollama"
    assert gateway.complete(request)["cloud_used"] is False
    with pytest.raises(RuntimeError):
        gateway.select_engine(SimpleNamespace(**{**request.__dict__, "preferred_engine": "vllm"}))


def test_local_trace_ledger_writes_sqlite_and_jsonl(tmp_path):
    ledger = LocalTraceLedger(tmp_path / "trace.db", tmp_path / "trace.jsonl")
    event = ledger.record("trace-1", "decision", {"cost": 0.0, "route": "local_cpu"})

    with sqlite3.connect(tmp_path / "trace.db") as conn:
        rows = conn.execute("SELECT event_id, event_type FROM trace_events WHERE trace_id = ?", ("trace-1",)).fetchall()
    jsonl = [json.loads(line) for line in (tmp_path / "trace.jsonl").read_text().splitlines()]

    assert rows == [(event["event_id"], "decision")]
    assert jsonl[0]["payload"]["route"] == "local_cpu"


def test_local_route_optimizer_persists_and_scores_routes(tmp_path):
    optimizer = LocalRouteOptimizer(tmp_path / "routes.db")
    optimizer.record(task_class="code", engine_id="ollama", model="m", success=True, latency_ms=80, tokens=10)
    optimizer.record(task_class="code", engine_id="ollama", model="m", success=True, latency_ms=100, tokens=12)
    optimizer.record(task_class="code", engine_id="llama_cpp", model="m", success=False, latency_ms=1, tokens=1)

    chosen = LocalRouteOptimizer(tmp_path / "routes.db").choose_route(SimpleNamespace(task_class="code"))

    assert chosen == "ollama"


def test_local_eval_gate_blocks_secret_patterns_and_unknown_rules():
    gate = LocalEvalGate()
    passed = gate.evaluate(
        request=SimpleNamespace(task_class="probe"),
        response="safe BEAST_NIM_LIVE_OK",
        rules=[{"type": "must_contain", "value": "BEAST_NIM_LIVE_OK"}, {"type": "no_secret_patterns"}],
    )
    blocked_secret = gate.evaluate(
        request=SimpleNamespace(task_class="probe"),
        response="password=abc",
        rules=[{"type": "no_secret_patterns"}],
    )
    blocked_unknown = gate.evaluate(
        request=SimpleNamespace(task_class="probe"),
        response="safe",
        rules=[{"type": "not_a_real_rule"}],
    )

    assert passed["promotion_allowed"] is True
    assert blocked_secret["promotion_allowed"] is False
    assert blocked_unknown["checks"][0]["reason"] == "unknown_rule_type"


def test_compute_forge_probe_does_real_local_work(tmp_path):
    probe = LocalCapabilityRegistry()._probe_compute_forge(tmp_path)

    assert probe["ready"] is True
    assert probe["checks"]["fingerprint"] is True
    assert probe["checks"]["secret_scan"] == "secret_scan"
    assert probe["checks"]["handoff"] == "prepare_handoff"
    assert probe["checks"]["work_items"] >= 3

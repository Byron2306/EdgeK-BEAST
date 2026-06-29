import pytest
from httpx import ASGITransport, AsyncClient
from rich.console import Console

from app.cli.api import ActionResult, BackendSnapshot, BeastApiClient
from app.cli.ui import PAGES, BeastMissionConsole, PageHost, intelligence_summary
from app.kernel.compute.crystal_reuse_gateway import CrystalReuseGateway, CrystalReuseRequest
from app.kernel.compute.inference_engine_fabric import InferenceEngineFabric
from app.kernel.compute.kv_cache_transport import CrossEngineKVCacheTransport
from app.kernel.security.agent_passport import AgentPassport, AgentPassportPolicy
from app.kernel.security.residue_seal import ResidueSeal
from app.kernel.storage.durable_inference_storage import DurableInferenceStorage
from app.kernel.storage.memory_hull import MemoryHull
from app.main import app


def _synthetic_snapshot() -> BackendSnapshot:
    return BackendSnapshot(
        base_url="http://test",
        online=True,
        gateway="OK",
        proxy="OK",
        mcp="OK",
        capability_inventory={"kinds": {"provider": 2, "skill": 3, "crystal": 1}},
        capabilities=[
            {"capability_id": "provider_litellm", "kind": "provider", "confidence": 0.95, "source": "registry"},
            {"capability_id": "crystal_reuse", "kind": "crystal", "confidence": 0.91, "source": "memory_hull"},
        ],
        provider_registry={"providers": [
            {"provider_id": "litellm", "backend": "openai_compatible", "enabled": True, "model_count": 2},
            {"provider_id": "ollama", "backend": "local", "enabled": True, "model_count": 1},
        ]},
        provider_adapters=[
            {"provider_id": "litellm", "backend": "litellm", "adapter_class": "LiteLLMAdapter", "proxy_path": "/v1/chat/completions", "default_model": "beast-auto"},
            {"provider_id": "ollama", "backend": "ollama", "adapter_class": "OllamaAdapter", "proxy_path": "/api/generate", "default_model": "qwen2.5:0.5b"},
        ],
        provider_secrets={"providers": {"litellm": {"status": "env"}}},
        prec_state={"counts": [{"kind": "operator", "status": "OK", "count": 1}], "recent": [{"lifecycle_id": "prec_1", "kind": "operator", "status": "OK", "current_phase": "crystallize"}]},
        prec_lifecycles=[{"lifecycle_id": "prec_1", "kind": "operator", "objective": "gauntlet", "status": "OK", "current_phase": "crystallize", "summary": "ready"}],
        litellm_config={"model_list": [{"model_name": "beast-auto", "litellm_params": {"model": "ollama/qwen2.5:0.5b"}}]},
        litellm_sidecar={"running": True, "port": 4000},
        nginx_config="server { listen 8080; proxy_pass http://127.0.0.1:8000; }",
        chronicles=[{"task_id": "task_1", "chronicle_type": "crystal", "provider": "local", "category": "done", "confidence": "0.93", "summary": "crystal reused", "memory_candidate": "yes", "memory_hull_verified": True, "memory_hull_sidecar_path": "/tmp/beast/vault/tasks/residue_1.residue.json"}],
        routes=[{"provider_id": "litellm", "route_provider": "litellm", "resolved_model": "beast-auto", "governed_by_beast": True}],
        insight_packet={"evidence": [{"id": "e1", "score": 0.9}]},
        handoff_precheck={"ready": True, "reason": "gauntlet"},
        http_telemetry={"request_count": 12, "io": {"rx_bytes": 1024, "tx_bytes": 2048}, "bandwidth": {"rx_bytes_per_second": 100, "tx_bytes_per_second": 200}, "latency_ms": {"avg": 12, "p95": 31}, "status_counts": {"200": 12}},
        runtime_metrics={"sample_size": 4, "health": {"status": "OK", "failure_count": 0, "failure_rate": 0}, "latency_ms": {"avg": 20, "p95": 50}, "provider_counts": {"litellm": {"ok": 2}}},
        session_handshake={"session_id": "gauntlet", "handshake_hash": "sha256:gauntlet", "latency_budget": {"preflight_budget_ms": 500, "scout_budget_ms": 300}},
        commons_state={"evidence_count": 3, "candidate_count": 2, "adopted_count": 1},
        commons_ranking={"count": 1, "rankings": [{"capability_id": "beast_sourceplan_prepare", "role": "tool_selector", "score": 0.88, "confidence": 0.82, "sample_size": 10}]},
        commons_evidence_plane={"plane_count": 2, "evidence_count": 5, "planes": [{"plane": "crystal", "evidence_count": 3}]},
        commons_candidates=[{"candidate_id": "cand_1", "kind": "skill", "score": 0.8, "source": "gauntlet"}],
        tool_laziness={"summary": {"skip_count": 1, "learn_more_count": 1, "estimated_latency_avoided_ms": 20}},
        provider_economist={"decision": "route_selected", "selected": {"provider": "litellm"}},
        capability_exchange_state={"enabled": True},
        otel_state={"configured": True},
        plugins_state={"count": 1},
        skill_promotion_candidates=[{"candidate_id": "skill_1", "kind": "skill", "confidence": 0.89, "source": "gauntlet"}],
        swarm_state={"profiles": [{"id": "profile_1"}]},
        swarm_governance={"status": "governed"},
        swarm_runs=[{"run_id": "run_1", "profile": "builder", "status": "OK", "value": "ready"}],
        ollama_status={"default_model": "qwen2.5:0.5b", "models": [{"name": "qwen2.5:0.5b"}]},
        beast_cli_plan={"ready": True, "mode": "openclaw", "actions": [{"name": "plan"}], "plan_hash": "sha256:plan"},
        kv_cache_state={"total_blocks": 1, "operations_logged": 3},
        crystal_reuse={
            "storage": {"active_credits": 2, "total_credits": 3, "total_reuse_count": 5, "measured_reuse_tokens_saved": 700},
            "kv_transport": {"total_blocks": 1, "operations_logged": 3},
            "integration_health": {
                "integration_count": 9,
                "configured_count": 3,
                "integrations": [
                    {"integration_id": "lmcache", "project": "LMCache", "configured": True, "role": "KV", "capabilities": {"kv_cache": True}, "live_probe": {"status": "ready", "ready": True}},
                    {"integration_id": "gptcache", "project": "GPTCache", "configured": True, "role": "semantic", "capabilities": {"semantic_cache": True}, "live_probe": {"status": "ready", "ready": True}},
                    {"integration_id": "promptfoo", "project": "Promptfoo", "configured": True, "role": "eval", "capabilities": {"eval_gate": True}, "live_probe": {"status": "configured_unverified", "ready": False}},
                ],
            },
        },
        memory_security={
            "memory_hull": {"root": "/tmp/beast/vault", "verified_sidecars": 2, "failed_sidecars": 0},
            "residue_seal": {"key_exists": True, "key_mode": "0o600"},
            "agent_passport": {"policy_lint": {"valid": True, "policy_count": 5}, "sample_decisions": {"scout_memory_append": {"allowed": True}}},
        },
        compute_state={"modes": {"shadow": 3}},
        compute_metrics={"sample_size": 4, "observed_total_tokens": 1000, "estimated_avoidable_total_tokens": 250, "stream_tokens_saved": 25},
        compute_savings={"potential_weekly_savings_usd": 0.12},
        crystal_compute={"state": "ready"},
        proof_local_semantic_pages={"active_verified_pages": 2, "page_count": 3, "reuse_hits": 4},
        proof_local_distillation={"adapter_packages": 1},
        commons_spaces={"count": 1, "scoreboard": {"spaces": 1, "valid_spaces": 1, "verified_spaces": 1, "provider_calls_avoided": 1, "gpu_avoided_spaces": 1, "adoptions": 1}, "spaces": [{"space_id": "space_1", "name": "Gauntlet Space", "task_class": "operator", "artifact_count": 3, "verifier_passed": True, "provider_calls_avoided": 1, "gpu_avoided": True}]},
        commons_economy={"credits": 1},
        commons_scale_economics={"proof_density": {"spaces": {"valid": 1, "live_reproduced": 1}, "workload": {"total_repeated_matches": 3, "total_cloud_calls_avoided": 1}, "proof_gap_to_10x3": {"spaces_needed": 9, "matches_needed": 27}}},
        commons_policy={"mode": "shadow", "recommendation": {"route": "local", "expected_compute_reduction": 0.5}},
        commons_policy_evaluation={"sample_size": 1, "top1_route_accuracy": 1.0},
        provider_model_fitness={"models": [{"provider": "litellm", "fitness_score": 0.91, "clean_completion_rate": 0.9, "samples": 5}]},
        master_mega_evidence={"release_version": "0.1", "release_status": "frozen", "secret_scan_passed": True, "controlled_design": {"observed_cells": 180, "target_cells": 450, "remaining_cells": 270, "progress_rate": 0.4}, "metrics": {"mature_deterministic_reuse": 12, "mature_qpccd": {"numerator": 12, "denominator": 24, "rate": 0.5}}},
        latest_mega_artifact={"artifact_path": "/tmp/mega", "mode": "gauntlet", "live": False, "provider_call_receipts": 2, "impact_fingerprint_files": 2, "integrity_hash": "sha256:mega"},
    )


def test_mammoth_local_layers_gauntlet(tmp_path):
    seal = ResidueSeal(tmp_path / "keys")
    payload = {"task": "mammoth", "decision": "local first"}
    signature = seal.sign(payload, purpose="gauntlet")
    assert seal.verify(payload, signature, expected_purpose="gauntlet")["verified"] is True
    assert seal.verify({**payload, "decision": "tampered"}, signature, expected_purpose="gauntlet")["verified"] is False

    hull = MemoryHull(tmp_path / "vault", seal=seal)
    receipt = hull.write_residue(task="Mammoth gauntlet", provider="local", decision="seal the residue", evidence={"tests": "passed"})
    assert receipt["verified"] is True
    assert hull.inventory(verify=True)["failed_sidecars"] == 0
    assert hull.search("mammoth")

    policy = AgentPassportPolicy(seal=seal, sign_decisions=True)
    scout = AgentPassport.local("scout/repo-reader")
    governor = AgentPassport.local("runtime-governor")
    proxy = AgentPassport.local("proxy/gateway")
    assert policy.evaluate(caller=scout, target="spiffe://beast.local/memory/vault", action="append")["allowed"] is True
    assert policy.evaluate(caller=proxy, target="spiffe://beast.local/provider/cloud", action="call")["allowed"] is False
    assert policy.evaluate(caller=governor, target="spiffe://beast.local/provider/cloud", action="call", facts={"quality_cascade": {"approved": True}})["allowed"] is True

    transport = CrossEngineKVCacheTransport(storage_dir=tmp_path / "kv")
    gateway = CrystalReuseGateway(
        storage=DurableInferenceStorage(tmp_path / "durable"),
        kv_transport=transport,
        memory_hull=hull,
        seal=seal,
    )
    request = CrystalReuseRequest(prompt="reuse this exact compute", model="qwen", tokenizer="tok", prompt_prefix="reuse this", preferred_engine="vllm", task_class="gauntlet", repo_fingerprint="repo")
    miss = gateway.decide(request)
    assert miss.action == "execute_local_cpu"

    record = gateway.record_execution_response(request, "verified answer", verified=True, avoided_tokens_estimate=321, evidence={"verification": "passed"})
    assert record["semantic_credit_id"].startswith("scc_")
    assert record["memory_hull"]["verified"] is True
    assert gateway.decide(request).action in {"reuse_answer", "reuse_semantic_credit"}

    kv_registration = gateway.register_kv_block(request, engine="vllm", location="cpu", num_layers=2, num_heads=2, head_dim=16, seq_len=128, size_bytes=4096)
    assert kv_registration["block"]["beast_object_type"] == "kv_cache_block"

    bundle = gateway.export_integration_bundle(miss)
    for integration in ["lmcache", "gptcache", "litellm", "openllmetry", "langfuse", "tensorzero", "promptfoo"]:
        assert integration in bundle

    inventory = gateway.inventory()
    assert inventory["integration_health"]["integration_count"] >= 9
    probed = gateway.integration_health(probe=True)
    assert probed["probe_enabled"] is True
    assert all(isinstance(row["live_probe"], dict) for row in probed["integrations"])

    fabric = InferenceEngineFabric()
    cache_ids = {row["cache_backend_id"] for row in fabric.inventory()["cache_backends"]}
    assert {"beast_crystal_reuse_gateway", "lmcache", "gptcache", "openllmetry", "langfuse", "tensorzero", "promptfoo"}.issubset(cache_ids)


@pytest.mark.asyncio
async def test_mammoth_gateway_endpoints_gauntlet():
    prompt = "mammoth gauntlet reusable compute"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        endpoints = {
            "health": await client.get("/health"),
            "compute": await client.get("/edgek/compute"),
            "inference_engines": await client.get("/edgek/inference-engines"),
            "crystal_compute": await client.get("/edgek/crystal-compute"),
            "kv_cache": await client.get("/edgek/kv-cache/state"),
            "memory_security": await client.get("/edgek/memory-security", params={"verify": "true"}),
            "crystal_reuse": await client.get("/edgek/crystal-reuse"),
            "integrations": await client.get("/edgek/crystal-reuse/integrations"),
            "integrations_probe": await client.get("/edgek/crystal-reuse/integrations", params={"probe": "true", "timeout_seconds": "0.2"}),
            "decision": await client.post("/edgek/crystal-reuse/decide", json={"prompt": prompt, "model": "local-test", "parameters": {"temperature": 0}}),
            "record": await client.post("/edgek/crystal-reuse/record", json={"prompt": prompt, "model": "local-test", "response": "gauntlet answer", "verified": True, "avoided_tokens_estimate": 123, "write_memory": True}),
            "export": await client.post("/edgek/crystal-reuse/export", json={"prompt": prompt, "model": "local-test"}),
            "prefill": await client.post("/edgek/crystal-reuse/prefill", json={"prompt": prompt, "model": "local-test", "tokenizer": "tok", "prompt_prefix": "mammoth", "kv_cache_metadata": {"engine": "test"}}),
            "kv_block": await client.post("/edgek/crystal-reuse/kv-block", json={"prompt": prompt, "model": "local-test", "tokenizer": "tok", "prompt_prefix": "mammoth", "engine": "vllm", "num_layers": 1, "num_heads": 1, "head_dim": 8, "seq_len": 64, "size_bytes": 512}),
        }

    assert all(response.status_code == 200 for response in endpoints.values()), {name: response.status_code for name, response in endpoints.items()}
    assert endpoints["memory_security"].json()["beast_object_type"] == "beast_memory_security_state"
    assert endpoints["crystal_reuse"].json()["beast_object_type"] == "crystal_reuse_gateway_inventory"
    assert endpoints["integrations"].json()["integration_count"] >= 9
    assert endpoints["integrations_probe"].json()["probe_enabled"] is True
    assert endpoints["export"].json()["beast_object_type"] == "beast_local_capability_export_bundle"
    assert endpoints["record"].json()["semantic_credit_id"].startswith("scc_")


@pytest.mark.asyncio
async def test_mammoth_session_turn_surfaces_crystal_reuse_decision(monkeypatch):
    client = BeastApiClient("http://test")

    async def crystal_reuse_decision(prompt, provider, model="beast-auto"):
        return {
            "decision_id": "crystal_reuse_test",
            "action": "reuse_answer",
            "source": "durable_inference_storage",
            "confidence": 0.97,
            "payload": {"reuse": {"payload": {"response": "cached BEAST answer"}}},
        }

    async def action(*args, **kwargs):
        return ActionResult(True, "ok", "ok", {"ready": True, "evidence": []})

    async def record(*args, **kwargs):
        return True

    monkeypatch.setattr(client, "crystal_reuse_decision", crystal_reuse_decision)
    monkeypatch.setattr(client, "build_task_envelope", action)
    monkeypatch.setattr(client, "compile_insight", action)
    monkeypatch.setattr(client, "prepare_handoff", action)
    monkeypatch.setattr(client, "record_outcome_evidence", record)

    events = [event async for event in client.stream_live_turn("hello", [], provider="litellm", model="beast-auto")]
    tool_text = "\n".join(str(event.get("text") or "") for event in events if event.get("type") == "tool")
    tokens = "".join(str(event.get("text") or "") for event in events if event.get("type") == "token")

    assert "crystal reuse: id=crystal_reuse_test action=reuse_answer" in tool_text
    assert "cached BEAST answer" in tokens


def test_mammoth_tui_every_page_gauntlet():
    snap = _synthetic_snapshot()
    summary = intelligence_summary(snap)
    assert summary["crystal_integration_count"] == 9
    assert summary["memory_hull_verified"] == 2
    assert summary["passport_policy_valid"] is True

    console = Console(record=True, width=180)
    rendered_pages = {}
    for page in PAGES:
        host = PageHost()
        host.page = page
        host.snapshot = snap
        host.selected_indices = {page: 0}
        renderable = host.render()
        assert renderable is not None, page
        console.print(renderable)
        rendered_pages[page] = console.export_text(clear=True)

    assert summary["crystal_reuse_credits"] == 2
    assert summary["crystal_integration_configured"] == 3
    assert summary["memory_hull_failed"] == 0
    assert set(rendered_pages) == set(PAGES)

    app_shell = BeastMissionConsole(base_url="http://test")
    app_shell.snapshot = snap
    app_shell.selected_page = "Deployment"
    assert app_shell.page_rows() == 8
    app_shell.selected_page = "Settings"
    assert app_shell.page_rows() == 10
    diagnostic_names = {row["name"] for row in app_shell.diagnostic_rows(snap)}
    assert {"Crystal reuse gateway", "Crystal integrations", "Memory security"}.issubset(diagnostic_names)

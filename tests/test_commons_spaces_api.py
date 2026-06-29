import importlib

import pytest
from httpx import ASGITransport, AsyncClient

from app.kernel.governance.commons_policy import CommonsPolicyLearner
from app.kernel.networking.commons_economy import ComputeReductionEconomy
from app.kernel.networking.commons_prototype import CommonsCrystalPromoter, FirstPrototypeRunner
from app.kernel.registry.commons_space_registry import CommonsSpaceRegistry
from app.kernel.networking.commons_spaces import package_tiny_llama_case
from app.kernel.networking.federated_commons import FederatedCommons


@pytest.mark.asyncio
async def test_commons_spaces_api_lists_details_adopts_and_recommends(monkeypatch, tmp_path):
    main = importlib.import_module("app.main")
    registry = CommonsSpaceRegistry(tmp_path / "spaces")
    source = __import__("pathlib").Path(__file__).resolve().parents[1] / "benchmarks/results/tiny_llama_opus_case_study_qwen25_05b"
    package_tiny_llama_case(source, registry.root / "tiny_llama_opus_gateway_repair")
    learner = CommonsPolicyLearner(registry)
    federation = FederatedCommons(registry, tmp_path / "federation")
    economy = ComputeReductionEconomy(registry)
    promoter = CommonsCrystalPromoter(registry, economy, tmp_path / "crystals")
    monkeypatch.setattr(main, "commons_space_registry", registry)
    monkeypatch.setattr(main, "commons_policy_learner", learner)
    monkeypatch.setattr(main, "federated_commons", federation)
    monkeypatch.setattr(main, "commons_economy", economy)
    monkeypatch.setattr(main, "commons_crystal_promoter", promoter)
    monkeypatch.setattr(main, "commons_prototype_runner", FirstPrototypeRunner(registry, economy, promoter))

    async with AsyncClient(transport=ASGITransport(app=main.app), base_url="http://test") as client:
        listed = await client.get("/edgek/commons-spaces")
        detail = await client.get("/edgek/commons-spaces/tiny_llama_opus_gateway_repair")
        bundle = await client.get("/edgek/commons-spaces/tiny_llama_opus_gateway_repair/bundle")
        public_registry = await client.get("/edgek/public-commons-registry")
        public_card = await client.get("/edgek/public-commons-registry/tiny_llama_opus_gateway_repair")
        scale = await client.get("/edgek/commons-scale/readiness")
        candidates = await client.get("/edgek/commons-scale/registration-candidates?limit=3")
        denied = await client.post(
            "/edgek/commons-spaces/tiny_llama_opus_gateway_repair/adopt",
            json={"approved": False, "dry_run": False},
        )
        adopted = await client.post(
            "/edgek/commons-spaces/tiny_llama_opus_gateway_repair/adopt",
            json={"approved": True, "dry_run": False, "approved_by": "test", "reason": "local verification passed"},
        )
        recommendation = await client.post("/edgek/commons-policy/recommend", json={
            "task_class": "hard_gateway_repair", "risk": "high", "approval_required": True,
        })
        evaluation = await client.get("/edgek/commons-policy/evaluation")
        replay = await client.post(
            "/edgek/commons-spaces/tiny_llama_opus_gateway_repair/replay",
            json={"deterministic_only": True},
        )
        envelope = await client.post(
            "/edgek/federated-commons/prepare/tiny_llama_opus_gateway_repair",
            json={"contributor_id": "api_node", "ttl_days": 7},
        )
        allow = await client.post("/edgek/federated-commons/allowlist", json={
            "contributor_id": "api_node", "approved": True, "reason": "API test node",
            "public_key_hash": envelope.json()["signature"]["public_key_hash"],
        })
        ingested = await client.post("/edgek/federated-commons/ingest", json={"envelope": envelope.json()})
        economy_state = await client.get("/edgek/commons-economy")
        proof = await client.get("/edgek/commons-economy/proof/tiny_llama_opus_gateway_repair")
        denied_credit = await client.post(
            "/edgek/commons-economy/credits/tiny_llama_opus_gateway_repair",
            json={"approved": False, "reason": "API approval gate"},
        )
        engines = await client.get("/edgek/inference-engines")
        gpu_denied = await client.post("/edgek/inference-engines/vllm/generate", json={"prompt": "test"})
        crystal_chain = await client.get("/edgek/crystal-chain")

    assert listed.status_code == 200
    assert listed.json()["count"] == 1
    assert detail.json()["receipt_validation"]["valid"] is True
    assert bundle.status_code == 200
    assert bundle.headers["content-type"] == "application/zip"
    assert public_registry.json()["primary_action"] == "import_as_quarantined_hypothesis"
    assert public_card.json()["local_adoption_engine"]["required"] is True
    assert scale.json()["latency_interpretation"]["comparison"] == "broken_vs_working"
    assert candidates.json()["beast_object_type"] == "commons_registration_candidates"
    assert denied.json()["status"] == "approval_required"
    assert adopted.json()["adopted"] is True
    assert recommendation.json()["mode"] == "shadow"
    assert recommendation.json()["enforcing"] is False
    assert evaluation.json()["sample_size"] == 1
    assert replay.json()["reproduced"] is True
    assert allow.json()["allowlisted"] is True
    assert ingested.json()["state"] == "quarantined_hypothesis"
    assert economy_state.json()["mode"] == "non_financial_simulation"
    assert proof.json()["components"]["observed_tokens_credited"] == 0
    assert denied_credit.status_code == 400
    assert engines.json()["host_policy"] == "cpu_first_capability_gated"
    assert gpu_denied.status_code == 400
    assert crystal_chain.json()["valid"] is True
    assert crystal_chain.json()["financial_asset"] is False

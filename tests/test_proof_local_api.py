import importlib
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from app.kernel.registry.commons_space_registry import CommonsSpaceRegistry
from app.kernel.networking.commons_spaces import package_tiny_llama_case
from app.kernel.networking.federated_commons import FederatedCommons


ROOT = Path(__file__).resolve().parents[1]
CASE = ROOT / "benchmarks/results/tiny_llama_opus_case_study_qwen25_05b"


@pytest.mark.asyncio
async def test_proof_local_phase1_and_2_api(monkeypatch, tmp_path):
    main = importlib.import_module("app.main")
    registry = CommonsSpaceRegistry(tmp_path / "spaces")
    package_tiny_llama_case(CASE, registry.root / "tiny_llama_opus_gateway_repair")
    federation = FederatedCommons(registry, tmp_path / "federation")
    monkeypatch.setattr(main, "commons_space_registry", registry)
    monkeypatch.setattr(main, "federated_commons", federation)

    async with AsyncClient(transport=ASGITransport(app=main.app), base_url="http://test") as client:
        receipt = await client.get(
            "/edgek/proof-local/spaces/tiny_llama_opus_gateway_repair/receipt",
            params={"contributor_id": "api_node"},
        )
        manifest = await client.get("/edgek/proof-local/spaces/tiny_llama_opus_gateway_repair/manifest")
        verifiers = await client.get("/edgek/proof-local/spaces/tiny_llama_opus_gateway_repair/verifiers")
        allow = await client.post("/edgek/federated-commons/allowlist", json={
            "contributor_id": "api_node",
            "public_key_hash": receipt.json()["signature"]["public_key_hash"],
            "approved": True,
            "reason": "API proof-local test",
        })
        ingest = await client.post("/edgek/proof-local/receipt-packets/ingest", json={"packet": receipt.json()})
        advertisement = await client.post("/edgek/proof-local/advertisements/prepare", json={
            "node_id": "api_cpu_node", "contributor_id": "api_node",
            "task_classes": ["hard_gateway_repair"],
            "verifier_classes": ["schema_validation"],
            "rtt_bucket_ms": 10,
            "max_transfer_bytes": 6000000,
        })
        advertisement_ingest = await client.post(
            "/edgek/proof-local/advertisements/ingest", json={"advertisement": advertisement.json()},
        )
        quarantine = await client.post("/edgek/proof-local/route", json={
            "task_class": "hard_gateway_repair", "required_verifiers": ["schema_validation"],
            "max_lan_rtt_ms": 50, "max_transfer_bytes": 5000000,
        })
        untrusted_boolean = await client.post("/edgek/proof-local/route", json={
            "task_class": "hard_gateway_repair", "required_verifiers": ["schema_validation"],
            "max_lan_rtt_ms": 50, "max_transfer_bytes": 5000000,
            "local_replay_verified": True,
        })
        local_replay = registry.replay("tiny_llama_opus_gateway_repair")
        replayed = await client.post("/edgek/proof-local/route", json={
            "task_class": "hard_gateway_repair", "required_verifiers": ["schema_validation"],
            "max_lan_rtt_ms": 50, "max_transfer_bytes": 5000000,
            "reproduction_id": local_replay["reproduction_id"],
        })

    assert receipt.status_code == 200
    assert manifest.json()["beast_object_type"] == "proof_manifest_stage"
    assert verifiers.json()["execution_policy"].startswith("receiver_maps")
    assert allow.json()["allowlisted"] is True
    assert ingest.json()["next_stage"] == "request_manifest"
    assert advertisement_ingest.json()["state"] == "fresh_advisory_metadata"
    assert quarantine.json()["gate"]["decision"] == "quarantine_and_replay"
    assert untrusted_boolean.json()["gate"]["decision"] == "quarantine_and_replay"
    assert untrusted_boolean.json()["reproduction_evidence"]["caller_boolean_ignored"] is True
    assert replayed.json()["gate"]["decision"] == "trusted_lan_replay"
    assert replayed.json()["gate"]["provider_execution_requested"] is False

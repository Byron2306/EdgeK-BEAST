from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from app.kernel.compute.crystal_reuse_gateway import CrystalReuseGateway
from app.kernel.compute.enterprise import EnterpriseManager
from app.kernel.compute.integration_harness import BeastHarnessRequest, BeastIntegrationHarness
from app.kernel.readiness_hardening import ProductionReadinessHardeningGauntlet
from app.kernel.security.agent_passport import AgentPassport, AgentPassportPolicy
from app.kernel.security.residue_seal import ResidueSeal
from app.kernel.storage.durable_inference_storage import DurableInferenceStorage
from app.kernel.storage.memory_hull import MemoryHull
from app.main import app


class FastReadiness(ProductionReadinessHardeningGauntlet):
    def production_ops_gate(self):
        return {
            "beast_object_type": "production_ops_hardening_gate",
            "status": "satisfied",
            "lab_status": "satisfied",
            "checks": {"thin_harness_test": True},
            "external_checks": {},
            "claim_boundary": "test gate",
        }


def _harness(tmp_path, provider_executor=None):
    seal = ResidueSeal(tmp_path / "keys")
    hull = MemoryHull(tmp_path / "vault", seal=seal)
    storage = DurableInferenceStorage(tmp_path / "durable")
    enterprise = EnterpriseManager(db_path=str(tmp_path / "enterprise.db"))
    gateway = CrystalReuseGateway(storage=storage, memory_hull=hull, seal=seal)
    harness = BeastIntegrationHarness(
        passport_policy=AgentPassportPolicy(seal=seal, sign_decisions=True),
        crystal_gateway=gateway,
        residue_seal=seal,
        memory_hull=hull,
        enterprise_manager=enterprise,
        readiness=FastReadiness(tmp_path / "readiness"),
        provider_executor=provider_executor,
    )
    return harness, gateway, storage, hull, enterprise


def test_thin_integration_harness_executes_provider_then_records_all_layers(tmp_path):
    def provider(request):
        return {
            "response": "provider answer",
            "provider": "local",
            "model": request.model,
            "cost_usd": 0.02,
            "total_tokens": 42,
        }

    harness, _gateway, _storage, hull, enterprise = _harness(tmp_path, provider_executor=provider)
    team = enterprise.create_team("Harness", daily_request_limit=5, daily_cost_limit_usd=1.0)
    user = enterprise.create_user(team["team_id"], "harness@example.com")
    caller = AgentPassport.local(
        "proxy/gateway",
        claims={"enterprise": {"team_id": team["team_id"], "user_id": user["user_id"], "key_id": "vk_test"}},
    )

    receipt = harness.run(
        BeastHarnessRequest(
            prompt="produce a verified reusable answer",
            model="local-test",
            caller=caller,
            provider="local",
            enterprise={"team_id": team["team_id"], "user_id": user["user_id"], "key_id": "vk_test"},
            projected_cost_usd=0.02,
            projected_tokens=42,
            metadata={"trace_id": "trace_harness_provider"},
        )
    )

    assert receipt["beast_object_type"] == "beast_thin_integration_harness_receipt"
    assert receipt["passport"]["allowed"] is True
    assert receipt["crystal_reuse_decision"]["action"] == "execute_local_cpu"
    assert receipt["provider_result"]["route"] == "local_cpu"
    assert receipt["provider_result"]["cloud_used"] is False
    assert receipt["provider_result"]["called"] is True
    assert receipt["verification"]["verified"] is True
    assert receipt["crystal_record"]["memory_hull"]["verified"] is True
    assert receipt["enterprise"]["usage"]["requests"] == 1
    assert receipt["enterprise"]["encrypted_trace"]["encrypted"] is True
    assert receipt["readiness_gate"]["receipt_hash"].startswith("sha256:")
    assert receipt["residue_seal"]["purpose"] == "beast_thin_integration_harness_receipt"
    assert hull.verify_sidecar(Path(receipt["crystal_record"]["memory_hull"]["sidecar_path"]))["verified"] is True


def test_thin_integration_harness_reuses_crystal_without_provider_call(tmp_path):
    calls = {"count": 0}

    def provider(_request):
        calls["count"] += 1
        return "should not run"

    harness, gateway, storage, _hull, _enterprise = _harness(tmp_path, provider_executor=provider)
    request = BeastHarnessRequest(
        prompt="already crystallized",
        model="local-test",
        caller=AgentPassport.local("proxy/gateway"),
        metadata={"trace_id": "trace_harness_reuse"},
    )
    crystal_request = request.crystal_request()
    storage.store_answer(crystal_request.prompt_hash, crystal_request.model, crystal_request.parameters, "cached answer")

    receipt = harness.run(request)

    assert calls["count"] == 0
    assert receipt["crystal_reuse_decision"]["action"] == "reuse_answer"
    assert receipt["provider_result"]["status"] == "skipped_by_crystal_reuse"
    assert receipt["provider_result"]["response"] == "cached answer"
    assert receipt["crystal_record"] is None
    assert gateway.decide(crystal_request).action == "reuse_answer"


def test_thin_integration_harness_never_crystallizes_placeholder_as_provider_output(tmp_path):
    harness, _gateway, _storage, _hull, _enterprise = _harness(tmp_path)

    receipt = harness.run(
        BeastHarnessRequest(
            prompt="must not fabricate a coding completion",
            model="local-test",
            caller=AgentPassport.local("proxy/gateway"),
            provider="local",
            metadata={"trace_id": "trace_harness_placeholder"},
        )
    )

    assert receipt["provider_result"]["synthetic_placeholder"] is True
    assert receipt["provider_result"]["status"] == "unavailable_no_provider_executor"
    assert receipt["verification"]["verified"] is False
    assert receipt["verification"]["reason"] == "synthetic_placeholder_is_not_a_provider_result"
    assert receipt["crystal_record"] is None


def test_thin_integration_harness_can_execute_through_local_gateway(tmp_path):
    class Candidate:
        engine_id = "ollama"

    class Fabric:
        def cpu_candidates(self):
            return [Candidate()]

        def generate(self, engine_id, **kwargs):
            return {
                "engine_id": engine_id,
                "response": "live local gateway answer",
                "prompt_tokens": 7,
                "output_tokens": 4,
                "latency_ms": 3.2,
                "status": "succeeded",
            }

    from app.kernel.compute.local_execution_gateway import LocalExecutionGateway

    seal = ResidueSeal(tmp_path / "keys")
    hull = MemoryHull(tmp_path / "vault", seal=seal)
    storage = DurableInferenceStorage(tmp_path / "durable")
    gateway = CrystalReuseGateway(storage=storage, memory_hull=hull, seal=seal)
    harness = BeastIntegrationHarness(
        passport_policy=AgentPassportPolicy(seal=seal, sign_decisions=True),
        crystal_gateway=gateway,
        residue_seal=seal,
        memory_hull=hull,
        enterprise_manager=EnterpriseManager(db_path=str(tmp_path / "enterprise.db")),
        readiness=FastReadiness(tmp_path / "readiness"),
        local_execution_gateway=LocalExecutionGateway(Fabric()),
    )

    receipt = harness.run(
        BeastHarnessRequest(
            prompt="use the actual local execution gateway",
            model="local-test",
            provider="local_cpu",
            caller=AgentPassport.local("proxy/gateway"),
            metadata={"trace_id": "trace_local_gateway"},
        )
    )

    assert receipt["provider_result"]["response"] == "live local gateway answer"
    assert receipt["provider_result"]["engine_id"] == "ollama"
    assert receipt["crystal_record"]["semantic_credit_id"].startswith("scc_")


@pytest.mark.asyncio
async def test_thin_integration_harness_endpoint_returns_receipt():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/edgek/integration-harness/run",
            json={
                "prompt": "endpoint harness smoke",
                "model": "local-test",
                "provider": "local",
                "metadata": {"trace_id": "trace_endpoint_harness"},
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["beast_object_type"] == "beast_thin_integration_harness_receipt"
    assert payload["passport"]["allowed"] is True
    assert payload["readiness_gate"]["gate"] == "production_ops"

import pytest
from httpx import ASGITransport, AsyncClient

from app.cli.api import BeastApiClient
from app.kernel.compute.integration_acceptance import CrystalIntegrationAcceptanceHarness
from app.kernel.compute.kv_cache_transport import CrossEngineKVCacheTransport
from app.kernel.compute.kv_restore_harness import KVRestoreHarness
from app.kernel.readiness_hardening import ProductionReadinessHardeningGauntlet
from app.kernel.security.agent_passport import AgentPassport
from app.main import app


def test_crystal_integration_acceptance_contracts_pass_without_live_services():
    receipt = CrystalIntegrationAcceptanceHarness().run(probe=False)

    assert receipt["beast_object_type"] == "beast_local_capability_acceptance_receipt"
    assert receipt["accepted_count"] >= 7
    assert all(item["contract_ok"] for item in receipt["results"])


def test_kv_restore_harness_moves_and_restores_tensor_payload(tmp_path):
    transport = CrossEngineKVCacheTransport(storage_dir=tmp_path / "kv")
    receipt = KVRestoreHarness(transport).run()

    assert receipt["beast_object_type"] == "beast_kv_restore_harness_receipt"
    assert receipt["moved_to_storage"] is True
    assert receipt["restored_to_cpu"] is True
    assert receipt["lookup_hit"] is True
    assert receipt["engine_checks"]["ollama"]["status"] == "restored"
    assert receipt["transport_stats"]["total_blocks"] >= 1


def test_readiness_soak_and_window_receipts(tmp_path):
    readiness = ProductionReadinessHardeningGauntlet(tmp_path)

    soak = readiness.federation_soak_gate(nodes=3, cycles=2)
    window = readiness.workload_frequency_receipt(window_days=7)

    assert soak["beast_object_type"] == "federation_soak_hardening_gate"
    assert soak["checks"]["node_count_at_least_three"] is True
    assert soak["checks"]["duplicates_suppressed"] is True
    assert window["beast_object_type"] == "workload_frequency_window_receipt"
    assert window["window_days"] == 7


def test_agent_passport_binds_to_workload_certificate():
    passport = AgentPassport.from_workload_certificate(
        "proxy/gateway",
        "-----BEGIN CERTIFICATE-----\nMIIB\n-----END CERTIFICATE-----\n",
    )

    assert passport.cert_fingerprint.startswith("sha256:")
    assert passport.claims["workload_identity"]["mtls_or_spire_ready"] is True


@pytest.mark.asyncio
async def test_gap_closure_api_endpoints_return_receipts():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        acceptance = await client.get("/edgek/crystal-reuse/acceptance")
        kv = await client.get("/edgek/kv-cache/restore-harness")
        groups = await client.get("/edgek/api/groups")
        route = await client.get("/edgek/providers/secrets/route/litellm")
        passport = await client.post(
            "/edgek/agent-passport/workload-certificate",
            json={"component": "proxy/gateway", "cert_pem": "-----BEGIN CERTIFICATE-----\nMIIB\n-----END CERTIFICATE-----\n"},
        )

    assert acceptance.status_code == 200
    assert acceptance.json()["beast_object_type"] == "beast_local_capability_acceptance_receipt"
    assert kv.status_code == 200
    assert kv.json()["lookup_hit"] is True
    assert groups.json()["stable"]["integration_harness"] == ["/edgek/integration-harness/run"]
    assert route.json()["status"] == "ready"
    assert passport.json()["cert_fingerprint"].startswith("sha256:")


@pytest.mark.asyncio
async def test_tui_live_turn_uses_integration_harness_by_default(monkeypatch):
    client = BeastApiClient("http://test")

    async def fake_harness(prompt, provider, model="beast-auto", *, metadata=None):
        return {
            "crystal_reuse_decision": {
                "decision_id": "crystal_test",
                "action": "execute_local_cpu",
                "source": "test",
                "confidence": 0.8,
            },
            "provider_result": {"called": True, "response": "harness answer"},
            "verification": {"verified": True},
        }

    async def no_op(*_args, **_kwargs):
        return None

    async def fake_action(*_args, **_kwargs):
        return _action(True, {"ready": True})

    monkeypatch.setattr(client, "integration_harness_turn", fake_harness)
    monkeypatch.setattr(client, "update_prec", no_op)
    monkeypatch.setattr(client, "build_task_envelope", fake_action)
    monkeypatch.setattr(client, "compile_insight", fake_action)
    monkeypatch.setattr(client, "prepare_handoff", fake_action)

    result = await client.live_turn("hello", [], provider="litellm", lifecycle_id="")

    assert result.assistant_text == "harness answer"
    assert result.data["integration_harness_receipt"]["provider_result"]["called"] is True
    assert any("integration harness" in event for event in result.tool_events)


def _action(ok, data):
    from app.cli.api import ActionResult

    return ActionResult(ok, "test", "ok", data)

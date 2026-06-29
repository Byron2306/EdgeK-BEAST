import importlib

import pytest
from httpx import ASGITransport, AsyncClient

from app.kernel.storage.outcome_evidence import NegativeCapabilityStore


@pytest.mark.asyncio
async def test_crystal_compute_api_records_reports_and_maintains(monkeypatch):
    main = importlib.import_module("app.main")
    store = NegativeCapabilityStore()
    monkeypatch.setattr(main, "crystal_compute_store", store)
    async with AsyncClient(transport=ASGITransport(app=main.app), base_url="http://test") as client:
        recorded = await client.post("/edgek/crystal-compute/outcomes", json={
            "capability_id": "provider:nvidia_nim",
            "task_class": "chat_completion",
            "outcome": "failure",
            "failure_category": "stream_incomplete",
            "scope": {"provider": "nvidia_nim", "model": "nemotron"},
            "retries": 1,
            "repair_depth": 1,
        })
        state = await client.get("/edgek/crystal-compute")
        maintained = await client.post("/edgek/crystal-compute/maintenance", json={})

    assert recorded.status_code == 200
    assert state.json()["summary"]["outcomes"] == 1
    assert len(state.json()["friction_profiles"]) == 1
    assert maintained.json()["records_after"] == 1


@pytest.mark.asyncio
async def test_crystal_compute_override_requires_operator_reason(monkeypatch):
    main = importlib.import_module("app.main")
    store = NegativeCapabilityStore()
    monkeypatch.setattr(main, "crystal_compute_store", store)
    evidence = await main.edgek_crystal_compute_record({
        "capability_id": "provider:nim", "task_class": "chat_completion", "outcome": "failure",
        "failure_category": "timeout", "scope": {"provider": "nim"},
    })
    record_id = evidence["negative_capability"]["record_id"]
    async with AsyncClient(transport=ASGITransport(app=main.app), base_url="http://test") as client:
        denied = await client.post(
            f"/edgek/crystal-compute/negative/{record_id}/override",
            json={"state": "suppressed", "approved_by": "operator", "approved": True},
        )
        accepted = await client.post(
            f"/edgek/crystal-compute/negative/{record_id}/override",
            json={"state": "suppressed", "approved_by": "operator", "reason": "incident resolved", "approved": True},
        )

    assert denied.status_code == 400
    assert accepted.json()["state"] == "suppressed"

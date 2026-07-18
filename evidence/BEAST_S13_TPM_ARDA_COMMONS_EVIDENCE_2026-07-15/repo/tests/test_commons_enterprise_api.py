import pytest
from httpx import ASGITransport, AsyncClient

import app.main as main
from app.kernel.commons.enterprise_plane import CommonsEnterprisePlane


@pytest.mark.asyncio
async def test_enterprise_commons_api_binds_identity_and_persists_route_event(tmp_path, monkeypatch):
    plane=CommonsEnterprisePlane(tmp_path)
    monkeypatch.setattr(main,"commons_enterprise_plane",plane)
    digest=main._active_workspace_identity.digest()
    async with AsyncClient(transport=ASGITransport(app=main.app),base_url="http://test") as client:
        snapshot=await client.get("/edgek/control-plane/commons")
        event=await client.post("/edgek/control-plane/commons/routes/events",headers={"X-BEAST-Workspace-Identity":digest},json={"route_id":"provider:test","event":"timeout"})
    assert snapshot.status_code==200 and snapshot.json()["status"]=="configuration_required"
    assert event.status_code==200 and event.headers["X-BEAST-Workspace-Identity-Status"]=="matched"
    assert CommonsEnterprisePlane(tmp_path).routes.score("provider:test").penalty>0


@pytest.mark.asyncio
async def test_enterprise_commons_issues_one_use_tpm_challenge(tmp_path, monkeypatch):
    plane = CommonsEnterprisePlane(tmp_path)
    monkeypatch.setattr(main, "commons_enterprise_plane", plane)
    digest = main._active_workspace_identity.digest()
    async with AsyncClient(transport=ASGITransport(app=main.app), base_url="http://test") as client:
        response = await client.post(
            "/edgek/control-plane/commons/attestation/challenges",
            headers={"X-BEAST-Workspace-Identity": digest},
            json={"node_id": "colleague-windows-node", "ttl_seconds": 120},
        )
    assert response.status_code == 200
    value = response.json()
    assert value["admitted"] is False
    assert len(value["challenge"]["nonce"]) == 64
    assert value["challenge"]["pcrs"] == [0, 2, 4, 7, 10, 14]
    assert plane.tpm_challenges.get(value["challenge"]["challenge_id"]).state == "issued"

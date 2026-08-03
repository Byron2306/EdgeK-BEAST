from httpx import ASGITransport, AsyncClient
import pytest

from app.main import app


@pytest.mark.asyncio
async def test_operator_language_api_resolves_beast_endpoint():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/edgek/compute/operator-language",
            json={"utterance": "what endpoint is beast on?", "tone": "concise"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["receipt"]["state"] == "resolved"
    assert payload["receipt"]["intent"] == "read_service_endpoint"
    assert payload["receipt"]["service_names"] == ["beast"]
    assert payload["receipt"]["provider_called"] is False
    assert payload["receipt"]["action_taken"] is False
    assert "127.0.0.1:8101" in payload["output"]


@pytest.mark.asyncio
async def test_operator_language_api_requires_utterance():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/edgek/compute/operator-language", json={})

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_scene_capsule_api_composes_render_only_svg():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/edgek/compute/scene-capsule",
            json={
                "capsule_id": "scene-capsule:api-test",
                "scene": {
                    "scene_id": "scene:api-status",
                    "canvas": {"width": 180, "height": 100, "background": "#07110d"},
                    "opcodes": [
                        {"kind": "place_asset", "args": {"asset_id": "beast.mascot.idle", "x": 8, "y": 14, "width": 56, "height": 56}},
                        {"kind": "draw_text", "args": {"x": 72, "y": 44, "text": "BEAST", "font_size": 16}},
                    ],
                },
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["beast_object_type"] == "scene_capsule_result"
    assert payload["svg"].startswith("<svg")
    assert payload["composition_receipt"]["verified"] is True
    assert payload["capsule"]["maximum_authority"] == "render_only"
    assert payload["capsule"]["network_scope"] == "none"
    assert payload["capsule"]["provider_scope"] == "none"
    assert payload["capsule"]["physical_scope"] == "none"
    assert payload["capsule"]["capsule_digest"].startswith("sha256:")


@pytest.mark.asyncio
async def test_visual_residual_api_runs_region_bound_generation():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/edgek/compute/visual-residual",
            json={
                "capsule_id": "scene-capsule:visual-api-test",
                "scene": {
                    "scene_id": "scene:visual-api",
                    "canvas": {"width": 180, "height": 100, "background": "#07110d"},
                    "opcodes": [
                        {"kind": "place_asset", "args": {"asset_id": "beast.mascot.idle", "x": 8, "y": 14, "width": 56, "height": 56}},
                        {"kind": "draw_text", "args": {"x": 72, "y": 44, "text": "BEAST", "font_size": 16}},
                    ],
                },
                "mask": {"mask_id": "mask:api-status-light", "x": 120, "y": 24, "width": 16, "height": 16},
                "prompt": "green status light",
                "seed": 5,
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["beast_object_type"] == "visual_residual_result"
    assert payload["output_base64"]
    assert payload["receipt"]["scene_capsule_digest"] == payload["scene_capsule"]["capsule_digest"]
    assert payload["receipt"]["verified"] is True
    assert payload["receipt"]["network_used"] is False
    assert payload["receipt"]["details"]["region_only"] is True


@pytest.mark.asyncio
async def test_provider_reduction_api_returns_scorecard():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/edgek/compute/provider-reduction")

    assert response.status_code == 200
    payload = response.json()
    assert payload["beast_object_type"] == "provider_reduction_scorecard"
    assert "observed_channels" in payload
    assert payload["scorecard_digest"].startswith("sha256:")


@pytest.mark.asyncio
async def test_reduction_evidence_api_rejects_raw_prompt_payloads():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/edgek/compute/reduction-evidence",
            json={
                "source_system": "forge_kv_prompt_cache",
                "receipt": {
                    "raw_prompt": "do not ingest me",
                    "prompt_tokens_avoided": 10,
                },
            },
        )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_reduction_evidence_discovery_api_rejects_out_of_scope_paths():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/edgek/compute/reduction-evidence/discover",
            json={"paths": ["/tmp"], "max_files": 10},
        )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_visual_assets_api_returns_registry_view():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/edgek/compute/visual-assets")

    assert response.status_code == 200
    payload = response.json()
    assert payload["beast_object_type"] == "visual_asset_registry"
    assert "assets" in payload
    assert payload["registry_digest"].startswith("sha256:")

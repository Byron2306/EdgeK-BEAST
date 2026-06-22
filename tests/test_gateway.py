import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


def _client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.mark.asyncio
async def test_health_endpoint():
    async with _client() as client:
        response = await client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


@pytest.mark.asyncio
async def test_root_endpoint():
    async with _client() as client:
        response = await client.get("/")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "BEAST Commons" in response.text
    assert "/beast-assets/idle/frame_00.png" in response.text
    assert "/commons-media/beast-logo.png" in response.text
    assert "/commons-media/inference-economy.mp4" in response.text
    assert "/commons-media/inference-inversion.pptx" in response.text
    assert "TUI Web Surface" in response.text
    assert "Raw status" not in response.text
    assert 'href="/edgek/federated-commons"' not in response.text


@pytest.mark.asyncio
async def test_root_info_endpoint():
    async with _client() as client:
        response = await client.get("/edgek/root-info")

    assert response.status_code == 200
    assert response.json()["service"] == "EdgeK BEAST Gateway"


@pytest.mark.asyncio
async def test_commons_media_assets():
    async with _client() as client:
        logo = await client.head("/commons-media/beast-logo.png")
        video = await client.head("/commons-media/inference-economy.mp4")
        deck = await client.head("/commons-media/inference-inversion.pptx")

    assert logo.status_code == 200
    assert logo.headers["content-type"] == "image/png"
    assert video.status_code == 200
    assert "video" in video.headers["content-type"]
    assert deck.status_code == 200


@pytest.mark.asyncio
async def test_openai_models():
    async with _client() as client:
        response = await client.get("/v1/models")

    assert response.status_code == 200
    assert "data" in response.json()


@pytest.mark.asyncio
async def test_openai_chat_completion():
    async with _client() as client:
        payload = {
            "model": "gpt-3.5-turbo",
            "messages": [
                {"role": "user", "content": "Hello, EdgeK BEAST!"}
            ],
            "max_tokens": 50,
        }
        response = await client.post("/v1/chat/completions", json=payload)

    assert response.status_code == 200
    assert "choices" in response.json()


@pytest.mark.asyncio
async def test_anthropic_message():
    async with _client() as client:
        payload = {
            "model": "claude-3-haiku-20240307",
            "max_tokens": 100,
            "messages": [
                {"role": "user", "content": "Hello, EdgeK BEAST!"}
            ],
        }
        response = await client.post("/v1/messages", json=payload)

    assert response.status_code == 200
    assert "content" in response.json() or "error" in response.json()

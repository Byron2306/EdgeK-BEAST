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
    assert response.json()["service"] == "EdgeK BEAST Gateway"


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

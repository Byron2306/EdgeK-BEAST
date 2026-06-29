import pytest
from httpx import ASGITransport, AsyncClient

from app.kernel.compute.perceive import ProviderType, perceiver
from app.main import app


def test_gemini_perceiver_normalizes_contents():
    ir = perceiver.perceive(
        {
            "model": "gemini-2.5-flash",
            "contents": [
                {"role": "user", "parts": [{"text": "Inspect the gateway."}]},
                {"role": "model", "parts": [{"text": "Acknowledged."}]},
            ],
            "generationConfig": {"maxOutputTokens": 128, "temperature": 0.1},
        },
        ProviderType.GEMINI,
    )

    assert ir.metadata["provider"] == "gemini"
    assert ir.messages[0]["role"] == "user"
    assert ir.messages[1]["role"] == "assistant"
    assert ir.max_tokens == 128
    assert ir.temperature == 0.1


@pytest.mark.asyncio
async def test_gemini_generate_content_endpoint_simulates_response(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/v1beta/models/gemini-2.5-flash:generateContent",
            json={
                "contents": [
                    {"role": "user", "parts": [{"text": "Say BEAST in one sentence."}]}
                ],
                "generationConfig": {"maxOutputTokens": 32},
            },
        )

    assert response.status_code == 200
    body = response.json()
    text = body["candidates"][0]["content"]["parts"][0]["text"]
    assert isinstance(text, str)
    assert text
    assert body["usageMetadata"]["totalTokenCount"] > 0

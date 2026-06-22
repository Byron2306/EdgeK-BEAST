import pytest

from app.cli.api import (
    ActionResult,
    BeastApiClient,
    classify_stream_failure,
    provider_stream_read_timeout,
)


def test_nvidia_stream_gets_longer_idle_timeout():
    assert provider_stream_read_timeout("nvidia_nim") == 210.0
    assert provider_stream_read_timeout("groq") == 90.0


def test_stream_failure_classification_separates_provider_timeout_from_stack_death():
    timeout = classify_stream_failure("ReadTimeout after waiting for NIM")
    refused = classify_stream_failure("All connection attempts failed: connection refused")

    assert timeout["recoverable"] is True
    assert timeout["local_service_failure"] is False
    assert refused["local_service_failure"] is True


@pytest.mark.asyncio
async def test_partial_provider_stream_is_preserved_and_recovered_locally(monkeypatch):
    client = BeastApiClient("http://gateway")

    async def result(*args, **kwargs):
        return ActionResult(True, "ok", "ok", {"ready": True})

    async def interrupted(*args, **kwargs):
        yield {"type": "token", "text": "provider partial"}
        yield {
            "type": "error",
            "error": "server disconnected without sending a completion marker",
            "recoverable": True,
            "local_service_failure": True,
        }

    async def fallback(*args, **kwargs):
        return "local continuation"

    monkeypatch.setattr(client, "build_task_envelope", result)
    monkeypatch.setattr(client, "compile_insight", result)
    monkeypatch.setattr(client, "prepare_handoff", result)
    monkeypatch.setattr(client, "stream_chat_completion", interrupted)
    monkeypatch.setattr(client, "_scout_fallback_reply", fallback)

    events = [event async for event in client.stream_live_turn("hello", [], provider="nvidia_nim")]
    done = events[-1]
    text = "".join(str(event.get("text") or "") for event in events if event.get("type") == "token")

    assert "provider partial" in text
    assert "local continuation" in text
    assert done["type"] == "done"
    assert done["data"]["provider_completed"] is False
    assert done["data"]["provider_recovered"] is True
    assert done["data"]["heal_recommended"] is True

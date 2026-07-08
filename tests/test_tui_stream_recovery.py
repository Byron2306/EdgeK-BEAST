import pytest

from app.cli.api import (
    ActionResult,
    BeastApiClient,
    classify_stream_failure,
    provider_stream_continuations,
    provider_stream_read_timeout,
)


def test_nvidia_stream_gets_longer_idle_timeout():
    assert provider_stream_read_timeout("nvidia_nim") == 210.0
    assert provider_stream_read_timeout("groq") == 90.0


def test_stream_continuations_default_to_bounded_recovery():
    assert provider_stream_continuations("nvidia_nim") == 2


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


@pytest.mark.asyncio
async def test_stream_chat_completion_continues_after_length_finish(monkeypatch):
    client = BeastApiClient("http://gateway")
    calls = []

    class FakeResponse:
        status_code = 200
        headers = {"content-type": "text/event-stream"}

        def __init__(self, attempt):
            self.attempt = attempt

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def aiter_lines(self):
            if self.attempt == 1:
                yield 'data: {"choices":[{"delta":{"content":"first "}}]}'
                yield 'data: {"choices":[{"delta":{},"finish_reason":"length"}]}'
            else:
                yield 'data: {"choices":[{"delta":{"content":"second"}}]}'
                yield 'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}'
                yield "data: [DONE]"

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        def stream(self, *args, **kwargs):
            calls.append(kwargs.get("json") or {})
            return FakeResponse(len(calls))

    monkeypatch.setattr("app.cli.api.httpx.AsyncClient", FakeClient)
    monkeypatch.setenv("BEAST_TUI_STREAM_CONTINUATIONS", "1")

    events = [
        event async for event in client.stream_chat_completion(
            "nvidia_nim",
            [{"role": "user", "content": "long answer"}],
        )
    ]
    text = "".join(str(event.get("text") or "") for event in events if event.get("type") == "token")
    done = events[-1]

    assert text == "first second"
    assert done["type"] == "provider_done"
    assert done["completed"] is True
    assert done["finish_reason"] == "stop"
    assert len(calls) == 2
    assert calls[1]["messages"][-1]["content"].startswith("Continue the previous answer directly")

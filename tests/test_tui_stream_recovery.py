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
async def test_partial_provider_stream_never_appends_fallback_when_disabled(monkeypatch):
    client = BeastApiClient("http://gateway")

    async def result(*args, **kwargs):
        return ActionResult(True, "ok", "ok", {"ready": True})

    async def interrupted(*args, **kwargs):
        yield {"type": "token", "text": '{"kind":"beast.action_intent.v1"'}
        yield {"type": "error", "error": "stream closed"}

    async def forbidden_fallback(*args, **kwargs):
        raise AssertionError("coding stream must not append local fallback text")

    monkeypatch.setattr(client, "build_task_envelope", result)
    monkeypatch.setattr(client, "compile_insight", result)
    monkeypatch.setattr(client, "prepare_handoff", result)
    monkeypatch.setattr(client, "stream_chat_completion", interrupted)
    monkeypatch.setattr(client, "_scout_fallback_reply", forbidden_fallback)

    events = [
        event async for event in client.stream_live_turn(
            "edit code", [], provider="nvidia_nim", governance_level="ide_agent_session", allow_fallback=False
        )
    ]

    assert any(event.get("type") == "token" for event in events)
    assert events[-1]["type"] == "error"
    assert events[-1]["partial_response"] is True


@pytest.mark.asyncio
async def test_completed_direct_stream_uses_context_safe_crystal_preflight_and_records(monkeypatch, tmp_path):
    target = tmp_path / "router.py"
    target.write_text("def route():\n    return 'local'\n", encoding="utf-8")
    client = BeastApiClient("http://gateway", workspace=tmp_path)
    observed = {}

    async def action(*args, **kwargs):
        return ActionResult(True, "ok", "ok", {"ready": True})

    async def decide(prompt, provider, model, **kwargs):
        observed["decision_prompt"] = prompt
        observed["decision_kwargs"] = kwargs
        return {"action": "execute_local_cpu", "source": "local_execution_gateway", "confidence": 0.7}

    async def provider(*args, **kwargs):
        yield {"type": "token", "text": "safe answer"}
        yield {"type": "provider_done", "completed": True, "finish_reason": "stop"}

    async def record(prompt, response, provider, model, **kwargs):
        observed["record_prompt"] = prompt
        observed["record_response"] = response
        observed["record_kwargs"] = kwargs
        return {"status": "recorded", "answer_credit_id": "answer-1"}

    async def outcome(*args, **kwargs):
        return True

    monkeypatch.setattr(client, "build_task_envelope", action)
    monkeypatch.setattr(client, "compile_insight", action)
    monkeypatch.setattr(client, "prepare_handoff", action)
    monkeypatch.setattr(client, "crystal_reuse_decision", decide)
    monkeypatch.setattr(client, "stream_chat_completion", provider)
    monkeypatch.setattr(client, "record_crystal_response", record)
    monkeypatch.setattr(client, "record_outcome_evidence", outcome)

    events = [event async for event in client.stream_live_turn(
        "Explain this route.",
        [{"role": "user", "content": "Use the current repository."}],
        provider="local",
        model="coder",
        context_files=["router.py"],
        governance_level="ide_agent_session",
    )]

    assert observed["decision_prompt"] == observed["record_prompt"]
    assert "router.py" in observed["decision_prompt"]
    assert observed["decision_kwargs"]["task_class"] == "ide_coding_completion"
    assert observed["record_response"] == "safe answer"
    assert observed["record_kwargs"]["verified"] is False
    assert any(event.get("type") == "tool" and "crystal record: recorded" in event.get("text", "") for event in events)


@pytest.mark.asyncio
async def test_crystal_hit_short_circuits_prec_and_provider_compute(monkeypatch, tmp_path):
    client = BeastApiClient("http://gateway", workspace=tmp_path)

    async def decide(*args, **kwargs):
        return {
            "decision_id": "reuse-short-circuit",
            "action": "reuse_answer",
            "source": "durable_inference_storage",
            "confidence": 1.0,
            "avoided_tokens_estimate": 90,
            "payload": {"reuse": {"payload": {"response": "crystallized answer"}}},
        }

    async def forbidden(*args, **kwargs):
        raise AssertionError("PREC/provider compute must not run on a crystal hit")

    monkeypatch.setattr(client, "crystal_reuse_decision", decide)
    monkeypatch.setattr(client, "build_task_envelope", forbidden)
    monkeypatch.setattr(client, "compile_insight", forbidden)
    monkeypatch.setattr(client, "prepare_handoff", forbidden)
    monkeypatch.setattr(client, "stream_chat_completion", forbidden)

    events = [event async for event in client.stream_live_turn("same task", [], provider="local", model="coder")]
    text = "".join(str(event.get("text") or "") for event in events if event.get("type") == "token")

    assert text == "crystallized answer"
    assert events[-1]["type"] == "done"
    assert events[-1]["data"]["provider_completed"] is True
    assert events[-1]["data"]["provider_streaming"] is False


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


@pytest.mark.asyncio
async def test_stream_chat_completion_accepts_complete_action_ir_without_terminal_marker(monkeypatch):
    client = BeastApiClient("http://gateway")

    class FakeResponse:
        status_code = 200
        headers = {"content-type": "text/event-stream"}

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def aiter_lines(self):
            yield 'data: {"choices":[{"delta":{"content":"{\\"kind\\":\\"beast.action_intent.v1\\",\\"actions\\":[]}"}}]}'

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        def stream(self, *args, **kwargs):
            return FakeResponse()

    monkeypatch.setattr("app.cli.api.httpx.AsyncClient", FakeClient)

    events = [
        event async for event in client.stream_chat_completion(
            "nvidia_nim",
            [{"role": "user", "content": "return action IR"}],
            accept_unmarked_action_ir=True,
        )
    ]

    assert events[-1]["type"] == "provider_done"
    assert events[-1]["completed"] is True
    assert events[-1]["finish_reason"] == "stream_closed_after_complete_action_ir"


@pytest.mark.asyncio
async def test_google_stream_uses_native_gemini_adapter(monkeypatch):
    client = BeastApiClient("http://gateway")
    observed = {}

    class FakeResponse:
        status_code = 200
        text = ""

        def json(self):
            return {
                "candidates": [
                    {"content": {"parts": [{"text": "native Gemini response"}]}}
                ]
            }

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, url, **kwargs):
            observed["url"] = url
            observed["payload"] = kwargs["json"]
            return FakeResponse()

    monkeypatch.setattr("app.cli.api.httpx.AsyncClient", FakeClient)

    events = [
        event async for event in client.stream_chat_completion(
            "google",
            [
                {"role": "system", "content": "Return only JSON."},
                {"role": "user", "content": "Fix the service."},
            ],
            model="gemini-2.5-flash",
        )
    ]

    assert observed["url"].endswith("/proxy/gemini/v1beta/models/gemini-2.5-flash:generateContent")
    assert observed["payload"]["contents"][0]["role"] == "user"
    assert observed["payload"]["systemInstruction"]["parts"][0]["text"] == "Return only JSON."
    assert events[0] == {"type": "token", "text": "native Gemini response"}
    assert events[-1]["finish_reason"] == "native_gemini_response"


@pytest.mark.asyncio
async def test_huggingface_stream_uses_native_adapter_path(monkeypatch):
    client = BeastApiClient("http://gateway")
    observed = {}

    class FakeResponse:
        status_code = 200
        headers = {"content-type": "application/json"}

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def aread(self):
            return b'{"choices":[{"message":{"content":"native HF response"},"finish_reason":"stop"}]}'

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        def stream(self, method, url, **kwargs):
            observed.update(method=method, url=url, params=kwargs.get("params"))
            return FakeResponse()

    monkeypatch.setattr("app.cli.api.httpx.AsyncClient", FakeClient)
    events = [event async for event in client.stream_chat_completion(
        "huggingface",
        [{"role": "user", "content": "Return a short answer."}],
        model="hf/openai/gpt-oss-120b",
    )]
    assert observed["url"].endswith("/proxy/huggingface/v1/chat/completions")
    assert observed["params"] == {}
    assert any(event.get("text") == "native HF response" for event in events)


@pytest.mark.asyncio
async def test_google_non_streaming_chat_and_text_extraction_use_native_adapter(monkeypatch):
    client = BeastApiClient("http://gateway")
    observed = {}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"candidates": [{"content": {"parts": [{"text": "patch plan JSON"}]}}]}

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, url, **kwargs):
            observed["url"] = url
            return FakeResponse()

    monkeypatch.setattr("app.cli.api.httpx.AsyncClient", FakeClient)

    result = await client.chat_completion(
        "google", [{"role": "user", "content": "draft a patch"}], "gemini-2.5-flash"
    )

    assert result.ok is True
    assert observed["url"].endswith("/proxy/gemini/v1beta/models/gemini-2.5-flash:generateContent")
    assert client._extract_assistant_text(result.data) == "patch plan JSON"


@pytest.mark.asyncio
async def test_anthropic_stream_uses_native_messages_adapter(monkeypatch):
    client = BeastApiClient("http://gateway")
    observed = {}

    class FakeResponse:
        status_code = 200
        text = ""

        def json(self):
            return {"content": [{"type": "text", "text": "native Anthropic response"}]}

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, url, **kwargs):
            observed["url"] = url
            observed["headers"] = kwargs["headers"]
            observed["payload"] = kwargs["json"]
            return FakeResponse()

    monkeypatch.setattr("app.cli.api.httpx.AsyncClient", FakeClient)

    events = [
        event async for event in client.stream_chat_completion(
            "anthropic",
            [{"role": "system", "content": "Return only JSON."}, {"role": "user", "content": "Fix it."}],
            model="claude-3-5-sonnet",
        )
    ]

    assert observed["url"].endswith("/proxy/anthropic/v1/messages")
    assert observed["headers"]["anthropic-version"] == "2023-06-01"
    assert observed["payload"]["system"] == "Return only JSON."
    assert observed["payload"]["messages"] == [{"role": "user", "content": "Fix it."}]
    assert events[0] == {"type": "token", "text": "native Anthropic response"}
    assert events[-1]["finish_reason"] == "native_anthropic_response"

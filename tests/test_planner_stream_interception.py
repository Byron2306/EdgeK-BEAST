from __future__ import annotations

import asyncio
import json

from app.kernel.agents.nim_planner_provider import NIMPlannerProvider
from app.kernel.agents.ollama_planner_provider import OllamaPlannerProvider
from app.kernel.agents.run_events import legacy_event_projection
from app.kernel.compute.streaming_interceptor import StreamingInterceptionEngine


ACTION = {"decision_type": "complete", "tool_id": "", "arguments": {}}


def test_streaming_engine_recognizes_typed_planner_decision():
    engine = StreamingInterceptionEngine(schema_contract=NIMPlannerProvider.ACTION_SCHEMA)
    state = engine.create_initial_state(100)

    result = engine.process_chunk(state, json.dumps(ACTION), token_count=4)

    assert result.should_stop is True
    assert result.stop_reason == "governed_object_complete"
    assert result.schema_valid is True


def test_stream_interception_projects_to_ide_event():
    name, payload = legacy_event_projection("agent.stream.interception", {
        "stop_reason": "governed_object_complete",
        "upstream_cancel_requested": True,
    })

    assert name == "agent_run_interception"
    assert payload["status"] == "cancelled_upstream"


def test_effect_tool_projection_is_visible_to_ide():
    name, payload = legacy_event_projection("agent.tool.completed", {
        "runtime": "effect_ts",
        "observation": {"tool_id": "workspace.read_range"},
    })

    assert name == "agent_run_tool"
    assert payload["runtime"] == "effect_ts"
    assert "Effect TS" in payload["text"]


def test_nim_stream_closes_upstream_after_complete_typed_decision(monkeypatch):
    class Response:
        closed = False

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            self.closed = True

        def close(self):
            self.closed = True

        def __iter__(self):
            chunks = [json.dumps(ACTION), " trailing output that must not be consumed"]
            for text in chunks:
                yield f"data: {json.dumps({'choices': [{'delta': {'content': text}}]})}\n".encode()

    response = Response()
    monkeypatch.setattr(
        "app.kernel.agents.nim_planner_provider._egress.urlopen",
        lambda *_args, **_kwargs: response,
    )
    provider = NIMPlannerProvider(api_key="test", max_retries=0)

    body = provider._request_stream({"model": "test", "stream": True})

    assert body["content"] == json.dumps(ACTION)
    assert response.closed is True
    assert body["stream_interception"]["upstream_cancel_requested"] is True
    assert body["stream_interception"]["stop_reason"] == "governed_object_complete"


def test_ollama_stream_closes_upstream_after_complete_typed_decision(monkeypatch):
    class Response:
        closed = False

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            self.closed = True

        def raise_for_status(self):
            return None

        async def aclose(self):
            self.closed = True

        async def aiter_lines(self):
            yield json.dumps({"response": json.dumps(ACTION), "done": False})
            yield json.dumps({"response": " trailing output", "done": True})

    response = Response()

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        def stream(self, *_args, **_kwargs):
            return response

    monkeypatch.setattr(
        "app.kernel.agents.ollama_planner_provider.httpx.AsyncClient",
        lambda **_kwargs: Client(),
    )
    provider = OllamaPlannerProvider(model="test", max_retries=0)

    body = asyncio.run(provider._request_stream_json_async(
        "/api/generate",
        {"model": "test", "stream": True},
        10,
    ))

    assert body["response"] == json.dumps(ACTION)
    assert response.closed is True
    assert body["stream_interception"]["upstream_cancel_requested"] is True
    assert body["stream_interception"]["stop_reason"] == "governed_object_complete"

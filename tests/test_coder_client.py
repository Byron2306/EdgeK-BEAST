from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from app.cli.coder_client import (
    CoderRuntimeClient,
    RuntimeClientError,
    RuntimeEvent,
    iter_sse_events,
)


async def _chunks(*values: bytes):
    for value in values:
        yield value


@pytest.mark.asyncio
async def test_iter_sse_events_reassembles_fragmented_canonical_event():
    source = _chunks(
        b"id: 7\nevent: agent.model.delta\nda",
        b'ta: {"sequence":7,"payload":{"text":"hel',
        b'lo"}}\n\n',
    )

    events = [event async for event in iter_sse_events(source)]

    assert events == [
        RuntimeEvent(
            event="agent.model.delta",
            data={"sequence": 7, "payload": {"text": "hello"}},
            event_id="7",
        )
    ]


@pytest.mark.asyncio
async def test_iter_sse_events_rejects_oversized_unterminated_frame():
    with pytest.raises(RuntimeClientError, match="SSE frame exceeds 32 bytes"):
        _ = [
            event
            async for event in iter_sse_events(
                _chunks(b"data: " + b"x" * 40), max_event_bytes=32
            )
        ]


def _transport() -> httpx.MockTransport:
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/edgek/providers/registry":
            return httpx.Response(
                200,
                json={
                    "beast_object_type": "provider_registry",
                    "providers": [
                        {
                            "provider_id": "ollama",
                            "default_model": "granite-code:8b",
                            "enabled": True,
                        }
                    ],
                },
            )
        if request.url.path == "/edgek/skills":
            return httpx.Response(200, json={"skills": [{"id": "skill-1"}]})
        if request.url.path == "/edgek/skills/state":
            return httpx.Response(200, json={"skills": {"total": 1}})
        if request.url.path == "/edgek/mcp/state":
            return httpx.Response(200, json={"servers": [{"name": "remotehub", "server_class": "github"}]})
        if request.url.path == "/edgek/ide/agent-sessions/create":
            payload = json.loads(request.content)
            assert payload == {
                "objective": "BEAST Coder persistent session",
                "mode": "agent",
                "provider": "ollama",
                "model": "granite-code:8b",
                "workspace_root": "/work/demo",
                "execution_target": "local",
                "tools": [],
                "files": [],
            }
            return httpx.Response(
                200,
                json={"ok": True, "session": {"session_id": "agent-a1"}},
            )
        if request.url.path == "/edgek/ide/agent-sessions/capabilities/grant":
            payload = json.loads(request.content)
            assert payload == {
                "session_id": "agent-a1",
                "workspace_root": "/work/demo",
                "capabilities": ["use_verified_skill"],
                "skill_id": "skill-review",
                "request_id": "coder-skill-skill-review",
            }
            return httpx.Response(
                200,
                json={
                    "ok": True,
                    "session": {"session_id": "agent-a1"},
                    "receipt": {"receipt_id": "grant-1"},
                },
            )
        if request.url.path == "/edgek/mcp/execute":
            payload = json.loads(request.content)
            assert payload == {
                "server_name": "remotehub",
                "tool_name": "github_search",
                "query": "BEAST",
                "workspace_root": "/work/demo",
            }
            return httpx.Response(
                200,
                json={
                    "executed": True,
                    "request_id": "mcp-1",
                    "content": "hello",
                    "edgek_crystal_tool_boundary": {
                        "beast_object_type": "crystal_tool_boundary_receipt"
                    },
                },
            )
        if request.url.path == "/edgek/agent-runs" and request.method == "POST":
            payload = json.loads(request.content)
            assert payload["session_id"] == "agent-a1"
            assert payload["mode"] == "analysis"
            assert payload["request"]["launch_strategy"] == "typed_planner"
            assert payload["request"]["prompt"] == "create hello.py"
            assert payload["request"]["workspace_root"] == "/work/demo"
            assert payload["launch"] is True
            return httpx.Response(
                200,
                json={"ok": True, "run": {"run_id": "run-9", "state": "planning"}},
            )
        if request.url.path == "/edgek/agent-runs/run-9/events":
            assert request.url.params["root_path"] == "/work/demo"
            return httpx.Response(
                200,
                headers={"content-type": "text/event-stream"},
                content=(
                    'id: 1\nevent: agent.model.delta\ndata: '
                    '{"sequence":1,"event_type":"agent.model.delta",'
                    '"payload":{"text":"hi"}}\n\n'
                    'id: 2\nevent: agent.tool.completed\ndata: '
                    '{"sequence":2,"event_type":"agent.tool.completed",'
                    '"payload":{"observation":{"ok":true,"receipt_id":"r-1"}}}\n\n'
                ).encode(),
            )
        return httpx.Response(404, json={"detail": "not found"})

    return httpx.MockTransport(handler)


@pytest.mark.asyncio
async def test_client_discovers_runtime_capabilities_and_runs_agent(tmp_path: Path):
    client = CoderRuntimeClient(
        "http://beast.test", Path("/work/demo"), transport=_transport()
    )

    providers = await client.discover_providers()
    skills = await client.discover_skills()
    mcp = await client.discover_mcp()
    session = await client.ensure_session("ollama", "granite-code:8b")
    skill_grant = await client.grant_verified_skill(session["session_id"], "skill-review")
    mcp_result = await client.execute_mcp(
        {"server_name": "remotehub", "tool_name": "github_search", "query": "BEAST"}
    )
    run = await client.start_run(
        session["session_id"], "create hello.py", "ollama", "granite-code:8b"
    )
    events = [event async for event in client.follow_run(run["run_id"])]
    await client.aclose()

    assert providers["providers"][0]["provider_id"] == "ollama"
    assert skills == {"skills": [{"id": "skill-1"}], "state": {"skills": {"total": 1}}}
    assert mcp["servers"][0]["name"] == "remotehub"
    assert skill_grant["receipt"]["receipt_id"] == "grant-1"
    assert mcp_result["executed"] is True
    assert mcp_result["request_id"] == "mcp-1"
    assert [event.event for event in events] == [
        "agent.model.delta",
        "agent.tool.completed",
    ]
    assert events[1].data["payload"]["observation"]["receipt_id"] == "r-1"


@pytest.mark.asyncio
@pytest.mark.parametrize("tool_name", ["read_file", "write_file", "shell", "token_compressor"])
async def test_client_blocks_workspace_bound_mcp_until_gateway_honors_selection(tool_name: str):
    client = CoderRuntimeClient(
        "http://beast.test", Path("/work/demo"), transport=_transport()
    )

    with pytest.raises(RuntimeClientError, match="does not honor the selected workspace"):
        await client.execute_mcp({"server_name": "remotehub", "tool_name": tool_name, "target": "README.md"})

    await client.aclose()


@pytest.mark.asyncio
async def test_client_reports_gateway_http_error_without_synthetic_success():
    transport = httpx.MockTransport(
        lambda request: httpx.Response(503, json={"detail": "gateway unavailable"})
    )
    client = CoderRuntimeClient(
        "http://beast.test", Path("/work/demo"), transport=transport
    )

    with pytest.raises(RuntimeClientError, match="503.*gateway unavailable"):
        await client.discover_mcp()

    await client.aclose()


@pytest.mark.asyncio
async def test_timed_out_turn_reads_its_own_receipt_without_posting_again(tmp_path, monkeypatch):
    import json

    monkeypatch.setenv("BEAST_CODER_AGENTRUN_MAX_SECONDS", "30")
    sent = []
    polls = []

    async def responder(request):
        if request.method == "POST":
            sent.append(json.loads(request.content)["turn_request_id"])
            raise httpx.ReadTimeout("lost reply", request=request)
        polls.append(request.url.path)
        # A completed receipt for a *different* request must never advance the UI.
        receipt = {"id": "0" * 32 if len(polls) == 1 else sent[0], "state": "completed"}
        return httpx.Response(200, json={"run": {"run_id": "r", "state": "completed",
            "checkpoint": {"coder_turn_reply": receipt}}})

    client = CoderRuntimeClient("http://localhost", tmp_path, transport=httpx.MockTransport(responder))
    try:
        assert (await client.start_turn("r"))["state"] == "completed"
    finally:
        await client.aclose()
    assert len(sent) == 1
    assert polls == ["/edgek/agent-runs/r"] * 2

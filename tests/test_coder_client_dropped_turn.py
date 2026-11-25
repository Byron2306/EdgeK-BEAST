"""A dropped turn POST must surface as a clear, recoverable message, not a crash."""
import asyncio

import httpx
import pytest

from app.cli.coder_client import CoderRuntimeClient, RuntimeTurnUnconfirmed


def _client(handler):
    return CoderRuntimeClient("http://gw.test", ".", transport=httpx.MockTransport(handler))


def test_read_error_on_turn_post_reports_unconfirmed_with_state():
    def handler(request):
        if request.method == "POST":
            raise httpx.ReadError("connection reset", request=request)
        return httpx.Response(200, json={"run": {"run_id": "agent-x", "state": "observing", "checkpoint": {}}})

    client = _client(handler)

    async def go():
        with pytest.raises(RuntimeTurnUnconfirmed) as info:
            await client.start_turn("agent-x")
        await client.aclose()
        return str(info.value)

    message = asyncio.run(go())
    assert "dropped the connection" in message and "observing" in message and "/next" in message


def test_read_error_after_turn_ran_returns_the_recorded_run():
    seen = {}

    def handler(request):
        if request.method == "POST":
            import json
            seen["id"] = json.loads(request.content)["turn_request_id"]
            raise httpx.RemoteProtocolError("server disconnected", request=request)
        return httpx.Response(200, json={"run": {"run_id": "agent-x", "state": "observing",
                                                 "checkpoint": {"coder_turn_reply": {"id": seen["id"],
                                                                                     "state": "observing"}}}})

    client = _client(handler)

    async def go():
        run = await client.start_turn("agent-x")
        await client.aclose()
        return run

    assert asyncio.run(go())["state"] == "observing"


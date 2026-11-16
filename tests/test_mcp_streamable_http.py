"""The HTTP MCP facade must also speak MCP Streamable HTTP (JSON-RPC at POST /mcp)."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.mcp.server import mcp_router

ACCEPT = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(mcp_router)
    return TestClient(app)


def test_streamable_http_initialize_list_and_call():
    c = _client()
    r = c.post("/mcp", headers=ACCEPT, json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t", "version": "0"}}})
    assert r.status_code == 200
    sid = r.headers.get("mcp-session-id")
    assert sid and r.json()["result"]["protocolVersion"] == "2025-06-18"
    h = {**ACCEPT, "mcp-session-id": sid}
    assert c.post("/mcp", headers=h, json={"jsonrpc": "2.0", "method": "notifications/initialized"}).status_code == 202
    tools = c.post("/mcp", headers=h, json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"}).json()
    assert len(tools["result"]["tools"]) > 10
    call = c.post("/mcp", headers=h, json={"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "beast_mcp_status", "arguments": {}}}).json()
    assert "result" in call and call["result"]["content"][0]["type"] == "text"


def test_streamable_http_unknown_method():
    c = _client()
    r = c.post("/mcp", headers=ACCEPT, json={"jsonrpc": "2.0", "id": 5, "method": "nope"})
    assert r.json()["error"]["code"] == -32601


def test_legacy_rest_facade_still_works():
    c = _client()
    assert c.get("/mcp/health").json()["status"] == "healthy"
    assert len(c.get("/mcp/tools/list").json()["tools"]) > 0

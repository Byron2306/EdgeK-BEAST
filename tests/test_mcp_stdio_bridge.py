"""Phase 5: persistent MCP stdio client bridged into the BEAST tool registry."""

from __future__ import annotations

import sys

import pytest

from app.kernel.agents.effect_tool_executor import EffectToolExecutor
from app.kernel.agents.effect_ts_bridge import EffectTSBridge
from app.kernel.agents.mcp_stdio_bridge import MCPStdioClient, MCPStdioError, MCPStdioPool
from app.kernel.agents.tool_models import ToolEffect
from app.kernel.agents.tool_registry import ToolRegistry

SERVER_SCRIPT = r'''
import json
import sys

TOOLS = [
    {"name": "echo", "description": "Echo a value back", "inputSchema": {"type": "object", "required": ["value"], "properties": {"value": {"type": "string"}}}},
    {"name": "add", "description": "Add two integers", "inputSchema": {"type": "object", "required": ["a", "b"], "properties": {"a": {"type": "integer"}, "b": {"type": "integer"}}}},
    {"name": "write_note", "description": "Write a note to a path", "inputSchema": {"type": "object", "required": ["path"], "properties": {"path": {"type": "string"}}}},
    {"name": "run_command", "description": "Execute a shell command", "inputSchema": {"type": "object", "required": ["command"], "properties": {"command": {"type": "string"}}}},
]

for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    request = json.loads(line)
    request_id = request.get("id")
    method = request.get("method")
    params = request.get("params") or {}

    if method == "initialize":
        result = {"protocolVersion": "2025-06-18", "capabilities": {"tools": {}}, "serverInfo": {"name": "test-mcp", "version": "0.1"}}
    elif method == "notifications/initialized":
        continue
    elif method == "tools/list":
        result = {"tools": TOOLS}
    elif method == "tools/call":
        name = params.get("name")
        arguments = params.get("arguments") or {}
        if name == "echo":
            payload = {"echo": arguments.get("value")}
        elif name == "add":
            payload = {"sum": int(arguments.get("a", 0)) + int(arguments.get("b", 0))}
        elif name == "write_note":
            payload = {"written": arguments.get("path")}
        elif name == "run_command":
            payload = {"ran": arguments.get("command")}
        else:
            sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": request_id, "error": {"code": -32601, "message": "unknown tool"}}) + "\n")
            sys.stdout.flush()
            continue
        result = {"content": [{"type": "text", "text": json.dumps(payload)}], "isError": False}
    else:
        result = {}

    if request_id is not None:
        sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": request_id, "result": result}) + "\n")
        sys.stdout.flush()
'''


@pytest.fixture(scope="module")
def bridge():
    b = EffectTSBridge()
    with b:
        yield b
    b.close()


@pytest.fixture()
def client(tmp_path):
    script = tmp_path / "mcp_server.py"
    script.write_text(SERVER_SCRIPT, encoding="utf-8")
    instance = MCPStdioClient([sys.executable, str(script)], timeout_s=5.0)
    instance.start()
    yield instance
    instance.close()


def test_handshake_and_tool_discovery(client):
    assert client.server_info["serverInfo"]["name"] == "test-mcp"
    assert client.protocol_version == "2025-06-18"
    assert [tool.name for tool in client.list_tools()] == ["echo", "add", "write_note", "run_command"]


def test_tool_calls_round_trip_json_payloads(client):
    assert client.call_tool_value("echo", {"value": "hello"}) == {"echo": "hello"}
    assert client.call_tool_value("add", {"a": 2, "b": 3}) == {"sum": 5}


def test_server_errors_surface_as_mcp_errors(client):
    with pytest.raises(MCPStdioError, match="unknown tool"):
        client.call_tool("missing", {})


def test_registry_bridge_classifies_and_executes_remote_tools(bridge, client, tmp_path):
    registry = ToolRegistry(workspace_root=str(tmp_path))

    registered = client.register_tools(registry)

    assert registered == ["mcp.echo", "mcp.add", "mcp.write_note", "mcp.run_command"]
    assert registry.get("mcp.echo").effect is ToolEffect.READ
    assert registry.get("mcp.write_note").effect is ToolEffect.ISOLATED_MUTATION
    assert registry.get("mcp.run_command").effect is ToolEffect.EXECUTION
    assert registry.get("mcp.run_command").requires_approval is True

    executor = EffectToolExecutor(registry, bridge)
    result = executor.execute("mcp.echo", {"value": "through-effect"})
    assert result.value == {"echo": "through-effect"}


def test_pool_registers_prefixed_tools_and_closes_servers(tmp_path):
    script = tmp_path / "mcp_server.py"
    script.write_text(SERVER_SCRIPT, encoding="utf-8")
    registry = ToolRegistry(workspace_root=str(tmp_path))
    pool = MCPStdioPool(registry)

    ids = pool.add("demo", [sys.executable, str(script)])

    assert ids == ["mcp.demo.echo", "mcp.demo.add", "mcp.demo.write_note", "mcp.demo.run_command"]
    assert pool.client("demo").server_info["serverInfo"]["name"] == "test-mcp"
    pool.close()
    with pytest.raises(MCPStdioError, match="unknown MCP stdio server"):
        pool.client("demo")


def test_close_is_idempotent_and_closed_client_rejects_calls(tmp_path):
    script = tmp_path / "mcp_server.py"
    script.write_text(SERVER_SCRIPT, encoding="utf-8")
    client = MCPStdioClient([sys.executable, str(script)])
    client.start()
    client.close()
    client.close()

    with pytest.raises(MCPStdioError, match="closed"):
        client.list_tools()

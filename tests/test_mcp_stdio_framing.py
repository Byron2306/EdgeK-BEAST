"""MCP stdio transport must speak the spec's newline-delimited JSON-RPC.

The official MCP SDKs (Python, TypeScript, VS Code, Claude Code) frame stdio
messages as one JSON object per line.  The legacy Content-Length framing is
kept for backward compatibility, and stdout must never be polluted by stray
prints from lazily imported kernel modules.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _spawn() -> subprocess.Popen:
    env = {**os.environ, "PYTHONPATH": str(ROOT)}
    return subprocess.Popen(
        [sys.executable, "-c", "from app.mcp.stdio_server import serve_stdio; serve_stdio()"],
        cwd=str(ROOT), stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=env,
    )


def _ndjson_exchange(messages):
    proc = _spawn()
    payload = "".join(json.dumps(m) + "\n" for m in messages).encode()
    out, _ = proc.communicate(payload, timeout=120)
    return [json.loads(line) for line in out.decode().splitlines() if line.strip()], out


def test_ndjson_initialize_and_tools_list():
    responses, raw = _ndjson_exchange([
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t", "version": "0"}}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
    ])
    assert b"Content-Length" not in raw
    assert responses[0]["id"] == 1 and responses[0]["result"]["protocolVersion"] == "2025-06-18"
    assert responses[1]["id"] == 2 and len(responses[1]["result"]["tools"]) > 10


def test_unknown_protocol_version_falls_back_to_supported():
    responses, _ = _ndjson_exchange([
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "1999-01-01", "capabilities": {}, "clientInfo": {"name": "t", "version": "0"}}},
    ])
    assert responses[0]["result"]["protocolVersion"] in {"2025-06-18", "2025-03-26", "2024-11-05", "2025-11-25"}


def test_tools_call_keeps_stdout_pure_jsonrpc():
    responses, raw = _ndjson_exchange([
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t", "version": "0"}}},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "beast_mcp_status", "arguments": {}}},
    ])
    for line in raw.decode().splitlines():
        if line.strip():
            json.loads(line)  # every stdout line must be JSON-RPC
    assert responses[-1]["id"] == 2 and "result" in responses[-1]


def test_unknown_method_returns_method_not_found():
    responses, _ = _ndjson_exchange([{"jsonrpc": "2.0", "id": 9, "method": "no/such"}])
    assert responses[0]["error"]["code"] == -32601


def test_legacy_content_length_framing_still_supported():
    proc = _spawn()
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "ping"}).encode()
    out, _ = proc.communicate(b"Content-Length: %d\r\n\r\n" % len(body) + body, timeout=60)
    assert out.startswith(b"Content-Length:")
    assert json.loads(out.split(b"\r\n\r\n", 1)[1])["id"] == 1

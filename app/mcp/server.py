"""HTTP-facing MCP façade for BEAST tools/resources/prompts."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.mcp.runtime import runtime
from app.mcp.builtin_custody import dispatch_with_custody

mcp_router = APIRouter()


class MCPToolCall(BaseModel):
    name: str
    arguments: Dict[str, Any] = {}


class MCPPromptRequest(BaseModel):
    name: str
    arguments: Optional[Dict[str, Any]] = None


@mcp_router.get("/mcp/health")
async def mcp_health() -> Dict[str, Any]:
    return {
        "status": "healthy",
        "service": "edgek-beast-mcp-http",
        "transport": "http-facade",
        "version": "1.0.0",
    }


@mcp_router.get("/mcp/tools/list")
async def list_mcp_tools() -> Dict[str, Any]:
    return {"tools": runtime.tool_definitions()}


@mcp_router.post("/mcp/tools/call")
async def call_mcp_tool(call: MCPToolCall) -> Dict[str, Any]:
    try:
        result = dispatch_with_custody(runtime, call.name, call.arguments)
        return {"content": [{"type": "text", "text": __import__('json').dumps(result, indent=2)}], "isError": bool(result.get("isError") or result.get("ok") is False)}
    except Exception as exc:  # pragma: no cover - surfaced to API client
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@mcp_router.get("/mcp/resources/list")
async def list_mcp_resources() -> Dict[str, Any]:
    return {"resources": runtime.list_resources()}


@mcp_router.get("/mcp/resources/read/{uri_path:path}")
async def read_mcp_resource(uri_path: str) -> Dict[str, Any]:
    try:
        uri = f"beast://{uri_path}"
        return runtime.read_resource(uri)
    except Exception as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@mcp_router.get("/mcp/prompts/list")
async def list_mcp_prompts() -> Dict[str, Any]:
    return {"prompts": runtime.list_prompts()}


@mcp_router.post("/mcp/prompts/get")
async def get_mcp_prompt(prompt: MCPPromptRequest) -> Dict[str, Any]:
    try:
        return runtime.get_prompt(prompt.name, prompt.arguments)
    except Exception as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# MCP Streamable HTTP transport (JSON response mode).
#
# The REST routes above are a BEAST-specific facade; real MCP clients (the
# official SDKs, Claude Code `--transport http`, VS Code `type: http`) speak
# JSON-RPC over POST to a single endpoint.  This reuses the stdio server's
# method handler so both transports expose identical tools/resources/prompts
# and the same fail-closed custody path for tools/call.
# ---------------------------------------------------------------------------
import uuid as _uuid

from fastapi import Request
from fastapi.responses import JSONResponse, Response

_MCP_HTTP_SESSIONS: Dict[str, float] = {}


def _jsonrpc_error(msg_id: Any, code: int, message: str) -> Dict[str, Any]:
    return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}}


def _dispatch_jsonrpc(message: Any) -> Optional[Dict[str, Any]]:
    from app.mcp import stdio_server

    if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
        return _jsonrpc_error(None, -32600, "Invalid request")
    method = message.get("method")
    msg_id = message.get("id")
    if not method:
        return None  # client response to a server request; nothing to do
    if method.startswith("notifications/"):
        return None
    try:
        result = stdio_server._handle(method, message.get("params"))
    except stdio_server._MethodNotFound as exc:
        return _jsonrpc_error(msg_id, -32601, str(exc))
    except Exception as exc:  # pragma: no cover - surfaced to client
        return _jsonrpc_error(msg_id, -32000, str(exc))
    return {"jsonrpc": "2.0", "id": msg_id, "result": result} if msg_id is not None else None


@mcp_router.post("/mcp")
async def mcp_streamable_http(request: Request) -> Response:
    import time as _time

    try:
        body = await request.json()
    except Exception:
        return JSONResponse(_jsonrpc_error(None, -32700, "Parse error"), status_code=400)
    batch = body if isinstance(body, list) else [body]
    responses = [r for r in (_dispatch_jsonrpc(m) for m in batch) if r is not None]
    headers: Dict[str, str] = {}
    if any(isinstance(m, dict) and m.get("method") == "initialize" for m in batch):
        sid = _uuid.uuid4().hex
        _MCP_HTTP_SESSIONS[sid] = _time.time()
        headers["Mcp-Session-Id"] = sid
    if not responses:
        return Response(status_code=202, headers=headers)
    payload: Any = responses if isinstance(body, list) else responses[0]
    return JSONResponse(payload, headers=headers)


@mcp_router.get("/mcp")
async def mcp_streamable_http_get() -> Response:
    # No server-initiated SSE stream is offered; spec says reply 405.
    return Response(status_code=405, headers={"Allow": "POST, DELETE"})


@mcp_router.delete("/mcp")
async def mcp_streamable_http_delete(request: Request) -> Response:
    _MCP_HTTP_SESSIONS.pop(request.headers.get("mcp-session-id", ""), None)
    return Response(status_code=204)

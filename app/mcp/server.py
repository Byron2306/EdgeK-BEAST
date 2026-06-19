"""HTTP-facing MCP façade for BEAST tools/resources/prompts."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.mcp.runtime import runtime

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
        result = runtime.call_tool(call.name, call.arguments)
        return {"content": [{"type": "text", "text": __import__('json').dumps(result, indent=2)}], "isError": False}
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

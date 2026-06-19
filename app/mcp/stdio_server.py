"""Minimal stdio MCP server for VS Code local integration.

Important: this module intentionally avoids importing the heavy BEAST runtime
before the MCP initialize handshake. VS Code waits for initialize quickly; the
runtime is lazy-loaded only when tools/resources/prompts are requested.
"""

from __future__ import annotations

import json
import logging
import sys
from functools import lru_cache
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

PROTOCOL_VERSION = "2025-06-18"
SERVER_INFO = {"name": "edgek-beast", "title": "EdgeK BEAST", "version": "1.0.1"}
CAPABILITIES = {
    "tools": {"listChanged": True},
    "resources": {"listChanged": True},
    "prompts": {"listChanged": True},
    "logging": {},
}

# Lightweight definitions so tools/list does not have to warm the whole kernel.
TOOL_DEFINITIONS = [
    {
        "name": "beast_prepare_task",
        "description": "Prepare a canonical BEAST task envelope from a user request.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "user_request": {"type": "string"},
                "provider": {"type": "string"},
                "task_class": {"type": "string"},
                "project": {"type": "string"},
                "dry_run": {"type": "boolean", "default": True},
            },
            "required": ["user_request"],
        },
    },
    {
        "name": "beast_run_quality_cascade",
        "description": "Run the local Quality Cascade before cloud escalation.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "envelope": {"type": "object"},
                "provider": {"type": "string"},
                "workspace_root": {"type": "string"},
            },
            "required": ["envelope", "provider"],
        },
    },
    {
        "name": "beast_run_maintenance_cascade",
        "description": "Run repo hygiene checks: compile, pytest collection, dependency sanity, docs links, and extension syntax.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "workspace_root": {"type": "string"},
                "run_tests": {"type": "boolean", "default": False},
                "pytest_args": {"type": "array", "items": {"type": "string"}},
                "include_extension_checks": {"type": "boolean", "default": True},
                "include_markdown": {"type": "boolean", "default": True},
                "run_packaging": {"type": "boolean", "default": False},
                "python_versions": {"type": "array", "items": {"type": "string"}},
                "timeout_seconds": {"type": "integer", "default": 60},
            },
        },
    },
    {
        "name": "beast_prepare_handoff",
        "description": "Build a bounded context packet for a cloud-model handoff.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "envelope": {"type": "object"},
                "provider": {"type": "string"},
                "max_tokens": {"type": "integer", "default": 8000},
            },
            "required": ["envelope", "provider"],
        },
    },
    {
        "name": "beast_sourceplan_prepare",
        "description": "Prepare a governed SourcePlan with output governance, bounded context, and selected files.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "objective": {"type": "string"},
                "files": {"type": "array", "items": {"type": "string"}},
                "provider": {"type": "string", "default": "litellm"},
                "provider_text": {"type": "string"},
            },
            "required": ["objective"],
        },
    },
    {
        "name": "beast_sourceplan_preview_hunks",
        "description": "Render a unified diff preview for a BEAST SourcePlan without applying it.",
        "inputSchema": {
            "type": "object",
            "properties": {"plan": {"type": "object"}},
            "required": ["plan"],
        },
    },
    {
        "name": "beast_sourceplan_apply_selected",
        "description": "Apply selected SourcePlan hunks with approval, verification, rollback, and Chronicle crystallization.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "plan": {"type": "object"},
                "approved": {"type": "boolean", "default": False},
            },
            "required": ["plan", "approved"],
        },
    },
    {
        "name": "beast_sourceplan_rollback_latest",
        "description": "Rollback the latest BEAST SourcePlan apply using the local rollback snapshot.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "beast_provider_fitness",
        "description": "Summarize provider route fitness, Chronicle evidence, and recommended runtime role.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "provider": {"type": "string"},
                "limit": {"type": "integer", "default": 50},
            },
        },
    },
    {
        "name": "beast_check_policy",
        "description": "Check whether an action is allowed under current governance rules.",
        "inputSchema": {
            "type": "object",
            "properties": {"action": {"type": "string"}, "context": {"type": "object"}},
            "required": ["action"],
        },
    },
    {
        "name": "beast_build_route_card",
        "description": "Create a provider route card for diagnostics or handoffs.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "provider": {"type": "string"},
                "envelope": {"type": "object"},
                "persist": {"type": "boolean", "default": True},
            },
            "required": ["provider"],
        },
    },
    {
        "name": "beast_publish_chronicle",
        "description": "Persist a diagnostic or governance result to the Chronicle store.",
        "inputSchema": {
            "type": "object",
            "properties": {"diagnostic_result": {"type": "object"}},
            "required": ["diagnostic_result"],
        },
    },
    {
        "name": "beast_get_workspace_graph",
        "description": "Return a lightweight view of the workspace graph/dependencies.",
        "inputSchema": {"type": "object", "properties": {"depth": {"type": "integer", "default": 2}}},
    },
    {
        "name": "beast_build_context_packet",
        "description": "Build a bounded evidence packet from task, route, and quality artifacts.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "envelope": {"type": "object"},
                "route_card": {"type": "object"},
                "quality_report": {"type": "object"},
                "workspace_root": {"type": "string"},
                "include_content": {"type": "boolean", "default": True},
                "max_files": {"type": "integer"},
                "semantic_limit": {"type": "integer", "default": 5},
            },
            "required": ["envelope"],
        },
    },
    {
        "name": "beast_score_forge",
        "description": "Build a pre-edit Forge scorecard with risk, benefit, and gate signals.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "envelope": {"type": "object"},
                "context_packet": {"type": "object"},
                "quality_report": {"type": "object"},
                "route_card": {"type": "object"},
            },
            "required": ["envelope"],
        },
    },
    {
        "name": "beast_plan_workflow",
        "description": "Build a Conductor workflow card using swarm role advice.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "envelope": {"type": "object"},
                "context_packet": {"type": "object"},
                "forge_scorecard": {"type": "object"},
                "route_card": {"type": "object"},
                "quality_report": {"type": "object"},
                "run_swarm": {"type": "boolean", "default": True},
                "persist": {"type": "boolean", "default": False},
            },
            "required": ["envelope"],
        },
    },
    {
        "name": "beast_validate_canon",
        "description": "Validate a BEAST object or artifact bundle against the V2 canon registry.",
        "inputSchema": {
            "type": "object",
            "properties": {"object": {"type": "object"}, "artifacts": {"type": "object"}},
        },
    },
    {
        "name": "beast_check_promotion",
        "description": "Check whether repeated successful work is eligible for approval-gated promotion.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "artifacts": {"type": "object"},
                "task_class": {"type": "string"},
                "provider": {"type": "string"},
                "category": {"type": "string"},
                "route_id": {"type": "string"},
                "min_repetitions": {"type": "integer", "default": 2},
                "persist": {"type": "boolean", "default": True},
            },
        },
    },
    {
        "name": "beast_openclaw_plan",
        "description": "Create an Ollama-first Openclaw/Nemoclaw execution plan from workflow artifacts.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "objective": {"type": "string"},
                "workflow": {"type": "object"},
                "context_packet": {"type": "object"},
                "mode": {"type": "string", "default": "openclaw"},
                "workspace_root": {"type": "string"},
                "use_ollama": {"type": "boolean", "default": True},
            },
            "required": ["objective"],
        },
    },
    {
        "name": "beast_openclaw_execute",
        "description": "Execute allowed Openclaw/Nemoclaw actions through the governed MCP broker; dry-run by default.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "objective": {"type": "string"},
                "workflow": {"type": "object"},
                "context_packet": {"type": "object"},
                "mode": {"type": "string", "default": "openclaw"},
                "workspace_root": {"type": "string"},
                "dry_run": {"type": "boolean", "default": True},
                "approved": {"type": "boolean", "default": False},
                "use_ollama": {"type": "boolean", "default": True},
            },
            "required": ["objective"],
        },
    },
    {
        "name": "beast_mcp_status",
        "description": "Return MCP health, broker audit counters, tool catalog, and Ollama readiness.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "beast_mcp_tool_catalog",
        "description": "Return BEAST MCP tools with schema, risk, audit, and execution metadata.",
        "inputSchema": {"type": "object", "properties": {}},
    },
]

RESOURCE_DEFINITIONS = [
    {
        "uri": "beast://workspace/status",
        "name": "Workspace Status",
        "description": "Current workspace state and BEAST health metrics.",
        "mimeType": "application/json",
    },
    {
        "uri": "beast://chronicles/recent",
        "name": "Recent Chronicles",
        "description": "Recently published diagnostic chronicles.",
        "mimeType": "application/json",
    },
    {
        "uri": "beast://route-cards/active",
        "name": "Active Route Cards",
        "description": "Recently generated provider route cards.",
        "mimeType": "application/json",
    },
]

PROMPT_DEFINITIONS = [
    {
        "name": "diagnose_provider_failure",
        "description": "Guide for diagnosing a provider failure with BEAST.",
        "arguments": [
            {"name": "provider", "description": "Provider to diagnose", "required": True},
            {"name": "user_request", "description": "Original request", "required": False},
        ],
    },
    {
        "name": "prepare_handoff_packet",
        "description": "Guide for creating a bounded handoff packet.",
        "arguments": [
            {"name": "task_description", "description": "Task to continue", "required": True},
            {"name": "provider", "description": "Target provider", "required": True},
        ],
    },
]


@lru_cache(maxsize=1)
def _runtime():
    logger.info("Lazy-loading BEAST MCP runtime")
    from app.mcp.runtime import runtime

    return runtime


def _read_message() -> Optional[Dict[str, Any]]:
    headers: Dict[str, str] = {}
    while True:
        line = sys.stdin.buffer.readline()
        if not line:
            return None
        if line in (b"\r\n", b"\n"):
            break
        key, value = line.decode("utf-8").split(":", 1)
        headers[key.strip().lower()] = value.strip()
    length = int(headers.get("content-length", "0"))
    if length <= 0:
        return None
    payload = sys.stdin.buffer.read(length)
    if not payload:
        return None
    return json.loads(payload.decode("utf-8"))


def _write_message(message: Dict[str, Any]) -> None:
    encoded = json.dumps(message, separators=(",", ":")).encode("utf-8")
    sys.stdout.buffer.write(f"Content-Length: {len(encoded)}\r\n\r\n".encode("ascii"))
    sys.stdout.buffer.write(encoded)
    sys.stdout.buffer.flush()


def _success(msg_id: Any, result: Dict[str, Any]) -> Dict[str, Any]:
    return {"jsonrpc": "2.0", "id": msg_id, "result": result}


def _error(msg_id: Any, code: int, message: str) -> Dict[str, Any]:
    return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}}


def _handle(method: str, params: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    params = params or {}
    if method == "initialize":
        requested = params.get("protocolVersion") or PROTOCOL_VERSION
        # Prefer the client's version for compatibility, but keep a safe fallback.
        negotiated = requested if isinstance(requested, str) else PROTOCOL_VERSION
        return {
            "protocolVersion": negotiated,
            "capabilities": CAPABILITIES,
            "serverInfo": SERVER_INFO,
            "instructions": "Use BEAST tools to prepare, validate, route, and compress agentic software work before escalation.",
        }
    if method == "ping":
        return {}
    if method == "tools/list":
        return {"tools": TOOL_DEFINITIONS}
    if method == "tools/call":
        result = _runtime().call_tool(params.get("name", ""), params.get("arguments", {}))
        return {"content": [{"type": "text", "text": json.dumps(result, indent=2)}], "isError": False}
    if method == "resources/list":
        return {"resources": RESOURCE_DEFINITIONS}
    if method == "resources/read":
        return _runtime().read_resource(params.get("uri", ""))
    if method == "prompts/list":
        return {"prompts": PROMPT_DEFINITIONS}
    if method == "prompts/get":
        return _runtime().get_prompt(params.get("name", ""), params.get("arguments", {}))
    raise ValueError(f"Unsupported MCP method: {method}")


def serve_stdio() -> None:
    logging.basicConfig(level=logging.INFO)
    logger.info("Starting EdgeK BEAST MCP stdio server")
    while True:
        message = _read_message()
        if message is None:
            break
        msg_id = message.get("id")
        method = message.get("method")
        if not method:
            if msg_id is not None:
                _write_message(_error(msg_id, -32600, "Invalid request"))
            continue
        if method == "notifications/initialized":
            continue
        try:
            result = _handle(method, message.get("params"))
            if msg_id is not None:
                _write_message(_success(msg_id, result))
        except Exception as exc:
            logger.exception("MCP stdio request failed")
            if msg_id is not None:
                _write_message(_error(msg_id, -32000, str(exc)))


__all__ = ["serve_stdio"]

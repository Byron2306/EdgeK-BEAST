"""Persistent MCP stdio client and ToolRegistry bridge (Phase 5).

BEAST already serves MCP (`app/mcp/stdio_server.py`, `app/mcp/server.py`).
This module is the other direction: it spawns a command-line MCP server once,
performs the JSON-RPC handshake, and exposes that server's tools as governed
BEAST tools so the agent runtime and CLI can call them.

Wire format is newline-delimited JSON-RPC 2.0, matching the stdio transport
used by the existing BEAST MCP server.
"""

from __future__ import annotations

import itertools
import json
import os
import queue
import subprocess
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from app.kernel.agents.tool_models import ToolEffect, ToolRisk, ToolSpec
from app.kernel.agents.tool_registry import ToolRegistry

PROTOCOL_VERSION = "2025-06-18"
CLIENT_INFO = {"name": "beast-stdio-bridge", "version": "1.0.0"}


class MCPStdioError(RuntimeError):
    pass


@dataclass
class MCPRemoteTool:
    name: str
    description: str = ""
    input_schema: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return {"name": self.name, "description": self.description, "inputSchema": self.input_schema}


class MCPStdioClient:
    """One long-lived MCP server subprocess speaking JSON-RPC over stdio."""

    def __init__(
        self,
        command: Sequence[str],
        *,
        cwd: Optional[str] = None,
        env: Optional[Dict[str, str]] = None,
        timeout_s: float = 5.0,
    ) -> None:
        if not command:
            raise MCPStdioError("MCP stdio command must not be empty")
        self.command = [str(part) for part in command]
        self.cwd = cwd
        self.env = dict(env or {})
        self.timeout_s = float(timeout_s)
        self.server_info: Dict[str, Any] = {}
        self.protocol_version = ""
        self._process: Optional[subprocess.Popen[str]] = None
        self._messages: "queue.Queue[Optional[Dict[str, Any]]]" = queue.Queue()
        self._stderr: List[str] = []
        self._ids = itertools.count(1)
        self._lock = threading.Lock()
        self._closed = False

    # -- lifecycle ---------------------------------------------------------

    def start(self) -> Dict[str, Any]:
        if self._closed:
            raise MCPStdioError("MCP stdio client is closed")
        if self._process is not None:
            return self.server_info
        self._process = subprocess.Popen(
            self.command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            cwd=self.cwd,
            env={**os.environ, **self.env},
        )
        threading.Thread(target=self._read_stdout, name="mcp-stdio-out", daemon=True).start()
        threading.Thread(target=self._read_stderr, name="mcp-stdio-err", daemon=True).start()
        result = self._request(
            "initialize",
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "clientInfo": CLIENT_INFO,
            },
        )
        self.server_info = dict(result or {})
        self.protocol_version = str(self.server_info.get("protocolVersion") or "")
        self._notify("notifications/initialized")
        return self.server_info

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        process, self._process = self._process, None
        if process is None:
            return
        try:
            if process.stdin:
                process.stdin.close()
        except OSError:
            pass
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()
        self._messages.put(None)

    def __enter__(self) -> "MCPStdioClient":
        self.start()
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    # -- MCP operations ----------------------------------------------------

    def list_tools(self) -> List[MCPRemoteTool]:
        result = self._request("tools/list", {})
        tools = result.get("tools") if isinstance(result, dict) else []
        return [
            MCPRemoteTool(
                name=str(item.get("name") or ""),
                description=str(item.get("description") or ""),
                input_schema=item.get("inputSchema") if isinstance(item.get("inputSchema"), dict) else {},
            )
            for item in (tools or [])
            if isinstance(item, dict) and str(item.get("name") or "").strip()
        ]

    def call_tool(self, name: str, arguments: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        result = self._request("tools/call", {"name": str(name), "arguments": dict(arguments or {})})
        if not isinstance(result, dict):
            return {"content": result, "isError": False}
        return {
            "content": result.get("content", []),
            "isError": bool(result.get("isError", False)),
        }

    def call_tool_value(self, name: str, arguments: Optional[Dict[str, Any]] = None) -> Any:
        """Call a tool and decode a JSON text payload when the server sent one."""
        result = self.call_tool(name, arguments)
        content = result.get("content")
        if result.get("isError"):
            raise MCPStdioError(_content_text(content) or f"MCP tool failed: {name}")
        if isinstance(content, list) and len(content) == 1 and isinstance(content[0], dict):
            text = content[0].get("text")
            if isinstance(text, str):
                try:
                    return json.loads(text)
                except json.JSONDecodeError:
                    return text
        return result

    # -- JSON-RPC ----------------------------------------------------------

    def _send(self, payload: Dict[str, Any]) -> None:
        if self._process is None:
            self.start()
        process = self._process
        if process is None or process.stdin is None:
            raise MCPStdioError("MCP stdio server is not running")
        try:
            process.stdin.write(json.dumps(payload) + "\n")
            process.stdin.flush()
        except (BrokenPipeError, ValueError) as exc:
            raise MCPStdioError(f"MCP stdio server closed its input: {exc}") from exc

    def _notify(self, method: str, params: Optional[Dict[str, Any]] = None) -> None:
        self._send({"jsonrpc": "2.0", "method": method, "params": params or {}})

    def _request(
        self,
        method: str,
        params: Optional[Dict[str, Any]] = None,
        *,
        timeout_s: Optional[float] = None,
    ) -> Any:
        if method != "initialize" and self._process is None:
            self.start()
        request_id = next(self._ids)
        with self._lock:
            self._send({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params or {}})
        deadline = time.monotonic() + float(timeout_s or self.timeout_s)
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise MCPStdioError(f"MCP request timed out: {method}")
            try:
                message = self._messages.get(timeout=remaining)
            except queue.Empty:
                raise MCPStdioError(f"MCP request timed out: {method}") from None
            if message is None:
                raise MCPStdioError(f"MCP stdio server exited during {method}: {self.stderr_tail}")
            if message.get("id") != request_id:
                continue  # server notification or unrelated reply
            if "error" in message:
                error = message.get("error") or {}
                raise MCPStdioError(str(error.get("message") or f"MCP error in {method}"))
            return message.get("result")

    def _read_stdout(self) -> None:
        process = self._process
        if process is None or process.stdout is None:
            return
        for line in process.stdout:
            text = line.strip()
            if not text:
                continue
            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                self._messages.put(payload)
        self._messages.put(None)

    def _read_stderr(self) -> None:
        process = self._process
        if process is None or process.stderr is None:
            return
        for line in process.stderr:
            self._stderr.append(line.rstrip())
            if len(self._stderr) > 100:
                del self._stderr[:50]

    @property
    def stderr_tail(self) -> str:
        return "\n".join(self._stderr[-10:])

    # -- registry bridge ---------------------------------------------------

    def as_tool_specs(self, *, prefix: str = "mcp.", category: str = "mcp") -> List[ToolSpec]:
        specs: List[ToolSpec] = []
        for tool in self.list_tools():
            tool_id = f"{prefix}{tool.name}"
            effect, risk = _classify(tool.name, tool.description)
            specs.append(
                ToolSpec(
                    tool_id=tool_id,
                    version="1.0",
                    title=tool.name,
                    description=tool.description or f"MCP tool {tool.name}",
                    category=category,
                    risk=risk,
                    effect=effect,
                    input_schema=tool.input_schema,
                    requires_approval=effect is not ToolEffect.READ,
                    handler=self._handler(tool.name),
                )
            )
        return specs

    def register_tools(
        self,
        registry: ToolRegistry,
        *,
        prefix: str = "mcp.",
        category: str = "mcp",
    ) -> List[str]:
        registered: List[str] = []
        for spec in self.as_tool_specs(prefix=prefix, category=category):
            registry.register(spec, replace=True)
            registered.append(spec.tool_id)
        return registered

    def _handler(self, remote_name: str):
        def handler(arguments: Dict[str, Any], context: Any = None) -> Any:
            return self.call_tool_value(remote_name, arguments)

        return handler


class MCPStdioPool:
    """Owns several MCP stdio servers and registers all their tools once."""

    def __init__(self, registry: ToolRegistry) -> None:
        self.registry = registry
        self.clients: Dict[str, MCPStdioClient] = {}
        self.tool_ids: List[str] = []

    def add(
        self,
        name: str,
        command: Sequence[str],
        *,
        prefix: Optional[str] = None,
        category: str = "mcp",
        cwd: Optional[str] = None,
        env: Optional[Dict[str, str]] = None,
        timeout_s: float = 5.0,
    ) -> List[str]:
        client = MCPStdioClient(command, cwd=cwd, env=env, timeout_s=timeout_s)
        client.start()
        registered = client.register_tools(
            self.registry,
            prefix=prefix if prefix is not None else f"mcp.{name}.",
            category=category,
        )
        self.clients[name] = client
        self.tool_ids.extend(registered)
        return registered

    def client(self, name: str) -> MCPStdioClient:
        client = self.clients.get(str(name or ""))
        if client is None:
            raise MCPStdioError(f"unknown MCP stdio server: {name}")
        return client

    def close(self) -> None:
        for client in self.clients.values():
            client.close()
        self.clients.clear()

    def __enter__(self) -> "MCPStdioPool":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()


def _content_text(content: Any) -> str:
    if isinstance(content, list):
        return " ".join(
            str(item.get("text") or "") for item in content if isinstance(item, dict)
        ).strip()
    return str(content or "")


def _classify(name: str, description: str) -> tuple[ToolEffect, ToolRisk]:
    text = f"{name} {description}".lower()
    if any(word in text for word in ("execute", "shell", "command", "run", "terminal")):
        return ToolEffect.EXECUTION, ToolRisk.HIGH
    if any(word in text for word in ("write", "edit", "delete", "remove", "move", "rename", "create", "apply")):
        return ToolEffect.ISOLATED_MUTATION, ToolRisk.MEDIUM
    return ToolEffect.READ, ToolRisk.LOW

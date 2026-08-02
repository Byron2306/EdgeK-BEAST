"""Canonical typed tool registry for BEAST agent runs."""

from __future__ import annotations

import threading
from typing import Any

from app.kernel.agents.tool_models import ToolSpec


class ToolRegistryError(ValueError):
    pass


class AgentToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}
        self._lock = threading.RLock()

    def register(self, spec: ToolSpec, *, replace: bool = False) -> ToolSpec:
        tool_id = str(spec.tool_id or "").strip()
        if not tool_id or "." not in tool_id:
            raise ToolRegistryError("tool_id must be a namespaced identifier")
        if spec.handler is None:
            raise ToolRegistryError(f"tool {tool_id} has no handler")
        with self._lock:
            if tool_id in self._tools and not replace:
                raise ToolRegistryError(f"tool already registered: {tool_id}")
            self._tools[tool_id] = spec
        return spec

    def get(self, tool_id: str) -> ToolSpec:
        with self._lock:
            spec = self._tools.get(str(tool_id or "").strip())
        if spec is None:
            raise KeyError(f"unknown agent tool: {tool_id}")
        return spec

    def list(self, *, category: str = "", effect: str = "") -> list[dict[str, Any]]:
        with self._lock:
            tools = list(self._tools.values())
        if category:
            tools = [tool for tool in tools if tool.category == category]
        if effect:
            tools = [tool for tool in tools if tool.effect.value == effect]
        return [tool.public_dict() for tool in sorted(tools, key=lambda item: item.tool_id)]

    def validate_arguments(self, spec: ToolSpec, arguments: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(arguments, dict):
            raise ToolRegistryError("tool arguments must be an object")
        schema = spec.input_schema if isinstance(spec.input_schema, dict) else {}
        required = schema.get("required") if isinstance(schema.get("required"), list) else []
        missing = [str(name) for name in required if name not in arguments]
        if missing:
            raise ToolRegistryError(f"missing required tool arguments: {', '.join(missing)}")
        properties = schema.get("properties") if isinstance(schema.get("properties"), dict) else {}
        if schema.get("additionalProperties") is False:
            unknown = sorted(set(arguments) - set(properties))
            if unknown:
                raise ToolRegistryError(f"unknown tool arguments: {', '.join(unknown)}")
        return dict(arguments)

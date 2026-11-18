"""
MCP Tools Adapter for BEAST.
Bridges the existing MCP tool definitions (app/mcp/tool_definitions.json)
to the new plugin system with Zod schemas, Effect runtime, and unified registry.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Union, Callable, Awaitable

from app.kernel.agents.tool_registry import ToolSpec, ToolRisk, ToolEffect, ExecutionTarget
from app.kernel.agents.plugin_system import (
    Plugin,
    PluginMetadata,
    PluginConfig,
    PluginState,
    PluginStatus,
    PluginType,
    PluginAgent,
    PluginManager,
    Skill,
    Integration,
)
from app.kernel.agents.tool_registry import (
    ToolSpec,
    ToolRisk,
    ToolEffect,
    ExecutionTarget,
)
from app.kernel.agents.tool_registry import (
    ToolRegistry,
    ToolSpec,
    ToolExecutor,
    ToolContext,
    ToolExecutionError,
    ToolNotFoundError,
    ToolValidationError,
    ToolApprovalError,
    create_tool_registry,
)
from app.kernel.agents.effect_runtime import (
    EffectError,
    RetryPolicy,
    DEFAULT_RETRY_POLICY,
    with_retry,
    with_timeout,
    span,
    CancellationToken,
)
from app.kernel.agents.agent_effect import EffectAgent, AgentContext, AgentCommand, AgentCommandType


# =============================================================================
# MCP Tool Definitions Loader
# =============================================================================

MCP_TOOL_DEFINITIONS_PATH = Path("app/mcp/tool_definitions.json")


def load_mcp_tool_definitions() -> List[Dict[str, Any]]:
    """Load MCP tool definitions from JSON file."""
    if not MCP_TOOL_DEFINITIONS_PATH.exists():
        return []

    with open(MCP_TOOL_DEFINITIONS_PATH) as f:
        return json.load(f)


# =============================================================================
# MCP Tool Adapter
# =============================================================================

class MCPToolAdapter:
    """Adapts MCP tool definitions to the new plugin system."""

    def __init__(self):
        self.tools: List[Dict[str, Any]] = load_mcp_tool_definitions()
        self._tool_functions: Dict[str, Callable] = {}

    def get_tool_specs(self) -> List[ToolSpec]:
        """Convert MCP tool definitions to new ToolSpec format."""
        specs = []

        for tool_def in self.tools:
            tool_id = tool_def.get("name", "")
            if not tool_id:
                continue

            # Parse input schema
            input_schema = tool_def.get("inputSchema", {"type": "object", "properties": {}})

            # Determine risk from tool name/description
            risk = self._infer_risk(tool_id, tool_def.get("description", ""))

            # Determine effect
            effect = self._infer_effect(tool_id, tool_def.get("description", ""))

            # Determine targets (mostly local for MCP tools)
            targets = [ExecutionTarget.LOCAL]

            # Check if approval needed
            requires_approval = self._requires_approval(tool_id, tool_def.get("description", ""))

            spec = ToolSpec(
                tool_id=tool_id,
                title=tool_def.get("description", tool_id).split(".")[0],
                description=tool_def.get("description", ""),
                category="mcp",
                risk=risk,
                effect=effect,
                input_schema=input_schema,
                targets=[ExecutionTarget.LOCAL],
                requires_approval=requires_approval,
                timeout_seconds=120,
                metadata={
                    "mcp_tool": True,
                    "original_name": tool_id,
                },
            )
            specs.append(spec)

        return specs

    def _infer_risk(self, tool_id: str, description: str) -> ToolRisk:
        """Infer risk level from tool name and description."""
        high_risk_keywords = ["promote", "install", "execute", "apply", "publish", "write", "delete", "archive", "rollback"]
        medium_risk_keywords = ["plan", "prepare", "build", "create", "compile", "validate", "score", "schedule"]

        tool_lower = tool_id.lower()
        desc_lower = description.lower()

        if any(kw in tool_lower or kw in desc_lower for kw in high_risk_keywords):
            return ToolRisk.HIGH
        if any(kw in tool_lower or kw in desc_lower for kw in medium_risk_keywords):
            return ToolRisk.MEDIUM
        return ToolRisk.LOW

    def _infer_effect(self, tool_id: str, description: str) -> ToolEffect:
        """Infer effect type from tool name and description."""
        write_keywords = ["write", "create", "install", "publish", "apply", "promote", "archive"]
        execute_keywords = ["execute", "run", "test", "verify", "grade", "execute", "analyze", "scan", "diagnose"]

        tool_lower = tool_id.lower()
        desc_lower = description.lower()

        if any(kw in tool_lower or kw in desc_lower for kw in execute_keywords):
            return ToolEffect.EXECUTE
        if any(kw in tool_lower or kw in desc_lower for kw in write_keywords):
            return ToolEffect.WRITE
        return ToolEffect.READ

    def _requires_approval(self, tool_id: str, description: str) -> bool:
        """Check if tool requires approval."""
        approval_keywords = ["promote", "install", "execute", "apply", "publish", "write", "delete", "archive", "rollback"]
        tool_lower = tool_id.lower()
        desc_lower = description.lower()
        return any(kw in tool_lower or kw in desc_lower for kw in approval_keywords)


# =============================================================================
# MCP Tool Executor (Bridges to actual implementations)
# =============================================================================

class MCPToolExecutor(ToolExecutor):
    """Executes MCP tools by routing to actual implementations."""

    def __init__(self, workspace_root: str, gateway_url: str = "http://127.0.0.1:8101"):
        self.workspace_root = workspace_root
        self.gateway_url = gateway_url
        self._handlers: Dict[str, Callable] = {}
        self._register_handlers()

    def _register_handlers(self):
        """Register tool handlers - maps tool_id to actual implementation."""
        # Import all the actual tool implementations
        try:
            from app.mcp.tools import MCP_TOOL_HANDLERS
            self._handlers = MCP_TOOL_HANDLERS
        except ImportError:
            # Fallback: create stub handlers
            self._handlers = {}

    async def execute(
        self,
        tool_id: str,
        arguments: Dict[str, Any],
        context: ToolContext,
    ) -> Dict[str, Any]:
        """Execute MCP tool by routing to actual handler."""
        # Check if we have a local handler
        if tool_id in self._handlers:
            handler = self._handlers[tool_id]
            return await handler(arguments, context)

        # Fallback: route through gateway
        return await self._execute_via_gateway(tool_id, arguments, context)

    async def _execute_via_gateway(
        self,
        tool_id: str,
        arguments: Dict[str, Any],
        context: ToolContext,
    ) -> Dict[str, Any]:
        """Execute tool via gateway HTTP call."""
        import urllib.request
        import urllib.error

        url = f"{self.gateway_url}/edgek/mcp/tools/{tool_id}"
        payload = json.dumps({
            "arguments": arguments,
            "context": {
                "run_id": context.run_id,
                "session_id": context.session_id,
                "workspace_root": context.workspace_root,
                "execution_target": context.execution_target,
            },
            "approval_id": context.approval_id,
        }).encode("utf-8")

        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=120) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8")
            raise ToolExecutionError(f"Gateway error {e.code}: {error_body}")
        except urllib.error.URLError as e:
            raise ToolExecutionError(f"Gateway unavailable: {e}")


# =============================================================================
# MCP Tool Plugin
# =============================================================================

class MCPToolPlugin(Plugin):
    """Plugin that provides all MCP tools."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self.adapter = MCPToolAdapter()
        self.executor = None

    async def initialize(self, agent: "PluginAgent") -> None:
        await super().initialize(agent)
        self.executor = MCPToolExecutor(agent.agent.context.workspace_root)

    def get_tools(self) -> List[ToolSpec]:
        return self.adapter.get_tool_specs()

    def get_skills(self) -> List[Skill]:
        """Create skills from MCP tool groups."""
        return [
            Skill(
                skill_id="mcp_beast_operations",
                name="BEAST Operations",
                description="Core BEAST operations: task preparation, SourcePlan, worktrees, verification",
                prompt_template="Perform BEAST operations for {{objective}}",
                tools=[
                    "beast_prepare_task",
                    "beast_prepare_handoff",
                    "beast_sourceplan_prepare",
                    "beast_worktree_create",
                    "beast_worktree_test",
                    "beast_worktree_promote",
                ],
                category="operations",
            ),
            Skill(
                skill_id="mcp_safety_governance",
                name="Safety & Governance",
                description="Safety classification, policy checks, worktree governance",
                prompt_template="Apply safety and governance for {{objective}}",
                tools=[
                    "beast_safety_classify_command",
                    "beast_safety_scan_workspace",
                    "beast_check_policy",
                    "beast_worktree_status",
                    "beast_worktree_diff",
                ],
                category="safety",
            ),
            Skill(
                skill_id="mcp_provider_routing",
                name="Provider Routing",
                description="Provider selection, economist, route cards, fitness",
                prompt_template="Route provider for {{objective}}",
                tools=[
                    "beast_provider_economist_select",
                    "beast_provider_fitness",
                    "beast_build_route_card",
                    "beast_mode_router_select",
                ],
                category="routing",
            ),
            Skill(
                skill_id="mcp_crystal_compute",
                name="Crystal Compute",
                description="Crystal compute, evidence bus, mission lattice, OTel export",
                prompt_template="Use crystal compute for {{objective}}",
                tools=[
                    "beast_crystal_compute",
                    "beast_evidence_bus_summary",
                    "beast_mission_lattice_summary",
                    "beast_otel_export",
                ],
                category="crystal",
            ),
            Skill(
                skill_id="mcp_maintenance_quality",
                name="Maintenance & Quality",
                description="Maintenance cascade, quality cascade, verification, compressors",
                prompt_template="Run maintenance and quality checks for {{objective}}",
                tools=[
                    "beast_run_maintenance_cascade",
                    "beast_run_quality_cascade",
                    "beast_verify",
                    "beast_compressors",
                ],
                category="quality",
            ),
        ]


# =============================================================================
# MCP Server Plugin (stdio/HTTP)
# =============================================================================

class MCPServerPlugin(Plugin):
    """Plugin that provides MCP server capabilities."""

    def get_tools(self) -> List[ToolSpec]:
        from app.kernel.agents.tool_registry import ToolSpec, ToolRisk, ToolEffect, ExecutionTarget
        return [
            ToolSpec(
                tool_id="mcp.server_status",
                title="MCP Server Status",
                description="Get MCP server health and tool catalog",
                category="mcp_server",
                risk=ToolRisk.LOW,
                effect=ToolEffect.READ,
                input_schema={"type": "object", "properties": {}},
                targets=[ExecutionTarget.LOCAL],
                requires_approval=False,
                timeout_seconds=10,
            ),
            ToolSpec(
                tool_id="mcp.install_config",
                title="Install MCP Config",
                description="Install MCP stdio config into editor",
                category="mcp_server",
                risk=ToolRisk.MEDIUM,
                effect=ToolEffect.WRITE,
                input_schema={
                    "type": "object",
                    "properties": {
                        "client": {"type": "string", "enum": ["cursor", "claude-code", "vscode", "cline"]},
                        "workspace": {"type": "string"},
                    },
                    "required": ["client"],
                },
                targets=[ExecutionTarget.LOCAL],
                requires_approval=True,
                timeout_seconds=30,
            ),
        ]

    def get_skills(self) -> List[Skill]:
        return [
            Skill(
                skill_id="mcp_server_management",
                name="MCP Server Management",
                description="Manage MCP server installation and configuration",
                prompt_template="Manage MCP server for {{objective}}",
                tools=["mcp.server_status", "mcp.install_config"],
                category="mcp_server",
            ),
        ]


# =============================================================================
# MCP HTTP Server Adapter
# =============================================================================

class MCPHTTPServerAdapter:
    """Adapts MCP HTTP server to plugin system."""

    def __init__(self, host: str = "127.0.0.1", port: int = 8765):
        self.host = host
        self.port = port
        self.base_url = f"http://{host}:{port}"

    async def call_tool(self, tool_id: str, arguments: Dict[str, Any], context: ToolContext) -> Dict[str, Any]:
        """Call MCP tool via HTTP."""
        import urllib.request
        import urllib.error

        url = f"{self.base_url}/mcp/tools/{tool_id}"
        payload = json.dumps({
            "arguments": arguments,
            "context": {
                "run_id": context.run_id,
                "session_id": context.session_id,
                "workspace_root": context.workspace_root,
            },
            "approval_id": context.approval_id,
        }).encode("utf-8")

        req = urllib.request.Request(
            f"{self.base_url}/mcp/tools/{tool_id}",
            data=json.dumps({"arguments": arguments}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=120) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8")
            raise ToolExecutionError(f"MCP HTTP error {e.code}: {error_body}")
        except urllib.error.URLError as e:
            raise ToolExecutionError(f"MCP HTTP server unavailable: {e}")


# =============================================================================
# Factory Functions
# =============================================================================

def create_mcp_tool_plugin(config: Optional[Dict[str, Any]] = None) -> MCPToolPlugin:
    """Create MCP tool plugin."""
    return MCPToolPlugin(config)


def create_mcp_server_plugin(config: Optional[Dict[str, Any]] = None) -> MCPServerPlugin:
    """Create MCP server plugin."""
    return MCPServerPlugin(config)


def register_mcp_tools(registry: ToolRegistry, workspace_root: str, gateway_url: str = "http://127.0.0.1:8101") -> None:
    """Register all MCP tools in the tool registry."""
    adapter = MCPToolAdapter()
    specs = adapter.get_tool_specs()

    for spec in specs:
        registry.register_spec(spec)

    # Register MCP executor
    executor = MCPToolExecutor(workspace_root, gateway_url)
    registry.register_executor(ExecutionTarget.LOCAL, executor)


def create_mcp_http_adapter(host: str = "127.0.0.1", port: int = 8765) -> MCPHTTPServerAdapter:
    """Create MCP HTTP server adapter."""
    return MCPHTTPServerAdapter(host, port)


# =============================================================================
# MCP Tool Catalog (for discovery)
# =============================================================================

def get_mcp_tool_catalog() -> List[Dict[str, Any]]:
    """Get catalog of all MCP tools for discovery."""
    adapter = MCPToolAdapter()
    tools = adapter.tools

    return [
        {
            "name": tool.get("name", ""),
            "description": tool.get("description", ""),
            "inputSchema": tool.get("inputSchema", {}),
            "risk": MCPToolAdapter()._infer_risk(tool.get("name", ""), tool.get("description", "")),
            "effect": MCPToolAdapter()._infer_effect(tool.get("name", ""), tool.get("description", "")),
        }
        for tool in tools
    ]


# =============================================================================
# Export
# =============================================================================

__all__ = [
    "MCPToolAdapter",
    "MCPToolExecutor",
    "MCPToolPlugin",
    "MCPServerPlugin",
    "MCPHTTPServerAdapter",
    "register_mcp_tools",
    "create_mcp_tool_plugin",
    "create_mcp_server_plugin",
    "create_mcp_http_adapter",
    "get_mcp_tool_catalog",
]
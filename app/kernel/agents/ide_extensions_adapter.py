"""
IDE Extensions Adapter for BEAST.
Bridges the existing desktop-IDE extensions (beast-crystal-lab, beast-companion, etc.)
to the new plugin system with Effect runtime, unified registry, and skill system.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import subprocess
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
# IDE Extension Manifest Loader
# =============================================================================

IDE_EXTENSIONS_DIR = Path("desktop-ide/extensions")


@dataclass
class IDEExtensionManifest:
    """Desktop-IDE extension manifest."""
    id: str = ""
    name: str = ""
    version: str = ""
    description: str = ""
    main: str = "extension.js"
    capabilities: List[str] = field(default_factory=list)
    contributes: Dict[str, Any] = field(default_factory=dict)


def load_ide_extension_manifests(extensions_dir: Path = IDE_EXTENSIONS_DIR) -> List[IDEExtensionManifest]:
    """Load all IDE extension manifests."""
    manifests = []

    if not extensions_dir.exists():
        return manifests

    for ext_dir in extensions_dir.iterdir():
        if not ext_dir.is_dir():
            continue

        manifest_file = ext_dir / "beast-extension.json"
        if not manifest_file.exists():
            continue

        try:
            with open(manifest_file) as f:
                data = json.load(f)
            manifest = IDEExtensionManifest(**data)
            manifests.append(manifest)
        except Exception as e:
            print(f"Failed to load IDE extension {ext_dir}: {e}")

    return manifests


# =============================================================================
# IDE Extension Adapter
# =============================================================================

class IDEExtensionAdapter(Plugin):
    """Adapter for desktop-IDE extensions."""

    def __init__(
        self,
        manifest: IDEExtensionManifest,
        extension_dir: Path,
        api: Any = None,
    ):
        super().__init__({})
        self.manifest = manifest
        self.extension_dir = extension_dir
        self.api = api
        self._command_handlers: Dict[str, Callable] = {}

    async def initialize(self, agent: "PluginAgent") -> None:
        await super().initialize(agent)
        self._register_command_handlers()

    def _register_command_handlers(self):
        """Register command handlers from extension."""
        commands = self.manifest.contributes.get("commands", [])

        for cmd in commands:
            cmd_id = cmd.get("id", "")
            if not cmd_id:
                continue

            # The extension.js handles navigation - we expose it as a tool
            self._command_handlers[cmd_id] = lambda cmd_id=cmd_id: self._execute_command(cmd_id)

    async def _execute_command(self, command_id: str) -> Dict[str, Any]:
        """Execute an IDE extension command."""
        # Map command to route
        routes = {
            "beast.openCrystallization": "crystallization",
            "beast.openEvidence": "evidence",
            "beast.openMission": "mission",
            "beast.openCompatibility": "compatibility",
            "beast.openTerminal": "terminal",
            "beast.openTesting": "testing",
            "beast.openSourcePlan": "source",
            "beast.openReview": "review",
        }

        route = routes.get(command_id)
        if route:
            return {"navigate": route, "command": command_id}

        return {"error": f"Unknown command: {command_id}"}

    def get_tools(self) -> List[ToolSpec]:
        """Convert extension commands to tools."""
        tools = []
        commands = self.manifest.contributes.get("commands", [])

        for cmd in commands:
            cmd_id = cmd.get("id", "")
            if not cmd_id:
                continue

            # Create unique tool_id by including extension prefix
            unique_tool_id = f"ide.{self.manifest.id.replace('.', '_').replace('-', '_')}.{cmd_id.replace('-', '_')}"
            tool_spec = ToolSpec(
                    tool_id=unique_tool_id,
                    title=cmd.get("title", cmd_id),
                    description=f"IDE Extension Command: {cmd.get('title', cmd_id)}",
                    category="ide_extension",
                    risk=ToolRisk.LOW,
                    effect=ToolEffect.READ,
                    input_schema={"type": "object", "properties": {}},
                    targets=[ExecutionTarget.LOCAL],
                    requires_approval=False,
                    timeout_seconds=10,
                    metadata={
                        "extension_id": self.manifest.id,
                        "extension_name": self.manifest.name,
                        "original_command": cmd_id,
                    },
                )
            tools.append(tool_spec)

        return tools

    def get_skills(self) -> List[Skill]:
        """Create skills from extension commands."""
        skills = []
        commands = self.manifest.contributes.get("commands", [])

        for cmd in commands:
            cmd_id = cmd.get("id", "")
            if not cmd_id:
                continue

            skill = Skill(
                skill_id=f"ide.{cmd_id}",
                name=cmd.get("title", cmd_id),
                description=f"IDE Extension: {cmd.get('title', cmd_id)}",
                prompt_template=f"Execute IDE command: {cmd.get('title', cmd_id)}",
                tools=[f"ide.{cmd_id}"],
                category="ide_extension",
            )
            skills.append(skill)

        return skills


# =============================================================================
# IDE Extension Executor
# =============================================================================

class IDEExtensionExecutor(ToolExecutor):
    """Executes IDE extension commands."""

    def __init__(self, extensions: List[IDEExtensionAdapter]):
        self.extensions = {ext.manifest.id: ext for ext in extensions}

    async def execute(
        self,
        tool_id: str,
        arguments: Dict[str, Any],
        context: ToolContext,
    ) -> Dict[str, Any]:
        """Execute IDE extension command."""
        # Parse tool_id format: ide.beast.openMission
        if not tool_id.startswith("ide."):
            raise ToolNotFoundError(f"Invalid IDE tool ID: {tool_id}")

        command_id = tool_id[4:]  # Remove "ide." prefix

        # Find the extension that owns this command
        for ext_id, ext in self.extensions.items():
            commands = ext.manifest.contributes.get("commands", [])
            if any(cmd.get("id") == command_id for cmd in commands):
                return await ext._execute_command(command_id)

        raise ToolNotFoundError(f"IDE command not found: {command_id}")


# =============================================================================
# IDE Extension Plugin
# =============================================================================

class IDEExtensionPlugin(Plugin):
    """Plugin that provides all IDE extensions."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self.extensions: List[IDEExtensionAdapter] = []
        self.executor: Optional[IDEExtensionExecutor] = None

    async def initialize(self, agent: "PluginAgent") -> None:
        await super().initialize(agent)

        # Load all IDE extensions
        manifests = load_ide_extension_manifests()
        for manifest in manifests:
            ext_dir = IDE_EXTENSIONS_DIR / manifest.id
            if ext_dir.exists():
                adapter = IDEExtensionAdapter(manifest, ext_dir)
                await adapter.initialize(agent)
                self.extensions.append(adapter)

        self.executor = IDEExtensionExecutor(self.extensions)

    def get_tools(self) -> List[ToolSpec]:
        all_tools = []
        for ext in self.extensions:
            all_tools.extend(ext.get_tools())
        return all_tools

    def get_skills(self) -> List[Skill]:
        all_skills = []
        for ext in self.extensions:
            all_skills.extend(ext.get_skills())
        return all_skills


# =============================================================================
# IDE Extension Skills
# =============================================================================

def create_ide_skills() -> List[Skill]:
    """Create skills from IDE extensions."""
    skills = []

    # Crystal Lab skill
    skills.append(Skill(
        skill_id="ide.crystal_lab",
        name="Crystal Lab Navigation",
        description="Open crystallization and evidence views",
        prompt_template="Navigate to crystallization or evidence view",
        tools=["ide.beast.openCrystallization", "ide.beast.openEvidence"],
        category="navigation",
    ))

    # Companion skill
    skills.append(Skill(
        skill_id="ide.companion",
        name="Companion Navigation",
        description="Open mission control and compatibility center",
        prompt_template="Navigate to mission control or compatibility center",
        tools=["ide.beast.openMission", "ide.beast.openCompatibility"],
        category="navigation",
    ))

    # Remote Toolkit skill
    skills.append(Skill(
        skill_id="ide.remote_toolkit",
        name="Remote Toolkit Navigation",
        description="Open remote compatibility and terminal",
        prompt_template="Navigate to remote compatibility or terminal",
        tools=["ide.beast.openCompatibility", "ide.beast.openTerminal"],
        category="navigation",
    ))

    # Code Health skill
    skills.append(Skill(
        skill_id="ide.code_health",
        name="Code Health Navigation",
        description="Open testing, SourcePlan review, and governed review",
        prompt_template="Navigate to testing, SourcePlan, or review",
        tools=["ide.beast.openTesting", "ide.beast.openSourcePlan", "ide.beast.openReview"],
        category="navigation",
    ))

    return skills


# =============================================================================
# Factory Functions
# =============================================================================

def create_ide_extension_plugin(config: Optional[Dict[str, Any]] = None) -> IDEExtensionPlugin:
    """Create IDE extension plugin."""
    return IDEExtensionPlugin(config)


def register_ide_extensions(registry: ToolRegistry, extensions_dir: Path = IDE_EXTENSIONS_DIR) -> None:
    """Register all IDE extension tools in the tool registry."""
    manifests = load_ide_extension_manifests(extensions_dir)

    for manifest in manifests:
        # Convert manifest ID (with dots) to directory name (with hyphens)
        ext_dir_name = manifest.id.replace('.', '-')
        ext_dir = extensions_dir / ext_dir_name
        if not ext_dir.exists():
            continue

        adapter = IDEExtensionAdapter(manifest, ext_dir)
        tools = adapter.get_tools()

        for spec in tools:
            registry.register_spec(spec)

    # Register IDE executor
    executor = IDEExtensionExecutor([
        IDEExtensionAdapter(m, extensions_dir / m.id)
        for m in manifests
        if (extensions_dir / m.id).exists()
    ])
    registry.register_executor(ExecutionTarget.LOCAL, executor)


def create_ide_extension_tools(extensions_dir: Path = IDE_EXTENSIONS_DIR) -> List[ToolSpec]:
    """Create tool specs for all IDE extension commands."""
    all_tools = []
    manifests = load_ide_extension_manifests(extensions_dir)

    for manifest in manifests:
        # Convert manifest ID (with dots) to directory name (with hyphens)
        ext_dir_name = manifest.id.replace('.', '-')
        ext_dir = extensions_dir / ext_dir_name
        if not ext_dir.exists():
            continue

        adapter = IDEExtensionAdapter(manifest, ext_dir)
        all_tools.extend(adapter.get_tools())

    return all_tools


# =============================================================================
# Export
# =============================================================================

__all__ = [
    "IDEExtensionManifest",
    "IDEExtensionAdapter",
    "IDEExtensionExecutor",
    "IDEExtensionPlugin",
    "load_ide_extension_manifests",
    "create_ide_extension_plugin",
    "register_ide_extensions",
    "create_ide_extension_tools",
    "create_ide_skills",
]
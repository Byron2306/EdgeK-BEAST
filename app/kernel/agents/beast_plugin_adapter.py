"""
Adapter to make existing BEAST plugins work with the new plugin system.
Bridges the old BEAST plugin manifest format to the new plugin system.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import sys
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
import importlib.util

from app.kernel.agents.tool_registry import ToolSpec, ToolRisk, ToolEffect, ExecutionTarget
from app.kernel.agents.ide_extensions_adapter import IDEExtensionAdapter, load_ide_extension_manifests as load_ide_extensions
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
)
from app.kernel.agents.zod_schemas import ToolSpec as ZodToolSpec, ToolRisk, ToolEffect, ExecutionTarget
from app.kernel.agents.tool_registry import ToolRegistry
from app.kernel.agents.agent_effect import EffectAgent, AgentContext


# =============================================================================
# Old BEAST Plugin Manifest Adapter
# =============================================================================

@dataclass
class OldBeastPluginManifest:
    """Old BEAST plugin manifest format."""
    beast_plugin_manifest_version: str = "1.0"
    id: str = ""
    name: str = ""
    version: str = ""
    publisher: str = ""
    description: str = ""
    risk_class: str = "medium"
    entrypoint: Dict[str, Any] = field(default_factory=dict)
    tools: List[Dict[str, Any]] = field(default_factory=list)
    permissions: Dict[str, Any] = field(default_factory=dict)
    budget: Dict[str, Any] = field(default_factory=dict)
    approval_policy: Dict[str, Any] = field(default_factory=dict)


def load_old_manifest(path: Path) -> OldBeastPluginManifest:
    """Load old BEAST plugin manifest."""
    with open(path) as f:
        data = json.load(f)
    return OldBeastManifest(**data)


@dataclass
class OldBeastManifest:
    """Internal representation of old manifest."""
    beast_plugin_manifest_version: str = "1.0"
    id: str = ""
    name: str = ""
    version: str = ""
    publisher: str = ""
    description: str = ""
    risk_class: str = "medium"
    entrypoint: Dict[str, Any] = field(default_factory=dict)
    tools: List[Dict[str, Any]] = field(default_factory=list)
    permissions: Dict[str, Any] = field(default_factory=dict)
    budget: Dict[str, Any] = field(default_factory=dict)
    approval_policy: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "OldBeastManifest":
        # Handle entrypoint with module key
        entrypoint = data.get("entrypoint", {})
        if isinstance(entrypoint, dict) and "module" in entrypoint and "kind" not in entrypoint:
            entrypoint = {**entrypoint, "kind": "python"}
        data = {**data, "entrypoint": entrypoint}
        # Use fields() instead of hasattr to include fields with default_factory
        valid_keys = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in valid_keys})


# =============================================================================
# Plugin Adapter (Bridges Old to New)
# =============================================================================

class OldPluginAdapter(Plugin):
    """Adapter that wraps an old BEAST plugin as a new Plugin."""

    def __init__(
        self,
        manifest: OldBeastManifest,
        plugin_path: Path,
        config: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(config)
        self.manifest = manifest
        self.plugin_path = plugin_path
        self._module = None
        self._tool_functions: Dict[str, Callable] = {}

    async def initialize(self, agent: "PluginAgent") -> None:
        """Load the old plugin module and register tools."""
        await super().initialize(agent)

        # Load the entrypoint module
        entrypoint = self.manifest.entrypoint
        if entrypoint.get("kind") == "python":
            module_name = entrypoint.get("module")
            if module_name:
                self._module = importlib.import_module(module_name)

        # Extract tool functions from module
        if self._module:
            for tool_def in self.manifest.tools:
                tool_name = tool_def.get("name")
                if tool_name and hasattr(self._module, tool_name):
                    self._tool_functions[tool_name] = getattr(self._module, tool_name)

    async def shutdown(self) -> None:
        self._module = None
        self._tool_functions.clear()
        await super().shutdown()

    def get_tools(self) -> List[ToolSpec]:
        """Convert old tool definitions to new ToolSpec format."""
        tools = []
        for tool_def in self.manifest.tools:
            tool_id = tool_def.get("name", "")
            if not tool_id:
                continue

            # Map old risk_class to new ToolRisk
            risk_map = {
                "low": ToolRisk.LOW,
                "medium": ToolRisk.MEDIUM,
                "high": ToolRisk.HIGH,
                "critical": ToolRisk.CRITICAL,
            }
            risk = risk_map.get(self.manifest.risk_class, ToolRisk.MEDIUM)

            # Determine effect from permissions
            effect = ToolEffect.READ
            perms = self.manifest.permissions
            if perms.get("filesystem_write") or perms.get("subprocess"):
                effect = ToolEffect.WRITE
            elif perms.get("subprocess"):
                effect = ToolEffect.EXECUTE

            # Determine targets
            targets = [ExecutionTarget.LOCAL]
            if self.manifest.permissions.get("network_domains"):
                targets.append(ExecutionTarget.SSH)

            # Build input schema from old tool definition
            input_schema = tool_def.get("inputSchema", {"type": "object", "properties": {}})

            tool_spec = ToolSpec(
                tool_id=tool_id,
                title=tool_def.get("description", tool_id),
                description=tool_def.get("description", ""),
                category="plugin",
                risk=risk,
                effect=effect,
                input_schema=input_schema,
                targets=[ExecutionTarget.LOCAL],
                requires_approval=bool(
                    self.manifest.approval_policy.get("first_run") or
                    self.manifest.approval_policy.get("filesystem_write")
                ),
                timeout_seconds=30,
            )
            tools.append(tool_spec)

        return tools

    def get_tool_function(self, tool_id: str) -> Optional[Callable]:
        """Get the actual tool function from the old module."""
        return self._tool_functions.get(tool_id)


# =============================================================================
# Plugin Loader for Old BEAST Plugins
# =============================================================================

class OldPluginLoader:
    """Loads old BEAST plugins into the new plugin system."""

    def __init__(self, plugin_agent: "PluginAgent", plugins_dir: Path = None):
        self.plugin_agent = plugin_agent
        self.plugins_dir = plugins_dir or Path("plugins")
        from app.kernel.agents.plugin_system import PluginDiscovery
        self.discovery = PluginDiscovery([self.plugins_dir])

    def load_manifest(self, manifest_path: Path) -> Optional[OldBeastManifest]:
        """Load and parse old manifest."""
        try:
            with open(manifest_path) as f:
                data = json.load(f)
            return OldBeastManifest.from_dict(data)
        except Exception as e:
            print(f"Failed to load manifest {manifest_path}: {e}")
            return None

    def create_adapter(self, manifest: OldBeastManifest, plugin_dir: Path) -> OldPluginAdapter:
        """Create adapter for old plugin."""
        return OldPluginAdapter(manifest, plugin_dir)

    async def load_plugin(self, manifest_path: Path) -> bool:
        """Load an old BEAST plugin into the new system."""
        manifest = self.load_manifest(manifest_path)
        if not manifest:
            return False

        plugin_dir = manifest_path.parent
        adapter = self.create_adapter(manifest, plugin_dir)

        # Create metadata for new system
        metadata = PluginMetadata(
            name=manifest.id,
            version=manifest.version,
            description=manifest.description,
            publisher=manifest.publisher,
            plugin_type=PluginType.TOOL,
            entry_point=manifest.entrypoint.get("module", manifest.id),
        )

        config = PluginConfig(enabled=True)
        self.plugin_agent.register_plugin(metadata, config)
        self.plugin_agent.plugins[manifest.id].status = PluginStatus.LOADING

        # Initialize adapter
        try:
            await adapter.initialize(self.plugin_agent)
        except Exception as e:
            print(f"Failed to initialize adapter for {manifest.id}: {e}")
            return False

        # Register tools
        for tool_spec in adapter.get_tools():
            self.plugin_agent.plugins[manifest.id].provided_tools.append(tool_spec.tool_id)
            if self.plugin_agent.tool_registry:
                self.plugin_agent.tool_registry.register_spec(tool_spec)

        self.plugin_agent.plugins[manifest.id].status = PluginStatus.LOADED
        self.plugin_agent.plugins[manifest.id].instance = adapter

        return True

    async def load_all(self, plugins_dir: Path = None) -> Dict[str, bool]:
        """Load all old BEAST plugins from directory."""
        dir_path = plugins_dir or self.plugins_dir
        results = {}

        if not dir_path.exists():
            return results

        for manifest_file in dir_path.glob("**/*.beast-plugin.json"):
            if manifest_file.name == "beast-plugin.schema.json":
                continue
            results[manifest_file.stem] = await self.load_plugin(manifest_file)

        return results


# =============================================================================
# Desktop-IDE Extension Adapter
# =============================================================================

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


class UnifiedPluginLoader:
    """Loads all plugins (old BEAST, IDE extensions, new format)."""

    def __init__(self, plugin_agent: "PluginAgent"):
        self.plugin_agent = plugin_agent
        self.old_loader = OldPluginLoader(plugin_agent)
        self.discovery = self.old_loader

    def discover(self) -> List[PluginMetadata]:
        return self.old_loader.discovery.discover()

    async def load_all(
        self,
        old_plugins_dir: Path = None,
        ide_extensions_dir: Path = None,
    ) -> Dict[str, bool]:
        """Load all plugins from all sources."""
        results = {}

        # Load old BEAST plugins
        if old_plugins_dir and old_plugins_dir.exists():
            old_results = await self.old_loader.load_all(old_plugins_dir)
            results.update({f"old:{k}": v for k, v in old_results.items()})

        # Load IDE extensions
        if ide_extensions_dir and ide_extensions_dir.exists():
            ide_results = await self._load_ide_extensions(ide_extensions_dir)
            results.update({f"ide:{k}": v for k, v in ide_results.items()})

        return results

    async def _load_ide_extensions(self, extensions_dir: Path) -> Dict[str, bool]:
        """Load IDE extensions as plugins."""
        results = {}
        manifests = load_ide_extensions(extensions_dir)

        for manifest in manifests:
            try:
                adapter = IDEExtensionAdapter(manifest, extensions_dir / manifest.id)
                await adapter.initialize(self.plugin_agent)

                metadata = PluginMetadata(
                    name=manifest.id,
                    version=manifest.version,
                    description=manifest.description,
                    plugin_type=PluginType.INTEGRATION,
                    entry_point=manifest.main,
                )
                config = PluginConfig(enabled=True)
                self.plugin_agent.register_plugin(metadata, config)

                state = self.plugin_agent.plugins[manifest.id]
                print(f"DEBUG: Registering tools for {manifest.id}")
                tools = adapter.get_tools()
                print(f"DEBUG: Tools from adapter.get_tools() for {manifest.id}: {[t.tool_id for t in tools]}")
                for tool_spec in tools:
                    print(f"DEBUG: Registering tool {tool_spec.tool_id}")
                    state.provided_tools.append(tool_spec.tool_id)
                    if self.plugin_agent.tool_registry:
                        self.plugin_agent.tool_registry.register_spec(tool_spec)

                state.status = PluginStatus.LOADED
                state.instance = adapter
                results[manifest.id] = True

            except Exception as e:
                print(f"Failed to load IDE extension {manifest.id}: {e}")
                results[manifest.id] = False

        return results


# =============================================================================
# Provider Economist as Plugin
# =============================================================================

class ProviderEconomistPlugin(Plugin):
    """Provider Economist as a first-class plugin."""

    def get_tools(self) -> List[ToolSpec]:
        from app.kernel.agents.zod_schemas import ToolSpec, ToolRisk, ToolEffect, ExecutionTarget
        return [
            ToolSpec(
                tool_id="beast_provider_economist_select",
                title="Select Best Provider Route",
                description="Choose the best eligible provider route for a requested role using economic evidence.",
                category="routing",
                risk=ToolRisk.MEDIUM,
                effect=ToolEffect.READ,
                input_schema={
                    "type": "object",
                    "properties": {
                        "candidates": {
                            "type": "array",
                            "items": {"type": "object"},
                            "description": "Array of provider route candidates with metrics",
                        },
                        "requested_role": {
                            "type": "string",
                            "description": "The role to select a provider for",
                        },
                        "policy": {
                            "type": "object",
                            "description": "Optional economist policy overrides",
                            "properties": {
                                "requested_role": {"type": "string"},
                                "task_class": {"type": "string"},
                                "max_latency_ms": {"type": "number"},
                                "max_usd_per_fix": {"type": "number"},
                                "min_auth_confidence": {"type": "number"},
                                "require_cost_observation": {"type": "boolean"},
                                "prefer_hidden_clean": {"type": "boolean"},
                                "friction_mode": {"type": "string", "enum": ["off", "shadow", "enforce"]},
                            },
                        },
                    },
                    "required": ["candidates", "requested_role"],
                },
                targets=[ExecutionTarget.LOCAL],
                requires_approval=False,
                timeout_seconds=30,
            ),
        ]

    def get_skills(self) -> List[Skill]:
        return [
            Skill(
                skill_id="select_provider_route",
                name="Select Provider Route",
                description="Economically select the best provider route for a task",
                prompt_template="Select the best provider route for role {{requested_role}} from candidates: {{candidates}}",
                tools=["beast_provider_economist_select"],
                category="routing",
            ),
        ]


# =============================================================================
# Factory Functions
# =============================================================================

def create_unified_plugin_manager(
    agent: Any,
    old_plugins_dir: Path = None,
    ide_extensions_dir: Path = None,
) -> "PluginManager":
    """Create plugin manager with all plugin types loaded."""
    from app.kernel.agents.plugin_system import PluginManager
    from app.kernel.agents.plugin_system import PluginMetadata, PluginConfig, PluginType

    manager = PluginManager(agent, plugin_dirs=[])

    # Create unified loader
    loader = UnifiedPluginLoader(manager.plugin_agent)

    # Load all plugins
    old_dir = old_plugins_dir or Path("plugins")
    ide_dir = ide_extensions_dir or Path("desktop-ide/extensions")

    asyncio.create_task(loader.load_all(old_dir, ide_dir))

    # Register Provider Economist as built-in
    economist_metadata = PluginMetadata(
        name="edgek.provider-economist",
        version="0.1.0",
        description="Local provider route selection using governed benchmark evidence.",
        publisher="EdgeK BEAST",
        plugin_type=PluginType.TOOL,
        entry_point="app.kernel.adapters.provider_economist",
    )
    manager.plugin_agent.register_plugin(economist_metadata, PluginConfig(enabled=True))

    return manager


async def load_all_beast_plugins(tool_registry: ToolRegistry) -> Dict[str, bool]:
    """Load all BEAST plugins (old format, IDE extensions, built-in)."""
    plugin_agent = PluginAgent(None, tool_registry=tool_registry)
    loader = UnifiedPluginLoader(plugin_agent)
    return await loader.load_all(
        old_plugins_dir=Path("plugins"),
        ide_extensions_dir=Path("desktop-ide/extensions"),
    )


# =============================================================================
# Export
# =============================================================================

__all__ = [
    "OldBeastManifest",
    "OldPluginAdapter",
    "OldPluginLoader",
    "IDEExtensionManifest",
    "IDEExtensionAdapter",
    "load_ide_extensions",
    "create_ide_extension_tools",
    "UnifiedPluginLoader",
    "ProviderEconomistPlugin",
    "create_unified_plugin_manager",
    "load_all_beast_plugins",
]
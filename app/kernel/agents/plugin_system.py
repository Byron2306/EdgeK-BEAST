"""Plugin system for BEAST.
OpenCode-inspired plugin architecture with Effect runtime integration.
"""

from __future__ import annotations

import asyncio
import hashlib
import importlib
import importlib.util
import json
import pkgutil
import sys
import time
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from enum import Enum
from typing import Any, AsyncGenerator, Awaitable, Callable, Dict, List, Optional, Set, Type
import hashlib

from app.kernel.agents.effect_runtime import (
    EffectError,
    span,
    CancellationToken,
)
from app.kernel.agents.zod_schemas import ToolSpec, ExecutionTarget
from app.kernel.agents.tool_registry import ToolRegistry, ToolSpec, ToolExecutor
from app.kernel.agents.agent_effect import EffectAgent, AgentContext, AgentCommand, AgentCommandType


# =============================================================================
# Plugin Types
# =============================================================================

class PluginStatus(str, Enum):
    UNLOADED = "unloaded"
    LOADING = "loading"
    LOADED = "loaded"
    ERROR = "error"
    UNLOADING = "unloading"


class PluginType(str, Enum):
    TOOL = "tool"
    SKILL = "skill"
    INTEGRATION = "integration"
    EXECUTOR = "executor"
    PROVIDER = "provider"


@dataclass
class PluginMetadata:
    """Plugin metadata (OpenCode plugin.json equivalent + BEAST extensions)."""
    # Core fields
    name: str
    version: str
    description: str
    author: str = ""
    license: str = "MIT"
    plugin_type: PluginType = PluginType.TOOL
    dependencies: List[str] = field(default_factory=list)  # Plugin names
    provides: List[str] = field(default_factory=list)  # Tool IDs, skill IDs, etc.
    requires: List[str] = field(default_factory=list)  # Capabilities needed
    entry_point: str = "plugin"  # Module attribute name
    config_schema: Optional[Dict[str, Any]] = None
    tags: List[str] = field(default_factory=list)
    homepage: str = ""
    repository: str = ""
    
    # BEAST extensions
    id: str = ""
    beast_plugin_manifest_version: str = "1.0"
    publisher: str = ""
    risk_class: str = "medium"
    entrypoint: Dict[str, Any] = field(default_factory=dict)
    tools: List[Dict[str, Any]] = field(default_factory=list)
    permissions: Dict[str, Any] = field(default_factory=dict)
    budget: Dict[str, Any] = field(default_factory=dict)
    approval_policy: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PluginConfig:
    """Runtime plugin configuration."""
    enabled: bool = True
    config: Dict[str, Any] = field(default_factory=dict)
    priority: int = 0  # Load order


@dataclass
class PluginState:
    """Runtime plugin state."""
    metadata: PluginMetadata
    config: PluginConfig
    status: PluginStatus = PluginStatus.UNLOADED
    module: Optional[Any] = None
    instance: Optional[Any] = None
    loaded_at: Optional[float] = None
    error: Optional[str] = None
    provided_tools: List[str] = field(default_factory=list)
    provided_skills: List[str] = field(default_factory=list)
    provided_integrations: List[str] = field(default_factory=list)


# =============================================================================
# Plugin Base Classes
# =============================================================================

class Plugin:
    """Base plugin class (OpenCode plugin pattern)."""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self._initialized = False

    async def initialize(self, agent: "PluginAgent") -> None:
        """Initialize plugin with agent context."""
        self._initialized = True

    async def shutdown(self) -> None:
        """Cleanup plugin resources."""
        self._initialized = False

    def get_tools(self) -> List[ToolSpec]:
        """Return tools provided by this plugin."""
        return []

    def get_skills(self) -> List[Skill]:
        """Return skills provided by this plugin."""
        return []

    def get_integrations(self) -> List[Integration]:
        """Return integrations provided by this plugin."""
        return []


class Skill:
    """Skill = prompt template + tool bundle (OpenCode skill pattern)."""
    
    def __init__(
        self,
        skill_id: str,
        name: str,
        description: str,
        prompt_template: str,
        tools: List[str] = None,
        parameters: Dict[str, Any] = None,
        category: str = "general",
    ):
        self.skill_id = skill_id
        self.name = name
        self.description = description
        self.prompt_template = prompt_template
        self.tools = tools or []
        self.parameters = parameters or {}
        self.category = category

    def render_prompt(self, parameters: Dict[str, Any]) -> str:
        """Render prompt template with parameters."""
        template = self.prompt_template
        for key, value in {**self.parameters, **parameters}.items():
            template = template.replace(f"{{{{{key}}}}}", str(value))
        return template


class Integration:
    """Integration with external system (MCP, LSP, etc.)."""
    
    def __init__(
        self,
        integration_id: str,
        name: str,
        description: str,
        integration_type: str = "mcp",
        config_schema: Dict[str, Any] = None,
    ):
        self.integration_id = integration_id
        self.name = name
        self.description = description
        self.integration_type = integration_type
        self.config_schema = config_schema or {}

    async def connect(self, config: Dict[str, Any]) -> bool:
        """Establish connection."""
        return True

    async def disconnect(self) -> None:
        """Close connection."""
        pass

    async def execute(self, method: str, params: Dict[str, Any]) -> Any:
        """Execute integration method."""
        raise NotImplementedError


# =============================================================================
# Plugin Discovery
# =============================================================================

class PluginDiscovery:
    """Discover plugins from filesystem."""

    def __init__(self, plugin_dirs: List[Path] = None):
        self.plugin_dirs = plugin_dirs or [
            Path("plugins"),
            Path.cwd() / ".beast" / "plugins",
            Path.home() / ".beast" / "plugins",
        ]

    def discover(self) -> List[PluginMetadata]:
        """Discover all plugins."""
        plugins = []
        for plugin_dir in self.plugin_dirs:
            if not plugin_dir.exists():
                continue
            for plugin_file in plugin_dir.glob("**/*.beast-plugin.json"):
                try:
                    with open(plugin_file) as f:
                        data = json.load(f)
                    metadata = PluginMetadata(**data)
                    plugins.append(metadata)
                except Exception as e:
                    print(f"Failed to load plugin {plugin_file}: {e}")
        return plugins

    def discover_python_plugins(self, package: str = "app.kernel.agents.plugins") -> List[PluginMetadata]:
        """Discover plugins from Python packages."""
        plugins = []
        try:
            module = importlib.import_module(package)
            for _, name, is_pkg in pkgutil.iter_modules(module.__path__):
                if is_pkg:
                    try:
                        plugin_module = importlib.import_module(f"{package}.{name}")
                        metadata = getattr(plugin_module, "PLUGIN_METADATA", None)
                        if metadata:
                            plugins.append(PluginMetadata(**metadata))
                    except Exception:
                        pass
        except Exception:
            pass
        return plugins


# =============================================================================
# Plugin Agent (Agent with Plugin Support)
# =============================================================================

class PluginAgent:
    """Agent with plugin system support."""
    
    def __init__(self, agent: Any, tool_registry: Optional[ToolRegistry] = None):
        self.agent = agent
        self.tool_registry = tool_registry
        self.plugins: Dict[str, PluginState] = {}
        self.skills: Dict[str, Skill] = {}
        self.integrations: Dict[str, Integration] = {}
        self._load_order: List[str] = []
        self._skill_registry: Dict[str, Skill] = {}

    def register_plugin(self, metadata: PluginMetadata, config: PluginConfig = None) -> None:
        """Register a plugin."""
        state = PluginState(
            metadata=metadata,
            config=config or PluginConfig(),
        )
        self.plugins[metadata.name] = state

    async def load_plugin(self, name: str) -> bool:
        """Load and initialize a plugin."""
        if name not in self.plugins:
            return False

        state = self.plugins[name]
        if state.status == PluginStatus.LOADED:
            return True

        state.status = PluginStatus.LOADING

        try:
            # Load module
            spec = importlib.util.find_spec(state.metadata.entry_point)
            if not spec:
                raise ImportError(f"Plugin entry point not found: {state.metadata.entry_point}")

            module = importlib.util.module_from_spec(spec)
            sys.modules[state.metadata.name] = module
            spec.loader.exec_module(module)

            # Get plugin class/instance
            plugin_attr = getattr(module, state.metadata.entry_point, None)
            if not plugin_attr:
                raise AttributeError(f"Plugin entry point not found: {state.metadata.entry_point}")

            # Instantiate if class, use directly if instance
            if isinstance(plugin_attr, type):
                instance = plugin_attr(state.config.config)
            else:
                instance = plugin_attr

            # Initialize
            await instance.initialize(self)

            # Register provided tools
            for tool_spec in instance.get_tools():
                state.provided_tools.append(tool_spec.tool_id)
                if self.tool_registry:
                    self.tool_registry.register_spec(tool_spec)

            # Register provided skills
            for skill in instance.get_skills():
                self.skills[skill.skill_id] = skill
                state.provided_skills.append(skill.skill_id)

            # Register provided integrations
            for integration in instance.get_integrations():
                self.integrations[integration.integration_id] = integration
                state.provided_integrations.append(integration.integration_id)

            state.module = module
            state.instance = instance
            state.status = PluginStatus.LOADED
            state.loaded_at = time.time()

            return True

        except Exception as e:
            state.status = PluginStatus.ERROR
            state.error = str(e)
            return False

    async def unload_plugin(self, name: str) -> bool:
        """Unload a plugin."""
        if name not in self.plugins:
            return False

        state = self.plugins[name]
        if state.status != PluginStatus.LOADED:
            return True

        state.status = PluginStatus.UNLOADING

        try:
            if state.instance:
                await instance.shutdown()

            # Remove provided tools/skills/integrations
            for tool_id in state.provided_tools:
                pass
            for skill_id in state.provided_skills:
                self.skills.pop(skill_id, None)
            for int_id in state.provided_integrations:
                if int_id in self.integrations:
                    integration = self.integrations.pop(int_id)
                    await integration.disconnect()

            state.instance = None
            state.module = None
            state.status = PluginStatus.UNLOADED

            return True

        except Exception as e:
            state.status = PluginStatus.ERROR
            state.error = str(e)
            return False

    async def reload_plugin(self, name: str) -> bool:
        """Hot-reload a plugin."""
        await self.unload_plugin(name)
        return await self.load_plugin(name)

    def get_skill(self, skill_id: str) -> Optional[Skill]:
        return self.skills.get(skill_id)

    def list_skills(self, category: str = None) -> List[Skill]:
        skills = list(self.skills.values())
        if category:
            skills = [s for s in skills if s.category == category]
        return skills

    def get_integration(self, integration_id: str) -> Optional[Integration]:
        return self.integrations.get(integration_id)

    async def execute_skill(self, skill_id: str, parameters: Dict[str, Any]) -> Any:
        """Execute a skill."""
        skill = self.skills.get(skill_id)
        if not skill:
            raise ValueError(f"Skill not found: {skill_id}")

        prompt = skill.render_prompt(parameters)
        return {
            "skill_id": skill.skill_id,
            "prompt": prompt,
            "tools": skill.tools,
        }


# =============================================================================
# Plugin Discovery
# =============================================================================

class PluginDiscovery:
    """Discover plugins from filesystem."""

    def __init__(self, plugin_dirs: List[Path] = None):
        self.plugin_dirs = plugin_dirs or [
            Path("plugins"),
            Path.cwd() / ".beast" / "plugins",
            Path.home() / ".beast" / "plugins",
        ]

    def discover(self) -> List[PluginMetadata]:
        """Discover all plugins."""
        plugins = []
        for plugin_dir in self.plugin_dirs:
            if not plugin_dir.exists():
                continue
            for plugin_file in plugin_dir.glob("**/*.beast-plugin.json"):
                try:
                    with open(plugin_file) as f:
                        data = json.load(f)
                    metadata = PluginMetadata(**data)
                    plugins.append(metadata)
                except Exception as e:
                    print(f"Failed to load plugin {plugin_file}: {e}")
        return plugins

    def discover_python_plugins(self, package: str = "app.kernel.agents.plugins") -> List[PluginMetadata]:
        """Discover plugins from Python packages."""
        plugins = []
        try:
            module = importlib.import_module(package)
            for _, name, is_pkg in pkgutil.iter_modules(module.__path__):
                if is_pkg:
                    try:
                        plugin_module = importlib.import_module(f"{package}.{name}")
                        metadata = getattr(plugin_module, "PLUGIN_METADATA", None)
                        if metadata:
                            plugins.append(PluginMetadata(**metadata))
                    except Exception:
                        pass
        except Exception:
            pass
        return plugins


# =============================================================================
# Plugin Manager (High-level API)
# =============================================================================

class PluginManager:
    """High-level plugin management."""

    def __init__(self, agent: Any, plugin_dirs: List[Path] = None):
        self.agent = agent
        self.plugin_agent = PluginAgent(agent)
        self.discovery = PluginDiscovery()
        self._auto_load = True

    async def initialize(self) -> None:
        """Initialize plugin system."""
        # Discover plugins
        discovered = self.discovery.discover()
        for metadata in discovered:
            self.plugin_agent.register_plugin(metadata)

        # Auto-load enabled plugins
        if self._auto_load:
            await self.load_all()

    async def load_all(self) -> Dict[str, bool]:
        """Load all registered plugins."""
        results = {}
        for name in self.plugin_agent.plugins:
            results[name] = await self.plugin_agent.load_plugin(name)
        return results

    async def load_plugin(self, name: str) -> bool:
        return await self.plugin_agent.load_plugin(name)

    async def unload_plugin(self, name: str) -> bool:
        return await self.plugin_agent.unload_plugin(name)

    async def reload_plugin(self, name: str) -> bool:
        return await self.plugin_agent.reload_plugin(name)

    def get_skill(self, skill_id: str) -> Optional[Skill]:
        return self.plugin_agent.get_skill(skill_id)

    def list_skills(self, category: str = None) -> List[Skill]:
        return self.plugin_agent.list_skills(category)

    async def execute_skill(self, skill_id: str, parameters: Dict[str, Any]) -> Any:
        return await self.plugin_agent.execute_skill(skill_id, parameters)

    def get_status(self) -> Dict[str, Any]:
        return {
            "plugins": {
                name: {
                    "status": state.status.value,
                    "version": state.metadata.version,
                    "tools": state.provided_tools,
                    "skills": state.provided_skills,
                    "integrations": state.provided_integrations,
                    "error": state.error,
                }
                for name, state in self.plugin_agent.plugins.items()
            },
            "skills": {
                skill_id: {
                    "name": skill.name,
                    "category": skill.category,
                    "tools": skill.tools,
                }
                for skill_id, skill in self.plugin_agent.skills.items()
            },
            "integrations": {
                int_id: {
                    "name": integration.name,
                    "type": integration.integration_type,
                }
                for int_id, integration in self.plugin_agent.integrations.items()
            },
        }


# =============================================================================
# Built-in Plugins
# =============================================================================

# Example: Code Analysis Plugin
class CodeAnalysisPlugin(Plugin):
    """Plugin providing code analysis tools."""

    def get_tools(self) -> List[ToolSpec]:
        from app.kernel.agents.zod_schemas import ToolSpec, ToolRisk, ToolEffect, ExecutionTarget
        return [
            ToolSpec(
                tool_id="code.analyze_complexity",
                title="Analyze Code Complexity",
                description="Analyze cyclomatic complexity of code",
                category="analysis",
                risk=ToolRisk.LOW,
                effect=ToolEffect.READ,
                input_schema={},
                targets=[ExecutionTarget.LOCAL],
            ),
            ToolSpec(
                tool_id="code.find_dependencies",
                title="Find Code Dependencies",
                description="Find import/dependency graph",
                category="analysis",
                risk=ToolRisk.LOW,
                effect=ToolEffect.READ,
                input_schema={},
                targets=[ExecutionTarget.LOCAL],
            ),
        ]

    def get_skills(self) -> List[Skill]:
        return [
            Skill(
                skill_id="analyze_codebase",
                name="Analyze Codebase",
                description="Comprehensive codebase analysis",
                prompt_template="Analyze the codebase at {{workspace_root}}. Focus on {{focus_area}}.",
                tools=["code.analyze_complexity", "code.find_dependencies"],
                category="analysis",
            ),
        ]


# Example: Testing Plugin
class TestingPlugin(Plugin):
    """Plugin providing testing tools."""

    def get_tools(self) -> List[ToolSpec]:
        from app.kernel.agents.zod_schemas import ToolSpec, ToolRisk, ToolEffect, ExecutionTarget
        return [
            ToolSpec(
                tool_id="test.run_unit",
                title="Run Unit Tests",
                description="Run unit tests for specified files",
                category="testing",
                risk=ToolRisk.MEDIUM,
                effect=ToolEffect.EXECUTE,
                input_schema={},
                targets=[ExecutionTarget.LOCAL, ExecutionTarget.CONTAINER],
                requires_approval=True,
            ),
        ]

    def get_skills(self) -> List[Skill]:
        return [
            Skill(
                skill_id="run_tests",
                name="Run Tests",
                description="Run tests for changed files",
                prompt_template="Run tests for {{files}}. Report failures.",
                tools=["test.run_unit"],
                category="testing",
            ),
        ]


# =============================================================================
# Plugin Registry (Built-in)
# =============================================================================

BUILTIN_PLUGINS: Dict[str, Type[Plugin]] = {
    "code_analysis": CodeAnalysisPlugin,
    "testing": TestingPlugin,
}


def create_plugin_manager(agent: Any, plugin_dirs: List[Path] = None) -> PluginManager:
    """Create plugin manager with built-in plugins."""
    manager = PluginManager(agent, plugin_dirs=[])

    # Register built-in plugins
    for name, plugin_class in BUILTIN_PLUGINS.items():
        metadata = PluginMetadata(
            name=name,
            version="1.0.0",
            description=f"Built-in {name} plugin",
            plugin_type=PluginType.TOOL,
            entry_point=f"app.kernel.agents.plugin_system.{plugin_class.__name__}",
        )
        config = PluginConfig(enabled=True)
        manager.plugin_agent.register_plugin(metadata, config)

    return manager


async def load_all_beast_plugins(plugin_agent: "PluginAgent") -> Dict[str, bool]:
    """Load all BEAST plugins (old format, IDE extensions, built-in)."""
    loader = UnifiedPluginLoader(plugin_agent)
    return await loader.load_all(
        old_plugins_dir=Path("plugins"),
        ide_extensions_dir=Path("desktop-ide/extensions"),
    )


# =============================================================================
# Export
# =============================================================================

__all__ = [
    "Plugin",
    "Skill",
    "Integration",
    "PluginMetadata",
    "PluginConfig",
    "PluginState",
    "PluginStatus",
    "PluginType",
    "PluginAgent",
    "PluginManager",
    "PluginDiscovery",
    "Skill",
    "Integration",
    "CodeAnalysisPlugin",
    "TestingPlugin",
    "BUILTIN_PLUGINS",
    "create_plugin_manager",
    "load_all_beast_plugins",
]
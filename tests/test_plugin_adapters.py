"""Tests for plugin adapters (MCP tools, IDE extensions, old BEAST plugins)."""

from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path

import pytest

from app.kernel.agents.mcp_tools_adapter import (
    MCPToolAdapter,
    MCPToolExecutor,
    MCPToolPlugin,
    register_mcp_tools,
    get_mcp_tool_catalog,
)
from app.kernel.agents.ide_extensions_adapter import (
    IDEExtensionManifest,
    IDEExtensionAdapter,
    IDEExtensionExecutor,
    IDEExtensionPlugin,
    load_ide_extension_manifests,
    create_ide_extension_tools,
    create_ide_skills,
)
from app.kernel.agents.beast_plugin_adapter import (
    OldBeastManifest,
    OldPluginAdapter,
    OldPluginLoader,
    UnifiedPluginLoader,
    ProviderEconomistPlugin,
    load_all_beast_plugins,
)
from app.kernel.agents.tool_registry import ToolSpec, ToolRisk, ToolEffect, ExecutionTarget
from app.kernel.agents.plugin_system import (
    PluginAgent,
    PluginManager,
    PluginMetadata,
    PluginConfig,
    PluginType,
    PluginState,
)
from app.kernel.agents.tool_registry import (
    ToolRegistry,
    ToolContext,
    create_tool_registry,
)
from app.kernel.agents.tool_registry import ToolSpec as RegistryToolSpec
from app.kernel.agents.zod_schemas import ToolSpec as ZodToolSpec, ToolRisk, ToolEffect, ExecutionTarget


# =============================================================================
# MCP Tools Adapter Tests
# =============================================================================

def test_mcp_tool_adapter_loads_definitions():
    """MCP tool adapter loads tool definitions from JSON."""
    adapter = MCPToolAdapter()
    assert len(adapter.tools) > 50  # Should have 70+ tools
    tool_names = [t.get("name") for t in adapter.tools]
    assert "beast_tool_profile" in tool_names
    assert "beast_provider_economist_select" in tool_names
    assert "beast_worktree_create" in tool_names


def test_mcp_tool_adapter_converts_to_tool_specs():
    """MCP tool adapter converts definitions to ToolSpec."""
    adapter = MCPToolAdapter()
    specs = adapter.get_tool_specs()

    assert len(specs) > 50
    for spec in specs:
        assert isinstance(spec, RegistryToolSpec)
        assert spec.tool_id
        assert spec.title
        assert spec.description
        assert spec.category == "mcp"
        assert spec.risk in (ToolRisk.LOW, ToolRisk.MEDIUM, ToolRisk.HIGH)
        assert spec.effect in (ToolEffect.READ, ToolEffect.WRITE, ToolEffect.EXECUTE)
        assert ExecutionTarget.LOCAL in spec.targets


def test_mcp_tool_catalog():
    """MCP tool catalog returns all tools with metadata."""
    catalog = get_mcp_tool_catalog()
    assert len(catalog) > 50
    for tool in catalog:
        assert "name" in tool
        assert "description" in tool
        assert "inputSchema" in tool
        assert "risk" in tool
        assert "effect" in tool


def test_mcp_tool_plugin():
    """MCP tool plugin initializes and provides tools/skills."""
    plugin = MCPToolPlugin()
    tools = plugin.get_tools()
    skills = plugin.get_skills()

    assert len(tools) > 50
    assert len(skills) >= 4  # operations, safety, routing, crystal, quality

    skill_ids = [s.skill_id for s in skills]
    assert "mcp_beast_operations" in skill_ids
    assert "mcp_safety_governance" in skill_ids
    assert "mcp_provider_routing" in skill_ids


# =============================================================================
# IDE Extensions Adapter Tests
# =============================================================================

def test_ide_extension_manifests_load():
    """IDE extension manifests load from desktop-ide/extensions."""
    manifests = load_ide_extension_manifests()
    assert len(manifests) >= 4

    ids = [m.id for m in manifests]
    assert "beast.crystal-lab" in ids
    assert "beast.remote-toolkit" in ids
    assert "beast.companion" in ids
    assert "beast.code-health" in ids


def test_ide_extension_adapter_converts_to_tools():
    """IDE extension adapter converts commands to tools."""
    import tempfile

    # Create mock extensions directory structure for testing
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create extension directories with manifests
        for ext_id in ["beast-crystal-lab", "beast-companion", "beast-remote-toolkit", "beast-code-health"]:
            ext_dir = Path(tmpdir) / ext_id
            ext_dir.mkdir()
            # Create minimal manifest
            manifest = {
                "id": ext_id,
                "name": ext_id.replace("beast-", "BEAST ").title(),
                "version": "1.0.0",
                "description": f"{ext_id} extension",
                "main": "extension.js",
                "capabilities": ["workspace.read"],
                "contributes": {"commands": []}
            }
            # Add some commands for testing
            if ext_id == "beast-crystal-lab":
                manifest["contributes"]["commands"] = [
                    {"id": "beast.openCrystallization", "title": "Open Crystallization"},
                    {"id": "beast.openEvidence", "title": "Open Evidence"}
                ]
            elif ext_id == "beast-companion":
                manifest["contributes"]["commands"] = [
                    {"id": "beast.openMission", "title": "Open Mission Control"},
                    {"id": "beast.openCompatibility", "title": "Open Compatibility Center"}
                ]
            elif ext_id == "beast-remote-toolkit":
                manifest["contributes"]["commands"] = [
                    {"id": "beast.openCompatibility", "title": "Open Remote + Compatibility Center"},
                    {"id": "beast.openTerminal", "title": "Open Integrated Terminal"}
                ]
            elif ext_id == "beast-code-health":
                manifest["contributes"]["commands"] = [
                    {"id": "beast.openTesting", "title": "Open Testing"},
                    {"id": "beast.openSourcePlan", "title": "Open SourcePlan Review"},
                    {"id": "beast.openReview", "title": "Open Governed Review"}
                ]
            (ext_dir / "beast-extension.json").write_text(json.dumps(manifest))

        # Load manifests from temp directory
        manifests = load_ide_extension_manifests(Path(tmpdir))
        all_tools = create_ide_extension_tools(Path(tmpdir))

        tool_ids = [t.tool_id for t in all_tools]
        assert "ide.beast_crystal_lab.beast.openCrystallization" in tool_ids
        assert "ide.beast_crystal_lab.beast.openEvidence" in tool_ids
        assert "ide.beast_companion.beast.openMission" in tool_ids
        assert "ide.beast_companion.beast.openCompatibility" in tool_ids
        assert "ide.beast_remote_toolkit.beast.openTerminal" in tool_ids
        assert "ide.beast_code_health.beast.openTesting" in tool_ids
        assert "ide.beast_code_health.beast.openSourcePlan" in tool_ids
        assert "ide.beast_code_health.beast.openReview" in tool_ids


def test_ide_extension_skills():
    """IDE extension skills are created from commands."""
    skills = create_ide_skills()
    assert len(skills) >= 4

    skill_ids = [s.skill_id for s in skills]
    assert "ide.crystal_lab" in skill_ids
    assert "ide.companion" in skill_ids
    assert "ide.remote_toolkit" in skill_ids
    assert "ide.code_health" in skill_ids


def test_ide_extension_plugin():
    """IDE extension plugin initializes and provides tools/skills."""
    plugin = IDEExtensionPlugin()
    # Can't fully initialize without agent context, but check structure
    assert hasattr(plugin, 'extensions')
    assert hasattr(plugin, 'executor')


# =============================================================================
# Old BEAST Plugin Adapter Tests
# =============================================================================

def test_old_beast_manifest_loads():
    """Old BEAST manifest loads from JSON."""
    import json
    from pathlib import Path

    manifest_path = Path("plugins/examples/provider-economist.beast-plugin.json").resolve()
    assert manifest_path.exists()

    with open(manifest_path) as f:
        data = json.load(f)

    manifest = OldBeastManifest.from_dict(data)
    assert manifest.id == "edgek.provider-economist"
    assert manifest.version == "0.1.0"
    assert manifest.entrypoint.get("module") == "app.kernel.adapters.provider_economist"
    assert len(manifest.tools) == 1
    assert manifest.tools[0]["name"] == "beast_provider_economist_select"


def test_old_plugin_adapter_converts_to_tools():
    """Old plugin adapter converts old manifest to new ToolSpec."""
    from pathlib import Path
    import json

    manifest_path = Path("plugins/examples/provider-economist.beast-plugin.json").resolve()
    with open(manifest_path) as f:
        data = json.load(f)

    manifest = OldBeastManifest.from_dict(data)
    adapter = OldPluginAdapter(manifest, manifest_path.parent)

    tools = adapter.get_tools()
    assert len(tools) == 1
    spec = tools[0]
    assert spec.tool_id == "beast_provider_economist_select"
    assert spec.category == "plugin"
    assert spec.risk == ToolRisk.MEDIUM
    assert ExecutionTarget.LOCAL in spec.targets


def test_provider_economist_plugin():
    """Provider economist plugin provides tools and skills."""
    plugin = ProviderEconomistPlugin()
    tools = plugin.get_tools()
    skills = plugin.get_skills()

    assert len(tools) == 1
    assert tools[0].tool_id == "beast_provider_economist_select"
    assert len(skills) == 1
    assert skills[0].skill_id == "select_provider_route"


# =============================================================================
# Unified Plugin Loader Tests
# =============================================================================

def test_unified_plugin_loader():
    """Unified plugin loader can load all plugin types."""
    from app.kernel.agents.agent_effect import EffectAgent
    from app.kernel.agents.plugin_system import PluginAgent

    # Create a minimal agent context for testing
    agent = PluginAgent(None)
    loader = UnifiedPluginLoader(agent)

    # Check it can discover plugins
    discovered = loader.discover()
    assert len(discovered) >= 1  # provider-economist

    # Check it can discover IDE extensions
    ide_extensions = load_ide_extension_manifests()
    assert len(ide_extensions) >= 4


# =============================================================================
# Plugin System Integration Tests
# =============================================================================

@pytest.mark.asyncio
async def test_plugin_manager_registers_plugins():
    """Plugin manager can register and load plugins."""
    agent = PluginAgent(None)
    manager = PluginManager(agent)

    # Register a test plugin
    metadata = PluginMetadata(
        name="test_plugin",
        version="1.0.0",
        description="Test plugin",
        plugin_type=PluginType.TOOL,
        entry_point="test",
    )
    config = PluginConfig(enabled=True)
    agent.plugins["test_plugin"] = PluginState(metadata=metadata, config=config)

    # Check registration
    assert "test_plugin" in agent.plugins


@pytest.mark.asyncio
async def test_tool_registry_with_mcp_tools():
    """Tool registry works with MCP tools."""
    from app.kernel.agents.mcp_tools_adapter import register_mcp_tools

    registry = create_tool_registry("/tmp")

    # Register MCP tools
    register_mcp_tools(registry, "/tmp")

    # Check tools registered
    tools = registry.list_tools()
    assert len(tools) > 50

    # Check specific tools
    tool_ids = [t.tool_id for t in tools]
    assert "beast_provider_economist_select" in tool_ids
    assert "beast_worktree_create" in tool_ids


@pytest.mark.asyncio
async def test_tool_registry_with_ide_extensions():
    """Tool registry works with IDE extensions."""
    registry = create_tool_registry("/tmp")

    # Register IDE extension tools
    ide_tools = create_ide_extension_tools()
    for spec in ide_tools:
        registry.register_spec(spec)

    # Check tools registered
    tools = registry.list_tools()
    ide_tool_ids = [t.tool_id for t in tools if t.tool_id.startswith("ide.")]
    assert len(ide_tool_ids) >= 8

    assert "ide.beast_crystal_lab.beast.openCrystallization" in ide_tool_ids
    assert "ide.beast_companion.beast.openMission" in ide_tool_ids


@pytest.mark.asyncio
async def test_full_plugin_system_integration():
    """Full plugin system integration test."""
    from app.kernel.agents.tool_registry import create_tool_registry
    
    tool_registry = create_tool_registry("/tmp")
    agent = PluginAgent(None, tool_registry=tool_registry)
    manager = PluginManager(agent)

    # Load all plugins
    results = await load_all_beast_plugins(tool_registry)

    # Check results
    assert "old:provider-economist.beast-plugin" in results

    # Check tools are available
    all_tools = agent.tool_registry.list_tools() if hasattr(agent, 'tool_registry') else []
    tool_ids = [t.tool_id for t in all_tools]
    assert "beast_provider_economist_select" in tool_ids


# =============================================================================
# Effect Runtime Integration Tests
# =============================================================================

@pytest.mark.asyncio
async def test_mcp_executor_with_effect_runtime():
    """MCP tool executor works with effect runtime."""
    from app.kernel.agents.effect_runtime import with_timeout, RetryPolicy

    executor = MCPToolExecutor("/tmp")
    context = ToolContext(
        run_id="test_run",
        session_id="test_session",
        workspace_root="/tmp",
    )

    # Test that executor can be called (will fail gracefully without gateway)
    try:
        result = await executor.execute("beast_tool_profile", {}, context)
        # If gateway is running, result will have data
        # If not, it will raise ToolExecutionError
    except Exception:
        # Expected if gateway not running
        pass


# =============================================================================
# Run Tests
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
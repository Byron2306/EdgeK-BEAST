from __future__ import annotations

import pytest

from app.kernel.agents.run_engine import AgentRunEngine
from app.kernel.agents.tool_runtime import build_default_tool_registry


def test_canonical_registry_keeps_beast_and_schema_catalogs_in_lockstep(tmp_path):
    from app.kernel.agents.canonical_tool_registry import CanonicalToolRegistry

    registry = CanonicalToolRegistry.from_agent_registry(
        build_default_tool_registry(),
        workspace_root=tmp_path,
    )

    beast_ids = {item["tool_id"] for item in registry.list()}
    schema_ids = {item.tool_id for item in registry.effect_registry.list_tools()}

    assert "workspace.read_range" in beast_ids
    assert "worktree.replace_exact" in beast_ids
    assert beast_ids == schema_ids


def test_canonical_registry_schema_rejects_unknown_arguments(tmp_path):
    from app.kernel.agents.canonical_tool_registry import CanonicalToolRegistry

    registry = CanonicalToolRegistry.from_agent_registry(
        build_default_tool_registry(),
        workspace_root=tmp_path,
    )
    spec = registry.get("workspace.read_range")

    with pytest.raises(ValueError, match="unknown|additional|unexpected"):
        registry.validate_arguments(
            spec,
            {"path": "app.py", "start_line": 1, "line_count": 5, "invented": True},
        )


def test_agent_run_engine_exposes_the_canonical_registry(tmp_path):
    from app.kernel.agents.canonical_tool_registry import CanonicalToolRegistry

    engine = AgentRunEngine(tmp_path)

    assert isinstance(engine.tool_registry, CanonicalToolRegistry)
    assert engine.tool_registry.effect_registry.get("workspace.index").handler is not None


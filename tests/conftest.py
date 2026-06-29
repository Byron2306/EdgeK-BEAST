"""Shared pytest configuration for BEAST tests."""

from __future__ import annotations

import pytest
from pathlib import Path
from app.kernel.compute.factory import ServiceFactory

# Initialize services at module level to run before test collection
ServiceFactory.initialize()

ROOT = Path(__file__).resolve().parents[1]


CLI_FILES = {
    "test_beast_cli_script.py",
}

MCP_FILES = {
    "test_mcp.py",
    "test_mcp_broker.py",
    "test_mcp_proper.py",
    "test_mcp_runtime_v2.py",
}

MANUAL_FILES = {
    "test_diagnose_huggingface.py",
    "test_mcp.py",
    "test_mcp_proper.py",
}

SEMANTIC_FILES = {
    "test_workspace_graph.py",
    "test_workspace_reasoning.py",
}

INTEGRATION_FILES = {
    "test_deployment_manager.py",
    "test_enterprise_mode.py",
    "test_huggingface_litellm_adapters.py",
    "test_os_bypass.py",
    "test_tool_integrations.py",
}

API_HINTS = (
    "ASGITransport",
    "TestClient",
    "AsyncClient",
)


def pytest_collection_modifyitems(config, items):
    for item in items:
        path = Path(str(item.fspath))
        name = path.name
        text = path.read_text(encoding="utf-8", errors="ignore")

        if "tests/benchmarks" in str(path):
            item.add_marker(pytest.mark.benchmark)
            continue

        if name in CLI_FILES:
            item.add_marker(pytest.mark.cli)
        elif name in MCP_FILES:
            item.add_marker(pytest.mark.mcp)
        elif name in MANUAL_FILES:
            item.add_marker(pytest.mark.manual)
        elif name in SEMANTIC_FILES:
            item.add_marker(pytest.mark.semantic)
        elif name in INTEGRATION_FILES:
            item.add_marker(pytest.mark.integration)
        elif any(hint in text for hint in API_HINTS):
            item.add_marker(pytest.mark.api)
        else:
            item.add_marker(pytest.mark.unit)

        if name in MANUAL_FILES:
            item.add_marker(pytest.mark.manual)

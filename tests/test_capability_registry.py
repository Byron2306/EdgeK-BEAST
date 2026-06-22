import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.kernel.capability_registry import CapabilityRegistry


def test_capability_registry_surfaces_core_families():
    registry = CapabilityRegistry(
        policies={
            "providers": {
                "openai": {
                    "enabled": True,
                    "base_url": "https://api.openai.com/v1",
                    "backend": "openai",
                    "env": "OPENAI_API_KEY",
                }
            }
        }
    )

    inventory = registry.list_capabilities()
    kinds = inventory["kinds"]
    ids = {item["capability_id"] for item in inventory["capabilities"]}

    assert inventory["beast_object_type"] == "capability_inventory"
    assert {"provider", "tool", "cli", "mcp_tool", "workflow", "route", "parser", "linter", "database", "plugin", "skill"} <= set(kinds)
    assert {"agentic_cli", "debugging", "lint_syntax", "parsing", "tool_bus", "vector"} <= set(inventory["families"])
    assert "provider:openai" in ids
    assert "workflow:handoff_prepare" in ids
    assert "workflow:chronicle_publish" in ids
    assert "workflow:prec_lifecycle" in ids
    assert "tool:semantic_interceptor" in ids
    assert "cli:diagnose" in ids
    assert "cli:openclaw_plan" in ids
    assert "mcp_tool:beast_openclaw_plan" in ids
    assert "tool:pytest_failure_parser" in ids
    assert "database:sqlite_local_embeddings" in ids

    openai = next(item for item in inventory["capabilities"] if item["capability_id"] == "provider:openai")
    assert openai["metadata"]["backend"] == "openai_compatible"
    assert openai["metadata"]["proxy_path"] == "/proxy/openai"


def test_capability_registry_filters_by_kind():
    inventory = CapabilityRegistry().list_capabilities(kind="workflow")

    assert inventory["count"] >= 1
    assert set(inventory["kinds"]) == {"workflow"}
    assert all(item["kind"] == "workflow" for item in inventory["capabilities"])


def test_capability_registry_rolls_up_families():
    families = CapabilityRegistry().list_families()

    assert families["beast_object_type"] == "capability_family_inventory"
    assert "agentic_cli" in families["families"]
    assert "cli:zeroclaw_plan" in families["families"]["agentic_cli"]["capability_ids"]
    assert "debugging" in families["families"]
    assert "workflow:test_failure_cascade" in families["families"]["debugging"]["capability_ids"]


def test_capability_registry_exports_commons_discovery_sources():
    sources = CapabilityRegistry().discovery_sources()

    assert sources["beast_object_type"] == "capability_registry_discovery_sources"
    assert sources["source_count"] == 2
    by_id = {source["source_id"]: source for source in sources["sources"]}
    assert "beast_capability_registry" in by_id
    assert "open_source_mcp_seed_catalog" in by_id
    registry_names = {item["tool_id"] for item in by_id["beast_capability_registry"]["items"]}
    mcp_names = {item["name"] for item in by_id["open_source_mcp_seed_catalog"]["items"]}
    assert "workflow:quality_cascade" in registry_names
    assert "mcp_filesystem_read" in mcp_names
    assert "mcp_playwright_inspect" in mcp_names
    assert all(item["risk_class"] in {"low", "medium", "high", "critical"} for source in sources["sources"] for item in source["items"])


@pytest.mark.asyncio
async def test_capability_family_endpoint():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/edgek/capabilities/families")
        discovery = await client.get("/edgek/capabilities/discovery-sources")
        vectors = await client.get("/edgek/vector/adapters")

    assert response.status_code == 200
    assert response.json()["beast_object_type"] == "capability_family_inventory"
    assert "tool_bus" in response.json()["families"]
    assert discovery.status_code == 200
    assert discovery.json()["beast_object_type"] == "capability_registry_discovery_sources"
    assert vectors.status_code == 200
    assert vectors.json()["beast_object_type"] == "vector_adapter_inventory"
    assert vectors.json()["active_adapter"] == "sqlite_local_embeddings"

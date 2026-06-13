import pytest
from httpx import ASGITransport, AsyncClient

from app.kernel.tool_integrations import RequiredIntegrationRegistry, ToolCallInterceptor
from app.kernel.deployment import DeploymentManager
from app.mcp.broker import MCPBroker, MCPDecision
from app.main import app


POLICIES = {
    "required_integrations": {
        "semantic_tool_interceptor": {"kind": "local", "required": True},
        "github": {"kind": "api", "required": True, "env": "GITHUB_TOKEN"},
        "postgres": {"kind": "database", "required": True, "env": "POSTGRES_DSN"},
        "rtk": {"kind": "compressor", "required": True, "binary": "rtk"},
        "sqz": {"kind": "compressor", "required": True, "binary": "sqz"},
        "longcodezip": {"kind": "compressor", "required": True, "binary": "longcodezip"},
        "reporelay": {"kind": "repository", "required": True, "binary": "reporelay"},
    },
    "mcp_server_classes": {
        "local_read_only": {"trust_level": "low", "requires_approval": False, "budget_multiplier": 1.0},
        "github": {"trust_level": "medium_high", "requires_approval": True, "budget_multiplier": 2.5},
        "postgres": {"trust_level": "high", "requires_approval": True, "budget_multiplier": 4.0},
        "token_compressor": {"trust_level": "low", "requires_approval": False, "budget_multiplier": 0.35},
    },
    "file_operations": {"blocked_patterns": [], "approval_required_patterns": [], "safe_read_patterns": ["**/*"]},
}


def test_required_integrations_surface_reports_not_ready(monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("POSTGRES_DSN", raising=False)
    status = RequiredIntegrationRegistry(POLICIES).status()

    names = {item["name"] for item in status["required_integrations"]}
    assert {"semantic_tool_interceptor", "github", "postgres", "rtk", "sqz", "longcodezip", "reporelay"} <= names
    github = next(item for item in status["required_integrations"] if item["name"] == "github")
    assert github["ready"] is bool(github["detail"].get("gh_auth_present"))
    postgres = next(item for item in status["required_integrations"] if item["name"] == "postgres")
    assert postgres["ready"] is bool(postgres["detail"].get("env_present") or postgres["detail"].get("ready"))


def test_file_read_interceptor_returns_top_three_relevant_paragraphs(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    source = workspace / "service.py"
    source.write_text(
        "\n\n".join([
            "def auth_login():\n    return 'token login session'",
            "def billing_invoice():\n    return 'invoice payment'",
            "def auth_refresh():\n    return 'refresh token session'",
            "def telemetry_packet():\n    return 'sensor frame'",
            "def auth_logout():\n    return 'logout token session'",
        ]),
        encoding="utf-8",
    )

    result = ToolCallInterceptor().intercept_read_file(
        {
            "tool_name": "read_file",
            "target": "service.py",
            "query": "auth token session",
            "limit": 3,
        },
        workspace_root=str(workspace),
    )

    assert result["intercepted"] is True
    assert result["backend"] == "basic_semantic_grep"
    assert len(result["snippets"]) == 3
    assert "billing_invoice" not in result["content"]
    assert result["bytes_returned"] < result["raw_bytes"]


def test_mcp_understands_github_postgres_and_token_compressor(tmp_path, monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    broker = MCPBroker(POLICIES, db_path=str(tmp_path / "mcp.db"))

    github = broker.evaluate({"tool_name": "github_get_repo", "repo": "owner/name"}, audit=False)
    postgres = broker.evaluate({"tool_name": "postgres_query", "query": "select 1"}, audit=False)
    compressor = broker.execute({"tool_name": "rtk", "server_class": "token_compressor", "text": "a\n\n\na\nb\nb"})

    assert github.server_class == "github"
    assert github.decision == MCPDecision.REQUIRE_APPROVAL
    assert postgres.server_class == "postgres"
    assert postgres.decision == MCPDecision.REQUIRE_APPROVAL
    assert compressor["executed"] is True
    assert compressor["server_class"] == "token_compressor"
    assert compressor["backend"] == "edgek_builtin_prune"


def test_deployment_config_routes_tool_call_interception():
    manager = DeploymentManager(POLICIES)
    litellm = manager.generate_litellm_config(beast_base_url="http://beast.local")
    nginx = manager.generate_nginx_config()

    assert litellm["edgek_beast"]["tool_call_interception"] == "http://beast.local/edgek/tools/intercept"
    assert "edgek_tool_interceptor" in litellm["mcp_servers"]
    assert "/tool-calls/" in nginx
    assert "tool-intercept" in nginx


@pytest.mark.asyncio
async def test_tool_intercept_and_integration_endpoints():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        integrations = await client.get("/edgek/tools/integrations")
        compressed = await client.post("/edgek/compression/prune", json={"text": "x\n\nx\ny", "algorithm": "sqz"})

    assert integrations.status_code == 200
    assert "required_integrations" in integrations.json()
    assert compressed.status_code == 200
    assert compressed.json()["mode"] == "token_pruning"

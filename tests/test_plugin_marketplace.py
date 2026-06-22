from app.kernel.plugin_marketplace import PluginMarketplace
from app.mcp.broker import MCPBroker


def sample_manifest():
    return {
        "beast_plugin_manifest_version": "1.0",
        "id": "example.route-helper",
        "name": "Route Helper",
        "version": "0.1.0",
        "publisher": "example",
        "description": "Read-only route helper.",
        "risk_class": "medium",
        "entrypoint": {"kind": "python", "module": "route_helper"},
        "tools": [{
            "name": "route_recommend",
            "description": "Recommend a route.",
            "inputSchema": {
                "type": "object",
                "properties": {"role": {"type": "string"}},
                "required": ["role"],
            },
        }],
        "permissions": {
            "filesystem_read": ["benchmarks/results"],
            "filesystem_write": [],
            "network_domains": [],
            "environment": [],
            "subprocess": False,
        },
        "budget": {
            "max_tokens_per_call": 2000,
            "max_cost_usd_per_call": 0.01,
            "max_latency_ms": 5000,
            "calls_per_hour": 100,
        },
        "approval_policy": {
            "install": True,
            "first_run": True,
            "network": False,
            "external_write": False,
            "filesystem_write": False,
        },
    }


def test_marketplace_prepares_and_validates_schema_pins(tmp_path):
    marketplace = PluginMarketplace(str(tmp_path / "plugins"))
    manifest = marketplace.prepare(sample_manifest())

    validation = marketplace.validate(manifest)

    assert validation["valid"] is True
    assert manifest["tools"][0]["tool_schema_hash"].startswith("sha256:")
    assert validation["tool_schema_pins"][0]["matched"] is True
    assert validation["requires_install_approval"] is True


def test_marketplace_hash_matches_mcp_broker_canonical_hashing(tmp_path):
    marketplace = PluginMarketplace(str(tmp_path / "plugins"))
    broker = MCPBroker(db_path=str(tmp_path / "broker.db"))
    tool = sample_manifest()["tools"][0]
    canonical = {
        "name": tool["name"],
        "description": tool["description"],
        "inputSchema": tool["inputSchema"],
    }

    assert marketplace.tool_schema_hash(tool) == "sha256:" + broker._compute_tool_schema_hash(canonical)


def test_marketplace_rejects_tampered_tool_schema(tmp_path):
    marketplace = PluginMarketplace(str(tmp_path / "plugins"))
    manifest = marketplace.prepare(sample_manifest())
    manifest["tools"][0]["inputSchema"]["properties"]["budget"] = {"type": "number"}

    validation = marketplace.validate(manifest)

    assert validation["valid"] is False
    assert "tools[0] schema hash mismatch" in validation["errors"]


def test_marketplace_enforces_permission_risk_and_approval_coherence(tmp_path):
    marketplace = PluginMarketplace(str(tmp_path / "plugins"))
    manifest = sample_manifest()
    manifest["risk_class"] = "low"
    manifest["permissions"]["network_domains"] = ["api.example.com"]
    manifest["approval_policy"]["network"] = False
    manifest = marketplace.prepare(manifest)

    validation = marketplace.validate(manifest)

    assert validation["valid"] is False
    assert "plugins with network access cannot use low risk_class" in validation["errors"]
    assert "network permission requires approval_policy.network=true" in validation["errors"]


def test_marketplace_install_is_dry_run_and_approval_gated(tmp_path):
    marketplace = PluginMarketplace(str(tmp_path / "plugins"))
    manifest = marketplace.prepare(sample_manifest())

    dry = marketplace.install(manifest)
    unapproved = marketplace.install(manifest, approved=False, dry_run=False)
    live = marketplace.install(manifest, approved=True, dry_run=False)
    inventory = marketplace.list_installed()

    assert dry["installed"] is False
    assert unapproved["installed"] is False
    assert live["installed"] is True
    assert inventory["count"] == 1
    assert inventory["plugins"][0]["id"] == "example.route-helper"


def test_marketplace_rejects_unapproved_install_policy_and_mismatched_entrypoint(tmp_path):
    marketplace = PluginMarketplace(str(tmp_path / "plugins"))
    manifest = sample_manifest()
    manifest["approval_policy"]["install"] = False
    manifest["entrypoint"] = {"kind": "mcp_stdio", "command": "python"}
    manifest = marketplace.prepare(manifest)

    validation = marketplace.validate(manifest)

    assert validation["valid"] is False
    assert "BEAST host policy requires approval_policy.install=true" in validation["errors"]
    assert "mcp_stdio entrypoint requires permissions.subprocess=true" in validation["errors"]
    assert "mcp_stdio entrypoint requires high or critical risk_class" in validation["errors"]

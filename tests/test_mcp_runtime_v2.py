from app.mcp.runtime import BeastToolRuntime
from app.kernel.data_processing.tool_laziness import ToolLazinessLearner
from app.kernel.data_processing.tool_laziness_plugin import ToolLazinessPlugin
from app.kernel.deployment.plugin_marketplace import PluginMarketplace
from app.kernel.storage.outcome_evidence import NegativeCapabilityStore


def test_runtime_exposes_v2_mcp_tools():
    runtime = BeastToolRuntime()
    names = {tool["name"] for tool in runtime.tool_definitions()}

    assert "beast_build_context_packet" in names
    assert "beast_sourceplan_prepare" in names
    assert "beast_sourceplan_preview_hunks" in names
    assert "beast_sourceplan_apply_selected" in names
    assert "beast_provider_fitness" in names
    assert "beast_provider_economist_select" in names
    assert "beast_tool_laziness_record" in names
    assert "beast_tool_laziness_recommend" in names
    assert "beast_otel_export" in names
    assert "beast_plugin_manifest_validate" in names
    assert "beast_plugin_marketplace_install" in names
    assert "beast_session_handshake" in names
    assert "beast_capability_exchange" in names
    assert "beast_run_maintenance_cascade" in names
    assert "beast_attach_network_chronicle" in names
    assert "beast_github_pr_ingest" in names
    assert "beast_github_pr_publish_chronicle" in names
    assert "beast_score_forge" in names
    assert "beast_plan_workflow" in names
    assert "beast_openclaw_plan" in names
    assert "beast_mcp_status" in names
    assert "beast_crystal_compute" in names


def test_crystal_compute_mcp_tool_exposes_failure_and_friction_state():
    runtime = BeastToolRuntime()
    runtime.crystal_compute_store = NegativeCapabilityStore()

    state = runtime.call_tool("beast_crystal_compute")

    assert state["phase1"] == "operational"
    assert state["phase2"] == "shadow"
    assert state["summary"]["outcomes"] == 0


def test_prepare_handoff_uses_current_context_packet_signature(tmp_path):
    runtime = BeastToolRuntime()
    envelope = runtime.call_tool(
        "beast_prepare_task",
        {
            "user_request": "Inspect app/main.py and prepare a bounded handoff",
            "task_class": "general_software_task",
            "dry_run": True,
        },
    )

    packet = runtime.call_tool(
        "beast_prepare_handoff",
        {
            "envelope": envelope,
            "provider": "local",
            "workspace_root": str(tmp_path),
            "max_tokens": 4096,
        },
    )

    assert packet["beast_object_type"] == "context_packet"
    assert packet["context_budget"]["max_tokens"] == 4096


def test_mcp_status_and_catalog_include_audit_metadata():
    runtime = BeastToolRuntime()

    status = runtime.call_tool("beast_mcp_status")
    catalog = runtime.call_tool("beast_mcp_tool_catalog")

    assert status["beast_object_type"] == "mcp_server_status"
    assert status["tools_registered"] == len(runtime.tool_definitions())
    assert status["audit_model"]["schema_pinning"] is True
    assert catalog["count"] == len(runtime.tool_definitions())
    assert any(tool["tool_id"] == "beast_openclaw_execute" for tool in catalog["tools"])
    laziness_record = next(tool for tool in catalog["tools"] if tool["tool_id"] == "beast_tool_laziness_record")
    economist = next(tool for tool in catalog["tools"] if tool["tool_id"] == "beast_provider_economist_select")
    assert laziness_record["idempotent"] is False
    assert laziness_record["risk"] == "persistent_write"
    assert economist["category"] == "governance"
    assert economist["required_trust_state"] == "trusted"
    exchange = next(tool for tool in catalog["tools"] if tool["tool_id"] == "beast_capability_exchange")
    assert exchange["idempotent"] is False
    assert exchange["risk"] == "gated_network_and_learning_write"


def test_openclaw_plan_tool_is_local_first():
    runtime = BeastToolRuntime()

    plan = runtime.call_tool(
        "beast_openclaw_plan",
        {
            "objective": "Plan a read-only inspection of app/main.py",
            "use_ollama": False,
        },
    )

    assert plan["beast_object_type"] == "beast_cli_plan"
    assert plan["mode"] == "openclaw"
    assert plan["profile"]["local_inference_first"] is True
    assert plan["session_handshake"]["beast_object_type"] == "beast_session_handshake"
    assert plan["preflight"]["beast_object_type"] == "beast_local_preflight"


def test_session_handshake_and_capability_exchange_mcp_tools():
    runtime = BeastToolRuntime()
    handshake = runtime.call_tool("beast_session_handshake", {
        "objective": "Use BEAST efficiently", "preflight_budget_ms": 100, "scout_budget_ms": 50,
    })
    evidence = runtime.call_tool("beast_capability_exchange", {
        "action": "prepare",
        "capability": {"capability_id": "tool.read", "kind": "tool", "version": "1"},
        "outcome": {"task_class": "coding", "role": "scout", "verified": True, "useful": True},
    })
    ranking = runtime.call_tool("beast_capability_exchange", {
        "action": "rank", "evidence": [evidence], "task_class": "coding", "role": "scout",
    })

    assert handshake["latency_budget"]["preflight_budget_ms"] == 100
    assert evidence["privacy"]["contains_source_code"] is False
    assert ranking["count"] == 1


def test_sourceplan_mcp_tools_prepare_and_preview(tmp_path, monkeypatch):
    target = tmp_path / "app.py"
    target.write_text("value = 'old'\n", encoding="utf-8")
    monkeypatch.setenv("BEAST_WORKSPACE", str(tmp_path))
    runtime = BeastToolRuntime()

    prepared = runtime.call_tool(
        "beast_sourceplan_prepare",
        {
            "objective": "Update app.py safely",
            "files": ["app.py"],
            "provider": "huggingface",
        },
    )
    preview = runtime.call_tool("beast_sourceplan_preview_hunks", {"plan": prepared["data"]})

    assert prepared["ok"] is True
    assert prepared["data"]["bridge_enforced"] is True
    assert prepared["data"]["provider_handoff_hash"].startswith("sha256:")
    assert preview["ok"] is True
    assert "diff" in preview["data"]


def test_provider_fitness_mcp_tool_returns_role_snapshot(tmp_path, monkeypatch):
    monkeypatch.setenv("BEAST_WORKSPACE", str(tmp_path))
    runtime = BeastToolRuntime()

    fitness = runtime.call_tool("beast_provider_fitness", {"limit": 10})

    assert fitness["beast_object_type"] == "provider_fitness_snapshot"
    assert "providers" in fitness
    assert "route_card_count" in fitness


def test_provider_economist_and_tool_laziness_mcp_plugins(tmp_path):
    runtime = BeastToolRuntime()
    learner = ToolLazinessLearner(db_path=str(tmp_path / "tools.db"))
    runtime.tool_laziness_learner = learner
    runtime.tool_laziness_plugin = ToolLazinessPlugin(learner)
    for _ in range(3):
        runtime.call_tool("beast_tool_laziness_record", {
            "tool_name": "web_search", "scenario": "local_import_fix",
            "useful": False, "tokens_spent": 100, "latency_ms": 500,
        })

    laziness = runtime.call_tool("beast_tool_laziness_recommend", {
        "candidate_tools": ["web_search", "read_file"],
        "scenario": "local_import_fix",
    })
    economist = runtime.call_tool("beast_provider_economist_select", {
        "requested_role": "primary_patch_provider",
        "candidates": [{
            "provider": "qwen", "recommended_role": "clean_patch_candidate",
            "hidden_clean_usd_per_fix": 0.001, "hidden_clean_rate": 0.2,
            "auth_confidence": 1.0, "avg_latency_ms": 1000,
        }],
    })

    assert laziness["tools_not_to_call"][0]["name"] == "web_search"
    assert economist["selected"]["provider"] == "qwen"


def test_otel_and_marketplace_mcp_plugins(tmp_path):
    runtime = BeastToolRuntime()
    runtime.plugin_marketplace = PluginMarketplace(str(tmp_path / "plugins"))
    otel = runtime.call_tool("beast_otel_export", {
        "chronicles": [{"task_id": "tsk_mcp", "provider": "local"}],
        "endpoint": "http://tempo:4318",
    })
    manifest = {
        "id": "example.mcp-test", "name": "MCP Test", "version": "0.1.0", "publisher": "tests",
        "risk_class": "low", "entrypoint": {"kind": "python", "module": "example"},
        "tools": [{"name": "example_read", "description": "Read example", "inputSchema": {"type": "object"}}],
        "permissions": {"filesystem_read": [], "filesystem_write": [], "network_domains": [], "environment": [], "subprocess": False},
        "budget": {"max_tokens_per_call": 100, "max_cost_usd_per_call": 0, "max_latency_ms": 1000, "calls_per_hour": 10},
        "approval_policy": {"install": True, "first_run": False, "network": False, "external_write": False, "filesystem_write": False},
    }
    validation = runtime.call_tool("beast_plugin_manifest_validate", {
        "manifest": manifest, "prepare_hashes": True,
    })

    assert otel["exported"] is False
    assert otel["span_count"] == 1
    assert validation["validation"]["valid"] is True


def test_maintenance_mcp_tool_runs_repo_hygiene(tmp_path, monkeypatch):
    (tmp_path / "hello.py").write_text("value = 1\n", encoding="utf-8")
    monkeypatch.setenv("BEAST_WORKSPACE", str(tmp_path))
    runtime = BeastToolRuntime()

    report = runtime.call_tool(
        "beast_run_maintenance_cascade",
        {
            "include_extension_checks": False,
            "include_markdown": False,
            "run_tests": False,
            "timeout_seconds": 10,
        },
    )

    checks = {check["name"]: check for check in report["checks"]}
    assert report["beast_object_type"] == "maintenance_cascade_report"
    assert checks["py_compile"]["status"] == "passed"
    assert checks["pytest"]["status"] == "skipped"

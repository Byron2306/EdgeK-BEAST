from app.mcp.runtime import BeastToolRuntime


def test_runtime_exposes_v2_mcp_tools():
    runtime = BeastToolRuntime()
    names = {tool["name"] for tool in runtime.tool_definitions()}

    assert "beast_build_context_packet" in names
    assert "beast_score_forge" in names
    assert "beast_plan_workflow" in names
    assert "beast_openclaw_plan" in names
    assert "beast_mcp_status" in names


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

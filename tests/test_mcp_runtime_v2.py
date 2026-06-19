from app.mcp.runtime import BeastToolRuntime


def test_runtime_exposes_v2_mcp_tools():
    runtime = BeastToolRuntime()
    names = {tool["name"] for tool in runtime.tool_definitions()}

    assert "beast_build_context_packet" in names
    assert "beast_sourceplan_prepare" in names
    assert "beast_sourceplan_preview_hunks" in names
    assert "beast_sourceplan_apply_selected" in names
    assert "beast_provider_fitness" in names
    assert "beast_run_maintenance_cascade" in names
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

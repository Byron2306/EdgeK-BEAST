from app.mcp.broker import MCPBroker, MCPDecision
from app.kernel.workspace_graph import WorkspaceGraph


POLICIES = {
    "mcp_server_classes": {
        "local_read_only": {
            "trust_level": "low",
            "requires_approval": False,
            "budget_multiplier": 1.0,
        },
        "shell": {
            "trust_level": "high",
            "requires_approval": True,
            "budget_multiplier": 5.0,
            "allowed_commands": ["git status", "pytest"],
            "denied_commands": ["rm -rf", "curl * | sh"],
        },
        "secrets": {
            "trust_level": "critical",
            "requires_approval": True,
            "budget_multiplier": 10.0,
            "secrets_handling": "never_log_or_transmit",
        },
    },
    "file_operations": {
        "blocked_patterns": ["**.env", "*.pem"],
        "approval_required_patterns": ["package.json", "infra/**"],
        "safe_read_patterns": ["README*", "app/**"],
    },
}


def test_mcp_broker_allows_local_read_only():
    result = MCPBroker(POLICIES).evaluate({"tool_name": "read_file", "target": "README.md"}, audit=False)

    assert result.decision == MCPDecision.ALLOW
    assert result.server_class == "local_read_only"
    assert result.requires_approval is False
    assert result.request_id


def test_mcp_broker_requires_approval_for_allowed_shell_command():
    result = MCPBroker(POLICIES).evaluate({"tool_name": "shell", "command": "git status --short"}, audit=False)

    assert result.decision == MCPDecision.REQUIRE_APPROVAL
    assert result.server_class == "shell"
    assert result.budget_multiplier == 5.0


def test_mcp_broker_denies_dangerous_shell_command():
    result = MCPBroker(POLICIES).evaluate({"tool_name": "shell", "command": "rm -rf /tmp/example"}, audit=False)

    assert result.decision == MCPDecision.DENY
    assert "denied" in result.reason


def test_mcp_broker_audits_evaluations(tmp_path):
    broker = MCPBroker(POLICIES, db_path=str(tmp_path / "mcp.db"))
    result = broker.evaluate({"tool_name": "read_file", "target": "README.md"})

    stats = broker.stats()
    events = broker.recent_audit_events()

    assert stats["audit_events"] == 1
    assert stats["execution_events"] == 0
    assert events[0]["request_id"] == result.request_id
    assert events[0]["decision"] == "allow"


def test_mcp_broker_registers_servers_and_uses_server_class(tmp_path):
    broker = MCPBroker(POLICIES, db_path=str(tmp_path / "mcp.db"))
    server = broker.register_server({
        "name": "local-shell",
        "server_class": "shell",
        "description": "Local shell MCP server",
    })

    result = broker.evaluate({
        "server_name": "local-shell",
        "command": "git status --short",
    })

    assert server["server_class"] == "shell"
    assert broker.list_servers()[0]["name"] == "local-shell"
    assert result.decision == MCPDecision.REQUIRE_APPROVAL
    assert result.approval_status == "pending"


def test_mcp_broker_blocks_sensitive_file_targets(tmp_path):
    broker = MCPBroker(POLICIES, db_path=str(tmp_path / "mcp.db"))
    result = broker.evaluate({"tool_name": "read_file", "target": "config/.env"})

    assert result.decision == MCPDecision.DENY
    assert "File target denied" in result.reason


def test_mcp_broker_creates_and_resolves_approval(tmp_path):
    broker = MCPBroker(POLICIES, db_path=str(tmp_path / "mcp.db"))
    result = broker.evaluate({"tool_name": "shell", "command": "git status --short"})

    pending = broker.list_approvals(status="pending")
    approval = broker.get_approval(result.request_id)
    resolved = broker.resolve_approval(
        result.request_id,
        approved=True,
        resolved_by="tester",
        reason="Safe status command",
    )

    assert pending[0]["request_id"] == result.request_id
    assert approval["status"] == "pending"
    assert resolved["status"] == "approved"
    assert resolved["resolved_by"] == "tester"
    assert broker.stats()["pending_approvals"] == 0


def test_mcp_broker_denies_pending_approval(tmp_path):
    broker = MCPBroker(POLICIES, db_path=str(tmp_path / "mcp.db"))
    result = broker.evaluate({"tool_name": "shell", "command": "pytest"})

    resolved = broker.resolve_approval(
        result.request_id,
        approved=False,
        resolved_by="tester",
        reason="Not now",
    )

    assert resolved["status"] == "denied"
    assert resolved["resolution_reason"] == "Not now"


def test_mcp_broker_executes_allowed_read_file(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "README.md").write_text("hello edgek", encoding="utf-8")
    broker = MCPBroker(POLICIES, db_path=str(tmp_path / "mcp.db"))

    result = broker.execute(
        {"tool_name": "read_file", "target": "README.md"},
        workspace_root=str(workspace),
    )

    assert result["executed"] is True
    assert result["content"] == "hello edgek"
    assert broker.stats()["execution_events"] == 1
    execution = broker.recent_execution_events()[0]
    assert execution["executed"] is True
    assert execution["server_class"] == "local_read_only"
    assert execution["target"] == "README.md"


def test_mcp_broker_enforces_tool_schema_pin_hash(tmp_path):
    broker = MCPBroker(POLICIES, db_path=str(tmp_path / "mcp.db"))
    request = {
        "server_name": "reader",
        "server_class": "local_read_only",
        "tool_name": "read_file",
        "tool_schema": {
            "name": "read_file",
            "inputSchema": {"type": "object", "properties": {"target": {"type": "string"}}},
        },
    }

    first = broker.evaluate(request)
    second = broker.evaluate(request)
    changed = broker.evaluate({
        **request,
        "tool_schema": {
            "name": "read_file",
            "inputSchema": {"type": "object", "properties": {"path": {"type": "string"}}},
        },
    })

    assert first.decision == MCPDecision.ALLOW
    assert second.decision == MCPDecision.ALLOW
    assert changed.decision == MCPDecision.DENY
    assert "schema hash mismatch" in changed.reason
    assert broker.stats()["schema_pins"] == 1
    assert broker.list_schema_pins()[0]["tool_name"] == "read_file"


def test_mcp_broker_read_file_uses_workspace_cache_on_repeated_read(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "README.md").write_text("cached edgek", encoding="utf-8")
    graph = WorkspaceGraph(str(tmp_path / "workspace_graph.db"))
    broker = MCPBroker(POLICIES, db_path=str(tmp_path / "mcp.db"), workspace_graph=graph)

    first = broker.execute({"tool_name": "read_file", "target": "README.md"}, workspace_root=str(workspace))
    second = broker.execute({"tool_name": "read_file", "target": "README.md"}, workspace_root=str(workspace))

    assert first["executed"] is True
    assert first["cache_hit"] is False
    assert second["executed"] is True
    assert second["cache_hit"] is True
    assert second["cache_source"] in {"l1", "l2"}
    assert graph.stats()["file_read_cache"]["l1_entries"] >= 1


def test_mcp_broker_blocks_read_file_path_escape(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("nope", encoding="utf-8")
    broker = MCPBroker(POLICIES, db_path=str(tmp_path / "mcp.db"))

    result = broker.execute(
        {"tool_name": "read_file", "target": "../outside.txt"},
        workspace_root=str(workspace),
    )

    assert result["executed"] is False
    assert "escapes workspace root" in result["reason"]
    execution = broker.recent_execution_events()[0]
    assert execution["executed"] is False
    assert "escapes workspace root" in execution["reason"]


def test_mcp_broker_executes_approved_shell_command(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    broker = MCPBroker(POLICIES, db_path=str(tmp_path / "mcp.db"))
    request = {
        "request_id": "shell-1",
        "tool_name": "shell",
        "command": "git status",
        "cwd": ".",
    }
    evaluation = broker.evaluate(request)
    broker.resolve_approval(evaluation.request_id, approved=True, resolved_by="tester")

    result = broker.execute(request, workspace_root=str(workspace))

    assert result["executed"] is True
    assert result["command"] == "git status"
    assert isinstance(result["returncode"], int)
    execution = broker.recent_execution_events()[0]
    assert execution["request_id"] == "shell-1"
    assert execution["executed"] is True
    assert execution["command"] == "git status"

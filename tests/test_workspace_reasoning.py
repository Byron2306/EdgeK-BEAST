from app.kernel.compute.perceive import EdgeKIR
from app.kernel.governance.reason import BudgetLedger, GovernanceDecision, Reasoner
from app.kernel.data_processing.workspace_graph import WorkspaceGraph


def test_reasoner_attaches_workspace_graph_context(tmp_path):
    graph = WorkspaceGraph(str(tmp_path / "workspace_graph.db"))
    timestamp = "2026-06-11T00:00:00Z"
    graph.upsert_node("file:app/main.py", "file", "app/main.py", {}, timestamp)

    reasoner = Reasoner(
        budget_ledger=BudgetLedger(str(tmp_path / "budget.db")),
        workspace_graph=graph,
    )
    ir = EdgeKIR(
        messages=[{"role": "user", "content": "Inspect app/main.py"}],
        model="gpt-3.5-turbo",
        max_tokens=10,
        metadata={"provider": "openai"},
    )

    result = reasoner.reason(ir, "workspace-reasoning")

    assert result.decision == GovernanceDecision.ALLOW
    assert "workspace_graph_context" in result.policies_applied
    assert result.modified_ir.metadata["workspace_graph_context"]["matched_node_count"] == 1


def test_reasoner_attaches_l1_l4_semantic_policy_context(tmp_path):
    graph = WorkspaceGraph(str(tmp_path / "workspace_graph.db"))
    timestamp = "2026-06-11T00:00:00Z"
    graph.upsert_node("file:tests/test_api.py", "file", "tests/test_api.py", {}, timestamp)

    reasoner = Reasoner(
        budget_ledger=BudgetLedger(str(tmp_path / "budget.db")),
        workspace_graph=graph,
    )
    ir = EdgeKIR(
        messages=[{"role": "user", "content": "Fix the failing pytest in tests/test_api.py and verify it"}],
        model="gpt-3.5-turbo",
        max_tokens=10,
        metadata={"provider": "openai"},
    )

    result = reasoner.reason(ir, "memory-policy")

    assert result.decision == GovernanceDecision.MODIFY
    assert "l1_runtime_memory_signals" in result.policies_applied
    context = result.modified_ir.metadata["l1_l4_semantic_policy_context"]
    assert context["chronicle_required"] is True
    assert any(signal["signal"] == "quality_cascade_candidate" for signal in context["signals"])


def test_reasoner_blocks_risky_tools_without_mcp_evaluation(tmp_path):
    reasoner = Reasoner(
        budget_ledger=BudgetLedger(str(tmp_path / "budget.db")),
        workspace_graph=WorkspaceGraph(str(tmp_path / "workspace_graph.db")),
    )
    ir = EdgeKIR(
        messages=[{"role": "user", "content": "Run this shell command"}],
        model="gpt-3.5-turbo",
        max_tokens=10,
        tools=[{"type": "function", "function": {"name": "shell_exec"}}],
        metadata={"provider": "openai"},
    )

    result = reasoner.reason(ir, "memory-policy")

    assert result.decision == GovernanceDecision.DENY
    assert "mcp_tool_governance_required" in result.policies_applied

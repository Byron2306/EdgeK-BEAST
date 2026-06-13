from app.kernel.perceive import EdgeKIR
from app.kernel.reason import BudgetLedger, GovernanceDecision, Reasoner
from app.kernel.workspace_graph import WorkspaceGraph


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


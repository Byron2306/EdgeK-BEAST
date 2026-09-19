import asyncio

from app.kernel.agents.planner_models import PlannerDecisionType
from app.kernel.agents.planner_provider import HeuristicPlannerProvider
from app.kernel.agents.tool_runtime import _extract_workspace_symbols


def _run_with_index():
    return {
        "mode": "agent",
        "provider": "ollama",
        "objective": "repair invoice defect",
        "checkpoint": {
            "planner": {
                "observations": [
                    {
                        "tool_id": "workspace.index",
                        "status": "completed",
                        "result": {
                            "beast_object_type": "beast_workspace_index_snapshot",
                            "tests": ["test_invoice.py"],
                            "files": [
                                {"path": "calculator.py", "language": "python"},
                                {"path": "pricing.py", "language": "python"},
                                {"path": "validation.py", "language": "python"},
                                {"path": "test_invoice.py", "language": "python"},
                            ],
                        },
                    },
                    {"tool_id": "worktree.bind", "status": "completed", "result": {"status": "active"}},
                ]
            }
        },
    }


def test_python_import_extraction_is_line_bounded():
    source = (
        "import pytest\n\n"
        "from calculator import invoice_total\n"
        "from validation import validate_discount\n\n"
        "def test_percentage_discount():\n"
        "    assert invoice_total(200.0, 15.0) == 170.0\n"
    )
    _symbols, imports = _extract_workspace_symbols("test_invoice.py", "python", source)
    assert imports == [
        {"path": "test_invoice.py", "target": "calculator", "kind": "import"},
        {"path": "test_invoice.py", "target": "validation", "kind": "import"},
        {"path": "test_invoice.py", "target": "pytest", "kind": "import"},
    ]


def test_heuristic_cockpit_runs_discovered_baseline_after_bind():
    decision = asyncio.run(HeuristicPlannerProvider().next_decision("", run=_run_with_index(), turn=3))
    assert decision.decision_type is PlannerDecisionType.TOOL
    assert decision.tool_id == "worktree.verify"
    assert decision.arguments["command"] == ["python", "-m", "pytest", "-q", "test_invoice.py"]
    assert "lifecycle orchestration" in decision.rationale

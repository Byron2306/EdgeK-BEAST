from __future__ import annotations

import asyncio

from app.kernel.agents.planner_provider import parse_planner_decision
from app.kernel.agents.tool_models import ToolExecutionContext
from app.kernel.agents.tool_runtime import _workspace_index
from app.kernel.agents.verification_planner import plan_verification


def test_root_level_test_python_file_is_discovered(tmp_path):
    (tmp_path / "calculator.py").write_text("def safe_average(values):\n    return 0.0\n", encoding="utf-8")
    (tmp_path / "test_calculator.py").write_text("from calculator import safe_average\n", encoding="utf-8")
    context = ToolExecutionContext(run_id="micro1", workspace_root=str(tmp_path))

    result = asyncio.run(_workspace_index({"limit": 100, "include_symbols": True}, context))

    assert "test_calculator.py" in result["tests"]
    assert result["summary"]["test_file_count"] == 1


def test_python_source_change_infers_related_pytest_from_workspace_evidence_without_catalog():
    run = {
        "request": {},
        "checkpoint": {
            "planner": {
                "observations": [
                    {
                        "tool_id": "workspace.index",
                        "status": "completed",
                        "result": {
                            "beast_object_type": "beast_workspace_index_snapshot",
                            "files": [
                                {"path": "calculator.py", "language": "python"},
                                {"path": "test_calculator.py", "language": "python"},
                            ],
                            "tests": ["test_calculator.py"],
                            "imports": [
                                {"path": "test_calculator.py", "target": "calculator", "kind": "import"},
                            ],
                        },
                    },
                    {
                        "tool_id": "worktree.replace_exact",
                        "status": "completed",
                        "result": {"path": "calculator.py"},
                    },
                ],
            },
        },
    }

    plan = plan_verification(run)

    assert plan["command"] == ["python", "-m", "pytest", "-q", "test_calculator.py"]
    assert plan["reason"] == "related_pytest_from_workspace_index"
    assert plan["scope"] == "related_tests"


def test_read_range_strips_end_line_even_when_line_count_already_present():
    decision = parse_planner_decision({
        "decision_type": "tool",
        "tool_id": "workspace.read_range",
        "arguments": {
            "path": "calculator.py",
            "start_line": 1,
            "end_line": 4,
            "line_count": 4,
        },
    })

    assert decision.arguments == {
        "path": "calculator.py",
        "start_line": 1,
        "line_count": 4,
    }


def test_equivalent_tool_decisions_ignore_summary_prose():
    raw = (
        '{"decision_type":"tool","tool_id":"workspace.read_range",'
        '"arguments":{"path":"calculator.py","start_line":1,"line_count":4},'
        '"summary":"Inspect the implementation."}'
        '\n'
        '{"decision_type":"tool","tool_id":"workspace.read_range",'
        '"arguments":{"path":"calculator.py","start_line":1,"line_count":4},'
        '"summary":"Read calculator source."}'
    )

    decision = parse_planner_decision(raw)

    assert decision.tool_id == "workspace.read_range"
    assert decision.arguments["path"] == "calculator.py"


def test_workspace_read_range_prefers_bound_worktree_bytes(tmp_path):
    from app.kernel.agents.tool_runtime import _workspace_read_range

    workspace = tmp_path / "workspace"
    worktree = tmp_path / "worktree"
    workspace.mkdir()
    worktree.mkdir()
    (workspace / "calculator.py").write_text("VALUE = 'original'\n", encoding="utf-8")
    (worktree / "calculator.py").write_text("VALUE = 'mutated'\n", encoding="utf-8")
    context = ToolExecutionContext(
        run_id="micro1",
        workspace_root=str(workspace),
        worktree_root=str(worktree),
    )

    result = asyncio.run(_workspace_read_range({"path": "calculator.py", "start_line": 1, "line_count": 10}, context))

    assert result["content"] == "VALUE = 'mutated'"


def test_approval_authority_digest_changes_when_mutation_arguments_change():
    from app.kernel.agents.tool_runtime import approval_authority_digest

    a = approval_authority_digest(
        tool_id="worktree.replace_exact",
        execution_target="local",
        arguments={"path": "calculator.py", "old_text": "x", "new_text": "y"},
        affected_paths=["calculator.py"],
    )
    b = approval_authority_digest(
        tool_id="worktree.replace_exact",
        execution_target="local",
        arguments={"path": "calculator.py", "old_text": "x", "new_text": "z"},
        affected_paths=["calculator.py"],
    )

    assert a != b


def test_approval_can_be_consumed_only_once(tmp_path):
    from app.kernel.agents.run_store import AgentRunStore

    store = AgentRunStore(tmp_path)
    run = store.create_run(session_id="s", objective="o")
    approval_id = "approval-1"
    store.create_approval(run["run_id"], {"request_id": approval_id, "tool_id": "worktree.replace_exact"})
    store.resolve_approval(run["run_id"], approval_id, {"approved": True})

    consumed = store.consume_approval(run["run_id"], approval_id)

    assert consumed["status"] == "consumed"
    try:
        store.consume_approval(run["run_id"], approval_id)
    except ValueError as exc:
        assert "not approved" in str(exc)
    else:
        raise AssertionError("approval replay was accepted")

from pathlib import Path
import pytest

from app.kernel.agents.run_engine import AgentRunEngine
from app.kernel.operations_console.mode_contract import WorkbenchModeEngine


def make_run(tmp_path: Path, mode="ask"):
    return AgentRunEngine(tmp_path).create_run(session_id="s", objective="obj", mode=mode, run_id=f"run-{mode}")


def test_contracts_match_phase5_semantics(tmp_path):
    engine = WorkbenchModeEngine(tmp_path)
    ask = engine.contract("ASK")
    edit = engine.contract("EDIT")
    agent = engine.contract("AGENT")
    review = engine.contract("REVIEW")
    assert ask["read_only"] and not ask["worktree_allowed"] and not ask["sourceplan_allowed"]
    assert edit["sourceplan_required"] and edit["repair_turn_limit"] == 1
    assert agent["worktree_required"] and agent["repeated_repair_allowed"]
    assert review["critic_role"] and review["verifier_role"] and not review["mutation_allowed"]
    assert all(engine.verify_contract(x) for x in (ask, edit, agent, review))


def test_ask_to_edit_is_durable_and_updates_run(tmp_path):
    make_run(tmp_path, "ask")
    receipt = WorkbenchModeEngine(tmp_path).transition("run-ask", "EDIT", operator_id="op", reason="bounded change")
    assert receipt["from_mode"] == "ASK" and receipt["to_mode"] == "EDIT"
    reopened = WorkbenchModeEngine(tmp_path)
    assert reopened.engine.store.get_run("run-ask")["mode"] == "edit"
    assert len(reopened.history("run-ask")) == 1


def test_review_to_agent_requires_explicit_conversion(tmp_path):
    make_run(tmp_path, "review")
    with pytest.raises(ValueError, match="explicit conversion"):
        WorkbenchModeEngine(tmp_path).transition("run-review", "AGENT", operator_id="op", reason="fix")


def test_review_to_agent_with_confirmation_passes(tmp_path):
    make_run(tmp_path, "review")
    result = WorkbenchModeEngine(tmp_path).transition(
        "run-review", "AGENT", operator_id="op", reason="convert findings", conversion_confirmed=True
    )
    assert result["to_mode"] == "AGENT"


def test_agent_cannot_jump_directly_to_edit(tmp_path):
    make_run(tmp_path, "agent")
    with pytest.raises(ValueError, match="illegal mode transition"):
        WorkbenchModeEngine(tmp_path).transition("run-agent", "EDIT", operator_id="op", reason="no")


def test_same_mode_transition_rejected(tmp_path):
    make_run(tmp_path, "ask")
    with pytest.raises(ValueError, match="must change"):
        WorkbenchModeEngine(tmp_path).transition("run-ask", "ASK", operator_id="op", reason="noop")


def test_operator_and_reason_required(tmp_path):
    make_run(tmp_path, "ask")
    with pytest.raises(ValueError, match="required"):
        WorkbenchModeEngine(tmp_path).transition("run-ask", "EDIT", operator_id="", reason="")


def test_active_tool_blocks_read_only_transition(tmp_path):
    run = make_run(tmp_path, "agent")
    AgentRunEngine(tmp_path).merge_checkpoint(run["run_id"], {"active_tool": "running"})
    with pytest.raises(ValueError, match="tool is active"):
        WorkbenchModeEngine(tmp_path).transition("run-agent", "ASK", operator_id="op", reason="pause")


def test_dirty_agent_requires_sourceplan_before_review(tmp_path):
    run = make_run(tmp_path, "agent")
    AgentRunEngine(tmp_path).merge_checkpoint(run["run_id"], {"worktree": {"dirty": True}})
    with pytest.raises(ValueError, match="reviewable SourcePlan"):
        WorkbenchModeEngine(tmp_path).transition("run-agent", "REVIEW", operator_id="op", reason="review")


def test_transition_receipt_grants_no_execution_authority(tmp_path):
    make_run(tmp_path, "ask")
    receipt = WorkbenchModeEngine(tmp_path).transition("run-ask", "AGENT", operator_id="op", reason="start")
    assert receipt["authority"] == "workbench_mode_transition_only"
    assert receipt["grants_execution_authority"] is False
    assert receipt["grants_promotion_authority"] is False

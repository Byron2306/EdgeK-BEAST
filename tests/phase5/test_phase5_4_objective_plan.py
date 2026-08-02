from pathlib import Path
import pytest
from app.kernel.agents.run_engine import AgentRunEngine
from app.kernel.operations_console.objective_plan import ObjectivePlanWorkspace
from app.kernel.operations_console.view_model import AgentOperationsConsoleViewModel


def make_run(tmp_path: Path, objective="Fix parser"):
    return AgentRunEngine(tmp_path).create_run(session_id="s", objective=objective, mode="agent", run_id="run-54")


def base_revision(ws):
    return ws.revise("run-54", objective="Fix parser", success_criteria=["Focused parser tests pass"],
        steps=[{"step_id":"inspect","title":"Inspect failure","status":"active"},{"step_id":"repair","title":"Repair parser"}],
        active_step_id="inspect", operator_id="op", reason="initial plan")


def test_initial_revision_is_durable_and_verifiable(tmp_path):
    make_run(tmp_path); receipt=base_revision(ObjectivePlanWorkspace(tmp_path))
    reopened=ObjectivePlanWorkspace(tmp_path)
    assert reopened.current("run-54")["revision_digest"] == receipt["revision_digest"]
    assert reopened.verify(receipt)


def test_requires_measurable_success_criteria(tmp_path):
    make_run(tmp_path)
    with pytest.raises(ValueError, match="success criterion"):
        ObjectivePlanWorkspace(tmp_path).revise("run-54", objective="Fix parser", success_criteria=[], steps=[{"title":"Inspect"}], operator_id="op", reason="x")


def test_requires_plan_steps(tmp_path):
    make_run(tmp_path)
    with pytest.raises(ValueError, match="plan step"):
        ObjectivePlanWorkspace(tmp_path).revise("run-54", objective="Fix parser", success_criteria=["Pass"], steps=[], operator_id="op", reason="x")


def test_material_objective_expansion_requires_confirmation(tmp_path):
    make_run(tmp_path); ws=ObjectivePlanWorkspace(tmp_path); base_revision(ws)
    with pytest.raises(ValueError, match="expansion"):
        ws.revise("run-54", objective="Fix parser and redesign authentication", success_criteria=["Focused parser tests pass"], steps=[{"title":"Inspect"}], operator_id="op", reason="expand")


def test_confirmed_expansion_is_recorded_but_grants_no_authority(tmp_path):
    make_run(tmp_path); ws=ObjectivePlanWorkspace(tmp_path); base_revision(ws)
    r=ws.revise("run-54", objective="Fix parser and redesign authentication", success_criteria=["Focused parser tests pass"], steps=[{"title":"Inspect"}], operator_id="op", reason="expand", expansion_confirmed=True)
    assert r["objective_expanded"] is True and r["grants_objective_expansion"] is False


def test_only_one_active_step_allowed(tmp_path):
    make_run(tmp_path)
    with pytest.raises(ValueError, match="only one"):
        ObjectivePlanWorkspace(tmp_path).revise("run-54", objective="Fix parser", success_criteria=["Pass"], steps=[{"step_id":"a","title":"A","status":"active"},{"step_id":"b","title":"B","status":"active"}], operator_id="op", reason="x")


def test_advance_completes_exact_step_and_activates_next(tmp_path):
    make_run(tmp_path); ws=ObjectivePlanWorkspace(tmp_path); base_revision(ws)
    r=ws.advance("run-54", completed_step_id="inspect", next_step_id="repair", operator_id="op", reason="inspection done")
    statuses={x["step_id"]:x["status"] for x in r["plan"]["steps"]}
    assert statuses == {"inspect":"completed","repair":"active"}


def test_history_is_versioned_and_chained(tmp_path):
    make_run(tmp_path); ws=ObjectivePlanWorkspace(tmp_path); first=base_revision(ws)
    second=ws.advance("run-54", completed_step_id="inspect", next_step_id="repair", operator_id="op", reason="done")
    history=ws.history("run-54")
    assert [x["plan_version"] for x in history] == [1,2]
    assert second["previous_revision_digest"] == first["revision_digest"]


def test_console_uses_durable_objective_and_plan(tmp_path):
    make_run(tmp_path); ws=ObjectivePlanWorkspace(tmp_path); base_revision(ws)
    snap=AgentOperationsConsoleViewModel(tmp_path).build("run-54")
    assert snap["run"]["objective"] == "Fix parser"
    assert snap["plan"]["version"] == 1 and snap["plan"]["active_step_id"] == "inspect"


def test_tampered_revision_fails_verification(tmp_path):
    make_run(tmp_path); ws=ObjectivePlanWorkspace(tmp_path); receipt=base_revision(ws)
    receipt["objective"]="tampered"
    assert ws.verify(receipt) is False

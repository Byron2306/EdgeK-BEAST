from app.kernel.execution.conductor_workflow import ConductorWorkflowBuilder
from app.kernel.execution.least_authority_tools import LeastAuthorityToolLoop
from app.cli.api import BeastApiClient


def test_least_authority_denies_mutating_tool_even_when_requested():
    loop = LeastAuthorityToolLoop()
    receipt = loop.authorize(
        {"name": "write_source", "category": "sourceplan", "bucket": "Modify", "mutating": True},
        phase="implementer", risk="low", approved=True,
    )

    assert receipt["allowed"] is False
    assert "SourcePlan approval" in receipt["reason"]
    assert receipt["receipt_id"].startswith("tool_")


def test_cli_client_exposes_same_authority_contract(tmp_path):
    plan = BeastApiClient("http://offline", workspace=tmp_path).least_authority_plan(
        [{"name": "cli:verify", "category": "audit", "bucket": "Verify", "mutating": False}],
        phase="review", risk="low",
    )
    assert plan["beast_object_type"] == "least_authority_tool_plan"
    assert plan["tools"][0]["receipt_id"].startswith("tool_")


def test_mutation_gate_requires_approval_and_a_bound_sourceplan():
    loop = LeastAuthorityToolLoop()
    denied = loop.mutation_gate("sourceplan_apply", phase="implementer", approved=False, sourceplan_bound=True)
    allowed = loop.mutation_gate("sourceplan_apply", phase="implementer", approved=True, sourceplan_bound=True)

    assert denied["mutation_permitted"] is False
    assert allowed["mutation_permitted"] is True
    assert allowed["execution_rule"].startswith("This receipt permits entry")


def test_conductor_dispatch_repairs_only_as_a_draft_after_failed_verification(tmp_path):
    builder = ConductorWorkflowBuilder(data_dir=str(tmp_path))
    workflow = builder.build(
        {
            "task_id": "tsk_1234567890abcdef",
            "task_class": "live_coding",
            "risk_level": "low",
            "approval_required_for": [],
            "success_criteria": ["tests pass"],
        },
        route_card={"route_id": "route_quality_live_coding"},
        run_swarm=False,
    )
    receipt = builder.dispatch(
        workflow,
        {
            "prepare_task": lambda: {"ok": True},
            "run_verification": lambda: {"ok": False, "failures": ["test failed"]},
            "repair_draft": lambda: {"ok": True, "draft_sourceplan": {"operations": []}},
        },
    )

    assert receipt["verification_failed"] is True
    assert receipt["stopped"] == "repair draft returned for SourcePlan validation"
    repair = next(item for item in receipt["outcomes"] if item["step_id"] == "repair_draft")
    assert repair["status"] == "draft_ready"
    assert "No source write" in receipt["source_write_rule"]


def test_conductor_dispatch_can_persist_and_list_receipts(tmp_path):
    builder = ConductorWorkflowBuilder(data_dir=str(tmp_path))
    workflow = builder.build(
        {"task_id": "tsk_abcdef1234567890", "task_class": "live_coding", "risk_level": "low", "approval_required_for": []},
        run_swarm=False,
    )
    receipt = builder.dispatch(workflow, {"prepare_task": lambda: {"ok": True}}, persist=True)
    index = builder.list_dispatches(workflow["workflow_id"])

    assert receipt["artifact"]["written"] is True
    assert index["count"] == 1
    assert index["dispatches"][0]["workflow_id"] == workflow["workflow_id"]


def test_conductor_resume_uses_durable_history_without_source_executor(tmp_path):
    builder = ConductorWorkflowBuilder(data_dir=str(tmp_path))
    workflow = builder.build(
        {"task_id": "tsk_resume123456789", "task_class": "live_coding", "risk_level": "low", "approval_required_for": []},
        run_swarm=False,
    )
    builder.dispatch(workflow, {"prepare_task": lambda: {"ok": True}}, persist=True)
    resumed = builder.resume(workflow, {"run_verification": lambda: {"ok": True}})

    assert resumed["resumed_from"]
    assert "source writes" in resumed["resume_rule"]

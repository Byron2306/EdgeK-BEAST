import pytest
from httpx import ASGITransport, AsyncClient

from app.kernel.conductor_workflow import ConductorWorkflowBuilder
from app.kernel.swarm import SwarmKernel
from app.main import app


def test_conductor_workflow_uses_swarm_as_planning_only_advice(tmp_path):
    swarm = SwarmKernel(db_path=str(tmp_path / "swarm.db"))
    builder = ConductorWorkflowBuilder(swarm_kernel=swarm, data_dir=str(tmp_path / "data"))
    envelope = {
        "task_id": "tsk_workflow",
        "task_class": "refactor_request",
        "risk_level": "medium",
        "intent": "Refactor provider router safely.",
        "success_criteria": ["compatibility preserved", "tests pass"],
        "approval_required_for": ["git_push"],
        "context_budget": {"max_tokens": 8000},
    }
    context_packet = {
        "packet_id": "pkt_workflow",
        "included_evidence": [{"kind": "file_snippet", "source": "app/main.py"}],
        "packet_stats": {"estimated_tokens": 500},
    }
    scorecard = {
        "scorecard_id": "forge_workflow",
        "decision": "proceed_with_constraints",
        "minimal_patch_first": True,
        "required_gates": {"compatibility_tests_required": True, "chronicle_required": True},
    }

    workflow = builder.build(
        envelope,
        context_packet=context_packet,
        forge_scorecard=scorecard,
        run_swarm=True,
        persist=True,
    )

    assert workflow["beast_object_type"] == "conductor_workflow_card"
    assert workflow["workflow_id"].startswith("wf_")
    assert workflow["executor_binding"]["available"] is False
    assert workflow["swarm"]["used"] is True
    assert workflow["swarm"]["execution_capability"] == "planning_only"
    assert workflow["swarm"]["model_call_executed"] is False
    assert workflow["decision"] == "proceed_with_constraints"
    assert any(gate["name"] == "compatibility_tests_required" for gate in workflow["required_gates"])
    assert "adapter_or_router_compatibility_tests" in workflow["verification_plan"]["required_checks"]
    assert all(step["executes_now"] is False for step in workflow["steps"])
    assert workflow["artifact"]["written"] is True
    assert builder.get_workflow(workflow["workflow_id"])["workflow_id"] == workflow["workflow_id"]
    assert builder.list_workflows()["count"] == 1


def test_conductor_workflow_honors_swarm_approval_gate(tmp_path):
    swarm = SwarmKernel(db_path=str(tmp_path / "swarm.db"))
    builder = ConductorWorkflowBuilder(swarm_kernel=swarm, data_dir=str(tmp_path / "data"))
    envelope = {
        "task_id": "tsk_high_risk",
        "task_class": "small_patch",
        "risk_level": "high",
        "intent": "Deploy to production and delete stale migration data.",
        "success_criteria": ["safe"],
        "context_budget": {"max_tokens": 8000},
    }

    workflow = builder.build(envelope, run_swarm=True)

    assert workflow["decision"] == "approval_required"
    assert any(gate["decision"] == "approval_required" for gate in workflow["required_gates"])


@pytest.mark.asyncio
async def test_workflow_plan_endpoint_builds_artifacts_and_swarm_advice():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/edgek/workflow/plan",
            json={
                "user_request": "Refactor app/adapters/huggingface_adapter.py provider route safely",
                "task_class": "refactor_request",
                "run_quality": False,
                "run_swarm": True,
            },
        )

    assert response.status_code == 200
    workflow = response.json()
    assert workflow["beast_object_type"] == "conductor_workflow_card"
    assert workflow["context_packet_id"].startswith("pkt_")
    assert workflow["forge_scorecard_id"].startswith("forge_")
    assert workflow["swarm"]["execution_capability"] == "planning_only"
    assert workflow["executor_binding"]["available"] is False

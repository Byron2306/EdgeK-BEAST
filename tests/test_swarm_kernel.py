import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.kernel.swarm import SwarmKernel


def test_swarm_governance_contract_lists_profiles_and_role_lanes(tmp_path):
    kernel = SwarmKernel(db_path=str(tmp_path / "swarm.db"))

    governance = kernel.governed_roles()

    assert governance["beast_object_type"] == "swarm_governance_profile"
    assert governance["profiles"]["hermes"]["role"] == "coordinator"
    assert governance["profiles"]["openclaw"]["execution_capability"] == "read_only_local_first"
    assert governance["profiles"]["nemoclaw"]["requires_approval"] is True
    assert governance["profiles"]["zeroclaw"]["default_execution"] == "no_tool_execution"
    assert set(governance["role_lanes"]) >= {
        "cartographer",
        "compressor",
        "sentinel",
        "verifier",
        "scribe",
        "critic",
    }


def test_swarm_kernel_runs_role_state_machine_and_logs_value(tmp_path):
    kernel = SwarmKernel(
        policies={"swarm": {"enabled": True}},
        db_path=str(tmp_path / "swarm.db"),
    )

    result = kernel.run({
        "objective": "Implement a bug fix and run targeted pytest",
        "context": "x" * 40000,
        "target_context_tokens": 2000,
        "files": ["app/kernel/reason.py"],
        "execution_result": {"success": True},
    })

    roles = [event["role"] for event in result["events"]]

    assert result["status"] == "succeeded"
    assert result["state"] == "completed"
    assert result["task_type"] == "test_repair"
    assert "conductor" in roles
    assert "sentinel" in roles
    assert "cartographer" in roles
    assert "compressor" in roles
    assert "verifier" in roles
    assert "scribe" in roles
    assert "supervisor" in roles
    assert "archivist" in roles
    assert result["metadata"]["execution_profile"]["profile"] == "hermes"
    assert result["value"]["estimated_tokens_saved"] > 0
    assert kernel.state()["runs"] == 1
    assert kernel.value_logs()[0]["run_id"] == result["run_id"]


def test_swarm_kernel_requires_approval_for_high_risk_workflow(tmp_path):
    kernel = SwarmKernel(db_path=str(tmp_path / "swarm.db"))

    result = kernel.run({
        "objective": "Deploy to production and delete stale migration data",
    })

    assert result["status"] == "approval_required"
    assert result["state"] == "blocked"
    assert any(gate["decision"] == "approval_required" for gate in result["gates"])


def test_swarm_nemoclaw_requires_explicit_approval_even_for_low_risk(tmp_path):
    kernel = SwarmKernel(db_path=str(tmp_path / "swarm.db"))

    result = kernel.run({
        "objective": "Inspect a provider diagnostic route",
        "profile": "nemoclaw",
    })

    assert result["status"] == "approval_required"
    assert result["metadata"]["execution_profile"]["profile"] == "nemoclaw"
    assert any(gate["name"] == "nemoclaw_explicit_approval" for gate in result["gates"])


def test_swarm_zeroclaw_is_planning_only_and_allows_no_tool_execution(tmp_path):
    kernel = SwarmKernel(db_path=str(tmp_path / "swarm.db"))

    result = kernel.run({
        "objective": "Plan the safest local inspection path",
        "profile": "zeroclaw",
    })

    roles = [event["role"] for event in result["events"]]

    assert result["status"] == "ready"
    assert result["metadata"]["execution_profile"]["profile"] == "zeroclaw"
    assert any(gate["name"] == "zeroclaw_planning_only" for gate in result["gates"])
    assert "hermes" in roles
    assert "scribe" in roles
    assert any(step["action"] == "enforce_no_tool_execution" for step in result["plan"])


def test_swarm_kernel_invokes_critic_after_failure_without_model_call(tmp_path):
    kernel = SwarmKernel(db_path=str(tmp_path / "swarm.db"))

    result = kernel.run({
        "objective": "Fix failing pytest import loop",
        "execution_result": {"success": False, "error": "ImportError loop"},
        "model_based_critic": True,
    })

    critic_events = [event for event in result["events"] if event["role"] == "critic"]

    assert result["status"] == "needs_revision"
    assert critic_events
    assert critic_events[0]["details"]["model_based_requested"] is True
    assert critic_events[0]["details"]["model_call_executed"] is False
    assert result["value"]["avoided_model_calls"] == 1.0


def test_swarm_kernel_gets_recent_runs_and_detail(tmp_path):
    kernel = SwarmKernel(db_path=str(tmp_path / "swarm.db"))
    run = kernel.run({"objective": "Update README documentation"})

    recent = kernel.recent_runs()
    detail = kernel.get_run(run["run_id"])

    assert recent[0]["run_id"] == run["run_id"]
    assert detail["objective"] == "Update README documentation"
    assert detail["events"]


@pytest.mark.asyncio
async def test_swarm_governance_endpoint_filters_profile():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/edgek/swarm/governance", params={"profile": "zeroclaw"})

    assert response.status_code == 200
    payload = response.json()
    assert list(payload["profiles"]) == ["zeroclaw"]
    assert payload["profiles"]["zeroclaw"]["execution_capability"] == "planning_only"
    assert "scribe" in payload["role_lanes"]

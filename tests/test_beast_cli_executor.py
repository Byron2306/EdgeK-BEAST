import pytest
from httpx import ASGITransport, AsyncClient

from app.kernel.beast_cli_executor import BeastCLIExecutor
from app.kernel.canon_registry import CanonRegistry
from app.mcp.broker import MCPBroker
from app.main import app


def test_openclaw_plan_is_local_first_and_read_only(tmp_path):
    executor = BeastCLIExecutor(canon_registry=CanonRegistry())
    workflow = {
        "beast_object_type": "conductor_workflow_card",
        "version": "1.0",
        "workflow_id": "wf_test",
        "task_id": "tsk_test",
        "task_class": "small_patch",
        "execution_mode": "advisory_plan",
        "executor_binding": {"available": False},
        "decision": "ready",
        "required_gates": [],
        "steps": [],
        "verification_plan": {},
        "workflow_hash": "sha256:" + "a" * 64,
    }
    context_packet = {
        "beast_object_type": "context_packet",
        "version": "1.0",
        "packet_id": "pkt_test",
        "task_id": "tsk_test",
        "task_class": "small_patch",
        "context_budget": {},
        "included_evidence": [{"kind": "file_snippet", "source": "app/main.py"}],
        "excluded_evidence": [],
        "packet_stats": {},
        "handoff_hash": "sha256:" + "b" * 64,
    }

    plan = executor.plan(
        objective="Inspect app/main.py",
        workflow=workflow,
        context_packet=context_packet,
        workspace_root=str(tmp_path),
        use_ollama=False,
    )

    assert plan["beast_object_type"] == "beast_cli_plan"
    assert plan["profile"]["mode"] == "openclaw"
    assert plan["profile"]["local_inference_first"] is True
    assert plan["swarm_governance"]["profile"]["profile"] == "openclaw"
    assert "verifier" in plan["swarm_governance"]["role_lanes"]
    assert plan["actions"][0]["risk"] == "read_only"
    assert plan["actions"][0]["request"]["server_class"] == "local_read_only"


def test_openclaw_executes_approved_read_only_mcp_action(tmp_path):
    (tmp_path / "notes.md").write_text("hello beast\n", encoding="utf-8")
    broker = MCPBroker(
        policies={
            "mcp_server_classes": {
                "local_read_only": {
                    "trust_level": "high",
                    "requires_approval": False,
                    "budget_multiplier": 1.0,
                }
            },
            "file_operations": {"blocked_patterns": ["*.env"], "approval_required_patterns": []},
        },
        db_path=str(tmp_path / "mcp.db"),
    )
    executor = BeastCLIExecutor(mcp_broker=broker)
    context_packet = {
        "included_evidence": [{"kind": "file_snippet", "source": "notes.md"}],
    }

    result = executor.execute(
        objective="Read notes",
        workflow={"required_gates": []},
        context_packet=context_packet,
        workspace_root=str(tmp_path),
        dry_run=False,
        approved=False,
        use_ollama=False,
    )

    assert result["status"] == "succeeded"
    assert result["summary"]["executed_count"] == 1
    assert result["results"][0]["mcp_result"]["content"] == "hello beast\n"


def test_nemoclaw_blocks_without_approval_for_gated_action():
    executor = BeastCLIExecutor()

    result = executor.execute(
        objective="Prepare high-risk action",
        workflow={"required_gates": []},
        context_packet={},
        mode="nemoclaw",
        dry_run=False,
        approved=False,
        use_ollama=False,
    )

    assert result["status"] == "blocked"
    assert any(item.get("reason") == "approval_required" for item in result["results"])


def test_nemoclaw_executes_approved_write_safe_mcp_action(tmp_path):
    broker = MCPBroker(
        policies={
            "mcp_server_classes": {
                "local_write": {
                    "trust_level": "medium",
                    "requires_approval": True,
                    "budget_multiplier": 2.0,
                }
            },
            "file_operations": {"blocked_patterns": ["*.env"], "approval_required_patterns": []},
        },
        db_path=str(tmp_path / "mcp.db"),
    )
    executor = BeastCLIExecutor(mcp_broker=broker)
    workflow = {
        "required_gates": [],
        "steps": [
            {
                "step_id": "write_file",
                "role": "nemoclaw",
                "action": "Write approved scratch file",
                "target": "scratch.txt",
                "content": "write-safe\n",
            }
        ],
    }

    result = executor.execute(
        objective="Write safe scratch file",
        workflow=workflow,
        context_packet={},
        mode="nemoclaw",
        dry_run=False,
        approved=True,
        workspace_root=str(tmp_path),
        use_ollama=False,
    )

    assert result["status"] == "succeeded"
    assert (tmp_path / "scratch.txt").read_text(encoding="utf-8") == "write-safe\n"
    assert result["summary"]["executed_count"] == 1


def test_hermes_plan_binds_swarm_roles():
    executor = BeastCLIExecutor()
    workflow = {
        "required_gates": [],
        "swarm": {
            "used": True,
            "status": "ready",
            "execution_capability": "advisory",
            "roles": ["conductor", "cartographer", "critic"],
        },
    }

    plan = executor.plan(
        objective="Coordinate swarm over provider diagnostic",
        workflow=workflow,
        context_packet={},
        mode="hermes",
        use_ollama=False,
    )

    assert plan["profile"]["mode"] == "hermes"
    assert plan["swarm_governance"]["routing"]["coordinator"] == "hermes"
    assert plan["swarm_binding"]["used"] is True
    assert plan["swarm_binding"]["roles"] == ["conductor", "cartographer", "critic"]
    assert "sentinel" in plan["swarm_binding"]["role_lanes"]
    assert any(action["action_id"].startswith("swarm_") for action in plan["actions"])


def test_openclaw_plan_shapes_actions_from_ranked_insight():
    executor = BeastCLIExecutor()
    insight_packet = {
        "ranked": True,
        "summary": {
            "evidence_count": 1,
            "top_insight": {
                "evidence_id": "ev_auth",
                "provider": "huggingface",
                "severity": "high",
                "expected_value": 0.81,
                "summary": "Credential mapping is missing.",
            },
            "handoff_recommendation": "Send ranked evidence.",
        },
        "evidence": [
            {
                "evidence_id": "ev_auth",
                "provider": "huggingface",
                "severity": "high",
                "expected_value": 0.81,
                "summary": "Credential mapping is missing.",
                "recommended_actions": ["Set HF_TOKEN before retrying"],
            }
        ],
    }

    plan = executor.plan(
        objective="Diagnose Hugging Face",
        workflow={"required_gates": [], "steps": []},
        context_packet={},
        insight_packet=insight_packet,
        mode="openclaw",
        use_ollama=False,
    )

    assert plan["local_insight"]["available"] is True
    assert plan["local_insight"]["evidence_count"] == 1
    assert any(action["action_id"].startswith("inspect_insight") for action in plan["actions"])
    assert any(action.get("summary") == "Set HF_TOKEN before retrying" for action in plan["actions"])


def test_zeroclaw_is_planning_only_even_when_execute_requested():
    executor = BeastCLIExecutor()

    result = executor.execute(
        objective="Plan only",
        workflow={"required_gates": [], "steps": [{"step_id": "prepare_task", "role": "conductor", "action": "prepare"}]},
        context_packet={"included_evidence": [{"kind": "file_snippet", "source": "notes.md"}]},
        mode="zeroclaw",
        dry_run=False,
        approved=True,
        use_ollama=False,
    )

    assert result["plan"]["profile"]["mode"] == "zeroclaw"
    assert result["status"] == "blocked"
    assert all(item["reason"] == "zeroclaw_planning_only" for item in result["results"])


@pytest.mark.asyncio
async def test_beast_cli_endpoints_plan_and_dry_run_execute():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        plan = await client.post(
            "/edgek/beast-cli/plan",
            json={
                "user_request": "Inspect app/main.py with Openclaw",
                "task_class": "small_patch",
                "run_swarm": True,
                "use_ollama": False,
            },
        )
        execution = await client.post(
            "/edgek/beast-cli/execute",
            json={
                "user_request": "Inspect app/main.py with Openclaw",
                "task_class": "small_patch",
                "dry_run": True,
                "use_ollama": False,
            },
        )

    assert plan.status_code == 200
    assert plan.json()["beast_object_type"] == "beast_cli_plan"
    assert plan.json()["profile"]["mode"] == "openclaw"
    assert plan.json()["session_handshake"]["beast_object_type"] == "beast_session_handshake"
    assert "phase_timings_ms" in plan.json()["preflight"]
    assert execution.status_code == 200
    assert execution.json()["beast_object_type"] == "beast_cli_execution"
    assert execution.json()["status"] in ("dry_run", "blocked")

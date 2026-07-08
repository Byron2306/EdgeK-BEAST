import pytest
from httpx import ASGITransport, AsyncClient

from app.cli.api import BeastApiClient
from app.kernel.adapters.provider_handoff import build_provider_handoff
from app.kernel.policy.architecture_decisions import architecture_decision_register
from app.kernel.security.safety_governor import SafetyGovernor
from app.main import app
from app.mcp.runtime import BeastToolRuntime


def test_architecture_decision_register_marks_adrs_accepted_implemented():
    register = architecture_decision_register()

    assert register["beast_object_type"] == "beast_architecture_decision_register"
    assert register["decision_count"] == 8
    assert {item["status"] for item in register["decisions"]} == {"accepted_implemented"}
    assert register["enforcement_summary"]["mutation_path"].startswith("SourcePlan")
    assert "Action IR" in register["enforcement_summary"]["provider_contract"]


@pytest.mark.asyncio
async def test_architecture_decisions_are_exposed_over_http_and_mcp():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        http = (await client.get("/edgek/architecture-decisions")).json()
    mcp = BeastToolRuntime().call_tool("beast_architecture_decisions")

    assert http["decision_count"] == 8
    assert mcp["decision_count"] == 8
    assert http["decisions"][0]["adr_id"] == "ADR-001"
    assert mcp["decisions"][-1]["adr_id"] == "ADR-008"


def test_sourceplan_scorecard_carries_all_architecture_invariants(tmp_path):
    target = tmp_path / "service.py"
    target.write_text("def value():\n    return 1\n", encoding="utf-8")
    client = BeastApiClient("http://offline", workspace=tmp_path)
    old_hash = client._file_hash_text(target.read_text(encoding="utf-8"))

    scorecard = client.sourceplan_scorecard({
        "plan_id": "adr_scorecard",
        "objective": "Update service through SourcePlan",
        "operations": [{
            "op_id": "op_1",
            "op": "replace_exact",
            "path": "service.py",
            "old": "return 1",
            "new": "return 2",
            "expected_hash": old_hash,
            "selected": True,
            "action_ir_id": "act_1",
            "action_ir_type": "replace_exact",
        }],
    }).data
    contract = scorecard["architecture_contract"]
    invariants = contract["invariants"]

    assert set(contract["adr_status"]) == {f"ADR-{idx:03d}" for idx in range(1, 9)}
    assert invariants["governance_first"]["authoritative_mutation_path"] == "sourceplan"
    assert invariants["receipt_authority"]["workspace_graph_role"] == "advisory"
    assert invariants["optional_code_cortex"]["hard_dependency"] is False
    assert invariants["action_ir_primary"]["compiled_operations"] == 1
    assert invariants["mode_permissions"]["selected_mode"] in {"implementer", "reviewer"}
    assert invariants["compiled_project_instructions"]["raw_instruction_paste_allowed"] is False
    assert scorecard["source_workbench"]["architecture_contract"]["adr_count"] == 8


def test_provider_handoff_requires_action_ir_and_local_sourceplan_compile(tmp_path):
    (tmp_path / "service.py").write_text("def value():\n    return 1\n", encoding="utf-8")

    handoff = build_provider_handoff(tmp_path, "Update value", ["service.py"], "local")
    output_rules = handoff["output"]["rules"]

    assert any("Action IR" in rule for rule in output_rules)
    assert any("SourcePlan" in rule for rule in output_rules)
    assert handoff["verify"]["required"] is True


def test_safety_governor_attaches_adr_008_to_bootstrap_commands(tmp_path):
    receipt = SafetyGovernor(tmp_path).classify_command("npm install", mode="architect", record=False)
    contract = receipt["architecture_contract"]

    assert receipt["decision"] == "sandbox/worktree_only"
    assert contract["adr_status"]["ADR-008"] == "accepted_implemented"
    assert contract["invariants"]["bootstrap_safety"]["implicit_trust"] is False
    assert contract["invariants"]["bootstrap_safety"]["safety_decision"] == "sandbox/worktree_only"

import pytest

from app.kernel.agents.sourceplan_approval import VerifiedDiffSourcePlan


def _inputs():
    return {
        "action_ir": {"kind": "beast.action_intent.v1", "actions": [{"type": "replace_exact", "target": {"path": "pricing.py"}}]},
        "diff": {"stat": " pricing.py | 1 +-", "diff": "-old\n+new\n"},
        "execution": {"mutation_applied": True, "receipt_digest": "sha256:mutation", "authority": {"approval_id": "canonical-agent-tools"}},
        "verification": {"status": "passed", "passed": True, "fresh": True},
        "forge_assistance": {"assistance_digest": "sha256:forge"},
        "crystal_assistance": {"assistance_key": "sha256:crystal"},
        "model_contribution": {"model_packet_digest": "sha256:model"},
    }


def test_verified_diff_builds_pending_sourceplan_and_binds_approval():
    builder = VerifiedDiffSourcePlan()
    plan = builder.build(**_inputs())
    approval = builder.approve(plan, operator_id="operator-1", reason="reviewed focused invoice fix")

    assert plan["status"] == "review_pending"
    assert plan["operator_decision"] == "pending"
    assert plan["changed_paths"] == ["pricing.py"]
    assert plan["plan_digest"].startswith("sha256:")
    assert approval["status"] == "approved"
    assert approval["approval"]["one_use"] is True
    assert approval["approval"]["plan_digest"] == plan["plan_digest"]


def test_sourceplan_requires_fresh_passing_verification():
    inputs = _inputs()
    inputs["verification"] = {"status": "failed", "passed": False}
    with pytest.raises(PermissionError, match="passing verification"):
        VerifiedDiffSourcePlan().build(**inputs)

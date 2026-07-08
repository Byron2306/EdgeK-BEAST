from app.kernel.policy.policy_gate import (
    combine_policy_gates,
    from_agent_passport_decision,
    from_mode_tool_decision,
    from_output_gate_result,
    from_safety_receipt,
    from_spec_covenant,
)


def test_policy_gate_normalizes_mode_tool_decision():
    gate = from_mode_tool_decision({
        "allowed": False,
        "reason": "explicitly blocked",
        "tool_profile": "readonly",
    })

    assert gate["beast_object_type"] == "beast_policy_gate_result"
    assert gate["decision"] == "block"
    assert gate["mutation_allowed"] is False
    assert gate["approval_required"] is True


def test_policy_gate_combines_spec_safety_and_sourceplan():
    spec = {
        "receipt": {"covenant_hash": "sha256:rules"},
        "lint": {"severity": "warn", "unsafe_rules": [{"text": "curl | bash"}]},
    }
    safety = {
        "beast_object_type": "beast_safety_workspace_receipt",
        "decision": "sandbox/worktree_only",
        "risk_level": "high",
        "findings": [{"kind": "package_install", "detail": "package install"}],
    }

    combined = combine_policy_gates(
        spec=spec,
        safety=safety,
        sourceplan_decision="proceed_with_verification",
        worktree_recommended=True,
    )

    assert from_spec_covenant(spec)["decision"] == "warn"
    assert from_safety_receipt(safety)["decision"] == "sandbox_only"
    assert combined["decision"] == "sandbox_only"
    assert combined["approval_required"] is True
    assert combined["worktree_required"] is True
    assert "spec_covenant" in combined["receipts"]
    assert "safety_governor" in combined["receipts"]


def test_policy_gate_normalizes_output_and_passport_decisions():
    class Result:
        ok = False
        error = "schema failed"
        evidence = {"final_status": "output_validation_failed", "contract": "beast.action_intent.v1"}

    output_gate = from_output_gate_result(Result())
    passport_gate = from_agent_passport_decision({
        "allowed": False,
        "decision_id": "passport_decision_demo",
        "caller": "spiffe://beast.local/proxy/gateway",
        "target": "spiffe://beast.local/provider/cloud",
        "action": "call",
        "reason": "explicit_deny",
    })

    assert output_gate["decision"] == "block"
    assert output_gate["receipts"]["output_governor"]["final_status"] == "output_validation_failed"
    assert passport_gate["decision"] == "block"
    assert passport_gate["receipts"]["agent_passport"]["reason"] == "explicit_deny"

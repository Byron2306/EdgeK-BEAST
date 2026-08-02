from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone

import pytest

from app.kernel.approvals import ApprovalContractFactory, ApprovalScope, ApprovalState, require_transition

NOW = datetime(2026, 7, 19, 12, 0, tzinfo=timezone.utc)


def base_payload():
    return {
        "approval_id": "approval_123",
        "run_id": "run_123",
        "step_id": "step_7",
        "agent_id": "agent:beast",
        "model_id": "model:test",
        "provider_id": "provider:local",
        "tool_id": "workspace.apply_patch",
        "tool_version": "1",
        "arguments": {"path": "app/example.py", "patch_digest": "sha256:abc"},
        "workspace_id": "workspace:repo",
        "execution_target": "local",
        "affected_resources": ["app/example.py"],
        "data_egress": [],
        "expected_side_effects": ["isolated worktree mutation"],
        "risk_class": "HIGH",
        "reason": "Apply the reviewed patch inside the mission worktree.",
        "budget_impact": {"tool_calls": 1, "wall_seconds": 5},
        "evidence_policy": {"level": "full"},
        "requested_scope": "ONCE",
        "permission_mode": "GUIDED",
        "policy_generation": "policy:7",
        "expiry_seconds": 600,
    }


def test_request_is_deterministic_and_valid():
    factory = ApprovalContractFactory()
    first = factory.create_request(base_payload(), now=NOW)
    second = factory.create_request(base_payload(), now=NOW)
    assert first == second
    factory.validate_request(first)
    assert first["request_digest"].startswith("sha256:")


def test_request_digest_detects_tampering():
    factory = ApprovalContractFactory()
    request = factory.create_request(base_payload(), now=NOW)
    tampered = deepcopy(request)
    tampered["arguments"]["path"] = "app/other.py"
    with pytest.raises(ValueError, match="digest mismatch"):
        factory.validate_request(tampered)


def test_approved_decision_is_request_and_policy_bound():
    factory = ApprovalContractFactory()
    request = factory.create_request(base_payload(), now=NOW)
    decision = factory.create_decision(request, {
        "operator_id": "operator:byron",
        "decision": "APPROVE",
        "scope": "ONCE",
        "reason": "Reviewed exact arguments.",
    }, now=NOW)
    factory.validate_decision(decision, request=request)
    assert decision["scope"] == ApprovalScope.ONCE.value


def test_negative_decision_requires_reason_and_no_scope():
    factory = ApprovalContractFactory()
    request = factory.create_request(base_payload(), now=NOW)
    with pytest.raises(ValueError, match="require a reason"):
        factory.create_decision(request, {"operator_id": "operator:x", "decision": "REJECT"}, now=NOW)
    with pytest.raises(ValueError, match="not an approval scope"):
        factory.create_decision(request, {
            "operator_id": "operator:x", "decision": "PERMANENTLY_DENY", "reason": "policy", "scope": "ONCE"
        }, now=NOW)


def test_edit_and_approve_requires_edited_once_scope():
    factory = ApprovalContractFactory()
    request = factory.create_request(base_payload(), now=NOW)
    with pytest.raises(ValueError, match="EDITED_SCOPE_ONCE"):
        factory.create_decision(request, {
            "operator_id": "operator:x", "decision": "EDIT_AND_APPROVE", "scope": "ONCE"
        }, now=NOW)


def test_legal_transition_contract_and_digest():
    factory = ApprovalContractFactory()
    request = factory.create_request(base_payload(), now=NOW)
    transition = factory.create_transition(
        request,
        from_state=ApprovalState.REQUESTED,
        to_state=ApprovalState.PENDING,
        actor="beast-runtime",
        reason="queued for operator review",
        now=NOW,
    )
    factory.validate_transition(transition, request=request)
    assert transition["to_state"] == "PENDING"


def test_illegal_transition_fails_closed():
    with pytest.raises(ValueError, match="illegal approval transition"):
        require_transition("REQUESTED", "CONSUMED")


def test_expiry_is_bounded():
    factory = ApprovalContractFactory()
    payload = base_payload()
    payload["expiry_seconds"] = 90000
    with pytest.raises(ValueError, match="between 30 and 86400"):
        factory.create_request(payload, now=NOW)


def test_missing_identity_fields_fail_closed():
    factory = ApprovalContractFactory()
    payload = base_payload()
    payload["step_id"] = ""
    with pytest.raises(ValueError, match="step_id is required"):
        factory.create_request(payload, now=NOW)

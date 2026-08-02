from copy import deepcopy

import pytest

from app.kernel.approvals import ApprovalRiskClassifier, RichApprovalEnvelopeBuilder, policy_from_payload


def base_classification(requirement_action=None):
    action = {
        "tool_id": "workspace.apply_patch", "tool_version": "1", "tool_class": "ISOLATED_MUTATION",
        "workspace_id": "workspace:repo", "execution_target": "local", "permission_mode": "GUIDED",
        "read_only": False, "trusted_workspace": True, "worktree_bound": True,
        "affected_resources": ["app/example.py"], "data_egress": [], "network_domains": [],
    }
    if requirement_action:
        action.update(requirement_action)
    return ApprovalRiskClassifier().classify(action, policy=policy_from_payload({"generation": "policy:44"}))


def request_payload():
    return {
        "run_id": "run_44", "step_id": "step_9", "agent_id": "agent:beast",
        "model_id": "model:coder", "provider_id": "provider:local",
        "tool_id": "workspace.apply_patch", "tool_version": "1",
        "arguments": {"path": "app/example.py", "token": "super-secret", "patch": "x" * 300},
        "workspace_id": "workspace:repo", "execution_target": "local",
        "affected_resources": ["app/example.py"], "data_egress": [],
        "expected_side_effects": ["isolated worktree mutation"], "risk_class": "HIGH",
        "reason": "Apply an exact patch in the mission worktree.",
        "budget_impact": {"tool_calls": 1, "wall_seconds": 5},
        "evidence_policy": {"level": "full"}, "requested_scope": "ONCE",
        "permission_mode": "GUIDED", "policy_generation": "policy:44", "expiry_seconds": 600,
    }


def build():
    return RichApprovalEnvelopeBuilder().build({
        "classification": base_classification(), "request": request_payload(),
        "affected_files": ["app/example.py"], "commands": [], "urls": [],
        "external_services": [], "operator_summary": "Review the exact isolated patch.",
    })


def test_builds_and_verifies_rich_envelope():
    envelope = build()
    assert envelope["beast_object_type"] == "beast_rich_approval_request_envelope"
    assert RichApprovalEnvelopeBuilder().verify(envelope)
    assert envelope["authority"] == "approval_request_description_only"
    assert envelope["capability_issued"] is False
    assert envelope["execution_authorized"] is False


def test_sensitive_arguments_are_redacted_and_bound():
    envelope = build()
    assert envelope["argument_view"]["token"]["redacted"] is True
    assert envelope["argument_view"]["patch"]["truncated"] is True
    assert envelope["argument_digest"].startswith("sha256:")


def test_tampered_classification_is_rejected():
    classification = base_classification()
    classification["risk_class"] = "LOW"
    with pytest.raises(ValueError, match="invalid or tampered"):
        RichApprovalEnvelopeBuilder().build({"classification": classification, "request": request_payload()})


def test_auto_allow_does_not_create_envelope():
    classification = base_classification({"tool_class": "READ_ONLY", "read_only": True, "worktree_bound": False, "tool_id": "workspace.read"})
    request = request_payload(); request.update({"tool_id": "workspace.read", "risk_class": "LOW"})
    with pytest.raises(ValueError, match="does not require"):
        RichApprovalEnvelopeBuilder().build({"classification": classification, "request": request})


def test_request_binding_mismatch_is_rejected():
    request = request_payload(); request["execution_target"] = "ssh"
    with pytest.raises(ValueError, match="does not match"):
        RichApprovalEnvelopeBuilder().build({"classification": base_classification(), "request": request})


def test_argument_tamper_breaks_verification():
    envelope = build(); broken = deepcopy(envelope)
    broken["approval_request"]["arguments"]["path"] = "app/other.py"
    assert not RichApprovalEnvelopeBuilder().verify(broken)


def test_authority_widening_breaks_verification():
    envelope = build(); envelope["execution_authorized"] = True
    assert not RichApprovalEnvelopeBuilder().verify(envelope)


def test_envelope_digest_recomputes_from_same_semantics():
    from app.kernel.approvals.digests import semantic_payload, sha256_digest
    envelope = build()
    assert envelope["envelope_digest"] == sha256_digest(semantic_payload(envelope, exclude={"envelope_digest"}))

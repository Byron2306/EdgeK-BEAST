from __future__ import annotations

from copy import deepcopy

import pytest

from app.kernel.approvals import (
    ApprovalContractFactory,
    ApprovalRiskClassifier,
    ApprovalRiskPolicy,
    ApprovalScopeEngine,
    RichApprovalEnvelopeBuilder,
)


def make_chain(*, scope="ONCE", risk="MEDIUM", tool_class="ISOLATED_MUTATION", decision="APPROVE", edited=False, permission_mode="GUIDED"):
    classifier = ApprovalRiskClassifier()
    classification = classifier.classify(
        {
            "tool_id": "workspace.apply_patch" if tool_class != "READ_ONLY" else "workspace.read_range",
            "tool_version": "1",
            "tool_class": tool_class,
            "workspace_id": "workspace:repo",
            "execution_target": "local",
            "permission_mode": permission_mode,
            "read_only": tool_class == "READ_ONLY",
            "trusted_workspace": True,
            "worktree_bound": tool_class != "READ_ONLY",
            "affected_resources": ["app/example.py"],
            "data_egress": [],
            "network_domains": [],
        },
        policy=ApprovalRiskPolicy(generation="policy:45", trusted_targets=("local",)),
    )
    request_data = {
        "run_id": "run_45", "step_id": "step_1", "agent_id": "agent:beast",
        "model_id": "model:coder", "provider_id": "provider:local",
        "arguments": {"path": "app/example.py", "mode": "exact"},
        "affected_resources": ["app/example.py"], "data_egress": [],
        "expected_side_effects": ["isolated worktree mutation"] if tool_class != "READ_ONLY" else [],
        "reason": "Perform the exact approved operation.", "budget_impact": {"tool_calls": 1},
        "evidence_policy": {"level": "full"}, "requested_scope": scope,
        "expiry_seconds": 600, "risk_class": classification["risk_class"],
    }
    envelope = RichApprovalEnvelopeBuilder().build({"classification": classification, "request": request_data})
    factory = ApprovalContractFactory()
    decision_payload = {"operator_id": "operator:byron", "decision": decision, "scope": scope, "policy_generation": "policy:45"}
    if edited:
        decision_payload["edited_arguments"] = {"path": "app/example.py", "mode": "edited"}
        decision_payload["edited_resources"] = ["app/example.py"]
    decision_record = factory.create_decision(envelope["approval_request"], decision_payload)
    return classification, envelope, decision_record


def candidate(envelope, classification, *, run_id=None):
    request = dict(envelope["approval_request"])
    request["approval_id"] = "approval_candidate"
    request["step_id"] = "step_2"
    if run_id is not None:
        request["run_id"] = run_id
    request.pop("request_digest", None)
    factory = ApprovalContractFactory()
    payload = dict(request)
    payload["expiry_seconds"] = 600
    for key in ("created_at", "expires_at", "state", "version", "beast_object_type"):
        payload.pop(key, None)
    rebuilt = factory.create_request(payload)
    return rebuilt, classification


def test_once_scope_matches_exact_call():
    classification, envelope, decision = make_chain()
    engine = ApprovalScopeEngine()
    grant = engine.create_grant({"envelope": envelope, "decision": decision})
    request, candidate_classification = candidate(envelope, classification)
    receipt = engine.evaluate({"grant": grant, "candidate_request": request, "candidate_classification": candidate_classification})
    assert receipt["result"] == "MATCH"
    assert engine.verify_grant(grant) and engine.verify_match(receipt)


def test_equivalent_run_scope_rejects_other_run():
    classification, envelope, decision = make_chain(scope="EQUIVALENT_CALLS_THIS_RUN", tool_class="READ_ONLY", permission_mode="REVIEW")
    engine = ApprovalScopeEngine(); grant = engine.create_grant({"envelope": envelope, "decision": decision})
    request, cc = candidate(envelope, classification, run_id="run_other")
    receipt = engine.evaluate({"grant": grant, "candidate_request": request, "candidate_classification": cc})
    assert receipt["result"] == "NO_MATCH" and "run_scope_mismatch" in receipt["reasons"]


def test_resource_widening_is_rejected():
    classification, envelope, decision = make_chain(scope="TOOL_SCOPE_THIS_WORKSPACE", tool_class="READ_ONLY", permission_mode="REVIEW")
    engine = ApprovalScopeEngine(); grant = engine.create_grant({"envelope": envelope, "decision": decision})
    request, cc = candidate(envelope, classification)
    request["affected_resources"] = ["app/example.py", "app/other.py"]
    request["request_digest"] = "sha256:tampered"
    receipt = engine.evaluate({"grant": grant, "candidate_request": request, "candidate_classification": cc})
    assert receipt["result"] == "DENIED"


def test_high_risk_cannot_receive_reusable_scope():
    classification, envelope, decision = make_chain(scope="TOOL_SCOPE_THIS_WORKSPACE", risk="HIGH")
    with pytest.raises(ValueError, match="single-use"):
        ApprovalScopeEngine().create_grant({"envelope": envelope, "decision": decision})


def test_read_only_target_requires_read_only_tool():
    classification, envelope, decision = make_chain(scope="READ_ONLY_THIS_TARGET", tool_class="ISOLATED_MUTATION")
    with pytest.raises(ValueError, match="read-only"):
        ApprovalScopeEngine().create_grant({"envelope": envelope, "decision": decision})


def test_read_only_target_matches_safe_read():
    classification, envelope, decision = make_chain(scope="READ_ONLY_THIS_TARGET", tool_class="READ_ONLY", permission_mode="REVIEW")
    engine = ApprovalScopeEngine(); grant = engine.create_grant({"envelope": envelope, "decision": decision})
    request, cc = candidate(envelope, classification)
    receipt = engine.evaluate({"grant": grant, "candidate_request": request, "candidate_classification": cc})
    assert receipt["result"] == "MATCH"


def test_edited_scope_binds_edited_call():
    classification, envelope, decision = make_chain(scope="EDITED_SCOPE_ONCE", decision="EDIT_AND_APPROVE", edited=True)
    engine = ApprovalScopeEngine(); grant = engine.create_grant({"envelope": envelope, "decision": decision})
    request, cc = candidate(envelope, classification)
    request = dict(request); request.pop("request_digest", None); request["arguments"] = {"path": "app/example.py", "mode": "edited"}
    factory = ApprovalContractFactory(); payload = dict(request)
    for key in ("created_at", "expires_at", "state", "version", "beast_object_type"):
        payload.pop(key, None)
    payload["expiry_seconds"] = 600
    request = factory.create_request(payload)
    receipt = engine.evaluate({"grant": grant, "candidate_request": request, "candidate_classification": cc})
    assert receipt["result"] == "MATCH"


def test_tampered_grant_is_denied():
    classification, envelope, decision = make_chain()
    engine = ApprovalScopeEngine(); grant = engine.create_grant({"envelope": envelope, "decision": decision})
    bad = deepcopy(grant); bad["tool_id"] = "git.push"
    request, cc = candidate(envelope, classification)
    receipt = engine.evaluate({"grant": bad, "candidate_request": request, "candidate_classification": cc})
    assert receipt["result"] == "DENIED" and "invalid_scope_grant" in receipt["reasons"]


def test_scope_grant_never_issues_authority():
    classification, envelope, decision = make_chain()
    grant = ApprovalScopeEngine().create_grant({"envelope": envelope, "decision": decision})
    assert grant["authority"] == "scope_matching_only"
    assert grant["capability_issued"] is False
    assert grant["execution_authorized"] is False

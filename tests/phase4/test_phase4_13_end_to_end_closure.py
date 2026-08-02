from __future__ import annotations

from copy import deepcopy

import pytest

from app.kernel.agents.run_engine import AgentRunEngine
from app.kernel.approvals import (
    ApprovalContractFactory, ApprovalRiskClassifier, ApprovalRiskPolicy,
    ApprovalScopeEngine, DurableApprovalCardStore, ExactStepResumeRuntime,
    PermissionModeEngine, Phase4EndToEndClosure, RequestBoundCapabilityIssuer,
    RichApprovalEnvelopeBuilder,
)


def chain(root):
    policy = ApprovalRiskPolicy(generation="policy:413", trusted_targets=("local",))
    action = {
        "tool_id": "workspace.read_range", "tool_version": "1", "tool_class": "READ_ONLY",
        "workspace_id": "workspace:repo", "execution_target": "local", "permission_mode": "REVIEW",
        "read_only": True, "trusted_workspace": True, "worktree_bound": False,
        "affected_resources": ["app/example.py"], "data_egress": [], "network_domains": [],
    }
    classification = ApprovalRiskClassifier().classify(action, policy=policy)
    envelope = RichApprovalEnvelopeBuilder().build({"classification": classification, "request": {
        "approval_id": "approval_413", "run_id": "run_413", "step_id": "step_413",
        "agent_id": "agent:beast", "model_id": "model:coder", "provider_id": "provider:local",
        "tool_id": "workspace.read_range", "tool_version": "1",
        "arguments": {"path": "app/example.py", "start": 1, "end": 20},
        "workspace_id": "workspace:repo", "execution_target": "local",
        "affected_resources": ["app/example.py"], "data_egress": [], "expected_side_effects": [],
        "risk_class": classification["risk_class"], "reason": "Read the exact approved source range.",
        "budget_impact": {"tool_calls": 1}, "evidence_policy": {"level": "summary"},
        "requested_scope": "ONCE", "permission_mode": "REVIEW", "policy_generation": "policy:413",
        "expiry_seconds": 600,
    }})
    request = envelope["approval_request"]
    cards = DurableApprovalCardStore(root)
    cards.create(envelope)
    decision = ApprovalContractFactory().create_decision(request, {
        "operator_id": "operator:byron", "decision": "APPROVE", "scope": "ONCE",
        "policy_generation": "policy:413",
    })
    card = cards.decide(request["approval_id"], decision)
    scopes = ApprovalScopeEngine()
    grant = scopes.create_grant({"envelope": envelope, "decision": decision})
    match = scopes.evaluate({"grant": grant, "candidate_request": request, "candidate_classification": classification})
    capability = RequestBoundCapabilityIssuer().issue({
        "classification": classification, "request": request, "decision": decision,
        "grant": grant, "scope_match": match,
    })
    engine = AgentRunEngine(root)
    engine.create_run(session_id="session_413", objective="closure", run_id="run_413")
    engine.store.transition("run_413", "waiting_for_approval")
    engine.merge_checkpoint("run_413", {"suspended_step": {"step_id": "step_413", "approval_id": "approval_413"}})
    consumption = ExactStepResumeRuntime(root).consume_and_resume(capability=capability, request=request)
    modes = PermissionModeEngine()
    mode_profile = modes.profile("REVIEW")
    mode_decision = modes.evaluate(action, policy=policy)
    return {
        "request": request, "classification": classification, "envelope": envelope, "card": card,
        "decision": decision, "scope_grant": grant, "scope_match": match, "capability": capability,
        "consumption_receipt": consumption, "mode_profile": mode_profile, "mode_decision": mode_decision,
    }


def test_complete_phase4_chain_closes(tmp_path):
    payload = chain(tmp_path)
    receipt = Phase4EndToEndClosure(tmp_path).close(payload)
    assert receipt["closure_status"] == "PASS"
    assert receipt["restart_safe"] is True
    assert receipt["exact_step_bound"] is True
    assert receipt["replay_denied"] is True
    assert Phase4EndToEndClosure.verify(receipt)


def test_closure_receipt_grants_no_authority(tmp_path):
    receipt = Phase4EndToEndClosure(tmp_path).close(chain(tmp_path))
    assert receipt["authority"] == "phase4_proof_receipt_only"
    assert receipt["grants_execution_authority"] is False
    assert receipt["grants_workspace_mutation"] is False
    assert receipt["grants_promotion_authority"] is False


def test_tampered_request_fails_closure(tmp_path):
    payload = chain(tmp_path); payload["request"] = deepcopy(payload["request"])
    payload["request"]["step_id"] = "other"
    with pytest.raises(ValueError): Phase4EndToEndClosure(tmp_path).close(payload)


def test_tampered_envelope_fails_closure(tmp_path):
    payload = chain(tmp_path); payload["envelope"] = deepcopy(payload["envelope"])
    payload["envelope"]["execution_authorized"] = True
    with pytest.raises(ValueError, match="rich_envelope"): Phase4EndToEndClosure(tmp_path).close(payload)


def test_scope_non_match_fails_closure(tmp_path):
    payload = chain(tmp_path); payload["scope_match"] = deepcopy(payload["scope_match"])
    payload["scope_match"]["result"] = "NO_MATCH"
    with pytest.raises(ValueError): Phase4EndToEndClosure(tmp_path).close(payload)


def test_capability_tamper_fails_closure(tmp_path):
    payload = chain(tmp_path); payload["capability"] = deepcopy(payload["capability"])
    payload["capability"]["tool_version"] = "999"
    with pytest.raises(ValueError, match="request_bound_capability"): Phase4EndToEndClosure(tmp_path).close(payload)


def test_consumption_replay_flag_widening_fails_closure(tmp_path):
    payload = chain(tmp_path); payload["consumption_receipt"] = deepcopy(payload["consumption_receipt"])
    payload["consumption_receipt"]["replay_allowed"] = True
    with pytest.raises(ValueError, match="consumption_receipt"): Phase4EndToEndClosure(tmp_path).close(payload)


def test_revoked_capability_fails_closure(tmp_path):
    payload = chain(tmp_path)
    closure = Phase4EndToEndClosure(tmp_path)
    closure.revocations.revoke({"target_type": "CAPABILITY", "target_id": payload["capability"]["capability_id"],
        "reason": "closure revocation proof", "operator_id": "operator:byron", "policy_generation": "policy:413"})
    with pytest.raises(ValueError, match="revoked"): closure.close(payload)


def test_card_survives_fresh_store_instance(tmp_path):
    payload = chain(tmp_path)
    restored = DurableApprovalCardStore(tmp_path).get("approval_413")
    assert restored["card_digest"] == payload["card"]["card_digest"]
    assert Phase4EndToEndClosure(tmp_path).close(payload)["restart_safe"] is True


def test_tampered_closure_receipt_fails_verification(tmp_path):
    receipt = Phase4EndToEndClosure(tmp_path).close(chain(tmp_path))
    receipt["future_authority_widened"] = True
    assert not Phase4EndToEndClosure.verify(receipt)

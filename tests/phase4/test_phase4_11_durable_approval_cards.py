from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest

from app.kernel.approvals import (
    ApprovalRiskClassifier,
    DurableApprovalCardStore,
    RichApprovalEnvelopeBuilder,
    policy_from_payload,
)


def envelope():
    action = {
        "tool_id": "workspace.apply_patch", "tool_version": "1", "tool_class": "ISOLATED_MUTATION",
        "workspace_id": "workspace:repo", "execution_target": "local", "permission_mode": "GUIDED",
        "read_only": False, "trusted_workspace": True, "worktree_bound": True,
        "affected_resources": ["app/example.py"], "data_egress": [], "network_domains": [],
    }
    classification = ApprovalRiskClassifier().classify(action, policy=policy_from_payload({"generation": "policy:411"}))
    request = {
        "run_id": "run_411", "step_id": "step_1", "agent_id": "agent:beast", "model_id": "model:coder",
        "provider_id": "provider:local", "tool_id": "workspace.apply_patch", "tool_version": "1",
        "arguments": {"path": "app/example.py", "token": "secret-value"}, "workspace_id": "workspace:repo",
        "execution_target": "local", "affected_resources": ["app/example.py"], "data_egress": [],
        "expected_side_effects": ["isolated mutation"], "risk_class": "HIGH", "reason": "Apply reviewed patch",
        "budget_impact": {"tool_calls": 1}, "evidence_policy": {"level": "full"}, "requested_scope": "ONCE",
        "permission_mode": "GUIDED", "policy_generation": "policy:411", "expiry_seconds": 600,
    }
    return RichApprovalEnvelopeBuilder().build({"classification": classification, "request": request, "operator_summary": "Review exact patch"})


def test_create_persists_complete_restart_safe_card(tmp_path):
    card = DurableApprovalCardStore(tmp_path).create(envelope())
    restored = DurableApprovalCardStore(tmp_path).get(card["approval_id"])
    assert restored == card
    assert restored["state"] == "PENDING"
    assert restored["redaction_status"] == "SAFE_VIEW_ONLY"
    assert restored["recovery"]["reconstruction_required"] is False


def test_card_retains_safe_view_not_raw_card_fields(tmp_path):
    card = DurableApprovalCardStore(tmp_path).create(envelope())
    assert card["envelope"]["argument_view"]["token"]["redacted"] is True
    assert "secret-value" not in str(card["envelope"]["argument_view"])


def test_card_is_bound_to_envelope_and_request_digests(tmp_path):
    card = DurableApprovalCardStore(tmp_path).create(envelope())
    assert card["request_digest"] == card["envelope"]["approval_request"]["request_digest"]
    assert card["envelope_digest"] == card["envelope"]["envelope_digest"]
    assert DurableApprovalCardStore(tmp_path).verify(card)


def test_tampered_envelope_is_rejected(tmp_path):
    broken = envelope(); broken["operator_summary"] = "changed"
    with pytest.raises(ValueError, match="invalid or tampered"):
        DurableApprovalCardStore(tmp_path).create(broken)


def test_duplicate_card_is_rejected(tmp_path):
    store = DurableApprovalCardStore(tmp_path); env = envelope(); store.create(env)
    with pytest.raises(ValueError, match="already exists"):
        store.create(env)


def test_bound_decision_updates_card_and_history(tmp_path):
    store = DurableApprovalCardStore(tmp_path); card = store.create(envelope())
    decision = {"decision": "APPROVE", "request_digest": card["request_digest"], "operator_id": "operator:1", "scope": "ONCE"}
    updated = store.decide(card["approval_id"], decision)
    assert updated["state"] == "APPROVED"
    assert updated["decision"] == decision
    assert updated["decision_history"] == [decision]


def test_wrong_request_digest_cannot_decide_card(tmp_path):
    store = DurableApprovalCardStore(tmp_path); card = store.create(envelope())
    with pytest.raises(ValueError, match="does not match"):
        store.decide(card["approval_id"], {"decision": "APPROVE", "request_digest": "sha256:nope"})


def test_terminal_card_cannot_be_decided_twice(tmp_path):
    store = DurableApprovalCardStore(tmp_path); card = store.create(envelope())
    decision = {"decision": "REJECT", "request_digest": card["request_digest"], "reason": "No"}
    store.decide(card["approval_id"], decision)
    with pytest.raises(ValueError, match="not awaiting"):
        store.decide(card["approval_id"], decision)


def test_event_chain_survives_restart(tmp_path):
    store = DurableApprovalCardStore(tmp_path); card = store.create(envelope())
    store.decide(card["approval_id"], {"decision": "REJECT", "request_digest": card["request_digest"], "reason": "No"})
    chain = DurableApprovalCardStore(tmp_path).verify_chain(card["approval_id"])
    assert chain["ok"] is True
    assert chain["event_count"] == 2


def test_card_grants_no_execution_authority(tmp_path):
    card = DurableApprovalCardStore(tmp_path).create(envelope())
    assert card["authority"] == "operator_review_record_only"
    assert card["capability_issued"] is False
    assert card["execution_authorized"] is False

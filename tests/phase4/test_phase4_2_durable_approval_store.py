from copy import deepcopy
from datetime import datetime, timedelta, timezone
import sqlite3
import pytest
from app.kernel.approvals import ApprovalContractFactory, ApprovalRecoveryService, DurableApprovalStore

NOW = datetime(2026,7,19,12,0,tzinfo=timezone.utc)

def payload(aid="approval_42", step="step_1"):
    return {"approval_id":aid,"run_id":"run_42","step_id":step,"agent_id":"agent:beast","model_id":"model:test","provider_id":"provider:local","tool_id":"tests.run","tool_version":"1","arguments":{"selector":"focused"},"workspace_id":"workspace:repo","execution_target":"local","affected_resources":["tests/"],"data_egress":[],"expected_side_effects":["subprocess"],"risk_class":"MEDIUM","reason":"Run focused tests","budget_impact":{"wall_seconds":30},"evidence_policy":{"level":"full"},"requested_scope":"ONCE","permission_mode":"GUIDED","policy_generation":"policy:8","expiry_seconds":600}

def test_persists_and_reopens(tmp_path):
    req=ApprovalContractFactory().create_request(payload(),now=NOW); s=DurableApprovalStore(tmp_path); out=s.create(req)
    assert out["state"]=="PENDING" and DurableApprovalStore(tmp_path).get(req["approval_id"])["request"]==req

def test_duplicate_id_and_active_run_step_fail_closed(tmp_path):
    f=ApprovalContractFactory(); s=DurableApprovalStore(tmp_path); s.create(f.create_request(payload(),now=NOW))
    with pytest.raises(ValueError): s.create(f.create_request(payload(),now=NOW))
    with pytest.raises(sqlite3.IntegrityError): s.create(f.create_request(payload("approval_other"),now=NOW))

def test_decision_and_transition_are_durable(tmp_path):
    f=ApprovalContractFactory(); req=f.create_request(payload(),now=NOW); s=DurableApprovalStore(tmp_path); s.create(req)
    dec=f.create_decision(req,{"operator_id":"operator:byron","decision":"APPROVE","scope":"ONCE","reason":"reviewed"},now=NOW)
    out=s.transition(req["approval_id"],to_state="APPROVED",actor="operator:byron",reason="reviewed",decision=dec)
    assert out["state"]=="APPROVED" and out["decision"]["decision"]=="APPROVE"

def test_event_chain_detects_tamper(tmp_path):
    f=ApprovalContractFactory(); req=f.create_request(payload(),now=NOW); s=DurableApprovalStore(tmp_path); s.create(req)
    assert s.verify_chain(req["approval_id"])["ok"]
    with sqlite3.connect(s.db_path) as db: db.execute("UPDATE approval_events SET event_json='{}' WHERE sequence=1")
    assert not s.verify_chain(req["approval_id"])["ok"]

def test_projection_rebuild_after_loss(tmp_path):
    f=ApprovalContractFactory(); req=f.create_request(payload(),now=NOW); s=DurableApprovalStore(tmp_path); s.create(req)
    with sqlite3.connect(s.db_path) as db: db.execute("DELETE FROM approval_projection")
    assert s.rebuild_projection()["approval_count"]==1 and s.get(req["approval_id"])["state"]=="PENDING"

def test_recovery_returns_exact_suspended_step_without_capability(tmp_path):
    req=ApprovalContractFactory().create_request(payload(),now=NOW); DurableApprovalStore(tmp_path).create(req)
    result=ApprovalRecoveryService(tmp_path).recover(now=NOW)
    assert result["pending"]==[{"approval_id":"approval_42","run_id":"run_42","step_id":"step_1","request_digest":req["request_digest"]}]
    assert result["capabilities_issued"]==0 and result["steps_resumed"]==0

def test_expiry_is_persisted(tmp_path):
    f=ApprovalContractFactory(); req=f.create_request(payload(),now=NOW); s=DurableApprovalStore(tmp_path); s.create(req)
    expired=s.expire_due(now=NOW+timedelta(seconds=601))
    assert expired==[req["approval_id"]] and s.get(req["approval_id"])["state"]=="EXPIRED"

def test_illegal_transition_rolls_back(tmp_path):
    f=ApprovalContractFactory(); req=f.create_request(payload(),now=NOW); s=DurableApprovalStore(tmp_path); s.create(req)
    with pytest.raises(ValueError): s.transition(req["approval_id"],to_state="CONSUMED",actor="x",reason="skip")
    assert s.get(req["approval_id"])["state"]=="PENDING"

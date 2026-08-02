from copy import deepcopy
from app.kernel.evidence.operator_approval import OperatorReviewApprovalEngine, digest_object, verify_receipt_digest

NOW="2026-07-19T12:00:00+00:00"

def handoff():
    core={
      "version":"3.8","beast_object_type":"beast_evidence_sourceplan_handoff_receipt","evidence_id":"crystal-1",
      "plan_id":"plan-1","disposition":"SOURCEPLAN_REVIEW_READY","sourceplan_digest":"sha256:"+"1"*64,
      "operations_digest":"sha256:"+"2"*64,"worktree_id":"wt-1","sourceplan_review_eligible":True,
      "sourceplan_apply_authorized":False,"workspace_mutation_authorized":False,"promotion_authorized":False,
      "phase2_governance_bypass_allowed":False
    }
    return {**core,"receipt_digest":digest_object(core)}

def decision(kind="APPROVE"):
    return {"operator_id":"operator:byron","decision":kind,"reason":"reviewed exact diff","review_acknowledged":True,
            "scope":"once","plan_id":"plan-1","sourceplan_digest":"sha256:"+"1"*64,
            "operations_digest":"sha256:"+"2"*64,"decided_at":NOW}

def run(h=None,d=None):
    return OperatorReviewApprovalEngine().resolve(handoff_receipt=h or handoff(),operator_decision=d or decision(),created_at=NOW,capability_nonce="fixed")

def test_approval_issues_one_use_capability():
    r=run(); assert r["disposition"]=="OPERATOR_APPROVED"; assert r["operator_approved"] is True
    assert r["sourceplan_apply_capability"]["scope"]=="once"; assert r["sourceplan_apply_authorized"] is False
    assert r["capability_consumed"] is False; assert verify_receipt_digest(r)

def test_rejection_issues_no_capability():
    r=run(d=decision("REJECT")); assert r["disposition"]=="OPERATOR_REJECTED"; assert r["sourceplan_apply_capability"] is None

def test_request_changes_issues_no_capability():
    r=run(d=decision("REQUEST_CHANGES")); assert r["disposition"]=="OPERATOR_CHANGES_REQUESTED"

def test_tampered_handoff_is_blocked():
    h=handoff(); h["plan_id"]="evil"; r=run(h=h); assert r["disposition"]=="OPERATOR_DECISION_BLOCKED"

def test_plan_binding_mismatch_is_blocked():
    d=decision(); d["plan_id"]="other"; assert "operator_plan_binding_mismatch" in run(d=d)["blockers"]

def test_digest_binding_mismatch_is_blocked():
    d=decision(); d["operations_digest"]="sha256:"+"9"*64; assert "operator_operations_digest_mismatch" in run(d=d)["blockers"]

def test_review_acknowledgement_required():
    d=decision(); d["review_acknowledged"]=False; assert "explicit_review_acknowledgement_required" in run(d=d)["blockers"]

def test_broad_scope_is_forbidden():
    d=decision(); d["scope"]="workspace"; assert "approval_scope_must_be_once" in run(d=d)["blockers"]

def test_receipt_is_deterministic_with_fixed_inputs():
    a=run(); b=run();
    # capability id is deliberately unique; semantic bindings remain deterministic
    assert a["review_digest"]==b["review_digest"] and a["request_digest"]==b["request_digest"]

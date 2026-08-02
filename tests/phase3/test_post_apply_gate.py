from app.kernel.evidence.post_apply_gate import PostApplyVerificationPromotionGate, digest_object


def signed(core):
    return {**core, "receipt_digest": digest_object(core)}


def fixtures():
    consumption = signed({
        "version":"3.10","beast_object_type":"beast_evidence_capability_consumption_receipt","evidence_id":"e1",
        "plan_id":"p1","worktree_id":"wt-1","disposition":"SOURCEPLAN_APPLIED","capability_consumed":True,
        "apply_succeeded":True,"rollback_performed":False,"sourceplan_digest":"sha256:"+"a"*64,
        "operations_digest":"sha256:"+"b"*64,"changed_files":["app/a.py"],"promotion_authorized":False,
        "phase2_governance_bypass_allowed":False,
    })
    files=[{"path":"app/a.py","digest":"sha256:"+"c"*64,"exists":True}]
    state={"files":files,"state_digest":digest_object(files)}
    verification=signed({
        "beast_object_type":"beast_post_apply_verification_receipt","consumption_receipt_digest":consumption["receipt_digest"],
        "plan_id":"p1","worktree_id":"wt-1","sourceplan_digest":consumption["sourceplan_digest"],
        "operations_digest":consumption["operations_digest"],"applied_state_digest":state["state_digest"],
        "overall_status":"PASS","workspace_clean":True,"verified_at":"2026-07-19T10:00:00+00:00",
        "checks":[{"check_id":x,"status":"PASS","receipt_digest":"sha256:"+str(i)*64} for i,x in enumerate(["content_safety","syntax","focused_tests"],1)]
    })
    rollback=signed({
        "beast_object_type":"beast_sourceplan_rollback_material_receipt","consumption_receipt_digest":consumption["receipt_digest"],
        "plan_id":"p1","worktree_id":"wt-1","materials":[{"path":"app/a.py","preimage_digest":"sha256:"+"d"*64}]
    })
    return consumption,verification,state,rollback


def test_promotion_eligible():
    c,v,s,r=fixtures(); out=PostApplyVerificationPromotionGate().evaluate(consumption_receipt=c,verification_receipt=v,applied_state=s,rollback_receipt=r,created_at="2026-07-19T10:05:00+00:00")
    assert out["disposition"]=="PROMOTION_ELIGIBLE" and out["promotion_eligible"] is True and out["promotion_authorized"] is False


def test_failed_required_check_blocks():
    c,v,s,r=fixtures(); v["checks"][1]["status"]="FAIL"; v=signed({k:x for k,x in v.items() if k!="receipt_digest"})
    out=PostApplyVerificationPromotionGate().evaluate(consumption_receipt=c,verification_receipt=v,applied_state=s,rollback_receipt=r,created_at="2026-07-19T10:05:00+00:00")
    assert out["disposition"]=="PROMOTION_INELIGIBLE" and "required_check_failed:syntax" in out["blockers"]


def test_tampered_consumption_blocks():
    c,v,s,r=fixtures(); c["changed_files"]=["evil.py"]
    out=PostApplyVerificationPromotionGate().evaluate(consumption_receipt=c,verification_receipt=v,applied_state=s,rollback_receipt=r,created_at="2026-07-19T10:05:00+00:00")
    assert "consumption_receipt_digest_invalid" in out["blockers"]


def test_state_drift_blocks():
    c,v,s,r=fixtures(); s["files"][0]["digest"]="sha256:"+"e"*64
    out=PostApplyVerificationPromotionGate().evaluate(consumption_receipt=c,verification_receipt=v,applied_state=s,rollback_receipt=r,created_at="2026-07-19T10:05:00+00:00")
    assert "applied_state_digest_invalid" in out["blockers"]


def test_missing_rollback_blocks():
    c,v,s,r=fixtures(); out=PostApplyVerificationPromotionGate().evaluate(consumption_receipt=c,verification_receipt=v,applied_state=s,rollback_receipt=None,created_at="2026-07-19T10:05:00+00:00")
    assert "rollback_material_receipt_required" in out["blockers"]

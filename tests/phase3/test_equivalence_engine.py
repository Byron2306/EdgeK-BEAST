from app.kernel.evidence.equivalence_engine import FreshVerificationEquivalenceEngine, digest_object

def signed(value):
    result = dict(value); result["receipt_digest"] = digest_object(result); return result

def reuse(mode="EXACT_REPLAY", disposition="PREPARED_EXACT_REPLAY"):
    return signed({"version":"3.6","beast_object_type":"beast_evidence_reuse_receipt","evidence_id":"crystal-1","requested_mode":mode,"disposition":disposition,"reuse_execution_authorized":True,"workspace_mutation_authorized":False,"promotion_authorized":False,"phase2_governance_bypass_allowed":False,"fresh_verification_required":True,"human_promotion_required":True,"worktree_id":"wt-1","worktree_root_digest":"sha256:root","current_fingerprint_digest":"sha256:current","candidate_fingerprint_digest":"sha256:candidate"})

def verification(r, statuses=None):
    statuses = statuses or {"content_safety":"PASS","syntax":"PASS","focused_tests":"PASS"}
    checks = [{"check_id":k,"status":v,"receipt_digest":"sha256:"+k} for k,v in statuses.items()]
    return signed({"beast_object_type":"beast_fresh_verification_receipt","reuse_receipt_digest":r["receipt_digest"],"worktree_id":"wt-1","worktree_root_digest":"sha256:root","current_fingerprint_digest":"sha256:current","phase2_worktree":True,"operator_workspace_touched":False,"overall_status":"PASS","checks":checks})

def evaluate(r, v, outcome):
    return FreshVerificationEquivalenceEngine().evaluate(reuse_receipt=r, verification_receipt=v, observed_outcome=outcome, created_at="2026-07-19T00:00:00Z")

def test_exact_equivalence_passes():
    r=reuse(); d=evaluate(r,verification(r),{"candidate_output_digest":"sha256:same","resulting_output_digest":"sha256:same","outcome_evidence_ref":"sha256:out"})
    assert d["disposition"]=="VERIFIED_EQUIVALENT" and d["sourceplan_synthesis_eligible"]
    assert not d["promotion_authorized"] and not d["workspace_mutation_authorized"]

def test_exact_mismatch_fails_closed():
    r=reuse(); d=evaluate(r,verification(r),{"candidate_output_digest":"sha256:a","resulting_output_digest":"sha256:b","outcome_evidence_ref":"sha256:out"})
    assert "exact_output_digest_mismatch" in d["blockers"]

def test_adaptation_passes_only_after_resolved_drift():
    r=reuse("ADAPTATION_SEED","PREPARED_ADAPTATION_SEED"); d=evaluate(r,verification(r),{"resulting_output_digest":"sha256:new","changed_paths":["app/x.py"],"drift_resolved":True,"outcome_evidence_ref":"sha256:out"})
    assert d["disposition"]=="VERIFIED_ADAPTED"

def test_missing_required_check_fails():
    r=reuse(); d=evaluate(r,verification(r,{"content_safety":"PASS","syntax":"PASS"}),{"candidate_output_digest":"sha256:a","resulting_output_digest":"sha256:a","outcome_evidence_ref":"sha256:out"})
    assert "required_check_missing:focused_tests" in d["blockers"]

def test_failed_required_check_fails():
    r=reuse(); d=evaluate(r,verification(r,{"content_safety":"PASS","syntax":"PASS","focused_tests":"FAIL"}),{"candidate_output_digest":"sha256:a","resulting_output_digest":"sha256:a","outcome_evidence_ref":"sha256:out"})
    assert "required_check_failed:focused_tests" in d["blockers"]

def test_binding_mismatch_fails():
    r=reuse(); v=verification(r); v["worktree_id"]="other"; v["receipt_digest"]=digest_object({k:x for k,x in v.items() if k!="receipt_digest"}); d=evaluate(r,v,{"candidate_output_digest":"sha256:a","resulting_output_digest":"sha256:a","outcome_evidence_ref":"sha256:out"})
    assert "verification_worktree_id_binding_mismatch" in d["blockers"]

def test_tamper_fails():
    r=reuse(); r["worktree_id"]="tampered"; d=evaluate(r,verification(r),{"candidate_output_digest":"sha256:a","resulting_output_digest":"sha256:a","outcome_evidence_ref":"sha256:out"})
    assert "reuse_receipt_digest_invalid" in d["blockers"]

def test_operator_workspace_touch_fails():
    r=reuse(); v=verification(r); v["operator_workspace_touched"]=True; v["receipt_digest"]=digest_object({k:x for k,x in v.items() if k!="receipt_digest"}); d=evaluate(r,v,{"candidate_output_digest":"sha256:a","resulting_output_digest":"sha256:a","outcome_evidence_ref":"sha256:out"})
    assert "operator_workspace_was_touched" in d["blockers"]

def test_digest_is_deterministic():
    r=reuse(); v=verification(r); outcome={"candidate_output_digest":"sha256:a","resulting_output_digest":"sha256:a","outcome_evidence_ref":"sha256:out"}
    assert evaluate(r,v,outcome)["receipt_digest"] == evaluate(r,v,outcome)["receipt_digest"]

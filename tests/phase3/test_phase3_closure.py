from pathlib import Path
from app.kernel.evidence.phase3_closure import Phase3EndToEndProofClosure, digest_object

def signed(core): return {**core, "receipt_digest": digest_object(core)}
def fixture(root: Path):
    ek=root/'app/kernel/evidence'; ek.mkdir(parents=True)
    names=['evidence_builder.py','evidence_ledger.py','fingerprint_engine.py','evidence_retrieval.py','compatibility_engine.py','reuse_engine.py','equivalence_engine.py','sourceplan_handoff.py','operator_approval.py','capability_consumption.py','post_apply_gate.py','promotion_closure.py']
    for n in names:(ek/n).write_text(n)
    pe={f'3.{i}':{'status':'PASS','verification_class':'operational','artifact_digest':'sha256:'+'a'*64} for i in range(1,13)}
    common={'evidence_id':'e','plan_id':'p','worktree_id':'w','sourceplan_digest':'sha256:'+'b'*64,'operations_digest':'sha256:'+'c'*64,'promotion_authorized':False,'phase2_governance_bypass_allowed':False}
    c={}
    c['3.5']=signed({**common,'version':'3.5','beast_object_type':'beast_evidence_compatibility_receipt','verdict':'EXACT'})
    c['3.6']=signed({**common,'version':'3.6','beast_object_type':'beast_evidence_reuse_receipt','disposition':'PREPARED_EXACT_REPLAY','compatibility_receipt_digest':c['3.5']['receipt_digest']})
    c['3.7']=signed({**common,'version':'3.7','beast_object_type':'beast_evidence_reuse_outcome_receipt','disposition':'VERIFIED_EQUIVALENT','reuse_receipt_digest':c['3.6']['receipt_digest']})
    c['3.8']=signed({**common,'version':'3.8','beast_object_type':'beast_evidence_sourceplan_handoff_receipt','disposition':'SOURCEPLAN_REVIEW_READY','outcome_receipt_digest':c['3.7']['receipt_digest']})
    c['3.9']=signed({**common,'version':'3.9','beast_object_type':'beast_evidence_operator_approval_receipt','disposition':'OPERATOR_APPROVED','handoff_receipt_digest':c['3.8']['receipt_digest']})
    c['3.10']=signed({**common,'version':'3.10','beast_object_type':'beast_evidence_capability_consumption_receipt','disposition':'SOURCEPLAN_APPLIED','approval_receipt_digest':c['3.9']['receipt_digest']})
    c['3.11']=signed({**common,'version':'3.11','beast_object_type':'beast_evidence_post_apply_promotion_gate_receipt','disposition':'PROMOTION_ELIGIBLE','consumption_receipt_digest':c['3.10']['receipt_digest']})
    c['3.12']=signed({**common,'version':'3.12','beast_object_type':'beast_evidence_promotion_closure_receipt','disposition':'PROMOTION_COMPLETED','eligibility_receipt_digest':c['3.11']['receipt_digest']})
    rr={'passed':63,'failed':0,'python_compilation':'PASS','architecture_checks':{'passed':8,'total':8}}
    return pe,c,rr

def test_complete_chain_closes(tmp_path):
    pe,c,rr=fixture(tmp_path); r=Phase3EndToEndProofClosure().close(root_path=str(tmp_path),phase_evidence=pe,receipt_chain=c,regression_report=rr,created_at='2026-07-19T12:00:00Z'); assert r['disposition']=='PHASE3_CLOSED'; assert r['phase3_complete'] is True

def test_tampered_receipt_blocks(tmp_path):
    pe,c,rr=fixture(tmp_path); c['3.8']['plan_id']='tampered'; r=Phase3EndToEndProofClosure().close(root_path=str(tmp_path),phase_evidence=pe,receipt_chain=c,regression_report=rr); assert 'receipt_digest_invalid:3.8' in r['blockers']

def test_parent_binding_break_blocks(tmp_path):
    pe,c,rr=fixture(tmp_path); x=dict(c['3.10']); x['approval_receipt_digest']='sha256:'+'9'*64; c['3.10']=signed({k:v for k,v in x.items() if k!='receipt_digest'}); r=Phase3EndToEndProofClosure().close(root_path=str(tmp_path),phase_evidence=pe,receipt_chain=c,regression_report=rr); assert any('receipt_parent_binding_invalid:3.10' in b for b in r['blockers'])

def test_missing_operational_phase_blocks(tmp_path):
    pe,c,rr=fixture(tmp_path); pe['3.4']['verification_class']='structural'; r=Phase3EndToEndProofClosure().close(root_path=str(tmp_path),phase_evidence=pe,receipt_chain=c,regression_report=rr); assert 'phase_operational_proof_missing:3.4' in r['blockers']

def test_regression_failure_blocks(tmp_path):
    pe,c,rr=fixture(tmp_path); rr['failed']=1; r=Phase3EndToEndProofClosure().close(root_path=str(tmp_path),phase_evidence=pe,receipt_chain=c,regression_report=rr); assert 'regression_failures_present' in r['blockers']

def test_writes_reproducible_bundle(tmp_path):
    pe,c,rr=fixture(tmp_path); out=tmp_path/'proof'; r=Phase3EndToEndProofClosure().close(root_path=str(tmp_path),phase_evidence=pe,receipt_chain=c,regression_report=rr,output_directory=str(out),created_at='2026-07-19T12:00:00Z'); assert Path(r['proof_bundle']['archive']).is_file(); assert r['promotion_authorized'] is False

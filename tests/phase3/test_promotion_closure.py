from pathlib import Path
from app.kernel.evidence.promotion_closure import PromotionExecutionRollbackClosure,digest_object,digest_file

def signed(c): return {**c,'receipt_digest':digest_object(c)}
def fx(tmp_path):
 w=tmp_path/'wt';o=tmp_path/'op';w.mkdir();o.mkdir();(w/'a.py').write_text('new');(o/'a.py').write_text('old')
 entries=[{'path':'a.py','digest':digest_file(w/'a.py'),'exists':True}]; sd=digest_object(entries)
 e=signed({'version':'3.11','beast_object_type':'beast_evidence_post_apply_promotion_gate_receipt','evidence_id':'e','plan_id':'p','worktree_id':'wt','disposition':'PROMOTION_ELIGIBLE','promotion_eligible':True,'promotion_authorized':False,'phase2_governance_bypass_allowed':False,'sourceplan_digest':'sha256:'+'a'*64,'operations_digest':'sha256:'+'b'*64,'applied_state_digest':sd,'changed_files':['a.py']})
 a=signed({'version':'3.12','beast_object_type':'beast_human_promotion_authorization','eligibility_receipt_digest':e['receipt_digest'],'plan_id':'p','worktree_id':'wt','sourceplan_digest':e['sourceplan_digest'],'operations_digest':e['operations_digest'],'applied_state_digest':sd,'operator_id':'operator:byron','decision':'PROMOTE','review_acknowledged':True,'scope':'once','decided_at':'2026-07-19T10:00:00+00:00'})
 return w,o,{'files':entries,'state_digest':sd},e,a

def test_promotes_exact_state(tmp_path):
 w,o,s,e,a=fx(tmp_path);r=PromotionExecutionRollbackClosure().execute(eligibility_receipt=e,promotion_authorization=a,worktree_root=str(w),operator_workspace_root=str(o),applied_state=s,operator_workspace_clean=True,created_at='2026-07-19T10:01:00+00:00');assert r['disposition']=='PROMOTION_COMPLETED';assert (o/'a.py').read_text()=='new';assert r['promotion_authorized'] is False

def test_tampered_eligibility_blocks(tmp_path):
 w,o,s,e,a=fx(tmp_path);e['changed_files']=['x.py'];r=PromotionExecutionRollbackClosure().execute(eligibility_receipt=e,promotion_authorization=a,worktree_root=str(w),operator_workspace_root=str(o),applied_state=s,operator_workspace_clean=True,created_at='2026-07-19T10:01:00+00:00');assert r['disposition']=='PROMOTION_BLOCKED';assert (o/'a.py').read_text()=='old'

def test_dirty_workspace_blocks(tmp_path):
 w,o,s,e,a=fx(tmp_path);r=PromotionExecutionRollbackClosure().execute(eligibility_receipt=e,promotion_authorization=a,worktree_root=str(w),operator_workspace_root=str(o),applied_state=s,operator_workspace_clean=False,created_at='2026-07-19T10:01:00+00:00');assert 'operator_workspace_not_clean' in r['blockers']

def test_digest_drift_blocks(tmp_path):
 w,o,s,e,a=fx(tmp_path);(w/'a.py').write_text('drift');r=PromotionExecutionRollbackClosure().execute(eligibility_receipt=e,promotion_authorization=a,worktree_root=str(w),operator_workspace_root=str(o),applied_state=s,operator_workspace_clean=True,created_at='2026-07-19T10:01:00+00:00');assert any('worktree_file_digest_mismatch' in x for x in r['blockers'])

def test_distinct_roots_required(tmp_path):
 w,o,s,e,a=fx(tmp_path);r=PromotionExecutionRollbackClosure().execute(eligibility_receipt=e,promotion_authorization=a,worktree_root=str(w),operator_workspace_root=str(w),applied_state=s,operator_workspace_clean=True,created_at='2026-07-19T10:01:00+00:00');assert 'worktree_and_operator_workspace_must_be_distinct' in r['blockers']

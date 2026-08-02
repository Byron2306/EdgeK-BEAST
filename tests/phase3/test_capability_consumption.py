from pathlib import Path
from app.kernel.evidence.capability_consumption import OneUseSourcePlanApplyEngine,digest_object

def receipt(plan,root):
 core={k:v for k,v in plan.items() if k not in {'sourceplan_digest','operations_digest'}}; sd=digest_object(core); od=digest_object(plan['operations']); hand='sha256:'+'a'*64; req=digest_object({'action':'sourceplan.apply','plan_id':plan['plan_id'],'sourceplan_digest':sd,'operations_digest':od,'handoff_receipt_digest':hand,'worktree_id':'wt-1'})
 capcore={'capability_id':'cap:1','request_digest':req,'authority':'human_operator','issuer_key_id':'operator:byron','expires_at':4102444800,'nonce':'n','audience':'beast-sourceplan-runtime','scope':'once','plan_id':plan['plan_id'],'sourceplan_digest':sd,'operations_digest':od,'approval_binding_digest':'sha256:'+'b'*64}
 cap={**capcore,'capability_digest':digest_object(capcore)}
 r={'version':'3.9','beast_object_type':'beast_evidence_operator_approval_receipt','evidence_id':'e1','plan_id':plan['plan_id'],'disposition':'OPERATOR_APPROVED','operator_id':'operator:byron','request_digest':req,'handoff_receipt_digest':hand,'sourceplan_digest':sd,'operations_digest':od,'worktree_id':'wt-1','operator_approved':True,'sourceplan_apply_capability':cap,'sourceplan_apply_authorized':False,'workspace_mutation_authorized':False,'promotion_authorized':False,'phase2_governance_bypass_allowed':False}
 return {**r,'receipt_digest':digest_object(r)}
def test_apply_and_replay_blocked(tmp_path):
 p=tmp_path/'a.txt';p.write_text('old'); plan={'plan_id':'p1','worktree_task_id':'wt-1','operations':[{'op_id':'1','op':'replace_exact','path':'a.txt','old_text':'old','new_text':'new','selected':True}]}; r=receipt(plan,tmp_path); e=OneUseSourcePlanApplyEngine(); out=e.execute(approval_receipt=r,sourceplan=plan,workspace_root=str(tmp_path)); assert out['apply_succeeded'] and p.read_text()=='new'; out2=e.execute(approval_receipt=r,sourceplan=plan,workspace_root=str(tmp_path)); assert not out2['apply_succeeded'] and 'capability_already_consumed' in out2['blockers']
def test_rollback_burns_key(tmp_path):
 (tmp_path/'a').write_text('x'); plan={'plan_id':'p2','worktree_task_id':'wt-1','operations':[{'op_id':'1','op':'replace_exact','path':'a','old_text':'missing','new_text':'y','selected':True}]};r=receipt(plan,tmp_path);o=OneUseSourcePlanApplyEngine().execute(approval_receipt=r,sourceplan=plan,workspace_root=str(tmp_path));assert o['rollback_performed'] and (tmp_path/'a').read_text()=='x' and o['capability_consumed']
def test_tamper_blocked(tmp_path):
 plan={'plan_id':'p3','worktree_task_id':'wt-1','operations':[{'op_id':'1','op':'create_or_replace','path':'a','content':'x','selected':True}]};r=receipt(plan,tmp_path);plan['operations'][0]['content']='evil';o=OneUseSourcePlanApplyEngine().execute(approval_receipt=r,sourceplan=plan,workspace_root=str(tmp_path));assert not o['capability_consumed']

"""BEAST Phase 3.12 human-authorized promotion transaction and rollback closure."""
from __future__ import annotations
import json, os, shutil, tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any, Mapping, Optional

SCHEMA_VERSION = "3.12"
class PromotionClosureError(ValueError): pass

def _canonical(v: Any)->bytes: return json.dumps(v,sort_keys=True,separators=(",",":"),ensure_ascii=False,default=str).encode()
def digest_object(v: Any)->str: return "sha256:"+sha256(_canonical(v)).hexdigest()
def digest_file(p: Path)->str:
    h=sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
    return 'sha256:'+h.hexdigest()
def verify_receipt_digest(r: Mapping[str,Any])->bool:
    return isinstance(r.get('receipt_digest'),str) and r['receipt_digest']==digest_object({k:v for k,v in r.items() if k!='receipt_digest'})
def _safe(path:str)->str:
    p=Path(path)
    if not path or p.is_absolute() or '..' in p.parts or '.git' in p.parts: raise PromotionClosureError(f'unsafe promotion path: {path}')
    return p.as_posix()
def _within(root:Path,p:Path)->bool:
    try: p.resolve(strict=False).relative_to(root.resolve()); return True
    except ValueError: return False

@dataclass(frozen=True)
class PromotionPolicy:
    maximum_files:int=100
    maximum_bytes:int=50_000_000
    require_clean_operator_workspace:bool=True
    require_post_promotion_verification:bool=True
    authorization_max_age_seconds:int=900
    def __post_init__(self):
        if not 1<=self.maximum_files<=1000 or not 1<=self.maximum_bytes<=2_000_000_000: raise PromotionClosureError('invalid promotion policy budget')
    @classmethod
    def from_mapping(cls,v:Optional[Mapping[str,Any]]):
        if not v:return cls()
        unknown=set(v)-set(cls.__dataclass_fields__)
        if unknown: raise PromotionClosureError(f'unknown promotion policy controls: {sorted(unknown)}')
        return cls(**dict(v))

class PromotionExecutionRollbackClosure:
    def execute(self,*,eligibility_receipt:Mapping[str,Any],promotion_authorization:Mapping[str,Any],worktree_root:str,operator_workspace_root:str,applied_state:Mapping[str,Any],operator_workspace_clean:bool,policy_controls:Optional[Mapping[str,Any]]=None,created_at:Optional[str]=None)->dict[str,Any]:
        policy=PromotionPolicy.from_mapping(policy_controls); blockers=[]
        if eligibility_receipt.get('beast_object_type')!='beast_evidence_post_apply_promotion_gate_receipt' or eligibility_receipt.get('version')!='3.11': blockers.append('phase3_11_eligibility_receipt_required')
        if not verify_receipt_digest(eligibility_receipt): blockers.append('eligibility_receipt_digest_invalid')
        if eligibility_receipt.get('disposition')!='PROMOTION_ELIGIBLE' or eligibility_receipt.get('promotion_eligible') is not True: blockers.append('promotion_not_eligible')
        if eligibility_receipt.get('promotion_authorized') is True or eligibility_receipt.get('phase2_governance_bypass_allowed') is True: blockers.append('illegal_inherited_promotion_authority')
        if promotion_authorization.get('beast_object_type')!='beast_human_promotion_authorization' or promotion_authorization.get('version')!='3.12': blockers.append('human_promotion_authorization_required')
        if not verify_receipt_digest(promotion_authorization): blockers.append('promotion_authorization_digest_invalid')
        for key in ('plan_id','worktree_id','sourceplan_digest','operations_digest','applied_state_digest'):
            if promotion_authorization.get(key)!=eligibility_receipt.get(key): blockers.append(f'promotion_authorization_{key}_mismatch')
        if promotion_authorization.get('eligibility_receipt_digest')!=eligibility_receipt.get('receipt_digest'): blockers.append('promotion_authorization_eligibility_binding_mismatch')
        if promotion_authorization.get('decision')!='PROMOTE' or promotion_authorization.get('review_acknowledged') is not True: blockers.append('explicit_human_promotion_required')
        if not str(promotion_authorization.get('operator_id') or '').startswith('operator:'): blockers.append('valid_operator_identity_required')
        if promotion_authorization.get('scope')!='once': blockers.append('promotion_scope_must_be_once')
        now=datetime.fromisoformat(created_at.replace('Z','+00:00')) if created_at else datetime.now(timezone.utc)
        try:
            decided=datetime.fromisoformat(str(promotion_authorization.get('decided_at')).replace('Z','+00:00'))
            if decided.tzinfo is None: raise ValueError
            age=(now.astimezone(timezone.utc)-decided.astimezone(timezone.utc)).total_seconds()
            if age< -60 or age>policy.authorization_max_age_seconds: blockers.append('promotion_authorization_stale')
        except Exception: blockers.append('invalid_promotion_authorization_timestamp')
        wr=Path(worktree_root).resolve(); ow=Path(operator_workspace_root).resolve()
        if wr==ow or _within(wr,ow) or _within(ow,wr): blockers.append('worktree_and_operator_workspace_must_be_distinct')
        if not wr.is_dir(): blockers.append('worktree_root_missing')
        if not ow.is_dir(): blockers.append('operator_workspace_root_missing')
        if policy.require_clean_operator_workspace and not operator_workspace_clean: blockers.append('operator_workspace_not_clean')
        entries=[]; total=0
        for item in applied_state.get('files') or []:
            try:path=_safe(str(item.get('path') or ''))
            except Exception as e:blockers.append(str(e));continue
            exists=bool(item.get('exists',True)); dg=item.get('digest')
            if not isinstance(dg,str) or not dg.startswith('sha256:'): blockers.append(f'invalid_applied_digest:{path}')
            src=wr/path
            if exists:
                if not src.is_file(): blockers.append(f'worktree_file_missing:{path}')
                else:
                    actual=digest_file(src); total+=src.stat().st_size
                    if actual!=dg: blockers.append(f'worktree_file_digest_mismatch:{path}')
            entries.append({'path':path,'digest':dg,'exists':exists})
        entries.sort(key=lambda x:x['path'])
        if digest_object(entries)!=applied_state.get('state_digest') or applied_state.get('state_digest')!=eligibility_receipt.get('applied_state_digest'): blockers.append('applied_state_binding_invalid')
        if sorted(x['path'] for x in entries)!=sorted(eligibility_receipt.get('changed_files') or []): blockers.append('promotion_changed_file_set_mismatch')
        if len(entries)>policy.maximum_files: blockers.append('promotion_file_budget_exceeded')
        if total>policy.maximum_bytes: blockers.append('promotion_byte_budget_exceeded')
        if blockers: return self._receipt(eligibility_receipt,promotion_authorization,now,'PROMOTION_BLOCKED',False,False,False,blockers,[],None,policy)
        backup=Path(tempfile.mkdtemp(prefix='beast-promotion-rollback-',dir=str(ow.parent)))
        journal=[]; promoted=[]; rolled=False
        try:
            for e in entries:
                rel=e['path']; src=wr/rel; dst=ow/rel
                if not _within(ow,dst): raise PromotionClosureError(f'workspace escape:{rel}')
                existed=dst.exists()
                if existed:
                    bp=backup/rel; bp.parent.mkdir(parents=True,exist_ok=True)
                    if dst.is_file(): shutil.copy2(dst,bp)
                    else: raise PromotionClosureError(f'non_file_destination:{rel}')
                journal.append({'path':rel,'existed':existed,'preimage_digest':digest_file(dst) if existed else None})
                dst.parent.mkdir(parents=True,exist_ok=True)
                if e['exists']:
                    fd,tmp=tempfile.mkstemp(prefix='.beast-promote-',dir=str(dst.parent)); os.close(fd); tp=Path(tmp)
                    shutil.copy2(src,tp); os.replace(tp,dst)
                elif dst.exists(): dst.unlink()
                promoted.append(rel)
            if policy.require_post_promotion_verification:
                for e in entries:
                    dst=ow/e['path']
                    if e['exists'] and (not dst.is_file() or digest_file(dst)!=e['digest']): raise PromotionClosureError(f'post_promotion_digest_mismatch:{e["path"]}')
                    if not e['exists'] and dst.exists(): raise PromotionClosureError(f'post_promotion_delete_failed:{e["path"]}')
            disposition='PROMOTION_COMPLETED'; success=True
        except Exception as exc:
            blockers.append(str(exc)); rolled=True; success=False; disposition='PROMOTION_ROLLED_BACK'
            for j in reversed(journal):
                dst=ow/j['path']; bp=backup/j['path']
                try:
                    if j['existed']:
                        dst.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(bp,dst)
                    elif dst.exists(): dst.unlink()
                except Exception as re: blockers.append(f'rollback_failed:{j["path"]}:{re}')
        rollback_manifest={'backup_root':str(backup),'materials':journal,'manifest_digest':digest_object(journal)}
        return self._receipt(eligibility_receipt,promotion_authorization,now,disposition,success,True,rolled,blockers,promoted,rollback_manifest,policy)
    def _receipt(self,e,a,now,disposition,success,auth_consumed,rolled,blockers,promoted,rollback,policy):
        core={'version':SCHEMA_VERSION,'beast_object_type':'beast_evidence_promotion_closure_receipt','evidence_id':e.get('evidence_id'),'plan_id':e.get('plan_id'),'worktree_id':e.get('worktree_id'),'disposition':disposition,'eligibility_receipt_digest':e.get('receipt_digest'),'promotion_authorization_digest':a.get('receipt_digest'),'sourceplan_digest':e.get('sourceplan_digest'),'operations_digest':e.get('operations_digest'),'applied_state_digest':e.get('applied_state_digest'),'promoted_files':promoted,'blockers':sorted(set(blockers)),'promotion_authorization_consumed':auth_consumed,'workspace_promotion_performed':success,'post_promotion_verified':success,'rollback_performed':rolled,'rollback_material':rollback,'authority':'completed_human_authorized_promotion_transaction' if success else 'promotion_transaction_closed','promotion_authorized':False,'further_mutation_authorized':False,'phase2_governance_bypass_allowed':False,'human_promotion_required':False if success else True,'policy_digest':digest_object(asdict(policy)),'created_at':now.astimezone(timezone.utc).isoformat()}
        return {**core,'receipt_digest':digest_object(core)}

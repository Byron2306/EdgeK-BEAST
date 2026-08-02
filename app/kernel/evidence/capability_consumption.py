"""BEAST Phase 3.10 one-use capability consumption and exact SourcePlan application."""
from __future__ import annotations
import json, os, sqlite3, tempfile
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any, Mapping, Optional

SCHEMA_VERSION="3.10"
ALLOWED_OPS={"replace_exact","create_or_replace","delete_exact","move_exact"}
class CapabilityConsumptionError(ValueError): pass

def _canonical(v:Any)->bytes:return json.dumps(v,sort_keys=True,separators=(",",":"),ensure_ascii=False,default=str).encode()
def digest_object(v:Any)->str:return "sha256:"+sha256(_canonical(v)).hexdigest()
def verify_receipt_digest(r:Mapping[str,Any])->bool:
 c={k:v for k,v in r.items() if k!="receipt_digest"}; return isinstance(r.get("receipt_digest"),str) and r["receipt_digest"]==digest_object(c)
def _safe(root:Path, rel:str)->Path:
 if not rel or Path(rel).is_absolute() or ".." in Path(rel).parts or ".git" in Path(rel).parts: raise CapabilityConsumptionError(f"unsafe path: {rel}")
 p=(root/rel).resolve()
 if root!=p and root not in p.parents: raise CapabilityConsumptionError(f"path escapes workspace: {rel}")
 return p
def _file_digest(p:Path)->str:
 return "sha256:"+sha256(p.read_bytes()).hexdigest() if p.exists() and p.is_file() else "sha256:"+sha256(b"").hexdigest()
@dataclass(frozen=True)
class ApplyPolicy:
 max_operations:int=100; max_total_bytes:int=5_000_000; require_worktree:bool=True
 @classmethod
 def from_mapping(cls,v:Optional[Mapping[str,Any]]):
  if not v:return cls()
  unknown=set(v)-set(cls.__dataclass_fields__)
  if unknown: raise CapabilityConsumptionError(f"unknown apply policy controls: {sorted(unknown)}")
  x=cls(**dict(v))
  if not 1<=x.max_operations<=500: raise CapabilityConsumptionError("invalid max_operations")
  if not 1<=x.max_total_bytes<=50_000_000: raise CapabilityConsumptionError("invalid max_total_bytes")
  return x
class OneUseSourcePlanApplyEngine:
 def execute(self,*,approval_receipt:Mapping[str,Any],sourceplan:Mapping[str,Any],workspace_root:str,ledger_path:Optional[str]=None,policy_controls:Optional[Mapping[str,Any]]=None,created_at:Optional[str]=None)->dict[str,Any]:
  policy=ApplyPolicy.from_mapping(policy_controls); blockers=[]; rollback=[]; changed=[]
  if approval_receipt.get("beast_object_type")!="beast_evidence_operator_approval_receipt" or approval_receipt.get("version")!="3.9": blockers.append("phase3_9_approval_receipt_required")
  if not verify_receipt_digest(approval_receipt): blockers.append("approval_receipt_digest_invalid")
  if approval_receipt.get("disposition")!="OPERATOR_APPROVED" or approval_receipt.get("operator_approved") is not True: blockers.append("operator_approval_required")
  cap=approval_receipt.get("sourceplan_apply_capability") or {}
  if digest_object({k:v for k,v in cap.items() if k!="capability_digest"})!=cap.get("capability_digest"): blockers.append("capability_digest_invalid")
  for k in ("sourceplan_apply_authorized","workspace_mutation_authorized","promotion_authorized","phase2_governance_bypass_allowed"):
   if approval_receipt.get(k) is True: blockers.append(f"approval_receipt_illegally_sets_{k}")
  plan_core={k:v for k,v in sourceplan.items() if k not in {"sourceplan_digest","operations_digest"}}
  plan_digest=digest_object(plan_core); ops=sourceplan.get("operations") or []; ops_digest=digest_object(ops)
  if plan_digest!=approval_receipt.get("sourceplan_digest") or plan_digest!=cap.get("sourceplan_digest"): blockers.append("sourceplan_digest_mismatch")
  if ops_digest!=approval_receipt.get("operations_digest") or ops_digest!=cap.get("operations_digest"): blockers.append("operations_digest_mismatch")
  if str(sourceplan.get("plan_id") or "")!=str(approval_receipt.get("plan_id") or "") or sourceplan.get("plan_id")!=cap.get("plan_id"): blockers.append("plan_id_mismatch")
  request=digest_object({"action":"sourceplan.apply","plan_id":sourceplan.get("plan_id"),"sourceplan_digest":plan_digest,"operations_digest":ops_digest,"handoff_receipt_digest":approval_receipt.get("handoff_receipt_digest"),"worktree_id":approval_receipt.get("worktree_id")})
  if request!=approval_receipt.get("request_digest") or request!=cap.get("request_digest"): blockers.append("request_digest_mismatch")
  now=datetime.fromisoformat(created_at.replace("Z","+00:00")) if created_at else datetime.now(timezone.utc)
  if float(cap.get("expires_at") or 0)<=now.timestamp(): blockers.append("capability_expired")
  if cap.get("scope")!="once" or cap.get("audience")!="beast-sourceplan-runtime" or cap.get("authority")!="human_operator": blockers.append("capability_authority_invalid")
  root=Path(workspace_root).expanduser().resolve()
  if policy.require_worktree and str(sourceplan.get("worktree_task_id") or sourceplan.get("worktree_id") or "")!=str(approval_receipt.get("worktree_id") or ""): blockers.append("worktree_binding_mismatch")
  if not ops or len(ops)>policy.max_operations: blockers.append("invalid_operation_count")
  total=0
  for op in ops:
   if op.get("op") not in ALLOWED_OPS or op.get("selected") is False: blockers.append(f"invalid_operation:{op.get('op')}")
   try:_safe(root,str(op.get("path") or op.get("from_path") or ""))
   except Exception as e:blockers.append(str(e))
   total+=len(str(op.get("new_text") or op.get("new") or op.get("content") or "").encode())
  if total>policy.max_total_bytes:blockers.append("apply_byte_budget_exceeded")
  consumed=False; apply_error=None
  if not blockers:
   db=Path(ledger_path or root/'.beast'/'one_use_capabilities.sqlite3'); db.parent.mkdir(parents=True,exist_ok=True)
   con=sqlite3.connect(str(db),timeout=10,isolation_level=None)
   try:
    con.execute("PRAGMA journal_mode=WAL"); con.execute("PRAGMA synchronous=FULL")
    con.execute("CREATE TABLE IF NOT EXISTS consumed_capabilities (capability_id TEXT PRIMARY KEY, request_digest TEXT NOT NULL, authority TEXT NOT NULL, issuer_key_id TEXT NOT NULL, consumed_at REAL NOT NULL)")
    con.execute("BEGIN IMMEDIATE")
    con.execute("INSERT INTO consumed_capabilities VALUES (?,?,?,?,?)",(cap.get("capability_id"),request,cap.get("authority"),cap.get("issuer_key_id") or approval_receipt.get("operator_id"),now.timestamp()))
    con.execute("COMMIT"); consumed=True
   except sqlite3.IntegrityError: blockers.append("capability_already_consumed"); con.execute("ROLLBACK")
   finally: con.close()
  if consumed:
   try:
    for op in ops:
     kind=op["op"]; src=_safe(root,str(op.get("path") or op.get("from_path"))); dst=_safe(root,str(op.get("to_path"))) if kind=="move_exact" else None
     before=src.read_bytes() if src.exists() and src.is_file() else None; rollback.append((src,before,dst))
     expected=op.get("expected_hash") or op.get("old_digest")
     if expected and expected not in {_file_digest(src),sha256((before or b"")).hexdigest()}: raise CapabilityConsumptionError(f"preimage hash mismatch: {src.relative_to(root)}")
     if kind=="replace_exact":
      old=str(op.get("old_text") if "old_text" in op else op.get("old") or ""); new=str(op.get("new_text") if "new_text" in op else op.get("new") or "")
      text=src.read_text(); count=text.count(old)
      if count!=1: raise CapabilityConsumptionError(f"replace_exact expected one match: {src.relative_to(root)}")
      src.write_text(text.replace(old,new,1))
     elif kind=="create_or_replace": src.parent.mkdir(parents=True,exist_ok=True); src.write_text(str(op.get("content") if "content" in op else op.get("new_text") or op.get("new") or ""))
     elif kind=="delete_exact":
      if not src.exists(): raise CapabilityConsumptionError(f"delete target missing: {src.relative_to(root)}")
      src.unlink()
     else:
      if not src.exists() or dst is None or dst.exists(): raise CapabilityConsumptionError("invalid move_exact state")
      dst.parent.mkdir(parents=True,exist_ok=True); os.replace(src,dst)
     changed.append(str((dst or src).relative_to(root)))
   except Exception as exc:
    apply_error=str(exc)
    for src,before,dst in reversed(rollback):
     try:
      if dst and dst.exists() and not src.exists(): src.parent.mkdir(parents=True,exist_ok=True); os.replace(dst,src)
      if before is None:
       if src.exists(): src.unlink()
      else: src.parent.mkdir(parents=True,exist_ok=True); src.write_bytes(before)
     except Exception: pass
  success=consumed and apply_error is None
  core={"version":SCHEMA_VERSION,"beast_object_type":"beast_evidence_capability_consumption_receipt","evidence_id":approval_receipt.get("evidence_id"),"plan_id":sourceplan.get("plan_id"),"disposition":"SOURCEPLAN_APPLIED" if success else ("APPLY_ROLLED_BACK" if consumed else "CAPABILITY_CONSUMPTION_BLOCKED"),"approval_receipt_digest":approval_receipt.get("receipt_digest"),"capability_id":cap.get("capability_id"),"capability_digest":cap.get("capability_digest"),"request_digest":request,"sourceplan_digest":plan_digest,"operations_digest":ops_digest,"worktree_id":approval_receipt.get("worktree_id"),"capability_consumed":consumed,"apply_succeeded":success,"rollback_performed":bool(consumed and apply_error),"changed_files":changed if success else [],"blockers":sorted(set(blockers)),"apply_error":apply_error,"policy_digest":digest_object(asdict(policy)),"created_at":now.astimezone(timezone.utc).isoformat(),"authority":"consumed_exact_apply_only","promotion_authorized":False,"human_promotion_required":True,"phase2_governance_bypass_allowed":False}
  return {**core,"receipt_digest":digest_object(core)}

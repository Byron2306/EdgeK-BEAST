"""Fail-closed publication approval, immutable commits, and revocation manifests."""
from __future__ import annotations

import hashlib, json, time
from dataclasses import asdict, dataclass, replace
from typing import Any, Mapping, Sequence


def digest(value: Any) -> str:
    return "sha256:"+hashlib.sha256(json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=True,default=str).encode()).hexdigest()


@dataclass(frozen=True)
class PublicationApproval:
    artifact_id: str
    dataset_id: str
    commit_subject_digest: str
    approver: str
    policy_digest: str
    appraisal_ref: str
    issued_at: float
    expires_at: float
    one_use_nonce: str
    approval_digest: str = ""
    def sealed(self):
        value=asdict(self); value.pop("approval_digest",None); return replace(self,approval_digest=digest(value))
    def validate(self, *, now: float | None=None):
        value=asdict(self); supplied=value.pop("approval_digest")
        if supplied != digest(value): raise ValueError("publication approval is tampered")
        if not all((self.artifact_id,self.dataset_id,self.approver,self.policy_digest,self.appraisal_ref,self.one_use_nonce)): raise ValueError("publication approval is incomplete")
        if (time.time() if now is None else now) >= self.expires_at: raise PermissionError("publication approval expired")


class PublicationApprovalGate:
    def __init__(self): self._consumed:set[str]=set()
    def consume(self, approval: PublicationApproval, *, commit_subject_digest: str, dataset_id: str, now: float|None=None) -> dict[str,Any]:
        approval.validate(now=now)
        if approval.dataset_id != dataset_id or approval.commit_subject_digest != commit_subject_digest: raise PermissionError("publication approval binding mismatch")
        if approval.one_use_nonce in self._consumed: raise PermissionError("publication approval already consumed")
        self._consumed.add(approval.one_use_nonce)
        return {"beast_object_type":"publication_approval_receipt","version":"1.0","approval_digest":approval.approval_digest,"dataset_id":dataset_id,"subject_digest":commit_subject_digest,"consumed":True}


def build_dataset_commit(*, dataset_id: str, parent_commit: str, manifest_digest: str, chunk_root_digest: str, attestation_digest: str, row_digest: str, author: str, created_at: str) -> dict[str,Any]:
    body={"beast_object_type":"forge_kv_dataset_commit","version":"1.0","dataset_id":dataset_id,"parent_commit":parent_commit,"manifest_digest":manifest_digest,"chunk_root_digest":chunk_root_digest,"attestation_digest":attestation_digest,"row_digest":row_digest,"author":author,"created_at":created_at,"authority":"verify_only","native_context_included":False}
    body["commit_digest"]=digest(body); return body


def build_revocation(*, dataset_id:str, commit_digest:str, reason:str, issuer:str, issued_at:str, replacement_commit:str="") -> dict[str,Any]:
    if not reason or not issuer: raise ValueError("revocation reason and issuer are required")
    body={"beast_object_type":"forge_kv_dataset_revocation","version":"1.0","dataset_id":dataset_id,"commit_digest":commit_digest,"reason":reason,"issuer":issuer,"issued_at":issued_at,"replacement_commit":replacement_commit,"tombstone":True,"authority":"deny_reuse"}
    body["revocation_digest"]=digest(body); return body

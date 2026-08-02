"""Tamper-evident evidence packet for one publication and remote reproduction."""
from __future__ import annotations
from dataclasses import dataclass,asdict,replace
import hashlib,json,time

def _hash(v): return "sha256:"+hashlib.sha256(json.dumps(v,sort_keys=True,separators=(",",":"),default=str).encode()).hexdigest()
@dataclass(frozen=True)
class CrossNodeEvidencePacket:
    dataset_id:str; local_commit_digest:str; remote_commit:str; publication_receipt_digest:str
    receiver_node_id:str; receiver_receipt_digest:str; attestation_receipt_digest:str
    reconstructed_root_digest:str; verifier_digest:str; native_context_exported:bool=False
    promotion_granted:bool=False; issued_at:float=0.0; packet_digest:str=""
    def sealed(self):
        v=replace(self,issued_at=self.issued_at or time.time(),packet_digest=""); body=asdict(v); body.pop("packet_digest")
        return replace(v,packet_digest=_hash(body))
    def validate(self):
        body=asdict(self); digest=body.pop("packet_digest")
        if digest!=_hash(body): raise ValueError("cross-node evidence packet is tampered")
        if self.native_context_exported or self.promotion_granted: raise ValueError("unsafe cross-node closure claim")
        for value in (self.local_commit_digest,self.publication_receipt_digest,self.receiver_receipt_digest,self.attestation_receipt_digest,self.reconstructed_root_digest,self.verifier_digest):
            if not str(value).startswith("sha256:"): raise ValueError("evidence digest is missing")
        return True

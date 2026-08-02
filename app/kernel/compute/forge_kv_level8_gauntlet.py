"""Offline Level 8 closure gauntlet."""
from __future__ import annotations
import hashlib,time
from pathlib import Path
from tempfile import TemporaryDirectory
from app.kernel.compute.forge_kv_level8_ceremony import ForgeKVLevel8Ceremony
from app.kernel.compute.forge_kv_publication import PublicationApproval,build_dataset_commit
from app.kernel.compute.forge_kv_xet import chunk_bytes


def _h(data:bytes)->str: return "sha256:"+hashlib.sha256(data).hexdigest()

class _Plane:
    def __init__(self): self.calls=0
    def publish_hf(self,**kw):
        self.calls+=1
        return {"status":"published","dataset_id":kw["commit"]["dataset_id"],"local_commit_digest":kw["commit"]["commit_digest"],
                "remote_commit":"remote:1","native_context_exported":False,"authority":"verify_only"}

def run_level8_gauntlet():
    payload=b"forge-level8-proof"; digest=_h(payload)
    manifest=chunk_bytes(payload,min_size=4096,avg_size=4096,max_size=4096)
    commit=build_dataset_commit(dataset_id="owner/private",parent_commit="",manifest_digest=digest,chunk_root_digest=manifest["root_digest"],
                                attestation_digest=digest,row_digest=digest,author="gauntlet",created_at="2026-07-20T00:00:00Z")
    approval=PublicationApproval("artifact","owner/private",commit["commit_digest"],"operator",digest,"arda:ok",0,9999999999,"nonce").sealed()
    plane=_Plane(); revocations=[]
    with TemporaryDirectory() as td:
        c=ForgeKVLevel8Ceremony(plane=plane,checkpoint_root=Path(td))
        c.prepare(ceremony_id="ceremony:1",dataset_id="owner/private",commit_digest=commit["commit_digest"])
        c.publish(ceremony_id="ceremony:1",approval=approval,commit=commit,files={"README.md":b"x"},chunks={digest:payload})
        c.attest(ceremony_id="ceremony:1",receiver_node_id="node:b",audience="owner/private",policy_digest=digest,verifier_digest=digest,
                 evidence_factory=lambda ch:{"nonce":ch.nonce,"node_id":ch.node_id},verifier=lambda ch,e:True)
        c.reconstruct(ceremony_id="ceremony:1",commit=commit,manifest=manifest,fetch_chunk=lambda d:payload,verify_artifact=lambda b:b==payload)
        c.revoke(ceremony_id="ceremony:1",reason="test closure",issuer="operator",issued_at="2026-07-20T00:00:01Z",
                 publish_revocation=revocations.append,fetch_revocations=lambda:list(revocations))
        final=c.close(ceremony_id="ceremony:1",receiver_node_id="node:b",reconstructed_root_digest=manifest["root_digest"],verifier_digest=digest)
        resumed=c.close(ceremony_id="ceremony:1",receiver_node_id="node:b",reconstructed_root_digest=manifest["root_digest"],verifier_digest=digest)
        return {"status":final.phase,"publication_calls":plane.calls,"resume_idempotent":final.final_packet==resumed.final_packet,
                "native_context_exported":final.final_packet["native_context_exported"],
                "promotion_granted":final.final_packet["promotion_granted"],
                "receiver_reuse_after_revocation":final.final_packet["receiver_reuse_after_revocation"]}

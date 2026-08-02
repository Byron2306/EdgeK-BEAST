from __future__ import annotations
import time, hashlib, json
from dataclasses import dataclass
from app.kernel.crystals.sealed_capsule import SealedCapsuleFactory
@dataclass(frozen=True,slots=True)
class CapsulePreparationReceipt:
    capsule_id:str; crystal_id:str; capsule_digest:str; size_bytes:int; seal_bitmap:int; authority:str; preparation_ms:float; registry_bound:bool; receipt_digest:str
class CrystalCapsuleForge:
    def __init__(self,*,factory=None,registry=None,event_sink=None): self.factory=factory or SealedCapsuleFactory(); self.registry=registry; self.event_sink=event_sink or (lambda e:None)
    def prepare(self,*,manifest,crystal_ir,verifier_manifest,signer,ttl_seconds=300,predicted_reuse_count=1):
        start=time.monotonic_ns(); handle=self.factory.create(manifest=manifest,crystal_ir=crystal_ir,verifier_manifest=verifier_manifest,signer=signer); ms=(time.monotonic_ns()-start)/1e6
        bound=False
        if self.registry:
            self.registry.register(handle,promotion_digest=manifest.promotion_digest,workspace_id=manifest.workspace_id,privacy_domain=manifest.privacy_domain,ttl_seconds=ttl_seconds,preparation_cost_ms=ms,predicted_reuse_count=predicted_reuse_count);bound=True
        body={'capsule_id':handle.receipt.capsule_id,'crystal_id':handle.receipt.crystal_id,'capsule_digest':handle.receipt.capsule_digest,'size_bytes':handle.receipt.payload_size,'seal_bitmap':handle.receipt.seal_bitmap,'authority':'artifact_only','preparation_ms':ms,'registry_bound':bound}
        dig='sha256:'+hashlib.sha256(json.dumps(body,sort_keys=True,separators=(',',':')).encode()).hexdigest(); self.event_sink({'event_type':'crystal.capsule_prepared',**body,'raw_ir_retained':False})
        return handle,CapsulePreparationReceipt(**body,receipt_digest=dig)

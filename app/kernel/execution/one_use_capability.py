from __future__ import annotations
from dataclasses import dataclass, asdict
import hashlib,json,threading,time,uuid

def dig(v): return "sha256:"+hashlib.sha256(json.dumps(v,sort_keys=True,separators=(",",":")).encode()).hexdigest()
@dataclass(frozen=True)
class CapabilityLease:
    lease_id:str; crystal_id:str; capsule_digest:str; audience:str; capability:str; expires_at:float; nonce:str
    @property
    def digest(self): return dig(asdict(self))
class OneUseCapabilityLedger:
    def __init__(self): self._lock=threading.Lock(); self._leases={}; self._consumed=set()
    def issue(self,*,crystal_id,capsule_digest,audience,capability,ttl=60):
        lease=CapabilityLease("cap_"+uuid.uuid4().hex,crystal_id,capsule_digest,audience,capability,time.time()+ttl,uuid.uuid4().hex); self._leases[lease.digest]=lease; return lease
    def consume(self,digest,*,crystal_id,capsule_digest,audience,capability,now=None):
        now=time.time() if now is None else now
        with self._lock:
            if digest in self._consumed: raise PermissionError("capability replay")
            lease=self._leases.get(digest)
            if not lease: raise PermissionError("unknown capability")
            if now>=lease.expires_at: raise PermissionError("expired capability")
            if (lease.crystal_id,lease.capsule_digest,lease.audience,lease.capability)!=(crystal_id,capsule_digest,audience,capability): raise PermissionError("capability binding mismatch")
            self._consumed.add(digest); return lease

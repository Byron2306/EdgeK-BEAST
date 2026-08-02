from __future__ import annotations
from dataclasses import dataclass, replace
from threading import RLock
import os, time
from app.kernel.crystals.sealed_capsule import SealedCapsuleHandle

@dataclass(frozen=True, slots=True)
class CapsuleRegistryEntry:
    capsule_id: str; crystal_id: str; capsule_digest: str; fd: int; size_bytes: int
    promotion_digest: str; workspace_id: str; privacy_domain: str
    created_ns: int; expires_ns: int; last_used_ns: int; use_count: int = 0
    preparation_cost_ms: float = 0.0; predicted_reuse_count: int = 1

class CapsuleRegistry:
    def __init__(self, *, max_entries: int = 128):
        self.max_entries=max(1,int(max_entries)); self._lock=RLock(); self._items={}
    def register(self, handle: SealedCapsuleHandle, *, promotion_digest:str, workspace_id:str, privacy_domain:str, ttl_seconds:float, preparation_cost_ms:float=0.0, predicted_reuse_count:int=1):
        if ttl_seconds<=0: raise ValueError('capsule TTL must be positive')
        now=time.time_ns(); dup=os.dup(handle.fd)
        e=CapsuleRegistryEntry(handle.receipt.capsule_id,handle.receipt.crystal_id,handle.receipt.capsule_digest,dup,handle.receipt.payload_size,promotion_digest,workspace_id,privacy_domain,now,now+int(ttl_seconds*1e9),now,0,float(preparation_cost_ms),max(1,int(predicted_reuse_count)))
        with self._lock:
            self.prune_expired()
            if len(self._items)>=self.max_entries: os.close(dup); raise OverflowError('capsule registry full')
            self._items[e.capsule_id]=e
        return e
    def get(self,capsule_id,*,workspace_id,privacy_domain):
        with self._lock:
            e=self._items.get(capsule_id)
            if e is None:return None
            if time.time_ns()>=e.expires_ns:self._close_locked(capsule_id);return None
            if e.workspace_id!=workspace_id or e.privacy_domain!=privacy_domain:return None
            e=replace(e,last_used_ns=time.time_ns(),use_count=e.use_count+1);self._items[capsule_id]=e;return e
    def entries(self):
        with self._lock:return tuple(self._items.values())
    def close(self,capsule_id):
        with self._lock:return self._close_locked(capsule_id)
    def _close_locked(self,capsule_id):
        e=self._items.pop(capsule_id,None)
        if e is None:return False
        try: os.close(e.fd)
        except OSError: pass
        return True
    def prune_expired(self):
        now=time.time_ns()
        with self._lock:
            ids=[k for k,v in self._items.items() if now>=v.expires_ns]
            for k in ids:self._close_locked(k)
            return len(ids)
    def close_all(self):
        with self._lock:
            ids=list(self._items)
            for k in ids:self._close_locked(k)
            return len(ids)

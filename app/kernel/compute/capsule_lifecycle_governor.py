from __future__ import annotations
from dataclasses import dataclass
@dataclass(frozen=True,slots=True)
class CapsuleLifecycleReceipt:
    pressure_level:str; speculative_creation_allowed:bool; evicted_capsules:tuple[str,...]; protected_capsules:tuple[str,...]
class CapsuleLifecycleGovernor:
    def __init__(self,*,registry,eviction_policy,pin_registry=None,event_sink=None,governor=None): self.registry=registry;self.policy=eviction_policy;self.pins=pin_registry;self.event_sink=event_sink or (lambda e:None);self.governor=governor
    def apply(self,pressure_level:str):
        level=str(pressure_level).lower(); protected=tuple(e.capsule_id for e in self.registry.entries() if self.pins and self.pins.is_pinned(e.capsule_id,workspace_id=e.workspace_id,privacy_domain=e.privacy_domain))
        chosen=self.policy.choose(self.registry.entries(),pressure_level=level,pin_registry=self.pins)
        if self.governor is not None:  # Compute Governor spine: evictions are dry-run proposals through admit
            from app.kernel.governance.governor_spine import dry_run_eviction
            d=dry_run_eviction(self.governor,'capsule',chosen,{'pressure_level':level})
            self.event_sink({'event_type':'crystal.capsule_lifecycle','pressure_level':level,'evicted':[],'dry_run':True,'would_evict':list(chosen),'governor_receipt':d.receipt_id,'protected':list(protected)})
            return CapsuleLifecycleReceipt(level,level=='low',(),protected)
        evicted=[]
        for cid in chosen:
            if self.registry.close(cid):evicted.append(cid)
        allowed=level=='low'
        r=CapsuleLifecycleReceipt(level,allowed,tuple(evicted),protected); self.event_sink({'event_type':'crystal.capsule_lifecycle','pressure_level':level,'evicted':list(evicted),'protected':list(protected)})
        return r

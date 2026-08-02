from __future__ import annotations
class CapsuleEvictionPolicy:
    def choose(self, entries, *, pressure_level:str, pin_registry=None, max_count:int|None=None):
        level=str(pressure_level).lower()
        if level not in {'high','critical'}: return ()
        candidates=[]
        for e in entries:
            if pin_registry and pin_registry.is_pinned(e.capsule_id,workspace_id=e.workspace_id,privacy_domain=e.privacy_domain): continue
            candidates.append(e)
        candidates.sort(key=lambda e:(e.use_count,e.last_used_ns,-e.size_bytes))
        limit=len(candidates) if level=='critical' else max(1,len(candidates)//2)
        if max_count is not None: limit=min(limit,max(0,int(max_count)))
        return tuple(e.capsule_id for e in candidates[:limit])

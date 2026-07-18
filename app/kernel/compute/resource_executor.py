"""Unified workload lanes beneath Agent Scheduler."""
from __future__ import annotations
from dataclasses import dataclass
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from threading import BoundedSemaphore, Lock

LANES=("interactive","io","cpu","inference","exclusive","hazardous")
@dataclass(frozen=True)
class WorkloadProfile:
    lane: str
    cpu_weight: int = 100
    memory_mb: int = 512
    timeout_seconds: int = 180
    isolation: str = "thread"
    exclusive_keys: tuple[str, ...] = ()

    def validate(self):
        if self.lane not in LANES: raise ValueError("unknown workload lane")
        if not 1 <= self.cpu_weight <= 1000: raise ValueError("cpu_weight must be 1..1000")
        if self.memory_mb < 64 or self.timeout_seconds < 1: raise ValueError("invalid resource envelope")
        if self.isolation not in {"thread", "process", "sandbox"}: raise ValueError("unsupported workload isolation")
        if any(not key or len(key) > 200 for key in self.exclusive_keys): raise ValueError("invalid exclusive key")

class ResourceExecutor:
    def __init__(self, *, max_workers: int=4, queue_depth: int=32):
        if max_workers < 1: raise ValueError("max_workers must be positive")
        if queue_depth < 0: raise ValueError("queue_depth cannot be negative")
        widths={"interactive":1,"io":max_workers,"cpu":max(1,max_workers//2),"inference":1,"exclusive":1,"hazardous":1}
        self._pools={lane:ThreadPoolExecutor(max_workers=widths[lane],thread_name_prefix=f"beast-{lane}") for lane in LANES}
        self._process_pool=ProcessPoolExecutor(max_workers=widths["cpu"])
        self._capacity={lane:widths[lane]+queue_depth for lane in LANES}
        self._admission={lane:BoundedSemaphore(self._capacity[lane]) for lane in LANES}
        self._widths=widths; self._queue_depth=queue_depth
        self._lock=Lock(); self._submitted={lane:0 for lane in LANES}; self._completed={lane:0 for lane in LANES}; self._rejected={lane:0 for lane in LANES}; self._exclusive_in_flight:set[str]=set(); self._closed=False
    def submit(self, profile: WorkloadProfile, fn, *args, **kwargs):
        profile.validate()
        if self._closed: raise RuntimeError("resource executor is shut down")
        approved=bool(kwargs.pop("approved",False))
        if profile.lane=="hazardous" and not approved: raise PermissionError("hazardous lane requires approval")
        sandboxed=bool(kwargs.pop("sandboxed",False))
        if profile.lane=="hazardous" and (profile.isolation!="sandbox" or not sandboxed): raise PermissionError("hazardous lane requires an acknowledged sandbox boundary")
        if not self._admission[profile.lane].acquire(blocking=False):
            with self._lock: self._rejected[profile.lane]+=1
            raise RuntimeError(f"{profile.lane} lane admission capacity exhausted")
        keys=set(profile.exclusive_keys)
        with self._lock:
            if keys & self._exclusive_in_flight:
                self._rejected[profile.lane]+=1; self._admission[profile.lane].release()
                raise RuntimeError("exclusive workload key is already active")
            self._exclusive_in_flight.update(keys); self._submitted[profile.lane]+=1
        try:
            pool=self._process_pool if profile.isolation=="process" else self._pools[profile.lane]
            future=pool.submit(fn,*args,**kwargs)
        except Exception:
            with self._lock:
                self._submitted[profile.lane]-=1; self._exclusive_in_flight.difference_update(keys)
            self._admission[profile.lane].release()
            raise
        future.add_done_callback(lambda _future,lane=profile.lane,lease_keys=keys:self._mark_complete(lane,lease_keys))
        return future
    def _mark_complete(self,lane,keys):
        with self._lock: self._completed[lane]+=1; self._exclusive_in_flight.difference_update(keys)
        self._admission[lane].release()
    def snapshot(self):
        with self._lock: return {lane:{"submitted":self._submitted[lane],"completed":self._completed[lane],"rejected":self._rejected[lane],"in_flight":self._submitted[lane]-self._completed[lane],"workers":self._widths[lane],"admission_capacity":self._capacity[lane]} for lane in LANES}
    def shutdown(self, *, wait=True):
        self._closed=True
        for pool in self._pools.values(): pool.shutdown(wait=wait,cancel_futures=not wait)
        self._process_pool.shutdown(wait=wait,cancel_futures=not wait)

from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter_ns, process_time_ns
from typing import Protocol
from .x4_contracts import build_manifest, X4Refusal
from .x4_cas import FileCAS
from .x4_protocol import Receiver
from .x5_contracts import LaneEconomics, SelectionPolicy, X5Receipt, X5Refusal
from .x5_economics import choose_lane, economics_dict

class GovernedLane(Protocol):
    name: str
    physical_lane: bool
    setup_us: int
    umem_bytes: int
    def fetch(self,index:int,expected_digest:str)->bytes: ...
    @property
    def retries(self)->int: ...

@dataclass
class MemoryGovernedLane:
    name: str
    chunks: tuple[bytes,...]
    physical_lane: bool=False
    setup_us: int=0
    umem_bytes: int=0
    corrupt_once_index: int|None=None
    _retries: int=0
    def fetch(self,index:int,expected_digest:str)->bytes:
        data=self.chunks[index]
        if self.corrupt_once_index==index and self._retries==0:
            self._retries += 1
            return data+b"!"
        return data
    @property
    def retries(self)->int: return self._retries

class LaneAdapter(Protocol):
    name: str
    physical_lane: bool
    setup_us: int
    umem_bytes: int
    def fetch(self,index:int,expected_digest:str)->bytes: ...
    @property
    def retries(self)->int: ...

def _measure_lane(lane: LaneAdapter, manifest, receiver: Receiver, needed: tuple[int,...], residency_us:int=1) -> LaneEconomics:
    wall0=perf_counter_ns(); cpu0=process_time_ns(); bytes_sent=0; accepted=0; failure=""; verified=False
    try:
        for seq,index in enumerate(needed,1):
            ref=manifest.chunks[index]
            data=lane.fetch(index,ref.digest)
            receiver.accept(manifest,index,data,seq)
            bytes_sent += len(data); accepted += 1
        verify0=perf_counter_ns(); receiver.reconstruct(manifest); verify1=perf_counter_ns(); verified=True
        reconstruct_us=max(0,(verify1-verify0)//1000)
    except Exception as exc:
        reconstruct_us=0; failure=str(exc)
    wall1=perf_counter_ns(); cpu1=process_time_ns()
    transfer_us=max(0,(wall1-wall0)//1000)
    cpu_us=max(0,(cpu1-cpu0)//1000)
    retry_us=max(0,lane.retries*100)
    umem_cost=max(0,lane.umem_bytes*residency_us)
    delivery=(accepted/len(needed)) if needed else 1.0
    return LaneEconomics(lane.name,lane.setup_us,transfer_us,0,reconstruct_us,retry_us,cpu_us,umem_cost,bytes_sent,manifest.object_size-bytes_sent,lane.retries,delivery,verified,True,lane.physical_lane,failure)

def run_x5(data:bytes,cas_root:Path,lanes:list[LaneAdapter],chunk_size:int=65536,preseed:int=0,policy:SelectionPolicy|None=None):
    policy=policy or SelectionPolicy()
    manifest=build_manifest(data,chunk_size); chunks=tuple(data[c.offset:c.offset+c.size] for c in manifest.chunks)
    cas=FileCAS(cas_root)
    for ref,part in zip(manifest.chunks[:preseed],chunks[:preseed]): cas.put_verified(part,ref.digest)
    base_receiver=Receiver(cas); needed=base_receiver.negotiate(manifest).needed_indexes
    measurements=[]
    for lane in lanes:
        # Each attempt uses a clean receiver sequence ledger but the same verified CAS.
        measurements.append(_measure_lane(lane,manifest,Receiver(cas),needed))
    selected=choose_lane(measurements,policy)
    baseline=next((e for e in measurements if e.lane=="ordinary_socket" and e.verified),selected)
    receipt=X5Receipt("X5",manifest.object_digest,manifest.manifest_digest,selected.lane,baseline.lane,selected.total_cost,baseline.total_cost,baseline.total_cost-selected.total_cost,selected.total_cost<=baseline.total_cost,selected.lane!=lanes[0].name,[economics_dict(e) for e in measurements],selected.bytes_sent,selected.bytes_avoided,selected.verified,False,"transport_selection_only").seal()
    return manifest,receipt,cas

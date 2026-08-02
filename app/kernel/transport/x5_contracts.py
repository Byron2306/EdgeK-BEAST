from __future__ import annotations
from dataclasses import dataclass, asdict
from hashlib import sha256
import json

class X5Refusal(ValueError): pass

def canonical(obj: object) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()

def digest_obj(obj: object) -> str:
    return "sha256:" + sha256(canonical(obj)).hexdigest()

@dataclass(frozen=True)
class LaneEconomics:
    lane: str
    setup_us: int
    transfer_us: int
    verify_us: int
    reconstruct_us: int
    retry_us: int
    cpu_us: int
    umem_residency_byte_us: int
    bytes_sent: int
    bytes_avoided: int
    retries: int
    delivery_ratio: float
    verified: bool
    lawful: bool
    physical_lane: bool
    failure_reason: str = ""
    def __post_init__(self):
        ints=(self.setup_us,self.transfer_us,self.verify_us,self.reconstruct_us,self.retry_us,self.cpu_us,self.umem_residency_byte_us,self.bytes_sent,self.bytes_avoided,self.retries)
        if any(v < 0 for v in ints): raise X5Refusal("negative economic field")
        if not 0 <= self.delivery_ratio <= 1: raise X5Refusal("invalid delivery ratio")
    @property
    def total_cost(self) -> int:
        return self.setup_us+self.transfer_us+self.verify_us+self.reconstruct_us+self.retry_us+self.cpu_us+self.umem_residency_byte_us

@dataclass(frozen=True)
class SelectionPolicy:
    minimum_delivery_ratio: float = 0.999
    maximum_retries: int = 2
    maximum_cost: int = 2**63-1
    require_verified: bool = True
    require_lawful: bool = True
    def __post_init__(self):
        if not 0 < self.minimum_delivery_ratio <= 1: raise X5Refusal("invalid minimum delivery ratio")
        if self.maximum_retries < 0 or self.maximum_cost <= 0: raise X5Refusal("invalid selection bounds")

@dataclass
class X5Receipt:
    phase: str
    object_digest: str
    manifest_digest: str
    selected_lane: str
    baseline_lane: str
    selected_total_cost: int
    baseline_total_cost: int
    net_savings: int
    break_even: bool
    fallback_used: bool
    attempts: list[dict]
    bytes_sent: int
    bytes_avoided: int
    reconstruction_verified: bool
    raw_payload_retained: bool
    authority: str
    receipt_digest: str = ""
    def seal(self):
        body=asdict(self); body.pop("receipt_digest",None)
        self.receipt_digest=digest_obj(body); return self

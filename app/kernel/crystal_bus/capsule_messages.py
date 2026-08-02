from __future__ import annotations
from dataclasses import dataclass, asdict
import hashlib, json, time, uuid

def canonical(value): return json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()
def digest(value): return "sha256:"+hashlib.sha256(canonical(value)).hexdigest()

@dataclass(frozen=True)
class CapsuleOffer:
    capsule_digest: str
    capsule_size: int
    crystal_id: str
    promotion_digest: str
    capability_lease_digest: str
    audience: str
    expires_at: float
    sequence: int = 0
    message_id: str = ""
    fd_count: int = 1
    message_type: str = "CRYSTAL_CAPSULE_OFFER"
    def __post_init__(self):
        if not self.message_id: object.__setattr__(self,"message_id","msg_"+uuid.uuid4().hex)
        if self.fd_count != 1 or self.capsule_size <= 0 or not all((self.capsule_digest,self.crystal_id,self.promotion_digest,self.capability_lease_digest,self.audience)):
            raise ValueError("invalid capsule offer")
    def with_sequence(self, seq:int):
        d=asdict(self); d["sequence"]=seq; return CapsuleOffer(**d)
    def encode(self)->bytes: return canonical(asdict(self))
    @classmethod
    def decode(cls,data:bytes):
        value=json.loads(data.decode()); offer=cls(**value)
        if offer.encode()!=data: raise ValueError("noncanonical capsule offer")
        return offer
    @property
    def control_digest(self): return digest(asdict(self))

from __future__ import annotations
from dataclasses import dataclass, asdict
from hashlib import sha256
import json

class X8Refusal(ValueError): pass

def canonical(obj: object) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()

def digest_obj(obj: object) -> str:
    return "sha256:" + sha256(canonical(obj)).hexdigest()

@dataclass(frozen=True)
class RemoteResidualCandidate:
    candidate_id: str
    sender_node: str
    object_digest: str
    manifest_digest: str
    total_bytes: int
    local_bytes: int
    transport_setup_us: int
    transport_us: int
    verification_us: int
    reconstruction_us: int
    admission_us: int
    expected_retry_us: int
    trust_verified: bool
    manifest_verified: bool
    replay_fresh: bool
    reconstruction_expected: bool
    promotion_allowed: bool = False
    execution_allowed: bool = False
    def __post_init__(self):
        if not self.candidate_id or not self.sender_node: raise X8Refusal("identity required")
        if not self.object_digest.startswith("sha256:") or not self.manifest_digest.startswith("sha256:"): raise X8Refusal("digest required")
        nums=(self.total_bytes,self.local_bytes,self.transport_setup_us,self.transport_us,self.verification_us,self.reconstruction_us,self.admission_us,self.expected_retry_us)
        if any(v < 0 for v in nums): raise X8Refusal("negative field")
        if self.local_bytes > self.total_bytes: raise X8Refusal("local bytes exceed object")
        if self.promotion_allowed or self.execution_allowed: raise X8Refusal("remote candidate cannot carry authority")
    @property
    def missing_bytes(self) -> int: return self.total_bytes-self.local_bytes
    @property
    def total_cost_us(self) -> int:
        return self.transport_setup_us+self.transport_us+self.verification_us+self.reconstruction_us+self.admission_us+self.expected_retry_us
    @property
    def eligible(self) -> bool:
        return self.trust_verified and self.manifest_verified and self.replay_fresh and self.reconstruction_expected

@dataclass(frozen=True)
class LocalRouteCandidate:
    route: str
    cost_us: int
    lawful: bool = True
    verified: bool = True
    def __post_init__(self):
        if not self.route or self.cost_us < 0: raise X8Refusal("invalid local route")

@dataclass(frozen=True)
class X8Policy:
    maximum_remote_cost_us: int = 60_000_000
    maximum_missing_bytes: int = 1 << 30
    require_positive_savings: bool = True
    def __post_init__(self):
        if self.maximum_remote_cost_us <= 0 or self.maximum_missing_bytes < 0: raise X8Refusal("invalid policy")

@dataclass
class X8DecisionReceipt:
    phase: str
    selected_route: str
    selected_candidate_id: str
    selected_cost_us: int
    baseline_route: str
    baseline_cost_us: int
    net_savings_us: int
    remote_selected: bool
    remote_eligible: bool
    missing_bytes: int
    local_bytes: int
    object_digest: str
    trust_verified: bool
    manifest_verified: bool
    replay_fresh: bool
    reconstruction_verified: bool
    promotion_allowed: bool
    execution_authority_transferred: bool
    authority: str
    alternatives: list[dict]
    receipt_digest: str = ""
    def seal(self):
        body=asdict(self); body.pop("receipt_digest",None)
        self.receipt_digest=digest_obj(body); return self

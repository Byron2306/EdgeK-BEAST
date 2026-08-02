from __future__ import annotations

from dataclasses import dataclass, asdict
from hashlib import sha256
import json, time


class X7Refusal(RuntimeError):
    pass


def canonical_digest(value: object) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    return "sha256:" + sha256(raw).hexdigest()


@dataclass(frozen=True)
class X7Approval:
    interface: str
    sender_node: str
    receiver_node: str
    object_digest: str
    max_packets: int
    max_bytes: int
    expires_unix_ns: int
    approval_id: str

    def validate(self, now_ns: int | None = None) -> None:
        now_ns = time.time_ns() if now_ns is None else now_ns
        if not self.interface or self.interface in {"lo", "any"}:
            raise X7Refusal("invalid production interface")
        if self.sender_node == self.receiver_node:
            raise X7Refusal("sender and receiver must be distinct")
        if not self.object_digest.startswith("sha256:"):
            raise X7Refusal("object digest must be sha256")
        if not 1 <= self.max_packets <= 1_000_000:
            raise X7Refusal("packet budget outside bounds")
        if not 1 <= self.max_bytes <= 1_073_741_824:
            raise X7Refusal("byte budget outside bounds")
        if self.expires_unix_ns <= now_ns:
            raise X7Refusal("operator approval expired")
        if not self.approval_id:
            raise X7Refusal("approval id required")

    @property
    def digest(self) -> str:
        return canonical_digest(asdict(self))


@dataclass(frozen=True)
class X7Preflight:
    interface_exists: bool
    interface_up: bool
    interface_matches_approval: bool
    peer_reachable: bool
    btf_available: bool
    bpffs_available: bool
    privileges_available: bool
    existing_xdp_program_id: int | None
    replacement_explicitly_allowed: bool

    def validate(self) -> None:
        required = {
            "interface_exists": self.interface_exists,
            "interface_up": self.interface_up,
            "interface_matches_approval": self.interface_matches_approval,
            "peer_reachable": self.peer_reachable,
            "btf_available": self.btf_available,
            "bpffs_available": self.bpffs_available,
            "privileges_available": self.privileges_available,
        }
        failed = [k for k, v in required.items() if not v]
        if failed:
            raise X7Refusal("preflight failed: " + ",".join(failed))
        if self.existing_xdp_program_id is not None and not self.replacement_explicitly_allowed:
            raise X7Refusal("existing XDP program present; replacement not approved")


@dataclass(frozen=True)
class X7LaneResult:
    lane: str
    verified: bool
    object_digest: str
    packets: int
    bytes_sent: int
    p99_latency_us: float
    delivery_ratio: float
    cpu_ms: float
    detached: bool
    rollback_verified: bool
    error: str | None = None


@dataclass(frozen=True)
class X7Receipt:
    phase: str
    approval_digest: str
    interface: str
    object_digest: str
    af_xdp: X7LaneResult
    socket_shadow: X7LaneResult
    roots_equal: bool
    budget_respected: bool
    xdp_detached: bool
    prior_xdp_restored: bool
    production_nic_touched: bool
    promotion_allowed: bool
    execution_allowed: bool
    authority: str
    closure_digest: str

    @classmethod
    def build(cls, approval: X7Approval, af: X7LaneResult, shadow: X7LaneResult,
              prior_xdp_restored: bool) -> "X7Receipt":
        roots_equal = af.verified and shadow.verified and af.object_digest == shadow.object_digest == approval.object_digest
        budget = af.packets <= approval.max_packets and af.bytes_sent <= approval.max_bytes
        base = {
            "phase": "X7",
            "approval_digest": approval.digest,
            "interface": approval.interface,
            "object_digest": approval.object_digest,
            "af_xdp": asdict(af),
            "socket_shadow": asdict(shadow),
            "roots_equal": roots_equal,
            "budget_respected": budget,
            "xdp_detached": af.detached,
            "prior_xdp_restored": prior_xdp_restored,
            "production_nic_touched": True,
            "promotion_allowed": False,
            "execution_allowed": False,
            "authority": "bounded_production_transport_canary_only",
        }
        return cls(
            phase="X7", approval_digest=approval.digest, interface=approval.interface,
            object_digest=approval.object_digest, af_xdp=af, socket_shadow=shadow,
            roots_equal=roots_equal, budget_respected=budget, xdp_detached=af.detached,
            prior_xdp_restored=prior_xdp_restored, production_nic_touched=True,
            promotion_allowed=False, execution_allowed=False,
            authority="bounded_production_transport_canary_only",
            closure_digest=canonical_digest(base),
        )

    @property
    def valid(self) -> bool:
        return all((self.roots_equal, self.budget_respected, self.xdp_detached,
                    self.prior_xdp_restored, self.af_xdp.rollback_verified,
                    self.socket_shadow.verified)) and not self.promotion_allowed and not self.execution_allowed

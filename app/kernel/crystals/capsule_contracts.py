from __future__ import annotations
from dataclasses import dataclass, asdict
from enum import Enum
from typing import Any, Mapping
import hashlib, json, time

MAGIC = "BEAST_CRYSTAL_CAPSULE"
CAPSULE_VERSION = 1
REQUIRED_SEAL_NAMES = ("F_SEAL_WRITE", "F_SEAL_GROW", "F_SEAL_SHRINK", "F_SEAL_SEAL")

def canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")

def sha256_digest(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()

class CapsuleStatus(str, Enum):
    VERIFIED_ARTIFACT = "verified_artifact"
    REJECTED_INTEGRITY = "rejected_integrity"
    REJECTED_SIGNATURE = "rejected_signature"
    REJECTED_SCOPE = "rejected_scope"
    REJECTED_POLICY = "rejected_policy"
    REJECTED_REVOKED = "rejected_revoked"
    REJECTED_EXPIRED = "rejected_expired"
    REJECTED_INCOMPATIBLE = "rejected_incompatible"

@dataclass(frozen=True)
class ExecutionBounds:
    max_runtime_ms: int
    max_memory_bytes: int
    max_output_bytes: int
    filesystem_scope: tuple[str, ...] = ()
    network_scope: tuple[str, ...] = ()
    def __post_init__(self):
        if min(self.max_runtime_ms, self.max_memory_bytes, self.max_output_bytes) <= 0:
            raise ValueError("execution bounds must be positive")

@dataclass(frozen=True)
class SealedCrystalCapsuleManifest:
    crystal_id: str
    crystal_ir_version: int
    artifact_digest: str
    promotion_digest: str
    policy_digest: str
    source_state_digest: str
    workspace_id: str
    privacy_domain: str
    task_class: str
    audience_class: str
    required_capability: str
    one_use_required: bool
    expires_at: float
    verifier_id: str
    rollback_contract_digest: str
    signer_id: str
    execution_bounds: ExecutionBounds
    capsule_version: int = CAPSULE_VERSION
    authority: str = "artifact_only"
    def __post_init__(self):
        required = [self.crystal_id, self.artifact_digest, self.promotion_digest, self.policy_digest,
                    self.source_state_digest, self.workspace_id, self.privacy_domain, self.task_class,
                    self.audience_class, self.required_capability, self.verifier_id,
                    self.rollback_contract_digest, self.signer_id]
        if not all(required): raise ValueError("manifest fields cannot be empty")
        if self.capsule_version != CAPSULE_VERSION: raise ValueError("unsupported capsule version")
        if self.authority != "artifact_only": raise ValueError("capsule cannot carry execution authority")
        if self.expires_at <= time.time() - 86400: raise ValueError("capsule expiry is implausibly old")
    def as_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["execution_bounds"]["filesystem_scope"] = list(self.execution_bounds.filesystem_scope)
        d["execution_bounds"]["network_scope"] = list(self.execution_bounds.network_scope)
        return d

@dataclass(frozen=True)
class CapsuleCreationReceipt:
    capsule_id: str
    crystal_id: str
    capsule_digest: str
    payload_size: int
    seal_bitmap: int
    required_seals_present: bool
    signer_id: str
    authority: str = "artifact_only"

@dataclass(frozen=True)
class CapsuleVerificationReceipt:
    status: CapsuleStatus
    capsule_digest: str = ""
    crystal_id: str = ""
    signer_id: str = ""
    seal_bitmap: int = 0
    reason: str = ""
    authority: str = "artifact_only"
    details: Mapping[str, Any] | None = None

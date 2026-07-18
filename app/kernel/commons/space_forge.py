"""Signed, bounded Commons Space manifests."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping
from app.kernel.execution.port_lease_broker import PortLeaseBroker, PortLease


@dataclass(frozen=True)
class SpaceManifest:
    space_id: str
    image_digest: str
    cpu: float
    memory_mb: int
    mounts: tuple[str, ...]
    outbound_policy: str
    port: int
    signature: str
    authority_ref: str = ""
    appraisal_ref: str = ""


class SpaceForge:
    def __init__(self, broker: PortLeaseBroker | None = None, *, verifier=None, appraisal_verifier=None, require_appraisal: bool = False, require_authority: bool = False, require_verification: bool = False):
        self.broker = broker or PortLeaseBroker(); self.verifier=verifier; self.appraisal_verifier=appraisal_verifier; self.require_appraisal=require_appraisal; self.require_authority=require_authority; self.require_verification=require_verification

    def validate(self, payload: Mapping[str, Any]) -> SpaceManifest:
        digest=str(payload.get("image_digest", "")); signature=str(payload.get("signature") or ""); authority=str(payload.get("authority_ref") or ""); appraisal=str(payload.get("appraisal_ref") or "")
        if not signature or not digest.startswith("sha256:") or len(digest)!=71:
            raise ValueError("signed digest-bound Space required")
        if self.require_authority and not authority: raise ValueError("Space signing authority is required")
        authority=authority or "beast.local/legacy"
        if self.require_appraisal and not appraisal: raise PermissionError("ARDA appraisal reference required")
        cpu=float(payload.get("cpu", 0)); memory=int(payload.get("memory_mb", 0)); port=int(payload.get("port", 0))
        if cpu <= 0 or memory <= 0 or not 0 <= port <= 65535: raise ValueError("invalid Space resource bounds")
        policy=str(payload.get("outbound_policy", "deny"))
        if policy not in {"deny", "outbound-docs-only", "allow-listed"}: raise ValueError("invalid outbound policy")
        mounts=tuple(str(item) for item in (payload.get("mounts") or ()))
        if any(not item.startswith("commons://") for item in mounts): raise ValueError("Space mounts must use commons:// identities")
        signed_body={"space_id":str(payload["space_id"]),"image_digest":digest,"cpu":cpu,"memory_mb":memory,"mounts":list(mounts),"outbound_policy":policy,"port":port,"authority_ref":authority,"appraisal_ref":appraisal}
        if self.require_verification and self.verifier is None: raise PermissionError("Space signature verifier is not configured")
        if self.verifier and not self.verifier(signed_body,signature,authority): raise PermissionError("Space signature verification failed")
        if self.require_appraisal and self.appraisal_verifier is None: raise PermissionError("ARDA appraisal verifier is not configured")
        if self.appraisal_verifier and not self.appraisal_verifier(payload.get("arda_appraisal"),signed_body): raise PermissionError("ARDA appraisal verification failed")
        return SpaceManifest(str(payload["space_id"]), digest, cpu, memory, mounts, policy, port, signature, authority, appraisal)

    def lease_port(self, space: SpaceManifest, *, workspace_id: str, capability_ref: str = "",
                   policy_generation: str = "", registry_digest: str = "") -> PortLease:
        return self.broker.reserve(
            space.space_id, workspace_id, port=space.port,
            authority_ref=space.authority_ref, appraisal_ref=space.appraisal_ref,
            capability_ref=capability_ref, policy_generation=policy_generation,
            registry_digest=registry_digest,
        )

"""Bounded Commons artifact/job scheduling and witness receipts."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib, json
import base64
from typing import Any, Mapping


@dataclass(frozen=True)
class ArtifactManifest:
    artifact_id: str
    kind: str
    digest: str
    signature: str


@dataclass(frozen=True)
class NodeAdvertisement:
    node_id: str
    attestation: str
    capabilities: tuple[str, ...]
    pressure_budget: float
    reliability: float
    route_penalty: float = 0.0
    expires_at: float = 0.0
    appraisal_ref: str = ""
    attestation_evidence: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class WitnessReceipt:
    job_id: str
    node_id: str
    artifact_digest: str
    output_digest: str
    verified: bool
    dataset_digest: str = ""
    dataset_shard: str = ""
    appraisal_ref: str = ""
    policy_generation: str = ""
    receipt_digest: str = ""
    authority: str = ""
    signature: str = ""


class CommonsJobChoir:
    def __init__(self, *, attestation_verifier=None, require_attestation_verification: bool = False,
                 witness_signer=None, witness_authority: str = ""):
        self.attestation_verifier=attestation_verifier; self.require_attestation_verification=require_attestation_verification
        self.witness_signer=witness_signer; self.witness_authority=witness_authority

    def publish(self, kind: str, payload: Mapping[str, Any], signature: str) -> ArtifactManifest:
        digest = "sha256:" + hashlib.sha256(json.dumps(dict(payload), sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        if not signature: raise ValueError("signed artifact manifest required")
        return ArtifactManifest(f"commons:{kind}:{digest[7:19]}", kind, digest, signature)

    def score(self, node: NodeAdvertisement, *, required: str) -> float:
        if not 0 <= node.reliability <= 1 or not 0 <= node.pressure_budget <= 1: raise ValueError("invalid node telemetry")
        return node.reliability + node.pressure_budget + (1.0 if required in node.capabilities else -100.0) + (1.0 if node.attestation == "verified" else -100.0) - max(0.0,node.route_penalty)

    def select(self, nodes, *, required: str, now: float = 0.0) -> NodeAdvertisement:
        if self.require_attestation_verification and self.attestation_verifier is None: raise PermissionError("Commons node attestation verifier is not configured")
        eligible=[node for node in nodes if required in node.capabilities and node.attestation=="verified" and (not node.expires_at or node.expires_at>now)]
        if self.attestation_verifier: eligible=[node for node in eligible if self.attestation_verifier(node)]
        if not eligible: raise LookupError("no attested Commons node satisfies the job")
        return max(eligible,key=lambda node:self.score(node,required=required))

    def witness(self, job_id: str, node: NodeAdvertisement, artifact: ArtifactManifest, output: bytes, *, lineage: Any = None) -> WitnessReceipt:
        if not job_id or node.attestation!="verified": raise PermissionError("verified node and job identity required")
        if self.require_attestation_verification and (self.attestation_verifier is None or not self.attestation_verifier(node)): raise PermissionError("cryptographic node attestation verification required")
        digest = "sha256:" + hashlib.sha256(output).hexdigest()
        shard = ""
        dataset_digest = ""
        if lineage is not None:
            dataset_digest = lineage.dataset_digest
            shard = f"{lineage.shard_index}/{lineage.shard_count}"
        policy_generation=str((node.attestation_evidence or {}).get("policy_generation") or "")
        body={"job_id":job_id,"node_id":node.node_id,"artifact_digest":artifact.digest,
              "output_digest":digest,"verified":node.attestation=="verified",
              "dataset_digest":dataset_digest,"dataset_shard":shard,
              "appraisal_ref":node.appraisal_ref,"policy_generation":policy_generation,
              "authority":self.witness_authority}
        canonical=json.dumps(body,sort_keys=True,separators=(",",":")).encode()
        receipt_digest="sha256:"+hashlib.sha256(canonical).hexdigest()
        signature=base64.b64encode(self.witness_signer.sign(canonical)).decode("ascii") if self.witness_signer else ""
        return WitnessReceipt(job_id,node.node_id,artifact.digest,digest,node.attestation=="verified",
                              dataset_digest,shard,node.appraisal_ref,policy_generation,
                              receipt_digest,self.witness_authority,signature)

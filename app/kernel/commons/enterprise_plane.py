"""Enterprise Commons composition root, admission workflows, and evidence."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import tempfile
import time
from typing import Any, Mapping

from .artifact_registry import CommonsArtifactRegistry
from .artifact_vault import ArtifactVault
from .chunk_store import ChunkStore
from .dataset_river import DatasetRiver
from .evidence_bridge import CommonsEvidenceBridge
from .job_choir import CommonsJobChoir
from .route_damping import RouteFlapDampener
from .space_forge import SpaceForge
from .tpm_attestation import DEFAULT_PCRS, TpmChallengeLedger


class CommonsEnterprisePlane:
    def __init__(self, root: str | Path, *, signature_verifier=None, appraisal_verifier=None,
                 node_attestation_verifier=None, witness_signer=None, witness_authority: str = "",
                 broker=None, sensorium=None, evidence=None, tpm_appraisal_issuer=None):
        self.root=Path(root); self.root.mkdir(parents=True,exist_ok=True)
        self.signature_verifier=signature_verifier; self.appraisal_verifier=appraisal_verifier
        self.node_attestation_verifier=node_attestation_verifier
        self.registry=CommonsArtifactRegistry(
            self.root/"registry"/"manifests.jsonl",require_signature=True,
            verifier=signature_verifier,require_verification=True,strict_load=True,
        )
        self.vault=ArtifactVault(self.root/"vault")
        self.chunks=ChunkStore(self.root/"chunks")
        self.datasets=DatasetRiver()
        self.jobs=CommonsJobChoir(
            attestation_verifier=node_attestation_verifier,require_attestation_verification=True,
            witness_signer=witness_signer,witness_authority=witness_authority,
        )
        self.routes=RouteFlapDampener(path=self.root/"routes"/"damping.json",strict_load=True)
        self.tpm_challenges=TpmChallengeLedger(self.root/"attestation"/"challenges.sqlite3")
        self.tpm_appraisal_issuer=tpm_appraisal_issuer
        self.spaces=SpaceForge(
            broker=broker,verifier=signature_verifier,appraisal_verifier=appraisal_verifier,
            require_appraisal=True,require_authority=True,require_verification=True,
        )
        self.evidence_bridge=CommonsEvidenceBridge(sensorium=sensorium,evidence=evidence)
        self.remote_imports_root=self.root/"remote-imports"
        self.remote_imports_root.mkdir(parents=True,exist_ok=True)

    def ingest_artifact(self, kind: str, metadata: Mapping[str,Any], payload: bytes, *,
                        signature: str, authority: str, workspace_id: str = "",
                        policy_generation: str = "unknown"):
        """Verify manifest, bytes, chunks, and emit one linked admission receipt."""
        payload_digest="sha256:"+hashlib.sha256(payload).hexdigest()
        if metadata.get("payload_digest") != payload_digest:
            raise ValueError("Commons manifest payload digest does not match supplied bytes")
        manifest=self.registry.publish(kind,dict(metadata),signature=signature,authority=authority)
        vault_digest=self.vault.put(payload)
        chunk_manifest=self.chunks.put(payload)
        if vault_digest!=payload_digest or chunk_manifest.artifact_digest!=payload_digest:
            raise RuntimeError("Commons storage layers disagree on content identity")
        node=self.evidence_bridge.emit("commons.artifact_admitted",{
            "artifact_id":manifest.artifact_id,"manifest_digest":manifest.digest,
            "payload_digest":payload_digest,"chunk_count":len(chunk_manifest.chunks),
            "authority":authority,
        },workspace_id=workspace_id,policy_generation=policy_generation)
        return {"manifest":manifest,"chunk_manifest":chunk_manifest,"evidence_node_id":node.node_id}

    def record_route_event(self, route_id: str, event: str, *, workspace_id: str = "",
                           policy_generation: str = "unknown", now: float | None = None):
        score=self.routes.record(route_id,event,now=now)
        node=self.evidence_bridge.emit("commons.route_damping",{
            "route_id":route_id,"event":event,"penalty":score.penalty,
            "suppressed":score.penalty>=self.routes.suppress_at,
        },workspace_id=workspace_id,policy_generation=policy_generation)
        return score,node

    def select_node(self, nodes, *, required: str, workspace_id: str = "",
                    policy_generation: str = "unknown", now: float | None = None):
        moment=time.time() if now is None else now
        eligible=[node for node in nodes if not self.routes.suppressed(node.node_id,now=moment)]
        selected=self.jobs.select(eligible,required=required,now=moment)
        evidence=self.evidence_bridge.emit("commons.job_scheduled",{
            "node_id":selected.node_id,"required_capability":required,
            "appraisal_ref":selected.appraisal_ref,"route_penalty":selected.route_penalty,
        },workspace_id=workspace_id,policy_generation=policy_generation)
        return selected,evidence

    def witness_job(self, job_id, node, artifact, output: bytes, *, lineage=None,
                    workspace_id: str = "", policy_generation: str = "unknown"):
        receipt=self.jobs.witness(job_id,node,artifact,output,lineage=lineage)
        evidence=self.evidence_bridge.emit("commons.job_witnessed",{
            "job_id":receipt.job_id,"node_id":receipt.node_id,
            "artifact_digest":receipt.artifact_digest,"output_digest":receipt.output_digest,
            "dataset_digest":receipt.dataset_digest,"receipt_digest":receipt.receipt_digest,
            "appraisal_ref":receipt.appraisal_ref,
        },workspace_id=workspace_id,policy_generation=policy_generation)
        return receipt,evidence

    def admit_space(self, payload: Mapping[str,Any], *, workspace_id: str,
                    capability_ref: str, policy_generation: str, registry_digest: str = ""):
        space=self.spaces.validate(payload)
        if not capability_ref or not policy_generation:
            raise PermissionError("Commons Space admission requires capability and policy generation")
        lease=self.spaces.lease_port(
            space,workspace_id=workspace_id,capability_ref=capability_ref,
            policy_generation=policy_generation,registry_digest=registry_digest,
        )
        evidence=self.evidence_bridge.emit("commons.space_admitted",{
            "space_id":space.space_id,"image_digest":space.image_digest,
            "lease_id":lease.lease_id,"listener_generation":lease.listener_generation,
            "authority_ref":space.authority_ref,"appraisal_ref":space.appraisal_ref,
            "capability_ref":capability_ref,
        },workspace_id=workspace_id,policy_generation=policy_generation)
        return space,lease,evidence

    def issue_tpm_challenge(self, node_id: str, *, ttl_seconds: float = 300.0):
        """Issue a one-use challenge; issuance is not an appraisal or admission."""
        return self.tpm_challenges.issue(
            node_id,
            audience="beast-commons-node-attestation",
            pcr_bank="sha256",
            pcrs=DEFAULT_PCRS,
            ttl_seconds=ttl_seconds,
        )

    def admit_remote_revision(self, node_id: str, revision: Mapping[str, Any], blobs: Mapping[str, bytes], *,
                              workspace_id: str = "", policy_generation: str = "unknown"):
        """Quarantine a pinned remote revision in local immutable custody.

        This is not promotion.  The remote signature has already been verified
        by the egress gateway; this boundary re-verifies all content identities
        and records that held-out local reproduction remains mandatory.
        """
        receipt=dict(revision.get("receipt") or {})
        manifest=dict(revision.get("manifest") or {})
        if receipt.get("node_id") != node_id or receipt.get("maximum_authority") != "verify_only":
            raise PermissionError("remote Commons receipt exceeded its pinned node or authority boundary")
        manifest_bytes=json.dumps(manifest,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()
        manifest_digest="sha256:"+hashlib.sha256(manifest_bytes).hexdigest()
        if revision.get("manifest_digest") != manifest_digest or receipt.get("manifest_digest") != manifest_digest:
            raise PermissionError("remote Commons manifest and receipt binding failed")
        if manifest.get("authority") != "remote_hypothesis" or manifest.get("maximum_authority") != "verify_only":
            raise PermissionError("remote Commons manifest may only enter as a verify-only hypothesis")
        custody=[]
        for item in manifest.get("files") or ():
            digest=str(item.get("digest") or ""); payload=blobs.get(digest)
            if payload is None or len(payload)!=int(item.get("size") or 0) or "sha256:"+hashlib.sha256(payload).hexdigest()!=digest:
                raise ValueError("remote Commons imported blob failed local custody verification")
            vault_digest=self.vault.put(payload); chunks=self.chunks.put(payload)
            if vault_digest!=digest or chunks.artifact_digest!=digest:
                raise RuntimeError("remote Commons local storage layers disagree")
            custody.append({"path":str(item.get("path") or ""),"digest":digest,"chunks":list(chunks.chunks)})
        record={
            "beast_object_type":"commons_remote_revision_quarantine_receipt","version":"1.0",
            "node_id":node_id,"bucket_id":receipt.get("bucket_id"),"revision":receipt.get("revision"),
            "manifest_digest":manifest_digest,"remote_receipt_digest":revision.get("receipt_digest"),
            "remote_node_signature":revision.get("node_signature"),"custody":custody,
            "status":"quarantined_hypothesis","maximum_authority":"verify_only",
            "local_reproduction_required":True,"advertised_claims_counted":0,
        }
        record_bytes=json.dumps(record,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()
        record["admission_digest"]="sha256:"+hashlib.sha256(record_bytes).hexdigest()
        target=self.remote_imports_root/(record["admission_digest"][7:]+".json")
        if not target.exists():
            descriptor,temp_name=tempfile.mkstemp(prefix=".remote-import-",suffix=".tmp",dir=self.remote_imports_root)
            try:
                with os.fdopen(descriptor,"w",encoding="utf-8") as handle:
                    json.dump(record,handle,sort_keys=True,separators=(",",":"),ensure_ascii=False)
                    handle.flush(); os.fsync(handle.fileno())
                os.replace(temp_name,target)
            finally:
                if os.path.exists(temp_name): os.unlink(temp_name)
        evidence=self.evidence_bridge.emit("commons.remote_revision_quarantined",record,
            workspace_id=workspace_id,policy_generation=policy_generation)
        return record,evidence

    def appraise_tpm_node(self, evidence: Mapping[str, Any], *, capabilities=("cpu",),
                          pressure_budget: float = 0.5, reliability: float = 0.8,
                          route_penalty: float = 0.0, workspace_id: str = ""):
        if self.tpm_appraisal_issuer is None:
            raise PermissionError("TPM appraisal issuer is not configured")
        appraisal = self.tpm_appraisal_issuer.issue(
            evidence,
            challenge_ledger=self.tpm_challenges,
            capabilities=tuple(str(item) for item in capabilities),
            pressure_budget=pressure_budget,
            reliability=reliability,
            route_penalty=route_penalty,
        )
        node = self.evidence_bridge.emit("commons.tpm_node_appraised", {
            "node_id": appraisal.node.node_id,
            "appraisal_ref": appraisal.node.appraisal_ref,
            "evidence_digest": appraisal.evidence_digest,
            "request_digest": appraisal.request_digest,
        }, workspace_id=workspace_id, policy_generation=self.tpm_appraisal_issuer.policy_generation)
        return appraisal, node

    def snapshot(self) -> dict:
        signature_ready=self.signature_verifier is not None
        appraisal_ready=self.appraisal_verifier is not None
        attestation_ready=self.node_attestation_verifier is not None
        ready=signature_ready and appraisal_ready and attestation_ready
        return {
            "version":"1.1","mode":"enterprise",
            "artifact_registry":{"count":len(self.registry.list()),"signature_required":self.registry.require_signature,"signature_verifier_configured":signature_ready,"replay_verified":True},
            "artifact_vault":self.vault.stats(),"chunk_store":self.chunks.stats(),
            "dataset_river":{"privacy_labels":sorted(self.datasets.PRIVACY_LABELS),"lineage_required":True,"lazy_streaming":True},
            "job_choir":{"attestation_required":True,"attestation_verifier_configured":attestation_ready,"signed_witnesses":self.jobs.witness_signer is not None},
            "tpm_attestation":{"challenge_ledger":self.tpm_challenges.snapshot(),"pcr_bank":"sha256","pcrs":list(DEFAULT_PCRS),"ak_activation_required":True,"event_log_replay_required":True,"windows_supported_by_contract":True,"submission_verifier_live":self.tpm_appraisal_issuer is not None},
            "route_damping":{"routes":self.routes.snapshot(),"suppress_at":self.routes.suppress_at,"half_life_seconds":self.routes.half_life},
            "space_forge":{"authority_required":self.spaces.require_authority,"appraisal_required":self.spaces.require_appraisal,"signature_verifier_configured":signature_ready,"appraisal_verifier_configured":appraisal_ready,"port_broker":"guardian" if getattr(self.spaces.broker,"guardian_client",None) else "in_process"},
            "evidence":{"control_graph_nodes":len(self.evidence_bridge.evidence.nodes),"sensorium_connected":self.evidence_bridge.sensorium is not None},
            "remote_imports":{"quarantined":len(list(self.remote_imports_root.glob("*.json"))),"local_reproduction_required":True},
            "admission":{"fail_closed":True,"ready":ready},"status":"ready" if ready else "configuration_required",
        }

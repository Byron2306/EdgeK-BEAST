"""Restart-safe live closure ceremony for Forge-KV publication and remote verification."""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from threading import RLock
from typing import Any, Callable, Mapping

from app.kernel.compute.forge_kv_cross_node_evidence import CrossNodeEvidencePacket
from app.kernel.compute.forge_kv_publication import PublicationApproval, build_revocation
from app.kernel.compute.forge_kv_receiver import ForgeKVReceiverWorker, RevocationPoller
from app.kernel.compute.forge_kv_remote_attestation import RemoteAttestationGate


def _digest(value: Any) -> str:
    encoded=json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=True,default=str).encode()
    return "sha256:"+hashlib.sha256(encoded).hexdigest()


def _atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(path.suffix+".tmp")
    tmp.write_text(json.dumps(dict(value),sort_keys=True,indent=2)+"\n",encoding="utf-8")
    tmp.replace(path)


@dataclass(frozen=True)
class ClosureCheckpoint:
    ceremony_id: str
    dataset_id: str
    commit_digest: str
    phase: str
    updated_at: float
    publication_receipt: Mapping[str, Any] | None = None
    receiver_receipt: Mapping[str, Any] | None = None
    attestation_receipt: Mapping[str, Any] | None = None
    revocation_manifest: Mapping[str, Any] | None = None
    final_packet: Mapping[str, Any] | None = None
    checkpoint_digest: str = ""

    def sealed(self) -> "ClosureCheckpoint":
        value=asdict(replace(self,checkpoint_digest="")); value.pop("checkpoint_digest",None)
        return replace(self,checkpoint_digest=_digest(value))

    def validate(self) -> None:
        value=asdict(self); supplied=value.pop("checkpoint_digest")
        if supplied != _digest(value): raise ValueError("closure checkpoint is tampered")


class ClosureCheckpointStore:
    def __init__(self, root: Path | str):
        self.root=Path(root).expanduser(); self._lock=RLock()

    def path_for(self, ceremony_id: str) -> Path:
        safe=ceremony_id.replace(":","_").replace("/","_")
        return self.root/(safe+".json")

    def save(self, checkpoint: ClosureCheckpoint) -> ClosureCheckpoint:
        item=checkpoint.sealed()
        with self._lock: _atomic_json(self.path_for(item.ceremony_id),asdict(item))
        return item

    def load(self, ceremony_id: str) -> ClosureCheckpoint | None:
        path=self.path_for(ceremony_id)
        if not path.exists(): return None
        item=ClosureCheckpoint(**json.loads(path.read_text(encoding="utf-8")))
        item.validate(); return item


class ForgeKVLevel8Ceremony:
    """Coordinates one approved publication, receiver verification, and revocation proof."""
    PHASES=("prepared","published","attested","reconstructed","revoked","closed")

    def __init__(self, *, plane: Any, checkpoint_root: Path | str,
                 attestation_gate: RemoteAttestationGate | None = None,
                 receiver: ForgeKVReceiverWorker | None = None):
        self.plane=plane
        self.store=ClosureCheckpointStore(checkpoint_root)
        self.attestation_gate=attestation_gate or RemoteAttestationGate()
        self.receiver=receiver or ForgeKVReceiverWorker()

    def prepare(self, *, ceremony_id: str, dataset_id: str, commit_digest: str, now: float | None=None) -> ClosureCheckpoint:
        existing=self.store.load(ceremony_id)
        if existing:
            if existing.dataset_id != dataset_id or existing.commit_digest != commit_digest:
                raise PermissionError("ceremony identity binding mismatch")
            return existing
        return self.store.save(ClosureCheckpoint(ceremony_id,dataset_id,commit_digest,"prepared",time.time() if now is None else now))

    def publish(self, *, ceremony_id: str, approval: PublicationApproval, commit: Mapping[str,Any],
                files: Mapping[str,bytes], chunks: Mapping[str,bytes], private: bool=True,
                branch: str="", open_pr: bool=True, now: float | None=None) -> ClosureCheckpoint:
        state=self._require(ceremony_id,"prepared")
        if state.publication_receipt is not None: return state
        receipt=self.plane.publish_hf(approval=approval,commit=commit,files=files,chunks=chunks,
                                      private=private,branch=branch,open_pr=open_pr,now=now)
        return self.store.save(replace(state,phase="published",updated_at=time.time(),publication_receipt=receipt,checkpoint_digest=""))

    def attest(self, *, ceremony_id: str, receiver_node_id: str, audience: str,
               policy_digest: str, verifier_digest: str, evidence_factory: Callable[[Any],Mapping[str,Any]],
               verifier: Callable[[Any,Mapping[str,Any]],bool], now: float | None=None) -> ClosureCheckpoint:
        state=self._require(ceremony_id,"published")
        if state.attestation_receipt is not None: return state
        challenge=self.attestation_gate.issue(node_id=receiver_node_id,audience=audience,policy_digest=policy_digest,
                                              verifier_digest=verifier_digest,now=now)
        evidence=evidence_factory(challenge)
        receipt=self.attestation_gate.verify_and_consume(challenge_id=challenge.challenge_id,evidence=evidence,
                                                         verifier=verifier,now=now)
        return self.store.save(replace(state,phase="attested",updated_at=time.time(),attestation_receipt=receipt,checkpoint_digest=""))

    def reconstruct(self, *, ceremony_id: str, commit: Mapping[str,Any], manifest: Mapping[str,Any],
                    fetch_chunk: Callable[[str],bytes], verify_artifact: Callable[[bytes],bool]) -> ClosureCheckpoint:
        state=self._require(ceremony_id,"attested")
        if state.receiver_receipt is not None: return state
        attestation=state.attestation_receipt or {}
        receipt=self.receiver.run(dataset_id=state.dataset_id,commit=commit,manifest=manifest,fetch_chunk=fetch_chunk,
                                  verify_attestation=lambda digest: bool(attestation.get("verified")),
                                  verify_artifact=verify_artifact)
        result=asdict(receipt)
        if not result["locally_verified"] or result["promotion_granted"]:
            raise PermissionError("receiver closure invariant failed")
        return self.store.save(replace(state,phase="reconstructed",updated_at=time.time(),receiver_receipt=result,checkpoint_digest=""))

    def revoke(self, *, ceremony_id: str, reason: str, issuer: str, issued_at: str,
               publish_revocation: Callable[[Mapping[str,Any]],None], fetch_revocations: Callable[[],list[Mapping[str,Any]]]) -> ClosureCheckpoint:
        state=self._require(ceremony_id,"reconstructed")
        if state.revocation_manifest is not None: return state
        tombstone=build_revocation(dataset_id=state.dataset_id,commit_digest=state.commit_digest,reason=reason,issuer=issuer,issued_at=issued_at)
        publish_revocation(tombstone)
        poller=RevocationPoller(fetch_revocations)
        result=poller.poll()
        if state.commit_digest not in result["revoked_commits"]:
            raise PermissionError("receiver did not enforce revocation")
        return self.store.save(replace(state,phase="revoked",updated_at=time.time(),revocation_manifest=tombstone,checkpoint_digest=""))

    def close(self, *, ceremony_id: str, receiver_node_id: str, reconstructed_root_digest: str,
              verifier_digest: str) -> ClosureCheckpoint:
        state=self._require(ceremony_id,"revoked")
        if state.final_packet is not None: return state
        publication=state.publication_receipt or {}; receiver=state.receiver_receipt or {}; attestation=state.attestation_receipt or {}
        packet=CrossNodeEvidencePacket(
            dataset_id=state.dataset_id, local_commit_digest=state.commit_digest,
            remote_commit=str(publication.get("remote_commit") or ""),
            publication_receipt_digest=_digest(publication), receiver_node_id=receiver_node_id,
            receiver_receipt_digest=_digest(receiver), attestation_receipt_digest=_digest(attestation),
            reconstructed_root_digest=reconstructed_root_digest, verifier_digest=verifier_digest,
            native_context_exported=False,promotion_granted=False,
        ).sealed()
        packet.validate()
        body=asdict(packet)
        body["revocation_digest"]=(state.revocation_manifest or {}).get("revocation_digest","")
        body["receiver_reuse_after_revocation"]=False
        body["closure_status"]="closed"
        body["closure_digest"]=_digest(body)
        return self.store.save(replace(state,phase="closed",updated_at=time.time(),final_packet=body,checkpoint_digest=""))

    def _require(self, ceremony_id: str, minimum_phase: str) -> ClosureCheckpoint:
        state=self.store.load(ceremony_id)
        if state is None: raise FileNotFoundError("closure ceremony not prepared")
        if self.PHASES.index(state.phase) < self.PHASES.index(minimum_phase):
            raise RuntimeError(f"closure phase {state.phase!r} has not reached {minimum_phase!r}")
        return state

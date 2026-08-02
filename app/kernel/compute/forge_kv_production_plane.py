"""Production composition root for governed Forge dataset publication."""
from __future__ import annotations

import json
import time
from dataclasses import asdict
from pathlib import Path
from threading import RLock
from typing import Any, Callable, Mapping

from app.kernel.compute.forge_kv_commons_state import CommonsContributionState
from app.kernel.compute.forge_kv_credentials import CredentialBroker
from app.kernel.compute.forge_kv_hf_operational import HuggingFaceDatasetRemote
from app.kernel.compute.forge_kv_progress import ProgressStream
from app.kernel.compute.forge_kv_publication import PublicationApproval, PublicationApprovalGate


class ForgeKVProductionPlane:
    """One governed path from immutable local commit to remote dataset contribution."""
    def __init__(self, *, credential_broker: CredentialBroker, hf_api_factory: Callable[[str], Any],
                 progress: ProgressStream | None = None, state: CommonsContributionState | None = None,
                 receipt_root: Path | str = "~/.local/state/beast/forge-publication"):
        self.credential_broker=credential_broker
        self.hf_api_factory=hf_api_factory
        self.progress=progress or ProgressStream()
        self.state=state or CommonsContributionState()
        self.approvals=PublicationApprovalGate()
        self.receipt_root=Path(receipt_root).expanduser()
        self._lock=RLock()

    def publish_hf(self, *, approval: PublicationApproval, commit: Mapping[str, Any],
                   files: Mapping[str, bytes], chunks: Mapping[str, bytes], private: bool = True,
                   branch: str = "", open_pr: bool = True, now: float | None = None) -> dict[str, Any]:
        clock=time.time() if now is None else now
        dataset_id=str(commit.get("dataset_id") or "")
        commit_digest=str(commit.get("commit_digest") or "")
        if commit.get("authority") != "verify_only" or commit.get("native_context_included") is not False:
            raise PermissionError("unsafe dataset commit")
        self.progress.publish("publication.started",dataset_id=dataset_id,commit_digest=commit_digest)
        approval_receipt=self.approvals.consume(approval,commit_subject_digest=commit_digest,dataset_id=dataset_id,now=clock)
        try:
            with self.credential_broker.lease("huggingface",dataset_id,now=clock) as lease:
                remote=HuggingFaceDatasetRemote(self.hf_api_factory(lease.token),lease.token)
                remote.ensure_dataset(dataset_id,private=private)
                uploaded=deduplicated=0
                for chunk_digest,payload in chunks.items():
                    if remote.has_chunk(dataset_id,chunk_digest):
                        deduplicated+=1; self.progress.publish("chunk.deduplicated",digest=chunk_digest)
                    else:
                        remote.upload_chunk(dataset_id,chunk_digest,payload)
                        uploaded+=1; self.progress.publish("chunk.uploaded",digest=chunk_digest,size=len(payload))
                if branch and open_pr:
                    outcome=remote.create_branch_and_pr(dataset_id,files,branch=branch,title=f"Forge contribution {commit_digest[:20]}",description="Proof-carrying Forge contribution")
                    remote_commit=str(outcome["commit"]); pr=str(outcome["pull_request"])
                    self.progress.publish("pull_request.opened",dataset_id=dataset_id,branch=branch)
                else:
                    remote_commit=remote.commit_files(dataset_id,files,message=f"Publish Forge contribution {commit_digest}",parent_commit=str(commit.get("parent_commit") or ""))
                    pr=""; self.progress.publish("commit.created",dataset_id=dataset_id,remote_commit=remote_commit)
            receipt={"beast_object_type":"forge_kv_publication_receipt","version":"1.0","status":"published",
                     "dataset_id":dataset_id,"local_commit_digest":commit_digest,"remote_commit":remote_commit,
                     "pull_request":pr,"chunks_uploaded":uploaded,"chunks_deduplicated":deduplicated,
                     "approval_digest":approval_receipt["approval_digest"],"native_context_exported":False,
                     "authority":"verify_only"}
            self._persist(receipt)
            self.state.record(receipt)
            self.progress.publish("publication.completed",dataset_id=dataset_id,remote_commit=remote_commit)
            return receipt
        except Exception as exc:
            failed={"status":"failed","dataset_id":dataset_id,"commit_digest":commit_digest,"error_type":type(exc).__name__}
            self.state.record(failed); self.progress.publish("publication.failed",**failed)
            raise

    def _persist(self, receipt: Mapping[str, Any]) -> None:
        self.receipt_root.mkdir(parents=True,exist_ok=True)
        target=self.receipt_root/(str(receipt["local_commit_digest"]).replace(":","_")+".json")
        temporary=target.with_suffix(".tmp")
        temporary.write_text(json.dumps(dict(receipt),sort_keys=True,indent=2)+"\n",encoding="utf-8")
        temporary.replace(target)

    def reachability(self) -> dict[str, Any]:
        return {"beast_object_type":"forge_kv_publication_reachability","version":"1.0",
                "production_plane_constructed":True,"approval_gate":True,"credential_broker":True,
                "progress_stream":True,"contribution_state":True,"default_online_publish":False,
                "authority":"read_only"}

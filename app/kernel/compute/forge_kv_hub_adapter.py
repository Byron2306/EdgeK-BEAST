"""Credential-isolated adapter for Hugging Face-style dataset publication.

No network client is constructed here. A caller supplies a narrow remote API
object after explicit publication approval. This keeps tokens outside the Forge.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol


class DatasetRemote(Protocol):
    def ensure_dataset(self, dataset_id: str, *, private: bool) -> Any: ...
    def has_chunk(self, dataset_id: str, digest: str) -> bool: ...
    def upload_chunk(self, dataset_id: str, digest: str, payload: bytes) -> Any: ...
    def commit_files(self, dataset_id: str, files: Mapping[str, bytes], *, message: str, parent_commit: str = "") -> str: ...


@dataclass(frozen=True)
class HubPublicationReceipt:
    dataset_id: str
    commit_digest: str
    uploaded_chunks: int
    deduplicated_chunks: int
    remote_commit: str
    private: bool
    online_published: bool
    authority: str = "verify_only"


class ForgeKVHubPublisher:
    def __init__(self, remote: DatasetRemote): self.remote=remote

    def publish(self, *, dataset_id: str, commit: Mapping[str,Any], files: Mapping[str,bytes], chunks: Mapping[str,bytes], approval_receipt: Mapping[str,Any], private: bool=True) -> HubPublicationReceipt:
        if approval_receipt.get("consumed") is not True: raise PermissionError("publication requires consumed approval")
        if approval_receipt.get("dataset_id") != dataset_id or approval_receipt.get("subject_digest") != commit.get("commit_digest"): raise PermissionError("approval receipt does not bind publication")
        if commit.get("authority") != "verify_only" or commit.get("native_context_included") is not False: raise PermissionError("unsafe dataset commit")
        self.remote.ensure_dataset(dataset_id,private=private)
        uploaded=deduped=0
        for chunk_digest,payload in chunks.items():
            if self.remote.has_chunk(dataset_id,chunk_digest): deduped+=1
            else: self.remote.upload_chunk(dataset_id,chunk_digest,payload); uploaded+=1
        remote_commit=self.remote.commit_files(dataset_id,files,message=f"BEAST Forge commit {commit['commit_digest']}",parent_commit=str(commit.get("parent_commit") or ""))
        return HubPublicationReceipt(dataset_id,str(commit["commit_digest"]),uploaded,deduped,str(remote_commit),private,True)

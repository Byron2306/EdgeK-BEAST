"""Receiver-side reconstruction worker and revocation poller."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Callable, Mapping
from app.kernel.compute.forge_kv_reconstruction import reconstruct
@dataclass(frozen=True)
class ReceiverReceipt:
    dataset_id:str; commit_digest:str; reconstructed:bool; locally_verified:bool; attestation_verified:bool; promotion_granted:bool=False
class ForgeKVReceiverWorker:
    def run(self,*,dataset_id:str,commit:Mapping[str,Any],manifest:Mapping[str,Any],fetch_chunk:Callable[[str],bytes],verify_attestation:Callable[[str],bool],verify_artifact:Callable[[bytes],bool]):
        if commit.get('authority')!='verify_only' or commit.get('native_context_included') is not False: raise PermissionError('unsafe commit')
        data,_=reconstruct(manifest,fetch_chunk)
        attested=verify_attestation(str(commit.get('attestation_digest') or ''))
        verified=bool(attested and verify_artifact(data))
        return ReceiverReceipt(dataset_id,str(commit['commit_digest']),True,verified,attested,False)
class RevocationPoller:
    def __init__(self,fetch:Callable[[],list[Mapping[str,Any]]]): self.fetch=fetch; self.revoked=set()
    def poll(self):
        items=self.fetch()
        for item in items:
            if item.get('tombstone') is True and item.get('authority')=='deny_reuse': self.revoked.add(str(item.get('commit_digest')))
        return {'revoked_count':len(self.revoked),'revoked_commits':tuple(sorted(self.revoked))}

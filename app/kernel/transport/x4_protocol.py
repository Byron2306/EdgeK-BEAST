from __future__ import annotations
from dataclasses import dataclass, asdict
from pathlib import Path
from hashlib import sha256
import json, time
from typing import Protocol
from .x4_contracts import ObjectManifest, Negotiation, NeedState, X4Refusal, digest_bytes, canonical
from .x4_cas import FileCAS

class DataLane(Protocol):
    name: str
    def fetch(self, chunk_index:int, expected_digest:str)->bytes: ...

@dataclass(frozen=True)
class ChunkAck:
    sequence:int; chunk_index:int; digest:str; accepted:bool; reason:str

class Receiver:
    def __init__(self,cas:FileCAS): self.cas=cas; self._last_sequence=-1
    def negotiate(self,m:ObjectManifest)->Negotiation:
        return Negotiation(m.manifest_digest,tuple(NeedState.HAVE if self.cas.has(c.digest) else NeedState.NEED for c in m.chunks))
    def accept(self,m:ObjectManifest,index:int,data:bytes,sequence:int)->ChunkAck:
        if sequence<=self._last_sequence: raise X4Refusal('sequence replay')
        if index<0 or index>=len(m.chunks): raise X4Refusal('chunk index out of range')
        ref=m.chunks[index]
        if len(data)!=ref.size: raise X4Refusal('chunk size mismatch')
        self.cas.put_verified(data,ref.digest)
        self._last_sequence=sequence
        return ChunkAck(sequence,index,ref.digest,True,'verified_and_admitted')
    def reconstruct(self,m:ObjectManifest)->bytes:
        out=b''.join(self.cas.get(c.digest) for c in m.chunks)
        if len(out)!=m.object_size or digest_bytes(out)!=m.object_digest: raise X4Refusal('object reconstruction mismatch')
        return out

@dataclass
class TransferReceipt:
    phase:str; manifest_digest:str; object_digest:str; lane:str; chunks_total:int; chunks_have:int; chunks_needed:int; chunks_sent:int; bytes_avoided:int; bytes_sent:int; reconstruction_verified:bool; raw_payload_retained:bool; authority:str; receipt_digest:str=''
    def seal(self):
        body=asdict(self); body.pop('receipt_digest',None); self.receipt_digest=digest_bytes(canonical(body)); return self

class Sender:
    def __init__(self, lanes:list[DataLane]): self.lanes=lanes
    def transfer(self,m:ObjectManifest,receiver:Receiver)->TransferReceipt:
        n=receiver.negotiate(m); needed=n.needed_indexes
        last_error=None
        for lane in self.lanes:
            sent=0; bytes_sent=0
            try:
                for seq,index in enumerate(needed,1):
                    ref=m.chunks[index]; data=lane.fetch(index,ref.digest)
                    receiver.accept(m,index,data,seq); sent+=1; bytes_sent+=len(data)
                receiver.reconstruct(m)
                avoided=m.object_size-bytes_sent
                return TransferReceipt('X4',m.manifest_digest,m.object_digest,lane.name,len(m.chunks),len(m.chunks)-len(needed),len(needed),sent,avoided,bytes_sent,True,False,'transport_only').seal()
            except Exception as e: last_error=e
        raise X4Refusal(f'all data lanes failed: {last_error}')

from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from .x4_contracts import ObjectManifest, build_manifest, digest_bytes, X4Refusal
from .x4_cas import FileCAS
from .x4_protocol import Receiver, Sender

@dataclass
class MemoryLane:
    name:str; chunks:tuple[bytes,...]; corrupt_index:int|None=None
    def fetch(self,index:int,expected_digest:str)->bytes:
        data=self.chunks[index]
        if self.corrupt_index==index: data=data+b'!'
        return data

def run_x4(data:bytes,cas_root:Path,chunk_size:int=65536,preseed:int=0):
    m=build_manifest(data,chunk_size); chunks=tuple(data[c.offset:c.offset+c.size] for c in m.chunks)
    cas=FileCAS(cas_root)
    for c,part in zip(m.chunks[:preseed],chunks[:preseed]): cas.put_verified(part,c.digest)
    receiver=Receiver(cas)
    sender=Sender([MemoryLane('af_xdp',chunks),MemoryLane('ordinary_socket',chunks)])
    receipt=sender.transfer(m,receiver)
    return m,receipt,receiver.reconstruct(m)

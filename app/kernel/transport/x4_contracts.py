from __future__ import annotations
from dataclasses import dataclass, asdict
from enum import Enum
from hashlib import sha256
import json
from typing import Iterable

class X4Refusal(ValueError): pass
class NeedState(str, Enum): HAVE='have'; NEED='need'

def digest_bytes(data: bytes) -> str: return 'sha256:' + sha256(data).hexdigest()
def canonical(obj: object) -> bytes: return json.dumps(obj, sort_keys=True, separators=(',', ':')).encode()

@dataclass(frozen=True)
class ChunkRef:
    index: int; offset: int; size: int; digest: str
    def __post_init__(self):
        if self.index < 0 or self.offset < 0 or self.size <= 0: raise X4Refusal('invalid chunk bounds')
        if not self.digest.startswith('sha256:') or len(self.digest) != 71: raise X4Refusal('invalid digest')

@dataclass(frozen=True)
class ObjectManifest:
    version: int; object_digest: str; object_size: int; chunk_size: int; chunks: tuple[ChunkRef, ...]
    def __post_init__(self):
        if self.version != 1 or self.object_size < 0 or not 4096 <= self.chunk_size <= 4*1024*1024: raise X4Refusal('invalid manifest')
        expected=0
        for i,c in enumerate(self.chunks):
            if c.index != i or c.offset != expected: raise X4Refusal('non-contiguous manifest')
            expected += c.size
        if expected != self.object_size: raise X4Refusal('manifest size mismatch')
    def body(self): return {'version':self.version,'object_digest':self.object_digest,'object_size':self.object_size,'chunk_size':self.chunk_size,'chunks':[asdict(c) for c in self.chunks]}
    @property
    def manifest_digest(self): return digest_bytes(canonical(self.body()))

def build_manifest(data: bytes, chunk_size: int=65536) -> ObjectManifest:
    if not 4096 <= chunk_size <= 4*1024*1024: raise X4Refusal('chunk_size out of bounds')
    chunks=[]
    for i,off in enumerate(range(0,len(data),chunk_size)):
        part=data[off:off+chunk_size]; chunks.append(ChunkRef(i,off,len(part),digest_bytes(part)))
    return ObjectManifest(1,digest_bytes(data),len(data),chunk_size,tuple(chunks))

@dataclass(frozen=True)
class Negotiation:
    manifest_digest: str; states: tuple[NeedState, ...]
    @property
    def needed_indexes(self): return tuple(i for i,s in enumerate(self.states) if s is NeedState.NEED)

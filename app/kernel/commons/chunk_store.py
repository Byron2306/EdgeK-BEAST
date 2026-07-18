"""Deterministic chunk store for Commons artifacts."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
import os
import tempfile
import re


@dataclass(frozen=True)
class ChunkManifest:
    artifact_digest: str
    chunk_size: int
    chunks: tuple[str, ...]
    artifact_size: int = 0


class ChunkStore:
    DIGEST_RE=re.compile(r"^sha256:[a-f0-9]{64}$")
    def __init__(self, root: Path, *, chunk_size: int = 65536):
        if not 1 <= chunk_size <= 16 * 1024 * 1024: raise ValueError("chunk_size outside policy")
        self.root, self.chunk_size = Path(root), chunk_size
        self.root.mkdir(parents=True, exist_ok=True)

    def put(self, payload: bytes) -> ChunkManifest:
        if not payload: raise ValueError("cannot chunk an empty artifact")
        chunks=[]
        for offset in range(0, len(payload), self.chunk_size):
            chunk=payload[offset:offset+self.chunk_size]; digest=hashlib.sha256(chunk).hexdigest(); path=self.root/digest
            if path.exists():
                if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest()!=digest:
                    raise ValueError("existing chunk violates immutable content identity")
            else:
                descriptor,temp_name=tempfile.mkstemp(prefix=".chunk-",suffix=".tmp",dir=self.root)
                try:
                    with os.fdopen(descriptor,"wb") as handle:
                        handle.write(chunk); handle.flush(); os.fsync(handle.fileno())
                    os.replace(temp_name,path)
                finally:
                    if os.path.exists(temp_name): os.unlink(temp_name)
            chunks.append("sha256:"+digest)
        return ChunkManifest("sha256:"+hashlib.sha256(payload).hexdigest(), self.chunk_size, tuple(chunks),len(payload))

    def get(self, manifest: ChunkManifest) -> bytes:
        payload=b"".join(self.stream(manifest))
        if manifest.artifact_size and len(payload)!=manifest.artifact_size: raise ValueError("assembled artifact size mismatch")
        if "sha256:"+hashlib.sha256(payload).hexdigest() != manifest.artifact_digest: raise ValueError("assembled artifact digest mismatch")
        return payload

    def stream(self, manifest: ChunkManifest, *, start_chunk: int = 0):
        if not self.DIGEST_RE.fullmatch(manifest.artifact_digest) or not 1<=manifest.chunk_size<=16*1024*1024:
            raise ValueError("invalid chunk manifest")
        if not 0 <= start_chunk <= len(manifest.chunks): raise ValueError("invalid start chunk")
        for digest in manifest.chunks[start_chunk:]:
            if not self.DIGEST_RE.fullmatch(digest): raise ValueError("invalid chunk digest")
            path = self.root / digest[7:]
            if path.is_symlink() or not path.is_file(): raise FileNotFoundError(digest)
            chunk = path.read_bytes()
            if "sha256:" + hashlib.sha256(chunk).hexdigest() != digest: raise ValueError("chunk digest mismatch")
            yield chunk

    def missing(self, manifest: ChunkManifest) -> tuple[str,...]: return tuple(digest for digest in manifest.chunks if not (self.root/digest[7:]).is_file())

    def stats(self) -> dict:
        files=[path for path in self.root.iterdir() if path.is_file() and not path.name.endswith(".tmp")]
        return {"chunks":len(files),"bytes":sum(path.stat().st_size for path in files),"chunk_size":self.chunk_size}

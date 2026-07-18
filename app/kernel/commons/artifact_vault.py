"""Persistent content-addressed Commons artifact bytes."""
from __future__ import annotations

import hashlib
from pathlib import Path
import os
import tempfile
import re


class ArtifactVault:
    DIGEST_RE=re.compile(r"^sha256:[a-f0-9]{64}$")
    def __init__(self, root: Path, *, max_artifact_bytes: int = 10 * 1024**3):
        self.root = Path(root); self.max_artifact_bytes=max_artifact_bytes; self.root.mkdir(parents=True, exist_ok=True)

    def put(self, payload: bytes) -> str:
        if not payload or len(payload)>self.max_artifact_bytes: raise ValueError("artifact size is outside vault policy")
        digest = "sha256:" + hashlib.sha256(payload).hexdigest()
        path = self.root / digest[7:]
        if path.exists():
            if path.is_symlink() or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=digest[7:]:
                raise ValueError("existing vault object is not the requested immutable content")
            return digest
        descriptor,temp_name=tempfile.mkstemp(prefix=".vault-",suffix=".tmp",dir=self.root)
        try:
            with os.fdopen(descriptor,"wb") as handle:
                handle.write(payload); handle.flush(); os.fsync(handle.fileno())
            os.replace(temp_name,path)
            directory=os.open(self.root,os.O_RDONLY)
            try: os.fsync(directory)
            finally: os.close(directory)
        finally:
            if os.path.exists(temp_name): os.unlink(temp_name)
        return digest

    def get(self, digest: str) -> bytes:
        if not self.DIGEST_RE.fullmatch(digest): raise ValueError("invalid artifact digest")
        path=self.root/digest[7:]
        if path.is_symlink() or not path.is_file(): raise ValueError("vault object is not a regular immutable file")
        if path.stat().st_size>self.max_artifact_bytes: raise ValueError("vault object exceeds size policy")
        payload = path.read_bytes()
        if "sha256:" + hashlib.sha256(payload).hexdigest() != digest: raise ValueError("artifact digest mismatch")
        return payload

    def has(self, digest: str) -> bool:
        if not self.DIGEST_RE.fullmatch(str(digest)): return False
        path=self.root/digest[7:]
        return path.is_file() and not path.is_symlink()
    def stats(self) -> dict:
        files=[path for path in self.root.iterdir() if path.is_file() and not path.name.endswith(".tmp")]
        return {"objects":len(files),"bytes":sum(path.stat().st_size for path in files),"max_artifact_bytes":self.max_artifact_bytes}

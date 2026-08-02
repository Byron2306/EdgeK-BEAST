from __future__ import annotations
from pathlib import Path
import os, tempfile
from .x4_contracts import digest_bytes, X4Refusal

class FileCAS:
    def __init__(self, root: Path): self.root=Path(root); self.root.mkdir(parents=True, exist_ok=True)
    def path(self,digest:str)->Path:
        if not digest.startswith('sha256:') or len(digest)!=71: raise X4Refusal('invalid digest')
        h=digest.split(':',1)[1]; return self.root/h[:2]/h[2:]
    def has(self,digest:str)->bool: return self.path(digest).is_file()
    def put_verified(self,data:bytes,expected:str)->Path:
        if digest_bytes(data)!=expected: raise X4Refusal('chunk digest mismatch')
        target=self.path(expected); target.parent.mkdir(parents=True,exist_ok=True)
        if target.exists():
            if digest_bytes(target.read_bytes())!=expected: raise X4Refusal('CAS corruption')
            return target
        fd,tmp=tempfile.mkstemp(prefix='.x4-',dir=target.parent)
        try:
            with os.fdopen(fd,'wb') as f: f.write(data); f.flush(); os.fsync(f.fileno())
            os.replace(tmp,target)
        finally:
            if os.path.exists(tmp): os.unlink(tmp)
        return target
    def get(self,digest:str)->bytes:
        data=self.path(digest).read_bytes()
        if digest_bytes(data)!=digest: raise X4Refusal('CAS corruption')
        return data

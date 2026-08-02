"""Resumable, digest-verified multipart transfer for Forge proof objects."""
from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from threading import RLock
from typing import Any, Callable, Mapping

from app.kernel.compute.forge_kv_bucket import sha256_bytes


def _atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(dict(payload), sort_keys=True, indent=2).encode() + b"\n"
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=f".{path.name}.", delete=False) as handle:
        handle.write(encoded); handle.flush(); os.fsync(handle.fileno()); temporary=Path(handle.name)
    os.replace(temporary, path)


@dataclass(frozen=True)
class MultipartReceipt:
    upload_id: str
    object_digest: str
    part_size: int
    part_count: int
    uploaded_parts: tuple[int, ...]
    skipped_parts: tuple[int, ...]
    completed: bool
    receipt_digest: str = ""

    def sealed(self) -> "MultipartReceipt":
        value=asdict(self); value.pop("receipt_digest",None)
        return replace(self, receipt_digest=sha256_bytes(json.dumps(value,sort_keys=True,separators=(",",":")).encode()))


class ResumableMultipartUploader:
    def __init__(self, ledger_path: Path | str, *, part_size: int = 4 * 1024 * 1024):
        if part_size < 64 * 1024: raise ValueError("part_size is too small")
        self.ledger_path, self.part_size, self._lock = Path(ledger_path), int(part_size), RLock()

    def _load(self) -> dict[str, Any]:
        if not self.ledger_path.exists(): return {"version":"1.0","uploads":{}}
        return json.loads(self.ledger_path.read_text())

    def upload(self, payload: bytes, *, upload_id: str, put_part: Callable[[str,int,bytes,str], Any], complete: Callable[[str,str,tuple[str,...]], Any]) -> MultipartReceipt:
        digest=sha256_bytes(payload); parts=[payload[i:i+self.part_size] for i in range(0,len(payload),self.part_size)] or [b""]
        with self._lock:
            ledger=self._load(); record=ledger["uploads"].setdefault(upload_id,{"object_digest":digest,"parts":{},"completed":False})
            if record["object_digest"] != digest: raise ValueError("upload_id is already bound to another object")
            uploaded=[]; skipped=[]; digests=[]
            for index, part in enumerate(parts):
                part_digest=sha256_bytes(part); digests.append(part_digest)
                if record["parts"].get(str(index)) == part_digest:
                    skipped.append(index); continue
                put_part(upload_id,index,part,part_digest)
                record["parts"][str(index)] = part_digest; uploaded.append(index); _atomic_json(self.ledger_path,ledger)
            complete(upload_id,digest,tuple(digests)); record["completed"]=True; _atomic_json(self.ledger_path,ledger)
        return MultipartReceipt(upload_id,digest,self.part_size,len(parts),tuple(uploaded),tuple(skipped),True).sealed()

"""Content-addressed bucket staging for export-safe Forge dataset objects."""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from threading import RLock
from typing import Any, Iterable, Mapping


def sha256_bytes(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=f".{path.name}.", delete=False) as handle:
        handle.write(payload); handle.flush(); os.fsync(handle.fileno()); temporary = Path(handle.name)
    os.replace(temporary, path)


@dataclass(frozen=True)
class BucketObjectReceipt:
    bucket: str
    key: str
    digest: str
    size: int
    created: bool

    def to_dict(self) -> dict[str, Any]:
        return {"beast_object_type":"forge_bucket_object_receipt","version":"1.0",**asdict(self)}


class LocalContentAddressedBucket:
    """Filesystem bucket with object identity bound to SHA-256 bytes.

    This is the production-safe local backend and test oracle. Remote adapters may
    implement the same put/head/get contract without receiving ambient credentials.
    """
    def __init__(self, root: Path | str, *, bucket: str = "forge-kv"):
        self.root, self.bucket = Path(root), str(bucket)
        self._lock = RLock()

    def _path(self, digest: str) -> Path:
        if not digest.startswith("sha256:") or len(digest) != 71:
            raise ValueError("invalid object digest")
        return self.root / self.bucket / "objects" / digest[7:9] / digest[9:]

    def head(self, digest: str) -> dict[str, Any] | None:
        path = self._path(digest)
        if not path.is_file(): return None
        return {"digest":digest,"size":path.stat().st_size,"key":str(path.relative_to(self.root / self.bucket))}

    def put(self, payload: bytes, *, expected_digest: str = "") -> BucketObjectReceipt:
        digest = sha256_bytes(payload)
        if expected_digest and expected_digest != digest:
            raise ValueError("bucket payload digest mismatch")
        path = self._path(digest)
        with self._lock:
            existing = path.is_file()
            if existing:
                current = path.read_bytes()
                if sha256_bytes(current) != digest:
                    raise RuntimeError("content-addressed bucket corruption")
            else:
                _atomic_write(path, payload)
        return BucketObjectReceipt(self.bucket, str(path.relative_to(self.root / self.bucket)), digest, len(payload), not existing)

    def get(self, digest: str) -> bytes:
        payload = self._path(digest).read_bytes()
        if sha256_bytes(payload) != digest:
            raise RuntimeError("bucket object failed digest verification")
        return payload

    def write_commit(self, commit: Mapping[str, Any]) -> BucketObjectReceipt:
        encoded = json.dumps(dict(commit), sort_keys=True, separators=(",",":"), ensure_ascii=True).encode()
        return self.put(encoded)

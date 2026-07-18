"""Local content-addressed Commons manifests; bytes are fetched only by policy."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
import fcntl
from typing import Any, Mapping
from pathlib import Path
from threading import RLock


@dataclass(frozen=True)
class CommonsManifest:
    artifact_id: str
    kind: str
    digest: str
    metadata: dict[str, Any]
    signature: str = ""
    authority: str = ""


class CommonsArtifactRegistry:
    def __init__(self, path: str | Path | None = None, *, require_signature: bool = False, verifier=None, require_verification: bool = False, strict_load: bool = False):
        self.path=Path(path) if path else None; self.require_signature=require_signature; self.verifier=verifier; self.require_verification=require_verification; self.strict_load=strict_load; self._items: dict[str, CommonsManifest] = {}; self._lock=RLock()
        if self.path and self.path.exists():
            for line_number,line in enumerate(self.path.read_text(encoding="utf-8").splitlines(),start=1):
                try:
                    item=CommonsManifest(**json.loads(line))
                    self._validate_loaded(item)
                    existing=self._items.get(item.artifact_id)
                    if existing and existing!=item: raise ValueError("conflicting duplicate artifact identity")
                    self._items[item.artifact_id]=item
                except Exception as exc:
                    if self.strict_load: raise ValueError(f"corrupt Commons registry record at line {line_number}") from exc

    @staticmethod
    def _identity(kind: str, metadata: Mapping[str, Any] | dict[str, Any]):
        body={"kind":kind,"metadata":dict(metadata)}
        digest="sha256:"+hashlib.sha256(json.dumps(body,sort_keys=True,separators=(",",":")).encode()).hexdigest()
        return body,digest,f"commons:{kind}:{digest[7:19]}"

    def _validate_loaded(self, item: CommonsManifest) -> None:
        body,digest,artifact_id=self._identity(item.kind,item.metadata)
        if item.digest!=digest or item.artifact_id!=artifact_id:
            raise ValueError("Commons manifest content identity mismatch")
        if self.require_signature and (not item.signature or not item.authority):
            raise PermissionError("persisted Commons manifest is unsigned")
        if self.require_verification:
            if self.verifier is None or not self.verifier(body,item.signature,item.authority):
                raise PermissionError("persisted Commons signature verification failed")

    def publish(self, kind: str, metadata: dict[str, Any], *, signature: str = "", authority: str = "") -> CommonsManifest:
        if not kind or not isinstance(metadata,dict): raise ValueError("artifact kind and metadata are required")
        if self.require_signature and (not signature or not authority): raise PermissionError("signed authority-bound manifest required")
        body,digest,artifact_id = self._identity(kind,metadata)
        if self.require_verification:
            if self.verifier is None:
                raise PermissionError("Commons signature verifier is not configured")
            if not self.verifier(body, signature, authority):
                raise PermissionError("Commons manifest signature verification failed")
        item = CommonsManifest(artifact_id, kind, digest, dict(metadata),signature,authority)
        with self._lock:
            existing=self._items.get(item.artifact_id)
            if existing and existing.digest!=item.digest: raise RuntimeError("artifact identity collision")
            self._items[item.artifact_id] = item
            if self.path and existing is None:
                self.path.parent.mkdir(parents=True,exist_ok=True)
                with self.path.open("a+",encoding="utf-8") as handle:
                    fcntl.flock(handle.fileno(),fcntl.LOCK_EX)
                    handle.seek(0)
                    for line in handle.read().splitlines():
                        persisted=CommonsManifest(**json.loads(line)); self._validate_loaded(persisted)
                        if persisted.artifact_id==item.artifact_id and persisted!=item:
                            raise RuntimeError("artifact identity collision in durable registry")
                        if persisted==item:
                            return persisted
                    handle.seek(0,os.SEEK_END)
                    handle.write(json.dumps(item.__dict__,sort_keys=True,separators=(",",":"))+"\n")
                    handle.flush(); os.fsync(handle.fileno())
                    fcntl.flock(handle.fileno(),fcntl.LOCK_UN)
        return item

    def get(self, artifact_id: str) -> CommonsManifest:
        with self._lock: return self._items[artifact_id]

    def list(self, *, kind: str = "", limit: int = 100) -> tuple[CommonsManifest, ...]:
        with self._lock: return tuple(item for item in self._items.values() if not kind or item.kind==kind)[:max(1,min(limit,1000))]

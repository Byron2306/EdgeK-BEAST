"""Mandatory workspace identity envelope for every governed request."""
from __future__ import annotations
from dataclasses import dataclass, asdict
import hashlib
import json
import subprocess
import uuid
from pathlib import Path

@dataclass(frozen=True)
class WorkspaceIdentity:
    repository: str
    remote: str
    branch: str
    head: str
    canonical_root: str
    worktree_id: str
    workspace_uuid: str

    def validate(self) -> None:
        if not self.repository or not self.canonical_root or not self.workspace_uuid:
            raise ValueError("workspace identity is incomplete")
        try:
            uuid.UUID(self.workspace_uuid)
        except ValueError as exc:
            raise ValueError("workspace_uuid must be a UUID") from exc
        if self.head and (len(self.head) < 7 or any(ch not in "0123456789abcdef" for ch in self.head.lower())):
            raise ValueError("HEAD is not a git object id")

    def digest(self) -> str:
        self.validate()
        return "sha256:"+hashlib.sha256(json.dumps(asdict(self),sort_keys=True,separators=(",",":")).encode()).hexdigest()

    def matches(self, other: "WorkspaceIdentity") -> bool:
        """Cache reuse requires an exact physical and source identity match."""
        return self.digest() == other.digest()

def discover(root: str | Path, *, workspace_uuid: str) -> WorkspaceIdentity:
    path=Path(root).resolve()
    def git(*args):
        try: return subprocess.check_output(["git", "-C", str(path), *args], text=True, stderr=subprocess.DEVNULL,timeout=2.0).strip()
        except Exception: return ""
    identity = WorkspaceIdentity(path.name, git("config","--get","remote.origin.url"), git("branch","--show-current"), git("rev-parse","HEAD"), str(path), git("rev-parse","--git-common-dir") or str(path/".git"), workspace_uuid)
    identity.validate()
    return identity

def stable_workspace_uuid(root: str | Path) -> str:
    """Derive a stable local UUID without exposing the absolute path on wire."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, str(Path(root).expanduser().resolve())))

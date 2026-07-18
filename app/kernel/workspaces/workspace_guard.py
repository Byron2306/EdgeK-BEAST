"""Staged exact-workspace identity enforcement for governed HTTP requests."""
from __future__ import annotations
from dataclasses import dataclass
from .workspace_identity import WorkspaceIdentity

@dataclass(frozen=True)
class WorkspaceGuardDecision:
    allowed: bool
    status: str
    expected_digest: str
    presented_digest: str

class WorkspaceIdentityGuard:
    def __init__(self, identity: WorkspaceIdentity, *, mode: str = "audit"):
        if mode not in {"audit","enforce"}: raise ValueError("guard mode must be audit or enforce")
        self.identity=identity; self.mode=mode
    def evaluate(self, presented_digest: str) -> WorkspaceGuardDecision:
        expected=self.identity.digest(); matches=presented_digest==expected
        allowed=matches or self.mode=="audit"
        return WorkspaceGuardDecision(allowed,"matched" if matches else ("audit_mismatch" if self.mode=="audit" else "denied"),expected,presented_digest)

"""Typed immutable evidence objects produced from promoted AgentRuns."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.kernel.evidence.evidence_digest import sha256_digest


@dataclass(frozen=True)
class EvidenceArtifact:
    artifact_id: str
    kind: str
    digest: str
    media_type: str = "application/json"
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "artifact_id": self.artifact_id,
            "kind": self.kind,
            "digest": self.digest,
            "media_type": self.media_type,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class EvidenceObject:
    evidence_id: str
    version: str
    kind: str
    created_at: float
    run_id: str
    task: dict[str, Any]
    environment: dict[str, Any]
    transformation: dict[str, Any]
    verification: dict[str, Any]
    promotion: dict[str, Any]
    provenance: dict[str, Any]
    authority: dict[str, Any]
    reuse_constraints: dict[str, Any]
    artifacts: tuple[EvidenceArtifact, ...]
    evidence_digest: str

    def core_dict(self) -> dict[str, Any]:
        return {
            "beast_object_type": "beast_evidence_crystal",
            "version": self.version,
            "evidence_id": self.evidence_id,
            "kind": self.kind,
            "created_at": self.created_at,
            "run_id": self.run_id,
            "task": self.task,
            "environment": self.environment,
            "transformation": self.transformation,
            "verification": self.verification,
            "promotion": self.promotion,
            "provenance": self.provenance,
            "authority": self.authority,
            "reuse_constraints": self.reuse_constraints,
            "artifacts": [artifact.as_dict() for artifact in self.artifacts],
        }

    def as_dict(self) -> dict[str, Any]:
        return {**self.core_dict(), "evidence_digest": self.evidence_digest}

    def verify_digest(self) -> bool:
        return self.evidence_digest == sha256_digest(self.core_dict())

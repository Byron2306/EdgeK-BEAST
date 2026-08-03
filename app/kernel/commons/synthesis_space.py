from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping

from app.kernel.compute.residual_contracts import canonical_json, sha256_digest, validate_digest


class SynthesisCapabilityKind(str, Enum):
    SEMANTIC = "semantic"
    VISUAL = "visual"


@dataclass(frozen=True, slots=True)
class SynthesisSpacePackage:
    space_id: str
    capability_kind: SynthesisCapabilityKind
    artifact_digests: tuple[str, ...]
    schemas: Mapping[str, Any]
    verifier_digest: str
    negative_cases: tuple[Mapping[str, Any], ...]
    replay_corpus: tuple[Mapping[str, Any], ...]
    evidence_digests: tuple[str, ...]
    reproducibility: Mapping[str, Any]
    authority: str = "remote_hypothesis"
    maximum_authority: str = "verify_only"
    local_reproduction_required: bool = True
    promoted_locally: bool = False

    def __post_init__(self) -> None:
        if not self.space_id.strip():
            raise ValueError("synthesis Space package requires space_id")
        if not isinstance(self.capability_kind, SynthesisCapabilityKind):
            object.__setattr__(self, "capability_kind", SynthesisCapabilityKind(self.capability_kind))
        for digest in self.artifact_digests:
            validate_digest(digest, field_name="artifact_digest")
        for digest in self.evidence_digests:
            validate_digest(digest, field_name="evidence_digest")
        validate_digest(self.verifier_digest, field_name="verifier_digest")
        if not self.artifact_digests:
            raise ValueError("synthesis Space package requires artifacts")
        for name, value in (
            ("schemas", self.schemas),
            ("negative_cases", self.negative_cases),
            ("replay_corpus", self.replay_corpus),
            ("reproducibility", self.reproducibility),
        ):
            if not value:
                raise ValueError(f"synthesis Space package requires {name}")
            canonical_json(value)
        if self.authority != "remote_hypothesis" or self.maximum_authority != "verify_only":
            raise PermissionError("synthesis Space packages enter Commons as verify-only hypotheses")
        if not self.local_reproduction_required:
            raise PermissionError("synthesis Space package must require local reproduction")
        if self.promoted_locally:
            raise PermissionError("remote synthesis Space package cannot self-promote")

    @property
    def package_digest(self) -> str:
        return sha256_digest(self)

    def to_manifest(self) -> dict[str, Any]:
        return {
            "beast_object_type": "commons_synthesis_space_package",
            "version": "1.0",
            "space_id": self.space_id,
            "capability_kind": self.capability_kind.value,
            "artifact_digests": list(self.artifact_digests),
            "schemas": dict(self.schemas),
            "verifier_digest": self.verifier_digest,
            "negative_cases": [dict(item) for item in self.negative_cases],
            "replay_corpus": [dict(item) for item in self.replay_corpus],
            "evidence_digests": list(self.evidence_digests),
            "reproducibility": dict(self.reproducibility),
            "authority": self.authority,
            "maximum_authority": self.maximum_authority,
            "local_reproduction_required": self.local_reproduction_required,
            "promoted_locally": self.promoted_locally,
            "package_digest": self.package_digest,
        }


def build_synthesis_space_package(
    *,
    space_id: str,
    capability_kind: SynthesisCapabilityKind,
    artifact_digests: tuple[str, ...],
    schemas: Mapping[str, Any],
    verifier: Mapping[str, Any],
    negative_cases: tuple[Mapping[str, Any], ...],
    replay_corpus: tuple[Mapping[str, Any], ...],
    evidence_digests: tuple[str, ...],
    reproducibility: Mapping[str, Any],
) -> SynthesisSpacePackage:
    verifier_digest = sha256_digest(verifier)
    return SynthesisSpacePackage(
        space_id=space_id,
        capability_kind=capability_kind,
        artifact_digests=artifact_digests,
        schemas=schemas,
        verifier_digest=verifier_digest,
        negative_cases=negative_cases,
        replay_corpus=replay_corpus,
        evidence_digests=evidence_digests,
        reproducibility={
            **dict(reproducibility),
            "verifier": dict(verifier),
            "local_reproduction_required": True,
        },
    )


def validate_synthesis_space_manifest(manifest: Mapping[str, Any]) -> SynthesisSpacePackage:
    supplied = str(manifest.get("package_digest") or "")
    payload = SynthesisSpacePackage(
        space_id=str(manifest.get("space_id") or ""),
        capability_kind=SynthesisCapabilityKind(str(manifest.get("capability_kind") or "")),
        artifact_digests=tuple(str(item) for item in (manifest.get("artifact_digests") or ())),
        schemas=dict(manifest.get("schemas") or {}),
        verifier_digest=str(manifest.get("verifier_digest") or ""),
        negative_cases=tuple(dict(item) for item in (manifest.get("negative_cases") or ())),
        replay_corpus=tuple(dict(item) for item in (manifest.get("replay_corpus") or ())),
        evidence_digests=tuple(str(item) for item in (manifest.get("evidence_digests") or ())),
        reproducibility=dict(manifest.get("reproducibility") or {}),
        authority=str(manifest.get("authority") or ""),
        maximum_authority=str(manifest.get("maximum_authority") or ""),
        local_reproduction_required=bool(manifest.get("local_reproduction_required")),
        promoted_locally=bool(manifest.get("promoted_locally")),
    )
    if supplied != payload.package_digest:
        raise ValueError("synthesis Space package digest mismatch")
    return payload

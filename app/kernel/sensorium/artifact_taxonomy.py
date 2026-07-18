"""Authority taxonomy for BEAST artifacts commonly called crystals.

Similarity, immutability, attestation, verification, and authority are distinct
properties.  This module gives every reusable artifact an explicit class and a
maximum authority so a retrieval hit cannot silently become permission to act.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum, IntEnum
from typing import Any, Dict, Mapping

from app.kernel.sensorium.contracts_hash import content_hash


class CrystalArtifactClass(str, Enum):
    EXACT_ANSWER_ENTRY = "exact_answer_entry"
    SEMANTIC_CACHE_ENTRY = "semantic_cache_entry"
    KV_PREFILL_BLOCK = "kv_prefill_block"
    SEMANTIC_COMPUTE_PAGE = "semantic_compute_page"
    MISSION_LATTICE_CELL = "mission_lattice_cell"
    GENERATIVE_CRYSTAL_TEMPLATE = "generative_crystal_template"
    CRYSTALLIZED_CAPABILITY = "crystallized_capability"
    RUNTIME_EPISODE = "runtime_episode"
    COMPUTE_CRYSTAL_IR = "compute_crystal_ir"
    CRYSTAL_CAPSULE = "crystal_capsule"


class ArtifactAuthority(IntEnum):
    """Ordered authority used only for ceiling checks, never policy grants."""

    CONTEXT_ONLY = 0
    PROPOSAL_ONLY = 1
    VERIFY_ONLY = 2
    BOUNDED_EXECUTE = 3

    @property
    def label(self) -> str:
        return {
            self.CONTEXT_ONLY: "context_only",
            self.PROPOSAL_ONLY: "proposal_only",
            self.VERIFY_ONLY: "verify_only",
            self.BOUNDED_EXECUTE: "bounded_execute",
        }[self]

    @classmethod
    def from_label(cls, value: str) -> "ArtifactAuthority":
        normalized = str(value or "").strip().lower()
        for member in cls:
            if member.label == normalized:
                return member
        raise ValueError(f"unknown artifact authority: {value}")


MAXIMUM_AUTHORITY = {
    CrystalArtifactClass.EXACT_ANSWER_ENTRY: ArtifactAuthority.VERIFY_ONLY,
    CrystalArtifactClass.SEMANTIC_CACHE_ENTRY: ArtifactAuthority.CONTEXT_ONLY,
    CrystalArtifactClass.KV_PREFILL_BLOCK: ArtifactAuthority.CONTEXT_ONLY,
    CrystalArtifactClass.SEMANTIC_COMPUTE_PAGE: ArtifactAuthority.CONTEXT_ONLY,
    CrystalArtifactClass.MISSION_LATTICE_CELL: ArtifactAuthority.CONTEXT_ONLY,
    CrystalArtifactClass.GENERATIVE_CRYSTAL_TEMPLATE: ArtifactAuthority.PROPOSAL_ONLY,
    CrystalArtifactClass.CRYSTALLIZED_CAPABILITY: ArtifactAuthority.BOUNDED_EXECUTE,
    CrystalArtifactClass.RUNTIME_EPISODE: ArtifactAuthority.CONTEXT_ONLY,
    CrystalArtifactClass.COMPUTE_CRYSTAL_IR: ArtifactAuthority.BOUNDED_EXECUTE,
    CrystalArtifactClass.CRYSTAL_CAPSULE: ArtifactAuthority.CONTEXT_ONLY,
}


def authority_allows(
    artifact_class: CrystalArtifactClass | str,
    requested: ArtifactAuthority | str,
) -> bool:
    """Return whether the artifact class ceiling permits the requested use.

    A true result is not an execution grant.  Policy, verification, attestation,
    capability lease, freshness, and approval still have to authorize the use.
    """

    selected_class = (
        artifact_class
        if isinstance(artifact_class, CrystalArtifactClass)
        else CrystalArtifactClass(str(artifact_class))
    )
    selected_authority = (
        requested
        if isinstance(requested, ArtifactAuthority)
        else ArtifactAuthority.from_label(str(requested))
    )
    return selected_authority <= MAXIMUM_AUTHORITY[selected_class]


@dataclass(frozen=True)
class CrystalArtifactDescriptor:
    artifact_class: CrystalArtifactClass
    authority: ArtifactAuthority
    verification_state: str
    applicability_hash: str
    policy_generation: str
    expires_at: str

    def validate(self) -> None:
        if not authority_allows(self.artifact_class, self.authority):
            ceiling = MAXIMUM_AUTHORITY[self.artifact_class].label
            raise ValueError(
                f"{self.artifact_class.value} cannot carry {self.authority.label}; "
                f"maximum is {ceiling}"
            )
        if self.verification_state not in {
            "unverified",
            "candidate",
            "heldout_validated",
            "promoted",
            "degraded",
            "quarantined",
            "superseded",
            "revoked",
            "expired",
        }:
            raise ValueError("invalid verification_state")
        if not self.applicability_hash.startswith("sha256:") or len(self.applicability_hash) != 71:
            raise ValueError("applicability_hash must be sha256:<64 hex chars>")
        try:
            int(self.applicability_hash[7:], 16)
        except ValueError as exc:
            raise ValueError("applicability_hash must be sha256:<64 hex chars>") from exc
        if not self.policy_generation:
            raise ValueError("policy_generation is required")
        if not self.expires_at:
            raise ValueError("expires_at is required")

    def to_dict(self) -> Dict[str, Any]:
        self.validate()
        payload = asdict(self)
        payload["artifact_class"] = self.artifact_class.value
        payload["authority"] = self.authority.label
        payload["beast_object_type"] = "crystal_artifact_descriptor"
        payload["version"] = "1.0"
        return payload


OBJECT_TYPE_CLASSES = {
    "answer_credit": CrystalArtifactClass.EXACT_ANSWER_ENTRY,
    "cached_answer": CrystalArtifactClass.EXACT_ANSWER_ENTRY,
    "semantic_cache_entry": CrystalArtifactClass.SEMANTIC_CACHE_ENTRY,
    "semantic_credit": CrystalArtifactClass.SEMANTIC_CACHE_ENTRY,
    "kv_cache_block": CrystalArtifactClass.KV_PREFILL_BLOCK,
    "semantic_compute_page": CrystalArtifactClass.SEMANTIC_COMPUTE_PAGE,
    "mission_crystal_lattice_cell": CrystalArtifactClass.MISSION_LATTICE_CELL,
    "mission_lattice_cell": CrystalArtifactClass.MISSION_LATTICE_CELL,
    "generative_crystal_template": CrystalArtifactClass.GENERATIVE_CRYSTAL_TEMPLATE,
    "deterministic_displacement_proof": CrystalArtifactClass.CRYSTALLIZED_CAPABILITY,
    "crystallized_capability": CrystalArtifactClass.CRYSTALLIZED_CAPABILITY,
    "runtime_episode": CrystalArtifactClass.RUNTIME_EPISODE,
    "compute_crystal_ir": CrystalArtifactClass.COMPUTE_CRYSTAL_IR,
    "crystal_capsule": CrystalArtifactClass.CRYSTAL_CAPSULE,
}


def describe_existing_artifact(
    payload: Mapping[str, Any],
    *,
    policy_generation: str,
    expires_at: str,
) -> CrystalArtifactDescriptor:
    """Describe a legacy artifact without mutating its persisted representation."""

    object_type = str(payload.get("beast_object_type") or payload.get("artifact_class") or "")
    try:
        artifact_class = OBJECT_TYPE_CLASSES[object_type]
    except KeyError as exc:
        raise ValueError(f"unsupported crystal-like object type: {object_type or '<missing>'}") from exc

    raw_state = str(payload.get("verification_state") or payload.get("state") or "unverified")
    state_aliases = {
        "active": "promoted",
        "demoted": "degraded",
        "invalidated": "revoked",
        "shadow_validation": "candidate",
    }
    verification_state = state_aliases.get(raw_state, raw_state)
    if verification_state not in {
        "unverified",
        "candidate",
        "heldout_validated",
        "promoted",
        "degraded",
        "quarantined",
        "superseded",
        "revoked",
        "expired",
    }:
        verification_state = "unverified"

    boundary = payload.get("applicability")
    if not isinstance(boundary, dict):
        boundary = {
            "boundary_hash": payload.get("boundary_hash") or "",
            "task_family": payload.get("task_family") or payload.get("task_class") or "",
            "policy_version": payload.get("policy_version") or policy_generation,
            "repo_fingerprint": payload.get("repo_fingerprint") or "",
        }
    authority = MAXIMUM_AUTHORITY[artifact_class]
    if artifact_class in {
        CrystalArtifactClass.CRYSTALLIZED_CAPABILITY,
        CrystalArtifactClass.COMPUTE_CRYSTAL_IR,
    } and verification_state != "promoted":
        authority = ArtifactAuthority.PROPOSAL_ONLY
    descriptor = CrystalArtifactDescriptor(
        artifact_class=artifact_class,
        authority=authority,
        verification_state=verification_state,
        applicability_hash=content_hash(boundary),
        policy_generation=policy_generation,
        expires_at=expires_at,
    )
    descriptor.validate()
    return descriptor

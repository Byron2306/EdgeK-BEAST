"""Canonical proof graph for cross-modal BEAST composition.

The proof graph is the shared substrate for text and visual outputs.  Text is
not used to generate visuals, and visuals are not used to interpret text: both
views must reference claims from this graph and verify against its digest.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Mapping

from .residual_contracts import canonical_json, sha256_digest, validate_digest


class ProofClaimStatus(str, Enum):
    SUPPORTED = "supported"
    RESIDUAL_SUPPORTED = "residual_supported"
    UNSUPPORTED = "unsupported"
    REFUTED = "refuted"
    STALE = "stale"


@dataclass(frozen=True, slots=True)
class ProofGraphClaim:
    claim_id: str
    claim_type: str
    subject: str
    predicate: str
    object: str
    status: ProofClaimStatus
    confidence_class: str
    fact_refs: tuple[str, ...]
    rule_ref: str = ""
    policy_ref: str = ""
    snapshot_ref: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.claim_id.strip() or not self.claim_type.strip() or not self.subject.strip() or not self.predicate.strip():
            raise ValueError("proof claims require claim_id, claim_type, subject, and predicate")
        if not isinstance(self.status, ProofClaimStatus):
            object.__setattr__(self, "status", ProofClaimStatus(self.status))
        if not self.fact_refs:
            raise ValueError("proof claims require at least one fact ref")
        canonical_json(self.metadata)

    @property
    def claim_digest(self) -> str:
        return sha256_digest(self)

    def to_dict(self) -> dict[str, Any]:
        return {**asdict(self), "status": self.status.value, "claim_digest": self.claim_digest}


@dataclass(frozen=True, slots=True)
class CanonicalProofGraph:
    graph_id: str
    claims: tuple[ProofGraphClaim, ...]
    world_snapshot_digest: str
    policy_digest: str
    capability_fact_digests: tuple[str, ...]
    causal_rule_digests: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.graph_id.strip():
            raise ValueError("proof graph requires graph_id")
        if not self.claims:
            raise ValueError("proof graph requires at least one claim")
        claim_ids = [claim.claim_id for claim in self.claims]
        if len(claim_ids) != len(set(claim_ids)):
            raise ValueError("proof graph claim ids must be unique")
        validate_digest(self.world_snapshot_digest, field_name="world_snapshot_digest")
        validate_digest(self.policy_digest, field_name="policy_digest")
        for digest in (*self.capability_fact_digests, *self.causal_rule_digests):
            validate_digest(digest, field_name="proof_graph_component_digest")

    @property
    def claim_ids(self) -> tuple[str, ...]:
        return tuple(claim.claim_id for claim in self.claims)

    @property
    def proof_graph_digest(self) -> str:
        return sha256_digest(self)

    def claim(self, claim_id: str) -> ProofGraphClaim:
        for claim in self.claims:
            if claim.claim_id == claim_id:
                return claim
        raise KeyError(claim_id)

    def to_dict(self) -> dict[str, Any]:
        return {**asdict(self), "claims": tuple(claim.to_dict() for claim in self.claims), "proof_graph_digest": self.proof_graph_digest}


@dataclass(frozen=True, slots=True)
class TextProofView:
    view_id: str
    text_output_digest: str
    claim_refs: tuple[str, ...]
    renderer_id: str = "beast.text-realizer.proof-view.v1"

    def __post_init__(self) -> None:
        if not self.view_id.strip() or not self.claim_refs:
            raise ValueError("text proof view requires view_id and claim_refs")
        validate_digest(self.text_output_digest, field_name="text_output_digest")

    @property
    def view_digest(self) -> str:
        return sha256_digest(self)

    def to_dict(self) -> dict[str, Any]:
        return {**asdict(self), "view_digest": self.view_digest}


@dataclass(frozen=True, slots=True)
class VisualProofPrimitive:
    primitive_id: str
    primitive: str
    claim_ref: str
    evidence_state: ProofClaimStatus
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.primitive_id.strip() or not self.primitive.strip() or not self.claim_ref.strip():
            raise ValueError("visual proof primitive requires primitive_id, primitive, and claim_ref")
        if not isinstance(self.evidence_state, ProofClaimStatus):
            object.__setattr__(self, "evidence_state", ProofClaimStatus(self.evidence_state))
        canonical_json(self.metadata)

    @property
    def primitive_digest(self) -> str:
        return sha256_digest(self)

    def to_dict(self) -> dict[str, Any]:
        return {**asdict(self), "evidence_state": self.evidence_state.value, "primitive_digest": self.primitive_digest}


@dataclass(frozen=True, slots=True)
class VisualProofView:
    view_id: str
    scene_capsule_digest: str
    rendered_visual_digest: str
    asset_manifest_digest: str
    layout_engine_digest: str
    primitives: tuple[VisualProofPrimitive, ...]
    compiler_id: str = "beast.scene-compiler.proof-view.v1"

    def __post_init__(self) -> None:
        if not self.view_id.strip() or not self.primitives:
            raise ValueError("visual proof view requires view_id and primitives")
        for name in ("scene_capsule_digest", "rendered_visual_digest", "asset_manifest_digest", "layout_engine_digest"):
            validate_digest(getattr(self, name), field_name=name)

    @property
    def claim_refs(self) -> tuple[str, ...]:
        return tuple(primitive.claim_ref for primitive in self.primitives)

    @property
    def view_digest(self) -> str:
        return sha256_digest(self)

    def to_dict(self) -> dict[str, Any]:
        return {**asdict(self), "primitives": tuple(item.to_dict() for item in self.primitives), "view_digest": self.view_digest}


def verify_cross_modal_proof_views(
    proof_graph: CanonicalProofGraph,
    text_view: TextProofView,
    visual_view: VisualProofView,
    *,
    expected_text_output_digest: str,
    expected_rendered_visual_digest: str,
) -> dict[str, Any]:
    validate_digest(expected_text_output_digest, field_name="expected_text_output_digest")
    validate_digest(expected_rendered_visual_digest, field_name="expected_rendered_visual_digest")
    claim_ids = set(proof_graph.claim_ids)
    text_refs_valid = set(text_view.claim_refs).issubset(claim_ids)
    visual_refs_valid = set(visual_view.claim_refs).issubset(claim_ids)
    primitive_state_valid = True
    primitive_failures: list[str] = []
    for primitive in visual_view.primitives:
        if primitive.claim_ref not in claim_ids:
            primitive_state_valid = False
            primitive_failures.append(primitive.primitive_id + ":unknown_claim")
            continue
        claim = proof_graph.claim(primitive.claim_ref)
        if primitive.evidence_state is not claim.status:
            primitive_state_valid = False
            primitive_failures.append(primitive.primitive_id + ":state_mismatch")
    text_digest_valid = text_view.text_output_digest == expected_text_output_digest
    visual_digest_valid = visual_view.rendered_visual_digest == expected_rendered_visual_digest
    proof_graph_valid = text_refs_valid and visual_refs_valid and primitive_state_valid
    text_valid = proof_graph_valid and text_digest_valid
    scene_semantically_valid = proof_graph_valid and visual_refs_valid and primitive_state_valid
    scene_render_valid = scene_semantically_valid and visual_digest_valid
    joined_verification = proof_graph_valid and text_valid and scene_semantically_valid and scene_render_valid
    failure_class = ""
    if not proof_graph_valid:
        failure_class = "proof_graph_reference_mismatch"
    elif not text_digest_valid:
        failure_class = "text_tamper"
    elif not visual_digest_valid:
        failure_class = "visual_tamper"
    return {
        "beast_object_type": "cross_modal_proof_view_verification",
        "version": "1.0",
        "proof_graph_digest": proof_graph.proof_graph_digest,
        "text_view_digest": text_view.view_digest,
        "visual_view_digest": visual_view.view_digest,
        "proof_graph_valid": proof_graph_valid,
        "text_valid": text_valid,
        "scene_semantically_valid": scene_semantically_valid,
        "scene_render_valid": scene_render_valid,
        "joined_verification": joined_verification,
        "failure_class": failure_class,
        "text_refs_valid": text_refs_valid,
        "visual_refs_valid": visual_refs_valid,
        "primitive_state_valid": primitive_state_valid,
        "primitive_failures": tuple(primitive_failures),
        "verification_digest": sha256_digest({
            "proof_graph_digest": proof_graph.proof_graph_digest,
            "text_view_digest": text_view.view_digest,
            "visual_view_digest": visual_view.view_digest,
            "expected_text_output_digest": expected_text_output_digest,
            "expected_rendered_visual_digest": expected_rendered_visual_digest,
            "joined_verification": joined_verification,
            "failure_class": failure_class,
        }),
    }

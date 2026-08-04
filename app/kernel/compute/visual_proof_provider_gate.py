"""Proof-bound gate for image-provider outputs.

External image providers are allowed to paint pixels, not invent claims.  This
module verifies that a provider image request was derived from a canonical
visual proof primitive and that the returned region bytes still satisfy the
primitive's bounded visual intent before the output can be trusted.
"""
from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass
from typing import Any, Mapping

from .generation_provider_adapters import GenerationModality, GenerationProviderReceipt, GenerationProviderRequest
from .proof_graph import CanonicalProofGraph, ProofClaimStatus, VisualProofPrimitive, VisualProofView
from .residual_contracts import canonical_json, sha256_digest, validate_digest
from .visual_residuals import (
    RegionMask,
    VisualPromptIntent,
    evaluate_visual_region_intent,
    evaluate_visual_region_perceptual,
    evaluate_visual_region_quality,
)


@dataclass(frozen=True, slots=True)
class VisualProofProviderPrompt:
    primitive_id: str
    claim_ref: str
    proof_graph_digest: str
    visual_view_digest: str
    prompt: str
    prompt_digest: str
    expected_intent: VisualPromptIntent
    raw_text_answer_used: bool = False
    builder_id: str = "beast.visual-proof-provider-prompt.v1"

    def __post_init__(self) -> None:
        for name in ("proof_graph_digest", "visual_view_digest", "prompt_digest"):
            validate_digest(getattr(self, name), field_name=name)
        if not self.primitive_id.strip() or not self.claim_ref.strip() or not self.prompt.strip():
            raise ValueError("visual proof provider prompt requires primitive, claim ref, and prompt")
        if not isinstance(self.expected_intent, VisualPromptIntent):
            object.__setattr__(self, "expected_intent", VisualPromptIntent(**dict(self.expected_intent)))

    @property
    def prompt_spec_digest(self) -> str:
        return sha256_digest(self)

    def to_dict(self) -> dict[str, Any]:
        return {**asdict(self), "prompt_spec_digest": self.prompt_spec_digest}


@dataclass(frozen=True, slots=True)
class VisualProviderProofGateReceipt:
    proof_graph_digest: str
    visual_view_digest: str
    primitive_digest: str
    claim_ref: str
    claim_status: str
    request_digest: str
    provider_receipt_digest: str
    prompt_spec_digest: str
    expected_prompt_digest: str
    actual_prompt_digest: str
    output_digest: str
    quality_receipt_digest: str
    intent_receipt_digest: str
    perceptual_receipt_digest: str
    proof_graph_valid: bool
    proof_prompt_valid: bool
    provider_receipt_valid: bool
    output_digest_valid: bool
    region_boundary_valid: bool
    quality_valid: bool
    intent_valid: bool
    perceptual_valid: bool
    current_supported_claim: bool
    trusted_for_promotion: bool
    failure_class: str
    refusal_reasons: tuple[str, ...] = ()
    verifier_id: str = "beast.visual-provider-proof-gate.v1"

    def __post_init__(self) -> None:
        for name in (
            "proof_graph_digest",
            "visual_view_digest",
            "primitive_digest",
            "request_digest",
            "provider_receipt_digest",
            "prompt_spec_digest",
            "expected_prompt_digest",
            "actual_prompt_digest",
            "output_digest",
            "quality_receipt_digest",
            "intent_receipt_digest",
            "perceptual_receipt_digest",
        ):
            validate_digest(getattr(self, name), field_name=name)
        canonical_json(self.refusal_reasons)

    @property
    def receipt_digest(self) -> str:
        return sha256_digest(self)

    def to_dict(self) -> dict[str, Any]:
        return {**asdict(self), "receipt_digest": self.receipt_digest}


def build_visual_proof_provider_prompt(
    proof_graph: CanonicalProofGraph,
    visual_view: VisualProofView,
    *,
    primitive_id: str,
) -> VisualProofProviderPrompt:
    """Build a provider prompt only from proof graph + visual primitive data."""
    primitive = _primitive(visual_view, primitive_id)
    claim = proof_graph.claim(primitive.claim_ref)
    expected_color = _expected_color(primitive, claim.status)
    object_hint = str(primitive.metadata.get("object_hint") or "")
    if object_hint not in {"status_light", "indicator", "badge", "region"}:
        object_hint = "status_light" if primitive.primitive.endswith("edge") else "region"
    treatment = str(primitive.metadata.get("visual_treatment") or "proof_bound_visual_treatment")
    prompt = " ".join(
        part
        for part in (
            "canonical proof-bound render primitive",
            primitive.primitive,
            "as",
            expected_color,
            object_hint.replace("_", " "),
            "with treatment",
            treatment,
            "no text no labels no extra causal claims",
        )
        if part
    )
    return VisualProofProviderPrompt(
        primitive_id=primitive.primitive_id,
        claim_ref=primitive.claim_ref,
        proof_graph_digest=proof_graph.proof_graph_digest,
        visual_view_digest=visual_view.view_digest,
        prompt=prompt,
        prompt_digest=sha256_digest({"prompt": prompt}),
        expected_intent=VisualPromptIntent(color_name=expected_color, object_hint=object_hint),
        raw_text_answer_used=False,
    )


def attest_visual_provider_output_against_proof(
    proof_graph: CanonicalProofGraph,
    visual_view: VisualProofView,
    *,
    primitive_id: str,
    provider_request: GenerationProviderRequest,
    provider_receipt: GenerationProviderReceipt,
    output: bytes,
    mask: RegionMask,
    require_current_supported_claim: bool = True,
) -> VisualProviderProofGateReceipt:
    prompt_spec = build_visual_proof_provider_prompt(proof_graph, visual_view, primitive_id=primitive_id)
    primitive = _primitive(visual_view, primitive_id)
    claim = proof_graph.claim(primitive.claim_ref)
    output_digest = "sha256:" + hashlib.sha256(output).hexdigest()
    quality = evaluate_visual_region_quality(mask, output)
    intent = evaluate_visual_region_intent(mask, output, prompt_spec.expected_intent)
    perceptual = evaluate_visual_region_perceptual(mask, output, prompt_spec.expected_intent)
    proof_graph_valid = (
        primitive.claim_ref in proof_graph.claim_ids
        and primitive.evidence_state is claim.status
        and visual_view.view_digest == prompt_spec.visual_view_digest
    )
    proof_prompt_valid = (
        provider_request.prompt_digest == prompt_spec.prompt_digest
        and provider_request.modality is GenerationModality.IMAGE
        and prompt_spec.raw_text_answer_used is False
    )
    provider_receipt_valid = (
        provider_receipt.request_digest == provider_request.request_digest
        and provider_receipt.modality == GenerationModality.IMAGE.value
        and provider_receipt.provider_calls_used >= 1
    )
    output_digest_valid = provider_receipt.output_digest == output_digest
    region_boundary_valid = len(output) == mask.width * mask.height * 4
    current_supported_claim = claim.status is ProofClaimStatus.SUPPORTED if require_current_supported_claim else claim.status is not ProofClaimStatus.STALE
    refusal_reasons = []
    if not proof_graph_valid:
        refusal_reasons.append("proof_graph_reference_mismatch")
    if not proof_prompt_valid:
        refusal_reasons.append("prompt_not_derived_from_visual_proof")
    if not provider_receipt_valid:
        refusal_reasons.append("provider_receipt_mismatch")
    if not output_digest_valid:
        refusal_reasons.append("provider_output_digest_mismatch")
    if not region_boundary_valid:
        refusal_reasons.append("region_boundary_mismatch")
    if not quality.passed:
        refusal_reasons.extend("quality:" + reason for reason in quality.refusal_reasons)
    if not intent.passed:
        refusal_reasons.extend("intent:" + reason for reason in intent.refusal_reasons)
    if not perceptual.passed:
        refusal_reasons.extend("perceptual:" + reason for reason in perceptual.refusal_reasons)
    if not current_supported_claim:
        refusal_reasons.append("claim_not_current_supported")
    trusted = (
        proof_graph_valid
        and proof_prompt_valid
        and provider_receipt_valid
        and output_digest_valid
        and region_boundary_valid
        and quality.passed
        and intent.passed
        and perceptual.passed
        and current_supported_claim
    )
    return VisualProviderProofGateReceipt(
        proof_graph_digest=proof_graph.proof_graph_digest,
        visual_view_digest=visual_view.view_digest,
        primitive_digest=primitive.primitive_digest,
        claim_ref=primitive.claim_ref,
        claim_status=claim.status.value,
        request_digest=provider_request.request_digest,
        provider_receipt_digest=provider_receipt.receipt_digest,
        prompt_spec_digest=prompt_spec.prompt_spec_digest,
        expected_prompt_digest=prompt_spec.prompt_digest,
        actual_prompt_digest=provider_request.prompt_digest,
        output_digest=output_digest,
        quality_receipt_digest=quality.receipt_digest,
        intent_receipt_digest=intent.receipt_digest,
        perceptual_receipt_digest=perceptual.receipt_digest,
        proof_graph_valid=proof_graph_valid,
        proof_prompt_valid=proof_prompt_valid,
        provider_receipt_valid=provider_receipt_valid,
        output_digest_valid=output_digest_valid,
        region_boundary_valid=region_boundary_valid,
        quality_valid=quality.passed,
        intent_valid=intent.passed,
        perceptual_valid=perceptual.passed,
        current_supported_claim=current_supported_claim,
        trusted_for_promotion=trusted,
        failure_class="" if trusted else _failure_class(refusal_reasons),
        refusal_reasons=tuple(sorted(refusal_reasons)),
    )


def _primitive(visual_view: VisualProofView, primitive_id: str) -> VisualProofPrimitive:
    for primitive in visual_view.primitives:
        if primitive.primitive_id == primitive_id:
            return primitive
    raise KeyError(primitive_id)


def _expected_color(primitive: VisualProofPrimitive, status: ProofClaimStatus) -> str:
    explicit = str(primitive.metadata.get("expected_color") or "")
    if explicit in {"red", "green", "blue", "yellow", "white", "black"}:
        return explicit
    return {
        ProofClaimStatus.SUPPORTED: "green",
        ProofClaimStatus.UNSUPPORTED: "yellow",
        ProofClaimStatus.REFUTED: "red",
        ProofClaimStatus.STALE: "yellow",
    }[status]


def _failure_class(reasons: list[str]) -> str:
    order = (
        ("proof_graph_reference_mismatch", "proof_graph_reference_mismatch"),
        ("prompt_not_derived_from_visual_proof", "prompt_proof_mismatch"),
        ("provider_receipt_mismatch", "provider_receipt_mismatch"),
        ("provider_output_digest_mismatch", "output_tamper"),
        ("region_boundary_mismatch", "region_boundary_mismatch"),
        ("quality:", "region_quality_failure"),
        ("intent:", "visual_intent_failure"),
        ("perceptual:", "visual_perceptual_failure"),
        ("claim_not_current_supported", "non_current_claim"),
    )
    for prefix, failure in order:
        if any(reason.startswith(prefix) for reason in reasons):
            return failure
    return "untrusted_provider_visual"

"""Cross-modal composition for joined operational + visual proofs.

The cross-modal plane does not replace the operational or visual composition
planes.  It binds their receipts into one auditable answer/display receipt so
BEAST can prove that a text conclusion and a visual explanation came from the
same verified substrate.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any, Mapping

from .proof_graph import (
    CanonicalProofGraph,
    TextProofView,
    VisualProofView,
    verify_cross_modal_proof_views,
)
from .residual_contracts import canonical_json, sha256_digest, utc_now_iso, validate_digest


class CrossModalStatus(str, Enum):
    COMPOSED = "composed"
    PARTIAL = "partial"
    UNSUPPORTED = "unsupported"


@dataclass(frozen=True, slots=True)
class CrossModalCompositionQuestion:
    question_id: str
    text_question_digest: str
    visual_question_digest: str
    operator_goal: str
    family: str = "restart_risk_visual_explanation"

    def __post_init__(self) -> None:
        if not self.question_id.strip() or not self.operator_goal.strip() or not self.family.strip():
            raise ValueError("cross-modal question requires question_id, operator_goal, and family")
        validate_digest(self.text_question_digest, field_name="text_question_digest")
        validate_digest(self.visual_question_digest, field_name="visual_question_digest")

    @property
    def question_digest(self) -> str:
        return sha256_digest(self)

    def to_dict(self) -> dict[str, Any]:
        return {**asdict(self), "question_digest": self.question_digest}


class CrossModalCompositionPlane:
    """Bind operational and visual composition receipts without blurring scope."""

    def compose_restart_risk_visual(
        self,
        question: CrossModalCompositionQuestion | Mapping[str, Any],
        *,
        text_receipt: Mapping[str, Any],
        visual_receipts: Mapping[str, Mapping[str, Any]],
        proof_graph: CanonicalProofGraph | Mapping[str, Any] | None = None,
        text_view: TextProofView | Mapping[str, Any] | None = None,
        visual_view: VisualProofView | Mapping[str, Any] | None = None,
        proof_first_realization: Mapping[str, Any] | None = None,
        expected_text_output_digest: str = "",
        expected_rendered_visual_digest: str = "",
    ) -> dict[str, Any]:
        q = question if isinstance(question, CrossModalCompositionQuestion) else _question_from_mapping(question)
        text = _receipt_mapping(text_receipt, name="text_receipt")
        visuals = {str(name): _receipt_mapping(receipt, name=f"visual_receipts.{name}") for name, receipt in visual_receipts.items()}
        if not visuals:
            raise ValueError("cross-modal composition requires at least one visual receipt")
        text_status = str(text.get("status") or "")
        visual_statuses = {name: str(receipt.get("status") or "") for name, receipt in visuals.items()}
        text_composed = bool(text.get("composed")) and text_status in {"composed", "residual_composed", "refuted"}
        visual_render_only = all(str(receipt.get("render_authority") or "") == "render_only" for receipt in visuals.values())
        visual_composed = all(bool(receipt.get("composed")) and visual_statuses[name] in {"composed", "residual_composed", "refuted"} for name, receipt in visuals.items())
        text_gaps = tuple(str(item) for item in text.get("unsupported_causal_gaps", ()) or ())
        visual_gaps = tuple(
            f"{name}:{gap}"
            for name, receipt in visuals.items()
            for gap in (receipt.get("unsupported_visual_gaps", ()) or ())
        )
        residual_scopes = tuple(
            str(payload.get("residual_scope") or "")
            for payload in [text.get("residual_payload") or {}, *(receipt.get("residual_payload") or {} for receipt in visuals.values())]
            if payload
        )
        proof_graph_obj = _coerce_proof_graph(proof_graph) if proof_graph is not None else None
        text_view_obj = _coerce_text_view(text_view) if text_view is not None else None
        visual_view_obj = _coerce_visual_view(visual_view) if visual_view is not None else None
        proof_verification = _proof_verification(
            proof_graph_obj,
            text_view_obj,
            visual_view_obj,
            text_receipt=text,
            visual_receipts=visuals,
            expected_text_output_digest=expected_text_output_digest,
            expected_rendered_visual_digest=expected_rendered_visual_digest,
        )
        proof_claim_statuses = tuple(claim.status.value for claim in proof_graph_obj.claims) if proof_graph_obj is not None else ()
        temporal_valid = "stale" not in proof_claim_statuses
        proof_first = dict(proof_first_realization or {})
        text_semantic_valid = bool(proof_first.get("text_semantic_entailment_valid")) if proof_first else bool(proof_verification.get("text_valid")) if proof_verification else False
        scene_plan_semantically_valid = bool(proof_first.get("scene_plan_semantically_valid")) if proof_first else bool(proof_verification.get("scene_semantically_valid")) if proof_verification else False
        scene_render_attempted = bool(proof_first.get("scene_render_attempted")) if proof_first else bool(proof_verification.get("scene_render_valid")) if proof_verification else False
        actual_scene_render_valid = bool(proof_first.get("scene_render_valid")) if proof_first else bool(proof_verification.get("scene_render_valid")) if proof_verification else False
        proof_first_failure = str(proof_first.get("failure_class") or "")
        provider_calls_used = int(text.get("provider_calls_used") or 0) + sum(int(receipt.get("provider_calls_used") or 0) for receipt in visuals.values())
        proof_ok = bool(proof_verification.get("joined_verification")) if proof_verification else False
        if text_composed and visual_composed and visual_render_only and (proof_verification == {} or (proof_ok and temporal_valid and text_semantic_valid and scene_plan_semantically_valid and actual_scene_render_valid)):
            status = CrossModalStatus.COMPOSED
        elif text_composed or visual_composed:
            status = CrossModalStatus.PARTIAL
        else:
            status = CrossModalStatus.UNSUPPORTED
        visual_receipt_set_digest = sha256_digest({
            "visual_receipt_digests": {
                name: str(receipt.get("receipt_digest") or sha256_digest(receipt))
                for name, receipt in visuals.items()
            }
        })
        receipt = {
            "beast_object_type": "cross_modal_composition_receipt",
            "version": "1.0",
            "question": q.to_dict(),
            "status": status.value,
            "composed": status is CrossModalStatus.COMPOSED,
            "partial": status is CrossModalStatus.PARTIAL,
            "text_receipt_digest": str(text.get("receipt_digest") or sha256_digest(text)),
            "visual_receipt_digests": {
                name: str(receipt.get("receipt_digest") or sha256_digest(receipt))
                for name, receipt in visuals.items()
            },
            "visual_receipt_set_digest": visual_receipt_set_digest,
            "text_status": text_status,
            "visual_statuses": visual_statuses,
            "text_answer": dict(text.get("answer") or {}),
            "proof_first": _proof_first_public(proof_first),
            "visual_answers": {
                name: dict(receipt.get("answer") or {})
                for name, receipt in visuals.items()
            },
            "proof_graph_digest": proof_graph_obj.proof_graph_digest if proof_graph_obj is not None else "",
            "proof_graph": proof_graph_obj.to_dict() if proof_graph_obj is not None else {},
            "proof_claim_statuses": proof_claim_statuses,
            "text_proof_view": text_view_obj.to_dict() if text_view_obj is not None else {},
            "visual_proof_view": visual_view_obj.to_dict() if visual_view_obj is not None else {},
            "proof_view_verification": proof_verification,
            "joined_verification": bool(proof_verification.get("joined_verification")) if proof_verification else False,
            "temporal_valid": temporal_valid,
            "current_claim_valid": bool(proof_verification.get("joined_verification")) and temporal_valid if proof_verification else False,
            "text_valid": bool(proof_verification.get("text_valid")) if proof_verification else False,
            "text_semantic_entailment_valid": text_semantic_valid,
            "scene_plan_semantically_valid": scene_plan_semantically_valid,
            "scene_semantically_valid": scene_plan_semantically_valid,
            "scene_render_attempted": scene_render_attempted,
            "scene_render_valid": actual_scene_render_valid,
            "scene_plan_digest": str(proof_first.get("scene_plan_digest") or ""),
            "rendered_artifact_digest": str(proof_first.get("rendered_artifact_digest") or ""),
            "rendered_artifact_media_type": str(proof_first.get("rendered_artifact_media_type") or ""),
            "rendered_artifact_dimensions": dict(proof_first.get("rendered_artifact_dimensions") or {}),
            "visual_asset_resolution": str(proof_first.get("visual_asset_resolution") or ""),
            "placeholder_allowed": proof_first.get("placeholder_allowed") is True,
            "failure_class": proof_first_failure or (str(proof_verification.get("failure_class") or "") if proof_verification else ""),
            "unsupported_causal_gaps": text_gaps,
            "unsupported_visual_gaps": visual_gaps,
            "residual_scopes": residual_scopes,
            "render_authority": "render_only" if visual_render_only else "mixed_or_invalid",
            "provider_calls_used": provider_calls_used,
            "claim_boundary": (
                "Cross-modal binding only. The receipt joins an operational composition receipt with one "
                "or more render-only visual composition receipts. When proof graph/views are supplied, "
                "text and visual must independently reference the same canonical claims. In proof-first "
                "mode, text and scene artifacts must be realized from the graph before joined custody. It does not "
                "create new facts, new pixels, actions, provider calls, or authority beyond the child receipts."
            ),
            "created_at": utc_now_iso(),
        }
        canonical_json(receipt)
        receipt["receipt_digest"] = sha256_digest(receipt)
        return receipt


def _question_from_mapping(value: Mapping[str, Any]) -> CrossModalCompositionQuestion:
    allowed = {"question_id", "text_question_digest", "visual_question_digest", "operator_goal", "family"}
    return CrossModalCompositionQuestion(**{key: item for key, item in dict(value).items() if key in allowed})


def _receipt_mapping(value: Mapping[str, Any], *, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or not value:
        raise ValueError(f"{name} must be a non-empty receipt mapping")
    canonical_json(value)
    return value


def _coerce_proof_graph(value: CanonicalProofGraph | Mapping[str, Any]) -> CanonicalProofGraph:
    if isinstance(value, CanonicalProofGraph):
        return value
    from .proof_graph import ProofGraphClaim

    data = dict(value)
    claims = tuple(
        claim if isinstance(claim, ProofGraphClaim) else ProofGraphClaim(**{
            key: item for key, item in dict(claim).items()
            if key in {"claim_id", "claim_type", "subject", "predicate", "object", "status", "confidence_class", "fact_refs", "rule_ref", "policy_ref", "snapshot_ref", "metadata"}
        })
        for claim in data.get("claims", ())
    )
    return CanonicalProofGraph(
        graph_id=str(data.get("graph_id") or ""),
        claims=claims,
        world_snapshot_digest=str(data.get("world_snapshot_digest") or ""),
        policy_digest=str(data.get("policy_digest") or ""),
        capability_fact_digests=tuple(data.get("capability_fact_digests") or ()),
        causal_rule_digests=tuple(data.get("causal_rule_digests") or ()),
    )


def _coerce_text_view(value: TextProofView | Mapping[str, Any]) -> TextProofView:
    if isinstance(value, TextProofView):
        return value
    data = dict(value)
    return TextProofView(
        view_id=str(data.get("view_id") or ""),
        text_output_digest=str(data.get("text_output_digest") or ""),
        claim_refs=tuple(data.get("claim_refs") or ()),
        renderer_id=str(data.get("renderer_id") or "beast.text-realizer.proof-view.v1"),
    )


def _coerce_visual_view(value: VisualProofView | Mapping[str, Any]) -> VisualProofView:
    if isinstance(value, VisualProofView):
        return value
    from .proof_graph import VisualProofPrimitive

    data = dict(value)
    primitives = tuple(
        item if isinstance(item, VisualProofPrimitive) else VisualProofPrimitive(**{
            key: field for key, field in dict(item).items()
            if key in {"primitive_id", "primitive", "claim_ref", "evidence_state", "metadata"}
        })
        for item in data.get("primitives", ())
    )
    return VisualProofView(
        view_id=str(data.get("view_id") or ""),
        scene_capsule_digest=str(data.get("scene_capsule_digest") or ""),
        rendered_visual_digest=str(data.get("rendered_visual_digest") or ""),
        asset_manifest_digest=str(data.get("asset_manifest_digest") or ""),
        layout_engine_digest=str(data.get("layout_engine_digest") or ""),
        primitives=primitives,
        compiler_id=str(data.get("compiler_id") or "beast.scene-compiler.proof-view.v1"),
    )


def _proof_verification(
    proof_graph: CanonicalProofGraph | None,
    text_view: TextProofView | None,
    visual_view: VisualProofView | None,
    *,
    text_receipt: Mapping[str, Any],
    visual_receipts: Mapping[str, Mapping[str, Any]],
    expected_text_output_digest: str = "",
    expected_rendered_visual_digest: str = "",
) -> dict[str, Any]:
    if proof_graph is None and text_view is None and visual_view is None:
        return {}
    if proof_graph is None or text_view is None or visual_view is None:
        raise ValueError("proof_graph, text_view, and visual_view must be supplied together")
    visual_digest = expected_rendered_visual_digest or sha256_digest({
        "visual_receipt_digests": {
            name: str(receipt.get("receipt_digest") or sha256_digest(receipt))
            for name, receipt in visual_receipts.items()
        }
    })
    return verify_cross_modal_proof_views(
        proof_graph,
        text_view,
        visual_view,
        expected_text_output_digest=expected_text_output_digest or sha256_digest(text_receipt.get("answer") or {}),
        expected_rendered_visual_digest=visual_digest,
    )


def _proof_first_public(proof_first: Mapping[str, Any]) -> dict[str, Any]:
    if not proof_first:
        return {}
    return {
        "beast_object_type": str(proof_first.get("beast_object_type") or ""),
        "version": str(proof_first.get("version") or ""),
        "execution_order": tuple(proof_first.get("execution_order") or ()),
        "proof_graph_compiled_before_outputs": proof_first.get("proof_graph_compiled_before_outputs") is True,
        "text_frame": dict(proof_first.get("text_frame") or {}),
        "text_artifact_digest": str(proof_first.get("text_artifact_digest") or ""),
        "text_artifact_text": str(proof_first.get("text_artifact_text") or ""),
        "scene_plan": dict(proof_first.get("scene_plan") or {}),
        "scene_plan_digest": str(proof_first.get("scene_plan_digest") or ""),
        "rendered_artifact_digest": str(proof_first.get("rendered_artifact_digest") or ""),
        "rendered_artifact_media_type": str(proof_first.get("rendered_artifact_media_type") or ""),
        "rendered_artifact_dimensions": dict(proof_first.get("rendered_artifact_dimensions") or {}),
        "text_semantic_entailment_valid": proof_first.get("text_semantic_entailment_valid") is True,
        "scene_plan_semantically_valid": proof_first.get("scene_plan_semantically_valid") is True,
        "scene_render_attempted": proof_first.get("scene_render_attempted") is True,
        "scene_render_valid": proof_first.get("scene_render_valid") is True,
        "visual_asset_resolution": str(proof_first.get("visual_asset_resolution") or ""),
        "placeholder_allowed": proof_first.get("placeholder_allowed") is True,
        "failure_class": str(proof_first.get("failure_class") or ""),
    }

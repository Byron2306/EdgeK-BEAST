"""Visual capability composition for bounded render-only inference.

This module proves that the visual layer can compose verified visual
capabilities instead of merely replaying one generated image.  It starts with
three small families:

    - status-card scene assembly
    - promoted/equivalent visual region reuse
    - layout safety for placing a visual asset into a canvas

The plane never creates pixels, calls providers, or grants non-render authority.
When a gap remains, residual routing is limited to declared metadata fields,
not image bytes.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Callable, Mapping

from .residual_contracts import canonical_json, sha256_digest, utc_now_iso, validate_digest


class VisualFactType(str, Enum):
    SCENE_CAPSULE = "scene_capsule"
    ASSET_MANIFEST = "asset_manifest"
    VISUAL_INTENT = "visual_intent"
    REGION_MASK = "region_mask"
    PROMOTED_VISUAL_ASSET = "promoted_visual_asset"
    QUALITY_RECEIPT = "quality_receipt"
    INTENT_RECEIPT = "intent_receipt"
    PERCEPTUAL_RECEIPT = "perceptual_receipt"
    FEATURE_EMBEDDING = "feature_embedding"
    EQUIVALENCE_RECEIPT = "equivalence_receipt"
    CANVAS_CONTRACT = "canvas_contract"
    LAYOUT_ANCHOR = "layout_anchor"


class VisualCompositionStatus(str, Enum):
    COMPOSED = "composed"
    RESIDUAL_COMPOSED = "residual_composed"
    UNSUPPORTED = "unsupported"
    REFUTED = "refuted"


@dataclass(frozen=True, slots=True)
class VisualCapabilityFact:
    fact_id: str
    fact_type: VisualFactType
    subject: str
    predicate: str
    value: Any
    evidence_digest: str
    object: str = ""
    authority: str = "render_only"
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.fact_id.strip() or not self.subject.strip() or not self.predicate.strip():
            raise ValueError("visual capability facts require fact_id, subject, and predicate")
        if not isinstance(self.fact_type, VisualFactType):
            object.__setattr__(self, "fact_type", VisualFactType(self.fact_type))
        validate_digest(self.evidence_digest, field_name="evidence_digest")
        canonical_json(self.value)
        canonical_json(self.metadata)
        if self.authority != "render_only":
            raise ValueError("visual capability facts must be render_only")

    @property
    def fact_digest(self) -> str:
        return sha256_digest(self)

    def to_dict(self) -> dict[str, Any]:
        return {**asdict(self), "fact_type": self.fact_type.value, "fact_digest": self.fact_digest}


@dataclass(frozen=True, slots=True)
class VisualCompositionQuestion:
    question_id: str
    scene_id: str
    region_id: str
    visual_goal: str
    question_type: str = "visual_status_card_composition"

    def __post_init__(self) -> None:
        if not self.question_id.strip() or not self.scene_id.strip() or not self.region_id.strip():
            raise ValueError("visual composition question requires question_id, scene_id, and region_id")
        if not self.visual_goal.strip():
            raise ValueError("visual composition question requires visual_goal")

    @property
    def question_digest(self) -> str:
        return sha256_digest(self)

    def to_dict(self) -> dict[str, Any]:
        return {**asdict(self), "question_digest": self.question_digest}


class VisualCapabilityCompositionPlane:
    """Compose verified render-only visual facts into bounded answers."""

    def compose_status_card(
        self,
        question: VisualCompositionQuestion | Mapping[str, Any],
        facts: tuple[VisualCapabilityFact, ...] | list[VisualCapabilityFact] | tuple[Mapping[str, Any], ...] | list[Mapping[str, Any]],
        *,
        residual_worker: Callable[[Mapping[str, Any]], Mapping[str, Any]] | None = None,
    ) -> dict[str, Any]:
        q = _coerce_question(question)
        visual_facts = _coerce_facts(facts)
        components = _select_status_card_components(q, visual_facts)
        missing = _missing_components_for(components, ("scene_capsule", "asset_manifest", "visual_intent", "layout_anchor"))
        unsupported = list(missing)
        status = VisualCompositionStatus.UNSUPPORTED
        answer: dict[str, Any] = {}
        residual_payload: dict[str, Any] | None = None
        residual_receipt: dict[str, Any] | None = None
        residual_used = False

        if not missing and components["promoted_asset"] is None:
            unsupported.append("status_card_region_asset")
            residual_payload = _residual_payload(
                q,
                components,
                task_family="visual_composition.status_card",
                unresolved_fields=("asset_candidate_class", "visual_rationale"),
                allowed_output={"asset_candidate_class": ("exact", "equivalent", "missing"), "visual_rationale": "string"},
                residual_scope="asset_gap_only",
            )
            if residual_worker is not None:
                result = dict(residual_worker(residual_payload))
                residual_receipt = _validate_residual_result(
                    residual_payload,
                    result,
                    allowed_fields=("asset_candidate_class", "visual_rationale"),
                    class_field="asset_candidate_class",
                    class_values=("exact", "equivalent", "missing"),
                    rationale_field="visual_rationale",
                )
                answer = {
                    "composition_class": result["asset_candidate_class"],
                    "summary": result["visual_rationale"],
                    "render_authority": "render_only",
                }
                status = VisualCompositionStatus.RESIDUAL_COMPOSED
                residual_used = True
                unsupported.clear()
        elif not missing:
            status = VisualCompositionStatus.COMPOSED
            answer = _status_card_answer(q, components)

        return _visual_receipt(
            q,
            status=status,
            answer=answer,
            components=components,
            unsupported=unsupported,
            residual_payload=residual_payload,
            residual_receipt=residual_receipt,
            residual_used=residual_used,
            claim_boundary=(
                "Bounded status-card visual composition only. The receipt can assert deterministic render-only "
                "assembly from a scene capsule, manifest, intent, anchor, and promoted asset. Missing asset "
                "selection may route only metadata fields, never pixels, to a residual worker."
            ),
        )

    def compose_promoted_region_reuse(
        self,
        question: VisualCompositionQuestion | Mapping[str, Any],
        facts: tuple[VisualCapabilityFact, ...] | list[VisualCapabilityFact] | tuple[Mapping[str, Any], ...] | list[Mapping[str, Any]],
        *,
        residual_worker: Callable[[Mapping[str, Any]], Mapping[str, Any]] | None = None,
    ) -> dict[str, Any]:
        q = _coerce_question(question)
        visual_facts = _coerce_facts(facts)
        components = _select_region_reuse_components(q, visual_facts)
        missing = _missing_components_for(
            components,
            ("scene_capsule", "region_mask", "visual_intent", "promoted_asset", "quality_receipt", "intent_receipt", "perceptual_receipt"),
        )
        unsupported = list(missing)
        status = VisualCompositionStatus.UNSUPPORTED
        answer: dict[str, Any] = {}
        residual_payload: dict[str, Any] | None = None
        residual_receipt: dict[str, Any] | None = None
        residual_used = False

        if not missing and components["feature_embedding"] is None and components["equivalence_receipt"] is None:
            unsupported.append("visual_equivalence_or_exact_digest")
            residual_payload = _residual_payload(
                q,
                components,
                task_family="visual_composition.promoted_region_reuse",
                unresolved_fields=("reuse_class", "visual_rationale"),
                allowed_output={"reuse_class": ("exact", "equivalent", "missing"), "visual_rationale": "string"},
                residual_scope="visual_equivalence_gap_only",
            )
            if residual_worker is not None:
                result = dict(residual_worker(residual_payload))
                residual_receipt = _validate_residual_result(
                    residual_payload,
                    result,
                    allowed_fields=("reuse_class", "visual_rationale"),
                    class_field="reuse_class",
                    class_values=("exact", "equivalent", "missing"),
                    rationale_field="visual_rationale",
                )
                answer = {
                    "reuse_class": result["reuse_class"],
                    "summary": result["visual_rationale"],
                    "render_authority": "render_only",
                }
                status = VisualCompositionStatus.RESIDUAL_COMPOSED
                residual_used = True
                unsupported.clear()
        elif not missing:
            status = VisualCompositionStatus.COMPOSED
            answer = _reuse_answer(q, components)

        return _visual_receipt(
            q,
            status=status,
            answer=answer,
            components=components,
            unsupported=unsupported,
            residual_payload=residual_payload,
            residual_receipt=residual_receipt,
            residual_used=residual_used,
            claim_boundary=(
                "Bounded promoted-region visual reuse only. The receipt can authorize render-only reuse "
                "when quality, intent, perceptual, and exact/equivalence evidence are present. It cannot "
                "invent pixels or broaden visual intent."
            ),
        )

    def compose_layout_safety(
        self,
        question: VisualCompositionQuestion | Mapping[str, Any],
        facts: tuple[VisualCapabilityFact, ...] | list[VisualCapabilityFact] | tuple[Mapping[str, Any], ...] | list[Mapping[str, Any]],
        *,
        residual_worker: Callable[[Mapping[str, Any]], Mapping[str, Any]] | None = None,
    ) -> dict[str, Any]:
        del residual_worker
        q = _coerce_question(question)
        visual_facts = _coerce_facts(facts)
        components = _select_layout_components(q, visual_facts)
        missing = _missing_components_for(components, ("canvas_contract", "layout_anchor", "promoted_asset"))
        unsupported = list(missing)
        status = VisualCompositionStatus.UNSUPPORTED
        answer: dict[str, Any] = {}
        if not missing:
            safe, summary = _layout_safety(components)
            status = VisualCompositionStatus.COMPOSED if safe else VisualCompositionStatus.REFUTED
            answer = {
                "layout_class": "safe" if safe else "unsafe",
                "summary": summary,
                "render_authority": "render_only",
            }

        return _visual_receipt(
            q,
            status=status,
            answer=answer,
            components=components,
            unsupported=unsupported,
            residual_payload=None,
            residual_receipt=None,
            residual_used=False,
            claim_boundary=(
                "Bounded visual layout composition only. The receipt can compare declared canvas, anchor, "
                "and asset dimensions for bounds safety; it does not resize, crop, or mutate the asset."
            ),
        )


def _visual_receipt(
    question: VisualCompositionQuestion,
    *,
    status: VisualCompositionStatus,
    answer: Mapping[str, Any],
    components: Mapping[str, VisualCapabilityFact | None],
    unsupported: list[str],
    residual_payload: Mapping[str, Any] | None,
    residual_receipt: Mapping[str, Any] | None,
    residual_used: bool,
    claim_boundary: str,
) -> dict[str, Any]:
    receipt = {
        "beast_object_type": "visual_capability_composition_receipt",
        "version": "1.0",
        "question": question.to_dict(),
        "status": status.value,
        "composed": status in {VisualCompositionStatus.COMPOSED, VisualCompositionStatus.RESIDUAL_COMPOSED, VisualCompositionStatus.REFUTED},
        "residual_used": residual_used,
        "answer": dict(answer),
        "component_fact_digests": {
            name: fact.fact_digest
            for name, fact in components.items()
            if isinstance(fact, VisualCapabilityFact)
        },
        "component_evidence_digests": tuple(
            fact.evidence_digest
            for fact in components.values()
            if isinstance(fact, VisualCapabilityFact)
        ),
        "unsupported_visual_gaps": tuple(unsupported),
        "residual_payload": dict(residual_payload or {}),
        "residual_receipt": dict(residual_receipt or {}),
        "claim_boundary": claim_boundary,
        "render_authority": "render_only",
        "provider_calls_used": 0,
        "created_at": utc_now_iso(),
    }
    receipt["receipt_digest"] = sha256_digest(receipt)
    return receipt


def _coerce_question(question: VisualCompositionQuestion | Mapping[str, Any]) -> VisualCompositionQuestion:
    return question if isinstance(question, VisualCompositionQuestion) else _question_from_mapping(question)


def _coerce_facts(
    facts: tuple[VisualCapabilityFact, ...] | list[VisualCapabilityFact] | tuple[Mapping[str, Any], ...] | list[Mapping[str, Any]],
) -> tuple[VisualCapabilityFact, ...]:
    return tuple(item if isinstance(item, VisualCapabilityFact) else _fact_from_mapping(item) for item in facts)


def _question_from_mapping(value: Mapping[str, Any]) -> VisualCompositionQuestion:
    allowed = {"question_id", "scene_id", "region_id", "visual_goal", "question_type"}
    return VisualCompositionQuestion(**{key: item for key, item in dict(value).items() if key in allowed})


def _fact_from_mapping(value: Mapping[str, Any]) -> VisualCapabilityFact:
    allowed = {"fact_id", "fact_type", "subject", "predicate", "value", "evidence_digest", "object", "authority", "metadata"}
    return VisualCapabilityFact(**{key: item for key, item in dict(value).items() if key in allowed})


def _select_status_card_components(question: VisualCompositionQuestion, facts: tuple[VisualCapabilityFact, ...]) -> dict[str, VisualCapabilityFact | None]:
    return {
        "scene_capsule": _first(facts, VisualFactType.SCENE_CAPSULE, subject=question.scene_id),
        "asset_manifest": _first(facts, VisualFactType.ASSET_MANIFEST, subject=question.scene_id),
        "visual_intent": _first(facts, VisualFactType.VISUAL_INTENT, subject=question.region_id),
        "layout_anchor": _first(facts, VisualFactType.LAYOUT_ANCHOR, subject=question.region_id),
        "promoted_asset": _first(facts, VisualFactType.PROMOTED_VISUAL_ASSET, subject=question.region_id),
    }


def _select_region_reuse_components(question: VisualCompositionQuestion, facts: tuple[VisualCapabilityFact, ...]) -> dict[str, VisualCapabilityFact | None]:
    return {
        "scene_capsule": _first(facts, VisualFactType.SCENE_CAPSULE, subject=question.scene_id),
        "region_mask": _first(facts, VisualFactType.REGION_MASK, subject=question.region_id),
        "visual_intent": _first(facts, VisualFactType.VISUAL_INTENT, subject=question.region_id),
        "promoted_asset": _first(facts, VisualFactType.PROMOTED_VISUAL_ASSET, subject=question.region_id),
        "quality_receipt": _first(facts, VisualFactType.QUALITY_RECEIPT, subject=question.region_id),
        "intent_receipt": _first(facts, VisualFactType.INTENT_RECEIPT, subject=question.region_id),
        "perceptual_receipt": _first(facts, VisualFactType.PERCEPTUAL_RECEIPT, subject=question.region_id),
        "feature_embedding": _first(facts, VisualFactType.FEATURE_EMBEDDING, subject=question.region_id),
        "equivalence_receipt": _first(facts, VisualFactType.EQUIVALENCE_RECEIPT, subject=question.region_id),
    }


def _select_layout_components(question: VisualCompositionQuestion, facts: tuple[VisualCapabilityFact, ...]) -> dict[str, VisualCapabilityFact | None]:
    return {
        "canvas_contract": _first(facts, VisualFactType.CANVAS_CONTRACT, subject=question.scene_id),
        "layout_anchor": _first(facts, VisualFactType.LAYOUT_ANCHOR, subject=question.region_id),
        "promoted_asset": _first(facts, VisualFactType.PROMOTED_VISUAL_ASSET, subject=question.region_id),
    }


def _first(
    facts: tuple[VisualCapabilityFact, ...],
    fact_type: VisualFactType,
    *,
    subject: str,
) -> VisualCapabilityFact | None:
    for fact in facts:
        if fact.fact_type is fact_type and fact.subject == subject:
            return fact
    return None


def _missing_components_for(components: Mapping[str, VisualCapabilityFact | None], names: tuple[str, ...]) -> list[str]:
    return [name for name in names if components.get(name) is None]


def _status_card_answer(question: VisualCompositionQuestion, components: Mapping[str, VisualCapabilityFact | None]) -> dict[str, Any]:
    asset = components["promoted_asset"]
    intent = components["visual_intent"]
    anchor = components["layout_anchor"]
    assert asset is not None and intent is not None and anchor is not None
    return {
        "composition_class": "deterministic_scene_plus_promoted_region",
        "summary": (
            f"Scene {question.scene_id} can render {question.visual_goal} using promoted asset "
            f"{_value_mapping(asset).get('asset_id', asset.subject)} at anchor {_value_mapping(anchor).get('anchor', anchor.subject)}."
        ),
        "visual_intent_digest": intent.fact_digest,
        "asset_digest": str(_value_mapping(asset).get("asset_digest") or asset.evidence_digest),
        "render_authority": "render_only",
    }


def _reuse_answer(question: VisualCompositionQuestion, components: Mapping[str, VisualCapabilityFact | None]) -> dict[str, Any]:
    asset = components["promoted_asset"]
    equivalence = components["equivalence_receipt"]
    feature = components["feature_embedding"]
    assert asset is not None
    reuse_class = "equivalent" if equivalence is not None else "exact"
    return {
        "reuse_class": reuse_class,
        "summary": (
            f"Region {question.region_id} can reuse promoted visual asset "
            f"{_value_mapping(asset).get('asset_id', asset.subject)} with quality, intent, perceptual, "
            f"and {'equivalence' if equivalence is not None else 'exact/feature'} evidence."
        ),
        "asset_digest": str(_value_mapping(asset).get("asset_digest") or asset.evidence_digest),
        "feature_embedding_digest": feature.fact_digest if feature is not None else "",
        "equivalence_receipt_digest": equivalence.fact_digest if equivalence is not None else "",
        "render_authority": "render_only",
    }


def _layout_safety(components: Mapping[str, VisualCapabilityFact | None]) -> tuple[bool, str]:
    canvas = components["canvas_contract"]
    anchor = components["layout_anchor"]
    asset = components["promoted_asset"]
    assert canvas is not None and anchor is not None and asset is not None
    canvas_value = _value_mapping(canvas)
    anchor_value = _value_mapping(anchor)
    asset_value = _value_mapping(asset)
    canvas_width = _number(canvas_value.get("width"))
    canvas_height = _number(canvas_value.get("height"))
    x = _number(anchor_value.get("x"))
    y = _number(anchor_value.get("y"))
    width = _number(anchor_value.get("width") or asset_value.get("width"))
    height = _number(anchor_value.get("height") or asset_value.get("height"))
    safe = canvas_width > 0 and canvas_height > 0 and width > 0 and height > 0 and x >= 0 and y >= 0 and x + width <= canvas_width and y + height <= canvas_height
    if safe:
        return True, f"Asset placement is within {canvas_width:g}x{canvas_height:g} canvas bounds at ({x:g}, {y:g}) with size {width:g}x{height:g}."
    return False, f"Asset placement would exceed {canvas_width:g}x{canvas_height:g} canvas bounds at ({x:g}, {y:g}) with size {width:g}x{height:g}."


def _residual_payload(
    question: VisualCompositionQuestion,
    components: Mapping[str, VisualCapabilityFact | None],
    *,
    task_family: str,
    unresolved_fields: tuple[str, ...],
    allowed_output: Mapping[str, Any],
    residual_scope: str,
) -> dict[str, Any]:
    payload = {
        "task_family": task_family,
        "question_digest": question.question_digest,
        "unresolved_fields": list(unresolved_fields),
        "allowed_output": dict(allowed_output),
        "component_fact_digests": {
            name: fact.fact_digest
            for name, fact in components.items()
            if isinstance(fact, VisualCapabilityFact)
        },
        "bounded_context": {
            name: fact.value
            for name, fact in components.items()
            if isinstance(fact, VisualCapabilityFact)
        },
        "forbidden_claims": ("new_pixels", "new_assets", "new_scene_authority", "network_or_provider_use", "physical_actions"),
        "residual_scope": residual_scope,
    }
    payload["residual_payload_digest"] = sha256_digest(payload)
    return payload


def _validate_residual_result(
    payload: Mapping[str, Any],
    result: Mapping[str, Any],
    *,
    allowed_fields: tuple[str, ...],
    class_field: str,
    class_values: tuple[str, ...],
    rationale_field: str,
) -> dict[str, Any]:
    allowed = set(allowed_fields)
    extra = sorted(set(result) - allowed)
    if extra:
        raise ValueError("visual composition residual returned undeclared fields: " + ", ".join(extra))
    classification = str(result.get(class_field) or "")
    if classification not in set(class_values):
        raise ValueError(f"visual composition residual returned invalid {class_field}")
    rationale = str(result.get(rationale_field) or "").strip()
    if not rationale:
        raise ValueError(f"visual composition residual must return {rationale_field}")
    receipt = {
        "beast_object_type": "visual_capability_composition_residual_receipt",
        "version": "1.0",
        "residual_payload_digest": str(payload.get("residual_payload_digest") or sha256_digest(payload)),
        "returned_fields": tuple(sorted(result)),
        "accepted": True,
        "created_at": utc_now_iso(),
    }
    receipt["receipt_digest"] = sha256_digest(receipt)
    return receipt


def _value_mapping(fact: VisualCapabilityFact) -> Mapping[str, Any]:
    return fact.value if isinstance(fact.value, Mapping) else {"value": fact.value}


def _number(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0

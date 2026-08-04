from pathlib import Path

from app.kernel.compute.compute_plane import ComputePlane
from app.kernel.compute.residual_contracts import sha256_digest
from app.kernel.compute.visual_capability_composition import (
    VisualCapabilityCompositionPlane,
    VisualCapabilityFact,
    VisualCompositionQuestion,
    VisualFactType,
)


def test_visual_composition_builds_status_card_from_scene_intent_and_asset():
    receipt = VisualCapabilityCompositionPlane().compose_status_card(
        _status_question(),
        _status_facts(include_asset=True),
    )

    assert receipt["status"] == "composed"
    assert receipt["answer"]["composition_class"] == "deterministic_scene_plus_promoted_region"
    assert receipt["render_authority"] == "render_only"
    assert receipt["provider_calls_used"] == 0
    assert set(receipt["component_fact_digests"]) == {
        "scene_capsule",
        "asset_manifest",
        "visual_intent",
        "layout_anchor",
        "promoted_asset",
    }


def test_visual_composition_routes_only_status_card_asset_gap_to_residual():
    seen = {}

    def worker(payload):
        seen.update(payload)
        return {
            "asset_candidate_class": "equivalent",
            "visual_rationale": "Bounded residual selected only an equivalent asset class; no pixels or new assets were produced.",
        }

    receipt = VisualCapabilityCompositionPlane().compose_status_card(
        _status_question(),
        _status_facts(include_asset=False),
        residual_worker=worker,
    )

    assert receipt["status"] == "residual_composed"
    assert receipt["residual_used"] is True
    assert seen["residual_scope"] == "asset_gap_only"
    assert seen["unresolved_fields"] == ["asset_candidate_class", "visual_rationale"]
    assert set(seen["allowed_output"]) == {"asset_candidate_class", "visual_rationale"}


def test_visual_composition_reuses_promoted_region_with_equivalence_proof():
    receipt = VisualCapabilityCompositionPlane().compose_promoted_region_reuse(
        _reuse_question(),
        _reuse_facts(include_equivalence=True),
    )

    assert receipt["status"] == "composed"
    assert receipt["answer"]["reuse_class"] == "equivalent"
    assert receipt["render_authority"] == "render_only"
    assert set(receipt["component_fact_digests"]) == {
        "scene_capsule",
        "region_mask",
        "visual_intent",
        "promoted_asset",
        "quality_receipt",
        "intent_receipt",
        "perceptual_receipt",
        "feature_embedding",
        "equivalence_receipt",
    }


def test_visual_composition_refuses_reuse_without_exact_or_equivalence_evidence():
    receipt = VisualCapabilityCompositionPlane().compose_promoted_region_reuse(
        _reuse_question(),
        _reuse_facts(include_equivalence=False),
    )

    assert receipt["status"] == "unsupported"
    assert receipt["unsupported_visual_gaps"] == ("visual_equivalence_or_exact_digest",)
    assert receipt["residual_payload"]["residual_scope"] == "visual_equivalence_gap_only"
    assert receipt["residual_payload"]["unresolved_fields"] == ["reuse_class", "visual_rationale"]


def test_visual_composition_checks_layout_safety_and_refutes_overflow():
    plane = VisualCapabilityCompositionPlane()
    safe = plane.compose_layout_safety(_layout_question(), _layout_facts(overflow=False))
    overflow = plane.compose_layout_safety(_layout_question(), _layout_facts(overflow=True))

    assert safe["status"] == "composed"
    assert safe["answer"]["layout_class"] == "safe"
    assert overflow["status"] == "refuted"
    assert overflow["answer"]["layout_class"] == "unsafe"
    assert overflow["composed"] is True


def test_compute_plane_records_visual_composition_learning(tmp_path: Path):
    plane = ComputePlane(root=tmp_path)
    status = plane.compose_visual_status_card(
        {"question": _status_question().to_dict(), "facts": [fact.to_dict() for fact in _status_facts(include_asset=True)]},
        interface="test",
    )
    reuse = plane.compose_visual_promoted_region_reuse(
        {"question": _reuse_question().to_dict(), "facts": [fact.to_dict() for fact in _reuse_facts(include_equivalence=True)]},
        interface="test",
    )
    layout = plane.compose_visual_layout_safety(
        {"question": _layout_question().to_dict(), "facts": [fact.to_dict() for fact in _layout_facts(overflow=False)]},
        interface="test",
    )
    learning = plane.capability_learning_report()

    assert status["status"] == reuse["status"] == layout["status"] == "composed"
    assert learning["by_capability_type"]["visual_composition"] == 3
    assert {item["capability_id"].split(":", 1)[0] for item in learning["capabilities"]} >= {
        "status-card",
        "promoted-region-reuse",
        "layout-safety",
    }


def _status_question() -> VisualCompositionQuestion:
    return VisualCompositionQuestion(
        question_id="visual-question:status-card",
        scene_id="scene:beast-status",
        region_id="region:status-light",
        visual_goal="green healthy status light on BEAST card",
    )


def _reuse_question() -> VisualCompositionQuestion:
    return VisualCompositionQuestion(
        question_id="visual-question:reuse-status-light",
        scene_id="scene:beast-status",
        region_id="region:status-light",
        visual_goal="reuse verified green status light region",
        question_type="visual_promoted_region_reuse",
    )


def _layout_question() -> VisualCompositionQuestion:
    return VisualCompositionQuestion(
        question_id="visual-question:layout-status-light",
        scene_id="scene:beast-status",
        region_id="region:status-light",
        visual_goal="place status light inside the status card canvas",
        question_type="visual_layout_safety",
    )


def _status_facts(*, include_asset: bool) -> tuple[VisualCapabilityFact, ...]:
    facts = [
        _fact(VisualFactType.SCENE_CAPSULE, "scene:beast-status", "capsule", {"capsule_digest": sha256_digest("scene-capsule")}),
        _fact(VisualFactType.ASSET_MANIFEST, "scene:beast-status", "manifest", {"manifest_digest": sha256_digest("manifest")}),
        _fact(VisualFactType.VISUAL_INTENT, "region:status-light", "intent", {"color": "green", "object": "status_light"}),
        _fact(VisualFactType.LAYOUT_ANCHOR, "region:status-light", "anchor", {"anchor": "top_right", "x": 120, "y": 24, "width": 16, "height": 16}),
    ]
    if include_asset:
        facts.append(_promoted_asset())
    return tuple(facts)


def _reuse_facts(*, include_equivalence: bool) -> tuple[VisualCapabilityFact, ...]:
    facts = [
        _fact(VisualFactType.SCENE_CAPSULE, "scene:beast-status", "capsule", {"capsule_digest": sha256_digest("scene-capsule")}),
        _fact(VisualFactType.REGION_MASK, "region:status-light", "mask", {"x": 120, "y": 24, "width": 16, "height": 16}),
        _fact(VisualFactType.VISUAL_INTENT, "region:status-light", "intent", {"color": "green", "object": "status_light"}),
        _promoted_asset(),
        _fact(VisualFactType.QUALITY_RECEIPT, "region:status-light", "quality", {"passed": True}),
        _fact(VisualFactType.INTENT_RECEIPT, "region:status-light", "intent_receipt", {"passed": True}),
        _fact(VisualFactType.PERCEPTUAL_RECEIPT, "region:status-light", "perceptual", {"passed": True, "center_luma_lift": 0.42}),
    ]
    if include_equivalence:
        facts.extend([
            _fact(VisualFactType.FEATURE_EMBEDDING, "region:status-light", "embedding", {"bins": [1, 4, 2, 8], "source": "visual_feature_embedding"}),
            _fact(VisualFactType.EQUIVALENCE_RECEIPT, "region:status-light", "equivalence", {"equivalent": True, "distance": 0.03}),
        ])
    return tuple(facts)


def _layout_facts(*, overflow: bool) -> tuple[VisualCapabilityFact, ...]:
    return (
        _fact(VisualFactType.CANVAS_CONTRACT, "scene:beast-status", "canvas", {"width": 180, "height": 100}),
        _fact(
            VisualFactType.LAYOUT_ANCHOR,
            "region:status-light",
            "anchor",
            {"x": 120 if not overflow else 170, "y": 24, "width": 16, "height": 16},
        ),
        _promoted_asset(),
    )


def _promoted_asset() -> VisualCapabilityFact:
    return _fact(
        VisualFactType.PROMOTED_VISUAL_ASSET,
        "region:status-light",
        "asset",
        {
            "asset_id": "visual.promoted.status_light.green",
            "asset_digest": sha256_digest("green-status-light-rgba"),
            "width": 16,
            "height": 16,
            "state": "promoted",
        },
    )


def _fact(
    fact_type: VisualFactType,
    subject: str,
    predicate: str,
    value,
    *,
    object: str = "",
) -> VisualCapabilityFact:
    return VisualCapabilityFact(
        fact_id=f"visual-fact:{fact_type.value}:{subject}:{predicate}:{object}",
        fact_type=fact_type,
        subject=subject,
        predicate=predicate,
        object=object,
        value=value,
        evidence_digest=sha256_digest({"fact": fact_type.value, "subject": subject, "predicate": predicate, "object": object, "value": value}),
    )

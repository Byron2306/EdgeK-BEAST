from pathlib import Path

from app.kernel.compute.compute_plane import ComputePlane
from app.kernel.compute.cross_modal_composition import CrossModalCompositionPlane, CrossModalCompositionQuestion
from app.kernel.compute.proof_graph import (
    CanonicalProofGraph,
    ProofGraphClaim,
    TextProofView,
    VisualProofPrimitive,
    VisualProofView,
    verify_cross_modal_proof_views,
)
from app.kernel.compute.residual_contracts import sha256_digest
from app.kernel.compute.visual_capability_composition import VisualCapabilityFact, VisualCompositionQuestion, VisualFactType
from tests.test_capability_composition import _facts as _restart_facts
from tests.test_capability_composition import _question as _restart_question


def test_cross_modal_binds_text_and_visual_composition_receipts():
    plane = ComputePlane(root=Path("/tmp/beast-cross-modal-test-a"))
    text = plane.compose_restart_destabilization_risk(
        {"question": _restart_question().to_dict(), "facts": [fact.to_dict() for fact in _restart_facts(include_causal_rule=True)]},
        interface="test",
    )
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
    question = CrossModalCompositionQuestion(
        question_id="cross-modal:restart-risk-visual",
        text_question_digest=text["question"]["question_digest"],
        visual_question_digest=status["question"]["question_digest"],
        operator_goal="Show restart risk and visualize the dependency status.",
    )
    receipt = CrossModalCompositionPlane().compose_restart_risk_visual(
        question,
        text_receipt=text,
        visual_receipts={"status_card": status, "promoted_region_reuse": reuse, "layout_safety": layout},
    )

    assert receipt["status"] == "composed"
    assert receipt["composed"] is True
    assert receipt["text_receipt_digest"] == text["receipt_digest"]
    assert set(receipt["visual_receipt_digests"]) == {"status_card", "promoted_region_reuse", "layout_safety"}
    assert receipt["render_authority"] == "render_only"
    assert receipt["provider_calls_used"] == 0
    assert receipt["receipt_digest"].startswith("sha256:")


def test_compute_plane_cross_modal_restart_visual_records_learning(tmp_path: Path):
    plane = ComputePlane(root=tmp_path)
    result = plane.compose_cross_modal_restart_risk_visual(_cross_modal_payload())
    learning = plane.capability_learning_report(limit=20)

    assert result["status"] == "composed"
    assert result["proof_first"]["proof_graph_compiled_before_outputs"] is True
    assert result["proof_graph_digest"].startswith("sha256:")
    assert result["joined_verification"] is True
    assert result["current_claim_valid"] is True
    assert result["text_valid"] is True
    assert result["text_semantic_entailment_valid"] is True
    assert result["scene_plan_digest"].startswith("sha256:")
    assert result["rendered_artifact_digest"].startswith("sha256:")
    assert result["rendered_artifact_media_type"] == "image/svg+xml"
    assert result["visual_receipt_set_digest"].startswith("sha256:")
    assert result["scene_render_attempted"] is True
    assert result["scene_semantically_valid"] is True
    assert result["scene_render_valid"] is True
    assert result["evidence_node_id"].startswith("sha256:")
    assert learning["by_capability_type"]["cross_modal_composition"] == 1
    assert result["provider_calls_used"] == 0
    assert result["render_authority"] == "render_only"


def test_cross_modal_reports_partial_when_visual_layout_is_refuted(tmp_path: Path):
    payload = _cross_modal_payload()
    payload["visual"]["layout_safety"] = {
        "question": _layout_question().to_dict(),
        "facts": [fact.to_dict() for fact in _layout_facts(overflow=True)],
    }
    result = ComputePlane(root=tmp_path).compose_cross_modal_restart_risk_visual(payload)

    assert result["status"] == "partial"
    assert result["visual_statuses"]["layout_safety"] == "refuted"
    assert result["visual_answers"]["layout_safety"]["layout_class"] == "unsafe"
    assert result["scene_plan_semantically_valid"] is True
    assert result["scene_render_attempted"] is False
    assert result["scene_render_valid"] is False
    assert result["failure_class"] == "layout_overflow"
    assert result["provider_calls_used"] == 0


def test_cross_modal_keeps_text_and_visual_residual_scopes_separate(tmp_path: Path):
    payload = _cross_modal_payload(include_text_rule=False, include_visual_asset=False, include_visual_equivalence=False)
    seen = {"text": None, "visual": []}

    def text_worker(packet):
        seen["text"] = packet
        return {
            "destabilization_risk_class": "low",
            "causal_rationale": "Only the restart causal label was filled.",
        }

    def visual_worker(packet):
        seen["visual"].append(packet)
        if packet["residual_scope"] == "asset_gap_only":
            return {"asset_candidate_class": "equivalent", "visual_rationale": "Only visual asset class metadata was filled."}
        return {"reuse_class": "missing", "visual_rationale": "Only visual reuse class metadata was filled."}

    result = ComputePlane(root=tmp_path).compose_cross_modal_restart_risk_visual(
        payload,
        residual_worker=text_worker,
        visual_residual_worker=visual_worker,
    )

    assert result["status"] == "partial"
    assert set(result["residual_scopes"]) == {"causal_gap_only", "asset_gap_only", "visual_equivalence_gap_only"}
    assert result["proof_graph"]["claims"][0]["status"] == "unsupported"
    assert result["proof_graph"]["claims"][0]["confidence_class"] == "missing_causal_rule"
    assert result["proof_graph"]["claims"][0]["rule_ref"] == ""
    assert result["scene_render_valid"] is False
    assert result["visual_asset_resolution"] == "unresolved"
    assert result["placeholder_allowed"] is True
    assert seen["text"]["unresolved_fields"] == ["destabilization_risk_class", "causal_rationale"]
    assert {tuple(item["unresolved_fields"]) for item in seen["visual"]} == {
        ("asset_candidate_class", "visual_rationale"),
        ("reuse_class", "visual_rationale"),
    }


def test_cross_modal_stale_evidence_preserves_graph_but_blocks_current_claim(tmp_path: Path):
    payload = _cross_modal_payload()
    payload["temporal_evidence"] = {"state": "stale", "snapshot_age_seconds": 900}
    result = ComputePlane(root=tmp_path).compose_cross_modal_restart_risk_visual(payload)

    assert result["status"] == "partial"
    assert result["joined_verification"] is True
    assert result["temporal_valid"] is False
    assert result["current_claim_valid"] is False
    assert result["proof_claim_statuses"] == ("stale",)
    assert result["proof_first"]["text_frame"]["risk_class"] == "unknown_current_state"
    assert result["proof_first"]["text_frame"]["current_conclusion_allowed"] is False
    assert "stale" in result["proof_first"]["text_artifact_text"]
    assert result["visual_proof_view"]["primitives"][0]["evidence_state"] == "stale"
    assert result["visual_proof_view"]["primitives"][0]["metadata"]["visual_treatment"] == "clock_badge_and_faded_status"


def test_cross_modal_tamper_detection_rejects_modified_text_or_visual(tmp_path: Path):
    result = ComputePlane(root=tmp_path).compose_cross_modal_restart_risk_visual(_cross_modal_payload())
    graph = _proof_graph_from_result(result)
    text_view = _text_view_from_result(result)
    visual_view = _visual_view_from_result(result)
    expected_text_digest = text_view.text_output_digest
    expected_visual_digest = visual_view.rendered_visual_digest

    text_tampered = verify_cross_modal_proof_views(
        graph,
        text_view,
        visual_view,
        expected_text_output_digest=sha256_digest({"tampered": "risk label"}),
        expected_rendered_visual_digest=expected_visual_digest,
    )
    visual_tampered = verify_cross_modal_proof_views(
        graph,
        text_view,
        visual_view,
        expected_text_output_digest=expected_text_digest,
        expected_rendered_visual_digest=sha256_digest({"tampered": "green light to red light"}),
    )

    assert text_tampered["joined_verification"] is False
    assert text_tampered["failure_class"] == "text_tamper"
    assert visual_tampered["joined_verification"] is False
    assert visual_tampered["failure_class"] == "visual_tamper"


def _cross_modal_payload(*, include_text_rule=True, include_visual_asset=True, include_visual_equivalence=True):
    text_question = _restart_question()
    status_question = _status_question()
    return {
        "question": {
            "question_id": "cross-modal:restart-risk-visual",
            "text_question_digest": text_question.question_digest,
            "visual_question_digest": status_question.question_digest,
            "operator_goal": "Show restart risk and visualize the dependency status.",
            "family": "restart_risk_visual_explanation",
        },
        "text": {
            "question": text_question.to_dict(),
            "facts": [fact.to_dict() for fact in _restart_facts(include_causal_rule=include_text_rule)],
        },
        "visual": {
            "status_card": {
                "question": status_question.to_dict(),
                "facts": [fact.to_dict() for fact in _status_facts(include_asset=include_visual_asset)],
            },
            "promoted_region_reuse": {
                "question": _reuse_question().to_dict(),
                "facts": [fact.to_dict() for fact in _reuse_facts(include_equivalence=include_visual_equivalence)],
            },
            "layout_safety": {
                "question": _layout_question().to_dict(),
                "facts": [fact.to_dict() for fact in _layout_facts(overflow=False)],
            },
        },
    }


def _proof_graph_from_result(result) -> CanonicalProofGraph:
    graph = result["proof_graph"]
    return CanonicalProofGraph(
        graph_id=graph["graph_id"],
        claims=tuple(_claim_from_dict(item) for item in graph["claims"]),
        world_snapshot_digest=graph["world_snapshot_digest"],
        policy_digest=graph["policy_digest"],
        capability_fact_digests=tuple(graph["capability_fact_digests"]),
        causal_rule_digests=tuple(graph["causal_rule_digests"]),
    )


def _claim_from_dict(item) -> ProofGraphClaim:
    return ProofGraphClaim(
        claim_id=item["claim_id"],
        claim_type=item["claim_type"],
        subject=item["subject"],
        predicate=item["predicate"],
        object=item["object"],
        status=item["status"],
        confidence_class=item["confidence_class"],
        fact_refs=tuple(item["fact_refs"]),
        rule_ref=item.get("rule_ref", ""),
        policy_ref=item.get("policy_ref", ""),
        snapshot_ref=item.get("snapshot_ref", ""),
        metadata=item.get("metadata", {}),
    )


def _text_view_from_result(result) -> TextProofView:
    view = result["text_proof_view"]
    return TextProofView(
        view_id=view["view_id"],
        text_output_digest=view["text_output_digest"],
        claim_refs=tuple(view["claim_refs"]),
        renderer_id=view["renderer_id"],
    )


def _visual_view_from_result(result) -> VisualProofView:
    view = result["visual_proof_view"]
    return VisualProofView(
        view_id=view["view_id"],
        scene_capsule_digest=view["scene_capsule_digest"],
        rendered_visual_digest=view["rendered_visual_digest"],
        asset_manifest_digest=view["asset_manifest_digest"],
        layout_engine_digest=view["layout_engine_digest"],
        primitives=tuple(
            VisualProofPrimitive(
                primitive_id=item["primitive_id"],
                primitive=item["primitive"],
                claim_ref=item["claim_ref"],
                evidence_state=item["evidence_state"],
                metadata=item["metadata"],
            )
            for item in view["primitives"]
        ),
        compiler_id=view["compiler_id"],
    )


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
        _fact(VisualFactType.LAYOUT_ANCHOR, "region:status-light", "anchor", {"x": 120 if not overflow else 170, "y": 24, "width": 16, "height": 16}),
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


def _fact(fact_type: VisualFactType, subject: str, predicate: str, value, *, object: str = "") -> VisualCapabilityFact:
    return VisualCapabilityFact(
        fact_id=f"visual-fact:{fact_type.value}:{subject}:{predicate}:{object}",
        fact_type=fact_type,
        subject=subject,
        predicate=predicate,
        object=object,
        value=value,
        evidence_digest=sha256_digest({"fact": fact_type.value, "subject": subject, "predicate": predicate, "object": object, "value": value}),
    )

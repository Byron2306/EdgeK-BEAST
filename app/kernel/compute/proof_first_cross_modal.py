"""Proof-first cross-modal compiler for BEAST.

This is the architectural inversion missing from the first cross-modal proof:
compile a canonical proof graph from verified facts first, then independently
realize text and visual artifacts from that graph.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Mapping

from .proof_graph import CanonicalProofGraph, ProofClaimStatus, ProofGraphClaim, TextProofView, VisualProofPrimitive, VisualProofView
from .residual_contracts import canonical_json, sha256_digest


@dataclass(frozen=True, slots=True)
class ProofTextFrame:
    claim_ref: str
    epistemic_status: str
    current_conclusion_allowed: bool
    risk_class: str
    reason: str
    previous_snapshot_risk_class: str = ""
    residual_suggestion_available: bool = False
    support_limit: str = ""
    renderer_id: str = "beast.proof-first.text-frame.v1"

    def __post_init__(self) -> None:
        if not self.claim_ref.strip() or not self.epistemic_status.strip() or not self.risk_class.strip():
            raise ValueError("proof text frame requires claim_ref, epistemic_status, and risk_class")
        canonical_json(asdict(self))

    @property
    def frame_digest(self) -> str:
        return sha256_digest(self)

    def to_dict(self) -> dict[str, Any]:
        return {**asdict(self), "frame_digest": self.frame_digest}


@dataclass(frozen=True, slots=True)
class ProofScenePrimitive:
    primitive_id: str
    primitive: str
    claim_refs: tuple[str, ...]
    state: str
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.primitive_id.strip() or not self.primitive.strip() or not self.claim_refs:
            raise ValueError("scene primitive requires id, primitive, and claim_refs")
        canonical_json(self.metadata)

    @property
    def primitive_digest(self) -> str:
        return sha256_digest(self)

    def to_dict(self) -> dict[str, Any]:
        return {**asdict(self), "primitive_digest": self.primitive_digest}


@dataclass(frozen=True, slots=True)
class ProofScenePlan:
    scene_plan_id: str
    proof_graph_digest: str
    family: str
    canvas: Mapping[str, int]
    primitives: tuple[ProofScenePrimitive, ...]
    visual_receipt_set_digest: str
    asset_resolution: str = "resolved"
    placeholder_allowed: bool = False
    layout_overflow: bool = False
    compiler_id: str = "beast.proof-first.scene-plan-compiler.v1"

    def __post_init__(self) -> None:
        if not self.scene_plan_id.strip() or not self.family.strip() or not self.primitives:
            raise ValueError("scene plan requires id, family, and primitives")
        canonical_json(self.canvas)
        canonical_json(self.asset_resolution)

    @property
    def scene_plan_digest(self) -> str:
        return sha256_digest(self)

    def to_dict(self) -> dict[str, Any]:
        return {**asdict(self), "primitives": tuple(item.to_dict() for item in self.primitives), "scene_plan_digest": self.scene_plan_digest}


def compile_restart_risk_proof_first(
    payload: Mapping[str, Any],
    *,
    visual_receipt_set_digest: str | None = None,
    residual_suggestion_available: bool = False,
) -> dict[str, Any]:
    text_payload = payload.get("text") if isinstance(payload.get("text"), Mapping) else {}
    text_question = text_payload.get("question") if isinstance(text_payload.get("question"), Mapping) else {}
    text_facts = tuple(item for item in (text_payload.get("facts") or ()) if isinstance(item, Mapping))
    visual_payload = payload.get("visual") if isinstance(payload.get("visual"), Mapping) else {}
    temporal_evidence = payload.get("temporal_evidence") if isinstance(payload.get("temporal_evidence"), Mapping) else {}
    source = str(text_question.get("source_service") or "source_service")
    target = str(text_question.get("target_service") or "target_service")
    question_digest = str(text_question.get("question_digest") or sha256_digest(text_question or {"source": source, "target": target}))
    fact_digests = tuple(sorted(_fact_digest(fact) for fact in text_facts))
    rule_ref = _component_digest(text_facts, "restart_causal_rule")
    policy_ref = _component_digest(text_facts, "restart_policy")
    evidence_ref = _component_digest(text_facts, "current_evidence")
    dependency_ref = _component_digest(text_facts, "dependency_topology")
    stale = str(temporal_evidence.get("state") or "").casefold() == "stale"
    has_dependency = bool(dependency_ref)
    if stale:
        claim_status = ProofClaimStatus.STALE
        confidence_class = "stale_previous_snapshot"
    elif not has_dependency:
        claim_status = ProofClaimStatus.REFUTED
        confidence_class = "topology_refuted"
    elif not rule_ref:
        claim_status = ProofClaimStatus.RESIDUAL_SUPPORTED if residual_suggestion_available else ProofClaimStatus.UNSUPPORTED
        confidence_class = "bounded_residual_inference" if residual_suggestion_available else "missing_causal_rule"
    else:
        claim_status = ProofClaimStatus.SUPPORTED
        confidence_class = "rule_proven"
    claim_id = "claim:restart-risk:" + question_digest.removeprefix("sha256:")[:16]
    graph = CanonicalProofGraph(
        graph_id="proof-first:restart-risk:" + question_digest.removeprefix("sha256:")[:16],
        claims=(
            ProofGraphClaim(
                claim_id=claim_id,
                claim_type="conditional_causal",
                subject=source,
                predicate="restart_destabilization_risk",
                object=target,
                status=claim_status,
                confidence_class=confidence_class,
                fact_refs=fact_digests or (sha256_digest({"empty_fact_set": question_digest}),),
                rule_ref=rule_ref,
                policy_ref=policy_ref,
                snapshot_ref=evidence_ref or sha256_digest({"temporal_evidence": temporal_evidence}),
                metadata={
                    "compiled_before_outputs": True,
                    "dependency_ref": dependency_ref,
                    "residual_suggestion_available": residual_suggestion_available,
                    "support_limit": "causal classification only" if residual_suggestion_available and not rule_ref else "",
                },
            ),
        ),
        world_snapshot_digest=sha256_digest({"fact_digests": fact_digests, "temporal_evidence": temporal_evidence}),
        policy_digest=sha256_digest({"policy": "proof-first-cross-modal.v1", "family": "restart_risk_visual_explanation"}),
        capability_fact_digests=fact_digests,
        causal_rule_digests=(rule_ref,) if rule_ref else (),
    )
    text_frame = realize_restart_risk_text_frame(graph)
    text_bytes = render_text_frame(text_frame).encode("utf-8")
    text_artifact_digest = "sha256:" + __import__("hashlib").sha256(text_bytes).hexdigest()
    scene_plan = compile_restart_risk_scene_plan(
        graph,
        visual_payload=visual_payload,
        visual_receipt_set_digest=visual_receipt_set_digest or sha256_digest({"visual_receipts": "not-yet-bound"}),
    )
    rendered = render_scene_plan_svg(scene_plan)
    rendered_artifact_digest = "sha256:" + __import__("hashlib").sha256(rendered).hexdigest()
    text_view = TextProofView(
        view_id="proof-first-text-view:" + text_artifact_digest.removeprefix("sha256:")[:16],
        text_output_digest=text_artifact_digest,
        claim_refs=(claim_id,),
        renderer_id="beast.proof-first.text-lexicalizer.v1",
    )
    visual_view = VisualProofView(
        view_id="proof-first-visual-view:" + scene_plan.scene_plan_digest.removeprefix("sha256:")[:16],
        scene_capsule_digest=scene_plan.scene_plan_digest,
        rendered_visual_digest=rendered_artifact_digest,
        asset_manifest_digest=sha256_digest({"asset_resolution": scene_plan.asset_resolution, "placeholder_allowed": scene_plan.placeholder_allowed}),
        layout_engine_digest=sha256_digest({"engine": scene_plan.compiler_id}),
        primitives=tuple(
            VisualProofPrimitive(
                primitive_id=primitive.primitive_id,
                primitive=primitive.primitive,
                claim_ref=primitive.claim_refs[0],
                evidence_state=claim_status,
                metadata={**dict(primitive.metadata), "proof_first": True},
            )
            for primitive in scene_plan.primitives
        ),
        compiler_id=scene_plan.compiler_id,
    )
    text_entailment = verify_text_frame_entails_claim(graph, text_frame)
    scene_semantic = verify_scene_plan_entails_graph(graph, scene_plan)
    scene_render_valid = bool(rendered) and not scene_plan.layout_overflow and scene_plan.asset_resolution == "resolved"
    failure_class = ""
    if scene_plan.layout_overflow:
        failure_class = "layout_overflow"
    elif scene_plan.asset_resolution != "resolved":
        failure_class = "visual_asset_unresolved"
    elif not text_entailment:
        failure_class = "text_claim_semantic_mismatch"
    return {
        "beast_object_type": "proof_first_cross_modal_realization",
        "version": "1.0",
        "execution_order": (
            "verified_facts_rules_policies_temporal_evidence",
            "canonical_proof_graph",
            "independent_text_frame",
            "independent_scene_plan",
            "actual_text_artifact_and_svg_artifact",
            "joined_custody_verification",
        ),
        "proof_graph": graph,
        "text_frame": text_frame.to_dict(),
        "text_artifact_text": text_bytes.decode("utf-8"),
        "text_artifact_digest": text_artifact_digest,
        "scene_plan": scene_plan.to_dict(),
        "scene_plan_digest": scene_plan.scene_plan_digest,
        "rendered_artifact_bytes": rendered,
        "rendered_artifact_digest": rendered_artifact_digest,
        "rendered_artifact_media_type": "image/svg+xml",
        "rendered_artifact_dimensions": dict(scene_plan.canvas),
        "text_view": text_view,
        "visual_view": visual_view,
        "proof_graph_compiled_before_outputs": True,
        "text_semantic_entailment_valid": text_entailment,
        "scene_plan_semantically_valid": scene_semantic,
        "scene_render_attempted": bool(rendered) and not scene_plan.layout_overflow,
        "scene_render_valid": scene_render_valid,
        "visual_asset_resolution": scene_plan.asset_resolution,
        "placeholder_allowed": scene_plan.placeholder_allowed,
        "failure_class": failure_class,
    }


def realize_restart_risk_text_frame(proof_graph: CanonicalProofGraph) -> ProofTextFrame:
    claim = proof_graph.claims[0]
    if claim.status is ProofClaimStatus.STALE:
        return ProofTextFrame(
            claim_ref=claim.claim_id,
            epistemic_status="stale",
            current_conclusion_allowed=False,
            risk_class="unknown_current_state",
            previous_snapshot_risk_class="low_if_previous_snapshot_still_applied",
            reason="The verified topology and restart rule suggest low risk under the previous snapshot, but current restart safety cannot be established because the health evidence is stale.",
        )
    if claim.status is ProofClaimStatus.UNSUPPORTED:
        return ProofTextFrame(
            claim_ref=claim.claim_id,
            epistemic_status="unsupported",
            current_conclusion_allowed=False,
            risk_class="unknown_causal_rule_gap",
            reason="Current causal restart safety cannot be established because the verified fact set lacks an explicit restart destabilization causal rule.",
        )
    if claim.status is ProofClaimStatus.RESIDUAL_SUPPORTED:
        return ProofTextFrame(
            claim_ref=claim.claim_id,
            epistemic_status="residual_supported",
            current_conclusion_allowed=False,
            risk_class="advisory_low",
            reason="A bounded residual classifier suggested low risk, but no verified causal rule exists, so BEAST cannot authorize a current causal conclusion.",
            residual_suggestion_available=True,
            support_limit="causal classification only",
        )
    if claim.status is ProofClaimStatus.REFUTED:
        return ProofTextFrame(
            claim_ref=claim.claim_id,
            epistemic_status="refuted",
            current_conclusion_allowed=True,
            risk_class="low_no_dependency_path",
            reason="No verified dependency evidence supports a path from the source service to the target service.",
        )
    return ProofTextFrame(
        claim_ref=claim.claim_id,
        epistemic_status="supported",
        current_conclusion_allowed=True,
        risk_class="low",
        reason="Verified dependency topology, restart policy, current evidence, and causal rule support a compatible rolling restart conclusion.",
    )


def render_text_frame(frame: ProofTextFrame) -> str:
    return frame.reason


def compile_restart_risk_scene_plan(
    proof_graph: CanonicalProofGraph,
    *,
    visual_payload: Mapping[str, Any],
    visual_receipt_set_digest: str,
) -> ProofScenePlan:
    claim = proof_graph.claims[0]
    layout_facts = _visual_facts(visual_payload, "layout_safety")
    status_facts = _visual_facts(visual_payload, "status_card")
    canvas = _canvas(layout_facts)
    anchor = _anchor(layout_facts) or _anchor(status_facts)
    layout_overflow = bool(anchor and (anchor["x"] + anchor["width"] > canvas["width"] or anchor["y"] + anchor["height"] > canvas["height"]))
    asset_resolution = "resolved" if _has_fact_type(status_facts, "promoted_visual_asset") else "unresolved"
    placeholder_allowed = asset_resolution != "resolved"
    state = claim.status.value
    primitives = (
        ProofScenePrimitive("primitive:risk-edge", "risk_edge", (claim.claim_id,), state, {"visual_treatment": _visual_treatment(claim.status)}),
        ProofScenePrimitive("primitive:source-service-node", "service_node", (claim.claim_id,), state, {"role": "source", "service": claim.subject}),
        ProofScenePrimitive("primitive:target-service-node", "service_node", (claim.claim_id,), state, {"role": "target", "service": claim.object}),
        ProofScenePrimitive("primitive:status-badge", "status_badge", (claim.claim_id,), state, {"asset_resolution": asset_resolution}),
    )
    return ProofScenePlan(
        scene_plan_id="scene-plan:restart-risk:" + proof_graph.proof_graph_digest.removeprefix("sha256:")[:16],
        proof_graph_digest=proof_graph.proof_graph_digest,
        family="restart_risk_visual_explanation",
        canvas=canvas,
        primitives=primitives,
        visual_receipt_set_digest=visual_receipt_set_digest,
        asset_resolution=asset_resolution,
        placeholder_allowed=placeholder_allowed,
        layout_overflow=layout_overflow,
    )


def render_scene_plan_svg(scene_plan: ProofScenePlan) -> bytes:
    if scene_plan.layout_overflow:
        return b""
    width = int(scene_plan.canvas.get("width") or 180)
    height = int(scene_plan.canvas.get("height") or 100)
    badge = "?" if scene_plan.asset_resolution != "resolved" else "●"
    color = "#23dc48"
    if any(primitive.state == "stale" for primitive in scene_plan.primitives):
        color = "#e8c547"
    if any(primitive.state == "unsupported" for primitive in scene_plan.primitives):
        color = "#e8c547"
    if any(primitive.state == "refuted" for primitive in scene_plan.primitives):
        color = "#dc3a31"
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">'
        '<rect width="100%" height="100%" fill="#07110d"/>'
        '<circle cx="42" cy="50" r="16" fill="#123d2a" stroke="#8ff0aa"/>'
        '<circle cx="138" cy="50" r="16" fill="#123d2a" stroke="#8ff0aa"/>'
        f'<path d="M58 50 L122 50" stroke="{color}" stroke-width="4" stroke-dasharray="{"6 4" if scene_plan.asset_resolution != "resolved" else "0"}"/>'
        f'<text x="36" y="55" font-size="14" fill="{color}">{badge}</text>'
        '</svg>'
    )
    return svg.encode("utf-8")


def verify_text_frame_entails_claim(proof_graph: CanonicalProofGraph, frame: ProofTextFrame) -> bool:
    claim = proof_graph.claim(frame.claim_ref)
    if frame.epistemic_status != claim.status.value:
        return False
    if claim.status is ProofClaimStatus.STALE:
        return frame.current_conclusion_allowed is False and frame.risk_class == "unknown_current_state" and "stale" in frame.reason.casefold()
    if claim.status is ProofClaimStatus.UNSUPPORTED:
        return frame.current_conclusion_allowed is False and "rule" in frame.reason.casefold()
    if claim.status is ProofClaimStatus.RESIDUAL_SUPPORTED:
        return frame.current_conclusion_allowed is False and frame.residual_suggestion_available and "no verified causal rule" in frame.reason.casefold()
    if claim.status is ProofClaimStatus.SUPPORTED:
        return bool(claim.rule_ref) and frame.current_conclusion_allowed is True and frame.risk_class in {"low", "elevated"}
    return frame.epistemic_status == "refuted"


def verify_scene_plan_entails_graph(proof_graph: CanonicalProofGraph, scene_plan: ProofScenePlan) -> bool:
    claim_ids = set(proof_graph.claim_ids)
    return all(set(primitive.claim_refs).issubset(claim_ids) for primitive in scene_plan.primitives)


def _fact_digest(fact: Mapping[str, Any]) -> str:
    digest = str(fact.get("fact_digest") or "")
    return digest if digest.startswith("sha256:") else sha256_digest(fact)


def _component_digest(facts: tuple[Mapping[str, Any], ...], fact_type: str) -> str:
    for fact in facts:
        if str(fact.get("fact_type") or "") == fact_type:
            return _fact_digest(fact)
    return ""


def _visual_facts(visual_payload: Mapping[str, Any], key: str) -> tuple[Mapping[str, Any], ...]:
    payload = visual_payload.get(key) if isinstance(visual_payload.get(key), Mapping) else {}
    return tuple(item for item in (payload.get("facts") or ()) if isinstance(item, Mapping))


def _has_fact_type(facts: tuple[Mapping[str, Any], ...], fact_type: str) -> bool:
    return any(str(fact.get("fact_type") or "") == fact_type for fact in facts)


def _canvas(facts: tuple[Mapping[str, Any], ...]) -> dict[str, int]:
    for fact in facts:
        if str(fact.get("fact_type") or "") == "canvas_contract":
            value = fact.get("value") if isinstance(fact.get("value"), Mapping) else {}
            return {"width": int(value.get("width") or 180), "height": int(value.get("height") or 100)}
    return {"width": 180, "height": 100}


def _anchor(facts: tuple[Mapping[str, Any], ...]) -> dict[str, int] | None:
    for fact in facts:
        if str(fact.get("fact_type") or "") == "layout_anchor":
            value = fact.get("value") if isinstance(fact.get("value"), Mapping) else {}
            return {
                "x": int(value.get("x") or 0),
                "y": int(value.get("y") or 0),
                "width": int(value.get("width") or 0),
                "height": int(value.get("height") or 0),
            }
    return None


def _visual_treatment(status: ProofClaimStatus) -> str:
    return {
        ProofClaimStatus.SUPPORTED: "solid_edge_with_rule_badge",
        ProofClaimStatus.RESIDUAL_SUPPORTED: "dashed_residual_advisory_edge",
        ProofClaimStatus.UNSUPPORTED: "dashed_interruption_with_explicit_unsupported_label",
        ProofClaimStatus.REFUTED: "blocked_or_crossed_relation",
        ProofClaimStatus.STALE: "clock_badge_and_faded_status",
    }[status]

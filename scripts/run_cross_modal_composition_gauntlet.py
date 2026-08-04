#!/usr/bin/env python3
"""Run BEAST cross-modal capability-composition gauntlet receipts."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.kernel.compute.capability_composition import CapabilityFactType, CompositionQuestion, LearnedCapabilityFact
from app.kernel.compute.compute_plane import ComputePlane
from app.kernel.compute.proof_graph import (
    CanonicalProofGraph,
    ProofGraphClaim,
    TextProofView,
    VisualProofPrimitive,
    VisualProofView,
    verify_cross_modal_proof_views,
)
from app.kernel.compute.residual_contracts import sha256_digest, utc_now_iso
from app.kernel.compute.visual_capability_composition import VisualCapabilityFact, VisualCompositionQuestion, VisualFactType


def run_cross_modal_composition_gauntlet(
    *,
    state_root: str | Path = REPO_ROOT / ".beast" / "state" / "cross_modal_composition_gauntlet",
    evidence_root: str | Path = REPO_ROOT / "evidence" / "cross-modal-composition",
    run_id: str | None = None,
) -> dict[str, Any]:
    run_id = run_id or utc_now_iso().replace(":", "").replace("+", "z")
    evidence_path = Path(evidence_root)
    evidence_path.mkdir(parents=True, exist_ok=True)
    plane = ComputePlane(root=Path(state_root))

    composed = plane.compose_cross_modal_restart_risk_visual(_payload())
    visual_refuted = plane.compose_cross_modal_restart_risk_visual(_payload(layout_overflow=True))
    stale_evidence = plane.compose_cross_modal_restart_risk_visual(
        {**_payload(), "temporal_evidence": {"state": "stale", "snapshot_age_seconds": 900}},
    )
    residual_seen = {"text": None, "visual": []}

    def text_worker(packet: Mapping[str, Any]) -> Mapping[str, Any]:
        residual_seen["text"] = dict(packet)
        return {
            "destabilization_risk_class": "low",
            "causal_rationale": "Residual filled only the declared restart causal label.",
        }

    def visual_worker(packet: Mapping[str, Any]) -> Mapping[str, Any]:
        residual_seen["visual"].append(dict(packet))
        if packet["residual_scope"] == "asset_gap_only":
            return {"asset_candidate_class": "equivalent", "visual_rationale": "Residual filled only asset class metadata."}
        return {"reuse_class": "missing", "visual_rationale": "Residual filled only visual reuse class metadata."}

    residual_composed = plane.compose_cross_modal_restart_risk_visual(
        _payload(include_text_rule=False, include_visual_asset=False, include_visual_equivalence=False),
        residual_worker=text_worker,
        visual_residual_worker=visual_worker,
    )
    hostile_residuals = _run_hostile_residual_attacks(Path(state_root) / "hostile_residuals")
    text_tamper = _tamper_verification(composed, tamper_text=True)
    visual_tamper = _tamper_verification(composed, tamper_visual=True)

    cases = {
        "restart_visual_composed": composed,
        "restart_visual_layout_refuted": visual_refuted,
        "restart_visual_stale_evidence": stale_evidence,
        "restart_visual_residual_scoped": residual_composed,
    }
    report = {
        "beast_object_type": "cross_modal_composition_gauntlet_receipt",
        "version": "2.0",
        "run_id": run_id,
        "observed_at": utc_now_iso(),
        "claim_boundary": (
            "Cross-modal composition gauntlet: proves a restart-risk operational answer and render-only "
            "visual explanation can be joined under one canonical proof graph. Text and visual views are "
            "sibling expressions of typed evidence-bound claims; stale evidence blocks current-claim validity; "
            "tampering either modality fails joined verification; residual routing remains limited to declared "
            "causal/visual metadata fields."
        ),
        "cases": cases,
        "scorecard": {
            "case_count": len(cases),
            "cross_modal_composed": sum(1 for item in cases.values() if item["status"] == "composed"),
            "cross_modal_partial": sum(1 for item in cases.values() if item["status"] == "partial"),
            "render_only_cases": sum(1 for item in cases.values() if item["render_authority"] == "render_only"),
            "joined_verifications": sum(1 for item in cases.values() if item.get("joined_verification") is True),
            "current_claim_invalid_due_to_stale": sum(1 for item in cases.values() if item.get("temporal_valid") is False and item.get("current_claim_valid") is False),
            "provider_calls_used": sum(int(item.get("provider_calls_used", 0)) for item in cases.values()),
            "joined_visual_receipts": sum(len(item.get("visual_receipt_digests", {})) for item in cases.values()),
            "layout_refutations": sum(1 for item in cases.values() if item.get("visual_statuses", {}).get("layout_safety") == "refuted"),
            "residual_scopes": tuple(sorted({scope for item in cases.values() for scope in item.get("residual_scopes", ())})),
            "text_residual_unresolved_fields": tuple((residual_seen.get("text") or {}).get("unresolved_fields") or ()),
            "visual_residual_unresolved_fields": tuple(tuple(item.get("unresolved_fields") or ()) for item in residual_seen["visual"]),
            "text_tamper_rejected": int(text_tamper["joined_verification"] is False and text_tamper["failure_class"] == "text_tamper"),
            "visual_tamper_rejected": int(visual_tamper["joined_verification"] is False and visual_tamper["failure_class"] == "visual_tamper"),
            "hostile_residual_attempts": hostile_residuals["attempts"],
            "hostile_residuals_rejected": hostile_residuals["rejected"],
            "residual_scope_violations": hostile_residuals["admitted"],
            "proof_graphs_compiled_before_outputs": sum(1 for item in cases.values() if item.get("proof_first", {}).get("proof_graph_compiled_before_outputs") is True),
            "text_semantic_entailment_passes": sum(1 for item in cases.values() if item.get("text_semantic_entailment_valid") is True),
            "visual_primitive_entailment_passes": sum(1 for item in cases.values() if item.get("scene_plan_semantically_valid") is True),
            "actual_text_artifacts_bound": sum(1 for item in cases.values() if str(item.get("proof_first", {}).get("text_artifact_digest") or "").startswith("sha256:")),
            "actual_visual_artifacts_bound": sum(1 for item in cases.values() if str(item.get("rendered_artifact_digest") or "").startswith("sha256:")),
            "layout_failures_reported_as_renders": sum(1 for item in cases.values() if item.get("failure_class") == "layout_overflow" and item.get("scene_render_valid") is True),
            "stale_claims_presented_as_current": sum(1 for item in cases.values() if "stale" in tuple(item.get("proof_claim_statuses") or ()) and item.get("current_claim_valid") is True),
            "residual_claims_called_rule_proven": sum(1 for item in cases.values() for claim in item.get("proof_graph", {}).get("claims", ()) if claim.get("rule_ref") == "" and claim.get("confidence_class") == "rule_proven"),
        },
        "hostile_residual_attacks": hostile_residuals,
        "tamper_verification": {
            "text_tamper": text_tamper,
            "visual_tamper": visual_tamper,
        },
        "capability_learning": plane.capability_learning_report(limit=100),
    }
    report["receipt_digest"] = sha256_digest(report)
    json_path = evidence_path / f"{run_id}.json"
    md_path = evidence_path / f"{run_id}.md"
    json_path.write_text(json.dumps(report, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(_markdown(report), encoding="utf-8")
    (evidence_path / "latest.json").write_text(json.dumps(report, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    (evidence_path / "latest.md").write_text(_markdown(report), encoding="utf-8")
    report["evidence_paths"] = {
        "json": str(json_path),
        "markdown": str(md_path),
        "latest_json": str(evidence_path / "latest.json"),
        "latest_markdown": str(evidence_path / "latest.md"),
    }
    return report


def _run_hostile_residual_attacks(state_root: Path) -> dict[str, Any]:
    attacks: list[dict[str, Any]] = []

    def record(case_id: str, fn) -> None:
        try:
            fn()
        except Exception as exc:
            attacks.append({"case_id": case_id, "rejected": True, "error": f"{type(exc).__name__}: {exc}"})
        else:
            attacks.append({"case_id": case_id, "rejected": False, "error": ""})

    record(
        "hostile_text_residual_forbidden_action_and_dependency",
        lambda: ComputePlane(root=state_root / "text").compose_restart_destabilization_risk(
            {"question": _text_question().to_dict(), "facts": [fact.to_dict() for fact in _text_facts(include_causal_rule=False)]},
            residual_worker=lambda _packet: {
                "destabilization_risk_class": "low",
                "causal_rationale": "Looks safe.",
                "final_answer": "Restart BEAST now.",
                "new_dependency": "invented-service",
                "provider_prompt": "generate the whole diagram",
            },
            interface="hostile-residual.text",
        ),
    )
    record(
        "hostile_visual_asset_residual_forbidden_asset_and_prompt",
        lambda: ComputePlane(root=state_root / "visual_asset").compose_visual_status_card(
            {"question": _status_question().to_dict(), "facts": [fact.to_dict() for fact in _status_facts(include_asset=False)]},
            residual_worker=lambda _packet: {
                "asset_candidate_class": "equivalent",
                "visual_rationale": "Looks close.",
                "new_asset_id": "invented.asset",
                "provider_prompt": "generate the whole card",
            },
            interface="hostile-residual.visual-asset",
        ),
    )
    record(
        "hostile_visual_reuse_residual_forbidden_pixels",
        lambda: ComputePlane(root=state_root / "visual_reuse").compose_visual_promoted_region_reuse(
            {"question": _reuse_question().to_dict(), "facts": [fact.to_dict() for fact in _reuse_facts(include_equivalence=False)]},
            residual_worker=lambda _packet: {
                "reuse_class": "equivalent",
                "visual_rationale": "Looks reusable.",
                "new_pixels": "base64:AAAA",
            },
            interface="hostile-residual.visual-reuse",
        ),
    )
    return {
        "attempts": len(attacks),
        "rejected": sum(1 for item in attacks if item["rejected"]),
        "admitted": sum(1 for item in attacks if not item["rejected"]),
        "attacks": tuple(attacks),
    }


def _payload(
    *,
    include_text_rule: bool = True,
    include_visual_asset: bool = True,
    include_visual_equivalence: bool = True,
    layout_overflow: bool = False,
) -> dict[str, Any]:
    text_question = _text_question()
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
            "facts": [fact.to_dict() for fact in _text_facts(include_causal_rule=include_text_rule)],
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
                "facts": [fact.to_dict() for fact in _layout_facts(overflow=layout_overflow)],
            },
        },
    }


def _text_question() -> CompositionQuestion:
    return CompositionQuestion(
        question_id="question:restart-beast-affects-commons",
        source_service="beast",
        target_service="commons",
        utterance="Could restarting BEAST destabilize Commons?",
    )


def _text_facts(*, include_causal_rule: bool) -> tuple[LearnedCapabilityFact, ...]:
    facts = [
        _text_fact(CapabilityFactType.SERVICE_HEALTH, "beast", "health", {"state": "healthy"}),
        _text_fact(CapabilityFactType.SERVICE_HEALTH, "commons", "health", {"state": "healthy"}),
        _text_fact(CapabilityFactType.DEPENDENCY_TOPOLOGY, "commons", "depends_on", {"relation": "depends_on"}, object="beast"),
        _text_fact(CapabilityFactType.RESTART_POLICY, "beast", "restart_policy", {"mode": "rolling_with_healthcheck"}),
        _text_fact(CapabilityFactType.CURRENT_EVIDENCE, "runtime", "current_evidence", {"state": "stable", "restart_count": 0}),
    ]
    if include_causal_rule:
        facts.append(_text_fact(CapabilityFactType.RESTART_CAUSAL_RULE, "service_restart", "causal_rule", {"rule": "rolling_restart_compatible_with_dependents"}, object="dependent_service"))
    return tuple(facts)


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
        _visual_fact(VisualFactType.SCENE_CAPSULE, "scene:beast-status", "capsule", {"capsule_digest": sha256_digest("scene-capsule")}),
        _visual_fact(VisualFactType.ASSET_MANIFEST, "scene:beast-status", "manifest", {"manifest_digest": sha256_digest("manifest")}),
        _visual_fact(VisualFactType.VISUAL_INTENT, "region:status-light", "intent", {"color": "green", "object": "status_light"}),
        _visual_fact(VisualFactType.LAYOUT_ANCHOR, "region:status-light", "anchor", {"anchor": "top_right", "x": 120, "y": 24, "width": 16, "height": 16}),
    ]
    if include_asset:
        facts.append(_promoted_asset())
    return tuple(facts)


def _reuse_facts(*, include_equivalence: bool) -> tuple[VisualCapabilityFact, ...]:
    facts = [
        _visual_fact(VisualFactType.SCENE_CAPSULE, "scene:beast-status", "capsule", {"capsule_digest": sha256_digest("scene-capsule")}),
        _visual_fact(VisualFactType.REGION_MASK, "region:status-light", "mask", {"x": 120, "y": 24, "width": 16, "height": 16}),
        _visual_fact(VisualFactType.VISUAL_INTENT, "region:status-light", "intent", {"color": "green", "object": "status_light"}),
        _promoted_asset(),
        _visual_fact(VisualFactType.QUALITY_RECEIPT, "region:status-light", "quality", {"passed": True}),
        _visual_fact(VisualFactType.INTENT_RECEIPT, "region:status-light", "intent_receipt", {"passed": True}),
        _visual_fact(VisualFactType.PERCEPTUAL_RECEIPT, "region:status-light", "perceptual", {"passed": True, "center_luma_lift": 0.42}),
    ]
    if include_equivalence:
        facts.extend([
            _visual_fact(VisualFactType.FEATURE_EMBEDDING, "region:status-light", "embedding", {"bins": [1, 4, 2, 8], "source": "visual_feature_embedding"}),
            _visual_fact(VisualFactType.EQUIVALENCE_RECEIPT, "region:status-light", "equivalence", {"equivalent": True, "distance": 0.03}),
        ])
    return tuple(facts)


def _layout_facts(*, overflow: bool) -> tuple[VisualCapabilityFact, ...]:
    return (
        _visual_fact(VisualFactType.CANVAS_CONTRACT, "scene:beast-status", "canvas", {"width": 180, "height": 100}),
        _visual_fact(VisualFactType.LAYOUT_ANCHOR, "region:status-light", "anchor", {"x": 120 if not overflow else 170, "y": 24, "width": 16, "height": 16}),
        _promoted_asset(),
    )


def _promoted_asset() -> VisualCapabilityFact:
    return _visual_fact(
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


def _text_fact(fact_type: CapabilityFactType, subject: str, predicate: str, value: Any, *, object: str = "") -> LearnedCapabilityFact:
    return LearnedCapabilityFact(
        fact_id=f"fact:{fact_type.value}:{subject}:{predicate}:{object}",
        fact_type=fact_type,
        subject=subject,
        predicate=predicate,
        object=object,
        value=value,
        evidence_digest=sha256_digest({"fact": fact_type.value, "subject": subject, "predicate": predicate, "object": object, "value": value}),
    )


def _visual_fact(fact_type: VisualFactType, subject: str, predicate: str, value: Any, *, object: str = "") -> VisualCapabilityFact:
    return VisualCapabilityFact(
        fact_id=f"visual-fact:{fact_type.value}:{subject}:{predicate}:{object}",
        fact_type=fact_type,
        subject=subject,
        predicate=predicate,
        object=object,
        value=value,
        evidence_digest=sha256_digest({"fact": fact_type.value, "subject": subject, "predicate": predicate, "object": object, "value": value}),
    )


def _tamper_verification(result: Mapping[str, Any], *, tamper_text: bool = False, tamper_visual: bool = False) -> dict[str, Any]:
    graph = _proof_graph_from_result(result)
    text_view = _text_view_from_result(result)
    visual_view = _visual_view_from_result(result)
    return verify_cross_modal_proof_views(
        graph,
        text_view,
        visual_view,
        expected_text_output_digest=sha256_digest({"tampered": "text-risk-label"}) if tamper_text else text_view.text_output_digest,
        expected_rendered_visual_digest=sha256_digest({"tampered": "visual-risk-edge"}) if tamper_visual else visual_view.rendered_visual_digest,
    )


def _proof_graph_from_result(result: Mapping[str, Any]) -> CanonicalProofGraph:
    graph = dict(result["proof_graph"])
    return CanonicalProofGraph(
        graph_id=str(graph["graph_id"]),
        claims=tuple(_claim_from_dict(item) for item in graph["claims"]),
        world_snapshot_digest=str(graph["world_snapshot_digest"]),
        policy_digest=str(graph["policy_digest"]),
        capability_fact_digests=tuple(graph["capability_fact_digests"]),
        causal_rule_digests=tuple(graph["causal_rule_digests"]),
    )


def _claim_from_dict(item: Mapping[str, Any]) -> ProofGraphClaim:
    return ProofGraphClaim(
        claim_id=str(item["claim_id"]),
        claim_type=str(item["claim_type"]),
        subject=str(item["subject"]),
        predicate=str(item["predicate"]),
        object=str(item["object"]),
        status=str(item["status"]),
        confidence_class=str(item["confidence_class"]),
        fact_refs=tuple(item["fact_refs"]),
        rule_ref=str(item.get("rule_ref", "")),
        policy_ref=str(item.get("policy_ref", "")),
        snapshot_ref=str(item.get("snapshot_ref", "")),
        metadata=dict(item.get("metadata", {})),
    )


def _text_view_from_result(result: Mapping[str, Any]) -> TextProofView:
    view = dict(result["text_proof_view"])
    return TextProofView(
        view_id=str(view["view_id"]),
        text_output_digest=str(view["text_output_digest"]),
        claim_refs=tuple(view["claim_refs"]),
        renderer_id=str(view["renderer_id"]),
    )


def _visual_view_from_result(result: Mapping[str, Any]) -> VisualProofView:
    view = dict(result["visual_proof_view"])
    return VisualProofView(
        view_id=str(view["view_id"]),
        scene_capsule_digest=str(view["scene_capsule_digest"]),
        rendered_visual_digest=str(view["rendered_visual_digest"]),
        asset_manifest_digest=str(view["asset_manifest_digest"]),
        layout_engine_digest=str(view["layout_engine_digest"]),
        primitives=tuple(
            VisualProofPrimitive(
                primitive_id=str(item["primitive_id"]),
                primitive=str(item["primitive"]),
                claim_ref=str(item["claim_ref"]),
                evidence_state=str(item["evidence_state"]),
                metadata=dict(item.get("metadata", {})),
            )
            for item in view["primitives"]
        ),
        compiler_id=str(view["compiler_id"]),
    )


def _markdown(report: Mapping[str, Any]) -> str:
    scorecard = report.get("scorecard") if isinstance(report.get("scorecard"), Mapping) else {}
    return "\n".join([
        f"# BEAST cross-modal composition gauntlet — {report['run_id']}",
        "",
        f"- Receipt digest: `{report['receipt_digest']}`",
        f"- Cases: `{scorecard.get('case_count', 0)}`",
        f"- Cross-modal composed: `{scorecard.get('cross_modal_composed', 0)}`",
        f"- Cross-modal partial: `{scorecard.get('cross_modal_partial', 0)}`",
        f"- Render-only cases: `{scorecard.get('render_only_cases', 0)}`",
        f"- Joined verifications: `{scorecard.get('joined_verifications', 0)}`",
        f"- Stale current-claim invalidations: `{scorecard.get('current_claim_invalid_due_to_stale', 0)}`",
        f"- Joined visual receipts: `{scorecard.get('joined_visual_receipts', 0)}`",
        f"- Layout refutations: `{scorecard.get('layout_refutations', 0)}`",
        f"- Residual scopes: `{scorecard.get('residual_scopes', ())}`",
        f"- Text residual unresolved fields: `{scorecard.get('text_residual_unresolved_fields', ())}`",
        f"- Visual residual unresolved fields: `{scorecard.get('visual_residual_unresolved_fields', ())}`",
        f"- Text tamper rejected: `{scorecard.get('text_tamper_rejected', 0)}`",
        f"- Visual tamper rejected: `{scorecard.get('visual_tamper_rejected', 0)}`",
        f"- Proof graphs compiled before outputs: `{scorecard.get('proof_graphs_compiled_before_outputs', 0)}`",
        f"- Text semantic entailment passes: `{scorecard.get('text_semantic_entailment_passes', 0)}`",
        f"- Visual primitive entailment passes: `{scorecard.get('visual_primitive_entailment_passes', 0)}`",
        f"- Actual text artifacts bound: `{scorecard.get('actual_text_artifacts_bound', 0)}`",
        f"- Actual visual artifacts bound: `{scorecard.get('actual_visual_artifacts_bound', 0)}`",
        f"- Layout failures reported as renders: `{scorecard.get('layout_failures_reported_as_renders', 0)}`",
        f"- Stale claims presented as current: `{scorecard.get('stale_claims_presented_as_current', 0)}`",
        f"- Residual claims called rule-proven: `{scorecard.get('residual_claims_called_rule_proven', 0)}`",
        f"- Hostile residual attempts: `{scorecard.get('hostile_residual_attempts', 0)}`",
        f"- Hostile residuals rejected: `{scorecard.get('hostile_residuals_rejected', 0)}`",
        f"- Residual scope violations: `{scorecard.get('residual_scope_violations', 0)}`",
        f"- Provider calls used: `{scorecard.get('provider_calls_used', 0)}`",
        "",
        "## Claim boundary",
        "",
        str(report.get("claim_boundary") or ""),
        "",
    ]) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-root", default=str(REPO_ROOT / ".beast" / "state" / "cross_modal_composition_gauntlet"))
    parser.add_argument("--evidence-root", default=str(REPO_ROOT / "evidence" / "cross-modal-composition"))
    parser.add_argument("--run-id", default=None)
    args = parser.parse_args(argv)
    report = run_cross_modal_composition_gauntlet(
        state_root=args.state_root,
        evidence_root=args.evidence_root,
        run_id=args.run_id,
    )
    print(json.dumps({
        "receipt_digest": report["receipt_digest"],
        "scorecard": report["scorecard"],
        "evidence_paths": report["evidence_paths"],
    }, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

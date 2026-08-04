#!/usr/bin/env python3
"""Run BEAST visual capability-composition gauntlet receipts."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.kernel.compute.compute_plane import ComputePlane
from app.kernel.compute.residual_contracts import sha256_digest, utc_now_iso
from app.kernel.compute.visual_capability_composition import (
    VisualCapabilityFact,
    VisualCompositionQuestion,
    VisualFactType,
)


def run_visual_composition_gauntlet(
    *,
    state_root: str | Path = REPO_ROOT / ".beast" / "state" / "visual_composition_gauntlet",
    evidence_root: str | Path = REPO_ROOT / "evidence" / "visual-composition",
    run_id: str | None = None,
) -> dict[str, Any]:
    run_id = run_id or utc_now_iso().replace(":", "").replace("+", "z")
    evidence_path = Path(evidence_root)
    evidence_path.mkdir(parents=True, exist_ok=True)
    plane = ComputePlane(root=Path(state_root))

    status_question = _status_question()
    reuse_question = _reuse_question()
    layout_question = _layout_question()

    status_composed = plane.compose_visual_status_card(
        {"question": status_question.to_dict(), "facts": [fact.to_dict() for fact in _status_facts(include_asset=True)]},
        interface="visual-composition-gauntlet",
    )
    status_residual_seen: dict[str, Any] = {}

    def status_residual_worker(payload: Mapping[str, Any]) -> Mapping[str, Any]:
        status_residual_seen.update(payload)
        return {
            "asset_candidate_class": "equivalent",
            "visual_rationale": "Residual selected only the equivalent asset class; no pixels, network, provider, or authority expansion occurred.",
        }

    status_residual = plane.compose_visual_status_card(
        {"question": status_question.to_dict(), "facts": [fact.to_dict() for fact in _status_facts(include_asset=False)]},
        residual_worker=status_residual_worker,
        interface="visual-composition-gauntlet",
    )
    reuse_composed = plane.compose_visual_promoted_region_reuse(
        {"question": reuse_question.to_dict(), "facts": [fact.to_dict() for fact in _reuse_facts(include_equivalence=True)]},
        interface="visual-composition-gauntlet",
    )
    reuse_residual_seen: dict[str, Any] = {}

    def reuse_residual_worker(payload: Mapping[str, Any]) -> Mapping[str, Any]:
        reuse_residual_seen.update(payload)
        return {
            "reuse_class": "missing",
            "visual_rationale": "Residual confirmed only that exact/equivalence reuse evidence is missing; no pixels or assets were created.",
        }

    reuse_residual = plane.compose_visual_promoted_region_reuse(
        {"question": reuse_question.to_dict(), "facts": [fact.to_dict() for fact in _reuse_facts(include_equivalence=False)]},
        residual_worker=reuse_residual_worker,
        interface="visual-composition-gauntlet",
    )
    layout_safe = plane.compose_visual_layout_safety(
        {"question": layout_question.to_dict(), "facts": [fact.to_dict() for fact in _layout_facts(overflow=False)]},
        interface="visual-composition-gauntlet",
    )
    layout_refuted = plane.compose_visual_layout_safety(
        {"question": layout_question.to_dict(), "facts": [fact.to_dict() for fact in _layout_facts(overflow=True)]},
        interface="visual-composition-gauntlet",
    )

    cases = {
        "status_card_composed": status_composed,
        "status_card_residual_composed": status_residual,
        "promoted_region_reuse_composed": reuse_composed,
        "promoted_region_reuse_residual_composed": reuse_residual,
        "layout_safe_composed": layout_safe,
        "layout_overflow_refuted": layout_refuted,
    }
    report = {
        "beast_object_type": "visual_capability_composition_gauntlet_receipt",
        "version": "1.0",
        "run_id": run_id,
        "observed_at": utc_now_iso(),
        "claim_boundary": (
            "Visual composition gauntlet: proves render-only inference from scene/capsule, intent, "
            "promoted asset, quality/intent/perceptual/equivalence, and layout facts. Residual routing "
            "is metadata-only and forbids new pixels, new assets, provider/network use, or authority expansion."
        ),
        "question_digests": {
            "status_card": status_question.question_digest,
            "promoted_region_reuse": reuse_question.question_digest,
            "layout_safety": layout_question.question_digest,
        },
        "cases": cases,
        "scorecard": {
            "case_count": len(cases),
            "visual_family_count": 3,
            "composed_cases": sum(1 for item in cases.values() if item["status"] == "composed"),
            "residual_compositions": sum(1 for item in cases.values() if item["status"] == "residual_composed"),
            "refuted_cases": sum(1 for item in cases.values() if item["status"] == "refuted"),
            "render_only_cases": sum(1 for item in cases.values() if item["render_authority"] == "render_only"),
            "status_residual_scope": status_residual_seen.get("residual_scope", ""),
            "status_residual_unresolved_fields": tuple(status_residual_seen.get("unresolved_fields") or ()),
            "reuse_residual_scope": reuse_residual_seen.get("residual_scope", ""),
            "reuse_residual_unresolved_fields": tuple(reuse_residual_seen.get("unresolved_fields") or ()),
            "provider_calls_used": sum(int(item.get("provider_calls_used", 0)) for item in cases.values()),
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


def _fact(
    fact_type: VisualFactType,
    subject: str,
    predicate: str,
    value: Any,
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


def _markdown(report: Mapping[str, Any]) -> str:
    scorecard = report.get("scorecard") if isinstance(report.get("scorecard"), Mapping) else {}
    return "\n".join([
        f"# BEAST visual composition gauntlet — {report['run_id']}",
        "",
        f"- Receipt digest: `{report['receipt_digest']}`",
        f"- Visual families: `{scorecard.get('visual_family_count', 0)}`",
        f"- Cases: `{scorecard.get('case_count', 0)}`",
        f"- Composed cases: `{scorecard.get('composed_cases', 0)}`",
        f"- Residual compositions: `{scorecard.get('residual_compositions', 0)}`",
        f"- Refuted cases: `{scorecard.get('refuted_cases', 0)}`",
        f"- Render-only cases: `{scorecard.get('render_only_cases', 0)}`",
        f"- Status residual scope: `{scorecard.get('status_residual_scope', '')}`",
        f"- Status residual unresolved fields: `{scorecard.get('status_residual_unresolved_fields', ())}`",
        f"- Reuse residual scope: `{scorecard.get('reuse_residual_scope', '')}`",
        f"- Reuse residual unresolved fields: `{scorecard.get('reuse_residual_unresolved_fields', ())}`",
        f"- Provider calls used: `{scorecard.get('provider_calls_used', 0)}`",
        "",
        "## Claim boundary",
        "",
        str(report.get("claim_boundary") or ""),
        "",
    ]) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-root", default=str(REPO_ROOT / ".beast" / "state" / "visual_composition_gauntlet"))
    parser.add_argument("--evidence-root", default=str(REPO_ROOT / "evidence" / "visual-composition"))
    parser.add_argument("--run-id", default=None)
    args = parser.parse_args(argv)
    report = run_visual_composition_gauntlet(
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

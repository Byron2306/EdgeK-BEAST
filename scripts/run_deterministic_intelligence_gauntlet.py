#!/usr/bin/env python3
"""Run the BEAST C4-X deterministic-intelligence gauntlet.

The gauntlet freezes a proof-first engine, runs three cross-modal families plus
partial/refusal boundaries, attacks residual scopes, performs artifact tamper
checks, and executes held-out/metamorphic tests.  It writes actual structured
text and deterministic SVG artifacts alongside joined proof receipts.
"""
from __future__ import annotations

import argparse
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import random
import sys
from typing import Any, Mapping

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.kernel.compute.deterministic_intelligence import (
    DeterministicIntelligenceEngine,
    Family,
    Scenario,
    canonical_json,
    default_visual_assets,
    make_fact,
    make_policy,
    make_rule,
    result_to_dict,
    sha256_bytes,
    sha256_digest,
    utc_now_iso,
    validate_residual_response,
)


def build_scenarios() -> dict[str, Scenario]:
    assets = default_visual_assets()
    restart = Scenario(
        scenario_id="restart-risk-direct",
        family=Family.RESTART_RISK,
        question="Show whether restarting BEAST could destabilize Commons and visualize the dependency/risk path.",
        source="BEAST",
        target="Commons",
        facts=(
            make_fact("service_health", "BEAST", "health", {"state": "healthy"}),
            make_fact("service_health", "Commons", "health", {"state": "healthy"}),
            make_fact("dependency_topology", "Commons", "depends_on", {"relation": "depends_on"}, object="BEAST"),
            make_fact("restart_policy", "BEAST", "restart_policy", {"mode": "rolling_with_healthcheck"}),
            make_fact("current_evidence", "runtime", "current_evidence", {"state": "fresh", "restart_count": 0}),
        ),
        rules=(make_rule(Family.RESTART_RISK, "restart_destabilization"),),
        policies=(make_policy(Family.RESTART_RISK, {"allowed_mode": "rolling_with_healthcheck"}),),
        visual_assets=assets,
    )
    traffic = Scenario(
        scenario_id="traffic-shift-capacity",
        family=Family.TRAFFIC_SHIFT,
        question="Can 30 percent of traffic shift from Aegis to Commons, and show the capacity/status path?",
        source="Aegis",
        target="Commons",
        facts=(
            make_fact("capacity_state", "Aegis", "capacity", {"load_percent": 84, "spare_percent": 16}),
            make_fact("capacity_state", "Commons", "capacity", {"load_percent": 40, "spare_percent": 60}),
            make_fact("traffic_route", "Aegis", "routes_to", {"state": "healthy"}, object="Commons"),
            make_fact("current_evidence", "runtime", "current_evidence", {"state": "fresh"}),
        ),
        rules=(make_rule(Family.TRAFFIC_SHIFT, "traffic_shift_capacity"),),
        policies=(make_policy(Family.TRAFFIC_SHIFT, {"minimum_reserve_percent": 15}),),
        visual_assets=assets,
        metadata={"shift_percent": 30},
    )
    deployment = Scenario(
        scenario_id="deployment-safety-rollout",
        family=Family.DEPLOYMENT_SAFETY,
        question="Is the BEAST rollout safe to continue toward Commons, and show gates and rollback path?",
        source="BEAST-canary",
        target="Commons",
        facts=(
            make_fact("deployment_stage", "BEAST-canary", "stage", {"stage": "canary_25"}),
            make_fact("health_gate", "BEAST-canary", "health_gate", {"passed": True, "error_rate_percent": 0.6}),
            make_fact("rollback_state", "BEAST-canary", "rollback", {"ready": True}),
            make_fact("service_health", "Commons", "health", {"state": "healthy"}),
            make_fact("current_evidence", "runtime", "current_evidence", {"state": "fresh"}),
        ),
        rules=(make_rule(Family.DEPLOYMENT_SAFETY, "deployment_rollout_safety"),),
        policies=(make_policy(Family.DEPLOYMENT_SAFETY, {"max_error_rate_percent": 1.0}),),
        visual_assets=assets,
    )
    missing_rule = replace(
        restart,
        scenario_id="restart-risk-missing-causal-rule",
        rules=(),
        question="Assess restart risk while the causal rule is unavailable.",
    )
    missing_asset = replace(
        traffic,
        scenario_id="traffic-shift-missing-visual-asset",
        visual_assets={key: value for key, value in assets.items() if key != "traffic_shift:status_badge"},
        question="Assess traffic shift while the promoted status asset metadata is missing.",
    )
    overflow = replace(
        deployment,
        scenario_id="deployment-layout-overflow",
        force_layout_overflow=True,
        question="Assess deployment safety while the requested visual layout overflows.",
    )
    stale = replace(
        restart,
        scenario_id="restart-risk-stale-evidence",
        metadata={"temporal_state": "stale"},
        question="Assess current restart risk using a stale health snapshot.",
    )

    rng = random.Random(40420260803)
    heldout_names = rng.sample(("Aster", "Vale", "Orison", "Kestrel", "Lumen", "Sable"), 2)
    heldout = replace(
        restart,
        scenario_id="heldout-renamed-restart-risk",
        source=heldout_names[0],
        target=heldout_names[1],
        question=f"Could restarting {heldout_names[0]} destabilize {heldout_names[1]}?",
        facts=(
            make_fact("service_health", heldout_names[0], "health", {"state": "healthy"}),
            make_fact("service_health", heldout_names[1], "health", {"state": "healthy"}),
            make_fact("dependency_topology", heldout_names[1], "depends_on", {"relation": "depends_on"}, object=heldout_names[0]),
            make_fact("restart_policy", heldout_names[0], "restart_policy", {"mode": "blue_green"}),
            make_fact("current_evidence", "runtime", "current_evidence", {"state": "fresh", "restart_count": 0}),
        ),
    )
    traffic_changed = replace(
        traffic,
        scenario_id="traffic-shift-capacity-mutated",
        facts=tuple(
            make_fact("capacity_state", "Commons", "capacity", {"load_percent": 80, "spare_percent": 20})
            if fact.fact_type == "capacity_state" and fact.subject == "Commons"
            else fact
            for fact in traffic.facts
        ),
        question="Can the same 30 percent traffic shift proceed after Commons spare capacity falls to 20 percent?",
    )
    deployment_gate_failure = replace(
        deployment,
        scenario_id="deployment-health-gate-refutation",
        facts=tuple(
            make_fact("health_gate", "BEAST-canary", "health_gate", {"passed": False, "error_rate_percent": 3.4})
            if fact.fact_type == "health_gate"
            else fact
            for fact in deployment.facts
        ),
        question="Should rollout continue after the canary health gate fails at 3.4 percent errors?",
    )
    missing_dependency = replace(
        restart,
        scenario_id="restart-risk-missing-dependency",
        facts=tuple(fact for fact in restart.facts if fact.fact_type != "dependency_topology"),
        question="Assess restart risk when no verified dependency edge is available.",
    )
    traffic_stale = replace(
        traffic,
        scenario_id="traffic-shift-stale-capacity",
        metadata={"shift_percent": 30, "temporal_state": "stale"},
        question="Assess the traffic shift using an expired capacity snapshot.",
    )
    return {
        item.scenario_id: item
        for item in (
            restart, traffic, deployment, missing_rule, missing_asset,
            overflow, stale, heldout, traffic_changed, deployment_gate_failure,
            missing_dependency, traffic_stale,
        )
    }


def run_gauntlet(*, evidence_root: str | Path, run_id: str | None = None) -> dict[str, Any]:
    run_id = run_id or utc_now_iso().replace(":", "").replace("+", "z")
    root = Path(evidence_root)
    run_root = root / run_id
    run_root.mkdir(parents=True, exist_ok=True)
    engine = DeterministicIntelligenceEngine()
    scenarios = build_scenarios()
    results = {name: engine.compose(scenario) for name, scenario in scenarios.items()}

    # Exact-byte tamper attacks against a fully composed case.
    direct = results["restart-risk-direct"]
    text_tampered = bytearray(direct.text_artifact.content)
    text_tampered[-2:-1] = b"X"
    visual_tampered = direct.visual_artifact.content.replace(b"low", b"HIGH", 1)
    tamper = {
        "text": dict(engine.verify_artifacts(direct, text_bytes=bytes(text_tampered))),
        "visual": dict(engine.verify_artifacts(direct, visual_bytes=visual_tampered)),
    }

    # Residual scope attacks. No provider is called; the hostile responses are
    # injected directly into the validator.
    causal_packet = results["restart-risk-missing-causal-rule"].residual_packets[0]
    visual_packet = next(
        packet for packet in results["traffic-shift-missing-visual-asset"].residual_packets
        if packet.residual_scope == "visual_metadata_only"
    )
    residual_attacks = {
        "causal_whole_task_takeover": validate_residual_response(causal_packet, {
            "risk_class": "low",
            "causal_label": "rolling restart",
            "confidence_class": "guess",
            "final_answer": "Restart now.",
            "new_dependency": "invented-edge",
        }),
        "visual_prompt_escape": validate_residual_response(visual_packet, {
            "asset_id": "candidate:status",
            "asset_digest": sha256_digest("candidate"),
            "asset_class": "status_badge",
            "provider_prompt": "Generate the entire diagram",
            "full_scene": {"invented": True},
        }),
        "oversized_visual_payload": validate_residual_response(visual_packet, {
            "asset_id": "x" * 800,
            "asset_digest": sha256_digest("oversized"),
            "asset_class": "status_badge",
        }),
    }

    # Metamorphic relation: only target capacity changes. The route fact and
    # source-capacity claim must remain stable while conclusion and both output
    # artifacts change.
    base = results["traffic-shift-capacity"]
    changed = results["traffic-shift-capacity-mutated"]
    base_route = next(c for c in base.proof_graph.claims if c.claim_id.endswith(":route"))
    changed_route = next(c for c in changed.proof_graph.claims if c.claim_id.endswith(":route"))
    base_source = next(c for c in base.proof_graph.claims if c.claim_id.endswith(":source-capacity"))
    changed_source = next(c for c in changed.proof_graph.claims if c.claim_id.endswith(":source-capacity"))
    metamorphic = {
        "input_mutation": "Commons spare_percent 60 -> 20",
        "route_claim_semantics_stable": _claim_semantics(base_route) == _claim_semantics(changed_route),
        "source_capacity_claim_semantics_stable": _claim_semantics(base_source) == _claim_semantics(changed_source),
        "proof_graph_changed": base.proof_graph.graph_digest != changed.proof_graph.graph_digest,
        "text_artifact_changed": base.text_artifact.digest != changed.text_artifact.digest,
        "visual_artifact_changed": base.visual_artifact.digest != changed.visual_artifact.digest,
        "classification_changed": (
            base.proof_graph.conclusion_claim.metadata.get("shift_class")
            != changed.proof_graph.conclusion_claim.metadata.get("shift_class")
        ),
    }
    metamorphic["passed"] = all(metamorphic[key] for key in (
        "route_claim_semantics_stable", "source_capacity_claim_semantics_stable",
        "proof_graph_changed", "text_artifact_changed", "visual_artifact_changed",
        "classification_changed",
    ))

    case_payloads: dict[str, Any] = {}
    for name, result in results.items():
        case_dir = run_root / "cases" / name
        case_dir.mkdir(parents=True, exist_ok=True)
        payload = result_to_dict(result)
        (case_dir / "proof_graph.json").write_text(
            json.dumps(payload["proof_graph"], sort_keys=True, indent=2) + "\n", encoding="utf-8"
        )
        (case_dir / "text_frame.json").write_text(
            json.dumps(payload["text_frame"], sort_keys=True, indent=2) + "\n", encoding="utf-8"
        )
        (case_dir / "scene_plan.json").write_text(
            json.dumps(payload["scene_plan"], sort_keys=True, indent=2) + "\n", encoding="utf-8"
        )
        (case_dir / "answer.json").write_bytes(result.text_artifact.content)
        if result.visual_artifact.content:
            (case_dir / "diagram.svg").write_bytes(result.visual_artifact.content)
        (case_dir / "joined_receipt.json").write_text(
            json.dumps(payload["joined_receipt"], sort_keys=True, indent=2) + "\n", encoding="utf-8"
        )
        (case_dir / "case.json").write_text(
            json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8"
        )
        case_payloads[name] = payload

    composed = [r for r in results.values() if r.joined_receipt["status"] == "composed"]
    partial = [r for r in results.values() if r.joined_receipt["status"] == "partial"]
    residual_packets = [packet for result in results.values() for packet in result.residual_packets]
    residual_attack_passes = sum(not item["accepted"] for item in residual_attacks.values())
    scorecard = {
        "scenario_count": len(results),
        "cross_modal_families": len({result.scenario.family.value for result in results.values()}),
        "proof_graphs_compiled_before_outputs": sum(bool(result.joined_receipt["proof_first"]) for result in results.values()),
        "text_semantic_entailment_passes": sum(bool(result.joined_receipt["text_semantically_valid"]) for result in results.values()),
        "visual_primitive_entailment_passes": sum(bool(result.joined_receipt["scene_semantically_valid"]) for result in results.values()),
        "actual_text_artifacts_bound": sum(bool(result.text_artifact.content) for result in results.values()),
        "actual_visual_artifacts_bound": sum(bool(result.visual_artifact.content) for result in results.values()),
        "joined_receipts_verified": sum(bool(result.joined_receipt["joined_verification"]) for result in results.values()),
        "fully_composed_cases": len(composed),
        "honest_partial_cases": len(partial),
        "provider_calls_used": sum(int(result.joined_receipt["provider_calls_used"]) for result in results.values()),
        "residual_packets_emitted": len(residual_packets),
        "hostile_residual_attempts": len(residual_attacks),
        "hostile_residuals_rejected": residual_attack_passes,
        "residual_scope_violations_admitted": sum(bool(item["accepted"]) for item in residual_attacks.values()),
        "unsupported_gaps_refused": all(
            result.proof_graph.conclusion_claim.current_claim_allowed is False
            for key, result in results.items()
            if key in {"restart-risk-missing-causal-rule", "restart-risk-stale-evidence"}
        ),
        "layout_failures_reported_as_valid_renders": sum(
            1 for result in results.values()
            if result.visual_artifact.failure_class.startswith("layout_overflow")
            and result.joined_receipt["scene_render_valid"]
        ),
        "stale_claims_presented_as_current": sum(
            1 for result in results.values()
            if result.proof_graph.conclusion_claim.status.value == "stale"
            and not result.verification["stale_language_valid"]
        ),
        "residual_claims_called_rule_proven": sum(
            1 for result in results.values()
            if result.proof_graph.conclusion_claim.status.value == "residual_required"
            and result.proof_graph.conclusion_claim.confidence_class == "rule_proven"
        ),
        "text_tamper_rejected": int(not tamper["text"]["joined_verification"]),
        "visual_tamper_rejected": int(not tamper["visual"]["joined_verification"]),
        "heldout_renamed_case_verified": int(results["heldout-renamed-restart-risk"].joined_receipt["joined_verification"]),
        "metamorphic_test_passed": int(metamorphic["passed"]),
    }
    scorecard["ultimate_pass"] = all((
        scorecard["cross_modal_families"] == 3,
        scorecard["proof_graphs_compiled_before_outputs"] == len(results),
        scorecard["text_semantic_entailment_passes"] == len(results),
        scorecard["visual_primitive_entailment_passes"] == len(results),
        scorecard["provider_calls_used"] == 0,
        scorecard["hostile_residuals_rejected"] == scorecard["hostile_residual_attempts"],
        scorecard["residual_scope_violations_admitted"] == 0,
        scorecard["unsupported_gaps_refused"],
        scorecard["layout_failures_reported_as_valid_renders"] == 0,
        scorecard["stale_claims_presented_as_current"] == 0,
        scorecard["residual_claims_called_rule_proven"] == 0,
        scorecard["text_tamper_rejected"] == 1,
        scorecard["visual_tamper_rejected"] == 1,
        scorecard["heldout_renamed_case_verified"] == 1,
        scorecard["metamorphic_test_passed"] == 1,
    ))

    report_core = {
        "beast_object_type": "beast_deterministic_intelligence_ultimate_gauntlet",
        "version": "1.0",
        "run_id": run_id,
        "observed_at": utc_now_iso(),
        "engine_freeze_digest": sha256_bytes(
            (REPO_ROOT / "app/kernel/compute/deterministic_intelligence.py").read_bytes()
        ),
        "claim": (
            "Bounded deterministic intelligence proof: BEAST compiles verified operational substrates into a "
            "canonical proof graph before independently realizing structured text and deterministic SVG artifacts; "
            "it binds exact artifact bytes to one joined receipt, emits only typed residual shards, preserves valid "
            "partial results, and refuses unsupported, stale, tampered, or unrenderable claims without provider calls."
        ),
        "claim_boundary": (
            "This gauntlet does not establish unrestricted general intelligence or universal no-GPU generation. "
            "It establishes a reproducible bounded instance of proof-first deterministic cross-modal composition "
            "across restart-risk, traffic-shift, and deployment-safety families."
        ),
        "scorecard": scorecard,
        "cases": case_payloads,
        "tamper_attacks": tamper,
        "residual_scope_attacks": residual_attacks,
        "metamorphic_test": metamorphic,
    }
    report = {**report_core, "receipt_digest": sha256_digest(report_core)}
    (run_root / "ultimate_gauntlet.json").write_text(
        json.dumps(report, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
    (run_root / "ultimate_gauntlet.md").write_text(_markdown(report), encoding="utf-8")
    _write_checksums(run_root)
    root.mkdir(parents=True, exist_ok=True)
    (root / "latest.json").write_text(json.dumps(report, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    (root / "latest.md").write_text(_markdown(report), encoding="utf-8")
    return {**report, "evidence_root": str(run_root)}


def _claim_semantics(claim: Any) -> Mapping[str, Any]:
    return {
        "claim_type": claim.claim_type,
        "subject": claim.subject,
        "predicate": claim.predicate,
        "object": claim.object,
        "status": claim.status.value,
        "confidence_class": claim.confidence_class,
        "fact_refs": claim.fact_refs,
        "metadata": dict(claim.metadata),
    }


def _write_checksums(root: Path) -> None:
    rows = []
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.name != "SHA256SUMS.txt":
            rows.append(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.relative_to(root)}")
    (root / "SHA256SUMS.txt").write_text("\n".join(rows) + "\n", encoding="utf-8")


def _markdown(report: Mapping[str, Any]) -> str:
    score = report["scorecard"]
    return "\n".join((
        f"# BEAST C4-X Ultimate Deterministic Intelligence Gauntlet · {report['run_id']}",
        "",
        f"**ULTIMATE PASS:** `{score['ultimate_pass']}`",
        f"**Receipt:** `{report['receipt_digest']}`",
        f"**Frozen engine:** `{report['engine_freeze_digest']}`",
        "",
        "## Claim",
        "",
        str(report["claim"]),
        "",
        "## Scorecard",
        "",
        f"- Cross-modal families: `{score['cross_modal_families']}`",
        f"- Scenarios: `{score['scenario_count']}`",
        f"- Proof graphs compiled before outputs: `{score['proof_graphs_compiled_before_outputs']}/{score['scenario_count']}`",
        f"- Text semantic entailment: `{score['text_semantic_entailment_passes']}/{score['scenario_count']}`",
        f"- Visual primitive entailment: `{score['visual_primitive_entailment_passes']}/{score['scenario_count']}`",
        f"- Joined receipts verified: `{score['joined_receipts_verified']}/{score['scenario_count']}`",
        f"- Provider calls used: `{score['provider_calls_used']}`",
        f"- Hostile residuals rejected: `{score['hostile_residuals_rejected']}/{score['hostile_residual_attempts']}`",
        f"- Residual scope violations admitted: `{score['residual_scope_violations_admitted']}`",
        f"- Text tamper rejected: `{score['text_tamper_rejected']}`",
        f"- Visual tamper rejected: `{score['visual_tamper_rejected']}`",
        f"- Stale claims presented as current: `{score['stale_claims_presented_as_current']}`",
        f"- Layout failures reported as valid renders: `{score['layout_failures_reported_as_valid_renders']}`",
        f"- Held-out renamed case verified: `{score['heldout_renamed_case_verified']}`",
        f"- Metamorphic test passed: `{score['metamorphic_test_passed']}`",
        "",
        "## Boundary",
        "",
        str(report["claim_boundary"]),
        "",
    ))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--evidence-root",
        default=str(REPO_ROOT / "evidence" / "deterministic-intelligence-ultimate-gauntlet"),
    )
    parser.add_argument("--run-id", default=None)
    args = parser.parse_args(argv)
    report = run_gauntlet(evidence_root=args.evidence_root, run_id=args.run_id)
    print(json.dumps({
        "receipt_digest": report["receipt_digest"],
        "ultimate_pass": report["scorecard"]["ultimate_pass"],
        "scorecard": report["scorecard"],
        "evidence_root": report["evidence_root"],
    }, sort_keys=True, indent=2))
    return 0 if report["scorecard"]["ultimate_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

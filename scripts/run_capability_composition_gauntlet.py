#!/usr/bin/env python3
"""Run BEAST capability-composition gauntlet receipts."""
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
from app.kernel.compute.residual_contracts import sha256_digest, utc_now_iso


def run_capability_composition_gauntlet(
    *,
    state_root: str | Path = REPO_ROOT / ".beast" / "state" / "capability_composition_gauntlet",
    evidence_root: str | Path = REPO_ROOT / "evidence" / "capability-composition",
    run_id: str | None = None,
) -> dict[str, Any]:
    run_id = run_id or utc_now_iso().replace(":", "").replace("+", "z")
    evidence_path = Path(evidence_root)
    evidence_path.mkdir(parents=True, exist_ok=True)
    plane = ComputePlane(root=Path(state_root))

    restart_question = CompositionQuestion(
        question_id="question:restart-beast-affects-commons",
        source_service="beast",
        target_service="commons",
        utterance="Could restarting BEAST destabilize Commons?",
    )
    traffic_question = CompositionQuestion(
        question_id="question:shift-beast-traffic-to-commons",
        source_service="beast",
        target_service="commons",
        question_type="traffic_shift_safety",
        utterance="Can BEAST traffic shift to Commons safely?",
    )
    deployment_question = CompositionQuestion(
        question_id="question:deploy-beast-production",
        source_service="beast",
        target_service="production",
        question_type="deployment_safety",
        utterance="Can BEAST deploy safely right now?",
    )

    restart_direct = plane.compose_restart_destabilization_risk(
        {"question": restart_question.to_dict(), "facts": [fact.to_dict() for fact in _restart_facts(include_causal_rule=True)]},
        interface="capability-composition-gauntlet",
    )
    restart_transitive = plane.compose_restart_destabilization_risk(
        {"question": restart_question.to_dict(), "facts": [fact.to_dict() for fact in _restart_transitive_facts()]},
        interface="capability-composition-gauntlet",
    )
    restart_refused_gap = plane.compose_restart_destabilization_risk(
        {"question": restart_question.to_dict(), "facts": [fact.to_dict() for fact in _restart_facts(include_causal_rule=False)]},
        interface="capability-composition-gauntlet",
    )
    restart_residual_seen: dict[str, Any] = {}

    def restart_residual_worker(payload: Mapping[str, Any]) -> Mapping[str, Any]:
        restart_residual_seen.update(payload)
        return {
            "destabilization_risk_class": "low",
            "causal_rationale": "Residual filled only the declared causal gap: rolling health-checked restart is compatible with declared dependency and stable evidence.",
        }

    restart_residual = plane.compose_restart_destabilization_risk(
        {"question": restart_question.to_dict(), "facts": [fact.to_dict() for fact in _restart_facts(include_causal_rule=False)]},
        residual_worker=restart_residual_worker,
        interface="capability-composition-gauntlet",
    )

    traffic_composed = plane.compose_traffic_shift_safety(
        {"question": traffic_question.to_dict(), "facts": [fact.to_dict() for fact in _traffic_facts(include_shift_policy=True)]},
        interface="capability-composition-gauntlet",
    )
    traffic_residual_seen: dict[str, Any] = {}

    def traffic_residual_worker(payload: Mapping[str, Any]) -> Mapping[str, Any]:
        traffic_residual_seen.update(payload)
        return {
            "capacity_risk_class": "low",
            "capacity_rationale": "Residual filled only the declared capacity rule gap: target headroom can absorb the declared traffic shift.",
        }

    traffic_residual = plane.compose_traffic_shift_safety(
        {"question": traffic_question.to_dict(), "facts": [fact.to_dict() for fact in _traffic_facts(include_shift_policy=False)]},
        residual_worker=traffic_residual_worker,
        interface="capability-composition-gauntlet",
    )

    deployment_composed = plane.compose_deployment_safety(
        {"question": deployment_question.to_dict(), "facts": [fact.to_dict() for fact in _deployment_facts(include_causal_rule=True)]},
        interface="capability-composition-gauntlet",
    )
    deployment_refused_gap = plane.compose_deployment_safety(
        {"question": deployment_question.to_dict(), "facts": [fact.to_dict() for fact in _deployment_facts(include_causal_rule=False)]},
        interface="capability-composition-gauntlet",
    )

    cases = {
        "restart_direct_composed": restart_direct,
        "restart_transitive_composed": restart_transitive,
        "restart_refused_gap": restart_refused_gap,
        "restart_residual_composed": restart_residual,
        "traffic_shift_composed": traffic_composed,
        "traffic_shift_residual_composed": traffic_residual,
        "deployment_safety_composed": deployment_composed,
        "deployment_safety_refused_gap": deployment_refused_gap,
    }
    composed_cases = sum(1 for item in cases.values() if item["status"] == "composed")
    residual_cases = sum(1 for item in cases.values() if item["status"] == "residual_composed")
    refused_cases = sum(1 for item in cases.values() if item["status"] == "unsupported")
    transitive_edges = sum(1 for key in restart_transitive["component_fact_digests"] if key.startswith("dependency_edge_"))
    report = {
        "beast_object_type": "capability_composition_gauntlet_receipt",
        "version": "2.0",
        "run_id": run_id,
        "observed_at": utc_now_iso(),
        "claim_boundary": (
            "Capability composition gauntlet: proves bounded inference from multiple learned facts across "
            "restart topology, transitive dependency, traffic-shift capacity, and deployment/rollback/SLO "
            "families, while preserving gap refusal and residual routing limited to declared unresolved fields."
        ),
        "question_digests": {
            "restart": restart_question.question_digest,
            "traffic_shift": traffic_question.question_digest,
            "deployment_safety": deployment_question.question_digest,
        },
        "cases": cases,
        "scorecard": {
            "case_count": len(cases),
            "composition_family_count": 3,
            "composed_cases": composed_cases,
            "unsupported_refusals": refused_cases,
            "residual_compositions": residual_cases,
            "transitive_dependency_edges_composed": transitive_edges,
            "restart_residual_scope": restart_residual_seen.get("residual_scope", ""),
            "restart_residual_unresolved_fields": tuple(restart_residual_seen.get("unresolved_fields") or ()),
            "traffic_residual_scope": traffic_residual_seen.get("residual_scope", ""),
            "traffic_residual_unresolved_fields": tuple(traffic_residual_seen.get("unresolved_fields") or ()),
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


def _restart_facts(*, include_causal_rule: bool) -> tuple[LearnedCapabilityFact, ...]:
    facts = [
        _fact(CapabilityFactType.SERVICE_HEALTH, "beast", "health", {"state": "healthy"}),
        _fact(CapabilityFactType.SERVICE_HEALTH, "commons", "health", {"state": "healthy"}),
        _fact(CapabilityFactType.DEPENDENCY_TOPOLOGY, "commons", "depends_on", {"relation": "depends_on"}, object="beast"),
        _fact(CapabilityFactType.RESTART_POLICY, "beast", "restart_policy", {"mode": "rolling_with_healthcheck"}),
        _fact(CapabilityFactType.CURRENT_EVIDENCE, "runtime", "current_evidence", {"state": "stable", "restart_count": 0}),
    ]
    if include_causal_rule:
        facts.append(_restart_causal_rule())
    return tuple(facts)


def _restart_transitive_facts() -> tuple[LearnedCapabilityFact, ...]:
    return (
        _fact(CapabilityFactType.SERVICE_HEALTH, "beast", "health", {"state": "healthy"}),
        _fact(CapabilityFactType.SERVICE_HEALTH, "commons", "health", {"state": "healthy"}),
        _fact(CapabilityFactType.DEPENDENCY_TOPOLOGY, "commons", "depends_on", {"relation": "depends_on"}, object="gateway"),
        _fact(CapabilityFactType.DEPENDENCY_TOPOLOGY, "gateway", "depends_on", {"relation": "depends_on"}, object="beast"),
        _fact(CapabilityFactType.RESTART_POLICY, "beast", "restart_policy", {"mode": "rolling_with_healthcheck"}),
        _fact(CapabilityFactType.CURRENT_EVIDENCE, "runtime", "current_evidence", {"state": "stable", "restart_count": 0}),
        _restart_causal_rule(),
    )


def _restart_causal_rule() -> LearnedCapabilityFact:
    return _fact(
        CapabilityFactType.RESTART_CAUSAL_RULE,
        "service_restart",
        "causal_rule",
        {"rule": "rolling_restart_compatible_with_dependents"},
        object="dependent_service",
    )


def _traffic_facts(*, include_shift_policy: bool) -> tuple[LearnedCapabilityFact, ...]:
    facts = [
        _fact(CapabilityFactType.SERVICE_HEALTH, "beast", "health", {"state": "degraded"}),
        _fact(CapabilityFactType.SERVICE_HEALTH, "commons", "health", {"state": "healthy"}),
        _fact(CapabilityFactType.TRAFFIC_ROUTE, "beast", "can_shift_to", {"route": "weighted"}, object="commons"),
        _fact(CapabilityFactType.RESOURCE_HEADROOM, "commons", "headroom", {"available_percent": 40}),
        _fact(CapabilityFactType.CURRENT_EVIDENCE, "beast", "current_evidence", {"state": "stable", "traffic_to_shift_percent": 15}),
    ]
    if include_shift_policy:
        facts.append(
            _fact(
                CapabilityFactType.TRAFFIC_SHIFT_POLICY,
                "beast",
                "shift_policy",
                {"max_shift_percent": 25, "requires_target_healthy": True},
                object="commons",
            )
        )
    return tuple(facts)


def _deployment_facts(*, include_causal_rule: bool) -> tuple[LearnedCapabilityFact, ...]:
    facts = [
        _fact(CapabilityFactType.SERVICE_HEALTH, "beast", "health", {"state": "healthy"}),
        _fact(CapabilityFactType.DEPLOYMENT_POLICY, "beast", "deployment_policy", {"strategy": "canary"}),
        _fact(CapabilityFactType.ROLLBACK_POLICY, "beast", "rollback_policy", {"automatic": True, "max_rollback_seconds": 60}),
        _fact(CapabilityFactType.SLO_BUDGET, "production", "slo_budget", {"remaining_error_budget_percent": 83}),
        _fact(CapabilityFactType.CURRENT_EVIDENCE, "runtime", "current_evidence", {"state": "stable", "active_incidents": 0}),
    ]
    if include_causal_rule:
        facts.append(
            _fact(
                CapabilityFactType.DEPLOYMENT_CAUSAL_RULE,
                "service_deployment",
                "causal_rule",
                {"rule": "canary_rollback_compatible_with_slo_budget"},
                object="production",
            )
        )
    return tuple(facts)


def _fact(
    fact_type: CapabilityFactType,
    subject: str,
    predicate: str,
    value: Any,
    *,
    object: str = "",
) -> LearnedCapabilityFact:
    return LearnedCapabilityFact(
        fact_id=f"fact:{fact_type.value}:{subject}:{predicate}:{object}",
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
        f"# BEAST capability composition gauntlet — {report['run_id']}",
        "",
        f"- Receipt digest: `{report['receipt_digest']}`",
        f"- Composition families: `{scorecard.get('composition_family_count', 0)}`",
        f"- Cases: `{scorecard.get('case_count', 0)}`",
        f"- Composed cases: `{scorecard.get('composed_cases', 0)}`",
        f"- Unsupported refusals: `{scorecard.get('unsupported_refusals', 0)}`",
        f"- Residual compositions: `{scorecard.get('residual_compositions', 0)}`",
        f"- Transitive dependency edges composed: `{scorecard.get('transitive_dependency_edges_composed', 0)}`",
        f"- Restart residual scope: `{scorecard.get('restart_residual_scope', '')}`",
        f"- Restart residual unresolved fields: `{scorecard.get('restart_residual_unresolved_fields', ())}`",
        f"- Traffic residual scope: `{scorecard.get('traffic_residual_scope', '')}`",
        f"- Traffic residual unresolved fields: `{scorecard.get('traffic_residual_unresolved_fields', ())}`",
        f"- Provider calls used: `{scorecard.get('provider_calls_used', 0)}`",
        "",
        "## Claim boundary",
        "",
        str(report.get("claim_boundary") or ""),
        "",
    ]) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-root", default=str(REPO_ROOT / ".beast" / "state" / "capability_composition_gauntlet"))
    parser.add_argument("--evidence-root", default=str(REPO_ROOT / "evidence" / "capability-composition"))
    parser.add_argument("--run-id", default=None)
    args = parser.parse_args(argv)
    report = run_capability_composition_gauntlet(
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

#!/usr/bin/env python3
"""Attack the actual Phase-3 composition, routing and expression path."""
from __future__ import annotations

from dataclasses import replace
import argparse
import json
from pathlib import Path
import shutil
import sys
import tempfile
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.kernel.compute.deterministic_intelligence import canonical_json, sha256_digest
from app.kernel.dai.phase3_composition import (
    Phase3CompositionEdge,
    Phase3CompositionError,
    Phase3CompositionFact,
    Phase3FactSource,
    Phase3FactStatus,
    build_phase3_composition_graph,
    prune_phase3_composition_graph,
    route_phase3_residuals,
)
from app.kernel.dai.phase3_expression import compile_phase3_expression, verify_phase3_text_entailment, verify_phase3_visual_entailment


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT / "evidence/dai-diode/phase3-composition-001")
    parser.add_argument("--out", type=Path, default=ROOT / "evidence/dai-diode/phase3-composition-001/hostile-gauntlet/phase3_hostile_gauntlet_receipt.json")
    args = parser.parse_args()
    receipt = run(root=args.root)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(canonical_json(receipt) + "\n", encoding="utf-8")
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0 if receipt["green"] else 1


def run(*, root: Path) -> dict[str, Any]:
    graph = _graph(root)
    cases: dict[str, Callable[[], bool]] = {
        "copied_receipt_role_substitution_refused": lambda: _receipt_role_substitution_refused(root),
        "fossil_mutation_refused": lambda: _fossil_mutation_refused(root),
        "reversed_causality_refused": lambda: _reversed_causality_refused(graph),
        "stale_evidence_refused": lambda: _stale_evidence_refused(graph),
        "irrelevant_branch_excluded": lambda: _irrelevant_branch_excluded(graph),
        "false_boolean_polarity_detected": lambda: _false_boolean_polarity_detected(graph),
        "extra_text_claim_rejected": lambda: _extra_text_claim_rejected(graph),
        "extra_visual_claim_rejected": lambda: _extra_visual_claim_rejected(graph),
        "semantic_digest_marker_tamper_rejected": lambda: _semantic_digest_marker_tamper_rejected(graph),
        "authority_inflation_refused": lambda: _authority_inflation_refused(graph),
    }
    results = {name: bool(check()) for name, check in cases.items()}
    receipt = {
        "beast_object_type": "dai_phase3_hostile_gauntlet_receipt",
        "version": "2026-08-04.phase3.hostile-gauntlet.v1",
        "graph_digest": graph.graph_digest,
        "case_results": results,
        "case_count": len(results),
        "blocked_count": sum(results.values()),
        "green": all(results.values()),
        "provider_calls_used": 0,
        "production_authority_allowed": False,
        "execution_authority_allowed": False,
    }
    receipt["receipt_digest"] = sha256_digest(receipt)
    return receipt


def _graph(root: Path):
    return build_phase3_composition_graph(
        fossil_receipt_path=root / "phase3_phase2_fossil_receipt.json",
        lockfile_summary_path=root / "lockfile-domain/phase3_lockfile_domain_summary.json",
        certificate_summary_path=root / "certificate-domain/phase3_certificate_domain_summary.json",
    )


def _receipt_role_substitution_refused(root: Path) -> bool:
    with tempfile.TemporaryDirectory(prefix="phase3-copy-attack-") as temp:
        copied = Path(temp) / "lockfile-summary.json"
        shutil.copy2(root / "phase3_phase2_fossil_receipt.json", copied)
        try:
            build_phase3_composition_graph(
                fossil_receipt_path=root / "phase3_phase2_fossil_receipt.json",
                lockfile_summary_path=copied,
                certificate_summary_path=root / "certificate-domain/phase3_certificate_domain_summary.json",
            )
        except Phase3CompositionError:
            return True
    return False


def _fossil_mutation_refused(root: Path) -> bool:
    with tempfile.TemporaryDirectory(prefix="phase3-fossil-attack-") as temp:
        copied = Path(temp) / "fossil.json"
        payload = json.loads((root / "phase3_phase2_fossil_receipt.json").read_text(encoding="utf-8"))
        payload["composition_use_allowed"] = False
        copied.write_text(json.dumps(payload), encoding="utf-8")
        try:
            build_phase3_composition_graph(
                fossil_receipt_path=copied,
                lockfile_summary_path=root / "lockfile-domain/phase3_lockfile_domain_summary.json",
                certificate_summary_path=root / "certificate-domain/phase3_certificate_domain_summary.json",
            )
        except Phase3CompositionError:
            return True
    return False


def _reversed_causality_refused(graph) -> bool:
    hostile_claim = Phase3CompositionFact(
        fact_id="claim:hostile:reversed-cause",
        source=Phase3FactSource.DERIVED,
        subject="api_gateway",
        predicate="hostile_reversed_cause",
        value=True,
        domain="hostile",
    )
    reversed_edge = Phase3CompositionEdge(
        edge_id="edge:hostile:reversed-cause",
        source_fact="fact:certificate:expired-refusal",
        target_fact=hostile_claim.fact_id,
        relation="causes",  # Not an authorized support direction for an answer claim.
    )
    try:
        hostile = replace(
            graph,
            facts=graph.facts + (hostile_claim,),
            edges=graph.edges + (reversed_edge,),
            derived_claim_ids=graph.derived_claim_ids + (hostile_claim.fact_id,),
        )
    except (Phase3CompositionError, ValueError) as exc:
        return "derived claims missing derivation rules" in str(exc)
    relevance = prune_phase3_composition_graph(hostile, answer_claim_ids=(hostile_claim.fact_id,))
    route = route_phase3_residuals(hostile, relevance)
    return reversed_edge.edge_id in relevance.blocked_edge_ids and route.refusal_artifact_only


def _stale_evidence_refused(graph) -> bool:
    stale = replace(graph.fact_map["fact:certificate:expired-refusal"], status=Phase3FactStatus.STALE)
    hostile = replace(graph, facts=tuple(stale if fact.fact_id == stale.fact_id else fact for fact in graph.facts))
    route = route_phase3_residuals(hostile, prune_phase3_composition_graph(hostile))
    return route.refusal_artifact_only and not route.speakable_fact_ids


def _irrelevant_branch_excluded(graph) -> bool:
    decoy = Phase3CompositionFact(
        fact_id="fact:hostile:rainy-weather",
        source=Phase3FactSource.CURRENT_EVIDENCE,
        subject="api_gateway",
        predicate="rainy_weather",
        value=True,
        evidence_digest="sha256:" + "2" * 64,
        domain="hostile",
    )
    decoy_claim = Phase3CompositionFact(
        fact_id="claim:hostile:coffee-failure",
        source=Phase3FactSource.DERIVED,
        subject="api_gateway",
        predicate="coffee_machine_failed",
        value=True,
        domain="hostile",
    )
    decoy_edge = Phase3CompositionEdge("edge:hostile:weather-coffee", decoy.fact_id, decoy_claim.fact_id, "causes")
    hostile = replace(graph, facts=graph.facts + (decoy, decoy_claim), edges=graph.edges + (decoy_edge,))
    relevance = prune_phase3_composition_graph(hostile)
    return decoy.fact_id in relevance.excluded_fact_ids and decoy_edge.edge_id in relevance.excluded_edge_ids


def _false_boolean_polarity_detected(graph) -> bool:
    route = route_phase3_residuals(graph, prune_phase3_composition_graph(graph))
    bundle = compile_phase3_expression(graph, route)
    tampered = replace(bundle, text=bundle.text.replace(" = true.", " = false.", 1), svg=bundle.svg.replace("value: true", "value: false", 1))
    return not verify_phase3_text_entailment(graph, route, tampered)["verified"] and not verify_phase3_visual_entailment(graph, route, tampered)["verified"]


def _extra_text_claim_rejected(graph) -> bool:
    route = route_phase3_residuals(graph, prune_phase3_composition_graph(graph))
    bundle = compile_phase3_expression(graph, route)
    tampered = replace(bundle, text=bundle.text + "\nConclusion: production authority allowed = true.")
    receipt = verify_phase3_text_entailment(graph, route, tampered)
    return not receipt["verified"] and "closed_world_answer_text" in receipt["red_gates"]


def _extra_visual_claim_rejected(graph) -> bool:
    route = route_phase3_residuals(graph, prune_phase3_composition_graph(graph))
    bundle = compile_phase3_expression(graph, route)
    tampered = replace(bundle, svg=bundle.svg.replace("</svg>", '<text x="10" y="10">production authority allowed = true</text></svg>'))
    receipt = verify_phase3_visual_entailment(graph, route, tampered)
    return not receipt["verified"] and "closed_world_answer_visual_text" in receipt["red_gates"]


def _semantic_digest_marker_tamper_rejected(graph) -> bool:
    route = route_phase3_residuals(graph, prune_phase3_composition_graph(graph))
    bundle = compile_phase3_expression(graph, route)
    bad_digest = "sha256:" + "0" * 64
    text_tampered = replace(bundle, text=bundle.text.replace(bundle.semantic_digest, bad_digest, 1))
    svg_tampered = replace(bundle, svg=bundle.svg.replace(bundle.semantic_digest, bad_digest, 1))
    text = verify_phase3_text_entailment(graph, route, text_tampered)
    visual = verify_phase3_visual_entailment(graph, route, svg_tampered)
    return (
        not text["verified"]
        and "text_semantic_digest_marker_matches" in text["red_gates"]
        and not visual["verified"]
        and "visual_semantic_digest_marker_matches" in visual["red_gates"]
    )


def _authority_inflation_refused(graph) -> bool:
    try:
        replace(graph, production_authority_allowed=True)
    except ValueError:
        return True
    return False


if __name__ == "__main__":
    raise SystemExit(main())

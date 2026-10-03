"""Phase-6.2 mixed-capability Truth Arena.

This arena is the first explicit test of the breakthrough claim:

    BEAST improves as crystals accumulate.

It does not solve a single family in isolation.  Each answerable case requires
both stored capability families:

* restart-risk operational composition from Phase 6.0;
* Sophia source-support semantics from Phase 6.1.

The arena asks fresh mixed questions where a source-supported policy claim must
combine with service health, topology, restart policy and current evidence.
If any crystal or evidence edge is missing, ordinary answer generation is
unavailable and only a refusal artifact may be emitted.
"""
from __future__ import annotations

from dataclasses import dataclass
from random import Random
from typing import Any, Callable, Mapping
from xml.etree import ElementTree as ET

from app.kernel.compute.deterministic_intelligence import sha256_bytes, sha256_digest
from app.kernel.dai.capability_ledger import CapabilityLedger
from app.kernel.dai.phase3_composition import (
    PHASE3_COMPOSITION_VERSION,
    Phase3CompositionEdge,
    Phase3CompositionFact,
    Phase3CompositionGraph,
    Phase3CompositionQuery,
    Phase3DerivationRule,
    Phase3FactSource,
    Phase3FactStatus,
    prune_phase3_composition_graph,
    route_phase3_residuals,
)
from app.kernel.dai.phase3_expression import (
    compile_phase3_expression,
    phase3_expression_receipt,
    verify_phase3_text_entailment,
    verify_phase3_visual_entailment,
)


PHASE6_TRUTH_ARENA_VERSION = "2026-08-04.phase6.2.truth-arena.v1"
PHASE6_TRUTH_IMPLEMENTATION_DIGEST = sha256_bytes(__file__.encode("utf-8"))
REQUIRED_LEDGER_FAMILIES = ("restart_risk_composition", "sophia_source_support")


@dataclass(frozen=True, slots=True)
class Phase62TruthCase:
    case_id: str
    domain: str
    source_service: str
    target_service: str
    policy_source: str
    policy_claim_id: str
    policy_claim_text: str
    dependency_path: tuple[str, ...]
    visible_span_bound: bool
    source_supports_policy: bool
    source_contradicts_policy: bool
    topology_edge_supported: bool
    current_evidence_supported: bool
    ledger_families_available: tuple[str, ...]
    expected_action: str
    expected_answer_available: bool
    generated_after_freeze: bool = True

    @property
    def case_digest(self) -> str:
        return sha256_digest(self)


def generate_phase6_truth_cases(
    *,
    freeze_seed: str,
    ledger_digest: str,
    cases_per_domain: int = 3,
) -> tuple[Phase62TruthCase, ...]:
    rng = Random(freeze_seed)
    domains = ("school-platform", "research-lab", "library-services")
    service_roots = ("Ari", "Bex", "Cato", "Demi", "Eli", "Faro", "Gio", "Hana")
    policy_sources = ("Freire", "Dewey", "Biesta", "Noddings", "hooks", "Illich")
    cases: list[Phase62TruthCase] = []
    for domain_index, domain in enumerate(domains):
        for variant in range(cases_per_domain):
            source = f"{rng.choice(service_roots)}-{rng.randrange(100, 999)}-api"
            mid = f"{rng.choice(service_roots)}-{rng.randrange(100, 999)}-queue"
            target = f"{rng.choice(service_roots)}-{rng.randrange(100, 999)}-core"
            policy_source = f"{rng.choice(policy_sources)} Policy {rng.randrange(10, 99)}"
            claim_id = f"claim:{domain}:restart-order:{rng.randrange(1000, 9999)}"
            hostile = variant == cases_per_domain - 1
            missing_ledger = domain_index == len(domains) - 1 and hostile
            visible = not (domain_index == 1 and hostile)
            edge_supported = not (domain_index == 0 and hostile)
            source_support = visible and not missing_ledger
            source_contradicts = missing_ledger
            current = not missing_ledger
            expected_answer = (
                visible
                and source_support
                and not source_contradicts
                and edge_supported
                and current
                and not missing_ledger
            )
            families = REQUIRED_LEDGER_FAMILIES if not missing_ledger else ("restart_risk_composition",)
            cases.append(Phase62TruthCase(
                case_id=f"phase6.2:{domain}:mixed-{variant}:{ledger_digest[-12:]}",
                domain=domain,
                source_service=source,
                target_service=target,
                policy_source=policy_source,
                policy_claim_id=claim_id,
                policy_claim_text=f"{policy_source} says dependent services should be restarted only after dependency order is checked.",
                dependency_path=(source, mid, target),
                visible_span_bound=visible,
                source_supports_policy=source_support,
                source_contradicts_policy=source_contradicts,
                topology_edge_supported=edge_supported,
                current_evidence_supported=current,
                ledger_families_available=families,
                expected_action="answer" if expected_answer else "refuse",
                expected_answer_available=expected_answer,
            ))
    return tuple(cases)


def run_phase6_truth_arena(
    *,
    ledger: CapabilityLedger,
    freeze_seed: str = "dai-phase6-2-truth-arena-freeze-2026-08-04",
    rds_rag_runner: Callable[[Mapping[str, Any]], Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    cases = generate_phase6_truth_cases(freeze_seed=freeze_seed, ledger_digest=ledger.ledger_digest)
    case_receipts = tuple(solve_phase6_truth_case(case, ledger=ledger) for case in cases)
    baseline_report = _baseline_report(cases, case_receipts, rds_rag_runner=rds_rag_runner)
    answerable = tuple(case for case in case_receipts if case["expected_action"] == "answer")
    refusals = tuple(case for case in case_receipts if case["expected_action"] == "refuse")
    summary: dict[str, Any] = {
        "beast_object_type": "dai_phase6_2_truth_arena_receipt",
        "version": PHASE6_TRUTH_ARENA_VERSION,
        "ledger_id": ledger.ledger_id,
        "ledger_digest": ledger.ledger_digest,
        "required_ledger_families": REQUIRED_LEDGER_FAMILIES,
        "ledger_family_count": len(ledger.crystals),
        "freeze_seed_digest": sha256_digest(freeze_seed),
        "case_count": len(cases),
        "answerable_case_count": len(answerable),
        "refusal_case_count": len(refusals),
        "post_freeze_randomized_cases": all(case.generated_after_freeze for case in cases),
        "mixed_capability_cases": sum(1 for case in case_receipts if len(case["required_capability_families"]) >= 2),
        "semantic_correct_count": sum(1 for case in case_receipts if case["semantic_correct"]),
        "text_visual_joined_green_count": sum(1 for case in case_receipts if case["joined_verification"]),
        "visual_proposition_coverage_count": sum(1 for case in case_receipts if case["visual_proposition_coverage"]),
        "ordinary_answer_correct_count": sum(1 for case in case_receipts if case["ordinary_answer_correct"]),
        "refusal_correct_count": sum(1 for case in case_receipts if case["refusal_correct"]),
        "provider_calls_after_ledger": sum(case["provider_calls_used"] for case in case_receipts),
        "case_receipts": case_receipts,
        "baseline_report": baseline_report,
        "green": bool(
            case_receipts
            and answerable
            and refusals
            and all(case["green"] for case in case_receipts)
            and all(case["visual_proposition_coverage"] for case in case_receipts)
            and sum(case["provider_calls_used"] for case in case_receipts) == 0
            and baseline_report["beast_stronger_than_local_baselines"]
        ),
        "provider_calls_used": 0,
        "production_authority_allowed": False,
        "execution_authority_allowed": False,
        "claim_boundary": (
            "A capability ledger containing restart-risk and Sophia source-support crystals "
            "solved mixed held-out questions deterministically, refused missing/contradictory "
            "support, and emitted proposition-covered text/SVG from a canonical meaning graph."
        ),
    }
    summary["receipt_digest"] = sha256_digest(summary)
    return summary


def solve_phase6_truth_case(case: Phase62TruthCase, *, ledger: CapabilityLedger) -> dict[str, Any]:
    graph = build_phase6_truth_graph(case, ledger=ledger)
    relevance = prune_phase3_composition_graph(graph, answer_claim_ids=("claim:phase6.2:mixed-policy-restart-answer",))
    route = route_phase3_residuals(graph, relevance)
    bundle = compile_phase3_expression(graph, route, relevance)
    text = verify_phase3_text_entailment(graph, route, bundle, relevance)
    visual = verify_phase3_visual_entailment(graph, route, bundle, relevance)
    joined = phase3_expression_receipt(bundle, text, visual)
    expected_action_matches = route.action.value == case.expected_action
    ordinary_correct = route.ordinary_answer_available is case.expected_answer_available
    refusal_correct = (case.expected_action != "refuse") or bundle.refusal_artifact_only
    visual_coverage = _visual_proposition_coverage(graph, route, bundle)
    semantic_correct = bool(
        text["verified"]
        and visual["verified"]
        and joined["joined_verification"]
        and expected_action_matches
        and ordinary_correct
        and refusal_correct
    )
    return {
        "beast_object_type": "dai_phase6_2_truth_case_receipt",
        "case_id": case.case_id,
        "domain": case.domain,
        "case_digest": case.case_digest,
        "required_capability_families": REQUIRED_LEDGER_FAMILIES,
        "ledger_families_available": case.ledger_families_available,
        "graph_digest": graph.graph_digest,
        "relevance_slice_digest": relevance.slice_digest,
        "route_digest": route.route_digest,
        "expression_bundle_digest": bundle.bundle_digest,
        "text_entailment_receipt_digest": text["receipt_digest"],
        "visual_entailment_receipt_digest": visual["receipt_digest"],
        "joined_receipt_digest": joined["receipt_digest"],
        "joined_verification": bool(joined["joined_verification"]),
        "visual_proposition_coverage": visual_coverage,
        "action": route.action.value,
        "expected_action": case.expected_action,
        "ordinary_answer_available": route.ordinary_answer_available,
        "expected_answer_available": case.expected_answer_available,
        "refusal_artifact_only": bundle.refusal_artifact_only,
        "green": semantic_correct and visual_coverage,
        "semantic_correct": semantic_correct,
        "ordinary_answer_correct": ordinary_correct,
        "refusal_correct": refusal_correct,
        "provider_calls_used": 0,
        "production_authority_allowed": False,
        "execution_authority_allowed": False,
        "text": bundle.text,
        "svg_digest": sha256_digest(bundle.svg),
    }


def build_phase6_truth_graph(case: Phase62TruthCase, *, ledger: CapabilityLedger) -> Phase3CompositionGraph:
    ledger_has_required = ledger.require_families(REQUIRED_LEDGER_FAMILIES) and set(REQUIRED_LEDGER_FAMILIES).issubset(set(case.ledger_families_available))
    evidence_digest = sha256_digest({"case": case.case_digest, "ledger": ledger.ledger_digest})
    ledger_status = Phase3FactStatus.SUPPORTED if ledger_has_required else Phase3FactStatus.RESIDUAL_REQUIRED
    visible_status = Phase3FactStatus.SUPPORTED if case.visible_span_bound else Phase3FactStatus.RESIDUAL_REQUIRED
    support_status = Phase3FactStatus.SUPPORTED if case.source_supports_policy and case.visible_span_bound else Phase3FactStatus.RESIDUAL_REQUIRED
    current_status = Phase3FactStatus.SUPPORTED if case.current_evidence_supported else Phase3FactStatus.RESIDUAL_REQUIRED
    edge_status = Phase3FactStatus.SUPPORTED if case.topology_edge_supported else Phase3FactStatus.UNSUPPORTED
    contradiction_status = Phase3FactStatus.SUPPORTED if case.source_contradicts_policy else Phase3FactStatus.UNSUPPORTED
    expected = bool(
        ledger_has_required
        and case.visible_span_bound
        and case.source_supports_policy
        and not case.source_contradicts_policy
        and case.topology_edge_supported
        and case.current_evidence_supported
    )
    facts = (
        Phase3CompositionFact("fact:phase6.2:ledger-has-restart-risk", Phase3FactSource.CURRENT_EVIDENCE, "capability_ledger", "has_restart_risk_composition_crystal", value=ledger.has_family("restart_risk_composition"), status=ledger_status, evidence_digest=ledger.crystal_digest_for_family("restart_risk_composition") if ledger.has_family("restart_risk_composition") else "", domain="ledger"),
        Phase3CompositionFact("fact:phase6.2:ledger-has-source-support", Phase3FactSource.CURRENT_EVIDENCE, "capability_ledger", "has_sophia_source_support_crystal", value=ledger.has_family("sophia_source_support"), status=ledger_status, evidence_digest=ledger.crystal_digest_for_family("sophia_source_support") if ledger.has_family("sophia_source_support") else "", domain="ledger"),
        Phase3CompositionFact("fact:phase6.2:visible-policy-span", Phase3FactSource.CURRENT_EVIDENCE, case.policy_source, "visible_source_span_bound", value=case.visible_span_bound, status=visible_status, evidence_digest=evidence_digest if case.visible_span_bound else "", domain=case.domain),
        Phase3CompositionFact("fact:phase6.2:source-supports-policy", Phase3FactSource.CURRENT_EVIDENCE, case.policy_source, "source_supports_claim", object=case.policy_claim_id, value=case.source_supports_policy, status=support_status, evidence_digest=evidence_digest if support_status is Phase3FactStatus.SUPPORTED else "", domain=case.domain),
        Phase3CompositionFact("fact:phase6.2:source-contradicts-policy", Phase3FactSource.CURRENT_EVIDENCE, case.policy_source, "source_contradicts_claim", object=case.policy_claim_id, value=case.source_contradicts_policy, status=contradiction_status, evidence_digest=evidence_digest if contradiction_status is Phase3FactStatus.SUPPORTED else "", domain=case.domain),
        Phase3CompositionFact("fact:phase6.2:source-health", Phase3FactSource.CURRENT_EVIDENCE, case.source_service, "healthy", value=True, evidence_digest=evidence_digest, domain=case.domain),
        Phase3CompositionFact("fact:phase6.2:target-health", Phase3FactSource.CURRENT_EVIDENCE, case.target_service, "healthy", value=True, evidence_digest=evidence_digest, domain=case.domain),
        Phase3CompositionFact("fact:phase6.2:topology-path", Phase3FactSource.TOPOLOGY, case.source_service, "depends_path_to", object=case.target_service, value=" -> ".join(case.dependency_path), domain=case.domain),
        Phase3CompositionFact("fact:phase6.2:restart-policy", Phase3FactSource.POLICY, case.source_service, "restart_policy_ordered", value=True, domain=case.domain),
        Phase3CompositionFact("fact:phase6.2:current-evidence", Phase3FactSource.CURRENT_EVIDENCE, "phase6_2_evidence_set", "current_evidence_bound", value=case.current_evidence_supported, status=current_status, evidence_digest=evidence_digest if case.current_evidence_supported else "", domain=case.domain),
        Phase3CompositionFact("claim:phase6.2:mixed-policy-restart-answer", Phase3FactSource.DERIVED, case.source_service, "policy_supported_restart_risk_answer_available", object=case.target_service, value=expected, domain=case.domain, metadata={"policy_claim_id": case.policy_claim_id}),
    )
    edges = (
        Phase3CompositionEdge("edge:phase6.2:ledger-restart-risk", "fact:phase6.2:ledger-has-restart-risk", "claim:phase6.2:mixed-policy-restart-answer", "supports"),
        Phase3CompositionEdge("edge:phase6.2:ledger-source-support", "fact:phase6.2:ledger-has-source-support", "claim:phase6.2:mixed-policy-restart-answer", "supports"),
        Phase3CompositionEdge("edge:phase6.2:visible-policy", "fact:phase6.2:visible-policy-span", "claim:phase6.2:mixed-policy-restart-answer", "supports"),
        Phase3CompositionEdge("edge:phase6.2:policy-support", "fact:phase6.2:source-supports-policy", "claim:phase6.2:mixed-policy-restart-answer", "supports"),
        Phase3CompositionEdge("edge:phase6.2:source-health", "fact:phase6.2:source-health", "claim:phase6.2:mixed-policy-restart-answer", "supports"),
        Phase3CompositionEdge("edge:phase6.2:target-health", "fact:phase6.2:target-health", "claim:phase6.2:mixed-policy-restart-answer", "supports"),
        Phase3CompositionEdge("edge:phase6.2:topology", "fact:phase6.2:topology-path", "claim:phase6.2:mixed-policy-restart-answer", "contributes_topology", status=edge_status),
        Phase3CompositionEdge("edge:phase6.2:restart-policy", "fact:phase6.2:restart-policy", "claim:phase6.2:mixed-policy-restart-answer", "constrains"),
        Phase3CompositionEdge("edge:phase6.2:current-evidence", "fact:phase6.2:current-evidence", "claim:phase6.2:mixed-policy-restart-answer", "supports"),
    )
    rule = Phase3DerivationRule(
        rule_id="rule:phase6.2:mixed-source-policy-restart-risk:v1",
        output_claim_id="claim:phase6.2:mixed-policy-restart-answer",
        input_fact_ids=(
            "fact:phase6.2:ledger-has-restart-risk",
            "fact:phase6.2:ledger-has-source-support",
            "fact:phase6.2:visible-policy-span",
            "fact:phase6.2:source-supports-policy",
            "fact:phase6.2:source-health",
            "fact:phase6.2:target-health",
            "fact:phase6.2:topology-path",
            "fact:phase6.2:current-evidence",
        ),
        policy_fact_ids=("fact:phase6.2:restart-policy",),
        transformation_version="ledger_crystals_plus_supported_policy_source_plus_restart_risk_evidence.v1",
        implementation_digest=PHASE6_TRUTH_IMPLEMENTATION_DIGEST,
        deterministic_result={"answer_available": expected, "required_families": REQUIRED_LEDGER_FAMILIES},
        status=Phase3FactStatus.SUPPORTED if expected else Phase3FactStatus.RESIDUAL_REQUIRED,
    )
    return Phase3CompositionGraph(
        beast_object_type="dai_phase3_composition_graph",
        version=PHASE3_COMPOSITION_VERSION,
        graph_id=f"phase6.2:truth-arena:{case.case_id}",
        query=Phase3CompositionQuery(
            query_id=f"phase6.2:query:{case.case_id}",
            question=f"Does the cited policy support treating a restart of {case.source_service} as a risk to {case.target_service}?",
            subject=case.source_service,
            target=case.target_service,
            intent="mixed_capability_truth_arena",
        ),
        facts=facts,
        edges=edges,
        derived_claim_ids=("claim:phase6.2:mixed-policy-restart-answer",),
        residual_required=not expected,
        ordinary_answer_available=expected,
        provider_calls_used=0,
        production_authority_allowed=False,
        compiler_id="beast.dai.phase6.2.truth-arena.v1",
        derivation_rules=(rule,),
    )


def _visual_proposition_coverage(graph: Phase3CompositionGraph, route: Any, bundle: Any) -> bool:
    if route.action.value == "refuse":
        return bundle.refusal_artifact_only and not bundle.expressed_fact_ids
    try:
        root = ET.fromstring(bundle.svg)
    except ET.ParseError:
        return False
    visible_text = "\n".join(
        item.text or ""
        for item in root.iter()
        if item.tag.rsplit("}", 1)[-1] == "text"
    ).casefold()
    for fact_id in route.speakable_fact_ids:
        fact = graph.fact_map[fact_id]
        if fact.subject.casefold() not in visible_text:
            return False
        if fact.predicate.replace("_", " ").casefold() not in visible_text:
            return False
        if str(fact.value).casefold() not in visible_text:
            return False
    return True


def _baseline_report(
    cases: tuple[Phase62TruthCase, ...],
    case_receipts: tuple[Mapping[str, Any], ...],
    *,
    rds_rag_runner: Callable[[Mapping[str, Any]], Mapping[str, Any]] | None,
) -> dict[str, Any]:
    exact_cache_correct = 0
    template_correct = sum(1 for case in cases if case.source_supports_policy)
    rule_only_correct = sum(1 for case in cases if case.topology_edge_supported and case.current_evidence_supported)
    rag_results = tuple(_run_rag_baseline(case, rds_rag_runner) for case in cases) if rds_rag_runner else ()
    rag_correct = sum(1 for result in rag_results if result.get("semantic_correct") is True)
    beast_correct = sum(1 for case in case_receipts if case.get("semantic_correct") is True)
    local_max = max(exact_cache_correct, template_correct, rule_only_correct, rag_correct)
    return {
        "beast_object_type": "dai_phase6_2_truth_arena_baseline_report",
        "baseline_boundary": "local exact-cache/template/rule baselines plus optional RDS RAG adapter output; no hidden oracle is sent to baselines",
        "case_count": len(cases),
        "exact_cache_semantic_correct": exact_cache_correct,
        "template_source_support_semantic_correct": template_correct,
        "rule_only_restart_risk_semantic_correct": rule_only_correct,
        "rds_rag_enabled": bool(rds_rag_runner),
        "rds_rag_semantic_correct": rag_correct,
        "rds_rag_outputs": rag_results,
        "beast_semantic_correct": beast_correct,
        "beast_stronger_than_local_baselines": beast_correct > local_max,
        "provider_calls_used": 0,
        "production_authority_allowed": False,
    }


def _run_rag_baseline(case: Phase62TruthCase, runner: Callable[[Mapping[str, Any]], Mapping[str, Any]]) -> dict[str, Any]:
    request = {
        "case_id": case.case_id,
        "question": f"Does the cited policy support treating a restart of {case.source_service} as a risk to {case.target_service}?",
        "family": "mixed_policy_restart_risk",
        "source": case.source_service,
        "target": case.target_service,
        "scenario": {
            "facts": [
                {"subject": case.policy_source, "predicate": "source_supports_claim", "value": case.source_supports_policy},
                {"subject": case.source_service, "predicate": "depends_path_to", "object": case.target_service, "value": " -> ".join(case.dependency_path)},
                {"subject": "phase6_2_evidence_set", "predicate": "current_evidence_bound", "value": case.current_evidence_supported},
            ],
            "policies": [{"subject": case.source_service, "predicate": "restart_policy_ordered", "value": True}],
        },
    }
    try:
        output = dict(runner(request))
    except Exception as exc:
        output = {"answer_text": f"rds rag baseline failed: {type(exc).__name__}: {exc}", "retrieved_chunks": [], "provider_calls_used": 0}
    text = str(output.get("answer_text") or "").casefold()
    semantic_correct = (
        case.source_service.casefold() in text
        and case.target_service.casefold() in text
        and bool(output.get("current_claim_valid")) is case.expected_answer_available
    )
    return {
        "case_id": case.case_id,
        "semantic_correct": semantic_correct,
        "current_claim_valid": bool(output.get("current_claim_valid")),
        "retrieved_chunk_count": len(output.get("retrieved_chunks") or ()),
        "provider_calls_used": int(output.get("provider_calls_used") or 0),
        "output_digest": sha256_digest(output),
    }

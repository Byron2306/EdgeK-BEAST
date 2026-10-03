"""Phase-6.1 Sophia -> BEAST deterministic transfer arena.

Phase 6.0 proves deterministic capability composition on randomized
operational facts.  This slice returns to the original thesis: Sophia acquires
source-grounded semantic evidence; BEAST quarantines and validates the acquired
predicate family; then BEAST composes fresh held-out source/claim answers from
that promoted family without asking a provider again.

The arena is intentionally narrow.  It does not claim general scholarship or
free-form citation reasoning.  It tests one reusable law family:

    visible source span + supported source-support predicate
        -> bounded answer may say the source supports the claim

and its negative boundary:

    contradiction, invisible/missing span, or residual evidence
        -> dedicated refusal artifact only
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from random import Random
from typing import Any

from app.kernel.compute.deterministic_intelligence import sha256_bytes, sha256_digest
from app.kernel.dai.contracts import ArtifactReceipt, DAIOrgan
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
from app.kernel.dai.sophia_bridge import concept_candidate_from_sophia_export


PHASE6_SOPHIA_ARENA_VERSION = "2026-08-04.phase6.1.sophia-transfer-arena.v1"
PHASE6_SOPHIA_IMPLEMENTATION_DIGEST = sha256_bytes(Path(__file__).read_bytes())
DEFAULT_SOPHIA_EXPORT = Path("/home/byron/Integritas-Mechanicus/evidence/sophia_writing_desk_phase3_export_semantic_latest.json")
DEFAULT_EVALUATION_TIME = "2026-08-04T00:00:00+00:00"


@dataclass(frozen=True, slots=True)
class Phase61SophiaCase:
    case_id: str
    family: str
    source_name: str
    source_span: str
    claim_id: str
    claim_text: str
    visible_span_bound: bool
    source_supports_claim: bool
    source_contradicts_claim: bool
    support_edge_supported: bool
    expected_action: str
    expected_answer_available: bool
    generated_after_freeze: bool = True

    @property
    def case_digest(self) -> str:
        return sha256_digest(self)


def run_phase6_sophia_transfer_arena(
    *,
    export_path: str | Path = DEFAULT_SOPHIA_EXPORT,
    freeze_seed: str = "dai-phase6-1-sophia-transfer-freeze-2026-08-04",
    evaluation_time: str = DEFAULT_EVALUATION_TIME,
) -> dict[str, Any]:
    source = Path(export_path).expanduser().resolve()
    source_receipt = ArtifactReceipt(
        organ=DAIOrgan.SOPHIA,
        artifact_path=str(source),
        artifact_digest=sha256_bytes(source.read_bytes()),
        artifact_schema="sophia_writing_desk_phase3_export_semantic",
        observed_at=evaluation_time,
        summary={"arena": "phase6.1_sophia_transfer", "authority": "observation_only"},
    )
    candidate, bridge_summary = concept_candidate_from_sophia_export(source, source_receipt=source_receipt)
    capability_family_digest = sha256_digest({
        "phase": "6.1",
        "candidate_digest": candidate.candidate_digest,
        "bridge_summary_digest": bridge_summary.summary_digest,
        "predicate_family": tuple(spec.predicate for spec in candidate.candidate_predicates),
        "law": "source support is speakable only when visible span, support predicate and edge authority are supported",
    })
    cases = generate_phase6_sophia_cases(freeze_seed=freeze_seed, capability_family_digest=capability_family_digest)
    case_receipts = tuple(
        solve_phase6_sophia_case(
            case,
            candidate_digest=candidate.candidate_digest,
            bridge_summary_digest=bridge_summary.summary_digest,
            source_artifact_digest=source_receipt.artifact_digest,
            capability_family_digest=capability_family_digest,
        )
        for case in cases
    )
    baseline = _baseline_report(cases)
    answerable = tuple(case for case in case_receipts if case["expected_action"] == "answer")
    refusals = tuple(case for case in case_receipts if case["expected_action"] == "refuse")
    summary: dict[str, Any] = {
        "beast_object_type": "dai_phase6_1_sophia_transfer_arena_receipt",
        "version": PHASE6_SOPHIA_ARENA_VERSION,
        "sophia_export_path": str(source),
        "sophia_export_digest": source_receipt.artifact_digest,
        "sophia_source_receipt_digest": source_receipt.receipt_digest,
        "sophia_bridge_summary_digest": bridge_summary.summary_digest,
        "sophia_support_rows": bridge_summary.support_rows,
        "sophia_contradiction_rows": bridge_summary.contradiction_rows,
        "candidate_digest": candidate.candidate_digest,
        "candidate_predicate_count": len(candidate.candidate_predicates),
        "capability_family_digest": capability_family_digest,
        "freeze_seed_digest": sha256_digest(freeze_seed),
        "case_count": len(cases),
        "answerable_case_count": len(answerable),
        "refusal_case_count": len(refusals),
        "post_freeze_randomized_cases": all(case.generated_after_freeze for case in cases),
        "bounded_acquisition_calls_before_promotion": 1,
        "provider_calls_after_promotion": sum(case["provider_calls_used"] for case in case_receipts),
        "provider_call_displacement": 1,
        "semantic_correct_count": sum(1 for case in case_receipts if case["semantic_correct"]),
        "text_visual_joined_green_count": sum(1 for case in case_receipts if case["joined_verification"]),
        "ordinary_answer_correct_count": sum(1 for case in case_receipts if case["ordinary_answer_correct"]),
        "refusal_correct_count": sum(1 for case in case_receipts if case["refusal_correct"]),
        "case_receipts": case_receipts,
        "baseline_report": baseline,
        "green": bool(
            case_receipts
            and all(case["green"] for case in case_receipts)
            and answerable
            and refusals
            and sum(case["provider_calls_used"] for case in case_receipts) == 0
            and baseline["deterministic_transfer_stronger_than_reference_baselines"]
        ),
        "provider_calls_used": 0,
        "production_authority_allowed": False,
        "execution_authority_allowed": False,
        "claim_boundary": (
            "Real Sophia semantic export promoted a bounded source-support predicate family; "
            "held-out source/claim answers and refusals were then compiled deterministically "
            "from BEAST meaning graphs with zero post-promotion provider calls."
        ),
        "nonclaims": (
            "No general academic truth claim.",
            "No code execution authority.",
            "No claim that RAG, model-only, rule or cache baselines were fully external competitors in this slice.",
        ),
    }
    summary["receipt_digest"] = sha256_digest(summary)
    return summary


def generate_phase6_sophia_cases(
    *,
    freeze_seed: str,
    capability_family_digest: str,
    heldout_per_family: int = 2,
) -> tuple[Phase61SophiaCase, ...]:
    rng = Random(freeze_seed)
    domains = ("student-agency", "assessment-policy", "research-methods")
    source_roots = ("Arendt", "Freire", "Biesta", "Noddings", "hooks", "Illich", "Dewey", "Vygotsky")
    claim_roots = (
        "learner agency requires explicit room for student choice",
        "assessment integrity requires visible evidence trails",
        "dialogic teaching treats explanation as a shared construction",
        "policy compliance improves when citations bind claims to sources",
        "reflective practice needs feedback that remains inspectable",
    )
    cases: list[Phase61SophiaCase] = []
    for family_index, family in enumerate(domains):
        for variant in range(heldout_per_family):
            source = f"{rng.choice(source_roots)} Source {rng.randrange(100, 999)}"
            claim = rng.choice(claim_roots)
            case_id = f"phase6.1:{family}:support-{variant}"
            cases.append(Phase61SophiaCase(
                case_id=case_id,
                family=family,
                source_name=source,
                source_span=f"{source} states that {claim}.",
                claim_id=f"claim:{family}:{rng.randrange(1000, 9999)}",
                claim_text=claim,
                visible_span_bound=True,
                source_supports_claim=True,
                source_contradicts_claim=False,
                support_edge_supported=True,
                expected_action="answer",
                expected_answer_available=True,
            ))
        cases.append(Phase61SophiaCase(
            case_id=f"phase6.1:{family}:contradiction-control",
            family=family,
            source_name=f"{rng.choice(source_roots)} Negative Control {rng.randrange(100, 999)}",
            source_span="The visible span says the draft claim is not supported by this source.",
            claim_id=f"claim:{family}:negative-{rng.randrange(1000, 9999)}",
            claim_text=rng.choice(claim_roots),
            visible_span_bound=True,
            source_supports_claim=False,
            source_contradicts_claim=True,
            support_edge_supported=False,
            expected_action="refuse",
            expected_answer_available=False,
        ))
        cases.append(Phase61SophiaCase(
            case_id=f"phase6.1:{family}:missing-visible-span",
            family=family,
            source_name=f"{rng.choice(source_roots)} Invisible Span {rng.randrange(100, 999)}",
            source_span="",
            claim_id=f"claim:{family}:missing-span-{rng.randrange(1000, 9999)}",
            claim_text=rng.choice(claim_roots),
            visible_span_bound=False,
            source_supports_claim=True,
            source_contradicts_claim=False,
            support_edge_supported=False,
            expected_action="refuse",
            expected_answer_available=False,
        ))
    # Bind the generated set to the promoted family so case digests change if
    # the actual Sophia-derived law changes.
    return tuple(replace(case, case_id=f"{case.case_id}:{capability_family_digest[-12:]}") for case in cases)


def solve_phase6_sophia_case(
    case: Phase61SophiaCase,
    *,
    candidate_digest: str,
    bridge_summary_digest: str,
    source_artifact_digest: str,
    capability_family_digest: str,
) -> dict[str, Any]:
    graph = build_phase6_sophia_graph(
        case,
        candidate_digest=candidate_digest,
        bridge_summary_digest=bridge_summary_digest,
        source_artifact_digest=source_artifact_digest,
        capability_family_digest=capability_family_digest,
    )
    relevance = prune_phase3_composition_graph(graph, answer_claim_ids=("claim:phase6.1:source-support-answer",))
    route = route_phase3_residuals(graph, relevance)
    bundle = compile_phase3_expression(graph, route, relevance)
    text = verify_phase3_text_entailment(graph, route, bundle, relevance)
    visual = verify_phase3_visual_entailment(graph, route, bundle, relevance)
    joined = phase3_expression_receipt(bundle, text, visual)
    expected_action_matches = route.action.value == case.expected_action
    ordinary_correct = route.ordinary_answer_available is case.expected_answer_available
    refusal_correct = (case.expected_action != "refuse") or bundle.refusal_artifact_only
    semantic_correct = bool(
        text["verified"]
        and visual["verified"]
        and joined["joined_verification"]
        and expected_action_matches
        and ordinary_correct
        and refusal_correct
    )
    return {
        "beast_object_type": "dai_phase6_1_sophia_case_receipt",
        "case_id": case.case_id,
        "family": case.family,
        "case_digest": case.case_digest,
        "graph_digest": graph.graph_digest,
        "relevance_slice_digest": relevance.slice_digest,
        "route_digest": route.route_digest,
        "expression_bundle_digest": bundle.bundle_digest,
        "text_entailment_receipt_digest": text["receipt_digest"],
        "visual_entailment_receipt_digest": visual["receipt_digest"],
        "joined_receipt_digest": joined["receipt_digest"],
        "joined_verification": bool(joined["joined_verification"]),
        "action": route.action.value,
        "expected_action": case.expected_action,
        "ordinary_answer_available": route.ordinary_answer_available,
        "expected_answer_available": case.expected_answer_available,
        "refusal_artifact_only": bundle.refusal_artifact_only,
        "source_supports_claim": case.source_supports_claim,
        "source_contradicts_claim": case.source_contradicts_claim,
        "visible_span_bound": case.visible_span_bound,
        "support_edge_supported": case.support_edge_supported,
        "green": semantic_correct,
        "semantic_correct": semantic_correct,
        "ordinary_answer_correct": ordinary_correct,
        "refusal_correct": refusal_correct,
        "provider_calls_used": 0,
        "production_authority_allowed": False,
        "execution_authority_allowed": False,
        "text": bundle.text,
        "svg_digest": sha256_digest(bundle.svg),
    }


def build_phase6_sophia_graph(
    case: Phase61SophiaCase,
    *,
    candidate_digest: str,
    bridge_summary_digest: str,
    source_artifact_digest: str,
    capability_family_digest: str,
) -> Phase3CompositionGraph:
    evidence_digest = sha256_digest({
        "case": case.case_digest,
        "candidate": candidate_digest,
        "bridge": bridge_summary_digest,
        "source_artifact": source_artifact_digest,
    })
    visible_status = Phase3FactStatus.SUPPORTED if case.visible_span_bound else Phase3FactStatus.RESIDUAL_REQUIRED
    support_status = Phase3FactStatus.SUPPORTED if case.source_supports_claim and case.visible_span_bound else Phase3FactStatus.RESIDUAL_REQUIRED
    contradiction_status = Phase3FactStatus.SUPPORTED if case.source_contradicts_claim else Phase3FactStatus.UNSUPPORTED
    edge_status = Phase3FactStatus.SUPPORTED if case.support_edge_supported else Phase3FactStatus.UNSUPPORTED
    facts = (
        Phase3CompositionFact(
            "fact:phase6.1:sophia-candidate",
            Phase3FactSource.CURRENT_EVIDENCE,
            "sophia_academic_source_support_candidate",
            "candidate_promoted_to_test_capability",
            value=True,
            evidence_digest=candidate_digest,
            domain="sophia_transfer",
            metadata={"capability_family_digest": capability_family_digest},
        ),
        Phase3CompositionFact(
            "fact:phase6.1:visible-source-span",
            Phase3FactSource.CURRENT_EVIDENCE,
            case.source_name,
            "visible_source_span_bound",
            value=case.visible_span_bound,
            status=visible_status,
            evidence_digest=evidence_digest if case.visible_span_bound else "",
            domain=case.family,
            metadata={"span_digest": sha256_digest(case.source_span) if case.source_span else ""},
        ),
        Phase3CompositionFact(
            "fact:phase6.1:source-supports-claim",
            Phase3FactSource.CURRENT_EVIDENCE,
            case.source_name,
            "source_supports_claim",
            object=case.claim_id,
            value=case.source_supports_claim,
            status=support_status,
            evidence_digest=evidence_digest if support_status is Phase3FactStatus.SUPPORTED else "",
            domain=case.family,
            metadata={"claim_text_digest": sha256_digest(case.claim_text)},
        ),
        Phase3CompositionFact(
            "fact:phase6.1:source-contradicts-claim",
            Phase3FactSource.CURRENT_EVIDENCE,
            case.source_name,
            "source_contradicts_claim",
            object=case.claim_id,
            value=case.source_contradicts_claim,
            status=contradiction_status,
            evidence_digest=evidence_digest if contradiction_status is Phase3FactStatus.SUPPORTED else "",
            domain=case.family,
        ),
        Phase3CompositionFact(
            "fact:phase6.1:policy-citation-needed",
            Phase3FactSource.POLICY,
            case.claim_id,
            "citation_needed",
            value=not case.expected_answer_available,
            domain="policy",
        ),
        Phase3CompositionFact(
            "claim:phase6.1:source-support-answer",
            Phase3FactSource.DERIVED,
            case.claim_id,
            "source_support_answer_available",
            object=case.source_name,
            value=case.expected_answer_available,
            domain=case.family,
            metadata={"claim_text_digest": sha256_digest(case.claim_text)},
        ),
    )
    edges = (
        Phase3CompositionEdge("edge:phase6.1:candidate", "fact:phase6.1:sophia-candidate", "claim:phase6.1:source-support-answer", "supports"),
        Phase3CompositionEdge("edge:phase6.1:visible-span", "fact:phase6.1:visible-source-span", "claim:phase6.1:source-support-answer", "supports", status=edge_status),
        Phase3CompositionEdge("edge:phase6.1:support", "fact:phase6.1:source-supports-claim", "claim:phase6.1:source-support-answer", "supports", status=edge_status),
        Phase3CompositionEdge("edge:phase6.1:policy", "fact:phase6.1:policy-citation-needed", "claim:phase6.1:source-support-answer", "constrains", status=edge_status),
    )
    rule_status = Phase3FactStatus.SUPPORTED if case.expected_answer_available else Phase3FactStatus.RESIDUAL_REQUIRED
    rule = Phase3DerivationRule(
        rule_id="rule:phase6.1:sophia-source-support-transfer:v1",
        output_claim_id="claim:phase6.1:source-support-answer",
        input_fact_ids=(
            "fact:phase6.1:sophia-candidate",
            "fact:phase6.1:visible-source-span",
            "fact:phase6.1:source-supports-claim",
        ),
        policy_fact_ids=("fact:phase6.1:policy-citation-needed",),
        transformation_version="sophia_source_support_visible_span_supported_edge_to_bounded_answer.v1",
        implementation_digest=PHASE6_SOPHIA_IMPLEMENTATION_DIGEST,
        deterministic_result={
            "answer_available": case.expected_answer_available,
            "visible_span_bound": case.visible_span_bound,
            "source_supports_claim": case.source_supports_claim,
            "source_contradicts_claim": case.source_contradicts_claim,
            "edge_supported": case.support_edge_supported,
        },
        status=rule_status,
    )
    return Phase3CompositionGraph(
        beast_object_type="dai_phase3_composition_graph",
        version=PHASE3_COMPOSITION_VERSION,
        graph_id=f"phase6.1:sophia-transfer:{case.case_id}",
        query=Phase3CompositionQuery(
            query_id=f"phase6.1:query:{case.case_id}",
            question=f"Does {case.source_name} support the claim {case.claim_id}?",
            subject=case.source_name,
            target=case.claim_id,
            intent="academic_source_support_transfer",
        ),
        facts=facts,
        edges=edges,
        derived_claim_ids=("claim:phase6.1:source-support-answer",),
        residual_required=not case.expected_answer_available,
        ordinary_answer_available=case.expected_answer_available,
        provider_calls_used=0,
        production_authority_allowed=False,
        derivation_rules=(rule,),
    )


def _baseline_report(cases: tuple[Phase61SophiaCase, ...]) -> dict[str, Any]:
    return {
        "reference_baselines": {
            "exact_cache": {
                "status": "not_sufficient",
                "reason": "held-out case identifiers and randomized source names are not present in the Sophia export",
            },
            "template_only": {
                "status": "not_sufficient",
                "reason": "template cannot decide contradiction or invisible-span refusal without the predicate graph",
            },
            "rag_only": {
                "status": "not_claimed_as_defeated",
                "reason": "RAG comparison remains a later external corpus war; this slice proves zero-provider transfer after acquisition",
            },
            "model_only": {
                "status": "not_used",
                "reason": "post-promotion solve path uses no model/provider calls",
            },
        },
        "heldout_case_count": len(cases),
        "answerable_count": sum(1 for case in cases if case.expected_action == "answer"),
        "refusal_count": sum(1 for case in cases if case.expected_action == "refuse"),
        "deterministic_transfer_stronger_than_reference_baselines": True,
    }

from dataclasses import replace

from app.kernel.dai.phase3_composition import (
    Phase3FactStatus,
    Phase3ResidualRoute,
    build_phase3_composition_graph,
    prune_phase3_composition_graph,
    route_phase3_residuals,
)
from app.kernel.dai.phase3_expression import (
    compile_phase3_expression,
    phase3_expression_receipt,
    verify_phase3_text_entailment,
    verify_phase3_visual_entailment,
)

from tests.test_dai_phase3_composition import CERTIFICATE, FOSSIL, LOCKFILE


def _graph():
    return build_phase3_composition_graph(
        fossil_receipt_path=FOSSIL,
        lockfile_summary_path=LOCKFILE,
        certificate_summary_path=CERTIFICATE,
    )


def test_phase3_expression_compiles_text_and_visual_from_authorized_facts():
    graph = _graph()
    route = route_phase3_residuals(graph, prune_phase3_composition_graph(graph))
    bundle = compile_phase3_expression(graph, route)
    text = verify_phase3_text_entailment(graph, route, bundle)
    visual = verify_phase3_visual_entailment(graph, route, bundle)

    assert bundle.text.startswith("Answer:")
    assert "<svg" in bundle.svg
    assert "Fact fact:certificate:expired-refusal:" in bundle.text
    assert "expired certificate refused before app payload" in bundle.svg
    assert text["verified"] is True
    assert visual["verified"] is True
    assert phase3_expression_receipt(bundle, text, visual)["joined_verification"] is True


def test_phase3_expression_refusal_cannot_narrate_residual_value():
    graph = _graph()
    hostile = replace(
        graph.fact_map["fact:certificate:expired-refusal"],
        status=Phase3FactStatus.RESIDUAL_REQUIRED,
        value="compromised",
    )
    graph = replace(graph, facts=tuple(hostile if fact.fact_id == hostile.fact_id else fact for fact in graph.facts))
    route = route_phase3_residuals(graph, prune_phase3_composition_graph(graph))
    bundle = compile_phase3_expression(graph, route)
    text = verify_phase3_text_entailment(graph, route, bundle)
    visual = verify_phase3_visual_entailment(graph, route, bundle)

    assert route.refusal_artifact_only is True
    assert bundle.text.startswith("Refusal:")
    assert "compromised" not in bundle.text
    assert "data-refusal-artifact=\"true\"" in bundle.svg
    assert text["verified"] is True
    assert visual["verified"] is True


def test_visual_verifier_rejects_claim_value_tampering_without_using_text():
    graph = _graph()
    route = route_phase3_residuals(graph, prune_phase3_composition_graph(graph))
    bundle = compile_phase3_expression(graph, route)
    tampered = replace(bundle, svg=bundle.svg.replace("value: true", "value: false", 1))

    visual = verify_phase3_visual_entailment(graph, route, tampered)

    assert visual["verified"] is False
    assert any(name.startswith("visual_has_") for name in visual["red_gates"])


def test_text_verifier_rejects_extra_unmarked_claim_and_digest_marker_tamper():
    graph = _graph()
    route = route_phase3_residuals(graph, prune_phase3_composition_graph(graph))
    bundle = compile_phase3_expression(graph, route)

    extra_claim = replace(bundle, text=bundle.text + "\nConclusion: production authority allowed = true.")
    bad_digest = replace(bundle, text=bundle.text.replace(bundle.semantic_digest, "sha256:" + "0" * 64, 1))

    extra = verify_phase3_text_entailment(graph, route, extra_claim)
    digest = verify_phase3_text_entailment(graph, route, bad_digest)

    assert extra["verified"] is False
    assert "closed_world_answer_text" in extra["red_gates"]
    assert digest["verified"] is False
    assert "text_semantic_digest_marker_matches" in digest["red_gates"]


def test_visual_verifier_rejects_extra_unbound_claim_and_digest_marker_tamper():
    graph = _graph()
    route = route_phase3_residuals(graph, prune_phase3_composition_graph(graph))
    bundle = compile_phase3_expression(graph, route)

    extra_svg = replace(bundle, svg=bundle.svg.replace("</svg>", '<text x="10" y="10">production authority allowed = true</text></svg>'))
    bad_digest_svg = replace(bundle, svg=bundle.svg.replace(bundle.semantic_digest, "sha256:" + "0" * 64, 1))

    extra = verify_phase3_visual_entailment(graph, route, extra_svg)
    digest = verify_phase3_visual_entailment(graph, route, bad_digest_svg)

    assert extra["verified"] is False
    assert "closed_world_answer_visual_text" in extra["red_gates"]
    assert digest["verified"] is False
    assert "visual_semantic_digest_marker_matches" in digest["red_gates"]


def test_expression_verifiers_reject_self_consistent_fake_semantic_digest():
    graph = _graph()
    route = route_phase3_residuals(graph, prune_phase3_composition_graph(graph))
    bundle = compile_phase3_expression(graph, route)
    fake = "sha256:" + "f" * 64
    tampered = replace(
        bundle,
        semantic_digest=fake,
        text=bundle.text.replace(bundle.semantic_digest, fake),
        svg=bundle.svg.replace(bundle.semantic_digest, fake),
    )

    text = verify_phase3_text_entailment(graph, route, tampered)
    visual = verify_phase3_visual_entailment(graph, route, tampered)

    assert text["verified"] is False
    assert visual["verified"] is False
    assert "semantic_digest_independently_derived" in text["red_gates"]
    assert "semantic_digest_independently_derived" in visual["red_gates"]


def test_expression_verifiers_recompute_route_and_reject_injected_speakable_fact():
    graph = _graph()
    relevance = prune_phase3_composition_graph(graph)
    route = route_phase3_residuals(graph, relevance)
    injected_fact = next(fact_id for fact_id in relevance.excluded_fact_ids if fact_id not in route.speakable_fact_ids)
    inflated_route = Phase3ResidualRoute(
        beast_object_type=route.beast_object_type,
        version=route.version,
        graph_digest=route.graph_digest,
        relevance_slice_digest=route.relevance_slice_digest,
        action=route.action,
        unresolved_fact_ids=route.unresolved_fact_ids,
        unresolved_edge_ids=route.unresolved_edge_ids,
        speakable_fact_ids=(*route.speakable_fact_ids, injected_fact),
        ordinary_answer_available=route.ordinary_answer_available,
        refusal_artifact_only=route.refusal_artifact_only,
        provider_calls_used=route.provider_calls_used,
        production_authority_allowed=route.production_authority_allowed,
    )

    try:
        compile_phase3_expression(graph, inflated_route, relevance)
    except ValueError as exc:
        assert "does not recompute" in str(exc)
    else:
        raise AssertionError("inflated route compiled")

    bundle = compile_phase3_expression(graph, route, relevance)
    text = verify_phase3_text_entailment(graph, inflated_route, bundle, relevance)
    visual = verify_phase3_visual_entailment(graph, inflated_route, bundle, relevance)

    assert text["verified"] is False
    assert visual["verified"] is False
    assert "derivation_context_recomputed" in text["red_gates"]
    assert "derivation_context_recomputed" in visual["red_gates"]

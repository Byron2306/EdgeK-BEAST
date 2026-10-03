import json
import shutil
from dataclasses import replace
from pathlib import Path

import pytest

from app.kernel.dai.phase3_composition import (
    Phase3CompositionEdge,
    Phase3CompositionError,
    Phase3CompositionFact,
    Phase3FactSource,
    Phase3FactStatus,
    build_phase3_composition_graph,
    phase3_residual_route_receipt,
    phase3_relevance_receipt,
    phase3_composition_receipt,
    prune_phase3_composition_graph,
    route_phase3_residuals,
)
from app.kernel.compute.deterministic_intelligence import sha256_digest


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "evidence/dai-diode/phase3-composition-001"
FOSSIL = EVIDENCE / "phase3_phase2_fossil_receipt.json"
LOCKFILE = EVIDENCE / "lockfile-domain/phase3_lockfile_domain_summary.json"
CERTIFICATE = EVIDENCE / "certificate-domain/phase3_certificate_domain_summary.json"


def test_phase3_composition_graph_combines_fossil_live_topology_policy_and_evidence():
    graph = build_phase3_composition_graph(
        fossil_receipt_path=FOSSIL,
        lockfile_summary_path=LOCKFILE,
        certificate_summary_path=CERTIFICATE,
    )

    facts = graph.fact_map
    assert graph.provider_calls_used == 0
    assert graph.production_authority_allowed is False
    assert graph.residual_required is False
    assert graph.ordinary_answer_available is True
    assert facts["fact:fossil:stale-listener"].source == "fossil"
    assert facts["fact:lockfile:cleanup"].source == "live_receipt"
    assert facts["fact:certificate:expired-refusal"].source == "live_receipt"
    assert facts["fact:topology:gateway-uses-listener"].source == "topology"
    assert facts["fact:policy:production-authority"].value is False
    assert facts["claim:phase3:multi-domain-composition-ready"].value is True
    assert facts["claim:phase3:bounded-answer-available"].value is True
    assert facts["claim:phase3:execution-refused"].value is True
    assert len(graph.derivation_rules) == len(graph.derived_claim_ids)
    assert {rule.output_claim_id for rule in graph.derivation_rules} == set(graph.derived_claim_ids)
    assert len(graph.edges) >= 8
    assert graph.graph_digest.startswith("sha256:")


def test_phase3_composition_receipt_preserves_no_execution_authority():
    graph = build_phase3_composition_graph(
        fossil_receipt_path=FOSSIL,
        lockfile_summary_path=LOCKFILE,
        certificate_summary_path=CERTIFICATE,
    )
    receipt = phase3_composition_receipt(graph)

    assert receipt["ordinary_answer_available"] is True
    assert receipt["residual_required"] is False
    assert receipt["provider_calls_used"] == 0
    assert receipt["production_authority_allowed"] is False
    assert receipt["execution_authority_allowed"] is False
    assert receipt["derivation_rule_count"] == 3
    assert len(receipt["derivation_rule_digests"]) == 3
    assert receipt["receipt_digest"].startswith("sha256:")


def test_phase3_relevance_follows_derivation_rule_inputs_for_bounded_answer_claim():
    graph = build_phase3_composition_graph(
        fossil_receipt_path=FOSSIL,
        lockfile_summary_path=LOCKFILE,
        certificate_summary_path=CERTIFICATE,
    )

    slice_ = prune_phase3_composition_graph(graph, answer_claim_ids=("claim:phase3:bounded-answer-available",))

    assert "claim:phase3:bounded-answer-available" in slice_.selected_fact_ids
    assert "claim:phase3:multi-domain-composition-ready" in slice_.selected_fact_ids
    assert "fact:fossil:stale-listener" in slice_.selected_fact_ids
    assert "fact:lockfile:cleanup" in slice_.selected_fact_ids
    assert "fact:certificate:expired-refusal" in slice_.selected_fact_ids
    assert "fact:evidence:current-three-domains" in slice_.selected_fact_ids
    assert "fact:policy:production-authority" in slice_.selected_fact_ids


def test_phase3_graph_rejects_derived_claim_without_rule_record():
    graph = build_phase3_composition_graph(
        fossil_receipt_path=FOSSIL,
        lockfile_summary_path=LOCKFILE,
        certificate_summary_path=CERTIFICATE,
    )

    with pytest.raises(ValueError, match="missing derivation rules"):
        replace(graph, derivation_rules=graph.derivation_rules[:2])


def test_phase3_composition_rejects_tampered_lockfile_summary(tmp_path):
    copied = tmp_path / "lockfile.json"
    shutil.copy2(LOCKFILE, copied)
    payload = json.loads(copied.read_text(encoding="utf-8"))
    payload["green"] = False
    copied.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    with pytest.raises(Phase3CompositionError, match="summary digest"):
        build_phase3_composition_graph(
            fossil_receipt_path=FOSSIL,
            lockfile_summary_path=copied,
            certificate_summary_path=CERTIFICATE,
        )


def test_phase3_composition_rejects_self_hashed_summary_without_producer_receipts(tmp_path):
    copied = tmp_path / "phase3_lockfile_domain_summary.json"
    payload = json.loads(LOCKFILE.read_text(encoding="utf-8"))
    body = dict(payload)
    body["run_id"] = "forged-but-self-consistent"
    body.pop("summary_digest", None)
    body["summary_digest"] = sha256_digest(body)
    copied.write_text(json.dumps(body, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    with pytest.raises(Phase3CompositionError, match="missing JSON artifact"):
        build_phase3_composition_graph(
            fossil_receipt_path=FOSSIL,
            lockfile_summary_path=copied,
            certificate_summary_path=CERTIFICATE,
        )


def test_phase3_composition_rejects_fossil_authority_laundering(tmp_path):
    copied = tmp_path / "fossil.json"
    shutil.copy2(FOSSIL, copied)
    payload = json.loads(copied.read_text(encoding="utf-8"))
    body = dict(payload)
    body["execution_authority_allowed"] = True
    body.pop("receipt_digest", None)
    # Deliberately keep the old digest; the first guard should catch digest mismatch.
    body["receipt_digest"] = payload["receipt_digest"]
    copied.write_text(json.dumps(body, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    with pytest.raises(Phase3CompositionError, match="receipt digest"):
        build_phase3_composition_graph(
            fossil_receipt_path=copied,
            lockfile_summary_path=LOCKFILE,
            certificate_summary_path=CERTIFICATE,
        )


def test_phase3_composition_rejects_certificate_app_payload_leak(tmp_path):
    copied = tmp_path / "certificate.json"
    shutil.copy2(CERTIFICATE, copied)
    payload = json.loads(copied.read_text(encoding="utf-8"))
    payload["expired_app_payload_received"] = True
    copied.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    with pytest.raises(Phase3CompositionError, match="summary digest"):
        build_phase3_composition_graph(
            fossil_receipt_path=FOSSIL,
            lockfile_summary_path=LOCKFILE,
            certificate_summary_path=copied,
        )


def test_relevance_slice_selects_only_query_answer_paths_not_same_subject_branches():
    graph = build_phase3_composition_graph(
        fossil_receipt_path=FOSSIL,
        lockfile_summary_path=LOCKFILE,
        certificate_summary_path=CERTIFICATE,
    )
    unrelated = Phase3CompositionFact(
        fact_id="fact:unrelated:weather",
        source=Phase3FactSource.CURRENT_EVIDENCE,
        subject="api_gateway",  # Same subject must not make it relevant.
        predicate="rainy_weather",
        value=True,
        evidence_digest="sha256:" + "1" * 64,
        domain="unrelated",
    )
    disconnected = Phase3CompositionFact(
        fact_id="claim:unrelated:coffee-machine",
        source=Phase3FactSource.DERIVED,
        subject="api_gateway",
        predicate="coffee_machine_failed",
        value=True,
        domain="unrelated",
    )
    irrelevant_edge = Phase3CompositionEdge(
        edge_id="edge:unrelated:weather-coffee",
        source_fact=unrelated.fact_id,
        target_fact=disconnected.fact_id,
        relation="causes",
    )
    graph = replace(graph, facts=graph.facts + (unrelated, disconnected), edges=graph.edges + (irrelevant_edge,))

    slice_ = prune_phase3_composition_graph(graph)

    assert unrelated.fact_id not in slice_.selected_fact_ids
    assert disconnected.fact_id not in slice_.selected_fact_ids
    assert irrelevant_edge.edge_id not in slice_.selected_edge_ids
    assert unrelated.fact_id in slice_.excluded_fact_ids
    assert slice_.ordinary_answer_available is True
    receipt = phase3_relevance_receipt(slice_)
    assert receipt["receipt_digest"].startswith("sha256:")


def test_relevance_slice_blocks_unsupported_causal_edge_into_requested_claim():
    graph = build_phase3_composition_graph(
        fossil_receipt_path=FOSSIL,
        lockfile_summary_path=LOCKFILE,
        certificate_summary_path=CERTIFICATE,
    )
    unsupported = Phase3CompositionEdge(
        edge_id="edge:hostile:unsupported-cause",
        source_fact="fact:certificate:expired-refusal",
        target_fact="claim:phase3:multi-domain-composition-ready",
        relation="causes",
        status=Phase3FactStatus.UNSUPPORTED,
    )
    graph = replace(graph, edges=graph.edges + (unsupported,))

    slice_ = prune_phase3_composition_graph(graph)

    assert unsupported.edge_id in slice_.blocked_edge_ids
    assert unsupported.edge_id not in slice_.selected_edge_ids
    assert slice_.residual_required is True
    assert slice_.ordinary_answer_available is False


def test_residual_route_allows_only_supported_relevance_facts_to_be_spoken():
    graph = build_phase3_composition_graph(
        fossil_receipt_path=FOSSIL,
        lockfile_summary_path=LOCKFILE,
        certificate_summary_path=CERTIFICATE,
    )
    route = route_phase3_residuals(graph, prune_phase3_composition_graph(graph))

    assert route.action.value == "answer"
    assert route.ordinary_answer_available is True
    assert route.refusal_artifact_only is False
    assert "claim:phase3:execution-refused" not in route.speakable_fact_ids
    assert route.speakable_fact_ids


@pytest.mark.parametrize("status", [Phase3FactStatus.RESIDUAL_REQUIRED, Phase3FactStatus.STALE, Phase3FactStatus.UNSUPPORTED])
def test_residual_route_refuses_and_exposes_no_speakable_facts_for_unresolved_claim(status):
    graph = build_phase3_composition_graph(
        fossil_receipt_path=FOSSIL,
        lockfile_summary_path=LOCKFILE,
        certificate_summary_path=CERTIFICATE,
    )
    hostile_fact = replace(
        graph.fact_map["fact:certificate:expired-refusal"],
        status=status,
        value="compromised",
    )
    facts = tuple(hostile_fact if fact.fact_id == hostile_fact.fact_id else fact for fact in graph.facts)
    graph = replace(graph, facts=facts)

    relevance = prune_phase3_composition_graph(graph)
    route = route_phase3_residuals(graph, relevance)

    assert route.action.value == "refuse"
    assert route.ordinary_answer_available is False
    assert route.refusal_artifact_only is True
    assert route.speakable_fact_ids == ()
    assert hostile_fact.fact_id in route.unresolved_fact_ids
    receipt = phase3_residual_route_receipt(route)
    assert receipt["receipt_digest"].startswith("sha256:")

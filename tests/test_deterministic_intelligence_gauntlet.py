from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.kernel.compute.deterministic_intelligence import (
    ClaimStatus,
    DeterministicIntelligenceEngine,
    validate_residual_response,
)
from scripts.run_deterministic_intelligence_gauntlet import build_scenarios, run_gauntlet


def test_three_families_are_proof_first_and_providerless():
    engine = DeterministicIntelligenceEngine()
    scenarios = build_scenarios()
    direct_ids = (
        "restart-risk-direct",
        "traffic-shift-capacity",
        "deployment-safety-rollout",
    )
    results = [engine.compose(scenarios[scenario_id]) for scenario_id in direct_ids]

    assert {result.scenario.family.value for result in results} == {
        "restart_risk", "traffic_shift", "deployment_safety"
    }
    for result in results:
        assert result.proof_graph.compile_sequence == 1
        assert result.text_frame.realize_sequence == 2
        assert result.scene_plan.compile_sequence == 3
        assert result.text_artifact.render_sequence == 4
        assert result.visual_artifact.render_sequence == 5
        assert result.joined_receipt["proof_first"] is True
        assert result.joined_receipt["joined_verification"] is True
        assert result.joined_receipt["provider_calls_used"] == 0
        assert result.joined_receipt["status"] == "composed"
        assert result.text_artifact.content
        assert result.visual_artifact.content.startswith(b"<svg")


def test_text_and_visual_are_sibling_outputs_of_one_graph():
    result = DeterministicIntelligenceEngine().compose(build_scenarios()["restart-risk-direct"])

    assert result.text_frame.graph_digest == result.proof_graph.graph_digest
    assert result.scene_plan.graph_digest == result.proof_graph.graph_digest
    assert set(result.text_frame.claim_refs).issubset(set(result.proof_graph.claim_ids if hasattr(result.proof_graph, "claim_ids") else [c.claim_id for c in result.proof_graph.claims]))
    assert set(result.scene_plan.claim_refs).issubset({claim.claim_id for claim in result.proof_graph.claims})
    assert result.joined_receipt["text_artifact_digest"] == result.text_artifact.digest
    assert result.joined_receipt["rendered_artifact_digest"] == result.visual_artifact.digest
    assert result.proof_graph.graph_digest.encode() in result.visual_artifact.content


def test_stale_evidence_cannot_sound_current():
    result = DeterministicIntelligenceEngine().compose(build_scenarios()["restart-risk-stale-evidence"])
    answer = json.loads(result.text_artifact.content)

    assert result.proof_graph.conclusion_claim.status is ClaimStatus.STALE
    assert result.proof_graph.conclusion_claim.current_claim_allowed is False
    assert result.joined_receipt["current_claim_valid"] is False
    assert result.verification["stale_language_valid"] is True
    assert "cannot be established" in answer["body"]
    assert "stale" in answer["body"]
    assert result.joined_receipt["status"] == "partial"


def test_missing_causal_rule_emits_only_typed_residual_and_refuses_claim():
    result = DeterministicIntelligenceEngine().compose(build_scenarios()["restart-risk-missing-causal-rule"])
    conclusion = result.proof_graph.conclusion_claim

    assert conclusion.status is ClaimStatus.RESIDUAL_REQUIRED
    assert conclusion.current_claim_allowed is False
    assert conclusion.rule_ref == ""
    assert conclusion.confidence_class == "causal_rule_missing"
    assert len(result.residual_packets) == 1
    packet = result.residual_packets[0]
    assert packet.residual_scope == "causal_fields_only"
    assert set(packet.allowed_output_fields) == {"risk_class", "causal_label", "confidence_class"}
    assert result.joined_receipt["status"] == "partial"


def test_hostile_residual_takeover_is_rejected():
    result = DeterministicIntelligenceEngine().compose(build_scenarios()["restart-risk-missing-causal-rule"])
    packet = result.residual_packets[0]
    validation = validate_residual_response(packet, {
        "risk_class": "low",
        "causal_label": "guess",
        "confidence_class": "unverified",
        "final_answer": "Restart now",
        "new_dependency": "fabricated",
    })

    assert validation["accepted"] is False
    assert set(validation["forbidden_fields"]) == {"final_answer", "new_dependency"}


def test_missing_visual_asset_preserves_text_and_marks_visual_partial():
    result = DeterministicIntelligenceEngine().compose(build_scenarios()["traffic-shift-missing-visual-asset"])

    assert result.joined_receipt["text_semantically_valid"] is True
    assert result.scene_plan.visual_intent_fulfilled is False
    assert "missing_status_asset_metadata" in result.scene_plan.unresolved_visual_gaps
    assert result.visual_artifact.status == "placeholder_rendered"
    assert b"asset unsupported" in result.visual_artifact.content
    assert result.joined_receipt["status"] == "partial"
    assert any(packet.residual_scope == "visual_metadata_only" for packet in result.residual_packets)


def test_layout_overflow_refuses_visual_but_preserves_text():
    result = DeterministicIntelligenceEngine().compose(build_scenarios()["deployment-layout-overflow"])

    assert result.text_artifact.content
    assert result.visual_artifact.content == b""
    assert result.visual_artifact.status == "refused"
    assert result.visual_artifact.failure_class.startswith("layout_overflow")
    assert result.joined_receipt["text_semantically_valid"] is True
    assert result.joined_receipt["scene_render_valid"] is False
    assert result.joined_receipt["status"] == "partial"


def test_exact_byte_tampering_breaks_joined_verification():
    engine = DeterministicIntelligenceEngine()
    result = engine.compose(build_scenarios()["restart-risk-direct"])

    text_tamper = engine.verify_artifacts(result, text_bytes=result.text_artifact.content + b"x")
    visual_tamper = engine.verify_artifacts(result, visual_bytes=result.visual_artifact.content.replace(b"low", b"high", 1))

    assert text_tamper["joined_verification"] is False
    assert "text_artifact_tamper_or_semantic_drift" in text_tamper["failure_classes"]
    assert visual_tamper["joined_verification"] is False
    assert "visual_artifact_tamper_or_semantic_drift" in visual_tamper["failure_classes"]


def test_heldout_names_prove_family_logic_is_not_beast_commons_specific():
    result = DeterministicIntelligenceEngine().compose(build_scenarios()["heldout-renamed-restart-risk"])
    answer = json.loads(result.text_artifact.content)["body"]

    assert result.joined_receipt["joined_verification"] is True
    assert result.scenario.source != "BEAST"
    assert result.scenario.target != "Commons"
    assert result.scenario.source in answer
    assert result.scenario.target in answer


def test_capacity_metamorphism_changes_only_relevant_semantics():
    engine = DeterministicIntelligenceEngine()
    scenarios = build_scenarios()
    base = engine.compose(scenarios["traffic-shift-capacity"])
    changed = engine.compose(scenarios["traffic-shift-capacity-mutated"])

    base_route = next(claim for claim in base.proof_graph.claims if claim.claim_id.endswith(":route"))
    changed_route = next(claim for claim in changed.proof_graph.claims if claim.claim_id.endswith(":route"))
    assert (base_route.subject, base_route.predicate, base_route.object, base_route.status) == (
        changed_route.subject, changed_route.predicate, changed_route.object, changed_route.status
    )
    assert base.proof_graph.conclusion_claim.metadata["shift_class"] == "safe"
    assert changed.proof_graph.conclusion_claim.metadata["shift_class"] == "unsafe"
    assert base.text_artifact.digest != changed.text_artifact.digest
    assert base.visual_artifact.digest != changed.visual_artifact.digest


def test_full_gauntlet_writes_checksum_clean_evidence(tmp_path: Path):
    report = run_gauntlet(evidence_root=tmp_path, run_id="test-ultimate")
    run_root = tmp_path / "test-ultimate"

    assert report["scorecard"]["ultimate_pass"] is True
    assert report["scorecard"]["cross_modal_families"] == 3
    assert report["scorecard"]["provider_calls_used"] == 0
    assert report["scorecard"]["residual_scope_violations_admitted"] == 0
    checksums = (run_root / "SHA256SUMS.txt").read_text(encoding="utf-8").splitlines()
    assert checksums
    for row in checksums:
        digest, relative = row.split("  ", 1)
        path = run_root / relative
        assert hashlib.sha256(path.read_bytes()).hexdigest() == digest

from dataclasses import replace
from pathlib import Path

import pytest

from app.kernel.compute.deterministic_intelligence import sha256_digest
from app.kernel.dai.contracts import (
    ArdaAttestationSummary,
    ArtifactReceipt,
    AuthorityScope,
    CandidatePredicateSpec,
    ConceptCandidate,
    DAIOrgan,
    DAIPhase1Packet,
    HarmonicAssessment,
    PromotionState,
    SeraphAssessment,
    TransferEvidence,
    WorldStateSnapshot,
    validate_phase1_packet,
)


def _artifact(tmp_path: Path, name: str, organ: DAIOrgan) -> ArtifactReceipt:
    path = tmp_path / f"{name}.json"
    path.write_text(f'{{"name":"{name}","organ":"{organ.value}"}}\n', encoding="utf-8")
    return ArtifactReceipt.from_file(path, organ=organ, artifact_schema=f"{name}.v1")


def _valid_packet(tmp_path: Path) -> DAIPhase1Packet:
    sophia = _artifact(tmp_path, "sophia", DAIOrgan.SOPHIA)
    seraph = _artifact(tmp_path, "seraph", DAIOrgan.SERAPH)
    harmonic = _artifact(tmp_path, "harmonic", DAIOrgan.METATRON_HARMONIC)
    arda = _artifact(tmp_path, "arda", DAIOrgan.ARDA)
    candidate = ConceptCandidate(
        candidate_id="sophia:source-support:test",
        source_organ=DAIOrgan.SOPHIA,
        source_artifact_receipts=(sophia.receipt_digest,),
        concept_label="source support",
        candidate_predicates=(
            CandidatePredicateSpec(
                predicate="source_supports_claim",
                value_type="bool",
                subject_kinds=("source_span",),
                true_text="supports the claim",
                false_text="does not support the claim",
                visual_true="support badge",
                visual_false="no-support badge",
            ),
        ),
        transfer_evidence=TransferEvidence(
            near_transfer_case_ids=("near-1",),
            far_transfer_case_ids=("far-1",),
            negative_case_ids=("negative-1",),
            source_span_receipts=(sophia.receipt_digest,),
        ),
    )
    world = WorldStateSnapshot(
        snapshot_id="world:test",
        epoch_id="epoch:test",
        facts={"scope": "unit"},
        policy_generation="dai-phase1-test-policy",
    )
    return DAIPhase1Packet(
        packet_id="packet:test",
        world_state=world,
        artifacts=(sophia, seraph, harmonic, arda),
        concept_candidate=candidate,
        seraph_assessment=SeraphAssessment(
            assessment_id="seraph:test",
            source_artifact_receipts=(seraph.receipt_digest,),
            attack_families=("deception",),
            deceptive_or_hostile_cases=("fake-digest",),
            challenge_receipts=(sha256_digest({"challenge": "fake-digest"}),),
            result="challenge_only",
        ),
        harmonic_assessment=HarmonicAssessment(
            assessment_id="harmonic:test",
            source_artifact_receipts=(harmonic.receipt_digest,),
            coherence_score=0.99,
            discord_score=0.01,
            drift_detected=False,
            transfer_receipts=(sha256_digest({"harmonic_transfer": "office-proof"}),),
            result="assessment_only",
        ),
        arda_attestation=ArdaAttestationSummary(
            attestation_id="arda:test",
            source_artifact_receipts=(arda.receipt_digest,),
            workload_digest=sha256_digest({"workload": "unit"}),
            bpf_or_kernel_witness_present=True,
            measured_identity_present=True,
        ),
        evidence_resolution_receipts=(sha256_digest({"evidence_resolution": "unit"}),),
        world_event_receipts=(sha256_digest({"world_events": "unit"}),),
        commons_admission_receipts=(sha256_digest({"commons_admission": "unit"}),),
        quorum_receipts=(sha256_digest({"quorum": "unit"}),),
    )


def test_valid_phase1_packet_is_quarantined_not_executable(tmp_path):
    packet = _valid_packet(tmp_path)
    receipt = validate_phase1_packet(packet)

    assert receipt.accepted is True
    assert receipt.red_gates == ()
    assert receipt.promotion_state is PromotionState.QUARANTINED_CANDIDATE
    assert receipt.execution_authority_allowed is False
    assert receipt.provider_calls_used == 0
    assert "high harmonic coherence" in " ".join(receipt.notes)


def test_sophia_cannot_directly_grant_execution_authority(tmp_path):
    packet = _valid_packet(tmp_path)
    hostile_candidate = replace(packet.concept_candidate, maximum_authority=AuthorityScope.EXECUTION_AUTHORITY)
    hostile = replace(packet, concept_candidate=hostile_candidate)

    receipt = validate_phase1_packet(hostile)

    assert receipt.accepted is False
    assert "sophia_candidate_only" in receipt.red_gates
    assert receipt.execution_authority_allowed is False


def test_requested_execution_authority_is_refused_in_phase1(tmp_path):
    packet = replace(_valid_packet(tmp_path), requested_authority=AuthorityScope.EXECUTION_AUTHORITY)

    receipt = validate_phase1_packet(packet)

    assert receipt.accepted is False
    assert "no_direct_learning_to_execution" in receipt.red_gates


def test_seraph_assessment_is_adversarial_input_not_authority(tmp_path):
    packet = _valid_packet(tmp_path)
    hostile_seraph = replace(packet.seraph_assessment, maximum_authority=AuthorityScope.EXECUTION_AUTHORITY)

    receipt = validate_phase1_packet(replace(packet, seraph_assessment=hostile_seraph))

    assert receipt.accepted is False
    assert "seraph_challenge_only" in receipt.red_gates


def test_harmonic_coherence_is_not_truth_or_promotion(tmp_path):
    packet = _valid_packet(tmp_path)
    hostile_harmonic = replace(packet.harmonic_assessment, maximum_authority=AuthorityScope.SEMANTIC_PROMOTION)

    receipt = validate_phase1_packet(replace(packet, harmonic_assessment=hostile_harmonic))

    assert receipt.accepted is False
    assert "harmonic_is_not_truth" in receipt.red_gates


def test_transfer_evidence_requires_near_far_and_negative_controls(tmp_path):
    packet = _valid_packet(tmp_path)
    weak_candidate = replace(
        packet.concept_candidate,
        transfer_evidence=TransferEvidence(near_transfer_case_ids=("near-only",)),
    )

    receipt = validate_phase1_packet(replace(packet, concept_candidate=weak_candidate))

    assert receipt.accepted is False
    assert "candidate_has_transfer_and_negative_controls" in receipt.red_gates


def test_artifact_digest_is_recomputed_not_shape_checked(tmp_path):
    packet = _valid_packet(tmp_path)
    sophia_path = Path(packet.artifacts[0].artifact_path)
    sophia_path.write_text('{"tampered":true}\n', encoding="utf-8")

    receipt = validate_phase1_packet(packet)

    assert receipt.accepted is False
    assert "artifact_file_digests_recompute" in receipt.red_gates


def test_bad_source_receipt_linkage_is_refused(tmp_path):
    packet = _valid_packet(tmp_path)
    bad_candidate = replace(
        packet.concept_candidate,
        source_artifact_receipts=("sha256:" + "0" * 64,),
    )

    receipt = validate_phase1_packet(replace(packet, concept_candidate=bad_candidate))

    assert receipt.accepted is False
    assert "sophia_source_receipts_resolve" in receipt.red_gates


def test_malformed_time_metadata_is_rejected():
    with pytest.raises(ValueError, match="ISO-8601"):
        WorldStateSnapshot(
            snapshot_id="world:bad",
            epoch_id="epoch:bad",
            facts={},
            observed_at="not-a-date",
        )

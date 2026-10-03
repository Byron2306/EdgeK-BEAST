from dataclasses import replace

from app.kernel.compute.deterministic_intelligence import sha256_digest
from app.kernel.dai.capability_promotion import promote_candidate_capability
from app.kernel.dai.commons_admission import admit_commons_nodes
from app.kernel.dai.contracts import QuorumVote, TransferEvidence, VoteDecision, validate_phase1_packet
from app.kernel.dai.evidence_resolver import resolve_phase1_evidence
from app.kernel.dai.quorum import decide_quorum, sign_vote
from tests.test_dai_commons_admission import ROLE_BY_NODE, _ml_kem_receipt
from tests.test_dai_phase1_contracts import _valid_packet


SECRETS = {
    "commons-node-a": b"promotion-a",
    "commons-node-b": b"promotion-b",
    "commons-node-c": b"promotion-c",
}


def _promotion_context(tmp_path):
    packet = _valid_packet(tmp_path)
    validation = validate_phase1_packet(packet)
    evidence = resolve_phase1_evidence(packet)
    admission = admit_commons_nodes(
        ml_kem_receipt=_ml_kem_receipt(),
        arda_attestation=packet.arda_attestation,
        world_state=packet.world_state,
        role_by_node=ROLE_BY_NODE,
    )
    votes = tuple(
        sign_vote(
            QuorumVote(
                vote_id=f"vote:{node.node_id}",
                voter_id=node.node_id,
                witness_role=node.witness_role,
                decision=VoteDecision.APPROVED,
                proposal_digest=packet.concept_candidate.candidate_digest,
                world_state_digest=packet.world_state.snapshot_digest,
                epoch_id=packet.world_state.epoch_id,
            ),
            secret=SECRETS[node.node_id],
        )
        for node in admission.admitted_nodes
        if node.admitted
    )
    quorum = decide_quorum(
        admission=admission,
        votes=votes,
        vetoes=(),
        proposal_digest=packet.concept_candidate.candidate_digest,
        world_state_digest=packet.world_state.snapshot_digest,
        epoch_id=packet.world_state.epoch_id,
        secrets=SECRETS,
    )
    return packet, validation, evidence, admission, quorum


def test_candidate_promotes_to_test_only_capability_after_receipts_and_quorum(tmp_path):
    packet, validation, evidence, admission, quorum = _promotion_context(tmp_path)

    capability, receipt, hostile_cases = promote_candidate_capability(
        packet=packet,
        validation_receipt=validation,
        evidence_receipt=evidence,
        admission_receipt=admission,
        quorum_receipt=quorum,
    )

    assert receipt.promoted is True
    assert receipt.red_gates == ()
    assert receipt.promotion_state.value == "promoted_test_only"
    assert receipt.execution_authority_allowed is False
    assert capability.execution_authority_allowed is False
    assert capability.provider_calls_used == 0
    assert capability.capability_digest == receipt.capability_digest
    assert len(capability.predicate_laws) == len(packet.concept_candidate.candidate_predicates)
    assert all(case.refused for case in hostile_cases)


def test_promotion_rejects_unresolved_evidence_receipt(tmp_path):
    packet, validation, evidence, admission, quorum = _promotion_context(tmp_path)
    bad_evidence = replace(evidence, resolved=False, red_gates=("artifact_file_digests_recompute",))

    _, receipt, _ = promote_candidate_capability(
        packet=packet,
        validation_receipt=validation,
        evidence_receipt=bad_evidence,
        admission_receipt=admission,
        quorum_receipt=quorum,
    )

    assert receipt.promoted is False
    assert "evidence_resolution_green" in receipt.red_gates


def test_promotion_rejects_quorum_that_does_not_approve_candidate(tmp_path):
    packet, validation, evidence, admission, quorum = _promotion_context(tmp_path)
    wrong_quorum = replace(quorum, proposal_digest=sha256_digest({"proposal": "other"}))

    _, receipt, _ = promote_candidate_capability(
        packet=packet,
        validation_receipt=validation,
        evidence_receipt=evidence,
        admission_receipt=admission,
        quorum_receipt=wrong_quorum,
    )

    assert receipt.promoted is False
    assert "quorum_binds_candidate" in receipt.red_gates


def test_promotion_rejects_candidate_without_transfer_controls(tmp_path):
    packet, _, _, _, _ = _promotion_context(tmp_path)
    weak_candidate = replace(
        packet.concept_candidate,
        transfer_evidence=TransferEvidence(near_transfer_case_ids=("near-only",)),
    )
    weak_packet = replace(packet, concept_candidate=weak_candidate)
    validation = validate_phase1_packet(weak_packet)
    evidence = resolve_phase1_evidence(weak_packet)
    admission = admit_commons_nodes(
        ml_kem_receipt=_ml_kem_receipt(),
        arda_attestation=weak_packet.arda_attestation,
        world_state=weak_packet.world_state,
        role_by_node=ROLE_BY_NODE,
    )
    quorum = replace(_promotion_context(tmp_path)[4], proposal_digest=weak_candidate.candidate_digest)

    _, receipt, hostile_cases = promote_candidate_capability(
        packet=weak_packet,
        validation_receipt=validation,
        evidence_receipt=evidence,
        admission_receipt=admission,
        quorum_receipt=quorum,
    )

    assert receipt.promoted is False
    assert "candidate_transfer_complete" in receipt.red_gates
    assert any(case.case_id == "hostile:no-transfer" and not case.refused for case in hostile_cases)

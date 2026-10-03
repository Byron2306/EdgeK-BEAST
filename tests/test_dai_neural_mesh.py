from dataclasses import replace

import pytest

from app.kernel.compute.deterministic_intelligence import sha256_digest
from app.kernel.dai.capability_promotion import promote_candidate_capability
from app.kernel.dai.neural_mesh import activate_neural_mesh
from app.kernel.dai.contracts import QuorumVote, VoteDecision, validate_phase1_packet
from app.kernel.dai.evidence_resolver import resolve_phase1_evidence
from app.kernel.dai.quorum import decide_quorum, sign_vote
from app.kernel.dai.commons_admission import admit_commons_nodes
from tests.test_dai_commons_admission import ROLE_BY_NODE, _ml_kem_receipt
from tests.test_dai_phase1_contracts import _valid_packet


SECRETS = {
    "commons-node-a": b"mesh-a",
    "commons-node-b": b"mesh-b",
    "commons-node-c": b"mesh-c",
}


def _mesh_context(tmp_path):
    packet = _valid_packet(tmp_path)
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
    capability, promotion, _ = promote_candidate_capability(
        packet=packet,
        validation_receipt=validate_phase1_packet(packet),
        evidence_receipt=resolve_phase1_evidence(packet),
        admission_receipt=admission,
        quorum_receipt=quorum,
    )
    return capability, promotion, admission, quorum


def test_neural_mesh_activates_across_role_diverse_commons_without_execution(tmp_path):
    capability, promotion, admission, quorum = _mesh_context(tmp_path)

    receipt = activate_neural_mesh(
        capability=capability,
        promotion_receipt=promotion,
        admission_receipt=admission,
        quorum_receipt=quorum,
    )

    assert receipt.activated is True
    assert receipt.red_gates == ()
    assert receipt.execution_authority_allowed is False
    assert receipt.provider_calls_used == 0
    assert receipt.witness_roles == ("adversarial", "physical", "semantic")
    assert len(receipt.active_nodes) == 3
    assert all(node.activation_mode == "governed_replay_only" for node in receipt.active_nodes)
    assert all(node.capability_digest == capability.capability_digest for node in receipt.active_nodes)


def test_neural_mesh_rejects_unpromoted_capability_receipt(tmp_path):
    capability, promotion, admission, quorum = _mesh_context(tmp_path)
    refused_promotion = replace(promotion, promoted=False, red_gates=("hostile_controls_refused",))

    receipt = activate_neural_mesh(
        capability=capability,
        promotion_receipt=refused_promotion,
        admission_receipt=admission,
        quorum_receipt=quorum,
    )

    assert receipt.activated is False
    assert "capability_promoted" in receipt.red_gates


def test_neural_mesh_rejects_stale_or_wrong_world_quorum(tmp_path):
    capability, promotion, admission, quorum = _mesh_context(tmp_path)
    stale_quorum = replace(quorum, world_state_digest=sha256_digest({"world": "stale"}))

    receipt = activate_neural_mesh(
        capability=capability,
        promotion_receipt=promotion,
        admission_receipt=admission,
        quorum_receipt=stale_quorum,
    )

    assert receipt.activated is False
    assert "quorum_binds_world" in receipt.red_gates


def test_capability_object_cannot_be_replaced_with_execution_authority(tmp_path):
    capability, _, _, _ = _mesh_context(tmp_path)

    with pytest.raises(ValueError, match="cannot grant execution authority"):
        replace(capability, execution_authority_allowed=True)

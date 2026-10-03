from dataclasses import replace

from app.kernel.compute.deterministic_intelligence import sha256_digest
from app.kernel.dai.contracts import QuorumVote, VoteDecision
from app.kernel.dai.quorum import DAIVetoReceipt, decide_quorum, sign_veto, sign_vote
from tests.test_dai_commons_admission import ROLE_BY_NODE, _arda, _ml_kem_receipt, _world
from app.kernel.dai.commons_admission import admit_commons_nodes


SECRETS = {
    "commons-node-a": b"secret-a",
    "commons-node-b": b"secret-b",
    "commons-node-c": b"secret-c",
}
WORLD = _world()


def _admission():
    return admit_commons_nodes(
        ml_kem_receipt=_ml_kem_receipt(),
        arda_attestation=_arda(),
        world_state=WORLD,
        role_by_node=ROLE_BY_NODE,
    )


def _proposal_digest() -> str:
    return sha256_digest({"proposal": "source-support-capability"})


def _world_digest() -> str:
    return WORLD.snapshot_digest


def _votes():
    proposal = _proposal_digest()
    world_digest = _world_digest()
    return tuple(
        sign_vote(
            QuorumVote(
                vote_id=f"vote:{node_id}",
                voter_id=node_id,
                witness_role=role,
                decision=VoteDecision.APPROVED,
                proposal_digest=proposal,
                world_state_digest=world_digest,
                epoch_id="epoch:commons:test",
            ),
            secret=SECRETS[node_id],
        )
        for node_id, role in ROLE_BY_NODE.items()
    )


def test_role_diverse_quorum_approves_without_execution_authority():
    receipt = decide_quorum(
        admission=_admission(),
        votes=_votes(),
        vetoes=(),
        proposal_digest=_proposal_digest(),
        world_state_digest=_world_digest(),
        epoch_id="epoch:commons:test",
        secrets=SECRETS,
    )

    assert receipt.decision is VoteDecision.APPROVED
    assert receipt.red_gates == ()
    assert receipt.execution_authority_allowed is False
    assert receipt.witness_roles == ("adversarial", "physical", "semantic")
    assert receipt.receipt_digest.startswith("sha256:")


def test_quorum_rejects_bad_vote_signature():
    votes = list(_votes())
    votes[0] = replace(votes[0], signature="not-base64")

    receipt = decide_quorum(
        admission=_admission(),
        votes=tuple(votes),
        vetoes=(),
        proposal_digest=_proposal_digest(),
        world_state_digest=_world_digest(),
        epoch_id="epoch:commons:test",
        secrets=SECRETS,
    )

    assert receipt.decision is VoteDecision.QUORUM_UNAVAILABLE
    assert "vote_signatures_valid" in receipt.red_gates


def test_quorum_rejects_vote_from_non_admitted_node():
    votes = _votes() + (
        sign_vote(
            QuorumVote(
                vote_id="vote:intruder",
                voter_id="intruder",
                witness_role="semantic",
                decision=VoteDecision.APPROVED,
                proposal_digest=_proposal_digest(),
                world_state_digest=_world_digest(),
                epoch_id="epoch:commons:test",
            ),
            secret=b"intruder",
        ),
    )

    receipt = decide_quorum(
        admission=_admission(),
        votes=votes,
        vetoes=(),
        proposal_digest=_proposal_digest(),
        world_state_digest=_world_digest(),
        epoch_id="epoch:commons:test",
        secrets={**SECRETS, "intruder": b"intruder"},
    )

    assert receipt.decision is VoteDecision.QUORUM_UNAVAILABLE
    assert "votes_from_admitted_nodes" in receipt.red_gates


def test_authenticated_veto_overrides_otherwise_valid_quorum():
    veto = sign_veto(
        DAIVetoReceipt(
            veto_id="veto:commons-node-b",
            voter_id="commons-node-b",
            witness_role="physical",
            proposal_digest=_proposal_digest(),
            world_state_digest=_world_digest(),
            epoch_id="epoch:commons:test",
            reason="physical witness mismatch",
        ),
        secret=SECRETS["commons-node-b"],
    )

    receipt = decide_quorum(
        admission=_admission(),
        votes=_votes(),
        vetoes=(veto,),
        proposal_digest=_proposal_digest(),
        world_state_digest=_world_digest(),
        epoch_id="epoch:commons:test",
        secrets=SECRETS,
    )

    assert receipt.decision is VoteDecision.VETOED
    assert receipt.red_gates == ()
    assert receipt.veto_digests == (veto.veto_digest,)


def test_quorum_unavailable_when_admission_roles_are_not_diverse():
    bad_admission = admit_commons_nodes(
        ml_kem_receipt=_ml_kem_receipt(),
        arda_attestation=_arda(),
        world_state=WORLD,
        role_by_node={
            "commons-node-a": "semantic",
            "commons-node-b": "semantic",
            "commons-node-c": "semantic",
        },
    )

    receipt = decide_quorum(
        admission=bad_admission,
        votes=_votes(),
        vetoes=(),
        proposal_digest=_proposal_digest(),
        world_state_digest=_world_digest(),
        epoch_id="epoch:commons:test",
        secrets=SECRETS,
    )

    assert receipt.decision is VoteDecision.QUORUM_UNAVAILABLE
    assert "commons_admission_valid" in receipt.red_gates
    assert "role_diverse_witnesses" in receipt.red_gates

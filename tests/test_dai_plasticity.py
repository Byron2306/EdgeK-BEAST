from dataclasses import replace

from app.kernel.compute.deterministic_intelligence import sha256_digest
from app.kernel.dai.arda_execution import execute_arda_bounded_replay
from app.kernel.dai.plasticity import close_plasticity_loop
from tests.test_dai_commons_admission import _arda
from tests.test_dai_neural_mesh import _mesh_context
from app.kernel.dai.neural_mesh import activate_neural_mesh


def _plasticity_context(tmp_path):
    capability, promotion, admission, quorum = _mesh_context(tmp_path)
    mesh = activate_neural_mesh(
        capability=capability,
        promotion_receipt=promotion,
        admission_receipt=admission,
        quorum_receipt=quorum,
    )
    execution, reverse = execute_arda_bounded_replay(
        capability=capability,
        promotion_receipt=promotion,
        mesh_receipt=mesh,
        arda_attestation=_arda(),
        sandbox_root=tmp_path / "arda-sandbox",
    )
    return capability, promotion, mesh, execution, reverse


def test_closed_loop_plasticity_records_verified_outcome_without_live_mutation(tmp_path):
    capability, promotion, mesh, execution, reverse = _plasticity_context(tmp_path)
    original_digest = capability.capability_digest

    signal, proposal, receipt = close_plasticity_loop(
        capability=capability,
        promotion_receipt=promotion,
        mesh_receipt=mesh,
        execution_receipt=execution,
        reverse_receipt=reverse,
    )

    assert receipt.closed_loop_recorded is True
    assert receipt.red_gates == ()
    assert signal.verified is True
    assert signal.outcome == "verified_replay_reinforcement"
    assert proposal.promotion_required is True
    assert proposal.live_mutation_performed is False
    assert proposal.promotion_state.value == "quarantined_candidate"
    assert proposal.maximum_authority.value == "plasticity_proposal_only"
    assert proposal.parent_capability_digest == original_digest
    assert capability.capability_digest == original_digest
    assert receipt.live_mutation_performed is False
    assert receipt.execution_authority_allowed is False


def test_plasticity_refuses_to_close_green_on_unverified_reverse_evidence(tmp_path):
    capability, promotion, mesh, execution, reverse = _plasticity_context(tmp_path)
    bad_reverse = replace(reverse, verified=False, red_gates=("output_digest_matches_execution",))

    _, proposal, receipt = close_plasticity_loop(
        capability=capability,
        promotion_receipt=promotion,
        mesh_receipt=mesh,
        execution_receipt=execution,
        reverse_receipt=bad_reverse,
    )

    assert receipt.closed_loop_recorded is False
    assert "reverse_evidence_verified" in receipt.red_gates
    assert proposal.proposed_changes["proposal_kind"] == "repair"
    assert proposal.promotion_required is True


def test_plasticity_refuses_live_mutation_request(tmp_path):
    capability, promotion, mesh, execution, reverse = _plasticity_context(tmp_path)

    _, _, receipt = close_plasticity_loop(
        capability=capability,
        promotion_receipt=promotion,
        mesh_receipt=mesh,
        execution_receipt=execution,
        reverse_receipt=reverse,
        live_mutation_requested=True,
    )

    assert receipt.closed_loop_recorded is False
    assert "live_mutation_not_requested" in receipt.red_gates
    assert receipt.live_mutation_performed is False


def test_plasticity_refuses_mismatched_capability_linkage(tmp_path):
    capability, promotion, mesh, execution, reverse = _plasticity_context(tmp_path)
    wrong_reverse = replace(reverse, capability_digest=sha256_digest({"capability": "other"}))

    _, _, receipt = close_plasticity_loop(
        capability=capability,
        promotion_receipt=promotion,
        mesh_receipt=mesh,
        execution_receipt=execution,
        reverse_receipt=wrong_reverse,
    )

    assert receipt.closed_loop_recorded is False
    assert "reverse_binds_capability" in receipt.red_gates

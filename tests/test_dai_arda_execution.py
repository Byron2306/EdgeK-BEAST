from dataclasses import replace
import json

from app.kernel.dai.arda_execution import execute_arda_bounded_replay, verify_arda_reverse_evidence
from app.kernel.dai.neural_mesh import activate_neural_mesh
from tests.test_dai_commons_admission import _arda
from tests.test_dai_neural_mesh import _mesh_context


def test_arda_bounded_execution_writes_sandbox_artifact_and_reverse_evidence(tmp_path):
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

    assert execution.executed is True
    assert execution.red_gates == ()
    assert execution.provider_calls_used == 0
    assert execution.host_mutation_allowed is False
    assert execution.execution_authority_allowed is False
    assert execution.written_files
    assert reverse.verified is True
    assert reverse.red_gates == ()
    output = json.loads((tmp_path / "arda-sandbox" / "arda_bounded_replay_output.json").read_text())
    assert output["capability_digest"] == capability.capability_digest
    assert output["host_mutation_performed"] is False
    assert output["execution_authority_allowed"] is False


def test_reverse_evidence_rejects_tampered_execution_output(tmp_path):
    capability, promotion, admission, quorum = _mesh_context(tmp_path)
    mesh = activate_neural_mesh(
        capability=capability,
        promotion_receipt=promotion,
        admission_receipt=admission,
        quorum_receipt=quorum,
    )
    execution, _ = execute_arda_bounded_replay(
        capability=capability,
        promotion_receipt=promotion,
        mesh_receipt=mesh,
        arda_attestation=_arda(),
        sandbox_root=tmp_path / "arda-sandbox",
    )
    output_path = tmp_path / "arda-sandbox" / "arda_bounded_replay_output.json"
    output_path.write_text('{"tampered":true}\n', encoding="utf-8")

    reverse = verify_arda_reverse_evidence(execution)

    assert reverse.verified is False
    assert "output_digest_matches_execution" in reverse.red_gates
    assert "effect_digest_recomputes" in reverse.red_gates


def test_arda_execution_refuses_unactivated_mesh(tmp_path):
    capability, promotion, admission, quorum = _mesh_context(tmp_path)
    mesh = activate_neural_mesh(
        capability=capability,
        promotion_receipt=promotion,
        admission_receipt=admission,
        quorum_receipt=quorum,
    )
    bad_mesh = replace(mesh, activated=False, red_gates=("capability_promoted",))

    execution, reverse = execute_arda_bounded_replay(
        capability=capability,
        promotion_receipt=promotion,
        mesh_receipt=bad_mesh,
        arda_attestation=_arda(),
        sandbox_root=tmp_path / "arda-sandbox",
    )

    assert execution.executed is False
    assert "mesh_activation_green" in execution.red_gates
    assert "output_artifact_written" in execution.red_gates
    assert reverse.verified is False
    assert not (tmp_path / "arda-sandbox" / "arda_bounded_replay_output.json").exists()


def test_arda_execution_refuses_host_mutation_request(tmp_path):
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
        request={"request_type": "bad", "host_mutation_requested": True},
    )

    assert execution.executed is False
    assert "host_mutation_not_requested" in execution.red_gates
    assert reverse.verified is False

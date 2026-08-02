import pytest

from app.kernel.networking.swarm_contracts import SwarmRoleInput, SwarmRoleResult


def test_role_result_is_typed_and_digest_is_stable():
    role_input = SwarmRoleInput("cartographer", {"files": ["pricing.py"]})
    result = SwarmRoleResult(
        role="cartographer",
        status="completed",
        inputs_digest=role_input.inputs_digest,
        outputs={"selected_files": ["pricing.py"]},
        evidence_refs=("workspace:fingerprint",),
        next_role="verifier",
    )

    assert result.to_dict()["status"] == "completed"
    assert result.to_dict()["evidence_refs"] == ["workspace:fingerprint"]
    assert role_input.inputs_digest == SwarmRoleInput("cartographer", {"files": ["pricing.py"]}).inputs_digest


def test_execution_claim_without_receipt_is_rejected():
    with pytest.raises(ValueError, match="tool receipt"):
        SwarmRoleResult(
            role="forge_executor",
            status="completed",
            inputs_digest="sha256:abc",
            outputs={"execution_claimed": True},
            mutations=1,
        )


def test_execution_claim_requires_receipt():
    result = SwarmRoleResult(
        role="forge_executor",
        status="completed",
        inputs_digest="sha256:abc",
        outputs={"execution_claimed": True, "tool_receipt": {"receipt_id": "r1"}},
        evidence_refs=("r1",),
        tool_calls=1,
        mutations=1,
    )
    assert result.to_dict()["mutations"] == 1

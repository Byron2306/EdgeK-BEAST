from dataclasses import replace

from app.kernel.commons.ml_kem import ML_KEM_ALGORITHM
from app.kernel.compute.deterministic_intelligence import sha256_digest
from app.kernel.dai.commons_admission import admit_commons_nodes
from app.kernel.dai.contracts import ArdaAttestationSummary, WorldStateSnapshot


ROLE_BY_NODE = {
    "commons-node-a": "semantic",
    "commons-node-b": "physical",
    "commons-node-c": "adversarial",
}


def _arda() -> ArdaAttestationSummary:
    return ArdaAttestationSummary(
        attestation_id="arda:test:commons",
        source_artifact_receipts=(sha256_digest({"arda": "artifact"}),),
        workload_digest=sha256_digest({"workload": "commons-admission-test"}),
        bpf_or_kernel_witness_present=True,
        measured_identity_present=True,
    )


def _world() -> WorldStateSnapshot:
    return WorldStateSnapshot(
        snapshot_id="world:commons:test",
        epoch_id="epoch:commons:test",
        facts={"scope": "commons-admission-unit"},
    )


def _node(node_id: str) -> dict:
    return {
        "node_id": node_id,
        "algorithm": ML_KEM_ALGORITHM,
        "confirmed": True,
        "secret_exported": False,
        "health_ok": True,
        "public_key_digest": sha256_digest({"public_key": node_id}),
        "transcript_digest": sha256_digest({"transcript": node_id}),
        "health_digest": sha256_digest({"health": node_id}),
    }


def _ml_kem_receipt() -> dict:
    payload = {
        "beast_object_type": "commons_ml_kem_gauntlet_receipt",
        "status": "passed",
        "algorithm": ML_KEM_ALGORITHM,
        "secret_storage_policy": "shared_secret_bytes_never_serialized",
        "nodes": [
            _node("commons-node-a"),
            _node("commons-node-b"),
            _node("commons-node-c"),
        ],
    }
    payload["receipt_digest"] = sha256_digest(payload)
    return payload


def test_commons_admission_binds_ml_kem_arda_world_and_roles():
    receipt = admit_commons_nodes(
        ml_kem_receipt=_ml_kem_receipt(),
        arda_attestation=_arda(),
        world_state=_world(),
        role_by_node=ROLE_BY_NODE,
    )

    assert receipt.admitted is True
    assert receipt.red_gates == ()
    assert receipt.witness_roles == ("adversarial", "physical", "semantic")
    assert len(receipt.admitted_nodes) == 3
    assert all(node.maximum_authority.value == "commons_admission_only" for node in receipt.admitted_nodes)
    assert receipt.receipt_digest.startswith("sha256:")


def test_commons_admission_can_bind_exact_external_world_digest():
    exact_world_digest = sha256_digest({"phase2": "live-world"})
    receipt = admit_commons_nodes(
        ml_kem_receipt=_ml_kem_receipt(),
        arda_attestation=_arda(),
        world_state=_world(),
        role_by_node=ROLE_BY_NODE,
        bound_world_state_digest=exact_world_digest,
    )

    assert receipt.admitted is True
    assert receipt.world_state_digest == exact_world_digest
    assert all(node.world_state_digest == exact_world_digest for node in receipt.admitted_nodes)


def test_commons_admission_rejects_wrong_ml_kem_algorithm():
    ml_kem = _ml_kem_receipt()
    ml_kem["algorithm"] = "RSA-KEM"

    receipt = admit_commons_nodes(
        ml_kem_receipt=ml_kem,
        arda_attestation=_arda(),
        world_state=_world(),
        role_by_node=ROLE_BY_NODE,
    )

    assert receipt.admitted is False
    assert "ml_kem_algorithm" in receipt.red_gates


def test_commons_admission_rejects_secret_exported_node():
    ml_kem = _ml_kem_receipt()
    ml_kem["nodes"][1]["secret_exported"] = True

    receipt = admit_commons_nodes(
        ml_kem_receipt=ml_kem,
        arda_attestation=_arda(),
        world_state=_world(),
        role_by_node=ROLE_BY_NODE,
    )

    assert receipt.admitted is False
    assert "all_nodes_confirmed_and_healthy" in receipt.red_gates


def test_commons_admission_rejects_missing_arda_physical_witness():
    arda = replace(_arda(), bpf_or_kernel_witness_present=False)

    receipt = admit_commons_nodes(
        ml_kem_receipt=_ml_kem_receipt(),
        arda_attestation=arda,
        world_state=_world(),
        role_by_node=ROLE_BY_NODE,
    )

    assert receipt.admitted is False
    assert "arda_physical_witness_present" in receipt.red_gates


def test_commons_admission_rejects_non_diverse_roles():
    receipt = admit_commons_nodes(
        ml_kem_receipt=_ml_kem_receipt(),
        arda_attestation=_arda(),
        world_state=_world(),
        role_by_node={
            "commons-node-a": "semantic",
            "commons-node-b": "semantic",
            "commons-node-c": "semantic",
        },
    )

    assert receipt.admitted is False
    assert "role_diverse_minimum" in receipt.red_gates

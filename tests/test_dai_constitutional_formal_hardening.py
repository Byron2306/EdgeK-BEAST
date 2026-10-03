from __future__ import annotations

from dataclasses import asdict

from app.kernel.compute.deterministic_intelligence import sha256_digest
from app.kernel.dai.constitutional_extensions import EffectManifest
from app.kernel.dai.constitutional_formal_hardening import (
    ByzantineNode,
    ByzantineQuorumPolicy,
    ByzantineVote,
    run_formal_hardening_demo,
    run_z3_effect_containment_model,
    sign_hybrid_ed25519_ml_dsa_65,
    verify_hybrid_signature_packet,
    evaluate_byzantine_commons_model,
)


def _manifest() -> EffectManifest:
    return EffectManifest(
        capability_id="cap:formal",
        capability_digest=sha256_digest("cap:formal"),
        permitted_reads=("ledger.json",),
        permitted_writes=("receipt.json",),
        network_destinations=(),
        syscalls=("openat", "read", "write", "close"),
        tools=("constitutional_verifier",),
        model_calls=(),
        data_classifications=("public_test_artifact",),
        resource_limits={"max_provider_calls": 0},
        expected_postconditions=("receipt_written",),
    )


def test_z3_bounded_effect_model_rejects_escape_admission() -> None:
    receipt = run_z3_effect_containment_model(_manifest())

    assert receipt["backend_available"] is True
    assert receipt["clean_admission_satisfiable"] is True
    assert receipt["hostile_escape_admission_unsat"] is True
    assert receipt["authority_escape_admission_unsat"] is True
    assert receipt["green"] is True


def test_hybrid_ed25519_ml_dsa_65_signs_same_bytes_and_rejects_tamper() -> None:
    payload = {"answer": "bounded", "digest": sha256_digest("payload")}
    packet, verified = sign_hybrid_ed25519_ml_dsa_65(payload)

    tampered = verify_hybrid_signature_packet(packet, {**payload, "answer": "tampered"})
    downgraded = asdict(packet)
    downgraded["ml_dsa_signature_b64"] = ""
    downgrade_check = verify_hybrid_signature_packet(downgraded, payload)

    assert verified["verified"] is True
    assert verified["gates"]["ed25519_signature_valid"] is True
    assert verified["gates"]["ml_dsa_65_signature_valid"] is True
    assert tampered["verified"] is False
    assert downgrade_check["verified"] is False


def test_byzantine_model_proves_single_proposition_safety_and_rejects_equivocation() -> None:
    proposal = sha256_digest("proposal")
    world = sha256_digest("world")
    nodes = (
        ByzantineNode("n1", "physical_execution_witness", "op1", "local", "d1", sha256_digest("k1")),
        ByzantineNode("n2", "semantic_witness", "op2", "gcp", "d2", sha256_digest("k2")),
        ByzantineNode("n3", "adversarial_witness", "op3", "azure", "d3", sha256_digest("k3")),
        ByzantineNode("n4", "governance_witness", "op4", "hf", "d4", sha256_digest("k4")),
        ByzantineNode("n5", "semantic_witness", "op5", "github", "d5", sha256_digest("k5")),
    )
    votes = tuple(ByzantineVote(n.node_id, proposal, world, "epoch", "approve") for n in nodes[:4])
    policy = ByzantineQuorumPolicy(
        policy_id="policy",
        proposition_scope="single_proposition_certificate",
        threshold=4,
        max_byzantine_faults=1,
        required_roles=("physical_execution_witness", "semantic_witness", "adversarial_witness", "governance_witness"),
        min_distinct_providers=3,
        min_distinct_control_domains=4,
    )

    receipt = evaluate_byzantine_commons_model(
        nodes=nodes,
        votes=votes,
        policy=policy,
        proposal_digest=proposal,
        world_state_hash=world,
        governance_epoch="epoch",
    )
    equivocation = evaluate_byzantine_commons_model(
        nodes=nodes,
        votes=votes + (ByzantineVote("n1", proposal, sha256_digest("fork"), "epoch", "approve"),),
        policy=policy,
        proposal_digest=proposal,
        world_state_hash=world,
        governance_epoch="epoch",
    )

    assert receipt["green"] is True
    assert receipt["quorum_intersection_fault_safe"] is True
    assert receipt["single_proposition_certificate_claimed"] is True
    assert receipt["persistent_state_machine_claimed"] is False
    assert equivocation["green"] is False
    assert "equivocation_detected" in equivocation["red_gates"]
    assert "fork_detected" in equivocation["red_gates"]


def test_phase6_5_demo_is_green_and_carries_hostile_controls() -> None:
    phase6_4 = {
        "green": True,
        "receipt_digest": sha256_digest("phase6.4"),
        "effect_containment_receipt": {"manifest": asdict(_manifest())},
    }

    receipt = run_formal_hardening_demo(constitutional_receipt=phase6_4)

    assert receipt["green"] is True
    assert all(receipt["formal_gates"].values())
    assert all(receipt["hostile_controls"].values())
    assert receipt["hybrid_signature_verification_receipt"]["verified"] is True
    assert receipt["byzantine_equivocation_receipt"]["green"] is False
    assert receipt["byzantine_weak_quorum_receipt"]["green"] is False

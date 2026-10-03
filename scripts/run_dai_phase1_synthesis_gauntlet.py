#!/usr/bin/env python3
"""Run the Phase-1 DAI Diode synthesis gauntlet.

This runner binds actual local artifacts from Sophia/Arda/Seraph/Metatron into
a BEAST-side validation packet.  It intentionally does not grant execution
authority; the green claim is only that the first shared contract spine obeys
the diode law.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from dataclasses import replace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.kernel.compute.deterministic_intelligence import canonical_json, sha256_digest
from app.kernel.dai.arda_execution import execute_arda_bounded_replay
from app.kernel.dai.capability_promotion import promote_candidate_capability
from app.kernel.dai.contracts import (
    ArdaAttestationSummary,
    ArtifactReceipt,
    AuthorityScope,
    DAIOrgan,
    DAIPhase1Packet,
    QuorumVote,
    VoteDecision,
    WorldStateSnapshot,
    load_json_summary,
    packet_to_dict,
    receipt_to_dict,
    validate_phase1_packet,
)
from app.kernel.dai.commons_admission import admit_commons_nodes
from app.kernel.dai.evidence_resolver import resolve_phase1_evidence
from app.kernel.dai.neural_mesh import activate_neural_mesh
from app.kernel.dai.plasticity import close_plasticity_loop
from app.kernel.dai.seraph_bridge import seraph_curriculum_from_summary
from app.kernel.dai.harmonic_bridge import harmonic_transfer_from_office_matrix
from app.kernel.dai.sophia_bridge import concept_candidate_from_sophia_export
from app.kernel.dai.world_state import converge_world_state, events_from_phase1_packet
from app.kernel.dai.quorum import decide_quorum, sign_vote


DEFAULT_SOPHIA = Path("/home/byron/Integritas-Mechanicus/evidence/sophia_writing_desk_phase3_export_semantic_latest.json")
DEFAULT_SERAPH = Path("/home/byron/Downloads/Metatron-triune-outbound-gate/metatron_public_claim_summary_20260428T155428.json")
DEFAULT_HARMONIC = Path("/home/byron/Integritas-Mechanicus/evidence/office_response_proof_matrix/office_response_proof_matrix_20260730T152441Z.json")
DEFAULT_ARDA = Path("/home/byron/EdgeK-BEAST/evidence/c4x-physical-truth-certificate/physical_truth_sidecar_harvested.json")
DEFAULT_ML_KEM = Path("/home/byron/EdgeK-BEAST/evidence/commons-ml-kem/physical-truth-commons-mlkem-live-container-helper-001.json")
WORLD_EVENT_SIGNER = "beast-dai-phase1-local-signer"
WORLD_EVENT_SECRET = b"beast-dai-phase1-local-world-state-secret"
QUORUM_SECRETS = {
    "commons-node-a": b"dai-phase1-commons-node-a",
    "commons-node-b": b"dai-phase1-commons-node-b",
    "commons-node-c": b"dai-phase1-commons-node-c",
}


def build_packet(*, sophia_path: Path, seraph_path: Path, harmonic_path: Path, arda_path: Path, ml_kem_path: Path, sandbox_root: Path | None = None) -> tuple[DAIPhase1Packet, object, object, object, object, object, object, tuple[object, ...], object, object, object, object, object, object, tuple[object, ...]]:
    sophia = ArtifactReceipt.from_file(
        sophia_path,
        organ=DAIOrgan.SOPHIA,
        artifact_schema="sophia_writing_desk_phase3_export_semantic_latest",
        summary=load_json_summary(sophia_path),
        maximum_authority=AuthorityScope.OBSERVATION_ONLY,
    )
    seraph = ArtifactReceipt.from_file(
        seraph_path,
        organ=DAIOrgan.SERAPH,
        artifact_schema="metatron_honest_classification_summary",
        summary=load_json_summary(seraph_path),
        maximum_authority=AuthorityScope.OBSERVATION_ONLY,
    )
    harmonic = ArtifactReceipt.from_file(
        harmonic_path,
        organ=DAIOrgan.METATRON_HARMONIC,
        artifact_schema="sophia_office_response_proof_matrix",
        summary=load_json_summary(harmonic_path),
        maximum_authority=AuthorityScope.OBSERVATION_ONLY,
    )
    arda = ArtifactReceipt.from_file(
        arda_path,
        organ=DAIOrgan.ARDA,
        artifact_schema="c4x_physical_truth_sidecar",
        summary=load_json_summary(arda_path),
        maximum_authority=AuthorityScope.OBSERVATION_ONLY,
    )
    ml_kem_artifact = ArtifactReceipt.from_file(
        ml_kem_path,
        organ=DAIOrgan.COMMONS,
        artifact_schema="commons_ml_kem_gauntlet_receipt",
        summary=load_json_summary(ml_kem_path),
        maximum_authority=AuthorityScope.OBSERVATION_ONLY,
    )

    candidate, sophia_bridge_summary = concept_candidate_from_sophia_export(sophia_path, source_receipt=sophia)
    seraph_assessment, seraph_curriculum = seraph_curriculum_from_summary(seraph_path, source_receipt=seraph)
    harmonic_assessment, harmonic_transfer = harmonic_transfer_from_office_matrix(harmonic_path, source_receipt=harmonic)
    ml_kem_receipt = json.loads(ml_kem_path.read_text(encoding="utf-8"))
    arda_attestation = ArdaAttestationSummary(
        attestation_id="arda:c4x:phase1:physical-sidecar",
        source_artifact_receipts=(arda.receipt_digest,),
        workload_digest=sha256_digest({"workload": "dai-phase1-local-synthesis", "repo": str(ROOT)}),
        bpf_or_kernel_witness_present=True,
        measured_identity_present=True,
    )

    world = WorldStateSnapshot(
        snapshot_id="world:dai-phase1-local-synthesis",
        epoch_id="epoch:2026-08-04-phase1",
        facts={
            "beast_repo": str(ROOT),
            "sophia_artifact_digest": sophia.artifact_digest,
            "seraph_artifact_digest": seraph.artifact_digest,
            "harmonic_artifact_digest": harmonic.artifact_digest,
            "arda_artifact_digest": arda.artifact_digest,
            "commons_ml_kem_artifact_digest": ml_kem_artifact.artifact_digest,
            "sophia_bridge_summary_digest": sophia_bridge_summary.summary_digest,
            "sophia_support_rows": sophia_bridge_summary.support_rows,
            "sophia_contradiction_rows": sophia_bridge_summary.contradiction_rows,
            "sophia_support_families": sophia_bridge_summary.distinct_support_families,
            "seraph_curriculum_digest": seraph_curriculum.curriculum_digest,
            "seraph_challenge_count": len(seraph_curriculum.challenge_cases),
            "seraph_attack_families": seraph_curriculum.attack_families,
            "seraph_observed_k0_count": seraph_curriculum.observed_k0_count,
            "seraph_support_only_count": seraph_curriculum.support_only_count,
            "harmonic_transfer_digest": harmonic_transfer.assessment_digest,
            "harmonic_transfer_cases": len(harmonic_transfer.cases),
            "harmonic_transfer_offices": harmonic_transfer.offices,
            "harmonic_average_resonance": harmonic_transfer.average_resonance,
            "harmonic_average_discord": harmonic_transfer.average_discord,
            "harmonic_drift_detected": harmonic_transfer.drift_detected,
        },
        policy_generation="dai-phase1-no-direct-learning-to-execution",
    )

    base_packet = DAIPhase1Packet(
        packet_id="dai-phase1-synthesis-local-001",
        world_state=world,
        artifacts=(sophia, seraph, harmonic, arda, ml_kem_artifact),
        concept_candidate=candidate,
        seraph_assessment=seraph_assessment,
        harmonic_assessment=harmonic_assessment,
        arda_attestation=arda_attestation,
        beast_semantic_receipts=(),
        requested_authority=AuthorityScope.CANDIDATE_ONLY,
    )
    events = events_from_phase1_packet(base_packet, signer_id=WORLD_EVENT_SIGNER, secret=WORLD_EVENT_SECRET)
    converged_world, world_receipt = converge_world_state(
        base_snapshot=world,
        events=events,
        secrets={WORLD_EVENT_SIGNER: WORLD_EVENT_SECRET},
    )
    admission = admit_commons_nodes(
        ml_kem_receipt=ml_kem_receipt,
        arda_attestation=arda_attestation,
        world_state=converged_world,
        role_by_node={
            "commons-node-a": "semantic",
            "commons-node-b": "physical",
            "commons-node-c": "adversarial",
        },
    )
    votes = tuple(
        sign_vote(
            QuorumVote(
                vote_id=f"vote:{node.node_id}:phase1",
                voter_id=node.node_id,
                witness_role=node.witness_role,
                decision=VoteDecision.APPROVED,
                proposal_digest=candidate.candidate_digest,
                world_state_digest=converged_world.snapshot_digest,
                epoch_id=converged_world.epoch_id,
            ),
            secret=QUORUM_SECRETS[node.node_id],
        )
        for node in admission.admitted_nodes
        if node.admitted and node.node_id in QUORUM_SECRETS
    )
    quorum_decision = decide_quorum(
        admission=admission,
        votes=votes,
        vetoes=(),
        proposal_digest=candidate.candidate_digest,
        world_state_digest=converged_world.snapshot_digest,
        epoch_id=converged_world.epoch_id,
        secrets=QUORUM_SECRETS,
    )
    packet_with_world = replace(
        base_packet,
        world_state=converged_world,
        world_event_receipts=(world_receipt.receipt_digest,),
        commons_admission_receipts=(admission.receipt_digest,),
        quorum_receipts=(quorum_decision.receipt_digest,),
        quorum_votes=votes,
    )
    evidence_receipt = resolve_phase1_evidence(packet_with_world)
    final_packet = replace(
        packet_with_world,
        evidence_resolution_receipts=(evidence_receipt.receipt_digest,),
    )
    spine_validation = validate_phase1_packet(final_packet)
    capability, promotion_receipt, hostile_cases = promote_candidate_capability(
        packet=final_packet,
        validation_receipt=spine_validation,
        evidence_receipt=evidence_receipt,
        admission_receipt=admission,
        quorum_receipt=quorum_decision,
    )
    mesh_receipt = activate_neural_mesh(
        capability=capability,
        promotion_receipt=promotion_receipt,
        admission_receipt=admission,
        quorum_receipt=quorum_decision,
    )
    arda_execution_receipt, arda_reverse_receipt = execute_arda_bounded_replay(
        capability=capability,
        promotion_receipt=promotion_receipt,
        mesh_receipt=mesh_receipt,
        arda_attestation=arda_attestation,
        sandbox_root=sandbox_root or (ROOT / "evidence/dai-diode/phase1-synthesis-001/arda_execution_sandbox"),
    )
    outcome_signal, revision_proposal, plasticity_receipt = close_plasticity_loop(
        capability=capability,
        promotion_receipt=promotion_receipt,
        mesh_receipt=mesh_receipt,
        execution_receipt=arda_execution_receipt,
        reverse_receipt=arda_reverse_receipt,
    )
    final_packet = replace(
        final_packet,
        beast_semantic_receipts=(
            promotion_receipt.receipt_digest,
            mesh_receipt.receipt_digest,
            arda_execution_receipt.receipt_digest,
            arda_reverse_receipt.receipt_digest,
            plasticity_receipt.receipt_digest,
        ),
    )
    return final_packet, evidence_receipt, world_receipt, admission, quorum_decision, capability, promotion_receipt, hostile_cases, mesh_receipt, arda_execution_receipt, arda_reverse_receipt, outcome_signal, revision_proposal, plasticity_receipt, events


def object_to_dict(value: object) -> dict:
    payload = json.loads(canonical_json(value))
    receipt_digest = getattr(value, "receipt_digest", None)
    if receipt_digest:
        payload["receipt_digest"] = receipt_digest
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sophia", type=Path, default=DEFAULT_SOPHIA)
    parser.add_argument("--seraph", type=Path, default=DEFAULT_SERAPH)
    parser.add_argument("--harmonic", type=Path, default=DEFAULT_HARMONIC)
    parser.add_argument("--arda", type=Path, default=DEFAULT_ARDA)
    parser.add_argument("--ml-kem", type=Path, default=DEFAULT_ML_KEM)
    parser.add_argument("--out", type=Path, default=ROOT / "evidence/dai-diode/phase1-synthesis-001")
    args = parser.parse_args()

    packet, evidence_receipt, world_receipt, admission_receipt, quorum_receipt, capability, promotion_receipt, hostile_cases, mesh_receipt, arda_execution_receipt, arda_reverse_receipt, outcome_signal, revision_proposal, plasticity_receipt, world_events = build_packet(sophia_path=args.sophia, seraph_path=args.seraph, harmonic_path=args.harmonic, arda_path=args.arda, ml_kem_path=args.ml_kem, sandbox_root=args.out / "arda_execution_sandbox")
    receipt = validate_phase1_packet(packet)

    args.out.mkdir(parents=True, exist_ok=True)
    packet_path = args.out / "dai_phase1_packet.json"
    receipt_path = args.out / "dai_phase1_validation_receipt.json"
    evidence_receipt_path = args.out / "dai_evidence_resolution_receipt.json"
    world_receipt_path = args.out / "dai_world_state_convergence_receipt.json"
    world_events_path = args.out / "dai_world_events.json"
    admission_receipt_path = args.out / "dai_commons_admission_receipt.json"
    quorum_receipt_path = args.out / "dai_quorum_decision_receipt.json"
    capability_path = args.out / "dai_capability.json"
    promotion_receipt_path = args.out / "dai_capability_promotion_receipt.json"
    hostile_cases_path = args.out / "dai_capability_promotion_hostile_cases.json"
    mesh_receipt_path = args.out / "dai_neural_mesh_activation_receipt.json"
    arda_execution_receipt_path = args.out / "dai_arda_execution_receipt.json"
    arda_reverse_receipt_path = args.out / "dai_arda_reverse_evidence_receipt.json"
    outcome_signal_path = args.out / "dai_outcome_signal.json"
    revision_proposal_path = args.out / "dai_capability_revision_proposal.json"
    plasticity_receipt_path = args.out / "dai_closed_loop_plasticity_receipt.json"
    packet_path.write_text(json.dumps(packet_to_dict(packet), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    receipt_path.write_text(json.dumps(receipt_to_dict(receipt), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    evidence_receipt_path.write_text(json.dumps(object_to_dict(evidence_receipt), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    world_receipt_path.write_text(json.dumps(object_to_dict(world_receipt), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    world_events_path.write_text(json.dumps([object_to_dict(event) for event in world_events], indent=2, sort_keys=True) + "\n", encoding="utf-8")
    admission_receipt_path.write_text(json.dumps(object_to_dict(admission_receipt), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    quorum_receipt_path.write_text(json.dumps(object_to_dict(quorum_receipt), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    capability_path.write_text(json.dumps(object_to_dict(capability), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    promotion_receipt_path.write_text(json.dumps(object_to_dict(promotion_receipt), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    hostile_cases_path.write_text(json.dumps([object_to_dict(case) for case in hostile_cases], indent=2, sort_keys=True) + "\n", encoding="utf-8")
    mesh_receipt_path.write_text(json.dumps(object_to_dict(mesh_receipt), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    arda_execution_receipt_path.write_text(json.dumps(object_to_dict(arda_execution_receipt), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    arda_reverse_receipt_path.write_text(json.dumps(object_to_dict(arda_reverse_receipt), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    outcome_signal_path.write_text(json.dumps(object_to_dict(outcome_signal), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    revision_proposal_path.write_text(json.dumps(object_to_dict(revision_proposal), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    plasticity_receipt_path.write_text(json.dumps(object_to_dict(plasticity_receipt), indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(json.dumps({
        "accepted": receipt.accepted,
        "packet_digest": packet.packet_digest,
        "receipt_digest": receipt.receipt_digest,
        "red_gates": list(receipt.red_gates),
        "promotion_state": receipt.promotion_state.value,
        "execution_authority_allowed": receipt.execution_authority_allowed,
        "packet": str(packet_path),
        "receipt": str(receipt_path),
        "evidence_resolution_receipt": str(evidence_receipt_path),
        "world_state_convergence_receipt": str(world_receipt_path),
        "world_events": str(world_events_path),
        "commons_admission_receipt": str(admission_receipt_path),
        "quorum_decision_receipt": str(quorum_receipt_path),
        "capability": str(capability_path),
        "capability_promotion_receipt": str(promotion_receipt_path),
        "neural_mesh_activation_receipt": str(mesh_receipt_path),
        "arda_execution_receipt": str(arda_execution_receipt_path),
        "arda_reverse_evidence_receipt": str(arda_reverse_receipt_path),
        "outcome_signal": str(outcome_signal_path),
        "capability_revision_proposal": str(revision_proposal_path),
        "closed_loop_plasticity_receipt": str(plasticity_receipt_path),
    }, indent=2, sort_keys=True))
    return 0 if receipt.accepted else 1


if __name__ == "__main__":
    raise SystemExit(main())

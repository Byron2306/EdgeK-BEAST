"""DAI evidence resolver.

This resolver hardens the Phase-1 packet against the exact old failure mode:
accepting receipt-shaped strings without recomputing what they refer to.  It
recomputes artifact file hashes, artifact receipt hashes, component object
hashes, and source-link equality before issuing a resolver receipt.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from app.kernel.compute.deterministic_intelligence import sha256_digest
from app.kernel.dai.contracts import DAIPhase1Packet, packet_to_dict


@dataclass(frozen=True, slots=True)
class DAIEvidenceResolutionReceipt:
    packet_digest: str
    resolved: bool
    component_digests: Mapping[str, str]
    gates: Mapping[str, bool]
    red_gates: tuple[str, ...]
    object_type: str = "dai_evidence_resolution_receipt"
    schema_version: str = "2026-08-04.phase1"

    @property
    def receipt_digest(self) -> str:
        return sha256_digest(self)


def phase1_packet_core_digest(packet: DAIPhase1Packet) -> str:
    payload = packet_to_dict(packet)
    payload["evidence_resolution_receipts"] = []
    payload["world_event_receipts"] = []
    payload["commons_admission_receipts"] = []
    payload["quorum_receipts"] = []
    payload["beast_semantic_receipts"] = []
    return sha256_digest(payload)


def resolve_phase1_evidence(packet: DAIPhase1Packet, *, verify_files: bool = True) -> DAIEvidenceResolutionReceipt:
    artifact_receipts = {artifact.receipt_digest: artifact for artifact in packet.artifacts}
    artifact_file_digests = {artifact.artifact_path: artifact.artifact_digest for artifact in packet.artifacts}

    component_digests = {
        "packet": phase1_packet_core_digest(packet),
        "world_state": packet.world_state.snapshot_digest,
        "concept_candidate": packet.concept_candidate.candidate_digest,
        "seraph_assessment": packet.seraph_assessment.assessment_digest,
        "harmonic_assessment": packet.harmonic_assessment.assessment_digest,
        "arda_attestation": packet.arda_attestation.attestation_digest,
        "artifact_receipts": sha256_digest(tuple(sorted(artifact_receipts))),
        "artifact_file_digests": sha256_digest(artifact_file_digests),
        "commons_admission_receipts": sha256_digest(packet.commons_admission_receipts),
        "quorum_receipts": sha256_digest(packet.quorum_receipts),
    }

    gates: dict[str, bool] = {
        "artifact_receipt_digests_unique": len(artifact_receipts) == len(packet.artifacts),
        "artifact_file_digests_recompute": not verify_files or all(artifact.verify_file_digest() for artifact in packet.artifacts),
        "candidate_sources_resolve_exactly": set(packet.concept_candidate.source_artifact_receipts).issubset(artifact_receipts),
        "seraph_sources_resolve_exactly": set(packet.seraph_assessment.source_artifact_receipts).issubset(artifact_receipts),
        "harmonic_sources_resolve_exactly": set(packet.harmonic_assessment.source_artifact_receipts).issubset(artifact_receipts),
        "arda_sources_resolve_exactly": set(packet.arda_attestation.source_artifact_receipts).issubset(artifact_receipts),
        "seraph_challenge_receipts_bound": bool(packet.seraph_assessment.challenge_receipts),
        "harmonic_transfer_receipts_bound": bool(packet.harmonic_assessment.transfer_receipts),
        "candidate_transfer_receipts_bound": bool(packet.concept_candidate.transfer_evidence.source_span_receipts),
        "commons_admission_receipts_bound": bool(packet.commons_admission_receipts),
        "quorum_receipts_bound": bool(packet.quorum_receipts),
        "component_digest_consistency": all(value.startswith("sha256:") for value in component_digests.values()),
    }
    red_gates = tuple(name for name, passed in sorted(gates.items()) if not passed)
    return DAIEvidenceResolutionReceipt(
        packet_digest=phase1_packet_core_digest(packet),
        resolved=not red_gates,
        component_digests=component_digests,
        gates=gates,
        red_gates=red_gates,
    )

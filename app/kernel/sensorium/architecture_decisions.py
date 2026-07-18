"""Phase S0 architecture decisions for the Sensorium and crystal plane."""

from __future__ import annotations

from typing import Any, Dict


SENSORIUM_ADR_ORDER = [f"SADR-{index:03d}" for index in range(1, 6)]

SENSORIUM_ADR_RECORDS: Dict[str, Dict[str, str]] = {
    "SADR-001": {
        "title": "Observation and actuation remain separate",
        "status": "accepted_contract",
        "invariant": "sensorium_adapters_emit_evidence_and_never_own_actuators",
    },
    "SADR-002": {
        "title": "A PID is not a process identity",
        "status": "accepted_contract",
        "invariant": "process_identity_is_content_bound_and_pidfd_is_live_internal_state",
    },
    "SADR-003": {
        "title": "Crystal Bus uses credentialed message-preserving local transport",
        "status": "accepted_for_phase_s4",
        "invariant": "sock_seqpacket_peer_identity_and_capability_lease_are_conjunctive",
    },
    "SADR-004": {
        "title": "Crystal capsules are immutable transport without ambient authority",
        "status": "accepted_for_phase_s4",
        "invariant": "sealed_memfd_does_not_grant_execution_or_confidentiality",
    },
    "SADR-005": {
        "title": "Equivalence requires sound reviewed rewrite evidence",
        "status": "accepted_for_phase_s7",
        "invariant": "semantic_similarity_never_creates_an_equivalence_edge",
    },
}


def sensorium_architecture_decision_register() -> Dict[str, Any]:
    return {
        "beast_object_type": "sensorium_architecture_decision_register",
        "version": "1.0",
        "decision_count": len(SENSORIUM_ADR_ORDER),
        "decisions": [
            {"adr_id": adr_id, **SENSORIUM_ADR_RECORDS[adr_id]}
            for adr_id in SENSORIUM_ADR_ORDER
        ],
        "claim_boundary": {
            "sensorium": "read_mostly_evidence_plane",
            "retrieval": "candidate_selection_not_authority",
            "capsule": "immutable_transport_not_authority_or_secrecy",
            "equivalence": "reviewed_rules_and_verifiers_only",
            "execution": "requires_policy_attestation_lease_freshness_and_approval",
        },
    }

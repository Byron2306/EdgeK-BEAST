"""DAI world-state event convergence.

The world state is a hash-derived reality contract.  Events are signed/bound,
hash-chained, and reduced into a canonical `WorldStateSnapshot`.  This does not
make the world true by itself; it makes the tested world explicit and replayable.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
import base64
import hashlib
import hmac
from typing import Any, Mapping, Sequence

from app.kernel.compute.deterministic_intelligence import canonical_json, sha256_digest
from app.kernel.dai.contracts import DAIPhase1Packet, WorldStateSnapshot, parse_iso_datetime, utc_now_iso
from app.kernel.dai.evidence_resolver import phase1_packet_core_digest


@dataclass(frozen=True, slots=True)
class DAIWorldEvent:
    event_id: str
    event_type: str
    subject: str
    payload: Mapping[str, Any]
    epoch_id: str
    sequence: int
    previous_event_digest: str = ""
    signer_id: str = ""
    signature: str = ""
    created_at: str = ""

    def __post_init__(self) -> None:
        if not self.event_id.strip() or not self.event_type.strip() or not self.subject.strip():
            raise ValueError("world event requires id, type and subject")
        if self.sequence < 1:
            raise ValueError("world event sequence must be positive")
        if not self.created_at:
            object.__setattr__(self, "created_at", utc_now_iso())
        parse_iso_datetime(self.created_at, field_name="created_at")
        canonical_json(self.payload)

    @property
    def signing_payload(self) -> Mapping[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "subject": self.subject,
            "payload": self.payload,
            "epoch_id": self.epoch_id,
            "sequence": self.sequence,
            "previous_event_digest": self.previous_event_digest,
            "created_at": self.created_at,
        }

    @property
    def event_digest(self) -> str:
        return sha256_digest({**self.signing_payload, "signer_id": self.signer_id, "signature": self.signature})


@dataclass(frozen=True, slots=True)
class WorldStateConvergenceReceipt:
    snapshot_digest: str
    event_count: int
    event_chain_head: str
    converged: bool
    gates: Mapping[str, bool]
    red_gates: tuple[str, ...]
    object_type: str = "dai_world_state_convergence_receipt"
    schema_version: str = "2026-08-04.phase1"

    @property
    def receipt_digest(self) -> str:
        return sha256_digest(self)


def sign_world_event(event: DAIWorldEvent, *, signer_id: str, secret: bytes) -> DAIWorldEvent:
    signature = hmac.new(secret, canonical_json(event.signing_payload).encode("utf-8"), hashlib.sha256).digest()
    return replace(event, signer_id=signer_id, signature=base64.b64encode(signature).decode("ascii"))


def verify_world_event(event: DAIWorldEvent, *, secrets: Mapping[str, bytes]) -> bool:
    secret = secrets.get(event.signer_id)
    if not secret:
        return False
    expected = hmac.new(secret, canonical_json(event.signing_payload).encode("utf-8"), hashlib.sha256).digest()
    try:
        return hmac.compare_digest(base64.b64decode(event.signature, validate=True), expected)
    except Exception:
        return False


def events_from_phase1_packet(packet: DAIPhase1Packet, *, signer_id: str, secret: bytes) -> tuple[DAIWorldEvent, ...]:
    unsigned: list[DAIWorldEvent] = []
    previous = ""
    sequence = 1
    event_specs: list[tuple[str, str, Mapping[str, Any]]] = [
        ("packet_core_bound", packet.packet_id, {"packet_core_digest": phase1_packet_core_digest(packet)}),
        ("artifact_bound", "sophia", {"artifact_digest": packet.artifacts[0].artifact_digest}),
        ("artifact_bound", "seraph", {"artifact_digest": packet.artifacts[1].artifact_digest}),
        ("artifact_bound", "harmonic", {"artifact_digest": packet.artifacts[2].artifact_digest}),
        ("artifact_bound", "arda", {"artifact_digest": packet.artifacts[3].artifact_digest}),
    ]
    if len(packet.artifacts) > 4:
        for artifact in packet.artifacts[4:]:
            event_specs.append(
                (
                    "artifact_bound",
                    artifact.organ.value,
                    {
                        "artifact_digest": artifact.artifact_digest,
                        "artifact_schema": artifact.artifact_schema,
                    },
                )
            )
    event_specs.extend([
        ("candidate_proposed", packet.concept_candidate.candidate_id, {"candidate_digest": packet.concept_candidate.candidate_digest}),
        ("seraph_curriculum_bound", packet.seraph_assessment.assessment_id, {"assessment_digest": packet.seraph_assessment.assessment_digest}),
        ("harmonic_transfer_bound", packet.harmonic_assessment.assessment_id, {"assessment_digest": packet.harmonic_assessment.assessment_digest}),
        ("arda_attestation_bound", packet.arda_attestation.attestation_id, {"attestation_digest": packet.arda_attestation.attestation_digest}),
    ])
    for event_type, subject, payload in event_specs:
        event = DAIWorldEvent(
            event_id=f"world:event:{sequence:04d}:{event_type}",
            event_type=event_type,
            subject=subject,
            payload=payload,
            epoch_id=packet.world_state.epoch_id,
            sequence=sequence,
            previous_event_digest=previous,
        )
        signed = sign_world_event(event, signer_id=signer_id, secret=secret)
        unsigned.append(signed)
        previous = signed.event_digest
        sequence += 1
    return tuple(unsigned)


def converge_world_state(
    *,
    base_snapshot: WorldStateSnapshot,
    events: Sequence[DAIWorldEvent],
    secrets: Mapping[str, bytes],
) -> tuple[WorldStateSnapshot, WorldStateConvergenceReceipt]:
    gates: dict[str, bool] = {
        "events_present": bool(events),
        "epoch_matches": all(event.epoch_id == base_snapshot.epoch_id for event in events),
        "sequences_contiguous": tuple(event.sequence for event in events) == tuple(range(1, len(events) + 1)),
        "signatures_valid": all(verify_world_event(event, secrets=secrets) for event in events),
    }
    previous = ""
    chain_ok = True
    for event in events:
        if event.previous_event_digest != previous:
            chain_ok = False
            break
        previous = event.event_digest
    gates["hash_chain_valid"] = chain_ok

    derived_facts = dict(base_snapshot.facts)
    derived_facts["world_event_count"] = len(events)
    derived_facts["world_event_chain_head"] = previous
    derived_facts["world_event_types"] = tuple(event.event_type for event in events)
    snapshot = WorldStateSnapshot(
        snapshot_id=base_snapshot.snapshot_id,
        epoch_id=base_snapshot.epoch_id,
        facts=derived_facts,
        observed_at=base_snapshot.observed_at,
        expires_at=base_snapshot.expires_at,
        policy_generation=base_snapshot.policy_generation,
    )
    red_gates = tuple(name for name, passed in sorted(gates.items()) if not passed)
    receipt = WorldStateConvergenceReceipt(
        snapshot_digest=snapshot.snapshot_digest,
        event_count=len(events),
        event_chain_head=previous,
        converged=not red_gates,
        gates=gates,
        red_gates=red_gates,
    )
    return snapshot, receipt

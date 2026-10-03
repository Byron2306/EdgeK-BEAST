from dataclasses import replace

from app.kernel.dai.world_state import (
    converge_world_state,
    events_from_phase1_packet,
    verify_world_event,
)
from tests.test_dai_phase1_contracts import _valid_packet


SIGNER = "unit-signer"
SECRET = b"unit-secret"


def test_world_events_are_signed_chained_and_converge(tmp_path):
    packet = _valid_packet(tmp_path)
    events = events_from_phase1_packet(packet, signer_id=SIGNER, secret=SECRET)
    snapshot, receipt = converge_world_state(
        base_snapshot=packet.world_state,
        events=events,
        secrets={SIGNER: SECRET},
    )

    assert len(events) == 9
    assert all(verify_world_event(event, secrets={SIGNER: SECRET}) for event in events)
    assert receipt.converged is True
    assert receipt.red_gates == ()
    assert snapshot.facts["world_event_count"] == len(events)
    assert snapshot.facts["world_event_chain_head"] == events[-1].event_digest


def test_world_state_rejects_wrong_signature_secret(tmp_path):
    packet = _valid_packet(tmp_path)
    events = events_from_phase1_packet(packet, signer_id=SIGNER, secret=SECRET)

    _, receipt = converge_world_state(
        base_snapshot=packet.world_state,
        events=events,
        secrets={SIGNER: b"wrong-secret"},
    )

    assert receipt.converged is False
    assert "signatures_valid" in receipt.red_gates


def test_world_state_rejects_broken_hash_chain(tmp_path):
    packet = _valid_packet(tmp_path)
    events = list(events_from_phase1_packet(packet, signer_id=SIGNER, secret=SECRET))
    events[2] = replace(events[2], previous_event_digest="sha256:" + "0" * 64)

    _, receipt = converge_world_state(
        base_snapshot=packet.world_state,
        events=tuple(events),
        secrets={SIGNER: SECRET},
    )

    assert receipt.converged is False
    assert "hash_chain_valid" in receipt.red_gates


def test_world_state_rejects_epoch_mismatch(tmp_path):
    packet = _valid_packet(tmp_path)
    events = list(events_from_phase1_packet(packet, signer_id=SIGNER, secret=SECRET))
    events[0] = replace(events[0], epoch_id="epoch:other")

    _, receipt = converge_world_state(
        base_snapshot=packet.world_state,
        events=tuple(events),
        secrets={SIGNER: SECRET},
    )

    assert receipt.converged is False
    assert "epoch_matches" in receipt.red_gates


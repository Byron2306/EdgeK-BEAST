from dataclasses import replace
from datetime import datetime, timezone

from app.kernel.compute.deterministic_intelligence import sha256_digest
from app.kernel.dai.phase2_stale_listener import (
    acquire_phase2_world_lease,
    attempt_stale_world_replay,
    execute_phase2_stale_listener_replacement,
    observe_listener,
    start_phase2_stale_listener_lab,
    stable_world_state_digest,
)


def test_phase2_replaces_stale_listener_and_preserves_unrelated_control():
    lab = start_phase2_stale_listener_lab(run_id="test-phase2-stale-listener")
    try:
        lease = acquire_phase2_world_lease(lab)
        receipt = execute_phase2_stale_listener_replacement(lab, lease)

        assert receipt.executed is True
        assert receipt.refused_reason == ""
        assert receipt.old_pid_retired is True
        assert receipt.exact_port_reused is True
        assert receipt.replacement_healthy is True
        assert receipt.unrelated_control_unchanged is True
        assert receipt.provider_calls_used == 0
        assert receipt.production_authority_allowed is False
        assert receipt.red_gates == ()
        assert "old_pid_retired" in receipt.green_gates
        assert receipt.after_replacement.port == lease.stale_port
        assert receipt.after_replacement.response == "phase2-replacement-service"
        assert receipt.after_control.pid == lease.control_pid
        assert receipt.after_control.port == lease.control_port
        assert receipt.after_control.response == "phase2-unrelated-control"
        assert receipt.receipt_digest.startswith("sha256:")
    finally:
        lab.cleanup()


def test_phase2_refuses_stale_world_reuse_after_replacement_with_zero_effect():
    lab = start_phase2_stale_listener_lab(run_id="test-phase2-stale-world-replay")
    try:
        lease = acquire_phase2_world_lease(lab)
        replacement = execute_phase2_stale_listener_replacement(lab, lease)
        assert replacement.executed is True

        replay = attempt_stale_world_replay(lab, lease)

        assert replay.refused is True
        assert replay.refusal_reason == "stale_lease_live_world_state_mismatch"
        assert replay.zero_effect is True
        assert replay.provider_calls_used == 0
        assert replay.red_gates == ()
        assert "stale_world_refused" in replay.green_gates
        assert observe_listener(lab.replacement).response == "phase2-replacement-service"
        assert observe_listener(lab.control).response == "phase2-unrelated-control"
    finally:
        lab.cleanup()


def test_phase2_refuses_wrong_stale_identity_before_any_mutation():
    lab = start_phase2_stale_listener_lab(run_id="test-phase2-wrong-identity")
    try:
        lease = acquire_phase2_world_lease(lab)
        hostile_lease = replace(lease, stale_pid=lease.stale_pid + 1000000)
        before_world = stable_world_state_digest(lab)

        receipt = execute_phase2_stale_listener_replacement(lab, hostile_lease)

        assert receipt.executed is False
        assert receipt.refused_reason == "stale_listener_identity_mismatch"
        assert stable_world_state_digest(lab) == before_world
        assert observe_listener(lab.stale).response == "phase2-stale-service"
        assert observe_listener(lab.control).response == "phase2-unrelated-control"
    finally:
        lab.cleanup()


def test_phase2_refuses_supplied_world_digest_mismatch_before_any_mutation():
    lab = start_phase2_stale_listener_lab(run_id="test-phase2-world-digest-mismatch")
    try:
        lease = acquire_phase2_world_lease(lab)
        before_world = stable_world_state_digest(lab)
        wrong_digest = sha256_digest({"hostile": "different-world"})

        receipt = execute_phase2_stale_listener_replacement(
            lab,
            lease,
            supplied_world_state_digest=wrong_digest,
        )

        assert receipt.executed is False
        assert receipt.refused_reason == "supplied_world_state_digest_mismatch"
        assert stable_world_state_digest(lab) == before_world
        assert observe_listener(lab.stale).response == "phase2-stale-service"
        assert observe_listener(lab.control).response == "phase2-unrelated-control"
    finally:
        lab.cleanup()


def test_phase2_refuses_expired_lease_before_any_mutation():
    lab = start_phase2_stale_listener_lab(run_id="test-phase2-expired-lease")
    try:
        lease = acquire_phase2_world_lease(lab)
        expired = replace(lease, expires_at="2000-01-01T00:00:00+00:00")
        before_world = stable_world_state_digest(lab)

        receipt = execute_phase2_stale_listener_replacement(lab, expired)

        assert receipt.executed is False
        assert receipt.refused_reason == "lease_expired"
        assert stable_world_state_digest(lab) == before_world
        assert observe_listener(lab.stale).response == "phase2-stale-service"
        assert observe_listener(lab.control).response == "phase2-unrelated-control"
    finally:
        lab.cleanup()


def test_phase2_refuses_consumed_lease_reuse_before_second_mutation():
    lab = start_phase2_stale_listener_lab(run_id="test-phase2-consumed-lease")
    try:
        lease = acquire_phase2_world_lease(lab)
        first = execute_phase2_stale_listener_replacement(lab, lease)
        assert first.executed is True
        before_world = stable_world_state_digest(lab)

        second = execute_phase2_stale_listener_replacement(lab, lease)

        assert second.executed is False
        assert second.refused_reason == "lease_already_consumed"
        assert stable_world_state_digest(lab) == before_world
        assert observe_listener(lab.replacement).response == "phase2-replacement-service"
        assert observe_listener(lab.control).response == "phase2-unrelated-control"
    finally:
        lab.cleanup()

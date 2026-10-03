from dataclasses import replace
import os

from app.kernel.compute.deterministic_intelligence import sha256_digest
from app.kernel.dai.phase3_lockfile import (
    acquire_phase3_lockfile_world_lease,
    attempt_phase3_lockfile_stale_world_replay,
    execute_phase3_lockfile_cleanup,
    observe_lockfile,
    stable_lockfile_world_state_digest,
    start_phase3_lockfile_lab,
)


def test_phase3_lockfile_cleanup_removes_only_stale_pidfile():
    lab = start_phase3_lockfile_lab(run_id="test-phase3-lockfile-cleanup")
    try:
        lease = acquire_phase3_lockfile_world_lease(lab)
        before_control = observe_lockfile(lab.control_lock, label="control")

        receipt = execute_phase3_lockfile_cleanup(lab, lease)

        assert receipt.executed is True
        assert receipt.refused_reason == ""
        assert receipt.stale_lock_removed is True
        assert receipt.stale_pid_was_dead is True
        assert receipt.unrelated_control_unchanged is True
        assert receipt.provider_calls_used == 0
        assert receipt.production_authority_allowed is False
        assert receipt.red_gates == ()
        assert not lab.stale_lock.exists()
        assert lab.control_lock.exists()
        assert observe_lockfile(lab.control_lock, label="control").content_digest == before_control.content_digest
        assert receipt.receipt_digest.startswith("sha256:")
    finally:
        lab.cleanup()


def test_phase3_lockfile_replay_refuses_stale_world_with_zero_effect():
    lab = start_phase3_lockfile_lab(run_id="test-phase3-lockfile-replay")
    try:
        lease = acquire_phase3_lockfile_world_lease(lab)
        cleanup = execute_phase3_lockfile_cleanup(lab, lease)
        assert cleanup.executed is True

        replay = attempt_phase3_lockfile_stale_world_replay(lab, lease)

        assert replay.refused is True
        assert replay.refusal_reason == "stale_lease_live_world_state_mismatch"
        assert replay.zero_effect is True
        assert replay.provider_calls_used == 0
        assert replay.red_gates == ()
        assert "stale_world_refused" in replay.green_gates
        assert lab.control_lock.exists()
    finally:
        lab.cleanup()


def test_phase3_lockfile_refuses_current_pid_cleanup_before_mutation():
    lab = start_phase3_lockfile_lab(run_id="test-phase3-lockfile-current-pid-live", stale_pid=os.getpid())
    try:
        lease = acquire_phase3_lockfile_world_lease(lab)
        before = stable_lockfile_world_state_digest(lab)

        receipt = execute_phase3_lockfile_cleanup(lab, lease)

        assert receipt.executed is False
        assert receipt.refused_reason == "stale_pid_is_alive"
        assert stable_lockfile_world_state_digest(lab) == before
        assert lab.stale_lock.exists()
        assert lab.control_lock.exists()
    finally:
        lab.cleanup()


def test_phase3_lockfile_refuses_supplied_world_digest_mismatch():
    lab = start_phase3_lockfile_lab(run_id="test-phase3-lockfile-wrong-world")
    try:
        lease = acquire_phase3_lockfile_world_lease(lab)
        before = stable_lockfile_world_state_digest(lab)

        receipt = execute_phase3_lockfile_cleanup(
            lab,
            lease,
            supplied_world_state_digest=sha256_digest({"hostile": "wrong-world"}),
        )

        assert receipt.executed is False
        assert receipt.refused_reason == "supplied_world_state_digest_mismatch"
        assert stable_lockfile_world_state_digest(lab) == before
        assert lab.stale_lock.exists()
    finally:
        lab.cleanup()


def test_phase3_lockfile_refuses_path_escape_before_mutation(tmp_path):
    lab = start_phase3_lockfile_lab(run_id="test-phase3-lockfile-path-escape")
    try:
        lease = acquire_phase3_lockfile_world_lease(lab)
        hostile = replace(lease, stale_lock_path=str(tmp_path / "outside.pidlock"))
        before = stable_lockfile_world_state_digest(lab)

        receipt = execute_phase3_lockfile_cleanup(lab, hostile)

        assert receipt.executed is False
        assert receipt.refused_reason == "lockfile_path_out_of_scope"
        assert stable_lockfile_world_state_digest(lab) == before
        assert lab.stale_lock.exists()
        assert lab.control_lock.exists()
    finally:
        lab.cleanup()

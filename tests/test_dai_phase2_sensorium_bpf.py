import json

from app.kernel.compute.deterministic_intelligence import sha256_digest
from app.kernel.dai.phase2_sensorium_bpf import (
    build_phase2_sensorium_bpf_witness,
    capture_phase2_cgroup_snapshot,
)
from app.kernel.dai.phase2_stale_listener import (
    acquire_phase2_world_lease,
    execute_phase2_stale_listener_replacement,
    start_phase2_stale_listener_lab,
)


def _sidecar(tmp_path, *, tamper_digest=False, loaded=3):
    bpf = {
        "bpf_authority_present": True,
        "arda_bpf_authoritative": True,
        "cgroup_bound": True,
        "read_only_program": True,
        "ring_loss_explicit": True,
        "raw_packet_payload_retained": False,
        "loaded_bpf_program_count": loaded,
    }
    digest = sha256_digest(bpf)
    bpf["receipt_digest"] = sha256_digest({"wrong": "digest"}) if tamper_digest else digest
    path = tmp_path / "sidecar.json"
    path.write_text(json.dumps({"bpf_receipt": bpf}, sort_keys=True), encoding="utf-8")
    return path


def test_phase2_sensorium_bpf_binds_sidecar_and_procfs_cgroups(tmp_path):
    lab = start_phase2_stale_listener_lab(run_id="test-phase2-bpf")
    try:
        lease = acquire_phase2_world_lease(lab)
        before = capture_phase2_cgroup_snapshot(lab, phase="before_replacement")
        replacement = execute_phase2_stale_listener_replacement(lab, lease)
        after = capture_phase2_cgroup_snapshot(lab, phase="after_replacement")

        report = build_phase2_sensorium_bpf_witness(
            phase2_world_state_digest=replacement.world_state_digest,
            proposal_digest=sha256_digest({"proposal": "phase2"}),
            live_replacement_receipt_digest=replacement.receipt_digest,
            before_cgroups=before,
            after_cgroups=after,
            bpf_sidecar_path=_sidecar(tmp_path),
        )

        assert report.passed is True
        assert report.bpf_authority_bound is True
        assert report.bpf_receipt_recomputed is True
        assert report.process_cgroup_snapshot_digest.startswith("sha256:")
        assert report.exact_phase2_kernel_events_bound is False
        assert "exact_phase2_kernel_events_bound" in report.red_gates
        assert report.authority_level == "bpf_substrate_plus_procfs_cgroup_witness"
        assert report.provider_calls_used == 0
    finally:
        lab.cleanup()


def test_phase2_sensorium_bpf_promotes_exact_event_binding_when_supplied(tmp_path):
    lab = start_phase2_stale_listener_lab(run_id="test-phase2-bpf-exact")
    try:
        lease = acquire_phase2_world_lease(lab)
        before = capture_phase2_cgroup_snapshot(lab, phase="before_replacement")
        replacement = execute_phase2_stale_listener_replacement(lab, lease)
        after = capture_phase2_cgroup_snapshot(lab, phase="after_replacement")
        observations = tuple(observation for observation in (*before, *after) if observation.procfs_cgroup_present)
        expectations = [
            {
                "pid": observation.pid,
                "tgid": observation.pid,
                "start_time_ticks": index + 100,
                "process_lease_id": f"process:sha256:{index:064x}",
                "role": observation.role,
                "requested_port": observation.port,
                "cgroup_raw_digest": observation.cgroup_raw_digest,
            }
            for index, observation in enumerate(observations)
        ]
        events = [
            {
                "event_type": "kernel.bpf.socket_bind",
                "cgroup_raw_digest": expectation["cgroup_raw_digest"],
                "pid": expectation["pid"],
                "tgid": expectation["tgid"],
                "start_time_ticks": expectation["start_time_ticks"],
                "process_lease_id": expectation["process_lease_id"],
                "role": expectation["role"],
                "requested_port": expectation["requested_port"],
                "normalized_port": expectation["requested_port"],
                "normalized_address": 16777343,
                "observation_digest": f"sha256:{index + 1:064x}",
            }
            for index, expectation in enumerate(expectations)
        ]

        report = build_phase2_sensorium_bpf_witness(
            phase2_world_state_digest=replacement.world_state_digest,
            proposal_digest=sha256_digest({"proposal": "phase2"}),
            live_replacement_receipt_digest=replacement.receipt_digest,
            before_cgroups=before,
            after_cgroups=after,
            bpf_sidecar_path=_sidecar(tmp_path),
            exact_kernel_events=events,
            exact_kernel_event_expectations=expectations,
        )

        assert report.passed is True
        assert report.exact_phase2_kernel_events_bound is True
        assert "exact_phase2_kernel_events_bound" not in report.red_gates
        assert report.authority_level == "exact_phase2_cgroup_kernel_witness"
        assert len(report.exact_kernel_event_digests) == len(events)
    finally:
        lab.cleanup()


def test_phase2_sensorium_bpf_rejects_fabricated_same_cgroup_wrong_lease_event(tmp_path):
    lab = start_phase2_stale_listener_lab(run_id="test-phase2-bpf-fabricated")
    try:
        lease = acquire_phase2_world_lease(lab)
        before = capture_phase2_cgroup_snapshot(lab, phase="before_replacement")
        replacement = execute_phase2_stale_listener_replacement(lab, lease)
        after = capture_phase2_cgroup_snapshot(lab, phase="after_replacement")
        observation = next(item for item in (*before, *after) if item.procfs_cgroup_present)
        expectation = {
            "pid": observation.pid,
            "tgid": observation.pid,
            "start_time_ticks": 123,
            "process_lease_id": "process:sha256:" + "a" * 64,
            "role": observation.role,
            "requested_port": observation.port,
            "cgroup_raw_digest": observation.cgroup_raw_digest,
        }
        fabricated = {
            "event_type": "kernel.bpf.socket_bind",
            "cgroup_raw_digest": observation.cgroup_raw_digest,
            "pid": observation.pid + 999,
            "tgid": observation.pid + 999,
            "start_time_ticks": 123,
            "process_lease_id": "process:sha256:" + "b" * 64,
            "role": "wrong-role",
            "requested_port": observation.port,
            "normalized_port": observation.port,
            "normalized_address": 16777343,
            "observation_digest": "sha256:" + "c" * 64,
        }

        report = build_phase2_sensorium_bpf_witness(
            phase2_world_state_digest=replacement.world_state_digest,
            proposal_digest=sha256_digest({"proposal": "phase2"}),
            live_replacement_receipt_digest=replacement.receipt_digest,
            before_cgroups=before,
            after_cgroups=after,
            bpf_sidecar_path=_sidecar(tmp_path),
            exact_kernel_events=[fabricated],
            exact_kernel_event_expectations=[expectation],
        )

        assert report.passed is True
        assert report.exact_phase2_kernel_events_bound is False
        assert report.authority_level == "bpf_substrate_plus_procfs_cgroup_witness"
        assert "exact_phase2_kernel_events_bound" in report.red_gates
    finally:
        lab.cleanup()


def test_phase2_sensorium_bpf_rejects_tampered_bpf_receipt_digest(tmp_path):
    lab = start_phase2_stale_listener_lab(run_id="test-phase2-bpf-tampered")
    try:
        lease = acquire_phase2_world_lease(lab)
        before = capture_phase2_cgroup_snapshot(lab, phase="before_replacement")
        replacement = execute_phase2_stale_listener_replacement(lab, lease)
        after = capture_phase2_cgroup_snapshot(lab, phase="after_replacement")

        report = build_phase2_sensorium_bpf_witness(
            phase2_world_state_digest=replacement.world_state_digest,
            proposal_digest=sha256_digest({"proposal": "phase2"}),
            live_replacement_receipt_digest=replacement.receipt_digest,
            before_cgroups=before,
            after_cgroups=after,
            bpf_sidecar_path=_sidecar(tmp_path, tamper_digest=True),
        )

        assert report.passed is False
        assert report.bpf_receipt_recomputed is False
        assert "bpf_receipt_recomputed" in report.red_gates
        assert "bpf_authority_bound" in report.red_gates
    finally:
        lab.cleanup()

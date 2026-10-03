import json
import ast
from pathlib import Path

from app.kernel.compute.deterministic_intelligence import sha256_digest
from scripts.run_dai_phase2_x2_exact_ring_buffer import _load_correlated_x2_events


def test_x2_exact_script_correlates_jsonl_events_to_lease_registry(tmp_path):
    lease_id = "process:sha256:" + "a" * 64
    registry_entries = [
        {
            "tgid": 1234,
            "start_time_ticks": 55,
            "process_lease_id": lease_id,
            "label": "stale",
            "role": "phase2-stale-service",
            "requested_port": 0,
            "cgroup_raw_digest": sha256_digest({"cgroup": "stale"}),
        }
    ]
    event = {
        "event_type": "kernel.bpf.socket_bind",
        "mission_id": "mission",
        "workspace_id": "workspace",
        "process_lease_id": lease_id,
        "observation_digest": sha256_digest({"observation": "bind"}),
        "body": {
            "attributes": {"arg0": 0, "arg1": 16777343},
            "pid": 1234,
            "tgid": 1234,
            "cgroup_id": 99,
            "correlated": True,
            "correlation_method": "live_procfs_start_time",
        },
    }
    log = tmp_path / "observations.jsonl"
    log.write_text(json.dumps(event, sort_keys=True) + "\n", encoding="utf-8")

    exact = _load_correlated_x2_events(log, registry_entries)

    assert exact == [
        {
            "event_type": "kernel.bpf.socket_bind",
            "observation_digest": event["observation_digest"],
            "process_lease_id": lease_id,
            "pid": 1234,
            "tgid": 1234,
            "start_time_ticks": 55,
            "kernel_cgroup_id": 99,
            "cgroup_raw_digest": registry_entries[0]["cgroup_raw_digest"],
            "label": "stale",
            "role": "phase2-stale-service",
            "requested_port": 0,
            "normalized_port": 0,
            "normalized_address": 16777343,
            "correlation_method": "live_procfs_start_time",
            "x2_projection_digest": sha256_digest(event),
        }
    ]


def test_x2_exact_script_ignores_uncorrelated_events(tmp_path):
    event = {
        "event_type": "kernel.bpf.socket_bind",
        "process_lease_id": "",
        "observation_digest": sha256_digest({"observation": "intruder"}),
        "body": {"pid": 9999, "tgid": 9999, "cgroup_id": 11},
    }
    log = tmp_path / "observations.jsonl"
    log.write_text(json.dumps(event, sort_keys=True) + "\n", encoding="utf-8")

    assert _load_correlated_x2_events(log, []) == []


def test_x2_exact_script_stop_observer_calls_include_logs():
    tree = ast.parse(Path("scripts/run_dai_phase2_x2_exact_ring_buffer.py").read_text(encoding="utf-8"))
    calls = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "_stop_observer"
    ]

    assert calls
    for call in calls:
        keyword_names = {keyword.arg for keyword in call.keywords}
        assert {"stdout_log", "stderr_log"} <= keyword_names

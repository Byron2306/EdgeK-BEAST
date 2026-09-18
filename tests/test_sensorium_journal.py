import json
import sqlite3

import pytest

from app.kernel.sensorium.journal import SensoriumJournal
from app.kernel.sensorium.runtime import SensoriumRuntime


def publish(runtime, index):
    return runtime.observe_owned(
        event_type="process.exec", source="journal-test",
        payload_schema="beast.sensor.process.exec.v1",
        payload={"index": index, "authorization": "Bearer never-persist-this-token"},
        mission_id="mission-journal", workspace_id="workspace-journal",
    )


def test_sensorium_journal_restores_offsets_and_only_sanitized_payloads(tmp_path):
    path = tmp_path / "sensorium.sqlite3"
    first = SensoriumRuntime(capacity=16, journal_path=path, boot_id="boot-journal")
    for index in range(3):
        publish(first, index)
    restored = SensoriumRuntime(capacity=16, journal_path=path, boot_id="boot-journal")
    assert [entry.offset for entry in restored.sequencer.latest(10)] == [1, 2, 3]
    receipt = publish(restored, 3)
    assert receipt.admitted.offset == 4
    encoded = json.dumps([entry.event.to_dict() for entry in SensoriumJournal(path).replay()])
    assert "never-persist-this-token" not in encoded
    assert "[REDACTED]" in encoded
    assert restored.sequencer.metrics()["journal"]["integrity_ok"] is True


def test_sensorium_journal_fails_closed_after_tampering(tmp_path):
    path = tmp_path / "sensorium.sqlite3"
    runtime = SensoriumRuntime(capacity=8, journal_path=path, boot_id="boot-journal")
    publish(runtime, 1)
    connection = sqlite3.connect(path)
    connection.execute("UPDATE sensor_events SET event_json=? WHERE offset=1", ('{"tampered":true}',))
    connection.commit(); connection.close()
    journal = SensoriumJournal(path)
    assert journal.integrity_ok is False
    assert journal.integrity_fracture["offset"] == 1
    with pytest.raises(RuntimeError, match="integrity"):
        SensoriumRuntime(capacity=8, journal_path=path, boot_id="boot-journal")


def test_socket_retirement_updates_payload_free_topology(tmp_path):
    runtime = SensoriumRuntime(capacity=8, export_root=tmp_path, boot_id="boot-journal")
    observation = {
        "family":"AF_INET", "protocol":"TCP", "local_address_class":"loopback", "local_port":8101,
        "remote_scope":"loopback", "owning_process":"process:sha256:" + "a"*64,
        "service_id":"beast", "workspace_id":"workspace-journal", "cgroup_id":"/beast",
        "listener_generation":1, "opened_at_monotonic_ns":1, "policy_class":"operator",
    }
    reconciled = runtime.observe_socket(observation)
    assert runtime.state()["socket_topology"]
    assert runtime.retire_socket(reconciled.identity.identity, reason="lease_released", workspace_id="workspace-journal")
    assert runtime.state()["socket_topology"] == ()


def test_sensorium_journal_shared_runtimes_allocate_contiguous_offsets(tmp_path):
    path = tmp_path / "shared-sensorium.sqlite3"
    first = SensoriumRuntime(capacity=16, journal_path=path, boot_id="boot-shared")
    second = SensoriumRuntime(capacity=16, journal_path=path, boot_id="boot-shared")

    one = first.observe_owned(
        event_type="agent.run.observed",
        source="agent-one",
        payload_schema="beast.sensor.agent_run_event.v1",
        payload={"run_id": "one", "source_event_type": "agent.repository.discovery"},
        mission_id="run-one",
        workspace_id="workspace:sha256:" + "1" * 64,
    )
    two = second.observe_owned(
        event_type="agent.run.observed",
        source="agent-two",
        payload_schema="beast.sensor.agent_run_event.v1",
        payload={"run_id": "two", "source_event_type": "agent.repository.discovery"},
        mission_id="run-two",
        workspace_id="workspace:sha256:" + "2" * 64,
    )

    assert one.admitted.offset == 1
    assert two.admitted.offset == 2
    replay = SensoriumJournal(path).replay()
    assert [entry.offset for entry in replay] == [1, 2]
    assert SensoriumJournal(path).metrics()["integrity_ok"] is True

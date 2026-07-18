import json
import importlib
from types import SimpleNamespace
from concurrent.futures import ThreadPoolExecutor

import pytest
from httpx import ASGITransport, AsyncClient

from app.kernel.sensorium.contracts import content_hash
from app.kernel.sensorium.runtime import SensoriumRuntime
from app.kernel.compute.perceive import ProviderType
from app.kernel.execution.orchestrator import PRECOrchestrator
from app.main import app


HASH_A = "sha256:" + "a" * 64
HASH_B = "sha256:" + "b" * 64


def observe(runtime: SensoriumRuntime, index: int, *, mission_id: str = "mission-one"):
    return runtime.observe_owned(
        event_type="process.exec",
        source="test_process_adapter",
        payload_schema="beast.sensor.process.exec.v1",
        payload={"index": index, "resource_delta": {"cpu_time_ms": 1.5}},
        mission_id=mission_id,
        workspace_id="edgek-beast",
    )


def test_bounded_sequencer_emits_loss_and_preserves_monotonic_offsets(tmp_path):
    runtime = SensoriumRuntime(capacity=4, export_root=tmp_path, boot_id="boot-test")
    for index in range(6):
        observe(runtime, index)

    entries = runtime.sequencer.snapshot(limit=20)
    offsets = [entry.offset for entry in entries]
    loss_events = [entry.event for entry in entries if entry.event.event_type == "sensorium.loss"]

    assert len(entries) == 4
    assert offsets == sorted(offsets)
    assert len(set(offsets)) == len(offsets)
    assert loss_events
    assert sum(event.payload["dropped_count"] for event in loss_events) >= 2
    metrics = runtime.sequencer.metrics()
    assert metrics["displaced"] >= 2
    assert metrics["generated_loss_events"] >= 1
    episode = runtime.close_episode(
        "mission-one",
        objective_hash=HASH_A,
        workspace_identity="edgek-beast",
        initial_state_hash=HASH_B,
        outcome={"status": "observed_with_loss", "effect_hash": HASH_A},
    )
    assert episode.source_loss["test_process_adapter"] == metrics["displaced"]


def test_privacy_gate_redacts_before_retention_and_forbids_sensitive_export(tmp_path):
    runtime = SensoriumRuntime(capacity=8, export_root=tmp_path, boot_id="boot-test")
    receipt = runtime.observe_owned(
        event_type="interception.provider_call",
        source="test_interceptor",
        payload_schema="beast.sensor.interception.provider_call.v1",
        payload={
            "authorization": "Bearer top-secret-token-value",
            "nested": {"api_key": "sk-thismustnotremain123456"},
            "message": "password=hunter2",
        },
        mission_id="mission-private",
        privacy_class="internal_sensitive",
        export_allowed=True,
    )
    retained = receipt.admitted.event
    encoded = json.dumps(retained.to_dict(), sort_keys=True)

    assert "top-secret" not in encoded
    assert "hunter2" not in encoded
    assert "sk-thismustnotremain" not in encoded
    assert retained.privacy["redaction_status"] == "passed"
    assert retained.privacy["redaction_count"] == 3
    assert retained.privacy["export_allowed"] is False
    with pytest.raises(PermissionError):
        runtime.exporter.export_entry(receipt.admitted, external=True)


def test_episode_is_ordered_hash_stable_and_aggregates_resources(tmp_path):
    runtime = SensoriumRuntime(capacity=16, export_root=tmp_path, boot_id="boot-test")
    for index in range(3):
        observe(runtime, index, mission_id="mission-episode")
    episode = runtime.close_episode(
        "mission-episode",
        objective_hash=HASH_A,
        workspace_identity="edgek-beast",
        initial_state_hash=HASH_B,
        outcome={"status": "verified_success", "effect_hash": HASH_A, "rollback_tested": True},
        resources={"network_bytes": 128},
    )

    assert len(episode.event_ids) == 3
    assert episode.causal_graph["edges"] == [
        [episode.event_ids[0], episode.event_ids[1]],
        [episode.event_ids[1], episode.event_ids[2]],
    ]
    assert episode.resources["cpu_time_ms"] == 4.5
    assert episode.resources["network_bytes"] == 128
    assert episode.episode_hash == content_hash(episode.content_payload())


def test_adapter_failure_becomes_event_without_exception_text(tmp_path):
    runtime = SensoriumRuntime(capacity=8, export_root=tmp_path, boot_id="boot-test")

    def failing_adapter():
        raise RuntimeError("secret internal failure detail")

    receipt = runtime.capture_adapter(
        event_type="pressure.sample",
        source="broken_pressure_adapter",
        payload_schema="beast.sensor.pressure.sample.v1",
        adapter=failing_adapter,
        mission_id="mission-failure",
    )
    event = receipt.admitted.event

    assert event.event_type == "sensorium.adapter_failure"
    assert event.payload["error_type"] == "RuntimeError"
    assert event.payload["error_message_retained"] is False
    assert "secret internal" not in json.dumps(event.to_dict())


def test_downstream_export_is_atomic_complete_json(tmp_path):
    runtime = SensoriumRuntime(capacity=8, export_root=tmp_path, boot_id="boot-test")
    receipt = observe(runtime, 1, mission_id="mission-export")
    event_path = runtime.exporter.export_entry(receipt.admitted)
    episode = runtime.close_episode(
        "mission-export",
        objective_hash=HASH_A,
        workspace_identity="edgek-beast",
        initial_state_hash=HASH_B,
        outcome={"status": "verified_success", "effect_hash": HASH_A},
    )
    episode_path = runtime.exporter.export_episode(episode)

    assert json.loads(event_path.read_text(encoding="utf-8"))["event"]["event_id"] == receipt.admitted.event.event_id
    assert json.loads(episode_path.read_text(encoding="utf-8"))["episode_hash"] == episode.episode_hash
    assert list(tmp_path.rglob("*.tmp")) == []


def test_read_model_never_exposes_event_payload_or_actuator(tmp_path):
    runtime = SensoriumRuntime(capacity=8, export_root=tmp_path, boot_id="boot-test")
    observe(runtime, 1)
    state = runtime.state()

    assert state["authority"] == "read_only"
    assert state["actuator_available"] is False
    assert state["recent_events"][0]["payload_included"] is False
    assert "payload" not in state["recent_events"][0]


def test_concurrent_publish_assigns_unique_ordered_offsets(tmp_path):
    runtime = SensoriumRuntime(capacity=128, export_root=tmp_path, boot_id="boot-test")
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda index: observe(runtime, index, mission_id="mission-concurrent"), range(64)))

    entries = runtime.sequencer.snapshot(limit=128)
    offsets = [entry.offset for entry in entries]
    event_ids = [entry.event.event_id for entry in entries]
    assert len(entries) == 64
    assert offsets == list(range(1, 65))
    assert len(set(event_ids)) == 64


@pytest.mark.asyncio
async def test_sensorium_http_state_is_read_only_and_payload_free():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/edgek/sensorium/state")

    assert response.status_code == 200
    payload = response.json()
    assert payload["beast_object_type"] == "sensorium_read_model"
    assert payload["authority"] == "read_only"
    assert payload["actuator_available"] is False


@pytest.mark.asyncio
async def test_normal_prec_cycle_produces_closed_runtime_episode(monkeypatch, tmp_path):
    module = importlib.import_module("app.kernel.execution.orchestrator")
    runtime = SensoriumRuntime(capacity=32, export_root=tmp_path, boot_id="boot-test")
    ir = SimpleNamespace(metadata={}, model="gpt-test")
    governance = SimpleNamespace(
        decision="allow",
        modified_ir=None,
        budget_impact=0,
    )

    monkeypatch.setattr(module.perceiver, "perceive", lambda body, provider: ir)
    monkeypatch.setattr(module.reasoner, "reason", lambda selected_ir, session: governance)
    monkeypatch.setattr(module.reasoner, "record_usage", lambda *args, **kwargs: None)

    async def execute(selected_ir, selected_governance):
        return {"choices": [{"message": {"content": "not retained by Sensorium"}}]}

    async def crystallize(**kwargs):
        return {"status": "ok"}

    monkeypatch.setattr(module.executor, "execute", execute)
    monkeypatch.setattr(module.crystallizer, "crystallize", crystallize)
    economizer = SimpleNamespace(economize=lambda selected_ir: SimpleNamespace(ir=selected_ir))
    orchestrator = PRECOrchestrator(economizer, sensorium=runtime)

    result = await orchestrator.execute_cycle(
        {"model": "gpt-test", "messages": [{"role": "user", "content": "private request"}]},
        ProviderType.OPENAI,
        "session-test",
    )

    assert result[1]["choices"][0]["message"]["content"] == "not retained by Sensorium"
    state = runtime.state()
    assert state["episodes"]["closed_count"] == 1
    assert state["recent_closed_episodes"][0]["event_count"] == 4
    retained = json.dumps([entry.event.to_dict() for entry in runtime.sequencer.latest(10)])
    assert "private request" not in retained
    assert "not retained by Sensorium" not in retained


@pytest.mark.asyncio
async def test_sensorium_failure_cannot_break_prec_cycle(monkeypatch):
    module = importlib.import_module("app.kernel.execution.orchestrator")
    ir = SimpleNamespace(metadata={}, model="gpt-test")
    governance = SimpleNamespace(decision="allow", modified_ir=None, budget_impact=0)
    monkeypatch.setattr(module.perceiver, "perceive", lambda body, provider: ir)
    monkeypatch.setattr(module.reasoner, "reason", lambda selected_ir, session: governance)
    monkeypatch.setattr(module.reasoner, "record_usage", lambda *args, **kwargs: None)

    async def execute(selected_ir, selected_governance):
        return {"result": "provider survived"}

    async def crystallize(**kwargs):
        return {"status": "ok"}

    class BrokenSensorium:
        def observe_owned(self, **kwargs):
            raise RuntimeError("sensor unavailable")

        def close_episode(self, *args, **kwargs):
            raise RuntimeError("episode unavailable")

    monkeypatch.setattr(module.executor, "execute", execute)
    monkeypatch.setattr(module.crystallizer, "crystallize", crystallize)
    economizer = SimpleNamespace(economize=lambda selected_ir: SimpleNamespace(ir=selected_ir))
    orchestrator = PRECOrchestrator(economizer, sensorium=BrokenSensorium())

    _, response, _ = await orchestrator.execute_cycle(
        {"model": "gpt-test", "messages": []}, ProviderType.OPENAI, "session-test"
    )

    assert response == {"result": "provider survived"}

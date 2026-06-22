from pathlib import Path

import pytest

from app.kernel.beast_config import BeastConfig
from app.kernel.beast_errors import CircuitBreaker, OllamaUnavailable
from app.kernel.distributed_forge_scheduler import DistributedForgeScheduler, NodeStatus


def test_config_parses_typed_environment_and_nonduplicated_compute_keys(monkeypatch, tmp_path):
    monkeypatch.setenv("BEAST_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("BEAST_LOGS_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("BEAST_KV_CACHE_DIR", str(tmp_path / "kv"))
    monkeypatch.setenv("BEAST_SCHEDULER_DIR", str(tmp_path / "scheduler"))
    monkeypatch.setenv("BEAST_OLLAMA_TIMEOUT", "17")
    monkeypatch.setenv("BEAST_STRUCTURED_LOGGING", "false")
    monkeypatch.setenv("BEAST_COMPUTE_WEEKLY_CALL_VOLUME", "250")
    config = BeastConfig()
    assert config.DATA_DIR == Path(tmp_path / "data")
    assert config.OLLAMA_TIMEOUT == 17
    assert config.STRUCTURED_LOGGING is False
    assert config.BEAST_COMPUTE_WEEKLY_CALL_VOLUME == 250


def test_circuit_breaker_opens_and_recovers(monkeypatch):
    breaker = CircuitBreaker(threshold=2, timeout_seconds=30)
    failing = lambda: (_ for _ in ()).throw(RuntimeError("offline"))
    with pytest.raises(OllamaUnavailable):
        breaker.call(failing)
    with pytest.raises(OllamaUnavailable):
        breaker.call(failing)
    assert breaker.is_open() is True
    with pytest.raises(OllamaUnavailable, match="Circuit breaker open"):
        breaker.call(lambda: "unreachable")
    breaker.record_success()
    assert breaker.is_open() is False
    assert breaker.call(lambda: "ok") == "ok"


def test_scheduler_honors_capabilities_and_degrades_after_failures(tmp_path):
    scheduler = DistributedForgeScheduler(tmp_path / "scheduler")
    scheduler.register_node("node", capabilities=["fingerprint"])
    scheduler.submit_work("local_inference", "/repo", priority=1)
    scheduler.submit_work("fingerprint", "/repo", priority=2)
    assigned = scheduler.assign_work("node", max_items=1)
    assert [item.work_item.work_type for item in assigned] == ["fingerprint"]
    assert scheduler.report_work_result(assigned[0].schedule_id, "wrong-node", False, {}) is False

    for _ in range(3):
        scheduler.submit_work("fingerprint", "/repo")
        item = scheduler.assign_work("node", max_items=1)[0]
        assert scheduler.report_work_result(item.schedule_id, "node", False, {"error": "fault"}) is True
    assert scheduler.nodes["node"].status == NodeStatus.DEGRADED
    assert scheduler.assign_work("node", max_items=1) == []

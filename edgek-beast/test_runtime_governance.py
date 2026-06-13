import pytest

from app.kernel.execute import Executor
from app.kernel.perceive import EdgeKIR
from app.kernel.reason import GovernanceDecision, GovernanceResult
from app.kernel.runtime import RuntimeGovernor


def test_runtime_governor_enforces_stasis_wall(tmp_path):
    governor = RuntimeGovernor(
        policies={
            "meta_rules": {
                "stasis_wall_enabled": True,
                "stasis_wall_max_concurrent": 1,
                "runtime_provider_timeout_seconds": 10,
            }
        },
        db_path=str(tmp_path / "runtime.db"),
    )

    first = governor.begin_execution("openai", "gpt-3.5-turbo")
    second = governor.begin_execution("openai", "gpt-3.5-turbo")

    assert first.allowed is True
    assert second.allowed is False
    assert "Stasis wall full" in second.reason

    governor.complete_execution(first.attempt_id, "openai", success=True)
    third = governor.begin_execution("openai", "gpt-3.5-turbo")
    assert third.allowed is True


def test_runtime_governor_uses_provider_specific_limits(tmp_path):
    governor = RuntimeGovernor(
        policies={
            "meta_rules": {
                "stasis_wall_enabled": True,
                "stasis_wall_max_concurrent": 5,
                "runtime_provider_timeout_seconds": 120,
            },
            "providers": {
                "openai": {
                    "runtime_max_concurrent": 1,
                    "runtime_timeout_seconds": 7,
                }
            },
        },
        db_path=str(tmp_path / "runtime.db"),
    )

    first = governor.begin_execution("openai", "gpt-3.5-turbo")
    second = governor.begin_execution("openai", "gpt-3.5-turbo")

    assert first.allowed is True
    assert first.timeout_seconds == 7
    assert second.allowed is False


def test_runtime_governor_opens_and_resets_circuit(tmp_path):
    governor = RuntimeGovernor(
        policies={
            "meta_rules": {
                "circuit_breaker_enabled": True,
                "circuit_breaker_failure_threshold": 2,
                "circuit_breaker_timeout_seconds": 60,
            }
        },
        db_path=str(tmp_path / "runtime.db"),
    )

    first = governor.begin_execution("openai", "gpt-3.5-turbo")
    governor.complete_execution(first.attempt_id, "openai", success=False, error_message="boom")
    second = governor.begin_execution("openai", "gpt-3.5-turbo")
    governor.complete_execution(second.attempt_id, "openai", success=False, error_message="boom again")

    blocked = governor.begin_execution("openai", "gpt-3.5-turbo")
    assert blocked.allowed is False
    assert governor.circuit_state("openai")["state"] == "open"

    reset = governor.reset_circuit("openai")
    assert reset["state"] == "closed"
    assert reset["failure_count"] == 0


def test_runtime_governor_exposes_attempt_history_and_detail(tmp_path):
    governor = RuntimeGovernor(
        policies={"meta_rules": {"runtime_provider_timeout_seconds": 10}},
        db_path=str(tmp_path / "runtime.db"),
    )

    admission = governor.begin_execution(
        "openai",
        "gpt-3.5-turbo",
        session_id="session-a",
        metadata={"purpose": "test"},
    )
    governor.complete_execution(admission.attempt_id, "openai", success=True)

    attempts = governor.recent_attempts(provider="openai", status="succeeded")
    detail = governor.get_attempt(admission.attempt_id)

    assert attempts[0]["attempt_id"] == admission.attempt_id
    assert detail["metadata"]["purpose"] == "test"
    assert detail["status"] == "succeeded"


def test_runtime_governor_sweeps_stale_started_attempts(tmp_path):
    governor = RuntimeGovernor(
        policies={"meta_rules": {"runtime_attempt_lease_ttl_seconds": 1}},
        db_path=str(tmp_path / "runtime.db"),
    )

    governor._record_attempt(
        "stale-1",
        "openai",
        "gpt-3.5-turbo",
        "default",
        "started",
        {"purpose": "stale-test"},
    )
    with governor._connect() as conn:
        conn.execute(
            "UPDATE runtime_attempts SET started_at = ? WHERE attempt_id = ?",
            ("2020-01-01T00:00:00Z", "stale-1"),
        )
    governor._active_counts["openai"] = 1

    integrity_before = governor.integrity_report()
    sweep = governor.sweep_stale_attempts()
    detail = governor.get_attempt("stale-1")

    assert integrity_before["ok"] is False
    assert sweep["swept_attempts"] == 1
    assert detail["status"] == "abandoned"
    assert governor.integrity_report()["ok"] is True
    assert governor._active_counts["openai"] == 0


@pytest.mark.asyncio
async def test_executor_records_runtime_success(tmp_path, monkeypatch):
    import app.kernel.execute as execute_module

    governor = RuntimeGovernor(
        policies={"meta_rules": {"runtime_provider_timeout_seconds": 10}},
        db_path=str(tmp_path / "runtime.db"),
    )
    monkeypatch.setattr(execute_module, "runtime_governor", governor)

    executor = Executor()
    ir = EdgeKIR(
        messages=[{"role": "user", "content": "hello"}],
        model="gpt-3.5-turbo",
        max_tokens=10,
        metadata={"provider": "openai"},
    )
    response = await executor.execute(
        ir,
        GovernanceResult(decision=GovernanceDecision.ALLOW),
    )

    assert "edgek_runtime" in response
    assert governor.state()["attempts"]["succeeded"] == 1

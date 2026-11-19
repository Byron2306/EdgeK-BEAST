import asyncio
import json
from pathlib import Path
import subprocess
import urllib.error

import pytest

from app.kernel.agents.coder_integrations import CoderIntegrationCoordinator
from app.kernel.agents.file_review import ReviewEvidence
from app.kernel.agents.nim_planner_provider import NIMPlannerProvider
from app.kernel.agents.planner_provider import PlannerDecisionError
from app.kernel.data_processing.quality_cascade import QualityCascade
from app.kernel.governance.runtime import RuntimeGovernor


@pytest.fixture
def governor(tmp_path, monkeypatch):
    monkeypatch.setenv("NVIDIA_API_KEY", "fixture-credential")
    monkeypatch.setenv("BEAST_NIM_PLANNER_STREAM", "0")
    return RuntimeGovernor(
        policies={"providers": {"nvidia_nim": {"enabled": True}},
                  "meta_rules": {"circuit_breaker_failure_threshold": 1}},
        db_path=str(tmp_path / "runtime.db"),
    )


def test_cascade_uses_loaded_policy_and_reports_missing_and_clean_logs(tmp_path, governor):
    coordinator = CoderIntegrationCoordinator(
        tmp_path, environ={"BEAST_QUALITY_CASCADE": "1"}, runtime_governor=governor,
    )

    def checks():
        result = coordinator.prepare(objective="source trace", task_metadata={"provider": "nvidia_nim"})
        event = next(e["payload"] for e in result["events"] if e["payload"]["capability"] == "quality_cascade")
        return {entry["name"]: entry["status"] for entry in event["checks"]}

    assert checks() == {"provider_policy": "passed", "credentials": "passed",
                        "runtime_circuit": "passed", "log_scan": "skipped"}
    log = tmp_path / "gateway.log"
    log.write_text("INFO nvidia_nim request succeeded\nERROR unrelated service timeout\n")
    assert checks()["log_scan"] == "passed"
    log.write_text("ERROR nvidia_nim returned HTTP 503\n")
    assert checks()["log_scan"] == "warning"


def test_transport_failure_opens_circuit_and_retry_does_not_call_nim(governor, monkeypatch):
    client = NIMPlannerProvider(model="test", runtime_governor=governor, max_retries=1)
    calls = []

    def fail(payload):
        calls.append(payload)
        raise urllib.error.HTTPError("https://example.invalid", 503, "fixture-outage", {}, None)

    monkeypatch.setattr(client, "_request_json", fail)
    with pytest.raises(PlannerDecisionError, match="Circuit breaker open"):
        asyncio.run(client.next_decision("Trace", run={"run_id": "run-fixture"}, turn=1))
    assert len(calls) == 1
    assert governor.circuit_state("nvidia_nim")["state"] == "open"
    attempts = governor.recent_attempts(provider="nvidia_nim", limit=10)
    assert {row["status"] for row in attempts} == {"failed", "rejected"}
    assert all(governor.get_attempt(row["attempt_id"])["metadata"]["run_id"] == "run-fixture" for row in attempts)


def test_bad_citation_is_not_an_outage_and_auth_error_does_not_open_circuit(governor, monkeypatch):
    client = NIMPlannerProvider(model="test", runtime_governor=governor, max_retries=0)
    evidence = ReviewEvidence("", {"a.py": {2}}, {"a.py": 2}, None,
                              source_lines={"a.py": {2: "return 42"}}, symbol_focused=True)
    reply = {"decision_type": "complete", "summary": "Trace",
             "arguments": {"points": [{"ref": "S1L99", "text": "Not in source."}]}}
    monkeypatch.setattr(client, "_request_json", lambda payload: {"content": json.dumps(reply)})
    decision = asyncio.run(client.next_decision(evidence.explanation_prompt("Trace"), run={"mode": "analysis"}, turn=1))
    assert not evidence.explanation_answer(decision)[0]
    assert governor.recent_attempts(provider="nvidia_nim", limit=1)[0]["status"] == "succeeded"
    assert governor.circuit_state("nvidia_nim")["failure_count"] == 0

    def unauthorized(payload):
        raise urllib.error.HTTPError("https://example.invalid", 401, "fixture-auth-error", {}, None)

    monkeypatch.setattr(client, "_request_json", unauthorized)
    with pytest.raises(RuntimeError, match="401"):
        asyncio.run(client.next_decision("Trace", run={}, turn=2))
    assert governor.circuit_state("nvidia_nim")["failure_count"] == 0
    assert governor.recent_attempts(provider="nvidia_nim", limit=1)[0]["status"] == "failed"


def test_disabled_loaded_policy_stops_before_transport(governor, monkeypatch):
    governor.policies["providers"]["nvidia_nim"]["enabled"] = False
    client = NIMPlannerProvider(model="test", runtime_governor=governor)
    monkeypatch.setattr(client, "_request_json", lambda _: pytest.fail("disabled provider was called"))
    with pytest.raises(PlannerDecisionError, match="disabled"):
        asyncio.run(client.next_decision("Trace", run={}, turn=1))


def test_proof_gateway_has_its_own_runtime_circuit_database(tmp_path, monkeypatch):
    root = Path(__file__).resolve().parents[2]
    stub = tmp_path / "stub-python"
    stub.write_text("#!/bin/sh\nprintf '%s\\n' \"$BEAST_RUNTIME_GOVERNOR_DB\"\n")
    stub.chmod(0o700)
    monkeypatch.setenv("BEAST_PROOF_PYTHON", str(stub))
    monkeypatch.setenv("BEAST_STATE_ROOT", str(tmp_path))
    monkeypatch.setenv("BEAST_RUNTIME_GOVERNOR_DB", "/unrelated/runtime.db")
    result = subprocess.run(["bash", str(root / "scripts/beast-coder-learning-gateway.sh")],
                            check=True, text=True, capture_output=True)
    assert result.stdout.strip() == str(tmp_path / "runtime-governor.db")


def test_hosted_run_shares_governor_between_preflight_and_transport(tmp_path, governor, monkeypatch):
    from app.kernel.agents.run_engine import AgentRunEngine
    from app.routes.ide_routes import agent_runs

    monkeypatch.setattr(agent_runs, "runtime_governor", governor)
    run = AgentRunEngine(tmp_path).create_run(
        session_id="fixture", objective="Explain the file", mode="analysis",
        provider="nvidia_nim", model=agent_runs.HOSTED_NEMOTRON_MODEL,
        request={"read_only_file_review": True},
    )
    run_id = run["run_id"]
    try:
        asyncio.run(agent_runs._execute_planner_run(tmp_path, run_id, base_url=""))
        runtime = agent_runs.TURN_RUNTIMES[run_id]
        assert runtime.provider.runtime_governor is governor
        assert runtime.integration_coordinator.runtime_governor is governor
    finally:
        agent_runs.TURN_RUNTIMES.pop(run_id, None)

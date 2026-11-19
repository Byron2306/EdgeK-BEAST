from app.cli.coder_client import RuntimeEvent
from app.cli.coder_state import project_runtime_event
from app.kernel.agents.coder_integrations import CoderIntegrationCoordinator


def test_quality_receipt_explains_which_checks_did_not_pass(tmp_path, monkeypatch):
    monkeypatch.setenv("NVIDIA_API_KEY", "never-export-this-key-value")
    (tmp_path / "gateway.log").write_text("nvidia_nim error: never-export-log-body\n")
    coordinator = CoderIntegrationCoordinator(tmp_path, environ={"BEAST_QUALITY_CASCADE": "1"})
    result = coordinator.prepare(objective="Explain the example", task_metadata={"provider": "nvidia_nim"})
    entry = next(event for event in result["events"] if event["payload"]["capability"] == "quality_cascade")
    receipt = entry["payload"]
    checks = {check["name"]: check for check in receipt["checks"]}
    assert checks["credentials"]["status"] == "passed"
    assert checks["runtime_circuit"] == {
        "name": "runtime_circuit", "status": "skipped", "reason": "Runtime governor unavailable",
    }
    assert checks["log_scan"]["status"] == "warning"
    assert receipt["verification_reason"] == "checks_not_all_passed"
    assert "never-export" not in str(receipt)
    projected = project_runtime_event(RuntimeEvent(event=entry["event_type"], data={"payload": receipt}))
    assert "runtime_circuit (skipped)" in projected.text
    assert "Runtime governor unavailable" in projected.text

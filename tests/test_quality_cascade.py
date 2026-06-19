from app.kernel.quality_cascade import QualityCascade
from app.kernel.runtime import RuntimeGovernor


def test_quality_cascade_runs_provider_steps(tmp_path, monkeypatch):
    monkeypatch.delenv("HF_TOKEN", raising=False)
    governor = RuntimeGovernor(
        policies={"meta_rules": {"runtime_provider_timeout_seconds": 10}},
        db_path=str(tmp_path / "runtime.db"),
    )
    (tmp_path / "gateway.log").write_text(
        "huggingface provider returned 429 quota exhausted\n",
        encoding="utf-8",
    )
    cascade = QualityCascade(
        policies={"providers": {"huggingface": {"enabled": True}}},
        runtime_governor=governor,
    )
    envelope = {
        "task_id": "tsk_test",
        "task_class": "provider_debugging",
        "inputs": {"provider": "huggingface"},
    }
    route = {
        "route_id": "route_provider_diagnostic_huggingface",
        "provider": "huggingface",
        "preferred_order": ["provider_policy", "credentials", "runtime_circuit", "log_scan"],
    }

    report = cascade.run(envelope, route, str(tmp_path))

    assert report["beast_object_type"] == "quality_cascade_report"
    assert report["status"] in ("failed", "warning")
    assert report["summary"]["check_count"] == 4
    assert len(report["evidence_records"]) == 4
    assert report["evidence_records"][1]["source_type"] == "quality_verifier"
    assert report["evidence_records"][1]["recommended_capability_id"] == "workflow:provider_diagnostic"
    assert report["evidence_records"][1]["capability_family"] == "diagnostics"
    assert "score_breakdown" in report["evidence_records"][1]
    assert [check["name"] for check in report["checks"]] == [
        "provider_policy",
        "credentials",
        "runtime_circuit",
        "log_scan",
    ]
    assert report["checks"][1]["status"] == "failed"

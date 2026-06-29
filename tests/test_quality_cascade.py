from app.kernel.data_processing.quality_cascade import QualityCascade
from app.kernel.governance.runtime import RuntimeGovernor


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


def test_maintenance_cascade_runs_repo_hygiene_checks(tmp_path):
    (tmp_path / "app").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "app" / "demo.py").write_text("def value():\n    return 42\n", encoding="utf-8")
    (tmp_path / "tests" / "test_demo.py").write_text(
        "from app.demo import value\n\n\ndef test_value():\n    assert value() == 42\n",
        encoding="utf-8",
    )
    (tmp_path / "README.md").write_text("# Demo\n\nSee [demo](app/demo.py).\n", encoding="utf-8")

    report = QualityCascade().run_maintenance(
        str(tmp_path),
        run_tests=False,
        include_extension_checks=False,
        include_markdown=True,
        timeout_seconds=30,
    )

    checks = {check["name"]: check for check in report["checks"]}
    assert report["beast_object_type"] == "maintenance_cascade_report"
    assert checks["py_compile"]["status"] == "passed"
    assert checks["pytest_collect"]["status"] == "passed"
    assert checks["markdown_summary"]["status"] == "passed"
    assert checks["pytest"]["status"] == "skipped"
    assert checks["language_inventory"]["status"] == "passed"


def test_maintenance_cascade_reports_compile_errors(tmp_path):
    (tmp_path / "broken.py").write_text("def nope(:\n", encoding="utf-8")

    report = QualityCascade().run_maintenance(
        str(tmp_path),
        run_tests=False,
        include_extension_checks=False,
        include_markdown=False,
        timeout_seconds=10,
    )

    checks = {check["name"]: check for check in report["checks"]}
    assert report["status"] == "failed"
    assert checks["py_compile"]["status"] == "failed"
    assert checks["py_compile"]["evidence"]["errors"][0]["path"] == "broken.py"


def test_maintenance_cascade_detects_non_python_surfaces(tmp_path):
    (tmp_path / "index.html").write_text("<!doctype html><main>ok</main>\n", encoding="utf-8")
    (tmp_path / "app.js").write_text("const value = 1;\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text("[build-system]\nrequires=[]\nbuild-backend='setuptools.build_meta'\n", encoding="utf-8")
    (tmp_path / "site").mkdir()
    (tmp_path / "_config.yml").write_text("title: Demo\n", encoding="utf-8")
    (tmp_path / "Example.java").write_text("class Example {}\n", encoding="utf-8")

    report = QualityCascade().run_maintenance(
        str(tmp_path),
        run_tests=False,
        include_extension_checks=False,
        include_markdown=False,
        run_packaging=False,
        timeout_seconds=10,
    )

    checks = {check["name"]: check for check in report["checks"]}
    assert checks["language_inventory"]["evidence"]["languages"]["html"] == 1
    assert checks["language_inventory"]["evidence"]["languages"]["java"] == 1
    assert checks["html_syntax"]["status"] == "passed"
    assert checks["python_package_build"]["status"] == "skipped"
    assert checks["jekyll_docker_build"]["status"] == "skipped"
    assert checks["java_build"]["status"] == "skipped"

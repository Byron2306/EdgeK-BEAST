import tempfile
from pathlib import Path

import pytest

from benchmarks.beast_systems_benchmark import create_workspace, run_task_pytest, write_file
from benchmarks.beast_xai_omni_gauntlet import ABLATION_TASKS, LOCAL_PROBE_GROUPS, _coverage, _write_omni_summary, run
from benchmarks.xai_omni_tasks import additional_tasks, omni_tasks


def test_omni_suite_has_24_unique_hidden_test_tasks():
    tasks = omni_tasks()
    assert len(tasks) == 24
    assert len({task.name for task in tasks}) == 24
    assert all(task.hidden_tests for task in tasks)
    assert all(task.allowed_edit_paths for task in tasks)
    assert set(ABLATION_TASKS).issubset({task.name for task in tasks})


def test_additional_fixture_repairs_pass_and_broken_states_fail():
    for task in additional_tasks():
        with tempfile.TemporaryDirectory(prefix=f"omni-fixture-{task.name}-") as temp:
            root = Path(temp)
            create_workspace(root, task)
            assert run_task_pytest(root).returncode != 0, task.name
            for rel, content in task.fixed_files.items():
                write_file(root, rel, content)
            assert run_task_pytest(root).returncode == 0, task.name


def test_coverage_requires_live_task_and_passing_local_probe():
    probes = {"groups": [{"name": name, "passed": True} for name in LOCAL_PROBE_GROUPS]}
    coverage = _coverage(omni_tasks(), probes)
    assert coverage["total_layers"] == 13
    assert coverage["covered_layers"] == 13
    assert all(row["live_tasks"] > 0 for row in coverage["layers"])


def test_omni_runner_rejects_unknown_provider_before_work(tmp_path):
    with pytest.raises(ValueError, match="unknown live provider preset"):
        run(live=False, output_name=str(tmp_path / "out"), max_tokens=400, timeout=1, skip_local=True, provider_name="missing")


def test_omni_summary_uses_selected_provider(tmp_path):
    path = tmp_path / "summary.md"
    report = {
        "omni_provider": "nvidia_nim",
        "governed_summary": {"nvidia_nim": {"tasks": 24, "completed": 24}},
        "raw_summary": {"nvidia_nim": {"tasks": 4, "completed": 0}},
        "governed_provider_fitness": {"nvidia_nim": {"score": 0.3}},
        "local_probe_matrix": {},
        "coverage": {},
        "live_results": [],
    }

    _write_omni_summary(report, path)

    text = path.read_text(encoding="utf-8")
    assert "BEAST Nvidia Nim Omni-Gauntlet" in text
    assert "24/24" in text

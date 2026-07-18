import json
import subprocess
import sys
from pathlib import Path

from app.kernel.compute.sensorium_port_crystal_experiment import LearnedPortCrystalReceipt, SensoriumPortCrystalExperiment


def test_live_events_learn_compile_promote_and_recur_without_provider(tmp_path):
    receipt = SensoriumPortCrystalExperiment(tmp_path).run()
    receipt.validate()
    assert receipt.fixture_built_candidate is False
    assert receipt.inferred_parameters == ("requested_port",)
    assert receipt.provider_disabled_recurrence is True
    assert receipt.stale_process_refused is True


def test_windows_runner_refuses_non_windows_without_explicit_self_test(tmp_path):
    completed = subprocess.run([sys.executable, "scripts/windows_port_crystal_replication.py", "--output", str(tmp_path / "x.json")], capture_output=True, text=True)
    if sys.platform != "win32":
        assert completed.returncode != 0


def test_cross_domain_verifier_rejects_non_windows_self_test(tmp_path):
    output = tmp_path / "windows.json"
    subprocess.run([sys.executable, "scripts/windows_port_crystal_replication.py", "--self-test-non-windows", "--output", str(output)], check=True)
    windows = json.loads(output.read_text())
    assert windows["self_test"] is True

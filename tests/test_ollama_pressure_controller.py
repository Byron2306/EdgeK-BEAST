from pathlib import Path

from app.kernel.compute.ollama_pressure_controller import OllamaPressureController
from app.kernel.governance.psi_governor import PsiGovernor


def _psi(root: Path, *, memory: str = "some avg10=0.00 avg60=0.00 avg300=0.00 total=0\nfull avg10=0.00 avg60=0.00 avg300=0.00 total=0\n") -> PsiGovernor:
    (root / "cpu").write_text("some avg10=0.00 avg60=0.00 avg300=0.00 total=0\nfull avg10=0.00 avg60=0.00 avg300=0.00 total=0\n")
    (root / "memory").write_text(memory)
    (root / "io").write_text("some avg10=0.00 avg60=0.00 avg300=0.00 total=0\nfull avg10=0.00 avg60=0.00 avg300=0.00 total=0\n")
    return PsiGovernor(root)


def test_pressure_controller_reduces_budget_on_high_memory(tmp_path):
    psi_root = tmp_path / "pressure"
    psi_root.mkdir()
    controller = OllamaPressureController(
        psi_governor=_psi(psi_root),
        meminfo=tmp_path / "meminfo",
    )
    controller.meminfo.write_text("MemTotal: 100000 kB\nMemAvailable: 10000 kB\n")
    decision = controller.decide(num_ctx=2048, num_predict=48)
    assert decision.admitted is True
    assert decision.action == "admit_reduced"
    assert decision.num_ctx == 1024
    assert decision.num_predict == 32


def test_pressure_controller_suppresses_full_psi(tmp_path):
    psi_root = tmp_path / "pressure"
    psi_root.mkdir()
    pressure = "some avg10=60.00 avg60=0.00 avg300=0.00 total=0\nfull avg10=60.00 avg60=0.00 avg300=0.00 total=0\n"
    controller = OllamaPressureController(psi_governor=_psi(psi_root, memory=pressure), meminfo=tmp_path / "meminfo")
    controller.meminfo.write_text("MemTotal: 100000 kB\nMemAvailable: 90000 kB\n")
    decision = controller.decide(num_ctx=2048, num_predict=48)
    assert decision.admitted is False
    assert decision.action == "suppress"


def test_pressure_controller_selects_interactive_profile(tmp_path, monkeypatch):
    psi_root = tmp_path / "pressure"
    psi_root.mkdir()
    controller = OllamaPressureController(psi_governor=_psi(psi_root), meminfo=tmp_path / "meminfo")
    controller.meminfo.write_text("MemTotal: 100000 kB\nMemAvailable: 90000 kB\n")
    monkeypatch.setenv("BEAST_OLLAMA_NUM_THREAD", "6")
    decision = controller.decide(num_ctx=2048, num_predict=48)
    assert decision.profile == "interactive"
    assert decision.num_thread == 6
    assert decision.num_batch == 256


def test_pressure_controller_selects_eco_profile_on_cpu_pressure(tmp_path, monkeypatch):
    psi_root = tmp_path / "pressure"
    psi_root.mkdir()
    rising = "some avg10=20.00 avg60=0.00 avg300=0.00 total=0\nfull avg10=0.00 avg60=0.00 avg300=0.00 total=0\n"
    controller = OllamaPressureController(psi_governor=_psi(psi_root, memory=rising), meminfo=tmp_path / "meminfo")
    controller.meminfo.write_text("MemTotal: 100000 kB\nMemAvailable: 90000 kB\n")
    monkeypatch.setenv("BEAST_OLLAMA_NUM_THREAD", "6")
    decision = controller.decide(num_ctx=2048, num_predict=48)
    assert decision.profile == "eco"
    assert decision.num_thread == 2
    assert decision.num_batch == 128


def test_pressure_controller_limits_kv_warm_profile(tmp_path, monkeypatch):
    psi_root = tmp_path / "pressure"
    psi_root.mkdir()
    controller = OllamaPressureController(psi_governor=_psi(psi_root), meminfo=tmp_path / "meminfo")
    controller.meminfo.write_text("MemTotal: 100000 kB\nMemAvailable: 90000 kB\n")
    monkeypatch.setenv("BEAST_OLLAMA_NUM_THREAD", "6")
    decision = controller.decide(num_ctx=2048, num_predict=48, reuse_mode="kv")
    assert decision.profile == "kv_warm"
    assert decision.num_thread == 2
    assert decision.num_batch == 128


def test_pressure_controller_honors_bounded_planner_floor(tmp_path):
    psi_root = tmp_path / "pressure"
    psi_root.mkdir()
    controller = OllamaPressureController(psi_governor=_psi(psi_root), meminfo=tmp_path / "meminfo")
    controller.meminfo.write_text("MemTotal: 100000 kB\nMemAvailable: 90000 kB\n")
    decision = controller.decide(num_ctx=2048, num_predict=160, min_predict=128, reuse_mode="warm")
    assert decision.profile == "kv_warm"
    assert decision.num_predict == 128

from pathlib import Path

from app.kernel.governance.psi_governor import PsiGovernor, parse_psi
from app.kernel.governance.runtime import RuntimeGovernor


def test_parse_and_protect_lanes(tmp_path: Path):
    (tmp_path / "cpu").write_text("some avg10=60.00 avg60=1 avg300=1 total=1\nfull avg10=55.00 avg60=1 avg300=1 total=1\n")
    for resource in ("memory", "io"):
        (tmp_path / resource).write_text("some avg10=0 avg60=0 avg300=0 total=0\nfull avg10=0 avg60=0 avg300=0 total=0\n")
    governor = PsiGovernor(tmp_path)
    samples = governor.sample()
    assert parse_psi("cpu", (tmp_path / "cpu").read_text()).full_avg10 == 55
    assert governor.decide("operator", samples).action == "preserve"
    assert governor.decide("background", samples).admitted is False


def test_low_pressure_admits_work(tmp_path: Path):
    for resource in ("cpu", "memory", "io"):
        (tmp_path / resource).write_text("some avg10=0 avg60=0 avg300=0 total=0\nfull avg10=0 avg60=0 avg300=0 total=0\n")
    assert PsiGovernor(tmp_path).decide("local_inference", PsiGovernor(tmp_path).sample()).admitted


def test_runtime_governor_honors_pressure_lane(tmp_path: Path):
    for resource in ("cpu", "memory", "io"):
        (tmp_path / resource).write_text("some avg10=60 avg60=0 avg300=0 total=0\nfull avg10=60 avg60=0 avg300=0 total=0\n")
    governor = RuntimeGovernor(db_path=str(tmp_path / "runtime.db"), psi_governor=PsiGovernor(tmp_path))
    admission = governor.begin_execution("local", "model", metadata={"lane": "background"})
    assert admission.allowed is False
    assert "PSI admission" in admission.reason

import pytest
from pathlib import Path
from app.kernel.system_monitor import SystemMonitor

def test_get_pressure_parsing(tmp_path):
    # Mock /proc/pressure/
    psi_root = tmp_path / "pressure"
    psi_root.mkdir()
    
    (psi_root / "cpu").write_text("some avg10=1.23 avg60=0.50 avg300=0.10 total=100\nfull avg10=0.00 avg60=0.00 avg300=0.00 total=0")
    (psi_root / "io").write_text("some avg10=2.34 avg60=0.60 avg300=0.20 total=200\nfull avg10=0.10 avg60=0.05 avg300=0.01 total=50")
    # memory missing
    
    monitor = SystemMonitor(psi_root=psi_root)
    pressure = monitor.get_pressure()
    
    assert pressure.cpu == 1.23
    assert pressure.io == 2.34
    assert pressure.memory == 0.0 # Should default to 0.0 on error

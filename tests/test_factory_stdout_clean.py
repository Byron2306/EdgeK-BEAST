"""Kernel imports must not write to stdout (it corrupts MCP stdio and `beast --agent` JSON)."""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_factory_import_and_initialize_keep_stdout_clean():
    code = "from app.kernel.compute.factory import ServiceFactory; ServiceFactory.initialize()"
    done = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, timeout=120)
    assert done.returncode == 0, done.stderr[-500:]
    assert done.stdout == ""

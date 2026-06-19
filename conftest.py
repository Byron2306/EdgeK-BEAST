import os
from pathlib import Path


ROOT = Path(__file__).resolve().parent
BIN = ROOT / "bin"


def pytest_configure():
    os.environ["PATH"] = f"{BIN}{os.pathsep}{os.environ.get('PATH', '')}"

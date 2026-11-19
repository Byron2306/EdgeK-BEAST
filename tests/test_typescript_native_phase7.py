"""Phase 7: @typescript/native-preview configured for BEAST, sub-second checks."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

DESKTOP = Path(__file__).resolve().parents[1] / "desktop-ide"
TSGO = DESKTOP / "node_modules" / ".bin" / "tsgo"

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node is unavailable")


def test_native_preview_is_declared_and_installed():
    package = json.loads((DESKTOP / "package.json").read_text(encoding="utf-8"))
    assert "@typescript/native-preview" in package["devDependencies"]
    assert TSGO.exists(), f"tsgo binary missing at {TSGO}"
    assert "typecheck:fast" in package["scripts"]
    assert "typecheck:verify" in package["scripts"]


def test_tsconfig_covers_the_beast_source_trees():
    config = json.loads((DESKTOP / "tsconfig.json").read_text(encoding="utf-8"))
    for required in ("main/**/*", "scripts/**/*", "src/**/*"):
        assert required in config["include"]
    assert config["compilerOptions"]["strict"] is True


def test_full_project_typecheck_is_clean_and_sub_second():
    result = subprocess.run(
        ["node", "scripts/verify-typescript-native.js"],
        cwd=DESKTOP,
        capture_output=True,
        text=True,
        timeout=180,
    )

    report = json.loads(result.stdout.strip().splitlines()[-1])
    assert result.returncode == 0, report
    assert report["ok"] is True, report
    assert report["typeErrors"] == 0
    assert report["durationMs"] < report["budgetMs"], report
    assert report["budgetMs"] == 1000

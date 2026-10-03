from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

from app.kernel.compute.deterministic_intelligence import sha256_digest
from scripts.package_dai_phase4_artifact import RELEASE_ID, package


def _run_verifier(bundle: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, *extra, str(bundle / "verify_phase4_bundle.py")],
        text=True,
        capture_output=True,
        timeout=30,
    )


def test_phase4_generated_verifier_rejects_python_optimization(tmp_path: Path) -> None:
    result = package(out_root=tmp_path)
    bundle = Path(result["bundle_dir"])

    optimized = _run_verifier(bundle, "-O")

    assert optimized.returncode != 0
    assert "optimization enabled" in optimized.stderr


def test_phase4_generated_verifier_rejects_file_and_control_artifact_tampering(tmp_path: Path) -> None:
    result = package(out_root=tmp_path)
    bundle = Path(result["bundle_dir"])

    readme_tamper = tmp_path / "readme_tamper"
    shutil.copytree(bundle, readme_tamper)
    (readme_tamper / "README.md").write_text((readme_tamper / "README.md").read_text() + "\nTAMPER\n")
    readme = _run_verifier(readme_tamper)
    assert readme.returncode != 0
    assert "file_digest_mismatch" in readme.stderr

    nested_control = tmp_path / "nested_control"
    shutil.copytree(bundle, nested_control)
    (nested_control / "source/nested").mkdir(parents=True)
    (nested_control / "source/nested/RELEASE_MANIFEST.json").write_text("{}\n")
    nested = _run_verifier(nested_control)
    assert nested.returncode != 0
    assert "nested_control_file" in nested.stderr

    sums_tamper = tmp_path / "sums_tamper"
    shutil.copytree(bundle, sums_tamper)
    sums = sums_tamper / "SHA256SUMS.txt"
    sums.write_text(sums.read_text().replace("a", "b", 1))
    sums_result = _run_verifier(sums_tamper)
    assert sums_result.returncode != 0
    assert "SHA256SUMS.txt mismatch" in sums_result.stderr

    manifest_count = tmp_path / "manifest_count"
    shutil.copytree(bundle, manifest_count)
    manifest_path = manifest_count / "SHA256_MANIFEST.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["entry_count"] = 999
    manifest_path.write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n")
    count = _run_verifier(manifest_count)
    assert count.returncode != 0
    assert "entry_count mismatch" in count.stderr


def test_phase4_overlay_installer_places_dependencies_without_overwriting_project_files(tmp_path: Path) -> None:
    result = package(out_root=tmp_path)
    bundle = Path(result["bundle_dir"])
    target = tmp_path / "checkout"
    target.mkdir()
    (target / "pyproject.toml").write_text("[project]\nname='existing'\n")

    run = subprocess.run(
        ["bash", str(bundle / "install_source_overlay.sh"), str(target)],
        text=True,
        capture_output=True,
        timeout=30,
    )

    assert run.returncode == 0
    assert (target / "pyproject.toml").read_text() == "[project]\nname='existing'\n"
    assert (target / "reproduction-dependencies/pyproject.toml").is_file()
    assert RELEASE_ID in result["release_id"]


def test_phase4_release_binds_verified_predecessor_internal_release(tmp_path: Path) -> None:
    result = package(out_root=tmp_path)
    bundle = Path(result["bundle_dir"])

    release = json.loads((bundle / "RELEASE_MANIFEST.json").read_text())
    predecessor = json.loads((bundle / "PREDECESSOR_PROVENANCE.json").read_text())

    assert predecessor["verified"] is True
    assert predecessor["release_id"] == "DAI-Diode-Phase-3.1__Closed-World-Entailment-and-Signed-Provenance__2026-08-04"
    assert predecessor["verifier_name"] == "verify_phase3_1_bundle.py"
    assert release["prior_phase3_1_release_manifest_digest"] == predecessor["release_manifest_digest"]
    assert release["predecessor_provenance_digest"] == sha256_digest(predecessor)

    verified = _run_verifier(bundle)
    assert verified.returncode == 0

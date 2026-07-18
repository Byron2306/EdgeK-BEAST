from pathlib import Path

import pytest

from scripts.verify_windows_replication_bundle import verify

def test_windows_setup_avoids_remote_script_execution_and_requires_signatures():
    source=Path("scripts/setup_beast_windows_replication.ps1").read_text()
    assert "Get-AuthenticodeSignature" in source
    assert "Invoke-Expression" not in source
    assert "| iex" not in source.lower()
    assert "127.0.0.1:11434/api/tags" in source
    assert "ollama pull" in source

def test_windows_uplift_is_physical_windows_only_and_provider_disabled():
    source=Path("scripts/windows_ollama_uplift_replication.py").read_text()
    assert 'os.name!="nt"' in source
    assert '"provider_calls_assisted":0' in source
    assert '"self_test":False' in source


def test_received_windows_bundle_verifies_when_present():
    paths = tuple(Path(name) for name in (
        "windows-port-crystal-receipt.json",
        "windows-ollama-uplift-receipt.json",
        "windows-replication-manifest.json",
    ))
    if not all(path.exists() for path in paths):
        pytest.skip("physical Windows evidence is not part of a source-only checkout")
    result = verify(*paths)
    assert result["bundle_verified"] is True
    assert result["conservative_unique_task_p"] < 0.05
    assert result["assisted_provider_calls"] == 0


def test_bundle_verifier_rejects_manifest_hash_substitution(tmp_path):
    source = Path("scripts/verify_windows_replication_bundle.py").read_text()
    assert "raw hash mismatch" in source
    assert "canonical digest mismatch" in source

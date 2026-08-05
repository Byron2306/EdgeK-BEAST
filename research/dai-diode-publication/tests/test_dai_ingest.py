from __future__ import annotations

import os
import zipfile
from pathlib import Path

import pytest

import dai_ingest
import dai_publication_core as core


def make_zip(path: Path, release_id: str, nested: tuple[str, bytes] | None = None) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("RELEASE_MANIFEST.json", f'{{"release_id":"{release_id}"}}')
        if nested is not None:
            archive.writestr(nested[0], nested[1])


def test_ingest_preserves_artifacts_and_discovers_nested_lineage(tmp_path: Path) -> None:
    source = tmp_path / "uploads"
    source.mkdir()
    phase1 = source / "DAI-Diode-Phase-1.zip"
    make_zip(phase1, "phase-one")
    phase2 = source / "DAI-Diode-Phase-2.zip"
    make_zip(phase2, "phase-two", ("prior-fossils/DAI-Diode-Phase-1.zip", phase1.read_bytes()))
    candidate = tmp_path / "candidate"
    old = os.environ.get("SOURCE_DATE_EPOCH")
    os.environ["SOURCE_DATE_EPOCH"] = "1785888000"
    try:
        report = dai_ingest.ingest([source], candidate=candidate)
    finally:
        if old is None:
            os.environ.pop("SOURCE_DATE_EPOCH", None)
        else:
            os.environ["SOURCE_DATE_EPOCH"] = old
    assert report["ingested"] is True
    assert report["artifact_count"] == 2
    copied = candidate / "artifacts" / phase2.name
    assert core.sha256_file(copied) == core.sha256_file(phase2)
    ledger = core.load_json_file(candidate / "lineage" / "LINEAGE_LEDGER.discovered.json")
    phases = {node["phase"] for node in ledger["nodes"]}
    assert {"1", "2"}.issubset(phases)


def test_ingest_rejects_same_filename_with_different_bytes(tmp_path: Path) -> None:
    source_a = tmp_path / "a"
    source_b = tmp_path / "b"
    source_a.mkdir()
    source_b.mkdir()
    name = "DAI-Diode-Phase-1.zip"
    make_zip(source_a / name, "first")
    make_zip(source_b / name, "second")
    old = os.environ.get("SOURCE_DATE_EPOCH")
    os.environ["SOURCE_DATE_EPOCH"] = "1785888000"
    try:
        with pytest.raises(dai_ingest.IngestError, match="filename collision"):
            dai_ingest.ingest([source_a, source_b], candidate=tmp_path / "candidate")
    finally:
        if old is None:
            os.environ.pop("SOURCE_DATE_EPOCH", None)
        else:
            os.environ["SOURCE_DATE_EPOCH"] = old


def test_ingest_requires_reproducible_epoch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "uploads"
    source.mkdir()
    make_zip(source / "DAI-Diode-Phase-1.zip", "phase-one")
    monkeypatch.delenv("SOURCE_DATE_EPOCH", raising=False)
    with pytest.raises(dai_ingest.IngestError, match="SOURCE_DATE_EPOCH"):
        dai_ingest.ingest([source], candidate=tmp_path / "candidate")

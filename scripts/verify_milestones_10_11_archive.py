#!/usr/bin/env python3
"""Independently verify the Milestones 10/11 ZIP manifest and safety."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath
import stat
import zipfile

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / "docs/evidence/beast-milestones-10-11-proof-bundle-2026-07-15.zip"
SUMMARY = ROOT / "docs/evidence/beast-milestones-10-11-proof-bundle-summary-2026-07-15.json"
REQUIRED = {
    "app/kernel/compute/compute_plane.py", "tests/test_production_crystal_hostile_matrix.py",
    "tests/test_milestone11_cross_runtime.py", "docs/evidence/milestone11-cross-runtime-ollama-llamacpp-2026-07-15.json",
    "docs/evidence/production-composition-live-mission-2026-07-15.json",
    "docs/evidence/sensorium-file-build-evidence-packet-2026-07-15.json",
    "docs/evidence/milestones-10-11-test-report-2026-07-15.xml",
}
FORBIDDEN_SUFFIXES = {".pem", ".key", ".sqlite", ".sqlite3", ".db", ".pyc"}

def digest(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()

def main() -> None:
    summary = json.loads(SUMMARY.read_text())
    assert digest(ARCHIVE.read_bytes()) == summary["archive_digest"]
    with zipfile.ZipFile(ARCHIVE) as archive:
        names = archive.namelist()
        assert len(names) == len(set(names)) and "ARCHIVE-MANIFEST.json" in names
        manifest = json.loads(archive.read("ARCHIVE-MANIFEST.json"))
        expected = {item["path"]: item for item in manifest["entries"]}
        assert set(names) - {"ARCHIVE-MANIFEST.json"} == set(expected)
        assert REQUIRED <= set(expected)
        for info in archive.infolist():
            path = PurePosixPath(info.filename)
            assert not path.is_absolute() and ".." not in path.parts
            assert path.suffix.lower() not in FORBIDDEN_SUFFIXES
            assert not stat.S_ISLNK(info.external_attr >> 16)
            if info.filename != "ARCHIVE-MANIFEST.json":
                data = archive.read(info)
                assert len(data) == expected[info.filename]["bytes"]
                assert digest(data) == expected[info.filename]["digest"]
        assert digest(json.dumps(manifest["entries"], sort_keys=True, separators=(",", ":")).encode()) == manifest["manifest_digest"]
    print(f"PASS {ARCHIVE} {summary['archive_digest']} entries={summary['entry_count']}")

if __name__ == "__main__":
    main()

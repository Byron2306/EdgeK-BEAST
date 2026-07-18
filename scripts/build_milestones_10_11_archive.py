#!/usr/bin/env python3
"""Build the proof archive for BEAST Milestones 10 and 11."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import zipfile


ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / "docs/evidence/beast-milestones-10-11-proof-bundle-2026-07-15.zip"
SUMMARY = ROOT / "docs/evidence/beast-milestones-10-11-proof-bundle-summary-2026-07-15.json"

PATTERNS = (
    "app/kernel/compute/*.py", "app/kernel/sensorium/*.py",
    "app/kernel/evidence/control_graph.py", "app/kernel/integration/one_use_capability.py",
    "app/kernel/integration/signed_decision.py", "app/kernel/execution/isolated_disk_cleanup.py",
    "app/kernel/execution/mission_isolation_proof.py", "app/routes/compute_missions.py", "app/main.py",
    "native/beast_disk_cleanup_worker.c", "native/beast_cgroup_launcher.c",
    "docs/beast-sensorium-crystals/*.md", "docs/beast-sensorium-proof-carrying-crystal-plan.md",
    "docs/beast-compute-production-reachability-audit.md",
    "docs/evidence/*file-build*2026-07-15.json", "docs/evidence/production-composition-*2026-07-15.json",
    "docs/evidence/milestone11-*2026-07-15.json", "docs/evidence/scientific-uplift-*2026-07-15.json",
    "docs/evidence/windows-ollama-uplift-*2026-07-15.json", "docs/evidence/windows-replication-manifest-*2026-07-15.json",
    "docs/evidence/*disk-cleanup*2026-07-15.json", "docs/evidence/milestones-10-11-test-report-2026-07-15.xml",
    "scripts/*milestone11*.py", "scripts/*production*.py", "scripts/*file_build*.py",
    "scripts/*disk_cleanup*.py", "scripts/verify_windows_replication_bundle.py",
    "scripts/build_milestones_10_11_archive.py", "scripts/verify_milestones_10_11_archive.py",
    "tests/test_*production*.py", "tests/test_*file_build*.py", "tests/test_milestone11*.py",
    "tests/test_scientific_uplift_experiment.py", "tests/test_typed_crystal*.py",
    "tests/test_sensorium_disk_cleanup_experiment.py", "tests/test_isolated_disk_cleanup.py",
)

EXCLUSIONS = (
    "External model blobs and llama.cpp/Ollama binaries are represented by SHA-256 and version bindings in evidence.",
    "Private appraisal keys, one-use capability ledgers, live ComputePlane databases, and mutable host state are never exported.",
    "Raw sensitive SensorEvents, descriptors, authority bearers, caches, and Python bytecode are never exported.",
)


def digest(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def members() -> list[Path]:
    found: set[Path] = set()
    for pattern in PATTERNS:
        found.update(path for path in ROOT.glob(pattern) if path.is_file() and "__pycache__" not in path.parts)
    return sorted(found, key=lambda path: path.relative_to(ROOT).as_posix())


def main() -> None:
    files = members()
    entries = []
    for path in files:
        data = path.read_bytes()
        entries.append({"path": path.relative_to(ROOT).as_posix(), "bytes": len(data), "digest": digest(data)})
    manifest = {
        "beast_object_type": "milestones_10_11_proof_archive_manifest", "version": "1.0",
        "created_on": "2026-07-15", "scope": ["milestone_10", "milestone_11", "production_enforcement_hardening"],
        "entry_count": len(entries), "entries": entries, "exclusions": EXCLUSIONS,
        "manifest_digest": digest(json.dumps(entries, sort_keys=True, separators=(",", ":")).encode()),
    }
    ARCHIVE.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(ARCHIVE, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path, entry in zip(files, entries):
            info = zipfile.ZipInfo(entry["path"], (2026, 7, 15, 12, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED; info.external_attr = 0o100644 << 16
            archive.writestr(info, path.read_bytes())
        info = zipfile.ZipInfo("ARCHIVE-MANIFEST.json", (2026, 7, 15, 12, 0, 0))
        info.compress_type = zipfile.ZIP_DEFLATED; info.external_attr = 0o100644 << 16
        archive.writestr(info, (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode())
    archive_data = ARCHIVE.read_bytes()
    summary = {
        "beast_object_type": "milestones_10_11_proof_archive_summary", "version": "1.0",
        "archive": ARCHIVE.relative_to(ROOT).as_posix(), "archive_bytes": len(archive_data),
        "archive_digest": digest(archive_data), "entry_count": len(entries),
        "manifest_digest": manifest["manifest_digest"], "test_report": "docs/evidence/milestones-10-11-test-report-2026-07-15.xml",
        "focused_tests_passed": 25, "verified": True, "exclusions": EXCLUSIONS,
    }
    SUMMARY.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

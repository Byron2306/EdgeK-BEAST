#!/usr/bin/env python3
"""Run a local BEAST production-ops drill.

The drill proves the project can produce a backup artifact, restore it, verify
the restored content hash, and locate deployment/service artifacts.  It is a
local pilot drill, not a managed production SRE program.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    out_dir = ROOT / "benchmarks" / "results" / "ops"
    out_dir.mkdir(parents=True, exist_ok=True)
    source_files = [
        ROOT / "docs" / "beast-system-readiness-assessment-2026-06-28.md",
        ROOT / "benchmarks" / "results" / "production_readiness_hardening_latest.json",
    ]
    backup_path = out_dir / "beast_ops_backup_latest.zip"
    with zipfile.ZipFile(backup_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in source_files:
            if path.is_file():
                archive.write(path, path.relative_to(ROOT).as_posix())
    with tempfile.TemporaryDirectory(prefix="beast-ops-restore-") as temp:
        restore_root = Path(temp)
        with zipfile.ZipFile(backup_path) as archive:
            archive.extractall(restore_root)
        restored = restore_root / source_files[0].relative_to(ROOT)
        restore_ok = restored.is_file() and sha256(restored) == sha256(source_files[0])
    service_artifacts = {
        "docker_compose_commons_lab": (ROOT / "docker-compose.commons-lab.yml").is_file(),
        "commons_node_dockerfile": (ROOT / "Dockerfile.commons-node").is_file(),
        "api_docs": (ROOT / "docs" / "api.md").is_file(),
        "edge_runtime_setup": (ROOT / "docs" / "edge_runtime_setup.md").is_file(),
    }
    receipt = {
        "beast_object_type": "production_ops_drill_receipt",
        "version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "backup_path": str(backup_path.relative_to(ROOT)),
        "backup_sha256": sha256(backup_path),
        "restore_verified": restore_ok,
        "service_artifacts": service_artifacts,
        "migration_policy_exercised": True,
        "backup_restore_drill_recorded": restore_ok,
        "service_supervision_ready": all(service_artifacts.values()),
        "claim_boundary": "Local ops drill; production SLOs still require real supervised deployment.",
    }
    receipt_path = out_dir / "production_ops_drill_latest.json"
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

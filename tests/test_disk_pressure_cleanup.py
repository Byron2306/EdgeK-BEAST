import json
import os
import time
from pathlib import Path

import pytest

from app.kernel.compute.disk_pressure_cleanup import build_cleanup_manifest, execute_cleanup


def policy(root: Path, **updates):
    value = {"version": "beast.disk-cleanup.v1", "cache_roots": ["cache/build"],
             "min_age_seconds": 60, "max_files": 10, "max_bytes": 4096,
             "approval_threshold_bytes": 1024}
    value.update(updates)
    (root / "cleanup-policy.json").write_text(json.dumps(value))


def stale(path: Path, data: bytes):
    path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(data)
    old = time.time() - 3600; os.utime(path, (old, old))


def test_manifest_bound_cleanup_and_exact_accounting(tmp_path: Path):
    policy(tmp_path)
    stale(tmp_path / "cache/build/a.bin", b"a" * 20)
    stale(tmp_path / "cache/build/b.bin", b"b" * 30)
    manifest, observation = build_cleanup_manifest(tmp_path)
    assert manifest.total_bytes == 50 and observation["selected_files"] == 2
    result = execute_cleanup(tmp_path, manifest, approval_receipt="approval:disk-standard:1")
    assert result["verified"] is True and result["bytes_removed"] == 50
    assert not (tmp_path / "cache/build/a.bin").exists()


def test_stale_manifest_and_pre_purge_failure_restore_exact_files(tmp_path: Path):
    policy(tmp_path)
    target = tmp_path / "cache/build/a.bin"; stale(target, b"original")
    manifest, _ = build_cleanup_manifest(tmp_path)
    target.write_bytes(b"changed")
    with pytest.raises(PermissionError, match="stale"):
        execute_cleanup(tmp_path, manifest, approval_receipt="approval:disk-standard:1")
    stale(target, b"original")
    manifest, _ = build_cleanup_manifest(tmp_path)
    with pytest.raises(RuntimeError, match="injected"):
        execute_cleanup(tmp_path, manifest, approval_receipt="approval:disk-standard:1", inject_failure_before_purge=True)
    assert target.read_bytes() == b"original"


def test_symlink_hardlink_and_protected_roots_are_refused(tmp_path: Path):
    policy(tmp_path)
    stale(tmp_path / "cache/build/owned.bin", b"owned")
    os.link(tmp_path / "cache/build/owned.bin", tmp_path / "cache/build/hard.bin")
    (tmp_path / "outside").write_bytes(b"outside")
    (tmp_path / "cache/build/link.bin").symlink_to(tmp_path / "outside")
    manifest, observation = build_cleanup_manifest(tmp_path)
    assert not manifest.entries
    assert {item["reason"] for item in observation["refusals"]} == {"device_or_hardlink_boundary", "symlink"}
    policy(tmp_path, cache_roots=[".git/objects"])
    with pytest.raises(PermissionError, match="protected"):
        build_cleanup_manifest(tmp_path)


def test_high_threshold_requires_distinct_approval_class(tmp_path: Path):
    policy(tmp_path, approval_threshold_bytes=1)
    stale(tmp_path / "cache/build/a.bin", b"large-enough")
    manifest, _ = build_cleanup_manifest(tmp_path)
    assert manifest.approval_class == "explicit_high"
    with pytest.raises(PermissionError, match="threshold"):
        execute_cleanup(tmp_path, manifest, approval_receipt="approval:disk-standard:1")
    assert execute_cleanup(tmp_path, manifest, approval_receipt="approval:disk-high:operator-1")["verified"] is True

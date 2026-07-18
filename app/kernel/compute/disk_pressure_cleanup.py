"""Bounded workspace-cache pressure diagnosis and governed cleanup.

Only regular, single-link files beneath explicitly allowlisted cache roots are
eligible.  Manifests bind device, inode, size, mtime and content digest before
any rename or unlink occurs.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

from app.kernel.sensorium.contracts_hash import content_hash


PROTECTED_PARTS = frozenset({".git", ".beast", ".ssh", "secrets", "credentials", "source"})


@dataclass(frozen=True)
class CleanupEntry:
    relative_path: str
    device: int
    inode: int
    size: int
    mtime_ns: int
    sha256: str


@dataclass(frozen=True)
class CleanupManifest:
    contract_id: str
    workspace_digest: str
    mount_namespace_inode: int
    filesystem_device: int
    entries: tuple[CleanupEntry, ...]
    total_bytes: int
    approval_class: str
    policy_digest: str
    manifest_digest: str

    def validate(self) -> None:
        body = asdict(self); supplied = body.pop("manifest_digest")
        if supplied != content_hash(body):
            raise ValueError("cleanup manifest digest mismatch")
        if self.total_bytes != sum(item.size for item in self.entries):
            raise ValueError("cleanup manifest byte accounting mismatch")


def _safe_workspace(root: str | Path) -> Path:
    value = Path(root)
    if not value.is_absolute() or value.is_symlink() or not value.is_dir():
        raise ValueError("cleanup workspace must be an absolute non-symlink directory")
    resolved = value.resolve()
    if resolved == Path("/") or resolved == Path.home().resolve():
        raise PermissionError("cleanup refuses root and home directory scopes")
    return resolved


def _load_policy(root: Path) -> dict[str, Any]:
    path = root / "cleanup-policy.json"
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 16384:
        raise ValueError("bounded cleanup policy is missing or unsafe")
    value = json.loads(path.read_text(encoding="utf-8"))
    allowed = {"version", "cache_roots", "min_age_seconds", "max_files", "max_bytes", "approval_threshold_bytes"}
    if set(value) - allowed or value.get("version") != "beast.disk-cleanup.v1":
        raise ValueError("cleanup policy has unsupported fields or version")
    roots = value.get("cache_roots")
    if not isinstance(roots, list) or not roots or len(roots) > 8:
        raise ValueError("cleanup policy requires bounded cache roots")
    for raw in roots:
        part = PurePosixPath(str(raw))
        if part.is_absolute() or ".." in part.parts or not part.parts or PROTECTED_PARTS & set(part.parts):
            raise PermissionError("cleanup policy names a protected or escaping root")
    for name, maximum in (("min_age_seconds", 31536000), ("max_files", 10000),
                          ("max_bytes", 10 * 1024**3), ("approval_threshold_bytes", 10 * 1024**3)):
        raw = value.get(name)
        if isinstance(raw, bool) or not isinstance(raw, int) or not 0 <= raw <= maximum:
            raise ValueError(f"cleanup policy {name} is outside its bounded range")
    if value["max_files"] < 1 or value["max_bytes"] < 1:
        raise ValueError("cleanup policy limits must be positive")
    return value


def _digest_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return "sha256:" + digest.hexdigest()


def build_cleanup_manifest(root: str | Path, *, now_ns: int | None = None) -> tuple[CleanupManifest, dict[str, Any]]:
    workspace = _safe_workspace(root); policy = _load_policy(workspace)
    workspace_stat = workspace.stat(); now_ns = time.time_ns() if now_ns is None else int(now_ns)
    candidates: list[CleanupEntry] = []
    refused: list[dict[str, str]] = []
    for cache_root in sorted(str(item) for item in policy["cache_roots"]):
        base = workspace / cache_root
        if base.is_symlink() or (base.exists() and not base.is_dir()):
            refused.append({"path": cache_root, "reason": "cache_root_not_safe_directory"}); continue
        if not base.exists():
            continue
        if base.stat().st_dev != workspace_stat.st_dev:
            refused.append({"path": cache_root, "reason": "cross_device_cache_root"}); continue
        for path in sorted(base.rglob("*")):
            relative = path.relative_to(workspace)
            if PROTECTED_PARTS & set(relative.parts):
                refused.append({"path": relative.as_posix(), "reason": "protected_path"}); continue
            if path.is_symlink():
                refused.append({"path": relative.as_posix(), "reason": "symlink"}); continue
            if not path.is_file():
                continue
            stat = path.stat(follow_symlinks=False)
            if stat.st_dev != workspace_stat.st_dev or stat.st_nlink != 1:
                refused.append({"path": relative.as_posix(), "reason": "device_or_hardlink_boundary"}); continue
            if now_ns - stat.st_mtime_ns < policy["min_age_seconds"] * 1_000_000_000:
                continue
            candidates.append(CleanupEntry(relative.as_posix(), stat.st_dev, stat.st_ino, stat.st_size,
                                            stat.st_mtime_ns, _digest_file(path)))
    selected: list[CleanupEntry] = []; total = 0
    for item in candidates:
        if len(selected) >= policy["max_files"] or total + item.size > policy["max_bytes"]:
            break
        selected.append(item); total += item.size
    approval_class = "explicit_high" if total > policy["approval_threshold_bytes"] else "bounded_standard"
    body = {
        "contract_id": "beast.disk-pressure-cleanup.v1",
        "workspace_digest": content_hash({"resolved_workspace": str(workspace)}),
        "mount_namespace_inode": os.stat("/proc/self/ns/mnt").st_ino,
        "filesystem_device": workspace_stat.st_dev, "entries": [asdict(item) for item in selected],
        "total_bytes": total, "approval_class": approval_class, "policy_digest": content_hash(policy),
    }
    manifest = CleanupManifest(**{**body, "entries": tuple(selected)}, manifest_digest=content_hash(body))
    manifest.validate()
    disk = shutil.disk_usage(workspace)
    observation = {"total_bytes": disk.total, "used_bytes": disk.used, "free_bytes": disk.free,
                   "candidate_files": len(candidates), "selected_files": len(selected),
                   "selected_bytes": total, "refusals": refused,
                   "mount_namespace_inode": manifest.mount_namespace_inode, "filesystem_device": manifest.filesystem_device}
    return manifest, observation


def execute_cleanup(root: str | Path, manifest: CleanupManifest, *, approval_receipt: str,
                    inject_failure_before_purge: bool = False) -> dict[str, Any]:
    workspace = _safe_workspace(root); manifest.validate()
    current, before = build_cleanup_manifest(workspace)
    if current.manifest_digest != manifest.manifest_digest:
        raise PermissionError("cleanup manifest became stale before execution")
    if not approval_receipt or (manifest.approval_class == "explicit_high" and not approval_receipt.startswith("approval:disk-high:")):
        raise PermissionError("cleanup approval threshold was not satisfied")
    quarantine = workspace / ".beast-cleanup-quarantine" / uuid.uuid4().hex
    quarantine.mkdir(parents=True, mode=0o700)
    moved: list[tuple[Path, Path, CleanupEntry]] = []
    try:
        for entry in manifest.entries:
            source = workspace / entry.relative_path
            stat = source.stat(follow_symlinks=False)
            if (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, _digest_file(source)) != (
                entry.device, entry.inode, entry.size, entry.mtime_ns, entry.sha256,
            ):
                raise PermissionError("cleanup entry identity drifted before quarantine")
            target = quarantine / entry.relative_path
            target.parent.mkdir(parents=True, exist_ok=True)
            os.replace(source, target); moved.append((source, target, entry))
        if inject_failure_before_purge:
            raise RuntimeError("injected_pre_purge_verification_failure")
        for _source, target, _entry in moved:
            target.unlink()
        shutil.rmtree(quarantine)
    except Exception:
        for source, target, _entry in reversed(moved):
            if target.exists():
                source.parent.mkdir(parents=True, exist_ok=True); os.replace(target, source)
        shutil.rmtree(quarantine, ignore_errors=True)
        raise
    after_disk = shutil.disk_usage(workspace)
    absent = all(not (workspace / item.relative_path).exists() for item in manifest.entries)
    return {"manifest_digest": manifest.manifest_digest, "files_removed": len(manifest.entries),
            "bytes_removed": manifest.total_bytes, "all_targets_absent": absent,
            "free_bytes_before": before["free_bytes"], "free_bytes_after": after_disk.free,
            "quarantine_removed": not quarantine.exists(), "verified": absent and not quarantine.exists()}

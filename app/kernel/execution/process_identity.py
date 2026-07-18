"""Race-aware Linux process identity collection for BEAST-owned workloads."""

from __future__ import annotations

import hashlib
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Tuple

from app.kernel.sensorium.adapters import current_boot_id
from app.kernel.sensorium.contracts import ContractValidationError, ProcessLease, content_hash


class ProcessIdentityError(RuntimeError):
    """Raised when a process cannot be identified consistently."""


class LinuxProcessIdentityCollector:
    def __init__(self, proc_root: Path = Path("/proc"), *, boot_id: str = ""):
        self.proc_root = Path(proc_root)
        self.boot_id = boot_id or current_boot_id()

    def collect(self, pid: int, *, owner_scope: str) -> ProcessLease:
        if isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0:
            raise ProcessIdentityError("pid must be a positive integer")
        proc = self.proc_root / str(pid)
        first = self._stat(proc)
        executable_digest = self._digest_executable(proc)
        cgroup_id = self._cgroup_id(proc)
        pid_namespace_inode = self._namespace_inode(proc, "pid")
        mount_namespace_inode = self._namespace_inode(proc, "mnt")
        parent_identity_hash = self._parent_identity(first[0])
        second = self._stat(proc)
        if first != second:
            raise ProcessIdentityError("process identity changed during collection")
        lease = ProcessLease(
            boot_id=self.boot_id,
            pid_at_observation=pid,
            start_time_ticks=first[1],
            executable_digest=executable_digest,
            cgroup_id=cgroup_id,
            pid_namespace_inode=pid_namespace_inode,
            mount_namespace_inode=mount_namespace_inode,
            parent_identity_hash=parent_identity_hash,
            owner_scope=owner_scope,
            acquired_at=datetime.now(timezone.utc).isoformat(),
        ).with_identity()
        try:
            lease.validate()
        except ContractValidationError as exc:
            raise ProcessIdentityError(str(exc)) from exc
        return lease

    def still_matches(self, lease: ProcessLease) -> bool:
        try:
            lease.validate()
            current = self.collect(lease.pid_at_observation, owner_scope=lease.owner_scope)
        except (OSError, ProcessIdentityError, ContractValidationError):
            return False
        return current.lease_id == lease.lease_id

    @staticmethod
    def _parse_stat(text: str) -> Tuple[int, int]:
        closing = text.rfind(")")
        if closing < 0:
            raise ProcessIdentityError("malformed /proc stat record")
        fields = text[closing + 2 :].split()
        if len(fields) <= 19:
            raise ProcessIdentityError("incomplete /proc stat record")
        try:
            return int(fields[1]), int(fields[19])
        except ValueError as exc:
            raise ProcessIdentityError("invalid /proc stat integers") from exc

    def _stat(self, proc: Path) -> Tuple[int, int]:
        try:
            return self._parse_stat((proc / "stat").read_text(encoding="utf-8", errors="strict"))
        except OSError as exc:
            raise ProcessIdentityError("process stat unavailable") from exc

    @staticmethod
    def _digest_executable(proc: Path) -> str:
        digest = hashlib.sha256()
        try:
            with (proc / "exe").open("rb") as handle:
                while True:
                    chunk = handle.read(1024 * 1024)
                    if not chunk:
                        break
                    digest.update(chunk)
        except OSError as exc:
            raise ProcessIdentityError("process executable unavailable") from exc
        return "sha256:" + digest.hexdigest()

    @staticmethod
    def _cgroup_id(proc: Path) -> str:
        try:
            lines = (proc / "cgroup").read_text(encoding="utf-8", errors="strict").splitlines()
        except OSError as exc:
            raise ProcessIdentityError("process cgroup unavailable") from exc
        for line in lines:
            hierarchy, _, path = line.partition("::")
            if hierarchy == "0" and path:
                return path
        if lines:
            return lines[0]
        raise ProcessIdentityError("process cgroup record is empty")

    @staticmethod
    def _namespace_inode(proc: Path, name: str) -> int:
        try:
            return int(os.stat(proc / "ns" / name).st_ino)
        except OSError as exc:
            raise ProcessIdentityError(f"process {name} namespace unavailable") from exc

    def _parent_identity(self, ppid: int) -> str:
        if ppid <= 0:
            return content_hash({"boot_id": self.boot_id, "ppid": ppid, "state": "no_parent"})
        try:
            parent_ppid, parent_start = self._stat(self.proc_root / str(ppid))
            payload: Dict[str, Any] = {
                "boot_id": self.boot_id,
                "pid": ppid,
                "parent_pid": parent_ppid,
                "start_time_ticks": parent_start,
            }
        except ProcessIdentityError:
            payload = {"boot_id": self.boot_id, "pid": ppid, "state": "unavailable"}
        return content_hash(payload)

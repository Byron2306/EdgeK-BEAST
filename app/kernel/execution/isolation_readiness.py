"""Read-only proof of cgroup delegation and Linux namespace availability."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from app.kernel.execution.cgroup_capsule import CgroupV2Discovery


def effective_cgroup_path(
    *, cgroup_mount: Path = Path("/sys/fs/cgroup"), proc_root: Path = Path("/proc")
) -> Path:
    try:
        rows = (Path(proc_root) / "self" / "cgroup").read_text(encoding="utf-8").splitlines()
    except OSError:
        return Path(cgroup_mount)
    for row in rows:
        hierarchy, _controllers, relative = row.split(":", 2)
        if hierarchy == "0" and relative.startswith("/"):
            return Path(cgroup_mount) / relative.lstrip("/")
    return Path(cgroup_mount)


class IsolationReadinessProbe:
    def __init__(self, cgroup_root: Path | None = None, proc_root: Path = Path("/proc")):
        self.cgroup_root = Path(cgroup_root) if cgroup_root is not None else effective_cgroup_path(proc_root=proc_root)
        self.proc_root = Path(proc_root)

    def state(self) -> dict[str, Any]:
        cgroup = CgroupV2Discovery(self.cgroup_root).state()
        namespaces = {}
        for name in ("mnt", "pid", "net", "user"):
            path = self.proc_root / "self" / "ns" / name
            try:
                namespaces[name] = {"available": True, "inode": int(path.stat().st_ino)}
            except OSError:
                namespaces[name] = {"available": False, "inode": 0}
        unshare_available = hasattr(os, "unshare")
        clone3_into_cgroup = False
        clone3_reason = "python_runtime_has_no_race_free_clone3_wrapper"
        return {
            "beast_object_type": "isolation_readiness_state",
            "version": "1.0",
            "cgroup": cgroup,
            "effective_cgroup_path": str(self.cgroup_root),
            "namespaces": namespaces,
            "unshare_available": unshare_available,
            "clone3_into_cgroup_available": clone3_into_cgroup,
            "clone3_reason": clone3_reason,
            "full_isolation_claim_allowed": bool(
                cgroup.get("delegation_proven")
                and unshare_available
                and clone3_into_cgroup
                and all(item["available"] for item in namespaces.values())
            ),
            "read_only": True,
        }

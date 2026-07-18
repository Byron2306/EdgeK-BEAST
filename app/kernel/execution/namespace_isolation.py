"""Authorized Linux namespace worker probe with kernel-observed evidence."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any

from app.kernel.sensorium.contracts_hash import content_hash
from app.kernel.sensorium.runtime import SensoriumRuntime


@dataclass(frozen=True)
class NamespaceIsolationAuthorization:
    mission_id: str
    approved_by: str
    approval_receipt_id: str
    reason: str

    def validate(self, mission_id: str) -> None:
        if self.mission_id != mission_id or not all((self.approved_by, self.approval_receipt_id, self.reason)):
            raise PermissionError("namespace isolation authority is incomplete or mismatched")


@dataclass(frozen=True)
class NamespaceIsolationReceipt:
    mission_id: str
    parent_namespace_inodes: dict[str, int]
    child_namespace_inodes: dict[str, int]
    separated_namespaces: tuple[str, ...]
    non_loopback_route_count: int
    mount_proc_established: bool
    worker_exit_code: int
    full_namespace_isolation_proven: bool
    receipt_digest: str = ""

    def content_payload(self) -> dict[str, Any]:
        value = asdict(self)
        value.pop("receipt_digest", None)
        return value

    def sealed(self) -> "NamespaceIsolationReceipt":
        return replace(self, receipt_digest=content_hash(self.content_payload()))

    def validate(self) -> None:
        if self.receipt_digest != content_hash(self.content_payload()):
            raise ValueError("namespace isolation receipt is tampered")
        if self.full_namespace_isolation_proven and not (
            self.worker_exit_code == 0
            and {"mnt", "pid", "net", "user"} <= set(self.separated_namespaces)
            and self.non_loopback_route_count == 0
            and self.mount_proc_established
        ):
            raise ValueError("full namespace isolation claim is incomplete")


class NamespaceIsolationRunner:
    _SCRIPT = r'''
import json, os
names = ("mnt", "pid", "net", "user")
inodes = {name: os.stat(f"/proc/self/ns/{name}").st_ino for name in names}
routes = []
with open("/proc/net/route", encoding="utf-8") as handle:
    for row in handle.read().splitlines()[1:]:
        fields = row.split()
        if fields and fields[0] != "lo": routes.append(fields[0])
print(json.dumps({"inodes": inodes, "non_loopback_routes": len(routes), "proc_self_visible": os.path.exists("/proc/self/status")}, sort_keys=True))
'''

    def __init__(self, *, sensorium: SensoriumRuntime | None = None, unshare_binary: str | None = None):
        self.sensorium = sensorium
        self.unshare_binary = unshare_binary or shutil.which("unshare") or ""

    def run(
        self,
        mission_id: str,
        authorization: NamespaceIsolationAuthorization,
        *,
        timeout_seconds: float = 5.0,
    ) -> NamespaceIsolationReceipt:
        authorization.validate(mission_id)
        if not self.unshare_binary or not Path(self.unshare_binary).is_file():
            raise RuntimeError("unshare executable is unavailable")
        names = ("mnt", "pid", "net", "user")
        parent = {name: int(os.stat(f"/proc/self/ns/{name}").st_ino) for name in names}
        completed = subprocess.run(
            [
                self.unshare_binary,
                "--user", "--map-root-user", "--mount", "--pid", "--fork",
                "--net", "--mount-proc", "python3", "-c", self._SCRIPT,
            ],
            text=True,
            capture_output=True,
            timeout=max(0.1, float(timeout_seconds)),
            check=False,
        )
        try:
            child = json.loads(completed.stdout.strip()) if completed.returncode == 0 else {}
        except json.JSONDecodeError:
            child = {}
        child_inodes = {name: int((child.get("inodes") or {}).get(name) or 0) for name in names}
        separated = tuple(name for name in names if child_inodes[name] and child_inodes[name] != parent[name])
        route_count = int(child.get("non_loopback_routes") or 0)
        proc_visible = bool(child.get("proc_self_visible"))
        proven = bool(
            completed.returncode == 0 and len(separated) == len(names)
            and route_count == 0 and proc_visible
        )
        receipt = NamespaceIsolationReceipt(
            mission_id, parent, child_inodes, separated, route_count, proc_visible,
            completed.returncode, proven,
        ).sealed()
        receipt.validate()
        if self.sensorium is not None:
            self.sensorium.observe_physical(
                event_type="isolation.namespace_verified" if proven else "isolation.namespace_reduced",
                source="namespace_isolation_runner",
                payload_schema="beast.sensor.isolation.namespace.v1",
                operation="isolation.namespace_verify",
                phase="verification",
                subject=f"mission:{mission_id}",
                result="success" if proven else "failure",
                payload={
                    "receipt_digest": receipt.receipt_digest,
                    "separated_namespaces": list(separated),
                    "non_loopback_route_count": route_count,
                    "worker_exit_code": completed.returncode,
                    "stderr_retained": False,
                    "reads": ["kernel_namespace_inodes", "network_route_table"],
                    "produces": [f"namespace_receipt:{receipt.receipt_digest}"],
                },
                mission_id=mission_id,
                confidence_method="kernel_namespace_inode_comparison",
            )
        return receipt

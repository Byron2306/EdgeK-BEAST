"""Read-only Linux Sensorium collectors.

They use procfs only, expose no remote addresses or packet payloads, and make
their limited attribution explicit.  eBPF/fanotify can be attached later via
the same normalized observation format without changing Sensorium contracts.
"""
from __future__ import annotations

import hashlib
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.kernel.sensorium.contracts import ProcessLease


_SOCKET_TABLES = (("tcp", "AF_INET", "TCP"), ("tcp6", "AF_INET6", "TCP"),
                  ("udp", "AF_INET", "UDP"), ("udp6", "AF_INET6", "UDP"))


def _boot_id(proc_root: Path) -> str:
    try:
        return (proc_root / "sys/kernel/random/boot_id").read_text(encoding="utf-8").strip()
    except OSError:
        return "procfs-unavailable"


def _process_lease(pid: int, *, proc_root: Path, boot_id: str) -> ProcessLease | None:
    try:
        stat = (proc_root / str(pid) / "stat").read_text(encoding="utf-8").split()
        executable = os.readlink(proc_root / str(pid) / "exe")
        cgroup = (proc_root / str(pid) / "cgroup").read_text(encoding="utf-8").strip()
        parent = int(stat[3]); start_ticks = int(stat[21])
        parent_digest = "sha256:" + hashlib.sha256(f"{boot_id}:{parent}".encode()).hexdigest()
        executable_digest = "sha256:" + hashlib.sha256(executable.encode()).hexdigest()
        return ProcessLease(boot_id, pid, start_ticks, executable_digest, "cgroup:" + hashlib.sha256(cgroup.encode()).hexdigest()[:24],
                            os.stat(proc_root / str(pid) / "ns/pid").st_ino, os.stat(proc_root / str(pid) / "ns/mnt").st_ino,
                            parent_digest, "host_observed", datetime.now(timezone.utc).isoformat()).with_identity()
    except (OSError, ValueError, IndexError):
        return None


def collect_socket_observations(*, workspace_id: str, proc_root: Path | str = "/proc", service_prefix: str = "pid") -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Return normalized TCP/UDP IPv4/IPv6 observations plus limitation receipt."""
    root = Path(proc_root)
    if not workspace_id:
        raise ValueError("workspace_id is required for socket attribution")
    boot_id = _boot_id(root)
    inode_owners: dict[str, int] = {}
    for entry in root.iterdir() if root.is_dir() else ():
        if not entry.name.isdigit():
            continue
        try:
            for fd in (entry / "fd").iterdir():
                target = os.readlink(fd)
                if target.startswith("socket:[") and target.endswith("]"):
                    inode_owners.setdefault(target[8:-1], int(entry.name))
        except OSError:
            continue
    leases: dict[int, ProcessLease] = {}
    rows: list[dict[str, Any]] = []
    for table, family, protocol in _SOCKET_TABLES:
        try:
            lines = (root / "net" / table).read_text(encoding="utf-8").splitlines()[1:]
        except OSError:
            continue
        for line in lines:
            fields = line.split()
            if len(fields) < 10 or ":" not in fields[1]:
                continue
            address, port_text = fields[1].rsplit(":", 1)
            try:
                port = int(port_text, 16)
            except ValueError:
                continue
            pid = inode_owners.get(fields[9])
            if pid is None:
                continue  # fail closed: no process identity, no attribution
            lease = leases.setdefault(pid, _process_lease(pid, proc_root=root, boot_id=boot_id))
            if lease is None:
                continue
            address_class = "loopback" if address.endswith("00000000") and address != "00000000" else "any"
            rows.append({"family": family, "protocol": protocol, "local_address_class": address_class,
                         "local_port": port, "remote_scope": "procfs_unattributed", "owning_process": lease.lease_id,
                         "service_id": f"{service_prefix}-{pid}", "workspace_id": workspace_id,
                         "cgroup_id": lease.cgroup_id, "listener_generation": lease.start_time_ticks,
                         "opened_at_monotonic_ns": time.monotonic_ns(), "policy_class": "observed_procfs",
                         "network_namespace": "host", "vrf": "unknown"})
    receipt = {"beast_object_type": "sensorium_linux_socket_snapshot", "version": "1.0",
               "collector": "procfs", "read_only": True, "packet_payloads_retained": False,
               "socket_count": len(rows), "families": ["AF_INET", "AF_INET6"], "protocols": ["TCP", "UDP"],
               "limitations": ["no_fanotify_file_attribution", "no_bpf_lifecycle_ordering", "no_packet_payload_or_vrf_resolution"]}
    return rows, receipt

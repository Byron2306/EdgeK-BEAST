"""Read-only, content-bound inspection of descendants of a ProcessLease."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.kernel.execution.process_identity import LinuxProcessIdentityCollector, ProcessIdentityError
from app.kernel.sensorium.contracts import ProcessLease
from app.kernel.sensorium.contracts_hash import content_hash


@dataclass(frozen=True)
class GovernedDescendantSnapshot:
    root_lease_id: str
    descendant_leases: tuple[ProcessLease, ...]
    scan_complete: bool
    snapshot_digest: str


class LinuxProcessDescendantInspector:
    def __init__(
        self,
        collector: LinuxProcessIdentityCollector | None = None,
        *,
        proc_root: Path = Path("/proc"),
    ):
        self.collector = collector or LinuxProcessIdentityCollector(proc_root=proc_root)
        self.proc_root = Path(proc_root)

    def capture(self, root: ProcessLease) -> GovernedDescendantSnapshot:
        root.validate()
        parent_by_pid: dict[int, int] = {}
        scan_complete = True
        try:
            entries = tuple(self.proc_root.iterdir())
        except OSError:
            entries = ()
            scan_complete = False
        for entry in entries:
            if not entry.name.isdigit():
                continue
            try:
                ppid, _start = self.collector._parse_stat(
                    (entry / "stat").read_text(encoding="utf-8", errors="strict")
                )
                parent_by_pid[int(entry.name)] = ppid
            except (OSError, ValueError, ProcessIdentityError):
                # Unrelated tasks may naturally exit between directory and
                # stat reads; that does not make the rooted closure partial.
                continue

        descendants: set[int] = set()
        frontier = {root.pid_at_observation}
        while frontier:
            children = {pid for pid, ppid in parent_by_pid.items() if ppid in frontier}
            children -= descendants
            if not children:
                break
            descendants.update(children)
            frontier = children

        leases = []
        for pid in sorted(descendants):
            try:
                lease = self.collector.collect(pid, owner_scope=root.owner_scope)
            except (OSError, ProcessIdentityError):
                scan_complete = False
                continue
            # Only descendants inside the governed physical boundary count as
            # managed orphans. Cross-cgroup descendants force an incomplete
            # result and therefore cannot produce an absence proof.
            if (
                lease.cgroup_id != root.cgroup_id
                or lease.pid_namespace_inode != root.pid_namespace_inode
                or lease.mount_namespace_inode != root.mount_namespace_inode
            ):
                scan_complete = False
                continue
            leases.append(lease)
        payload = {
            "root_lease_id": root.lease_id,
            "descendant_lease_ids": [item.lease_id for item in leases],
            "scan_complete": scan_complete,
        }
        return GovernedDescendantSnapshot(
            root.lease_id, tuple(leases), scan_complete, content_hash(payload)
        )

    def absence(self, snapshot: GovernedDescendantSnapshot) -> bool:
        return bool(
            snapshot.scan_complete
            and all(not self.collector.still_matches(lease) for lease in snapshot.descendant_leases)
        )

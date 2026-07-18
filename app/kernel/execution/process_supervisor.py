"""pidfd-backed lifecycle supervision for BEAST-owned processes."""

from __future__ import annotations

import os
import signal
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from threading import RLock
from typing import Any, Dict, List, Optional

from app.kernel.execution.epoll_constellation import EpollConstellation
from app.kernel.execution.process_identity import LinuxProcessIdentityCollector
from app.kernel.sensorium.contracts import ProcessLease
from app.kernel.sensorium.runtime import SensoriumRuntime


@dataclass(frozen=True)
class ProcessSignalAuthorization:
    lease_id: str
    signal_number: int
    approved_by: str
    approval_receipt_id: str
    reason: str

    def validate(self, lease: ProcessLease, signal_number: int) -> None:
        if self.lease_id != lease.lease_id:
            raise PermissionError("signal authorization lease mismatch")
        if self.signal_number != signal_number:
            raise PermissionError("signal authorization signal mismatch")
        if not self.approved_by or not self.approval_receipt_id or not self.reason:
            raise PermissionError("signal authorization is incomplete")


@dataclass
class ManagedProcessLease:
    lease: ProcessLease
    pidfd: int
    exited: bool = False


class ProcessLeaseSupervisor:
    def __init__(
        self,
        *,
        collector: Optional[LinuxProcessIdentityCollector] = None,
        constellation: Optional[EpollConstellation] = None,
        sensorium: Optional[SensoriumRuntime] = None,
    ):
        if not hasattr(os, "pidfd_open"):
            raise RuntimeError("pidfd_open is unavailable")
        if not hasattr(signal, "pidfd_send_signal"):
            raise RuntimeError("pidfd_send_signal is unavailable")
        self.collector = collector or LinuxProcessIdentityCollector()
        self.constellation = constellation or EpollConstellation()
        self._owns_constellation = constellation is None
        self.sensorium = sensorium
        self._managed: Dict[str, ManagedProcessLease] = {}
        self._fd_to_lease: Dict[int, str] = {}
        self._lock = RLock()

    def acquire(self, pid: int, *, owner_scope: str = "beast_mission", mission_id: str = "") -> ProcessLease:
        pidfd = os.pidfd_open(pid, 0)
        try:
            lease = self.collector.collect(pid, owner_scope=owner_scope)
            self.constellation.register(
                pidfd,
                kind="process_exit",
                identity=lease.lease_id,
                metadata={"mission_id": mission_id, "owner_scope": owner_scope},
            )
        except Exception:
            os.close(pidfd)
            raise
        with self._lock:
            if lease.lease_id in self._managed:
                self.constellation.unregister(pidfd)
                os.close(pidfd)
                raise ValueError("process lease is already managed")
            self._managed[lease.lease_id] = ManagedProcessLease(lease=lease, pidfd=pidfd)
            self._fd_to_lease[pidfd] = lease.lease_id
        self._observe("process.lease_acquired", lease, mission_id, {
            "lease_id": lease.lease_id,
            "pid_at_observation": lease.pid_at_observation,
            "owner_scope": owner_scope,
            "pidfd_serialized": False,
        })
        return lease

    def verify(self, lease_id: str) -> bool:
        with self._lock:
            managed = self._managed.get(lease_id)
            if managed is None or managed.exited:
                return False
            lease = managed.lease
        return self.collector.still_matches(lease)

    def poll(self, timeout: float = 0.0) -> List[ProcessLease]:
        exited: List[ProcessLease] = []
        for event in self.constellation.poll(timeout=timeout):
            if event.kind != "process_exit" or not (event.readable or event.hangup or event.error):
                continue
            with self._lock:
                managed = self._managed.get(event.identity)
                if managed is None or managed.exited:
                    continue
                managed.exited = True
                managed.lease = replace(
                    managed.lease,
                    exited_at=datetime.now(timezone.utc).isoformat(),
                )
                exited.append(managed.lease)
            self._observe(
                "process.exit",
                managed.lease,
                str(event.metadata.get("mission_id") or ""),
                {"lease_id": managed.lease.lease_id, "exit_observed_via": "pidfd_epoll"},
            )
        return exited

    def send_signal(
        self,
        lease_id: str,
        signal_number: int,
        authorization: ProcessSignalAuthorization,
        *,
        mission_id: str = "",
    ) -> Dict[str, Any]:
        if signal_number not in {signal.SIGTERM, signal.SIGINT, signal.SIGHUP, signal.SIGKILL}:
            raise ValueError("unsupported process signal")
        with self._lock:
            managed = self._managed.get(lease_id)
            if managed is None or managed.exited:
                raise ProcessLookupError("managed process is unavailable")
            authorization.validate(managed.lease, signal_number)
            # The pidfd prevents signalling a reused numeric PID, while this
            # second content check proves that the authority still names the
            # same physical process immediately before the destructive edge.
            if not self.collector.still_matches(managed.lease):
                raise ProcessLookupError("process identity drifted before pidfd signal")
            signal.pidfd_send_signal(managed.pidfd, signal_number, None, 0)
            lease = managed.lease
        receipt = {
            "beast_object_type": "pidfd_signal_receipt",
            "version": "1.0",
            "lease_id": lease.lease_id,
            "signal_number": signal_number,
            "approved_by": authorization.approved_by,
            "approval_receipt_id": authorization.approval_receipt_id,
            "reason": authorization.reason,
            "targeted_via": "pidfd",
            "integer_pid_signal_used": False,
            "identity_revalidated_immediately_before_signal": True,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self._observe("process.signal_sent", lease, mission_id, receipt)
        return receipt

    def release(self, lease_id: str) -> None:
        with self._lock:
            managed = self._managed.pop(lease_id, None)
            if managed is None:
                return
            self._fd_to_lease.pop(managed.pidfd, None)
            self.constellation.unregister(managed.pidfd)
            os.close(managed.pidfd)

    def state(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "beast_object_type": "process_lease_supervisor_state",
                "version": "1.0",
                "managed_count": len(self._managed),
                "live_count": sum(not item.exited for item in self._managed.values()),
                "exited_count": sum(item.exited for item in self._managed.values()),
                "pidfd_supported": True,
                "pidfd_signal_supported": True,
                "integer_pid_signal_used": False,
                "leases": [
                    {
                        "lease_id": item.lease.lease_id,
                        "pid_at_observation": item.lease.pid_at_observation,
                        "owner_scope": item.lease.owner_scope,
                        "exited": item.exited,
                    }
                    for item in self._managed.values()
                ],
            }

    def close(self) -> None:
        with self._lock:
            lease_ids = list(self._managed)
        for lease_id in lease_ids:
            self.release(lease_id)
        if self._owns_constellation:
            self.constellation.close()

    def _observe(self, event_type: str, lease: ProcessLease, mission_id: str, payload: Dict[str, Any]) -> None:
        if self.sensorium is None:
            return
        try:
            self.sensorium.observe_owned(
                event_type=event_type,
                source="process_lease_supervisor",
                payload_schema=f"beast.sensor.{event_type}.v1",
                payload=payload,
                mission_id=mission_id,
                process_lease_id=lease.lease_id,
            )
        except Exception:
            return

    def __enter__(self) -> "ProcessLeaseSupervisor":
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.close()

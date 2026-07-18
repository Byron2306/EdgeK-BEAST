"""Explicitly authorized cgroup v2 mission capsule boundary."""

from __future__ import annotations

import os
import re
import signal
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

from app.kernel.sensorium.contracts import ProcessLease
from app.kernel.sensorium.runtime import SensoriumRuntime


CGROUP_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,127}$")


@dataclass(frozen=True)
class CgroupAuthorization:
    action: str
    mission_id: str
    approved_by: str
    approval_receipt_id: str
    reason: str
    destructive: bool = False

    def require(self, action: str, mission_id: str, *, destructive: bool = False) -> None:
        if self.action != action or self.mission_id != mission_id:
            raise PermissionError("cgroup authorization scope mismatch")
        if not self.approved_by or not self.approval_receipt_id or not self.reason:
            raise PermissionError("cgroup authorization is incomplete")
        if destructive and not self.destructive:
            raise PermissionError("destructive cgroup authorization is required")


class CgroupV2Discovery:
    def __init__(self, root: Path = Path("/sys/fs/cgroup")):
        self.root = Path(root)

    def state(self) -> Dict[str, Any]:
        controllers = self._words(self.root / "cgroup.controllers")
        delegated_controllers = [item.lstrip("+") for item in self._words(self.root / "cgroup.subtree_control")]
        controls = {
            "events": (self.root / "cgroup.events").exists(),
            "freeze": (self.root / "cgroup.freeze").exists(),
            "kill": (self.root / "cgroup.kill").exists(),
            "pressure": (self.root / "cgroup.pressure").exists(),
        }
        return {
            "beast_object_type": "cgroup_v2_capability_state",
            "version": "1.0",
            "root": str(self.root),
            "available": (self.root / "cgroup.controllers").exists(),
            "controllers": controllers,
            "delegated_controllers": delegated_controllers,
            "controls": controls,
            "delegated_writable": os.access(self.root, os.W_OK),
            "subtree_control_writable": os.access(self.root / "cgroup.subtree_control", os.W_OK),
            "delegation_proven": bool(
                controllers
                and (self.root / "cgroup.procs").exists()
                and (self.root / "cgroup.subtree_control").exists()
                and os.access(self.root, os.W_OK)
                and os.access(self.root / "cgroup.subtree_control", os.W_OK)
            ),
            "inspection_mutates_state": False,
        }

    @staticmethod
    def _words(path: Path) -> list[str]:
        try:
            return sorted(set(path.read_text(encoding="utf-8").split()))
        except OSError:
            return []


class CgroupMissionCapsule:
    def __init__(
        self,
        root: Path,
        mission_id: str,
        *,
        sensorium: Optional[SensoriumRuntime] = None,
        synthetic: bool = False,
    ):
        if not CGROUP_NAME_RE.fullmatch(mission_id):
            raise ValueError("invalid cgroup mission id")
        self.root = Path(root)
        self.mission_id = mission_id
        self.path = self.root / "beast.slice" / mission_id
        self.sensorium = sensorium
        self.synthetic = bool(synthetic)

    def create(self, authorization: CgroupAuthorization) -> Dict[str, Any]:
        authorization.require("create", self.mission_id)
        self.path.mkdir(parents=True, exist_ok=False)
        return self._receipt("create", authorization, confirmed=self.path.is_dir())

    def attach_process(
        self,
        lease: ProcessLease,
        supervisor: Any,
        authorization: CgroupAuthorization,
    ) -> Dict[str, Any]:
        authorization.require("attach", self.mission_id)
        lease.validate()
        if not supervisor.verify(lease.lease_id):
            raise ProcessLookupError("process lease is not current before cgroup attachment")
        self._control("cgroup.procs").write_text(f"{lease.pid_at_observation}\n", encoding="utf-8")
        stable_after_write = bool(supervisor.verify(lease.lease_id))
        if not stable_after_write:
            raise ProcessLookupError(
                "process identity changed during cgroup attachment; admission is not confirmed"
            )
        return self._receipt(
            "attach",
            authorization,
            confirmed=True,
            details={
                "lease_id": lease.lease_id,
                "pid_at_observation": lease.pid_at_observation,
                "identity_verified_before_write": True,
                "identity_verified_after_write": stable_after_write,
                "kernel_interface": "cgroup.procs",
            },
        )

    def freeze(self, frozen: bool, authorization: CgroupAuthorization) -> Dict[str, Any]:
        action = "freeze" if frozen else "thaw"
        authorization.require(action, self.mission_id)
        self._control("cgroup.freeze").write_text("1\n" if frozen else "0\n", encoding="utf-8")
        events = self.events()
        return self._receipt(
            action,
            authorization,
            confirmed=events.get("frozen") == (1 if frozen else 0),
            details={"requested_frozen": frozen, "observed_events": events},
        )

    def configure_resources(
        self,
        limits: Dict[str, str],
        authorization: CgroupAuthorization,
    ) -> Dict[str, Any]:
        authorization.require("configure", self.mission_id)
        allowed = {"cpu.max", "memory.max", "memory.swap.max", "memory.oom.group", "pids.max", "io.max"}
        if not limits or set(limits) - allowed:
            raise ValueError("unsupported or empty cgroup resource limit set")
        observed: Dict[str, str] = {}
        for name, raw in sorted(limits.items()):
            value = str(raw).strip()
            if not value or "\n" in value or "\r" in value:
                raise ValueError(f"invalid cgroup resource limit: {name}")
            control = self._control(name)
            control.write_text(value + "\n", encoding="utf-8")
            observed[name] = control.read_text(encoding="utf-8").strip()
        confirmed = observed == {name: str(value).strip() for name, value in sorted(limits.items())}
        return self._receipt(
            "configure",
            authorization,
            confirmed=confirmed,
            details={"requested_limits": dict(limits), "observed_limits": observed},
        )

    def kill(self, authorization: CgroupAuthorization) -> Dict[str, Any]:
        authorization.require("kill", self.mission_id, destructive=True)
        self._control("cgroup.kill").write_text("1\n", encoding="utf-8")
        return self._receipt(
            "kill",
            authorization,
            confirmed=False,
            details={"requested": True, "confirmation_requires_populated_zero": True},
        )

    def cleanup(self, authorization: CgroupAuthorization) -> Dict[str, Any]:
        authorization.require("cleanup", self.mission_id)
        if not self.empty():
            raise RuntimeError("cannot remove a populated cgroup capsule")
        if self.synthetic:
            for child in self.path.iterdir():
                if child.is_file():
                    child.unlink()
        self.path.rmdir()
        parent = self.path.parent
        try:
            parent.rmdir()
        except OSError:
            pass
        return self._receipt("cleanup", authorization, confirmed=not self.path.exists())

    def events(self) -> Dict[str, int]:
        try:
            rows = self._control("cgroup.events").read_text(encoding="utf-8").splitlines()
        except OSError:
            return {}
        result: Dict[str, int] = {}
        for row in rows:
            key, _, raw = row.partition(" ")
            try:
                result[key] = int(raw.strip())
            except ValueError:
                continue
        return result

    def pressure(self) -> Dict[str, str]:
        result = {}
        for resource in ("cpu", "memory", "io"):
            path = self.path / f"{resource}.pressure"
            try:
                result[resource] = path.read_text(encoding="utf-8").strip()
            except OSError:
                continue
        return result

    def empty(self) -> bool:
        return self.events().get("populated") == 0

    def member_pids(self) -> list[int]:
        try:
            rows = self._control("cgroup.procs").read_text(encoding="utf-8").splitlines()
        except OSError:
            return []
        members = []
        for row in rows:
            try:
                pid = int(row.strip())
            except ValueError:
                continue
            if pid > 0:
                members.append(pid)
        return sorted(set(members))

    def orphan_state(self, expected_pids: Iterable[int]) -> Dict[str, Any]:
        expected = sorted({int(pid) for pid in expected_pids if int(pid) > 0})
        members = self.member_pids()
        unexpected = sorted(set(members) - set(expected))
        missing = sorted(set(expected) - set(members))
        return {
            "beast_object_type": "cgroup_capsule_orphan_state",
            "version": "1.0",
            "mission_id": self.mission_id,
            "members": members,
            "expected": expected,
            "unexpected_members": unexpected,
            "missing_expected_members": missing,
            "orphaned": bool(unexpected),
            "populated": self.events().get("populated"),
            "read_only": True,
        }

    def graceful_cleanup(
        self,
        supervisor: Any,
        lease_ids: Iterable[str],
        signal_authorizations: Dict[str, Any],
        *,
        timeout_seconds: float = 2.0,
        kill_authorization: Optional[CgroupAuthorization] = None,
    ) -> Dict[str, Any]:
        """Request graceful pidfd termination before optional cgroup kill."""
        signal_receipts = []
        for lease_id in lease_ids:
            authorization = signal_authorizations.get(lease_id)
            if authorization is None:
                raise PermissionError(f"missing signal authorization for lease: {lease_id}")
            signal_receipts.append(supervisor.send_signal(
                lease_id,
                signal.SIGTERM,
                authorization,
                mission_id=self.mission_id,
            ))
        deadline = time.monotonic() + max(0.0, float(timeout_seconds))
        while not self.empty() and time.monotonic() < deadline:
            supervisor.poll(timeout=min(0.05, max(0.0, deadline - time.monotonic())))
        escalated = False
        kill_receipt = None
        if not self.empty() and kill_authorization is not None:
            kill_receipt = self.kill(kill_authorization)
            escalated = True
        return {
            "beast_object_type": "cgroup_graceful_cleanup_receipt",
            "version": "1.0",
            "mission_id": self.mission_id,
            "signal_receipts": signal_receipts,
            "empty_after_graceful_wait": self.empty(),
            "escalated_to_cgroup_kill": escalated,
            "kill_receipt": kill_receipt,
            "escalation_required": not self.empty() and kill_authorization is None,
            "timeout_seconds": max(0.0, float(timeout_seconds)),
        }

    def state(self) -> Dict[str, Any]:
        return {
            "beast_object_type": "cgroup_mission_capsule_state",
            "version": "1.0",
            "mission_id": self.mission_id,
            "path": str(self.path),
            "exists": self.path.is_dir(),
            "events": self.events(),
            "pressure": self.pressure(),
            "controls": {
                name: (self.path / name).exists()
                for name in ("cgroup.procs", "cgroup.events", "cgroup.freeze", "cgroup.kill")
            },
            "read_only_projection": True,
        }

    def _control(self, name: str) -> Path:
        path = self.path / name
        if not path.exists():
            raise RuntimeError(f"cgroup control is unavailable: {name}")
        return path

    def _receipt(
        self,
        action: str,
        authorization: CgroupAuthorization,
        *,
        confirmed: bool,
        details: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        receipt = {
            "beast_object_type": "cgroup_capsule_action_receipt",
            "version": "1.0",
            "mission_id": self.mission_id,
            "action": action,
            "confirmed": confirmed,
            "authorization": asdict(authorization),
            "details": dict(details or {}),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        if self.sensorium is not None:
            try:
                self.sensorium.observe_owned(
                    event_type=f"cgroup.{action}",
                    source="cgroup_mission_capsule",
                    payload_schema=f"beast.sensor.cgroup.{action}.v1",
                    payload=receipt,
                    mission_id=self.mission_id,
                )
            except Exception:
                pass
        return receipt

"""Capability-detected Linux pressure, memory, and execution primitives.

All mutating kernel controls are deny-by-default.  Callers must opt in with
``allow_mutation=True`` and still satisfy kernel permission checks.
"""
from __future__ import annotations

import ctypes
import dataclasses
import errno
import json
import os
import platform
import re
import select
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional

libc = ctypes.CDLL(None, use_errno=True)


class KernelPrimitiveError(OSError):
    """A Linux primitive failed with a preserved errno."""


class MutationDenied(PermissionError):
    """A privileged kernel mutation was attempted without explicit authority."""


def _raise_errno(name: str) -> None:
    err = ctypes.get_errno()
    raise KernelPrimitiveError(err, f"{name} failed: {os.strerror(err)}")


@dataclasses.dataclass(frozen=True)
class KernelCapability:
    name: str
    available: bool
    writable: bool = False
    detail: str = ""


@dataclasses.dataclass(frozen=True)
class PsiMetric:
    avg10: float = 0.0
    avg60: float = 0.0
    avg300: float = 0.0
    total_us: int = 0


@dataclasses.dataclass(frozen=True)
class PressureResource:
    some: PsiMetric = PsiMetric()
    full: PsiMetric = PsiMetric()


@dataclasses.dataclass(frozen=True)
class SystemPressure:
    cpu: PressureResource
    io: PressureResource
    memory: PressureResource

    @property
    def normalized_score(self) -> float:
        # PSI averages are percentages. Weight full stalls more heavily.
        values = []
        for item in (self.cpu, self.io, self.memory):
            values.append(min(1.0, item.some.avg10 / 100.0))
            values.append(min(1.0, item.full.avg10 / 50.0))
        return max(values, default=0.0)


@dataclasses.dataclass(frozen=True)
class ResctrlGroupReceipt:
    group: str
    schemata: str
    task_ids: tuple[int, ...]
    applied: bool


@dataclasses.dataclass(frozen=True)
class DamonContextReceipt:
    context_index: int
    pid: int
    operations: str
    state: str
    configured: bool


class _IOVec(ctypes.Structure):
    _fields_ = [("iov_base", ctypes.c_void_p), ("iov_len", ctypes.c_size_t)]


class ExecutionPrimitives:
    """Safe wrappers for pidfd, process_madvise, and memfd primitives."""

    # Syscall numbers are architecture-specific. Prefer Python wrappers.
    _SYSCALLS = {
        "x86_64": {"pidfd_getfd": 438, "process_madvise": 440},
        "aarch64": {"pidfd_getfd": 438, "process_madvise": 440},
    }

    @classmethod
    def _syscall_number(cls, name: str) -> int:
        machine = platform.machine().lower()
        try:
            return cls._SYSCALLS[machine][name]
        except KeyError as exc:
            raise NotImplementedError(f"{name} syscall number unknown for {machine}") from exc

    @staticmethod
    def pidfd_open(pid: int, flags: int = 0) -> int:
        if pid <= 0:
            raise ValueError("pid must be positive")
        if hasattr(os, "pidfd_open"):
            return os.pidfd_open(pid, flags)
        nr = 434 if platform.machine().lower() in {"x86_64", "aarch64"} else None
        if nr is None:
            raise NotImplementedError("pidfd_open unavailable on this architecture")
        result = libc.syscall(nr, ctypes.c_int(pid), ctypes.c_uint(flags))
        if result < 0:
            _raise_errno("pidfd_open")
        return int(result)

    @classmethod
    def pidfd_getfd(cls, pidfd: int, targetfd: int, flags: int = 0) -> int:
        if min(pidfd, targetfd) < 0:
            raise ValueError("file descriptors must be non-negative")
        result = libc.syscall(
            cls._syscall_number("pidfd_getfd"),
            ctypes.c_int(pidfd), ctypes.c_int(targetfd), ctypes.c_uint(flags),
        )
        if result < 0:
            _raise_errno("pidfd_getfd")
        return int(result)

    @classmethod
    def process_madvise(
        cls,
        pidfd: int,
        ranges: Iterable[tuple[int, int]],
        advice: int,
        flags: int = 0,
    ) -> int:
        normalized = tuple((int(addr), int(length)) for addr, length in ranges)
        if not normalized or any(addr < 0 or length <= 0 for addr, length in normalized):
            raise ValueError("ranges must contain positive lengths and non-negative addresses")
        array_type = _IOVec * len(normalized)
        iovecs = array_type(*(_IOVec(ctypes.c_void_p(a), n) for a, n in normalized))
        result = libc.syscall(
            cls._syscall_number("process_madvise"),
            ctypes.c_int(pidfd), ctypes.byref(iovecs), ctypes.c_size_t(len(iovecs)),
            ctypes.c_int(advice), ctypes.c_uint(flags),
        )
        if result < 0:
            _raise_errno("process_madvise")
        return int(result)

    @staticmethod
    def memfd_create(name: str, flags: int | None = None, *, seal: bool = False) -> int:
        if not name or "/" in name:
            raise ValueError("memfd name must be non-empty and contain no slash")
        if not hasattr(os, "memfd_create"):
            raise NotImplementedError("os.memfd_create is unavailable")
        actual_flags = flags if flags is not None else getattr(os, "MFD_CLOEXEC", 0x0001)
        if seal:
            actual_flags |= getattr(os, "MFD_ALLOW_SEALING", 0x0002)
        return os.memfd_create(name, actual_flags)

    @staticmethod
    def process_alive(pidfd: int) -> bool:
        poller = select.poll()
        poller.register(pidfd, select.POLLIN)
        return not bool(poller.poll(0))


class SystemMonitor:
    """Linux pressure and memory policy interface with explicit mutation gates."""

    _GROUP_RE = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")

    def __init__(
        self,
        *,
        psi_root: Path = Path("/proc/pressure"),
        damon_root: Path = Path("/sys/kernel/mm/damon/admin"),
        resctrl_root: Path = Path("/sys/fs/resctrl"),
        zswap_root: Path = Path("/sys/module/zswap/parameters"),
        ksm_root: Path = Path("/sys/kernel/mm/ksm"),
        allow_mutation: bool = False,
    ) -> None:
        self.psi_root = Path(psi_root)
        self.damon_root = Path(damon_root)
        self.resctrl_root = Path(resctrl_root)
        self.zswap_root = Path(zswap_root)
        self.ksm_root = Path(ksm_root)
        self.allow_mutation = allow_mutation
        self.exec_prims = ExecutionPrimitives()

    def capabilities(self) -> dict[str, KernelCapability]:
        paths = {
            "psi": self.psi_root,
            "damon_sysfs": self.damon_root,
            "resctrl": self.resctrl_root,
            "zswap": self.zswap_root / "enabled",
            "ksm": self.ksm_root / "run",
        }
        result = {}
        for name, path in paths.items():
            result[name] = KernelCapability(
                name=name,
                available=path.exists(),
                writable=os.access(path, os.W_OK) if path.exists() else False,
                detail=str(path),
            )
        result["pidfd_open"] = KernelCapability("pidfd_open", hasattr(os, "pidfd_open"))
        result["memfd_create"] = KernelCapability("memfd_create", hasattr(os, "memfd_create"))
        return result

    @staticmethod
    def _parse_psi(text: str) -> PressureResource:
        rows: dict[str, PsiMetric] = {}
        for line in text.splitlines():
            fields = line.split()
            if not fields or fields[0] not in {"some", "full"}:
                continue
            values = dict(field.split("=", 1) for field in fields[1:] if "=" in field)
            try:
                rows[fields[0]] = PsiMetric(
                    avg10=float(values.get("avg10", 0.0)),
                    avg60=float(values.get("avg60", 0.0)),
                    avg300=float(values.get("avg300", 0.0)),
                    total_us=int(values.get("total", 0)),
                )
            except ValueError:
                rows[fields[0]] = PsiMetric()
        return PressureResource(rows.get("some", PsiMetric()), rows.get("full", PsiMetric()))

    def get_pressure(self) -> SystemPressure:
        values = {}
        for resource in ("cpu", "io", "memory"):
            try:
                values[resource] = self._parse_psi((self.psi_root / resource).read_text())
            except OSError:
                values[resource] = PressureResource()
        return SystemPressure(values["cpu"], values["io"], values["memory"])

    def _require_mutation(self) -> None:
        if not self.allow_mutation:
            raise MutationDenied("kernel mutation requires allow_mutation=True")

    @staticmethod
    def _write(path: Path, value: str) -> None:
        path.write_text(value, encoding="utf-8")

    def set_zswap(self, enabled: bool) -> None:
        self._require_mutation()
        self._write(self.zswap_root / "enabled", "1" if enabled else "0")

    def set_ksm(self, enabled: bool, *, pages_to_scan: int | None = None, sleep_ms: int | None = None) -> None:
        self._require_mutation()
        if pages_to_scan is not None:
            if pages_to_scan <= 0:
                raise ValueError("pages_to_scan must be positive")
            self._write(self.ksm_root / "pages_to_scan", str(pages_to_scan))
        if sleep_ms is not None:
            if sleep_ms < 0:
                raise ValueError("sleep_ms must be non-negative")
            self._write(self.ksm_root / "sleep_millisecs", str(sleep_ms))
        self._write(self.ksm_root / "run", "1" if enabled else "0")

    def configure_damon_vaddr(self, pid: int, *, context_index: int = 0, start: bool = False) -> DamonContextReceipt:
        self._require_mutation()
        if pid <= 0 or context_index < 0:
            raise ValueError("invalid pid or context index")
        kdamonds = self.damon_root / "kdamonds"
        self._write(kdamonds / "nr_kdamonds", "1")
        kd = kdamonds / "0"
        self._write(kd / "contexts" / "nr_contexts", str(context_index + 1))
        context = kd / "contexts" / str(context_index)
        self._write(context / "operations", "vaddr")
        self._write(context / "targets" / "nr_targets", "1")
        self._write(context / "targets" / "0" / "pid_target", str(pid))
        state = "on" if start else "off"
        if start:
            self._write(kd / "state", state)
        return DamonContextReceipt(context_index, pid, "vaddr", state, True)

    def create_resctrl_group(
        self,
        group: str,
        *,
        schemata: str,
        task_ids: Iterable[int] = (),
    ) -> ResctrlGroupReceipt:
        self._require_mutation()
        if not self._GROUP_RE.fullmatch(group) or group in {".", ".."}:
            raise ValueError("invalid resctrl group")
        if not schemata.strip() or "\x00" in schemata:
            raise ValueError("schemata must be non-empty")
        tasks = tuple(int(pid) for pid in task_ids)
        if any(pid <= 0 for pid in tasks):
            raise ValueError("task IDs must be positive")
        path = self.resctrl_root / group
        path.mkdir(exist_ok=True)
        self._write(path / "schemata", schemata.rstrip() + "\n")
        for pid in tasks:
            self._write(path / "tasks", str(pid))
        return ResctrlGroupReceipt(group, schemata.rstrip(), tasks, True)

    def snapshot(self) -> dict[str, Any]:
        pressure = self.get_pressure()
        return {
            "beast_object_type": "beast_linux_system_snapshot",
            "pressure": dataclasses.asdict(pressure),
            "pressure_score": pressure.normalized_score,
            "capabilities": {k: dataclasses.asdict(v) for k, v in self.capabilities().items()},
            "mutation_enabled": self.allow_mutation,
        }

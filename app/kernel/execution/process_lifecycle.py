"""Owned-process lifecycle: clean, race-free teardown for BEAST workers.

The memory hull (residue store) and socket guardian (port leases) had no way
to end a process.  This is the lifecycle layer for the governed model-call
path: model-serving and agent-worker processes that BEAST *spawned or
explicitly adopted* can be torn down when the interceptor sees a stalled
stream, a circuit opens, placement changes (VRAM pressure / Ollama-TGI
time-share), the governor budget is exhausted, or the verifier flags runaway
output.

Safety properties:
* **Ownership proof**: a handle holds a pidfd opened at spawn/adopt time plus
  the kernel start time (``/proc/<pid>/stat`` field 22) and cgroup path. Every
  signal goes through ``pidfd_send_signal`` on that pidfd, so a recycled PID
  can never be hit; start time and cgroup are re-checked before signalling.
* **Never-kill list**: PID 1, ourselves, processes of other users (system
  Ollama runs as ``ollama``), anything listening on protected ports (8101,
  8131 by default), and docker/containerd/system.slice cgroups (seraph, ARDA).
* **Escalation**: SIGTERM, grace period (pidfd poll), SIGKILL; then
  ``cgroup.kill`` when the process lives in a BEAST-owned user scope
  (``systemd-run --user --scope``), which also reaps descendants.
* **Reclaim**: registered release callbacks (socket-guardian lease release,
  memfd close, memory-hull entry retirement) run after exit; owned fds are
  closed; VRAM held by the pid (nvidia-smi compute-apps) is measured before
  and after.
* **Receipts**: every teardown appends a hash-chained ``process_teardown``
  receipt to the governor receipt log (pid, start time, cgroup, reason,
  signal path, resources reclaimed).

Gated by ``BEAST_PROCESS_LIFECYCLE`` (default off) for anything but tests.
"""
from __future__ import annotations

import os
import select
import shutil
import signal
import subprocess
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence

PROTECTED_PORTS = (8101, 8131)
FOREIGN_CGROUP_MARKERS = ("docker", "containerd", "system.slice", "libpod", "machine.slice")
TRIGGERS = frozenset({"stream_stall", "circuit_open", "placement_change", "budget_exhausted", "runaway_output",
                      "operator_request", "test"})


def enabled(env: Mapping[str, str] | None = None) -> bool:
    env = os.environ if env is None else env
    return str(env.get("BEAST_PROCESS_LIFECYCLE", "0")).strip().lower() in {"1", "true", "yes", "on"}


def proc_start_time(pid: int) -> Optional[int]:
    try:
        raw = Path(f"/proc/{pid}/stat").read_text()
    except OSError:
        return None
    # comm may contain spaces/parens: split after the last ')'
    fields = raw[raw.rindex(")") + 2:].split()
    return int(fields[19])  # field 22 overall (starttime), index 19 after pid/comm


def proc_cgroup(pid: int) -> str:
    try:
        for line in Path(f"/proc/{pid}/cgroup").read_text().splitlines():
            if line.startswith("0::"):
                return line[3:]
    except OSError:
        pass
    return ""


def proc_uid(pid: int) -> Optional[int]:
    try:
        return os.stat(f"/proc/{pid}").st_uid
    except OSError:
        return None


def listening_ports_of(pid: int) -> List[int]:
    """Ports a pid listens on (TCP, via /proc/net + fd inodes); best effort, no root needed for own pids."""
    inodes = set()
    try:
        for fd in os.listdir(f"/proc/{pid}/fd"):
            try:
                target = os.readlink(f"/proc/{pid}/fd/{fd}")
            except OSError:
                continue
            if target.startswith("socket:["):
                inodes.add(target[8:-1])
    except OSError:
        return []
    ports = []
    for table in ("/proc/net/tcp", "/proc/net/tcp6"):
        try:
            lines = Path(table).read_text().splitlines()[1:]
        except OSError:
            continue
        for line in lines:
            parts = line.split()
            if len(parts) > 9 and parts[3] == "0A" and parts[9] in inodes:
                ports.append(int(parts[1].rsplit(":", 1)[1], 16))
    return sorted(set(ports))


def gpu_memory_by_pid() -> Dict[int, int]:
    if not shutil.which("nvidia-smi"):
        return {}
    try:
        out = subprocess.check_output(["nvidia-smi", "--query-compute-apps=pid,used_memory", "--format=csv,noheader,nounits"],
                                      text=True, timeout=5)
    except Exception:
        return {}
    usage: Dict[int, int] = {}
    for line in out.strip().splitlines():
        try:
            pid, mem = [int(x.strip()) for x in line.split(",")]
            usage[pid] = usage.get(pid, 0) + mem
        except ValueError:
            continue
    return usage


def gpu_used_total_mib() -> Optional[int]:
    if not shutil.which("nvidia-smi"):
        return None
    try:
        return int(subprocess.check_output(["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
                                           text=True, timeout=5).strip().splitlines()[0])
    except Exception:
        return None


@dataclass
class OwnedProcess:
    handle_id: str
    pid: int
    pidfd: int
    start_time: int
    cgroup: str
    origin: str                      # "spawned" | "adopted"
    label: str
    beast_scope: bool = False        # lives in a BEAST-owned systemd --user scope
    popen: Optional[subprocess.Popen] = None
    owned_fds: List[int] = field(default_factory=list)
    releases: List[tuple[str, Callable[[], Any]]] = field(default_factory=list)
    closed: bool = False

    def public(self) -> Dict[str, Any]:
        return {"handle_id": self.handle_id, "pid": self.pid, "start_time": self.start_time, "cgroup": self.cgroup,
                "origin": self.origin, "label": self.label, "beast_scope": self.beast_scope}


class OwnershipError(PermissionError):
    pass


class ProcessLifecycle:
    def __init__(self, *, receipts: Any = None, protected_ports: Sequence[int] = PROTECTED_PORTS,
                 scope_prefix: str = "beast-worker", use_scope: bool | None = None,
                 cgroup_root: str = "/sys/fs/cgroup"):
        self.receipts = receipts
        self.protected_ports = tuple(protected_ports)
        self.scope_prefix = scope_prefix
        self.use_scope = bool(shutil.which("systemd-run")) if use_scope is None else use_scope
        self.cgroup_root = Path(cgroup_root)
        self.handles: Dict[str, OwnedProcess] = {}
        self.uid = os.getuid()

    # -- ownership --------------------------------------------------------------------------------
    def _refuse_reason(self, pid: int, *, cgroup: str) -> Optional[str]:
        if pid <= 1 or pid == os.getpid():
            return "protected_pid"
        if proc_uid(pid) != self.uid:
            return "foreign_uid"
        if any(m in cgroup for m in FOREIGN_CGROUP_MARKERS):
            return "foreign_cgroup"
        hit = set(listening_ports_of(pid)) & set(self.protected_ports)
        if hit:
            return f"protected_port:{sorted(hit)}"
        return None

    def _track(self, pid: int, *, origin: str, label: str, beast_scope: bool, popen=None) -> OwnedProcess:
        pidfd = os.pidfd_open(pid)
        start = proc_start_time(pid)
        if start is None:
            os.close(pidfd)
            raise OwnershipError(f"pid {pid} vanished before it could be tracked")
        cgroup = proc_cgroup(pid)
        handle = OwnedProcess(handle_id="proc_" + uuid.uuid4().hex[:12], pid=pid, pidfd=pidfd, start_time=start,
                              cgroup=cgroup, origin=origin, label=label, beast_scope=beast_scope, popen=popen)
        self.handles[handle.handle_id] = handle
        return handle

    def spawn(self, argv: Sequence[str], *, label: str, scope: bool | None = None, env: Mapping[str, str] | None = None,
              stdout: Any = subprocess.DEVNULL, stderr: Any = subprocess.DEVNULL, cwd: str | None = None) -> OwnedProcess:
        """Spawn a worker; with ``scope`` it runs in its own BEAST user scope (cgroup.kill-able)."""
        use_scope = self.use_scope if scope is None else scope
        unit = f"{self.scope_prefix}-{uuid.uuid4().hex[:10]}"
        command = list(argv)
        if use_scope:
            command = ["systemd-run", "--user", "--scope", "--quiet", f"--unit={unit}", "--collect", "--", *command]
        popen = subprocess.Popen(command, env=dict(env) if env is not None else None, stdout=stdout, stderr=stderr,
                                 cwd=cwd, start_new_session=True)
        handle = self._track(popen.pid, origin="spawned", label=label, beast_scope=False, popen=popen)
        if use_scope:
            # systemd-run --scope execs the command in place once the scope exists.
            deadline = time.monotonic() + 3.0
            while time.monotonic() < deadline and unit not in proc_cgroup(popen.pid):
                time.sleep(0.02)
            handle.cgroup = proc_cgroup(popen.pid)
            handle.beast_scope = unit in handle.cgroup and f"{self.scope_prefix}-" in handle.cgroup
        return handle

    def adopt(self, pid: int, *, label: str, expected_start_time: int | None = None,
              require_beast_scope: bool = False) -> OwnedProcess:
        cgroup = proc_cgroup(pid)
        reason = self._refuse_reason(pid, cgroup=cgroup)
        if reason:
            raise OwnershipError(f"refusing to adopt pid {pid}: {reason}")
        start = proc_start_time(pid)
        if expected_start_time is not None and start != expected_start_time:
            raise OwnershipError(f"refusing to adopt pid {pid}: start_time mismatch")
        in_scope = f"/{self.scope_prefix}-" in cgroup
        if require_beast_scope and not in_scope:
            raise OwnershipError(f"refusing to adopt pid {pid}: not in a BEAST-owned scope")
        return self._track(pid, origin="adopted", label=label, beast_scope=in_scope)

    def attach_fd(self, handle: OwnedProcess, fd: int) -> None:
        handle.owned_fds.append(int(fd))

    def on_release(self, handle: OwnedProcess, name: str, fn: Callable[[], Any]) -> None:
        handle.releases.append((name, fn))

    # -- teardown ---------------------------------------------------------------------------------
    def _alive(self, handle: OwnedProcess) -> bool:
        try:
            signal.pidfd_send_signal(handle.pidfd, 0)
        except ProcessLookupError:
            return False
        except OSError:
            return False
        if handle.popen is not None and handle.popen.poll() is not None:
            return False
        return True

    def _wait(self, handle: OwnedProcess, timeout: float) -> bool:
        poller = select.poll()
        poller.register(handle.pidfd, select.POLLIN)
        deadline = time.monotonic() + max(0.0, timeout)
        while True:
            remaining = deadline - time.monotonic()
            if poller.poll(max(0, int(remaining * 1000))):
                if handle.popen is not None:
                    try:
                        handle.popen.wait(timeout=1)
                    except subprocess.TimeoutExpired:
                        pass
                return True
            if remaining <= 0:
                return False

    def _verify_identity(self, handle: OwnedProcess) -> Optional[str]:
        start = proc_start_time(handle.pid)
        if start is None:
            return None  # already gone (zombie reaped); pidfd still pins identity
        if start != handle.start_time:
            return "start_time_changed"
        cgroup = proc_cgroup(handle.pid)
        if handle.beast_scope and cgroup and cgroup != handle.cgroup:
            return "cgroup_changed"
        reason = self._refuse_reason(handle.pid, cgroup=cgroup or handle.cgroup)
        if reason and reason != "foreign_uid":
            return reason
        if reason == "foreign_uid" and proc_uid(handle.pid) is not None:
            return reason
        return None

    def terminate(self, handle_or_id: OwnedProcess | str, *, reason: str, grace_s: float = 3.0,
                  measure_vram: bool = True) -> Dict[str, Any]:
        handle = self.handles[handle_or_id] if isinstance(handle_or_id, str) else handle_or_id
        if reason not in TRIGGERS:
            raise ValueError(f"unknown teardown trigger: {reason}")
        started = time.monotonic()
        refusal = self._verify_identity(handle)
        if refusal:
            receipt = self._receipt(handle, reason, ["refused"], {"refused": refusal}, started, ok=False)
            raise OwnershipError(f"teardown refused for pid {handle.pid}: {refusal} (receipt {receipt.get('receipt_id')})")
        vram_before = gpu_memory_by_pid().get(handle.pid, 0) if measure_vram else None
        gpu_total_before = gpu_used_total_mib() if measure_vram else None
        path: List[str] = []
        if self._alive(handle):
            signal.pidfd_send_signal(handle.pidfd, signal.SIGTERM)
            path.append("pidfd:SIGTERM")
            if not self._wait(handle, grace_s):
                if self._alive(handle):
                    signal.pidfd_send_signal(handle.pidfd, signal.SIGKILL)
                    path.append("pidfd:SIGKILL")
                    self._wait(handle, 5.0)
        else:
            path.append("already_exited")
        if handle.beast_scope and handle.cgroup:
            kill_file = self.cgroup_root / handle.cgroup.lstrip("/") / "cgroup.kill"
            try:
                if kill_file.exists():
                    kill_file.write_text("1")
                    path.append("cgroup.kill")
            except OSError as exc:
                path.append(f"cgroup.kill_failed:{type(exc).__name__}")
        reclaimed: Dict[str, Any] = {"fds_closed": 0, "releases": {}}
        for fd in handle.owned_fds:
            try:
                os.close(fd)
                reclaimed["fds_closed"] += 1
            except OSError:
                pass
        handle.owned_fds.clear()
        for name, fn in handle.releases:
            try:
                fn()
                reclaimed["releases"][name] = "ok"
            except Exception as exc:  # noqa: BLE001 - reclaim is best effort, recorded
                reclaimed["releases"][name] = f"error:{type(exc).__name__}"
        handle.releases.clear()
        try:
            os.close(handle.pidfd)
        except OSError:
            pass
        handle.closed = True
        if measure_vram:
            time.sleep(0.5)
            reclaimed["vram_pid_before_mib"] = vram_before
            reclaimed["vram_pid_after_mib"] = gpu_memory_by_pid().get(handle.pid, 0)
            reclaimed["gpu_used_before_mib"] = gpu_total_before
            reclaimed["gpu_used_after_mib"] = gpu_used_total_mib()
        receipt = self._receipt(handle, reason, path, reclaimed, started, ok=True)
        self.handles.pop(handle.handle_id, None)
        return {"ok": True, "pid": handle.pid, "signal_path": path, "reclaimed": reclaimed,
                "receipt_id": receipt.get("receipt_id"), "elapsed_ms": round((time.monotonic() - started) * 1000, 1)}

    def _receipt(self, handle: OwnedProcess, reason: str, path: Iterable[str], reclaimed: Mapping[str, Any],
                 started: float, *, ok: bool) -> Dict[str, Any]:
        body = {"type": "process_teardown", "ok": ok, "trigger": reason, **handle.public(),
                "signal_path": list(path), "reclaimed": dict(reclaimed),
                "elapsed_ms": round((time.monotonic() - started) * 1000, 1)}
        if self.receipts is None:
            return body
        return self.receipts._append(body)  # same hash chain as governor decisions


__all__ = ["OwnedProcess", "OwnershipError", "ProcessLifecycle", "TRIGGERS", "enabled", "gpu_memory_by_pid",
           "proc_cgroup", "proc_start_time"]

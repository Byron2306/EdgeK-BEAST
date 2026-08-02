from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from threading import Event, Lock
import ctypes
import errno
import hashlib
import json
import os
import signal
import struct
import time
from typing import Any, Callable, Iterable, Mapping, Protocol, Sequence

from ..bpf_event_contracts import BPFEventKind, KernelObservation
from ..bpf_loss_receipts import LossLedger
from ..bpf_ring_adapter import BPFSensoriumAdapter, ProcessLeaseResolver
from .x1_runtime import inspect_prerequisites

EVENT_STRUCT = struct.Struct("<QIIIIIIQQ16sQQ")


class X2Error(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class AttachPoint:
    program: str
    kind: str
    target: str
    required: bool = True

    def __post_init__(self) -> None:
        if self.kind not in {"tracepoint", "kprobe", "kretprobe", "fentry", "fexit"}:
            raise ValueError(f"unsupported attach kind: {self.kind}")
        if not self.program or not self.target:
            raise ValueError("program and target are required")


@dataclass(frozen=True, slots=True)
class X2AttachManifest:
    object_path: str
    ring_map: str = "events"
    loss_map: str = "loss_counters"
    attachments: tuple[AttachPoint, ...] = field(default_factory=tuple)
    poll_timeout_ms: int = 100
    health_interval_s: float = 5.0

    def __post_init__(self) -> None:
        if not self.object_path.endswith(".bpf.o"):
            raise ValueError("object_path must reference a .bpf.o CO-RE object")
        if not self.attachments:
            raise ValueError("explicit attachment manifest may not be empty")
        if self.poll_timeout_ms < 1 or self.health_interval_s <= 0:
            raise ValueError("invalid polling configuration")

    @property
    def digest(self) -> str:
        body = json.dumps(self.to_dict(include_digest=False), sort_keys=True, separators=(",", ":")).encode()
        return "sha256:" + hashlib.sha256(body).hexdigest()

    def to_dict(self, *, include_digest: bool = True) -> dict[str, Any]:
        d = asdict(self)
        if include_digest:
            d["manifest_digest"] = self.digest
        d["authority"] = "observation_only"
        d["automatic_attach"] = False
        return d

    @classmethod
    def from_json(cls, path: str | Path) -> "X2AttachManifest":
        raw = json.loads(Path(path).read_text())
        raw["attachments"] = tuple(AttachPoint(**item) for item in raw["attachments"])
        return cls(**raw)


DEFAULT_ATTACHMENTS = (
    AttachPoint("on_exec", "tracepoint", "sched/sched_process_exec"),
    AttachPoint("on_exit", "tracepoint", "sched/sched_process_exit"),
    AttachPoint("on_wakeup", "tracepoint", "sched/sched_wakeup"),
    AttachPoint("on_switch", "tracepoint", "sched/sched_switch"),
    AttachPoint("on_tcp_connect", "tracepoint", "syscalls/sys_enter_connect", required=False),
    AttachPoint("on_bind", "tracepoint", "syscalls/sys_enter_bind", required=False),
    AttachPoint("on_write", "kprobe", "vfs_write", required=False),
    AttachPoint("on_pwrite", "kprobe", "vfs_pwrite", required=False),
)


class RingBackend(Protocol):
    def open(self, manifest: X2AttachManifest) -> Mapping[str, Any]: ...
    def poll(self, timeout_ms: int) -> Sequence[bytes]: ...
    def read_kernel_losses(self) -> int: ...
    def close(self) -> Mapping[str, Any]: ...


class InMemoryRingBackend:
    """Deterministic backend used for contract tests and dry runs."""
    def __init__(self, records: Iterable[bytes] = (), *, kernel_losses: int = 0) -> None:
        self.records = list(records)
        self.kernel_losses = kernel_losses
        self.opened = False

    def open(self, manifest: X2AttachManifest) -> Mapping[str, Any]:
        self.opened = True
        return {"backend": "memory", "attached": [asdict(x) for x in manifest.attachments]}

    def poll(self, timeout_ms: int) -> Sequence[bytes]:
        if not self.opened:
            raise X2Error("backend not open")
        if not self.records:
            time.sleep(min(timeout_ms / 1000.0, 0.002))
            return ()
        return (self.records.pop(0),)

    def read_kernel_losses(self) -> int:
        return self.kernel_losses

    def close(self) -> Mapping[str, Any]:
        was = self.opened
        self.opened = False
        return {"detached": was, "backend": "memory"}


class LibbpfBackend:
    """Production boundary for a generated libbpf skeleton/shared loader.

    X2 intentionally refuses to improvise attachment through shell commands. The
    supplied shared library must expose the narrow beast_x2_* ABI documented in README.
    """
    def __init__(self, shared_library: str | Path) -> None:
        self.path = Path(shared_library)
        self.lib: ctypes.CDLL | None = None
        self.handle: int | None = None

    def open(self, manifest: X2AttachManifest) -> Mapping[str, Any]:
        if not inspect_prerequisites().load_ready:
            raise PermissionError("live BPF attachment requires root or delegated BPF capabilities")
        if not self.path.is_file():
            raise FileNotFoundError(self.path)
        self.lib = ctypes.CDLL(str(self.path))
        for symbol in ("beast_x2_open", "beast_x2_poll", "beast_x2_loss", "beast_x2_close",
                       "beast_x2_attachment_mask"):
            if not hasattr(self.lib, symbol):
                raise X2Error(f"loader ABI missing {symbol}")
        manifest_blob = json.dumps(manifest.to_dict()).encode()
        self.lib.beast_x2_open.argtypes = [ctypes.c_char_p, ctypes.c_size_t]
        self.lib.beast_x2_open.restype = ctypes.c_void_p
        handle = self.lib.beast_x2_open(manifest_blob, len(manifest_blob))
        if not handle:
            raise X2Error("libbpf loader refused manifest or failed attachment")
        self.handle = int(handle)
        self.lib.beast_x2_attachment_mask.argtypes = [ctypes.c_void_p]
        self.lib.beast_x2_attachment_mask.restype = ctypes.c_uint
        mask = int(self.lib.beast_x2_attachment_mask(self.handle))
        attached = [asdict(point) for index, point in enumerate(manifest.attachments) if mask & (1 << index)]
        missing_required = [point.program for index, point in enumerate(manifest.attachments)
                            if point.required and not (mask & (1 << index))]
        if missing_required:
            self.close()
            raise X2Error(f"required BPF programs not attached: {missing_required}")
        object_digest = "sha256:" + hashlib.sha256(Path(manifest.object_path).read_bytes()).hexdigest()
        return {
            "backend": "libbpf",
            "loader": str(self.path),
            "manifest_digest": manifest.digest,
            "bpf_object": str(manifest.object_path),
            "bpf_object_digest": object_digest,
            "bpf_object_loaded": True,
            "programs_attached": attached,
        }

    def poll(self, timeout_ms: int) -> Sequence[bytes]:
        if self.lib is None or self.handle is None:
            raise X2Error("backend not open")
        buf = (ctypes.c_ubyte * EVENT_STRUCT.size)()
        self.lib.beast_x2_poll.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_size_t]
        self.lib.beast_x2_poll.restype = ctypes.c_int
        rc = self.lib.beast_x2_poll(self.handle, timeout_ms, buf, EVENT_STRUCT.size)
        if rc == 0:
            return ()
        # A controlled SIGTERM interrupts the blocking ring poll.  Signal
        # handlers have already requested runtime shutdown, so this is not a
        # data-plane failure and the outer loop will detach and write a receipt.
        if rc == -errno.EINTR:
            return ()
        if rc < 0:
            raise X2Error(f"ring poll failed: {rc}")
        if rc != EVENT_STRUCT.size:
            raise X2Error(f"unexpected event size: {rc}")
        return (bytes(buf),)

    def read_kernel_losses(self) -> int:
        if self.lib is None or self.handle is None:
            return 0
        self.lib.beast_x2_loss.argtypes = [ctypes.c_void_p]
        self.lib.beast_x2_loss.restype = ctypes.c_ulonglong
        return int(self.lib.beast_x2_loss(self.handle))

    def close(self) -> Mapping[str, Any]:
        if self.lib is not None and self.handle is not None:
            self.lib.beast_x2_close.argtypes = [ctypes.c_void_p]
            self.lib.beast_x2_close(self.handle)
        detached = self.handle is not None
        self.handle = None
        self.lib = None
        return {"detached": detached, "backend": "libbpf"}


def decode_kernel_record(data: bytes) -> KernelObservation:
    if len(data) != EVENT_STRUCT.size:
        raise ValueError(f"invalid record size {len(data)}; expected {EVENT_STRUCT.size}")
    ts, cpu, pid, tgid, uid, gid, kind, cgroup, seq, comm, arg0, arg1 = EVENT_STRUCT.unpack(data)
    try:
        event_kind = BPFEventKind(kind)
    except ValueError as exc:
        raise ValueError(f"unknown event kind {kind}") from exc
    safe_comm = comm.split(b"\0", 1)[0].decode("utf-8", "replace")
    return KernelObservation(event_kind, ts, cpu, pid, tgid, uid, gid, cgroup, seq, safe_comm,
                             {"arg0": int(arg0), "arg1": int(arg1)})


@dataclass(slots=True)
class X2RunReceipt:
    manifest_digest: str
    started_ns: int
    ended_ns: int
    backend: Mapping[str, Any]
    detach: Mapping[str, Any]
    health: Mapping[str, Any]
    stop_reason: str
    authority: str = "observation_only"
    raw_payload_retained: bool = False

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["receipt_digest"] = "sha256:" + hashlib.sha256(
            json.dumps(d, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        return d


class X2RingRuntime:
    def __init__(self, *, manifest: X2AttachManifest, backend: RingBackend,
                 sink: Callable[[Mapping[str, Any]], None], lease_resolver: ProcessLeaseResolver,
                 receipt_sink: Callable[[Mapping[str, Any]], None] | None = None) -> None:
        self.manifest = manifest
        self.backend = backend
        self.ledger = LossLedger()
        self.adapter = BPFSensoriumAdapter(sink=sink, lease_resolver=lease_resolver, ledger=self.ledger)
        self.receipt_sink = receipt_sink
        self._stop = Event()
        self._lock = Lock()

    def request_stop(self) -> None:
        self._stop.set()

    def run(self, *, max_polls: int | None = None) -> X2RunReceipt:
        prereq = inspect_prerequisites()
        if isinstance(self.backend, LibbpfBackend) and not prereq.load_ready:
            raise X2Error(f"host not load-ready: {prereq.to_dict()}")
        started = time.time_ns()
        backend_receipt = self.backend.open(self.manifest)
        stop_reason = "requested"
        polls = 0
        last_kernel_losses = 0
        last_health_ns = time.monotonic_ns()
        try:
            while not self._stop.is_set():
                if max_polls is not None and polls >= max_polls:
                    stop_reason = "max_polls"
                    break
                polls += 1
                try:
                    records = self.backend.poll(self.manifest.poll_timeout_ms)
                except Exception:
                    self.ledger.poll_error()
                    stop_reason = "poll_error"
                    raise
                current_losses = self.backend.read_kernel_losses()
                if current_losses < last_kernel_losses:
                    self.ledger.poll_error()
                    raise X2Error("kernel loss counter regressed")
                self.ledger.kernel_loss(current_losses - last_kernel_losses)
                last_kernel_losses = current_losses
                for raw in records:
                    try:
                        observation = decode_kernel_record(raw)
                        self.adapter.accept(observation)
                    except Exception:
                        self.ledger.decode_failure()
                now_ns = time.monotonic_ns()
                if self.receipt_sink and now_ns - last_health_ns >= int(self.manifest.health_interval_s * 1_000_000_000):
                    self.receipt_sink(self.ledger.receipt().to_dict())
                    last_health_ns = now_ns
        finally:
            detach = self.backend.close()
        health = self.ledger.receipt().to_dict()
        health["correlation"] = self.adapter.correlation_receipt()
        receipt = X2RunReceipt(self.manifest.digest, started, time.time_ns(), backend_receipt, detach,
                               health, stop_reason)
        if self.receipt_sink:
            self.receipt_sink(receipt.to_dict())
        return receipt


def install_signal_handlers(runtime: X2RingRuntime) -> None:
    def stop(_signum: int, _frame: Any) -> None:
        runtime.request_stop()
    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)

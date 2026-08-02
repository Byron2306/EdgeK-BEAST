"""Capability-gated BPF ring-buffer observability facade.

Actual BPF program loading remains delegated to a privileged libbpf/bpftool
sidecar.  This module owns validation, bounded decoding, loss accounting, and
safe handoff into BEAST telemetry.
"""
from __future__ import annotations

import dataclasses
import json
import os
import queue
import shutil
import struct
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Callable, Mapping, Optional


@dataclasses.dataclass(frozen=True)
class BpfCapability:
    bpftool_available: bool
    bpf_fs_mounted: bool
    ringbuf_supported: bool
    sk_lookup_supported: bool
    detail: str = ""


@dataclasses.dataclass(frozen=True)
class RingBufferEvent:
    event_type: int
    payload: bytes
    occurred_ns: int
    cpu: int | None = None
    lost_events: int = 0


class RingBufferDecodeError(ValueError):
    pass


class BpfRingBuffer:
    """Bounded event consumer with an injectable privileged backend."""

    HEADER = struct.Struct("<IIQ")  # event_type, payload_size, occurred_ns

    def __init__(self, *, max_event_bytes: int = 1 << 20, queue_size: int = 4096) -> None:
        self.max_event_bytes = max(64, int(max_event_bytes))
        self._queue: queue.Queue[RingBufferEvent] = queue.Queue(maxsize=max(1, queue_size))
        self._callbacks: list[Callable[[RingBufferEvent], None]] = []
        self._lost = 0
        self._running = threading.Event()
        self._thread: Optional[threading.Thread] = None

    @staticmethod
    def probe() -> BpfCapability:
        bpftool = shutil.which("bpftool")
        bpf_fs = Path("/sys/fs/bpf").is_dir()
        ringbuf = False
        sk_lookup = False
        detail = ""
        if bpftool:
            try:
                result = subprocess.run([bpftool, "feature", "probe", "kernel"], capture_output=True, text=True, timeout=5, check=False)
                text = result.stdout + result.stderr
                ringbuf = "ringbuf" in text.lower()
                sk_lookup = "sk_lookup" in text.lower()
                detail = text[:2048]
            except (OSError, subprocess.TimeoutExpired) as exc:
                detail = str(exc)
        return BpfCapability(bool(bpftool), bpf_fs, ringbuf, sk_lookup, detail)

    def decode(self, raw: bytes) -> RingBufferEvent:
        if len(raw) < self.HEADER.size:
            raise RingBufferDecodeError("event shorter than header")
        event_type, payload_size, occurred_ns = self.HEADER.unpack_from(raw)
        if payload_size > self.max_event_bytes:
            raise RingBufferDecodeError("event exceeds configured bound")
        end = self.HEADER.size + payload_size
        if end != len(raw):
            raise RingBufferDecodeError("payload size mismatch")
        return RingBufferEvent(event_type, raw[self.HEADER.size:end], occurred_ns)

    def submit_raw(self, raw: bytes) -> bool:
        event = self.decode(raw)
        try:
            self._queue.put_nowait(event)
            return True
        except queue.Full:
            self._lost += 1
            return False

    def submit_json(self, event_type: int, payload: Mapping[str, Any], *, occurred_ns: int | None = None) -> bool:
        body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        return self.submit_raw(self.HEADER.pack(event_type, len(body), occurred_ns or time.time_ns()) + body)

    def register_callback(self, callback: Callable[[RingBufferEvent], None]) -> None:
        self._callbacks.append(callback)

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._running.set()
        self._thread = threading.Thread(target=self._dispatch, name="beast-bpf-ringbuf", daemon=True)
        self._thread.start()

    def _dispatch(self) -> None:
        while self._running.is_set():
            try:
                event = self._queue.get(timeout=0.25)
            except queue.Empty:
                continue
            if self._lost:
                event = dataclasses.replace(event, lost_events=self._lost)
                self._lost = 0
            for callback in tuple(self._callbacks):
                try:
                    callback(event)
                except Exception:
                    continue

    def stop(self, timeout: float = 2.0) -> None:
        self._running.clear()
        if self._thread and self._thread is not threading.current_thread():
            self._thread.join(timeout)

    @property
    def lost_events(self) -> int:
        return self._lost

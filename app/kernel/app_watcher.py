"""Linux fanotify watcher with safe notification mode and polling fallback."""
from __future__ import annotations

import ctypes
import dataclasses
import errno
import os
import select
import stat
import threading
import time
from pathlib import Path
from typing import Callable, Iterable, Optional

libc = ctypes.CDLL(None, use_errno=True)

FAN_CLASS_NOTIF = 0x00000000
FAN_CLOEXEC = 0x00000001
FAN_NONBLOCK = 0x00000002
FAN_MARK_ADD = 0x00000001
FAN_MARK_ONLYDIR = 0x00000008
FAN_MARK_MOUNT = 0x00000010
FAN_ACCESS = 0x00000001
FAN_MODIFY = 0x00000002
FAN_CLOSE_WRITE = 0x00000008
FAN_OPEN = 0x00000020
FAN_MOVED_FROM = 0x00000040
FAN_MOVED_TO = 0x00000080
FAN_CREATE = 0x00000100
FAN_DELETE = 0x00000200
FAN_DELETE_SELF = 0x00000400
FAN_MOVE_SELF = 0x00000800
FAN_EVENT_ON_CHILD = 0x08000000
FAN_Q_OVERFLOW = 0x00004000
FAN_NOFD = -1
FANOTIFY_METADATA_VERSION = 3


class FanotifyMetadata(ctypes.Structure):
    _fields_ = [
        ("event_len", ctypes.c_uint32),
        ("vers", ctypes.c_uint8),
        ("reserved", ctypes.c_uint8),
        ("metadata_len", ctypes.c_uint16),
        ("mask", ctypes.c_uint64),
        ("fd", ctypes.c_int32),
        ("pid", ctypes.c_int32),
    ]


@dataclasses.dataclass(frozen=True)
class FileWatchEvent:
    kind: str
    path: str
    pid: int | None
    mask: int
    backend: str
    occurred_at: float
    overflow: bool = False


class AppWatcher:
    """Watch a local tree without interposing on file-open permission decisions."""

    def __init__(
        self,
        watch_path: Path,
        *,
        recursive_mount: bool = True,
        polling_interval: float = 1.0,
        fallback_to_polling: bool = True,
    ) -> None:
        self.watch_path = Path(watch_path).resolve()
        if not self.watch_path.exists():
            raise FileNotFoundError(self.watch_path)
        self.polling_interval = max(0.1, float(polling_interval))
        self.callbacks: list[Callable[[FileWatchEvent], None]] = []
        self._running = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._fd = -1
        self.backend = "fanotify"
        try:
            self._fd = self._init_fanotify(recursive_mount)
        except OSError:
            if not fallback_to_polling:
                raise
            self.backend = "polling"
        self._snapshot = self._scan() if self.backend == "polling" else {}

    def _init_fanotify(self, recursive_mount: bool) -> int:
        fd = libc.fanotify_init(FAN_CLASS_NOTIF | FAN_CLOEXEC | FAN_NONBLOCK, os.O_RDONLY | os.O_LARGEFILE)
        if fd < 0:
            err = ctypes.get_errno()
            raise OSError(err, os.strerror(err))
        mask = FAN_MODIFY | FAN_CLOSE_WRITE | FAN_CREATE | FAN_DELETE | FAN_MOVED_FROM | FAN_MOVED_TO | FAN_DELETE_SELF | FAN_MOVE_SELF | FAN_EVENT_ON_CHILD
        flags = FAN_MARK_ADD | (FAN_MARK_MOUNT if recursive_mount else FAN_MARK_ONLYDIR)
        result = libc.fanotify_mark(fd, flags, ctypes.c_uint64(mask), -1, os.fsencode(self.watch_path))
        if result < 0:
            err = ctypes.get_errno()
            os.close(fd)
            raise OSError(err, os.strerror(err))
        return int(fd)

    def register_callback(self, callback: Callable[[FileWatchEvent], None]) -> None:
        if not callable(callback):
            raise TypeError("callback must be callable")
        self.callbacks.append(callback)

    def unregister_callback(self, callback: Callable[[FileWatchEvent], None]) -> None:
        self.callbacks = [item for item in self.callbacks if item is not callback]

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._running.set()
        self._thread = threading.Thread(target=self._run, name=f"beast-watch:{self.watch_path.name}", daemon=True)
        self._thread.start()

    def _emit(self, event: FileWatchEvent) -> None:
        for callback in tuple(self.callbacks):
            try:
                callback(event)
            except Exception:
                # A consumer must not kill the watcher thread.
                continue

    @staticmethod
    def _kind(mask: int) -> str:
        if mask & FAN_Q_OVERFLOW:
            return "OVERFLOW"
        if mask & FAN_CREATE:
            return "CREATED"
        if mask & FAN_DELETE:
            return "DELETED"
        if mask & (FAN_MOVED_FROM | FAN_MOVED_TO | FAN_MOVE_SELF):
            return "MOVED"
        if mask & (FAN_MODIFY | FAN_CLOSE_WRITE):
            return "MODIFIED"
        return "CHANGED"

    def _run(self) -> None:
        if self.backend == "fanotify":
            self._run_fanotify()
        else:
            self._run_polling()

    def _run_fanotify(self) -> None:
        poller = select.poll()
        poller.register(self._fd, select.POLLIN | select.POLLERR)
        size = ctypes.sizeof(FanotifyMetadata)
        while self._running.is_set():
            for _, mask in poller.poll(500):
                if mask & select.POLLERR:
                    self._emit(FileWatchEvent("OVERFLOW", str(self.watch_path), None, FAN_Q_OVERFLOW, self.backend, time.time(), True))
                    continue
                try:
                    data = os.read(self._fd, 65536)
                except BlockingIOError:
                    continue
                except OSError:
                    return
                offset = 0
                while offset + size <= len(data):
                    meta = FanotifyMetadata.from_buffer_copy(data[offset:offset + size])
                    if meta.vers != FANOTIFY_METADATA_VERSION or meta.event_len < meta.metadata_len:
                        break
                    path = ""
                    if meta.fd >= 0:
                        try:
                            path = os.readlink(f"/proc/self/fd/{meta.fd}")
                        except OSError:
                            path = ""
                        finally:
                            os.close(meta.fd)
                    overflow = bool(meta.mask & FAN_Q_OVERFLOW)
                    self._emit(FileWatchEvent(self._kind(meta.mask), path, meta.pid or None, int(meta.mask), self.backend, time.time(), overflow))
                    offset += int(meta.event_len)

    def _scan(self) -> dict[str, tuple[int, int, int]]:
        values: dict[str, tuple[int, int, int]] = {}
        for root, dirs, files in os.walk(self.watch_path, followlinks=False):
            for name in (*dirs, *files):
                path = Path(root) / name
                try:
                    info = path.lstat()
                except OSError:
                    continue
                values[str(path)] = (info.st_mtime_ns, info.st_size, stat.S_IFMT(info.st_mode))
        return values

    def _run_polling(self) -> None:
        while self._running.is_set():
            time.sleep(self.polling_interval)
            if not self._running.is_set():
                break
            current = self._scan()
            before = self._snapshot
            for path in sorted(current.keys() - before.keys()):
                self._emit(FileWatchEvent("CREATED", path, None, 0, self.backend, time.time()))
            for path in sorted(before.keys() - current.keys()):
                self._emit(FileWatchEvent("DELETED", path, None, 0, self.backend, time.time()))
            for path in sorted(current.keys() & before.keys()):
                if current[path] != before[path]:
                    self._emit(FileWatchEvent("MODIFIED", path, None, 0, self.backend, time.time()))
            self._snapshot = current

    def stop(self, timeout: float = 2.0) -> None:
        self._running.clear()
        if self._fd >= 0:
            try:
                os.close(self._fd)
            except OSError:
                pass
            self._fd = -1
        if self._thread and self._thread is not threading.current_thread():
            self._thread.join(timeout=max(0.0, timeout))

    def __enter__(self) -> "AppWatcher":
        self.start()
        return self

    def __exit__(self, *_: object) -> None:
        self.stop()

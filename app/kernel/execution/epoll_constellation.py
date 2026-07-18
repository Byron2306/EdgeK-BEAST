"""One epoll constellation for live kernel and runtime handles."""

from __future__ import annotations

import select
from dataclasses import dataclass
from threading import RLock
from typing import Any, Dict, List


@dataclass(frozen=True)
class LifecycleHandle:
    fd: int
    kind: str
    identity: str
    metadata: Dict[str, Any]


@dataclass(frozen=True)
class LifecycleEvent:
    fd: int
    kind: str
    identity: str
    readable: bool
    error: bool
    hangup: bool
    raw_mask: int
    metadata: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "beast_object_type": "lifecycle_handle_event",
            "version": "1.0",
            "fd_serialized_as_identity": False,
            "kind": self.kind,
            "identity": self.identity,
            "readable": self.readable,
            "error": self.error,
            "hangup": self.hangup,
            "raw_mask": self.raw_mask,
            "metadata": dict(self.metadata),
        }


class EpollConstellation:
    def __init__(self):
        if not hasattr(select, "epoll"):
            raise RuntimeError("epoll is unavailable on this platform")
        self._epoll = select.epoll()
        self._handles: Dict[int, LifecycleHandle] = {}
        self._lock = RLock()
        self._closed = False

    def register(self, fd: int, *, kind: str, identity: str, metadata: Dict[str, Any] | None = None) -> None:
        if fd < 0 or not kind or not identity:
            raise ValueError("fd, kind, and identity are required")
        with self._lock:
            self._ensure_open()
            if fd in self._handles:
                raise ValueError("file descriptor is already registered")
            mask = select.EPOLLIN | select.EPOLLERR | select.EPOLLHUP
            self._epoll.register(fd, mask)
            self._handles[fd] = LifecycleHandle(fd, kind, identity, dict(metadata or {}))

    def unregister(self, fd: int) -> None:
        with self._lock:
            handle = self._handles.pop(fd, None)
            if handle is None or self._closed:
                return
            try:
                self._epoll.unregister(fd)
            except OSError:
                pass

    def poll(self, timeout: float = 0.0, maxevents: int = 64) -> List[LifecycleEvent]:
        with self._lock:
            self._ensure_open()
            ready = self._epoll.poll(max(0.0, float(timeout)), max(1, int(maxevents)))
            result = []
            for fd, mask in ready:
                handle = self._handles.get(fd)
                if handle is None:
                    continue
                result.append(LifecycleEvent(
                    fd=fd,
                    kind=handle.kind,
                    identity=handle.identity,
                    readable=bool(mask & select.EPOLLIN),
                    error=bool(mask & select.EPOLLERR),
                    hangup=bool(mask & select.EPOLLHUP),
                    raw_mask=mask,
                    metadata=dict(handle.metadata),
                ))
            return result

    def state(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "beast_object_type": "epoll_constellation_state",
                "version": "1.0",
                "registered_count": len(self._handles),
                "handle_kinds": sorted({handle.kind for handle in self._handles.values()}),
                "closed": self._closed,
                "read_only_observer": True,
            }

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._handles.clear()
            self._epoll.close()
            self._closed = True

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("epoll constellation is closed")

    def __enter__(self) -> "EpollConstellation":
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.close()

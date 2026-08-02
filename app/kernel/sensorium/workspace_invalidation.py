"""Fail-closed workspace change detection for context and crystal reuse."""
from __future__ import annotations

import hashlib
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


@dataclass(frozen=True)
class WorkspaceChange:
    path: str
    kind: str
    digest: str = ""
    source: str = "polling"
    occurred_at: float = 0.0


class WorkspaceInvalidationBus:
    """Small process-local bus; subscribers cannot prevent other subscribers."""

    def __init__(self, *, max_files: int = 512, max_bytes: int = 256 * 1024) -> None:
        self.max_files = max(1, int(max_files))
        self.max_bytes = max(1024, int(max_bytes))
        self._snapshots: dict[str, dict[str, tuple[int, int, str]]] = {}
        self._subscribers: list[Callable[[WorkspaceChange], None]] = []
        self._lock = threading.RLock()

    def subscribe(self, callback: Callable[[WorkspaceChange], None]) -> None:
        if not callable(callback):
            raise TypeError("callback must be callable")
        with self._lock:
            self._subscribers.append(callback)

    def _files(self, root: Path) -> list[Path]:
        files: list[Path] = []
        try:
            for path in root.rglob("*"):
                if path.is_file() and ".git" not in path.parts and ".beast" not in path.parts:
                    files.append(path)
        except OSError:
            return []
        return sorted(files, key=lambda item: str(item))[: self.max_files]

    def _digest(self, path: Path) -> str:
        try:
            size = path.stat().st_size
            if size > self.max_bytes:
                return f"size:{size}"
            return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError:
            return "missing"

    def _snapshot(self, root: Path) -> dict[str, tuple[int, int, str]]:
        values: dict[str, tuple[int, int, str]] = {}
        for path in self._files(root):
            try:
                info = path.stat()
                values[str(path)] = (info.st_mtime_ns, info.st_size, self._digest(path))
            except OSError:
                continue
        return values

    def poll(self, root: Path | str) -> list[WorkspaceChange]:
        resolved = str(Path(root).expanduser().resolve())
        current = self._snapshot(Path(resolved))
        with self._lock:
            previous = self._snapshots.get(resolved, current)
            self._snapshots[resolved] = current
            changes: list[WorkspaceChange] = []
            for path in sorted(current.keys() - previous.keys()):
                changes.append(WorkspaceChange(path, "created", current[path][2], occurred_at=time.time()))
            for path in sorted(previous.keys() - current.keys()):
                changes.append(WorkspaceChange(path, "deleted", "missing", occurred_at=time.time()))
            for path in sorted(current.keys() & previous.keys()):
                if current[path] != previous[path]:
                    changes.append(WorkspaceChange(path, "modified", current[path][2], occurred_at=time.time()))
            subscribers = tuple(self._subscribers)
        for change in changes:
            for callback in subscribers:
                try:
                    callback(change)
                except Exception:
                    continue
        return changes

    def forget(self, root: Path | str) -> None:
        with self._lock:
            self._snapshots.pop(str(Path(root).expanduser().resolve()), None)

"""Real-time workspace file sync primitives (Phase 5).

The IDE needs to know which files changed since the model last saw them.
``WorkspaceSync`` takes content-addressed snapshots (mtime, size, sha256) and
``FileSyncWatcher`` polls them on a background thread, emitting added/changed/
removed paths. The context bridge can then rebuild context from the diff instead
of rescanning and re-sending every selected file.
"""

from __future__ import annotations

import hashlib
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, Iterable, Mapping, Optional, Union

DEFAULT_EXCLUDED_PARTS = frozenset(
    {".git", ".hg", ".svn", "node_modules", "venv", ".venv", "__pycache__", ".pytest_cache", "dist", "build"}
)
DEFAULT_SENSITIVE_NAMES = frozenset({".env", ".env.local", ".env.production", "id_rsa", "id_dsa"})
DEFAULT_SENSITIVE_SUFFIXES = (".pem", ".key", ".p12", ".pfx", ".crt")


@dataclass(frozen=True)
class FileState:
    path: str
    mtime_ns: int
    size: int
    sha256: str

    def as_dict(self) -> Dict[str, object]:
        return {"path": self.path, "mtime_ns": self.mtime_ns, "size": self.size, "sha256": self.sha256}


@dataclass
class SyncSnapshot:
    files: Dict[str, FileState] = field(default_factory=dict)
    captured_at: float = field(default_factory=time.time)

    def diff(self, other: Optional["SyncSnapshot"]) -> Dict[str, list[str]]:
        previous = other.files if other is not None else {}
        added = sorted(path for path in self.files if path not in previous)
        removed = sorted(path for path in previous if path not in self.files)
        changed = sorted(
            path
            for path, state in self.files.items()
            if path in previous and (state.mtime_ns, state.size, state.sha256) != (
                previous[path].mtime_ns,
                previous[path].size,
                previous[path].sha256,
            )
        )
        return {"added": added, "changed": changed, "removed": removed}


@dataclass
class WorkspaceSync:
    workspace_root: Union[str, Path]
    excluded_parts: frozenset[str] = DEFAULT_EXCLUDED_PARTS
    sensitive_names: frozenset[str] = DEFAULT_SENSITIVE_NAMES
    sensitive_suffixes: tuple[str, ...] = DEFAULT_SENSITIVE_SUFFIXES
    max_bytes: int = 2_000_000
    extensions: Optional[tuple[str, ...]] = None

    def __post_init__(self) -> None:
        self.workspace_root = Path(self.workspace_root).expanduser().resolve()

    def _included(self, path: Path) -> bool:
        try:
            relative = path.relative_to(Path(self.workspace_root))
        except ValueError:
            return False
        if any(part in self.excluded_parts for part in relative.parts):
            return False
        name = path.name
        if name in self.sensitive_names or name.startswith(".env"):
            return False
        if any(name.endswith(suffix) for suffix in self.sensitive_suffixes):
            return False
        if self.extensions and path.suffix.lower() not in self.extensions:
            return False
        return True

    def scan(self) -> Dict[str, FileState]:
        root = Path(self.workspace_root)
        states: Dict[str, FileState] = {}
        if not root.is_dir():
            return states
        for path in root.rglob("*"):
            if not path.is_file() or not self._included(path):
                continue
            try:
                stat = path.stat()
                if stat.st_size > self.max_bytes:
                    continue
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
            except OSError:
                continue
            relative = path.relative_to(root).as_posix()
            states[relative] = FileState(relative, stat.st_mtime_ns, stat.st_size, "sha256:" + digest)
        return states

    def snapshot(self) -> SyncSnapshot:
        return SyncSnapshot(self.scan())

    def diff(self, previous: Optional[SyncSnapshot]) -> Dict[str, list[str]]:
        return self.snapshot().diff(previous)

    def changed_since(self, previous: Optional[SyncSnapshot]) -> Dict[str, list[str]]:
        return self.diff(previous)


class FileSyncWatcher:
    """Background poller that emits diffs whenever the workspace changes."""

    def __init__(
        self,
        sync: WorkspaceSync,
        *,
        interval_s: float = 1.0,
        on_change: Optional[Callable[[Dict[str, list[str]]], None]] = None,
    ) -> None:
        self.sync = sync
        self.interval_s = max(0.05, float(interval_s))
        self.on_change = on_change
        self.snapshot: Optional[SyncSnapshot] = None
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.last_diff: Dict[str, list[str]] = {"added": [], "changed": [], "removed": []}

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def poll(self) -> Dict[str, list[str]]:
        current = self.sync.snapshot()
        diff = current.diff(self.snapshot)
        self.snapshot = current
        self.last_diff = diff
        return diff

    def start(self) -> None:
        if self.running:
            return
        self._stop.clear()
        self.snapshot = self.sync.snapshot()
        self._thread = threading.Thread(target=self._loop, name="beast-file-sync", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        thread, self._thread = self._thread, None
        if thread is not None:
            thread.join(timeout=max(1.0, self.interval_s * 2))

    def _loop(self) -> None:
        while not self._stop.wait(self.interval_s):
            diff = self.poll()
            if any(diff.values()) and self.on_change is not None:
                try:
                    self.on_change(diff)
                except Exception:  # noqa: BLE001 - a watcher callback must not kill the loop
                    continue

    def __enter__(self) -> "FileSyncWatcher":
        self.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self.stop()


def scan_workspace(workspace_root: Union[str, Path], **kwargs: object) -> Dict[str, FileState]:
    return WorkspaceSync(workspace_root, **kwargs).scan()

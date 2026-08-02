"""Read-only process telemetry for local Ollama admission and proof.

This intentionally uses procfs as the portable baseline.  BPF can enrich the
same snapshot later, but unavailable kernel instrumentation never fabricates
latency, tokens, or ownership.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class OllamaRuntimeSnapshot:
    pid: int
    start_ticks: int
    rss_bytes: int
    cpu_ticks: int
    read_bytes: int
    write_bytes: int
    voluntary_context_switches: int
    involuntary_context_switches: int
    socket_fds: int
    observed_at: float
    source: str = "procfs"

    def to_dict(self) -> dict[str, Any]:
        return {
            "pid": self.pid, "start_ticks": self.start_ticks,
            "rss_bytes": self.rss_bytes, "cpu_ticks": self.cpu_ticks,
            "read_bytes": self.read_bytes, "write_bytes": self.write_bytes,
            "voluntary_context_switches": self.voluntary_context_switches,
            "involuntary_context_switches": self.involuntary_context_switches,
            "socket_fds": self.socket_fds, "observed_at": self.observed_at,
            "source": self.source,
        }


class OllamaRuntimeSensor:
    """Bounded, read-only observations of Ollama and its llama server."""

    def __init__(self, proc_root: Path | str = "/proc") -> None:
        self.proc_root = Path(proc_root)

    @staticmethod
    def _read(path: Path) -> str:
        try:
            return path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return ""

    def _is_ollama(self, directory: Path) -> bool:
        comm = self._read(directory / "comm").strip().lower()
        cmdline = self._read(directory / "cmdline").replace("\x00", " ").lower()
        return "ollama" in comm or "ollama" in cmdline

    def _snapshot_pid(self, pid: int) -> OllamaRuntimeSnapshot | None:
        directory = self.proc_root / str(pid)
        if not self._is_ollama(directory):
            return None
        stat_fields = self._read(directory / "stat").split()
        if len(stat_fields) < 24:
            return None
        io_values: dict[str, int] = {}
        for line in self._read(directory / "io").splitlines():
            key, _, value = line.partition(":")
            if key in {"read_bytes", "write_bytes"}:
                try:
                    io_values[key] = int(value.strip())
                except ValueError:
                    pass
        status: dict[str, int] = {}
        for line in self._read(directory / "status").splitlines():
            key, _, value = line.partition(":")
            if key in {"voluntary_ctxt_switches", "nonvoluntary_ctxt_switches"}:
                try:
                    status[key] = int(value.strip())
                except ValueError:
                    pass
        try:
            page_size = os.sysconf("SC_PAGE_SIZE")
            rss_bytes = max(0, int(stat_fields[23])) * int(page_size)
            cpu_ticks = max(0, int(stat_fields[13])) + max(0, int(stat_fields[14]))
            start_ticks = max(0, int(stat_fields[21]))
        except (ValueError, OSError):
            return None
        try:
            socket_fds = sum(1 for fd in (directory / "fd").iterdir()
                             if self._readlink_socket(fd))
        except OSError:
            socket_fds = 0
        return OllamaRuntimeSnapshot(
            pid=pid, start_ticks=start_ticks, rss_bytes=rss_bytes,
            cpu_ticks=cpu_ticks, read_bytes=io_values.get("read_bytes", 0),
            write_bytes=io_values.get("write_bytes", 0),
            voluntary_context_switches=status.get("voluntary_ctxt_switches", 0),
            involuntary_context_switches=status.get("nonvoluntary_ctxt_switches", 0),
            socket_fds=socket_fds, observed_at=time.time(),
        )

    @staticmethod
    def _readlink_socket(path: Path) -> bool:
        try:
            return os.readlink(path).startswith("socket:[")
        except OSError:
            return False

    def sample(self) -> dict[str, Any]:
        snapshots: list[OllamaRuntimeSnapshot] = []
        try:
            entries = sorted(item for item in self.proc_root.iterdir() if item.name.isdigit())
        except OSError:
            entries = []
        for entry in entries:
            snapshot = self._snapshot_pid(int(entry.name))
            if snapshot is not None:
                snapshots.append(snapshot)
        return {
            "collector": "procfs_runtime", "read_only": True,
            "bpf_enrichment": False, "processes": [item.to_dict() for item in snapshots],
            "limitations": ["no_token_level_attribution", "no_kernel_bpf_lifecycle_ordering"],
            "observed_at": time.time(),
        }

    @staticmethod
    def delta(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
        previous = {int(item["pid"]): item for item in before.get("processes", [])}
        current = {int(item["pid"]): item for item in after.get("processes", [])}
        rows = []
        for pid, item in current.items():
            old = previous.get(pid)
            if old is None or int(old.get("start_ticks", -1)) != int(item.get("start_ticks", -2)):
                continue
            rows.append({"pid": pid, **{key: int(item.get(key, 0)) - int(old.get(key, 0))
                      for key in ("cpu_ticks", "read_bytes", "write_bytes",
                                  "voluntary_context_switches", "involuntary_context_switches")}})
        return {"processes": rows, "process_count": len(current), "source": "procfs_delta"}

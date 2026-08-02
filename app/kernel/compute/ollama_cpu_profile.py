"""Topology-aware CPU profile for local Ollama requests."""
from __future__ import annotations

import math
import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CpuTopology:
    logical_cpus: int
    physical_cores: int

    @property
    def recommended_threads(self) -> int:
        return max(2, min(self.physical_cores, int(math.ceil(self.physical_cores * 0.6))))


def detect_topology(sys_cpu: Path = Path("/sys/devices/system/cpu")) -> CpuTopology:
    logical = len(list(sys_cpu.glob("cpu[0-9]*"))) or (os.cpu_count() or 1)
    pairs: set[tuple[str, str]] = set()
    for cpu in sys_cpu.glob("cpu[0-9]*"):
        try:
            pairs.add(((cpu / "topology/physical_package_id").read_text().strip(), (cpu / "topology/core_id").read_text().strip()))
        except OSError:
            continue
    return CpuTopology(logical, len(pairs) or logical)


def request_options(*, reduced: bool = False) -> dict[str, int]:
    topology = detect_topology()
    configured = os.environ.get("BEAST_OLLAMA_NUM_THREAD", "").strip()
    threads = int(configured) if configured.isdigit() else topology.recommended_threads
    if reduced:
        threads = min(threads, 2)
    raw_batch = os.environ.get("BEAST_OLLAMA_NUM_BATCH", "256")
    batch = int(raw_batch) if raw_batch.isdigit() else 256
    if reduced:
        batch = min(batch, 128)
    return {"num_thread": max(1, min(topology.physical_cores, threads)), "num_batch": max(32, min(2048, batch))}

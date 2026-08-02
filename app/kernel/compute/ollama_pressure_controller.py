"""Pressure-aware admission and budget control for local Ollama inference."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from app.kernel.governance.psi_governor import PsiGovernor
from app.kernel.compute.ollama_cpu_profile import request_options


@dataclass(frozen=True)
class OllamaPressureDecision:
    admitted: bool
    action: str
    reason: str
    num_ctx: int
    num_predict: int
    memory_available_mb: int = 0
    memory_percent: float = 0.0
    profile: str = "interactive"
    num_thread: int = 0
    num_batch: int = 0
    queue_required: bool = False
    cpu_some_avg10: float = 0.0
    cpu_full_avg10: float = 0.0
    cgroup: dict[str, Any] | None = None
    affinity: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"beast_object_type": "ollama_pressure_decision", "version": "1.0", **asdict(self)}


class OllamaPressureController:
    """Translate PSI and RAM pressure into bounded Ollama request budgets."""

    def __init__(self, *, psi_governor: PsiGovernor | None = None, meminfo: Path = Path("/proc/meminfo"), memory_reduce_percent: float = 82.0, memory_suppress_percent: float = 94.0) -> None:
        self.psi_governor = psi_governor or PsiGovernor()
        self.meminfo = Path(meminfo)
        self.memory_reduce_percent = float(memory_reduce_percent)
        self.memory_suppress_percent = float(memory_suppress_percent)

    def sample_memory(self) -> tuple[int, int, float]:
        values: dict[str, int] = {}
        try:
            for line in self.meminfo.read_text(encoding="utf-8", errors="replace").splitlines():
                key, _, raw = line.partition(":")
                if key in {"MemTotal", "MemAvailable"}:
                    values[key] = int(raw.strip().split()[0])
        except (OSError, ValueError, IndexError):
            return 0, 0, 0.0
        total = values.get("MemTotal", 0)
        available = values.get("MemAvailable", 0)
        used = max(0, total - available)
        return available // 1024, used // 1024, (used / total * 100.0) if total else 0.0

    def decide(
        self,
        *,
        num_ctx: int,
        num_predict: int,
        min_predict: int = 0,
        lane: str = "agent_planner",
        reuse_mode: str = "cold",
    ) -> OllamaPressureDecision:
        available_mb, _used_mb, memory_percent = self.sample_memory()
        samples = self.psi_governor.sample()
        psi = self.psi_governor.decide(lane, samples)
        cpu = samples.get("cpu")
        cpu_some = float(cpu.some_avg10 if cpu else 0.0)
        cpu_full = float(cpu.full_avg10 if cpu else 0.0)
        topology_options = request_options()
        eco_options = request_options(reduced=True)
        warm_options = {
            "num_thread": min(topology_options["num_thread"], 2),
            "num_batch": min(topology_options["num_batch"], 128),
        }
        controls = {
            "mode": "request_governed",
            "cgroup": "not_applied_by_ollama_api",
            "affinity": "not_applied_by_ollama_api",
            "parallelism": 1,
        }
        affinity = {
            "mode": "advisory",
            "requested_threads": topology_options["num_thread"],
            "applied": False,
        }
        if not psi.admitted or memory_percent >= self.memory_suppress_percent:
            reason = psi.reason if not psi.admitted else "memory pressure"
            return OllamaPressureDecision(False, "suppress", reason, 0, 0, available_mb, memory_percent, "refused", 0, 0, True, cpu_some, cpu_full, controls, affinity)
        if reuse_mode in {"kv", "warm"}:
            profile = "kv_warm"
            options = warm_options
            action = "admit_warm"
            reason = "verified KV route; limited warm inference"
        elif psi.action == "admit_reduced" or memory_percent >= self.memory_reduce_percent:
            profile = "eco"
            options = eco_options
            action = "admit_reduced"
            reason = "high host pressure; eco inference profile"
        else:
            profile = "interactive"
            options = topology_options
            action = "admit"
            reason = "low host pressure; interactive inference profile"
        requested_predict = max(1, int(num_predict))
        bounded_predict = min(requested_predict, 32 if profile != "interactive" else requested_predict)
        if min_predict:
            bounded_predict = max(bounded_predict, min(int(min_predict), requested_predict))
        return OllamaPressureDecision(
            True,
            action,
            reason,
            max(512 if profile != "interactive" else 256, min(int(num_ctx), 1024 if profile != "interactive" else int(num_ctx))),
            max(16 if profile != "interactive" else 8, bounded_predict),
            available_mb,
            memory_percent,
            profile,
            options["num_thread"],
            options["num_batch"],
            False,
            cpu_some,
            cpu_full,
            controls,
            {**affinity, "requested_threads": options["num_thread"]},
        )

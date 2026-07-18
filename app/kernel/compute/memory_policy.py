"""Read-only memory capability discovery and residency recommendations."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict


@dataclass(frozen=True)
class MemoryCapabilities:
    resctrl: bool
    damon: bool
    zswap: bool
    details: Dict[str, bool]


@dataclass(frozen=True)
class ResidencyAdvice:
    memory_class: str
    residency: str
    action: str
    reason: str


class MemoryPolicy:
    def __init__(self, *, resctrl_root: Path = Path("/sys/fs/resctrl"), damon_root: Path = Path("/sys/kernel/mm/damon"), zswap_path: Path = Path("/sys/module/zswap")):
        self.resctrl_root, self.damon_root, self.zswap_path = Path(resctrl_root), Path(damon_root), Path(zswap_path)

    def capabilities(self) -> MemoryCapabilities:
        details = {
            "resctrl_mount": self.resctrl_root.is_dir(),
            "resctrl_tasks": (self.resctrl_root / "tasks").exists(),
            "damon_sysfs": self.damon_root.is_dir(),
            "zswap_module": self.zswap_path.is_dir(),
        }
        return MemoryCapabilities(details["resctrl_mount"], details["damon_sysfs"], details["zswap_module"], details)

    def advise(self, memory_class: str, *, pressure: float = 0.0) -> ResidencyAdvice:
        if memory_class == "operator":
            return ResidencyAdvice(memory_class, "protected", "preserve", "operator lane")
        if memory_class == "active_model":
            return ResidencyAdvice(memory_class, "hot", "preserve", "active model working set")
        if pressure >= 50.0 or memory_class in {"deception_artifact", "inactive_worktree"}:
            return ResidencyAdvice(memory_class, "cold", "reclaimable", "memory pressure or inactive class")
        return ResidencyAdvice(memory_class, "warm", "retain", "normal pressure")


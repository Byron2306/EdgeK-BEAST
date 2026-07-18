"""PSI-driven, policy-only compute breathing for BEAST execution lanes."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Mapping


@dataclass(frozen=True)
class PsiSample:
    resource: str
    some_avg10: float
    full_avg10: float


@dataclass(frozen=True)
class LaneDecision:
    lane: str
    admitted: bool
    action: str
    reason: str


def parse_psi(resource: str, text: str) -> PsiSample:
    values = {}
    for line in text.splitlines():
        parts = line.split()
        if not parts:
            continue
        values[parts[0]] = next((float(item.split("=")[1]) for item in parts[1:] if item.startswith("avg10=")), 0.0)
    return PsiSample(resource, values.get("some", 0.0), values.get("full", 0.0))


class PsiGovernor:
    """Read PSI and return bounded lane decisions; it never schedules directly."""

    def __init__(self, root: Path = Path("/proc/pressure"), *, rising: float = 10.0, full: float = 50.0):
        self.root, self.rising, self.full = root, rising, full

    def sample(self) -> Dict[str, PsiSample]:
        result = {}
        for resource in ("cpu", "memory", "io"):
            try:
                result[resource] = parse_psi(resource, (self.root / resource).read_text())
            except OSError:
                result[resource] = PsiSample(resource, 0.0, 0.0)
        return result

    def decide(self, lane: str, samples: Mapping[str, PsiSample]) -> LaneDecision:
        peak_some = max((sample.some_avg10 for sample in samples.values()), default=0.0)
        peak_full = max((sample.full_avg10 for sample in samples.values()), default=0.0)
        if lane in {"operator", "security"}:
            return LaneDecision(lane, True, "preserve", "protected lane")
        if peak_full >= self.full:
            return LaneDecision(lane, False, "suppress", "full PSI pressure")
        if peak_some >= self.rising:
            action = "delay" if lane in {"summary", "background", "indexing"} else "admit_reduced"
            return LaneDecision(lane, action != "delay", action, "rising PSI pressure")
        return LaneDecision(lane, True, "admit", "low PSI pressure")


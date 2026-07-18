"""Telemetry-driven workload interference classification."""
from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class InterferenceDecision:
    bucket: str
    cpu_weight: int
    memory_concurrency: int
    io_weight: int
    reason: str

def classify(*, cpu_pressure: float, memory_pressure: float, io_pressure: float, trust: str = "verified", lane: str = "background") -> InterferenceDecision:
    for name,value in (("cpu",cpu_pressure),("memory",memory_pressure),("io",io_pressure)):
        if not 0.0 <= value <= 1.0: raise ValueError(f"{name}_pressure must be between 0 and 1")
    pressure=max(cpu_pressure,memory_pressure,io_pressure)
    if trust in {"operator","security"}:
        return InterferenceDecision("protected",200,8,200,"protected trust lane")
    if trust in {"quarantine","deception"}:
        return InterferenceDecision("quarantine",10,1,10,"restricted trust lane")
    if pressure >= .8: return InterferenceDecision("constrained",25,1,25,f"full {max((('cpu',cpu_pressure),('memory',memory_pressure),('io',io_pressure)),key=lambda item:item[1])[0]} pressure")
    if pressure >= .5: return InterferenceDecision("throttled",60,2,60,f"rising pressure in {lane} lane")
    return InterferenceDecision("normal",100,4,100,"pressure within budget")

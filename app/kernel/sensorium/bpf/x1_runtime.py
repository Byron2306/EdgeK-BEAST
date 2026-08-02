from __future__ import annotations
from dataclasses import dataclass, asdict
from pathlib import Path
import json, os, platform, time
from typing import Any, Mapping


_CAP_NET_ADMIN = 12
_CAP_PERFMON = 38
_CAP_BPF = 39


def _has_bpf_delegation() -> bool:
    """Return whether this process has the delegated capabilities needed by X1.

    A systemd service should run as an unprivileged account with a small
    capability bounding set, not as UID 0.  Linux exposes effective
    capabilities as a hexadecimal bitset in ``/proc/self/status``.
    """
    if os.geteuid() == 0:
        return True
    try:
        cap_eff = next(
            line.split(":", 1)[1].strip()
            for line in Path("/proc/self/status").read_text().splitlines()
            if line.startswith("CapEff:")
        )
        effective = int(cap_eff, 16)
    except (OSError, StopIteration, ValueError):
        return False
    required = (1 << _CAP_BPF) | (1 << _CAP_PERFMON) | (1 << _CAP_NET_ADMIN)
    return (effective & required) == required

@dataclass(frozen=True, slots=True)
class X1PrerequisiteReport:
    linux: bool
    btf_present: bool
    tracefs_present: bool
    bpffs_present: bool
    privileged: bool
    clang_present: bool
    bpftool_present: bool
    kernel_release: str

    @property
    def load_ready(self) -> bool:
        return self.linux and self.btf_present and self.tracefs_present and self.privileged

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self); d["load_ready"] = self.load_ready
        d["authority"] = "observation_only"; d["fail_closed"] = True
        return d

def inspect_prerequisites() -> X1PrerequisiteReport:
    from shutil import which
    return X1PrerequisiteReport(
        linux=platform.system() == "Linux",
        btf_present=Path("/sys/kernel/btf/vmlinux").exists(),
        tracefs_present=Path("/sys/kernel/tracing").exists() or Path("/sys/kernel/debug/tracing").exists(),
        bpffs_present=Path("/sys/fs/bpf").exists(),
        privileged=_has_bpf_delegation(),
        clang_present=which("clang") is not None,
        bpftool_present=which("bpftool") is not None,
        kernel_release=platform.release(),
    )

def write_prerequisite_receipt(path: str | Path) -> Mapping[str, Any]:
    report = inspect_prerequisites().to_dict()
    report["timestamp_ns"] = time.time_ns()
    p = Path(path); p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report

"""Privilege-gated host scheduling and network enforcement.

Discovery is always safe.  Mutation requires an explicit operator approval and
uses only declared commands; no policy route silently changes host scheduling,
VRFs, resctrl groups, DAMON schemes, or packet paths.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


@dataclass(frozen=True)
class HostCapability:
    name: str
    available: bool
    mutable: bool
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "available": self.available, "mutable": self.mutable, "detail": self.detail}


class HostEnforcementController:
    """Live detector and explicit plan/apply controller for Linux facilities."""
    def __init__(self, *, root: Path | str = "/") -> None:
        self.root = Path(root)

    def capabilities(self) -> dict[str, Any]:
        is_root = os.geteuid() == 0
        ip = shutil.which("ip")
        capabilities = (
            HostCapability("sched_ext", (self.root / "sys/kernel/sched_ext").exists(), is_root and (self.root / "sys/fs/bpf").exists(), "kernel sched_ext interface and BPF filesystem required"),
            HostCapability("resctrl", (self.root / "sys/fs/resctrl").is_dir(), is_root and os.access(self.root / "sys/fs/resctrl", os.W_OK), "resctrl filesystem must be mounted"),
            HostCapability("damon", (self.root / "sys/kernel/mm/damon/admin").is_dir(), is_root and os.access(self.root / "sys/kernel/mm/damon/admin", os.W_OK), "DAMON admin sysfs required"),
            HostCapability("vrf", bool(ip), is_root and bool(ip), "iproute2 and CAP_NET_ADMIN required"),
            HostCapability("af_xdp", (self.root / "sys/fs/bpf").exists(), is_root and (self.root / "sys/fs/bpf").exists(), "AF_XDP program/UMEM loader required"),
        )
        return {"beast_object_type": "host_enforcement_capabilities", "authority": "operator_gated",
                "host_mutation_allowed": is_root, "capabilities": [item.to_dict() for item in capabilities]}

    def plan(self, facility: str, config: Mapping[str, Any]) -> dict[str, Any]:
        available = {row["name"]: row for row in self.capabilities()["capabilities"]}
        if facility not in available:
            raise ValueError("unsupported host enforcement facility")
        commands: list[list[str]] = []
        if facility == "vrf":
            name = str(config.get("name") or "beast-vrf")
            table = str(int(config.get("table") or 1001))
            commands = [["ip", "link", "add", name, "type", "vrf", "table", table], ["ip", "link", "set", name, "up"]]
        elif facility == "resctrl":
            name = str(config.get("group") or "beast")
            commands = [["mkdir", "-p", str(self.root / "sys/fs/resctrl" / name)]]
        elif facility == "damon":
            commands = [["sh", "-c", "# configure reviewed DAMON scheme via sysfs"]]
        elif facility == "sched_ext":
            commands = [["sh", "-c", "# attach reviewed sched_ext BPF scheduler object"]]
        elif facility == "af_xdp":
            commands = [["sh", "-c", "# attach reviewed AF_XDP XDP program and UMEM"]]
        return {"beast_object_type": "host_enforcement_plan", "facility": facility, "capability": available[facility],
                "commands": commands, "dry_run": True, "requires": ["approved=true", "allow_host_mutation=true", "root/CAP_NET_ADMIN as applicable"],
                "opaque_program_loading": facility in {"sched_ext", "af_xdp"}}

    def apply(self, facility: str, config: Mapping[str, Any], *, approved: bool, allow_host_mutation: bool) -> dict[str, Any]:
        plan = self.plan(facility, config)
        if not approved or not allow_host_mutation:
            return {**plan, "status": "approval_required", "executed": False}
        capability = plan["capability"]
        if not capability["mutable"]:
            return {**plan, "status": "capability_unavailable", "executed": False}
        if facility in {"sched_ext", "af_xdp", "damon"}:
            return {**plan, "status": "reviewed_loader_required", "executed": False,
                    "reason": "BEAST will not attach opaque kernel programs or DAMON schemes without a signed reviewed loader artifact."}
        results = []
        for command in plan["commands"]:
            completed = subprocess.run(command, capture_output=True, text=True, timeout=15, check=False)
            results.append({"command": " ".join(command), "returncode": completed.returncode,
                            "stderr": completed.stderr[-500:]})
            if completed.returncode:
                return {**plan, "status": "failed", "executed": True, "results": results}
        return {**plan, "status": "applied", "executed": True, "results": results}

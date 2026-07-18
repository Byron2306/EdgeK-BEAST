"""Hardened systemd boundary for offline scientific compute evidence jobs."""
from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class EvidenceJobSpec:
    unit_name: str
    entrypoint: Path
    arguments: tuple[str, ...]
    working_directory: Path
    network_allowed: bool = False
    writable_paths: tuple[Path, ...] = ()


class EvidenceJobSupervisor:
    def __init__(self):
        self.last_unit = ""

    def run(self, spec: EvidenceJobSpec, *, timeout_seconds: float = 900.0) -> subprocess.CompletedProcess[str]:
        if not spec.entrypoint.is_file() or not spec.unit_name.startswith("beast-evidence-"):
            raise ValueError("invalid evidence job specification")
        command = [
            "systemd-run", "--user", "--wait", "--pipe", "--collect",
            f"--unit={spec.unit_name}", "--property=NoNewPrivileges=yes",
            "--property=PrivateTmp=yes", "--property=ProtectSystem=strict",
            "--property=ProtectHome=read-only", "--property=MemoryMax=1G",
            "--property=TasksMax=64", f"--working-directory={spec.working_directory}",
        ]
        if not spec.network_allowed:
            command.append("--property=PrivateNetwork=yes")
        for path in spec.writable_paths:
            resolved = path.resolve()
            resolved.mkdir(parents=True, exist_ok=True)
            command.append(f"--property=ReadWritePaths={resolved}")
        command.extend(("python3", str(spec.entrypoint), *spec.arguments))
        completed = subprocess.run(command, text=True, capture_output=True, timeout=timeout_seconds, check=False)
        self.last_unit = spec.unit_name
        if completed.returncode != 0:
            raise RuntimeError(f"supervised evidence job failed: {completed.stderr[-500:]}")
        return completed

"""Guardian/systemd boundary for production Forge runners."""
from __future__ import annotations

import subprocess
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


@dataclass(frozen=True)
class ForgeServiceSpec:
    node_id: str
    repository: str
    unit_name: str
    delegate: bool = True
    no_new_privileges: bool = True
    protect_system: str = "strict"


class ForgeSupervisor:
    """Starts Forge only as a hardened, delegated transient user service."""

    def __init__(self, *, isolation_verifier, runner: Path | None = None):
        self.isolation_verifier = isolation_verifier
        self.runner = runner or Path(__file__).resolve().parents[3] / "internal" / "run_forge_node.py"
        self.last_unit = ""

    def start(self, spec: ForgeServiceSpec, attestation: Mapping[str, Any]) -> str:
        if not self.isolation_verifier(attestation):
            raise PermissionError("Forge service requires a current isolation attestation")
        if not spec.delegate or not spec.no_new_privileges or spec.protect_system != "strict":
            raise PermissionError("Forge service specification weakens the Guardian boundary")
        command = [
            "systemd-run", "--user", f"--unit={spec.unit_name}", "--collect",
            "--property=Delegate=yes", "--property=NoNewPrivileges=yes",
            "--property=PrivateTmp=yes", "--property=ProtectSystem=strict",
            "--property=ProtectHome=read-only", "--property=KillMode=mixed",
            "python3", str(self.runner), "--node-id", spec.node_id, "--repo", spec.repository,
            "--isolation-attestation-json", json.dumps(dict(attestation), sort_keys=True, separators=(",", ":")),
        ]
        subprocess.run(command, check=True, capture_output=True, text=True)
        self.last_unit = spec.unit_name
        return spec.unit_name

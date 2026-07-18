"""Physical port-conflict fixture helpers for definitive crystal validation."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import socket
import subprocess
import sys
from dataclasses import dataclass


@dataclass(frozen=True)
class ProcessSocketEvidence:
    pid: int
    start_time_ticks: int
    executable_digest: str
    port: int
    health_probe_passed: bool


def start_listener() -> tuple[subprocess.Popen, ProcessSocketEvidence]:
    code = "import socket,time; s=socket.socket(); s.bind(('127.0.0.1',0)); s.listen(); print(s.getsockname()[1],flush=True); time.sleep(30)"
    proc = subprocess.Popen([sys.executable, "-c", code], stdout=subprocess.PIPE, text=True)
    assert proc.stdout is not None
    port = int(proc.stdout.readline().strip())
    stat = (Path(f"/proc/{proc.pid}/stat").read_text()).split()
    start = int(stat[21])
    exe = Path(f"/proc/{proc.pid}/exe").resolve()
    digest = "sha256:" + hashlib.sha256(exe.read_bytes()).hexdigest()
    probe = socket.create_connection(("127.0.0.1", port), timeout=1)
    probe.close()
    return proc, ProcessSocketEvidence(proc.pid, start, digest, port, True)


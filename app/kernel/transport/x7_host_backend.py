from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import time
from hashlib import sha256
from pathlib import Path
from typing import Any

from .x7_contracts import X7Approval, X7LaneResult, X7Preflight, X7Refusal


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_WORKER = ROOT / "bpf" / "build" / "beast_x3_af_xdp_worker"
DEFAULT_OBJECT = ROOT / "bpf" / "build" / "beast_x3_redirect.bpf.o"


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except Exception:
        return ""


def _iface_root(interface: str) -> Path:
    return Path("/sys/class/net") / interface


def _iface_exists(interface: str) -> bool:
    return _iface_root(interface).exists()


def _iface_up(interface: str) -> bool:
    return _read_text(_iface_root(interface) / "operstate") == "up"


def _iface_carrier(interface: str) -> bool:
    return _read_text(_iface_root(interface) / "carrier") == "1"


def _ping(peer_host: str, interface: str, timeout_seconds: float = 1.0) -> bool:
    if not peer_host:
        return False
    ping = shutil.which("ping")
    if not ping:
        return False
    completed = subprocess.run(
        [ping, "-c", "1", "-W", str(max(1, int(timeout_seconds))), "-I", interface, peer_host],
        capture_output=True,
        text=True,
        timeout=max(2.0, timeout_seconds + 1.0),
        check=False,
    )
    return completed.returncode == 0


def _bpftool_existing_xdp_program_id(interface: str) -> int | None:
    bpftool = shutil.which("bpftool")
    if not bpftool:
        return None
    completed = subprocess.run(
        [bpftool, "-j", "net", "show", "dev", interface],
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )
    if completed.returncode != 0 or not completed.stdout.strip():
        return None
    try:
        payload = json.loads(completed.stdout)
    except Exception:
        return None
    rows = payload if isinstance(payload, list) else [payload]
    for row in rows:
        xdp = row.get("xdp") if isinstance(row, dict) else None
        if not isinstance(xdp, dict):
            continue
        for candidate in (xdp.get("id"), xdp.get("prog_id")):
            if isinstance(candidate, int):
                return candidate
    return None


class X7HostBackend:
    """Host-backed X7 production canary adapter.

    This adapter intentionally refuses to hide missing host state. It uses:
    - sysfs + ping for preflight
    - the reviewed BEAST AF_XDP worker for the AF_XDP lane
    - an explicit UDP echo peer for the socket-shadow lane

    The AF_XDP worker owns its own XDP attach/detach lifecycle and refuses to
    replace an existing program because it uses UPDATE_IF_NOEXIST. For that
    reason ``attach`` is a no-op and ``detach_and_restore`` is vacuously true
    when preflight confirms no prior XDP program was present.
    """

    def __init__(
        self,
        *,
        interface: str,
        peer_host: str,
        peer_port: int = 45678,
        queue_id: int = 0,
        duration_seconds: int = 5,
        generic_xdp: bool = False,
        replacement_explicitly_allowed: bool = False,
        worker_path: Path = DEFAULT_WORKER,
        object_path: Path = DEFAULT_OBJECT,
    ) -> None:
        self.interface = interface
        self.peer_host = peer_host
        self.peer_port = int(peer_port)
        self.queue_id = int(queue_id)
        self.duration_seconds = int(duration_seconds)
        self.generic_xdp = bool(generic_xdp)
        self.replacement_explicitly_allowed = bool(replacement_explicitly_allowed)
        self.worker_path = Path(worker_path)
        self.object_path = Path(object_path)

    def inspect(self, approval: X7Approval) -> X7Preflight:
        interface_exists = _iface_exists(approval.interface)
        interface_up = interface_exists and _iface_up(approval.interface) and _iface_carrier(approval.interface)
        return X7Preflight(
            interface_exists=interface_exists,
            interface_up=interface_up,
            interface_matches_approval=(approval.interface == self.interface),
            peer_reachable=_ping(self.peer_host, self.interface),
            btf_available=Path("/sys/kernel/btf/vmlinux").exists(),
            bpffs_available=Path("/sys/fs/bpf").exists(),
            privileges_available=(os.geteuid() == 0),
            existing_xdp_program_id=_bpftool_existing_xdp_program_id(self.interface),
            replacement_explicitly_allowed=self.replacement_explicitly_allowed,
        )

    def attach(self, approval: X7Approval) -> int | None:
        if approval.interface != self.interface:
            raise X7Refusal("approval interface does not match configured backend interface")
        return None

    def run_af_xdp(self, approval: X7Approval, object_path: Path) -> X7LaneResult:
        if not self.object_path.is_file():
            raise X7Refusal(f"AF_XDP XDP object missing: {self.object_path}")
        build = subprocess.run(
            ["make", "-C", str(ROOT / "bpf"), "beast-x3-worker"],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        if build.returncode != 0:
            raise X7Refusal(f"AF_XDP worker build failed: {(build.stderr or build.stdout).strip()[:500]}")
        payload = object_path.read_bytes()
        packet_size = min(max(len(payload), 64), 2048)
        packets_per_second = max(1, min(approval.max_packets, 128))
        command = [
            str(self.worker_path),
            "--interface", self.interface,
            "--object", str(self.object_path),
            "--queue", str(self.queue_id),
            "--duration", str(self.duration_seconds),
        ]
        if self.generic_xdp:
            command.append("--generic-xdp")
        worker = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        start = time.perf_counter()
        try:
            time.sleep(0.25)
            sender = subprocess.run(
                [
                    "/usr/bin/python3",
                    str(ROOT / "scripts" / "x7_shadow_peer.py"),
                    "send",
                    "--host", self.peer_host,
                    "--port", str(self.peer_port),
                    "--seconds", str(max(1, self.duration_seconds - 1)),
                    "--packets-per-second", str(packets_per_second),
                    "--payload-size", str(packet_size),
                ],
                capture_output=True,
                text=True,
                timeout=max(10, self.duration_seconds + 5),
                check=False,
            )
            if sender.returncode != 0:
                raise X7Refusal(f"peer traffic sender failed: {(sender.stderr or sender.stdout).strip()[:500]}")
            output, errors = worker.communicate(timeout=max(10, self.duration_seconds + 5))
        finally:
            if worker.poll() is None:
                worker.kill()
        if worker.returncode != 0:
            raise X7Refusal(f"AF_XDP worker failed: {(errors or output).strip()[:500]}")
        try:
            result = json.loads(output)
        except Exception as exc:
            raise X7Refusal(f"AF_XDP worker returned invalid JSON: {exc}") from exc
        elapsed_ms = max(1.0, (time.perf_counter() - start) * 1000.0)
        object_digest = "sha256:" + sha256(object_path.read_bytes()).hexdigest()
        return X7LaneResult(
            lane="af_xdp",
            verified=int(result.get("packets_rx", 0)) > 0,
            object_digest=object_digest,
            packets=int(result.get("packets_rx", 0)),
            bytes_sent=int(result.get("bytes_rx", 0)),
            p99_latency_us=float(result.get("p99_latency_us", 0.0) or 0.0),
            delivery_ratio=1.0 if int(result.get("packets_rx", 0)) > 0 else 0.0,
            cpu_ms=elapsed_ms,
            detached=False,
            rollback_verified=False,
            error=None if int(result.get("packets_rx", 0)) > 0 else "no_ingress_packets_observed",
        )

    def detach_and_restore(self, approval: X7Approval, prior_program_id: int | None) -> tuple[bool, bool]:
        _ = approval
        return True, prior_program_id is None

    def run_socket_shadow(self, approval: X7Approval, object_path: Path) -> X7LaneResult:
        start = time.perf_counter()
        completed = subprocess.run(
            [
                "/usr/bin/python3",
                str(ROOT / "scripts" / "x7_shadow_peer.py"),
                "echo-check",
                "--host", self.peer_host,
                "--port", str(self.peer_port),
                "--file", str(object_path),
            ],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        if completed.returncode != 0:
            raise X7Refusal(f"socket shadow failed: {(completed.stderr or completed.stdout).strip()[:500]}")
        try:
            payload = json.loads(completed.stdout)
        except Exception as exc:
            raise X7Refusal(f"socket shadow returned invalid JSON: {exc}") from exc
        return X7LaneResult(
            lane="ordinary_socket_shadow",
            verified=bool(payload.get("verified")),
            object_digest=str(payload.get("object_digest") or ""),
            packets=1,
            bytes_sent=int(payload.get("bytes_sent", 0)),
            p99_latency_us=float(payload.get("latency_us", 0.0) or 0.0),
            delivery_ratio=1.0 if bool(payload.get("verified")) else 0.0,
            cpu_ms=max(1.0, (time.perf_counter() - start) * 1000.0),
            detached=True,
            rollback_verified=True,
            error=None if bool(payload.get("verified")) else "socket_shadow_digest_mismatch",
        )


def default_backend() -> X7HostBackend:
    return X7HostBackend(
        interface=os.environ.get("BEAST_X7_INTERFACE", "enp3s0"),
        peer_host=os.environ.get("BEAST_X7_PEER_HOST", "10.204.0.2"),
        peer_port=int(os.environ.get("BEAST_X7_PEER_PORT", "45678")),
        queue_id=int(os.environ.get("BEAST_X7_QUEUE_ID", "0")),
        duration_seconds=int(os.environ.get("BEAST_X7_DURATION_SECONDS", "5")),
        generic_xdp=str(os.environ.get("BEAST_X7_GENERIC_XDP", "")).strip().lower() in {"1", "true", "yes", "on"},
        replacement_explicitly_allowed=str(os.environ.get("BEAST_X7_REPLACE_XDP", "")).strip().lower() in {"1", "true", "yes", "on"},
    )

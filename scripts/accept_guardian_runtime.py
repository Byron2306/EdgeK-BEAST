#!/usr/bin/env python3
"""Live acceptance for Guardian-retained BEAST and Commons listeners."""
from __future__ import annotations

import argparse
import errno
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from urllib.error import HTTPError
from urllib.request import urlopen

from cryptography.hazmat.primitives import serialization

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.kernel.execution.process_identity import LinuxProcessIdentityCollector
from app.kernel.execution.socket_guardian import SocketGuardianClient


SERVICES = {
    "beast": {
        "unit": "beast-beast-guardian-consumer.service",
        "port": 8101,
        "url": "http://127.0.0.1:8101/health",
    },
    "commons": {
        "unit": "beast-commons-guardian-consumer.service",
        "port": 8601,
        "url": "http://127.0.0.1:8601/edgek/control-plane/commons",
    },
}


def _main_pid(unit: str) -> int:
    value = subprocess.check_output(
        ["systemctl", "--user", "show", unit, "-p", "MainPID", "--value"], text=True
    ).strip()
    return int(value)


def _http_json(url: str, timeout: float = 1.0):
    with urlopen(url, timeout=timeout) as response:
        return response.status, json.loads(response.read())


def _wait_http(url: str, deadline: float):
    last = None
    while time.monotonic() < deadline:
        try:
            return _http_json(url)
        except Exception as exc:
            last = exc
            time.sleep(0.05)
    raise RuntimeError(f"service did not recover before deadline: {url}: {last}")


def _handoff(state_root: Path, service: str):
    return json.loads((state_root / f"{service}-handoff.json").read_text(encoding="utf-8"))


def _guardian_snapshot(config_root: Path):
    public = serialization.load_pem_public_key(
        (config_root / "guardian-receipt-ed25519.pub.pem").read_bytes()
    )
    client = SocketGuardianClient(
        Path(os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}")
        / "beast/socket-guardian.sock",
        process_lease_provider=lambda: LinuxProcessIdentityCollector().collect(
            os.getpid(), owner_scope="guardian-live-acceptance"
        ),
        receipt_verifier=public,
    )
    return {lease.service_id: lease.__dict__ for lease in client.snapshot()}


def _monitor_port_ownership(stop: threading.Event, results: dict[int, dict[str, int]]) -> None:
    while not stop.is_set():
        for port, counts in results.items():
            probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                probe.bind(("127.0.0.1", port))
            except OSError as exc:
                if exc.errno == errno.EADDRINUSE:
                    counts["retained"] += 1
                else:
                    counts["unexpected_error"] += 1
            else:
                counts["ownership_gap"] += 1
            finally:
                probe.close()
        stop.wait(0.005)


def run(config_root: Path, state_root: Path, *, mode: str) -> dict:
    guardian_pid_before = _main_pid("beast-socket-guardian.service")
    before = {
        name: {
            "pid": _main_pid(item["unit"]),
            "handoff": _handoff(state_root, name),
            "http": _http_json(item["url"], timeout=5),
        }
        for name, item in SERVICES.items()
    }
    boundary_status = None
    try:
        urlopen("http://127.0.0.1:8601/edgek/control-plane/services", timeout=3)
    except HTTPError as exc:
        boundary_status = exc.code
    if boundary_status != 404:
        raise RuntimeError("Commons path boundary did not deny an unrelated route")
    port_samples = {
        item["port"]: {"retained": 0, "ownership_gap": 0, "unexpected_error": 0}
        for item in SERVICES.values()
    }
    if mode in {"consumer_restart", "guardian_replacement"}:
        stop = threading.Event()
        monitor = threading.Thread(
            target=_monitor_port_ownership, args=(stop, port_samples), daemon=True
        )
        monitor.start()
        try:
            units = [item["unit"] for item in SERVICES.values()]
            if mode == "consumer_restart":
                subprocess.run(["systemctl", "--user", "restart"] + units, check=True)
            else:
                subprocess.run(["systemctl", "--user", "stop"] + units, check=True)
                subprocess.run(
                    ["systemctl", "--user", "restart", "beast-socket-guardian.service"],
                    check=True,
                )
                subprocess.run(["systemctl", "--user", "start"] + units, check=True)
            deadline = time.monotonic() + 45
            for item in SERVICES.values():
                _wait_http(item["url"], deadline)
        finally:
            stop.set()
            monitor.join(timeout=2)
    health_deadline = time.monotonic() + 10
    after_snapshot = _guardian_snapshot(config_root)
    while time.monotonic() < health_deadline and any(
        after_snapshot.get(name, {}).get("health_state") != "healthy" for name in SERVICES
    ):
        time.sleep(0.05)
        after_snapshot = _guardian_snapshot(config_root)
    after = {
        name: {
            "pid": _main_pid(item["unit"]),
            "handoff": _handoff(state_root, name),
            "http": _http_json(item["url"], timeout=5),
            "guardian": after_snapshot[name],
        }
        for name, item in SERVICES.items()
    }
    generations_before = {
        name: before[name]["handoff"]["lease"]["listener_generation"] for name in SERVICES
    }
    generations_after = {
        name: after[name]["handoff"]["lease"]["listener_generation"] for name in SERVICES
    }
    assertions = {
        "commons_path_boundary_404": boundary_status == 404,
        "pids_replaced": all(before[name]["pid"] != after[name]["pid"] for name in SERVICES),
        "guardian_health_healthy": all(
            after[name]["guardian"]["health_state"] == "healthy" for name in SERVICES
        ),
        "no_port_ownership_gap": all(
            result["ownership_gap"] == 0 and result["retained"] > 0
            for result in port_samples.values()
        ),
    }
    if mode == "consumer_restart":
        assertions.update({
            "lease_ids_retained": all(
                before[name]["handoff"]["lease"]["lease_id"]
                == after[name]["handoff"]["lease"]["lease_id"]
                for name in SERVICES
            ),
            "listener_generations_retained": generations_before == generations_after,
            "guardian_pid_retained": guardian_pid_before == _main_pid("beast-socket-guardian.service"),
        })
    else:
        assertions.update({
            "guardian_pid_replaced": guardian_pid_before != _main_pid("beast-socket-guardian.service"),
            "listener_generations_advanced": all(
                generations_after[name] == generations_before[name] + 1 for name in SERVICES
            ),
            "ports_retained": all(
                before[name]["handoff"]["lease"]["port"]
                == after[name]["handoff"]["lease"]["port"]
                for name in SERVICES
            ),
        })
    if not all(assertions.values()):
        raise RuntimeError("Guardian live acceptance failed: " + json.dumps(assertions, sort_keys=True))
    return {
        "schema": "beast.guardian.runtime-acceptance.v1",
        "mode": mode,
        "claim_boundary": "live user-service replacement; not host reboot or hardware attestation",
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "assertions": assertions,
        "before": before,
        "after": after,
        "port_ownership_samples": port_samples,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--restart", action="store_true", help="replace BEAST/Commons consumers")
    mode.add_argument("--replace-guardian", action="store_true", help="replace Guardian between consumer stops")
    parser.add_argument("--config-root", default="~/.config/beast")
    parser.add_argument("--state-root", default="~/.local/state/beast")
    args = parser.parse_args()
    state_root = Path(args.state_root).expanduser().resolve()
    selected_mode = "guardian_replacement" if args.replace_guardian else "consumer_restart"
    report = run(Path(args.config_root).expanduser().resolve(), state_root, mode=selected_mode)
    evidence_name = {
        "consumer_restart": "guardian-consumer-restart-acceptance-latest.json",
        "guardian_replacement": "guardian-replacement-acceptance-latest.json",
    }[selected_mode]
    target = state_root / evidence_name
    temporary = target.with_name(target.name + ".tmp")
    temporary.write_text(json.dumps(report, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    temporary.chmod(0o600)
    os.replace(temporary, target)
    print(json.dumps({"status": "passed", "evidence": str(target), **report["assertions"]}, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

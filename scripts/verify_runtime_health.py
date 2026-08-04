#!/usr/bin/env python3
"""Verify that Guardian-managed BEAST services remain healthy over time.

The verifier derives probe URLs from `.byron/services.yaml`, samples systemd
restart counters, and exits non-zero if a required service becomes unhealthy or
restarts during the observation window.  It writes a JSON receipt only when an
explicit output path is supplied.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import time
from urllib.error import URLError
from urllib.request import ProxyHandler, build_opener

import yaml


ROOT = Path(__file__).resolve().parents[1]
GUARDIAN_UNITS = {
    "beast": "beast-beast-guardian-consumer.service",
    "commons": "beast-commons-guardian-consumer.service",
}


def _registry(path: Path) -> dict[str, dict[str, object]]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    services = raw.get("services") or {}
    selected = {name: dict(services[name]) for name in GUARDIAN_UNITS if name in services}
    if set(selected) != set(GUARDIAN_UNITS):
        raise ValueError("registry must declare BEAST and Commons services")
    return selected


def _restarts(unit: str) -> int:
    result = subprocess.run(
        ["systemctl", "--user", "show", unit, "--property=NRestarts", "--value"],
        check=True,
        capture_output=True,
        text=True,
    )
    return int(result.stdout.strip() or "0")


def _sample(services: dict[str, dict[str, object]], opener) -> dict[str, object]:
    result: dict[str, object] = {}
    for name, service in services.items():
        upstream = str(service["upstream"])
        health_path = str(service.get("health_path") or "/health")
        url = f"http://{upstream}{health_path}"
        try:
            with opener.open(url, timeout=5) as response:
                status = int(response.status)
            result[name] = {"url": url, "status": status, "healthy": 200 <= status < 400}
        except (OSError, URLError) as exc:
            result[name] = {"url": url, "status": 0, "healthy": False, "error": str(exc)}
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--registry", type=Path, default=ROOT / ".byron" / "services.yaml")
    parser.add_argument("--duration-seconds", type=int, default=600)
    parser.add_argument("--interval-seconds", type=int, default=15)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.duration_seconds < 1 or args.interval_seconds < 1:
        raise ValueError("duration and interval must be positive")

    services = _registry(args.registry)
    opener = build_opener(ProxyHandler({}))
    initial_restarts = {name: _restarts(unit) for name, unit in GUARDIAN_UNITS.items()}
    samples = []
    deadline = time.monotonic() + args.duration_seconds
    while True:
        health = _sample(services, opener)
        restarts = {name: _restarts(unit) for name, unit in GUARDIAN_UNITS.items()}
        samples.append({"observed_at": time.time(), "health": health, "restarts": restarts})
        if not all(item["healthy"] for item in health.values()):
            break
        if restarts != initial_restarts or time.monotonic() >= deadline:
            break
        time.sleep(min(args.interval_seconds, max(0.0, deadline - time.monotonic())))

    final = samples[-1]
    passed = all(item["healthy"] for item in final["health"].values()) and final["restarts"] == initial_restarts
    receipt = {
        "beast_object_type": "guardian_runtime_health_receipt",
        "passed": passed,
        "duration_seconds": args.duration_seconds,
        "initial_restarts": initial_restarts,
        "final_restarts": final["restarts"],
        "samples": samples,
    }
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({key: receipt[key] for key in ("passed", "initial_restarts", "final_restarts")}, sort_keys=True))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())

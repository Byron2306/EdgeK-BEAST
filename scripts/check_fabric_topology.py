#!/usr/bin/env python3
"""Read-only fabric topology check. Exit 0 when consistent, 1 on drift."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from app.kernel.networking.fabric_topology import FabricTopology  # noqa: E402


def _registry_endpoints(url: str) -> dict[str, str]:
    import httpx

    response = httpx.get(url.rstrip("/") + "/edgek/control-plane/commons/remote", timeout=10, trust_env=False)
    response.raise_for_status()
    return {str(node["node_id"]): str(node["endpoint"]) for node in response.json().get("nodes") or []}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--services", default=str(REPOSITORY_ROOT / ".byron" / "services.yaml"))
    parser.add_argument("--manifest", default=str(REPOSITORY_ROOT / ".beast" / "remote-commons-lab" / "manifest.json"))
    parser.add_argument("--compose", default=str(REPOSITORY_ROOT / "docker-compose.commons-lab.yml"))
    parser.add_argument("--compose-override", default="")
    parser.add_argument("--gateway-url", default="", help="optional loopback gateway to compare live registry endpoints")
    args = parser.parse_args()
    topology = FabricTopology.load(
        services_path=args.services, lab_manifest_path=args.manifest,
        compose_base_path=args.compose, compose_override_path=args.compose_override or None,
    )
    endpoints = _registry_endpoints(args.gateway_url) if args.gateway_url else None
    report = topology.report(endpoints)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["consistent"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

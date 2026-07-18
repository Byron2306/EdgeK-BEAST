#!/usr/bin/env python3
"""Submit an ordinary mission through the running BEAST application API."""
from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.request


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--beast-url", default="http://127.0.0.1:8000")
    parser.add_argument("--task-family", required=True)
    parser.add_argument("--workspace-root", required=True)
    parser.add_argument("--mission-id", default="")
    parser.add_argument("--interface", choices=("api", "cli", "ide"), default="cli")
    args = parser.parse_args()
    payload = {"task_family": args.task_family, "workspace_root": args.workspace_root}
    if args.mission_id:
        payload["mission_id"] = args.mission_id
    request = urllib.request.Request(
        args.beast_url.rstrip("/") + (
            "/edgek/compute/missions" if args.interface == "api"
            else f"/edgek/compute/{args.interface}/missions"
        ),
        data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            print(json.dumps(json.loads(response.read()), indent=2, sort_keys=True))
    except urllib.error.HTTPError as exc:
        print(exc.read().decode())
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

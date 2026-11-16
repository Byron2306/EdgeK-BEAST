#!/usr/bin/env python3
"""Verify exact Commons service identity and its signed node descriptor."""
from __future__ import annotations

import argparse
import json
import os
import time
from collections.abc import Callable, Mapping
from typing import Any
from urllib.request import Request, urlopen

from app.kernel.commons.node_health import verify_node_health


def _fetcher(base_url: str) -> Callable[[str], Mapping[str, Any]]:
    origin = base_url.rstrip("/")

    def fetch(path: str) -> Mapping[str, Any]:
        request = Request(origin + path, headers={"Accept": "application/json"})
        with urlopen(request, timeout=3) as response:
            if response.status != 200:
                raise RuntimeError(f"health endpoint returned {response.status}")
            return json.loads(response.read(1_048_577))

    return fetch


def run_healthcheck(
    *, base_url: str, expected_node_id: str,
    fetch_json: Callable[[str], Mapping[str, Any]] | None = None,
    now: float | None = None,
) -> dict[str, Any]:
    fetch = fetch_json or _fetcher(base_url)
    try:
        health = dict(fetch("/health"))
        if (
            health.get("ok") is not True
            or health.get("service") != "beast-remote-commons-node"
            or health.get("node_id") != expected_node_id
        ):
            return {"ok": False, "reason": "service_identity_mismatch"}
        return verify_node_health(
            fetch("/v1/node"),
            expected_node_id=expected_node_id,
            now=time.time() if now is None else now,
        )
    except Exception as exc:
        return {"ok": False, "reason": "probe_failed", "error_type": type(exc).__name__}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument(
        "--node-id",
        default=os.environ.get("BEAST_COMMONS_NODE_ID", os.environ.get("BEAST_NODE_ID", "")),
    )
    args = parser.parse_args(argv)
    result = run_healthcheck(base_url=args.base_url, expected_node_id=args.node_id)
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0 if result.get("ok") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Smoke-test the Docker Commons federation lab over HTTP."""

from __future__ import annotations

import json
import sys
import time
from typing import Any, Dict

import httpx


NODE_A = "http://127.0.0.1:8101"
NODE_B = "http://127.0.0.1:8102"
NODE_A_INTERNAL = "http://commons-node-a:8000"


def get(client: httpx.Client, url: str) -> Dict[str, Any]:
    res = client.get(url)
    res.raise_for_status()
    return res.json()


def post(client: httpx.Client, url: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    res = client.post(url, json=payload)
    res.raise_for_status()
    return res.json()


def wait_for(client: httpx.Client, base: str, timeout: int = 60) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if get(client, base + "/health").get("status") == "healthy":
                return
        except Exception:
            time.sleep(1)
    raise RuntimeError(f"node did not become healthy: {base}")


def main() -> None:
    with httpx.Client(timeout=20) as client:
        wait_for(client, NODE_A)
        wait_for(client, NODE_B)
        registry_a = get(client, NODE_A + "/edgek/commons-spaces")
        registry_b = get(client, NODE_B + "/edgek/commons-spaces")
        spaces = registry_a.get("spaces") or []
        node_b_space_ids = {str(item.get("space_id") or "") for item in registry_b.get("spaces") or []}
        space = next(
            (item for item in spaces if item.get("valid") and str(item.get("space_id") or "") not in node_b_space_ids),
            None,
        )
        if space is None:
            space = next((item for item in spaces if item.get("valid")), None)
        if not space:
            raise RuntimeError("node A has no valid spaces to federate")
        space_id = str(space["space_id"])
        bundle_import: Dict[str, Any]
        try:
            bundle_import = post(
                client,
                NODE_B + "/edgek/commons-spaces/import-remote",
                {
                    "bundle_url": NODE_A_INTERNAL + f"/edgek/commons-spaces/{space_id}/bundle",
                    "approved": True,
                    "dry_run": False,
                    "timeout_seconds": 60,
                },
            )
        except httpx.HTTPStatusError as exc:
            bundle_import = {"imported": False, "error": exc.response.text}
        envelope = post(
            client,
            NODE_A + f"/edgek/federated-commons/prepare/{space_id}",
            {"contributor_id": "commons-node-a", "ttl_days": 7},
        )
        allow = post(
            client,
            NODE_B + "/edgek/federated-commons/allowlist",
            {
                "contributor_id": "commons-node-a",
                "public_key_hash": envelope["signature"]["public_key_hash"],
                "approved": True,
                "reason": "local docker commons lab smoke",
            },
        )
        ingest = post(
            client,
            NODE_B + "/edgek/federated-commons/ingest",
            {"envelope": envelope},
        )
        reproduced: Dict[str, Any]
        try:
            reproduced = post(
                client,
                NODE_B + f"/edgek/federated-commons/{envelope['envelope_id']}/reproduce",
                {"deterministic_only": True},
            )
        except httpx.HTTPStatusError as exc:
            reproduced = {"reproduced": False, "error": exc.response.text}
        print(json.dumps({
            "space_id": space_id,
            "node_a_spaces": registry_a.get("count"),
            "node_b_spaces_before": registry_b.get("count"),
            "bundle_import": bundle_import,
            "allowlist": allow,
            "ingest": ingest,
            "reproduction": reproduced,
            "node_b_federation": get(client, NODE_B + "/edgek/federated-commons"),
        }, indent=2, sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2), file=sys.stderr)
        raise

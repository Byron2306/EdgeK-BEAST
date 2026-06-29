#!/usr/bin/env python3
"""Smoke-test the Docker Commons federation lab over HTTP."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any, Dict

import httpx


NODE_A = "http://127.0.0.1:8101"
NODE_B = "http://127.0.0.1:8102"
NODE_C = "http://127.0.0.1:8103"
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
        wait_for(client, NODE_C)
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
        receipt_packet = get(
            client,
            NODE_A + f"/edgek/proof-local/spaces/{space_id}/receipt?contributor_id=commons-node-a",
        )
        receipt_ingest_b = post(
            client, NODE_B + "/edgek/proof-local/receipt-packets/ingest", {"packet": receipt_packet},
        )
        allow_c = post(
            client,
            NODE_C + "/edgek/federated-commons/allowlist",
            {
                "contributor_id": "commons-node-a",
                "public_key_hash": receipt_packet["signature"]["public_key_hash"],
                "approved": True,
                "reason": "local docker proof-local smoke",
            },
        )
        receipt_ingest_c = post(
            client, NODE_C + "/edgek/proof-local/receipt-packets/ingest", {"packet": receipt_packet},
        )
        tampered_packet = json.loads(json.dumps(receipt_packet))
        tampered_packet["manifest_hash"] = "sha256:" + "f" * 64
        tampered_response = client.post(
            NODE_C + "/edgek/proof-local/receipt-packets/ingest", json={"packet": tampered_packet},
        )
        if tampered_response.status_code != 400:
            raise RuntimeError("tampered receipt packet was not rejected before bundle transfer")
        advertisement = post(
            client,
            NODE_A + "/edgek/proof-local/advertisements/prepare",
            {
                "node_id": "commons-node-a",
                "contributor_id": "commons-node-a",
                "task_classes": [space.get("task_class")],
                "verifier_classes": ["schema_validation"],
                "load_bucket": "low",
                "rtt_bucket_ms": 10,
                "max_transfer_bytes": 6_000_000,
                "ttl_seconds": 300,
            },
        )
        advertisement_b = post(
            client, NODE_B + "/edgek/proof-local/advertisements/ingest", {"advertisement": advertisement},
        )
        advertisement_c = post(
            client, NODE_C + "/edgek/proof-local/advertisements/ingest", {"advertisement": advertisement},
        )
        route_b = post(
            client,
            NODE_B + "/edgek/proof-local/route",
            {
                "task_class": space.get("task_class"),
                "space_id": space_id,
                "manifest_hash": receipt_packet.get("manifest_hash"),
                "required_verifiers": ["schema_validation"],
                "max_lan_rtt_ms": 50,
                "max_transfer_bytes": 5_000_000,
            },
        )
        staged_manifest_b = post(
            client,
            NODE_B + "/edgek/proof-local/import-staged",
            {
                "base_url": NODE_A_INTERNAL,
                "space_id": space_id,
                "contributor_id": "commons-node-a",
                "stop_after": "manifest",
            },
        )
        if route_b.get("gate", {}).get("decision") != "quarantine_and_replay":
            raise RuntimeError("LAN proof route bypassed local replay quarantine")
        if int(staged_manifest_b.get("transfer", {}).get("bytes_avoided") or 0) <= 0:
            raise RuntimeError("manifest-first transfer did not measure avoided bundle bytes")
        staged_bundle_b = post(
            client,
            NODE_B + "/edgek/proof-local/import-staged",
            {
                "base_url": NODE_A_INTERNAL,
                "space_id": space_id,
                "contributor_id": "commons-node-a",
                "stop_after": "bundle",
                "approved": True,
                "dry_run": False,
            },
        )
        if staged_bundle_b.get("stage") != "bundle":
            raise RuntimeError("signed staged bundle did not reach local import verification")
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
        reproduction_id = str((reproduced.get("replay") or {}).get("reproduction_id") or "")
        if not reproduction_id:
            raise RuntimeError(
                "federated replay did not produce local evidence: "
                + json.dumps(reproduced, sort_keys=True)
            )
        route_b_verified = post(
            client,
            NODE_B + "/edgek/proof-local/route",
            {
                "task_class": space.get("task_class"),
                "space_id": space_id,
                "manifest_hash": receipt_packet.get("manifest_hash"),
                "required_verifiers": ["schema_validation"],
                "max_lan_rtt_ms": 50,
                "max_transfer_bytes": 5_000_000,
                "reproduction_id": reproduction_id,
            },
        )
        if route_b_verified.get("gate", {}).get("decision") != "trusted_lan_replay":
            raise RuntimeError(
                "verified local reproduction did not unlock the LAN proof route: "
                + json.dumps(route_b_verified, sort_keys=True)
            )
        if route_b_verified.get("gate", {}).get("provider_execution_requested") is not False:
            raise RuntimeError("verified LAN proof route did not displace provider execution")
        federation_state_b = get(client, NODE_B + "/edgek/federated-commons")
        report = {
            "beast_object_type": "proof_local_phase12_lab_receipt",
            "version": "1.0",
            "ok": True,
            "space_id": space_id,
            "nodes": {
                "node_a_spaces": registry_a.get("count"),
                "node_b_spaces_before": registry_b.get("count"),
                "node_b_allowlisted": allow.get("allowlisted"),
                "node_c_allowlisted": allow_c.get("allowlisted"),
            },
            "phase1": {
                "packet_id": receipt_packet.get("packet_id"),
                "manifest_hash": receipt_packet.get("manifest_hash"),
                "privacy_class": receipt_packet.get("privacy_class"),
                "declared_artifact_bytes": receipt_packet.get("declared_artifact_bytes"),
                "declared_bundle_bytes": receipt_packet.get("declared_bundle_bytes"),
                "node_b_receipt_accepted": receipt_ingest_b.get("accepted"),
                "node_c_receipt_accepted": receipt_ingest_c.get("accepted"),
                "tampered_packet_rejected": tampered_response.status_code == 400,
                "staged_stop": staged_manifest_b.get("stage"),
                "bytes_received": staged_manifest_b.get("transfer", {}).get("bytes_received"),
                "bytes_avoided": staged_manifest_b.get("transfer", {}).get("bytes_avoided"),
                "full_bundle_avoided": staged_manifest_b.get("transfer", {}).get("full_bundle_avoided"),
                "credit_eligible": staged_manifest_b.get("transfer", {}).get("credit_eligible"),
                "signed_bundle_imported_or_duplicate": bool(
                    staged_bundle_b.get("import", {}).get("imported")
                    or staged_bundle_b.get("import", {}).get("duplicate")
                ),
            },
            "phase2": {
                "advertisement_id": advertisement.get("advertisement_id"),
                "node_b_advertisement_accepted": advertisement_b.get("accepted"),
                "node_c_advertisement_accepted": advertisement_c.get("accepted"),
                "pre_replay_gate": route_b.get("gate", {}).get("decision"),
                "post_replay_gate": route_b_verified.get("gate", {}).get("decision"),
                "reproduction_id": reproduction_id,
                "reproduction_evidence_verified": route_b_verified.get("reproduction_evidence", {}).get("verified_locally"),
                "provider_execution_requested": route_b_verified.get("gate", {}).get("provider_execution_requested"),
                "fallback": route_b_verified.get("gate", {}).get("fallback"),
            },
            "legacy_federation": {
                "bundle_imported_or_duplicate": bool(bundle_import.get("imported") or bundle_import.get("duplicate")),
                "envelope_ingested": ingest.get("accepted"),
                "reproduced": bool((reproduced.get("replay") or {}).get("reproduced")),
            },
            "aggregate_transfer_metrics": federation_state_b.get("transfer_metrics") or {},
            "claim_boundary": "CPU Docker LAN evidence; no public internet, cross-OS, financial credit, or production traffic claim",
        }
        output = Path("benchmarks/results/proof_local_phase12_lab_latest.json")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2), file=sys.stderr)
        raise

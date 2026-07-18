#!/usr/bin/env python3
"""Register, probe and seed the provisioned remote Commons lab."""
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.kernel.commons.enterprise_plane import CommonsEnterprisePlane
from app.kernel.commons.discovery import CommonsDiscoveryCatalog
from app.kernel.commons.lattice_trust import CrystalLatticeTrustStore
from app.kernel.commons.remote_client import CommonsEgressGate, RemoteCommonsGateway, RemoteCommonsRegistry
from app.kernel.commons.remote_protocol import CommonsRequestSigner, sha256_bytes


async def bootstrap(root: Path, state_root: Path) -> dict:
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    env = manifest["gateway_env"]
    signer = CommonsRequestSigner.from_pem_file(
        env["BEAST_COMMONS_REMOTE_CLIENT_KEY"],
        node_id=env["BEAST_COMMONS_REMOTE_CLIENT_NODE_ID"],
        key_id=env["BEAST_COMMONS_REMOTE_CLIENT_KEY_ID"],
    )
    client_config_path = state_root / "commons-remote" / "client-config.json"
    client_config_path.parent.mkdir(parents=True, exist_ok=True)
    lattice_trust_path = root / "trust-commons" / "lattice-trust.yaml"
    lattice_trust = CrystalLatticeTrustStore.from_file(lattice_trust_path)
    client_config_path.write_text(json.dumps({
        "beast_object_type": "remote_commons_client_configuration",
        "version": "1.0",
        "private_key_path": env["BEAST_COMMONS_REMOTE_CLIENT_KEY"],
        "node_id": env["BEAST_COMMONS_REMOTE_CLIENT_NODE_ID"],
        "key_id": env["BEAST_COMMONS_REMOTE_CLIENT_KEY_ID"],
        "allowed_hosts": ["127.0.0.1"],
        "lattice_trust_store_path": str(lattice_trust_path),
        "development_loopback_only": True,
    }, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    gateway = RemoteCommonsGateway(
        RemoteCommonsRegistry(state_root / "commons-remote" / "nodes.sqlite3"),
        CommonsEgressGate(allowed_hosts=("127.0.0.1",), allow_insecure_loopback=True),
        signer=signer,
        lattice_trust_store=lattice_trust,
        discovery_catalog=CommonsDiscoveryCatalog(state_root / "commons-remote" / "discovery.sqlite3"),
    )
    discovery = await gateway.discover_origins(
        tuple(f"http://127.0.0.1:{node['port']}" for node in manifest["nodes"]),
        source="static_seed",
        auto_register=True,
    )
    refused = [row for row in discovery["results"] if not row.get("registered")]
    if refused:
        raise RuntimeError(f"lattice discovery admission failed: {refused}")
    probes = []
    for node in manifest["nodes"]:
        probe = await gateway.probe(node["node_id"])
        if not probe.get("ok"):
            raise RuntimeError(f"node probe failed: {probe}")
        probes.append(probe)

    node_id = manifest["nodes"][0]["node_id"]
    try:
        await gateway.create_bucket(node_id, {
            "owner": "edgek",
            "name": "verified-crystals",
            "visibility": "public",
            "description": "Proof-carrying reusable BEAST hypotheses; local reproduction required",
        })
    except RuntimeError as exc:
        if "(409)" not in str(exc):
            raise
    payload = json.dumps({
        "beast_object_type": "remote_commons_lab_seed",
        "version": "1.0",
        "claim": "transport and custody path operational",
        "authority": "remote_hypothesis",
        "maximum_authority": "verify_only",
        "execution_authority": False,
    }, sort_keys=True, separators=(",", ":")).encode("utf-8")
    blob = await gateway.put_blob(node_id, payload)
    committed = await gateway.commit_revision(
        node_id,
        owner="edgek",
        name="verified-crystals",
        revision="bootstrap-v1",
        replace=True,
        manifest={
            "authority": "remote_hypothesis",
            "maximum_authority": "verify_only",
            "files": [{"path": "proof/transport-custody.json", "digest": blob["digest"], "size": len(payload)}],
            "metadata": {"kind": "proof_carrying_crystal", "promotion_state": "quarantined"},
            "proof": {"local_reproduction_required": True, "advertised_claims_counted": 0},
        },
    )
    remote, blobs = await gateway.pull_revision(
        node_id, owner="edgek", name="verified-crystals", revision="bootstrap-v1",
    )
    local_plane = CommonsEnterprisePlane(state_root / "commons-enterprise")
    admission, evidence = local_plane.admit_remote_revision(
        node_id, remote, blobs, workspace_id="remote-commons-lab-bootstrap",
    )
    return {
        "status": "ready",
        "nodes": probes,
        "discovery": {
            "protocol": discovery["protocol"],
            "candidate_count": discovery["catalog"]["candidate_count"],
            "trusted_candidate_count": discovery["catalog"]["trusted_candidate_count"],
            "admissions": [row["admission"] for row in discovery["results"]],
        },
        "bucket_id": "edgek/verified-crystals",
        "revision": "bootstrap-v1",
        "manifest_digest": committed["manifest_digest"],
        "local_admission": admission,
        "evidence_node_id": evidence.node_id,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".beast/remote-commons-lab")
    parser.add_argument("--state-root", default=".beast")
    args = parser.parse_args()
    result = asyncio.run(bootstrap(Path(args.root).expanduser().resolve(), Path(args.state_root).expanduser().resolve()))
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

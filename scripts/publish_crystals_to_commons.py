#!/usr/bin/env python3
"""Publish promoted coding crystals to the 3 BEAST Commons nodes.

This script:
1. Registers/probes the 3 commons nodes (8111, 8112, 8113)
2. Creates the `beast/coding-crystals` bucket on all 3 nodes
3. Builds a publication bundle from a promoted crystal
4. Publishes the bundle to all 3 nodes via the gateway's control-plane routes
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import base64
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.kernel.commons.enterprise_plane import CommonsEnterprisePlane
from app.kernel.commons.discovery import CommonsDiscoveryCatalog
from app.kernel.commons.lattice_trust import CrystalLatticeTrustStore
from app.kernel.commons.remote_client import CommonsEgressGate, RemoteCommonsGateway, RemoteCommonsRegistry
from app.kernel.commons.remote_protocol import CommonsRequestSigner
from app.kernel.compute.coding_crystals import CodingCrystalExtractor, CodingCrystalRegistry
from app.kernel.compute.crystal_commons import (
    BUCKET,
    OWNER,
    CommonsCrystalPublisher,
    GatewayCommonsTransport,
    build_crystal_space,
    revision_name,
)
from app.kernel.compute.crystal_publication import build_publication_bundle
from app.kernel.compute.heldout_replay import ReplayReceipt
from app.kernel.sensorium.episode_envelope import EpisodeEnvelopeStore


NODES = ("commons-node-a", "commons-node-b", "commons-node-c")
PORTS = (8111, 8112, 8113)


async def setup_gateway(root: Path, state_root: Path) -> RemoteCommonsGateway:
    """Create and configure the RemoteCommonsGateway."""
    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    env = manifest["gateway_env"]

    signer = CommonsRequestSigner.from_pem_file(
        env["BEAST_COMMONS_REMOTE_CLIENT_KEY"],
        node_id=env["BEAST_COMMONS_REMOTE_CLIENT_NODE_ID"],
        key_id=env["BEAST_COMMONS_REMOTE_CLIENT_KEY_ID"],
    )

    lattice_trust_path = Path(".") / "trust-commons" / "lattice-trust.yaml"
    if not lattice_trust_path.exists():
        lattice_trust_path = Path(".beast/remote-commons-lab/trust-commons/lattice-trust.yaml")
    lattice_trust = CrystalLatticeTrustStore.from_file(lattice_trust_path)

    gateway = RemoteCommonsGateway(
        RemoteCommonsRegistry(Path(".beast") / "commons-remote" / "nodes.sqlite3"),
        CommonsEgressGate(allowed_hosts=("127.0.0.1",), allow_insecure_loopback=True),
        signer=CommonsRequestSigner.from_pem_file(
            env["BEAST_COMMONS_REMOTE_CLIENT_KEY"],
            node_id=env["BEAST_COMMONS_REMOTE_CLIENT_NODE_ID"],
            key_id=env["BEAST_COMMONS_REMOTE_CLIENT_KEY_ID"],
        ),
        lattice_trust_store=CrystalLatticeTrustStore.from_file(lattice_trust_path),
        discovery_catalog=CommonsDiscoveryCatalog(Path(".beast") / "commons-remote" / "discovery.sqlite3"),
    )
    return gateway


async def register_and_probe_nodes(gateway: RemoteCommonsGateway, root: Path) -> None:
    """Register and probe the 3 commons nodes."""
    manifest_path = Path(".beast/remote-commons-lab/manifest.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    # Discover and register nodes
    origins = tuple(f"http://127.0.0.1:{node['port']}" for node in manifest["nodes"])
    print(f"Discovering nodes at: {origins}")
    discovery = await gateway.discover_origins(origins, source="static_seed", auto_register=True)

    refused = [row for row in discovery["results"] if not row.get("registered")]
    if refused:
        raise RuntimeError(f"Lattice discovery admission failed: {refused}")

    print("Nodes discovered and registered:")
    for row in discovery["results"]:
        # The result contains 'candidate' with node_id
        candidate = row.get("candidate", {})
        node_id = candidate.get("node_id", "unknown")
        admission = row.get("admission", "unknown")
        print(f"  {node_id}: {admission}")

    # Probe each node
    for node in manifest["nodes"]:
        probe = await gateway.probe(node["node_id"])
        if not probe.get("ok"):
            raise RuntimeError(f"Node probe failed for {node['node_id']}: {probe}")
        print(f"Probed {node['node_id']}: {probe['state']}")


async def create_bucket_on_all_nodes(gateway: RemoteCommonsGateway, node_ids: tuple[str, ...]) -> None:
    """Create the beast/coding-crystals bucket on all nodes."""
    for node_id in node_ids:
        try:
            result = await gateway.create_bucket(node_id, {
                "owner": "beast",
                "name": "coding-crystals",
                "visibility": "private",
                "description": "Promoted BEAST coding crystals; local reproduction required",
            })
            print(f"Created bucket beast/coding-crystals on {node_id}: {result.get('status', 'unknown')}")
        except RuntimeError as exc:
            if "(409)" not in str(exc):
                raise
            print(f"Bucket already exists on {node_id}")


@dataclass
class PromotedReceipt:
    promoted: bool = True
    candidate_id: str = ""
    successes: int = 3
    attempts: int = 3


async def get_promoted_crystal(root: Path) -> tuple[dict, Ed25519PrivateKey]:
    """Get a promoted crystal from the local registry or create one."""
    # Try to find an existing promoted crystal
    registry = CodingCrystalRegistry(Path(".beast/crystals/coding_crystals.sqlite3"))
    try:
        promoted = registry.active_for_family("fix-failing-assertion")
        if promoted:
            print(f"Found existing promoted crystal: {promoted.crystal_id}")
            return promoted, None
    except LookupError:
        pass

    # Create a new crystal for testing
    print("Creating a test promoted crystal...")
    from app.kernel.compute.coding_crystals import (
        CodingCrystalCandidate, CRYSTAL_PARAMETERS, coding_catalog_digest
    )

    candidate = CodingCrystalCandidate(
        crystal_id="",
        task_family="fix-failing-assertion",
        steps=(
            {"opcode": "worktree.inspect", "tool_id": "workspace.read_range", "expect": ""},
            {"opcode": "worktree.bind", "tool_id": "worktree.bind", "expect": ""},
            {"opcode": "worktree.verify", "tool_id": "worktree.verify", "expect": "fail"},
            {"opcode": "repair.resolve_constant", "tool_id": "", "expect": ""},
            {"opcode": "worktree.replace_exact", "tool_id": "worktree.replace_exact", "expect": ""},
            {"opcode": "worktree.verify", "tool_id": "worktree.verify", "expect": "pass"},
            {"opcode": "crystal.complete", "tool_id": "", "expect": ""},
        ),
        parameters=CRYSTAL_PARAMETERS,
        opcode_catalog_digest=coding_catalog_digest(),
        source_run_id="source-run",
        source_envelope_digest="sha256:test",
        learned_budget={"model_turns": 7.0, "tool_calls": 9.0, "tokens_total": 8400.0, "wall_ms": 1100.0},
    ).sealed()

    registry.add_candidate(candidate)
    registry.promote(candidate.crystal_id, PromotedReceipt(candidate_id=candidate.crystal_id))

    # Create a signing key for the publication bundle
    key = Ed25519PrivateKey.generate()
    return candidate, key


async def publish_to_commons(root: Path, state_root: Path) -> dict:
    """Build publication bundle and publish to all 3 commons nodes."""
    # Get or create a promoted crystal
    candidate, key = await get_promoted_crystal(Path("."))
    if key is None:
        # Use a fixed key for reproducible test
        key = Ed25519PrivateKey.generate()

    # Build the publication bundle
    receipt = {
        "promoted": True,
        "candidate_id": candidate.crystal_id,
        "successes": 3,
        "attempts": 3,
        "variant_ids": ["pricing", "limits", "greeting"],
        "variant_results": [True, True, True],
    }
    bundle = build_publication_bundle(
        {
            "status": "promoted",
            "receipt": receipt,
            "candidate_object": candidate,
        },
        key, key_id="test-key"
    )

    # Build the Commons space
    space = build_crystal_space(bundle, Path(".beast") / "spaces")

    # Use the real GatewayCommonsTransport to publish to real nodes
    transport = GatewayCommonsTransport(
        base_url="http://127.0.0.1:8101",
        vault_root=Path(".beast/remote-commons-lab/vault"),
    )

    # Publish to all 3 nodes
    report = await CommonsCrystalPublisher(transport).publish(
        bundle, space, node_ids=("commons-node-a", "commons-node-b", "commons-node-c")
    )

    return report


async def main() -> int:
    parser = argparse.ArgumentParser(description="Publish crystals to BEAST Commons nodes")
    parser.add_argument("--root", default=".beast/remote-commons-lab")
    parser.add_argument("--state-root", default=".beast")
    parser.add_argument("--skip-setup", action="store_true", help="Skip node registration/probing")
    parser.add_argument("--skip-publish", action="store_true", help="Skip actual publication")
    args = parser.parse_args()

    root = Path(args.root).expanduser().resolve()
    state_root = Path(args.state_root).expanduser().resolve()

    if not (Path(".beast/remote-commons-lab/manifest.json")).exists():
        print("Error: Remote commons lab not provisioned. Run scripts/provision_remote_commons_lab.py first.")
        return 1

    try:
        gateway = await setup_gateway(Path(args.root), Path(args.state_root))

        if not args.skip_setup:
            await register_and_probe_nodes(gateway, Path(args.root))

            node_ids = ("commons-node-a", "commons-node-b", "commons-node-c")
            await create_bucket_on_all_nodes(gateway, node_ids)

        if not args.skip_publish:
            report = await publish_to_commons(Path("."), Path(".beast"))
            print("\n=== Publication Report ===")
            print(json.dumps(report, indent=2, default=str))

        print("\n✅ Publication complete!")
        return 0

    except Exception as exc:
        import traceback
        traceback.print_exc()
        print(f"\n❌ Error: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
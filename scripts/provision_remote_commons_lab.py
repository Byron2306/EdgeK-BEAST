#!/usr/bin/env python3
"""Provision unique node/client identities for the remote Commons lab."""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
from pathlib import Path
import stat

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
import yaml


def private_pem(key: Ed25519PrivateKey) -> bytes:
    return key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )


def public_pem(key: Ed25519PrivateKey) -> bytes:
    return key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )


def write_new(path: Path, payload: bytes, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise FileExistsError(f"refusing to replace existing identity material: {path}")
    path.write_bytes(payload)
    path.chmod(mode)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".beast/remote-commons-lab")
    parser.add_argument("--nodes", type=int, default=3)
    parser.add_argument("--base-port", type=int, default=8111)
    parser.add_argument("--client-node-id", default="beast-control-plane")
    args = parser.parse_args()
    root = Path(args.root).expanduser().resolve()
    if not 1 <= args.nodes <= 20:
        raise SystemExit("--nodes must be between 1 and 20")
    if not 1024 <= args.base_port <= 65535 - args.nodes:
        raise SystemExit("--base-port is outside the non-privileged TCP range")
    root.mkdir(parents=True, exist_ok=True)
    client_key = Ed25519PrivateKey.generate()
    client_dir = root / "control-plane"
    write_new(client_dir / "client.pem", private_pem(client_key), stat.S_IRUSR | stat.S_IWUSR)
    write_new(client_dir / "client.pub.pem", public_pem(client_key), stat.S_IRUSR | stat.S_IWUSR)
    client_record = {
        "node_id": args.client_node_id,
        "key_id": "beast-commons-client-v1",
        "public_key_path": "client.pub.pem",
        "scopes": ["bucket:read", "bucket:write", "blob:write"],
    }
    nodes = []
    for index in range(args.nodes):
        node_id = f"commons-node-{chr(ord('a') + index)}"
        node_dir = root / node_id
        key = Ed25519PrivateKey.generate()
        write_new(node_dir / "node.pem", private_pem(key), stat.S_IRUSR | stat.S_IWUSR)
        # Trust paths are deliberately node-local; the private client key is never mounted.
        write_new(node_dir / "client.pub.pem", public_pem(client_key), stat.S_IRUSR | stat.S_IWUSR)
        (node_dir / "clients.yaml").write_text(
            yaml.safe_dump({"clients": [{**client_record, "public_key_path": "client.pub.pem"}]}, sort_keys=False),
            encoding="utf-8",
        )
        raw_public = key.public_key().public_bytes_raw()
        node_pin = base64.b64encode(raw_public).decode("ascii")
        (node_dir / "node-registration.json").write_text(
            json.dumps(
                {
                    "node_id": node_id,
                    "endpoint": f"http://127.0.0.1:{args.base_port + index}",
                    "node_public_key": node_pin,
                    "expected_workload_digest": "",
                    "require_arda": False,
                    "trust_policy": "lattice",
                    "expected_policy_generation": "",
                    "development_note": "Run scripts/attest_remote_commons_lab.py before admission; ARDA is optional additive substrate evidence.",
                },
                indent=2,
                sort_keys=True,
            ) + "\n",
            encoding="utf-8",
        )
        nodes.append({"node_id": node_id, "public_key": node_pin, "port": args.base_port + index})
    gateway_env = {
        "BEAST_COMMONS_REMOTE_CLIENT_KEY": str(client_dir / "client.pem"),
        "BEAST_COMMONS_REMOTE_CLIENT_NODE_ID": args.client_node_id,
        "BEAST_COMMONS_REMOTE_CLIENT_KEY_ID": "beast-commons-client-v1",
        "BEAST_COMMONS_TRUST_STORE": str(root / "trust-commons" / "commons-trust.yaml"),
        "BEAST_COMMONS_LATTICE_TRUST_STORE": str(root / "trust-commons" / "lattice-trust.yaml"),
        "BEAST_COMMONS_REMOTE_ALLOWED_HOSTS": "127.0.0.1",
        "BEAST_COMMONS_REMOTE_ALLOW_HTTP_LOOPBACK": "1",
    }
    (root / "gateway.env").write_text(
        "\n".join(f"{key}={value}" for key, value in gateway_env.items()) + "\n",
        encoding="utf-8",
    )
    manifest = {
        "beast_object_type": "remote_commons_lab_provisioning",
        "version": "1.0",
        "root": str(root),
        "client_public_key_sha256": "sha256:" + hashlib.sha256(public_pem(client_key)).hexdigest(),
        "nodes": nodes,
        "gateway_env": gateway_env,
    }
    (root / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

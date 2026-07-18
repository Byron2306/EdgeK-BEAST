#!/usr/bin/env python3
"""Bind provisioned Commons lab identities to the verified crystal lattice."""
from __future__ import annotations

import argparse
import base64
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
import yaml

from app.kernel.commons.lattice_trust import CrystalLatticeAttestationIssuer
from app.kernel.commons.remote_protocol import sha256_bytes
from app.kernel.security.crystal_lattice_ledger import CrystalLatticeLedger


def _private_pem(key: Ed25519PrivateKey) -> bytes:
    return key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )


def _public_pem(key: Ed25519PrivateKey) -> bytes:
    return key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )


def _authority_key(root: Path) -> Ed25519PrivateKey:
    path = root / "lattice-authority.pem"
    if path.exists():
        key = serialization.load_pem_private_key(path.read_bytes(), password=None)
        if not isinstance(key, Ed25519PrivateKey):
            raise ValueError("existing lattice authority is not an Ed25519 key")
        return key
    key = Ed25519PrivateKey.generate()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_private_pem(key))
    path.chmod(0o600)
    return key


def attest(root: Path, *, lattice_root: Path, ttl_seconds: int) -> dict:
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    verification = CrystalLatticeLedger(lattice_root).verify().to_dict()
    if not verification["valid"] or int(verification["checkpoint_count"]) <= 0:
        raise PermissionError("a valid non-empty crystal lattice ledger is required")

    authority_dir = root / "trust-commons"
    key = _authority_key(authority_dir)
    public_path = authority_dir / "lattice-authority.pub.pem"
    public_path.write_bytes(_public_pem(key))
    public_path.chmod(0o644)
    authority = "edgek-crystal-compute-lattice"
    key_id = "edgek-lattice-lab-v1"
    policy_generation = "crystal-lattice:commons-lab-v1"
    issuer = CrystalLatticeAttestationIssuer(
        key, authority=authority, key_id=key_id, policy_generation=policy_generation,
    )
    workload_digest = sha256_bytes((PROJECT_ROOT / "app" / "commons_node_main.py").read_bytes())
    attestations = []
    for node in manifest["nodes"]:
        node_dir = root / str(node["node_id"])
        registration_path = node_dir / "node-registration.json"
        registration = json.loads(registration_path.read_text(encoding="utf-8"))
        subject = {
            "node_id": registration["node_id"],
            "workload_digest": workload_digest,
            "node_public_key": registration["node_public_key"],
            "protocol": "beast-commons-http-signature-v1",
            "capabilities": [
                "bucket_registry", "immutable_blobs", "signed_revisions", "replay_resistant_requests",
            ],
            "maximum_authority": "verify_only",
        }
        evidence = issuer.issue(
            subject=subject,
            lattice_verification=verification,
            ttl_seconds=ttl_seconds,
        )
        (node_dir / "trust-evidence.json").write_text(
            json.dumps({"trust_evidence": [evidence]}, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        registration.update({
            "expected_workload_digest": workload_digest,
            "require_arda": False,
            "trust_policy": "lattice",
            "expected_policy_generation": "",
            "trust_note": "Native crystal-lattice trust; ARDA hardware appraisal is optional additive evidence.",
        })
        registration_path.write_text(json.dumps(registration, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        attestations.append({
            "node_id": registration["node_id"],
            "attestation_id": evidence["attestation_id"],
            "subject_digest": evidence["subject_digest"],
        })

    trust_path = authority_dir / "lattice-trust.yaml"
    trust_path.write_text(yaml.safe_dump({
        "beast_object_type": "crystal_lattice_trust_store",
        "version": "1.0",
        "lattice_authorities": [{
            "authority": authority,
            "key_id": key_id,
            "public_key_path": public_path.name,
            "policy_generations": [policy_generation],
            "accepted_lattice_heads": [verification["head_hash"]],
            "minimum_checkpoint_count": verification["checkpoint_count"],
        }],
    }, sort_keys=False), encoding="utf-8")
    result = {
        "status": "lattice_attested",
        "authority": authority,
        "trust_store_path": str(trust_path),
        "lattice": verification,
        "nodes": attestations,
    }
    (authority_dir / "attestation-manifest.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8",
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".beast/remote-commons-lab")
    parser.add_argument("--lattice-root", default="benchmarks/results/crystal_lattice_ledger")
    parser.add_argument("--ttl-seconds", type=int, default=30 * 24 * 60 * 60)
    args = parser.parse_args()
    if args.ttl_seconds < 300:
        raise SystemExit("--ttl-seconds must be at least 300")
    result = attest(
        Path(args.root).expanduser().resolve(),
        lattice_root=Path(args.lattice_root).expanduser().resolve(),
        ttl_seconds=args.ttl_seconds,
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

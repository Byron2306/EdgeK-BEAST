#!/usr/bin/env python3
"""Deploy the bounded DIO semantic witness as a Hugging Face Docker Space.

The Space gets a persistent Ed25519 key through a Hub secret.  The private key
is never uploaded with the source snapshot; only its public fingerprint can be
counted by a DIO admission record.
"""
from __future__ import annotations

import argparse
import base64
from dataclasses import asdict
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from huggingface_hub import HfApi

from app.kernel.compute.deterministic_intelligence import sha256_bytes, sha256_digest, utc_now_iso
from app.kernel.dai.dio_distributed_quorum import public_key_b64, public_key_fingerprint


DEFAULT_SPACE_NAME = "dio-phase2-semantic-witness"
TOKEN_NAMES = ("HF_TOKEN", "HUGGINGFACE_API_KEY", "HUGGINGFACEHUB_API_TOKEN")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-id", default="", help="Space repo, default: authenticated-user/dio-phase2-semantic-witness")
    parser.add_argument("--private", action="store_true", help="create the Space privately")
    parser.add_argument("--governance-epoch", default="dio-phase5-online-001")
    parser.add_argument("--out", type=Path, default=Path("evidence/dai-diode/phase2.1-hf-witness/dio_hf_space_deployment.json"))
    args = parser.parse_args()
    result = deploy(repo_id=args.repo_id, private=args.private, governance_epoch=args.governance_epoch)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def deploy(*, repo_id: str = "", private: bool = False, governance_epoch: str = "dio-phase5-online-001") -> dict[str, Any]:
    token = _load_hf_token()
    api = HfApi(token=token)
    account = api.whoami(token=token)
    owner = str(account["name"])
    resolved_repo = repo_id or f"{owner}/{DEFAULT_SPACE_NAME}"
    key, key_path = _load_or_create_key()
    public_key = public_key_b64(key.public_key())
    fingerprint = public_key_fingerprint(public_key)
    source_manifest = _source_manifest()
    verifier_commit = sha256_digest({"dio_hf_phase4_source_manifest": source_manifest})
    container_manifest = sha256_digest({"witness_source_manifest": source_manifest, "dockerfile": "deploy/dio-hf-witness/Dockerfile"})

    api.create_repo(repo_id=resolved_repo, repo_type="space", space_sdk="docker", private=private, exist_ok=True, token=token)
    api.add_space_secret(resolved_repo, "BEAST_DIO_WITNESS_PRIVATE_KEY_B64", base64.b64encode(key.private_bytes_raw()).decode("ascii"), description="Persistent Ed25519 signing identity for the bounded DIO witness", token=token)
    variables = {
        "BEAST_DIO_WITNESS_NODE_ID": "dio:hf:semantic-witness-01",
        "BEAST_DIO_WITNESS_ROLE": "semantic_witness",
        "BEAST_DIO_WITNESS_VERIFIER_COMMIT": verifier_commit,
        "BEAST_DIO_WITNESS_CONTAINER_MANIFEST": container_manifest,
        "BEAST_DIO_WITNESS_OPERATOR_ROOT": "hf:Byron230686",
        "BEAST_DIO_WITNESS_GOVERNANCE_EPOCH": governance_epoch,
    }
    for name, value in variables.items():
        api.add_space_variable(resolved_repo, name, value, token=token)

    with tempfile.TemporaryDirectory(prefix="dio-hf-witness-") as temp_dir:
        stage = Path(temp_dir)
        _stage_source(stage)
        commit = api.upload_folder(
            repo_id=resolved_repo,
            repo_type="space",
            folder_path=stage,
            commit_message="Deploy bounded DIO Phase 4 Commons semantic witness",
            token=token,
        )
    body = {
        "beast_object_type": "dio_hf_witness_space_deployment",
        "repo_id": resolved_repo,
        "space_url": f"https://huggingface.co/spaces/{resolved_repo}",
        "node_id": variables["BEAST_DIO_WITNESS_NODE_ID"],
        "role": variables["BEAST_DIO_WITNESS_ROLE"],
        "runtime_platform": "huggingface-docker-space",
        "infrastructure_provider": "huggingface",
        "maximum_authority": "remote_signed_software_witness_only",
        "production_authority_allowed": False,
        "execution_authority_allowed": False,
        "public_signing_key": public_key,
        "key_fingerprint": fingerprint,
        "local_private_key_path": str(key_path),
        "verifier_commit": verifier_commit,
        "container_manifest": container_manifest,
        "operator_root": variables["BEAST_DIO_WITNESS_OPERATOR_ROOT"],
        "governance_epoch": variables["BEAST_DIO_WITNESS_GOVERNANCE_EPOCH"],
        "source_manifest": source_manifest,
        "hub_commit": getattr(commit, "oid", ""),
        "deployed_at": utc_now_iso(),
    }
    body["deployment_digest"] = sha256_digest(body)
    return body


def _load_hf_token() -> str:
    for name in TOKEN_NAMES:
        value = os.environ.get(name, "").strip()
        if value:
            return value
    for path in (ROOT / ".beast/provider_secrets.env", ROOT / ".beast/vector.env"):
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            name, value = stripped.split("=", 1)
            if name.strip() in TOKEN_NAMES and value.strip().strip('"').strip("'"):
                return value.strip().strip('"').strip("'")
    raise RuntimeError("No Hugging Face token found. Set HF_TOKEN or add it to .beast/provider_secrets.env")


def _load_or_create_key() -> tuple[Ed25519PrivateKey, Path]:
    key_path = ROOT / ".beast/dio-hf-witness/semantic-witness-01.ed25519.b64"
    if key_path.exists():
        raw = base64.b64decode(key_path.read_text(encoding="ascii").strip(), validate=True)
        return Ed25519PrivateKey.from_private_bytes(raw), key_path
    key_path.parent.mkdir(parents=True, exist_ok=True)
    key = Ed25519PrivateKey.generate()
    encoded = base64.b64encode(key.private_bytes_raw()).decode("ascii")
    key_path.write_text(encoded + "\n", encoding="ascii")
    key_path.chmod(0o600)
    return key, key_path


def _stage_source(stage: Path) -> None:
    shutil.copy2(ROOT / "deploy/dio-hf-witness/Dockerfile", stage / "Dockerfile")
    shutil.copy2(ROOT / "deploy/dio-hf-witness/README.md", stage / "README.md")
    shutil.copy2(ROOT / "deploy/dio-hf-witness/requirements.dio-hf-witness.txt", stage / "requirements.dio-hf-witness.txt")
    for relative in (
        "app/__init__.py",
        "app/dio_hf_witness_main.py",
        "app/kernel/__init__.py",
        "app/kernel/compute/__init__.py",
        "app/kernel/compute/deterministic_intelligence.py",
        "app/kernel/dai/__init__.py",
        "app/kernel/dai/dio_distributed_quorum.py",
        "app/kernel/dai/dio_commons_online.py",
        "app/kernel/dai/dio_remote_witness_packet.py",
    ):
        destination = stage / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, destination)


def _source_manifest() -> dict[str, str]:
    files = (
        "deploy/dio-hf-witness/Dockerfile",
        "deploy/dio-hf-witness/README.md",
        "deploy/dio-hf-witness/requirements.dio-hf-witness.txt",
        "app/__init__.py",
        "app/dio_hf_witness_main.py",
        "app/kernel/__init__.py",
        "app/kernel/compute/__init__.py",
        "app/kernel/compute/deterministic_intelligence.py",
        "app/kernel/dai/__init__.py",
        "app/kernel/dai/dio_distributed_quorum.py",
        "app/kernel/dai/dio_commons_online.py",
        "app/kernel/dai/dio_remote_witness_packet.py",
    )
    return {relative: sha256_bytes((ROOT / relative).read_bytes()) for relative in files}


if __name__ == "__main__":
    raise SystemExit(main())

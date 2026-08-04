#!/usr/bin/env python3
"""Run a live Commons ML-KEM-768 key-agreement gauntlet.

Receipts store public material, ciphertext digests, transcript digests, and
confirmation digests.  They never store shared secrets.
"""
from __future__ import annotations

import argparse
import base64
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import httpx

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.kernel.commons.ml_kem import (
    ML_KEM_ALGORITHM,
    challenge_confirmation_body,
    confirmation_mac,
    encapsulate,
)
from app.kernel.commons.remote_protocol import canonical_json, sha256_bytes
from app.kernel.compute.residual_contracts import sha256_digest, utc_now_iso


DEFAULT_NODES = (
    "http://127.0.0.1:8111",
    "http://127.0.0.1:8112",
    "http://127.0.0.1:8113",
)


def run_commons_ml_kem_gauntlet(
    *,
    nodes: tuple[str, ...] = DEFAULT_NODES,
    run_id: str | None = None,
    evidence_root: str | Path = REPO_ROOT / "evidence" / "commons-ml-kem",
    timeout_seconds: float = 10.0,
    oqs_helper_container: str = "",
) -> dict[str, Any]:
    evidence = Path(evidence_root)
    evidence.mkdir(parents=True, exist_ok=True)
    run_id = run_id or utc_now_iso().replace(":", "").replace("+", "z")
    node_results = []
    failures = []
    with httpx.Client(timeout=timeout_seconds) as client:
        for index, base_url in enumerate(nodes):
            try:
                node_results.append(_probe_node(
                    client,
                    base_url.rstrip("/"),
                    index=index,
                    oqs_helper_container=oqs_helper_container,
                ))
            except Exception as exc:
                failures.append({
                    "base_url": base_url,
                    "failure": f"{type(exc).__name__}: {exc}",
                })
    pairwise = _pairwise_matrix(node_results)
    receipt = {
        "beast_object_type": "commons_ml_kem_gauntlet_receipt",
        "version": "1.0",
        "run_id": run_id,
        "observed_at": utc_now_iso(),
        "algorithm": ML_KEM_ALGORITHM,
        "node_count": len(node_results),
        "nodes_requested": list(nodes),
        "nodes": node_results,
        "pairwise_transcript_matrix": pairwise,
        "failure_count": len(failures),
        "failures": failures,
        "secret_storage_policy": "shared_secret_bytes_never_serialized",
        "status": "passed" if len(node_results) == len(nodes) and not failures and all(item["confirmed"] for item in node_results) else "failed",
    }
    receipt["receipt_digest"] = sha256_digest(receipt)
    json_path = evidence / f"{run_id}.json"
    md_path = evidence / f"{run_id}.md"
    json_path.write_text(json.dumps(receipt, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(_markdown(receipt), encoding="utf-8")
    (evidence / "latest.json").write_text(json.dumps(receipt, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    (evidence / "latest.md").write_text(_markdown(receipt), encoding="utf-8")
    receipt["evidence_paths"] = {
        "json": str(json_path),
        "markdown": str(md_path),
        "latest_json": str(evidence / "latest.json"),
        "latest_markdown": str(evidence / "latest.md"),
    }
    return receipt


def _probe_node(
    client: httpx.Client,
    base_url: str,
    *,
    index: int,
    oqs_helper_container: str = "",
) -> dict[str, Any]:
    health = client.get(base_url + "/health")
    health.raise_for_status()
    health_payload = health.json()
    key_response = client.get(base_url + "/v1/ml-kem/key")
    key_response.raise_for_status()
    key_payload = key_response.json()
    document = dict(key_payload["document"])
    if document["algorithm"] != ML_KEM_ALGORITHM:
        raise RuntimeError("unexpected ML-KEM algorithm: " + str(document["algorithm"]))
    public_key = base64.b64decode(document["public_key_b64"], validate=True)
    if sha256_bytes(public_key) != document["public_key_digest"]:
        raise RuntimeError("ML-KEM public key digest mismatch")
    nonce = f"commons-ml-kem-gauntlet:{index}:{sha256_bytes(public_key).removeprefix('sha256:')[:24]}"
    transcript = {
        "node_id": document["node_id"],
        "base_url": base_url,
        "algorithm": document["algorithm"],
        "public_key_digest": document["public_key_digest"],
        "health_digest": sha256_digest(health_payload),
    }
    transcript_digest = sha256_bytes(canonical_json(transcript))
    if oqs_helper_container:
        helper = _encapsulate_with_docker_helper(
            oqs_helper_container,
            node_id=document["node_id"],
            algorithm=document["algorithm"],
            public_key_b64=document["public_key_b64"],
            public_key_digest=document["public_key_digest"],
            challenge_nonce=nonce,
            transcript_digest=transcript_digest,
        )
        ciphertext_b64 = helper["ciphertext_b64"]
        ciphertext_digest = helper["ciphertext_digest"]
        ciphertext_size_bytes = int(helper["ciphertext_size_bytes"])
        shared_secret_size_bytes = int(helper["shared_secret_size_bytes"])
        expected_mac = helper["expected_confirmation_mac_b64"]
    else:
        ciphertext, shared_secret = encapsulate(public_key, algorithm=document["algorithm"])
        ciphertext_b64 = base64.b64encode(ciphertext).decode("ascii")
        ciphertext_digest = sha256_bytes(ciphertext)
        ciphertext_size_bytes = len(ciphertext)
        shared_secret_size_bytes = len(shared_secret)
        body = challenge_confirmation_body(
            node_id=document["node_id"],
            algorithm=document["algorithm"],
            public_key_digest=document["public_key_digest"],
            ciphertext_digest=ciphertext_digest,
            challenge_nonce=nonce,
            transcript_digest=transcript_digest,
        )
        expected_mac = confirmation_mac(shared_secret, body)
    challenge = client.post(base_url + "/v1/ml-kem/challenge", json={
        "public_key_digest": document["public_key_digest"],
        "ciphertext_b64": ciphertext_b64,
        "challenge_nonce": nonce,
        "transcript_digest": transcript_digest,
    })
    challenge.raise_for_status()
    challenge_payload = challenge.json()
    confirmation = dict(challenge_payload["confirmation"])
    confirmed = confirmation.get("confirmation_mac_b64") == expected_mac
    return {
        "base_url": base_url,
        "node_id": str(health_payload.get("node_id") or document["node_id"]),
        "health_digest": sha256_digest(health_payload),
        "health_ok": health_payload.get("ok") is True,
        "algorithm": document["algorithm"],
        "public_key_digest": document["public_key_digest"],
        "public_key_document_digest": document["document_digest"],
        "public_key_signature_digest": sha256_digest(str(key_payload.get("node_signature") or "")),
        "ciphertext_digest": ciphertext_digest,
        "ciphertext_size_bytes": ciphertext_size_bytes,
        "shared_secret_size_bytes": shared_secret_size_bytes,
        "transcript_digest": transcript_digest,
        "challenge_confirmation_digest": challenge_payload["confirmation_digest"],
        "challenge_signature_digest": sha256_digest(str(challenge_payload.get("node_signature") or "")),
        "confirmed": confirmed,
        "secret_exported": False,
    }


def _encapsulate_with_docker_helper(
    container: str,
    *,
    node_id: str,
    algorithm: str,
    public_key_b64: str,
    public_key_digest: str,
    challenge_nonce: str,
    transcript_digest: str,
) -> dict[str, Any]:
    """Use a Commons container's liboqs install without serializing secrets."""
    helper_input = {
        "node_id": node_id,
        "algorithm": algorithm,
        "public_key_b64": public_key_b64,
        "public_key_digest": public_key_digest,
        "challenge_nonce": challenge_nonce,
        "transcript_digest": transcript_digest,
    }
    code = r'''
import base64, hashlib, hmac, json, sys
import oqs

def canonical_json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()

def sha256_bytes(value):
    return "sha256:" + hashlib.sha256(value).hexdigest()

payload = json.loads(sys.stdin.read())
public_key = base64.b64decode(payload["public_key_b64"], validate=True)
with oqs.KeyEncapsulation(payload["algorithm"]) as kem:
    ciphertext, shared_secret = kem.encap_secret(public_key)
ciphertext_digest = sha256_bytes(ciphertext)
body = {
    "beast_object_type": "commons_ml_kem_challenge_confirmation",
    "version": "1.0",
    "node_id": payload["node_id"],
    "algorithm": payload["algorithm"],
    "public_key_digest": payload["public_key_digest"],
    "ciphertext_digest": ciphertext_digest,
    "challenge_nonce": payload["challenge_nonce"],
    "transcript_digest": payload["transcript_digest"],
    "maximum_authority": "key_agreement_proof_only",
}
expected_mac = base64.b64encode(hmac.new(shared_secret, canonical_json(body), hashlib.sha256).digest()).decode("ascii")
print(json.dumps({
    "ciphertext_b64": base64.b64encode(ciphertext).decode("ascii"),
    "ciphertext_digest": ciphertext_digest,
    "ciphertext_size_bytes": len(ciphertext),
    "shared_secret_size_bytes": len(shared_secret),
    "expected_confirmation_mac_b64": expected_mac,
    "secret_exported": False,
}, sort_keys=True))
'''
    completed = subprocess.run(
        ["docker", "exec", "-i", container, "python", "-c", code],
        input=json.dumps(helper_input),
        text=True,
        capture_output=True,
        check=True,
    )
    for line in reversed(completed.stdout.splitlines()):
        line = line.strip()
        if line.startswith("{"):
            value = json.loads(line)
            if value.get("secret_exported") is not False:
                raise RuntimeError("OQS helper secret policy violation")
            return value
    raise RuntimeError("OQS helper did not return JSON")


def _pairwise_matrix(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for source in nodes:
        for target in nodes:
            if source["node_id"] == target["node_id"]:
                continue
            rows.append({
                "from_node_id": source["node_id"],
                "to_node_id": target["node_id"],
                "algorithm": ML_KEM_ALGORITHM,
                "source_health_digest": source["health_digest"],
                "target_public_key_digest": target["public_key_digest"],
                "pair_transcript_digest": sha256_digest({
                    "from": source["node_id"],
                    "to": target["node_id"],
                    "algorithm": ML_KEM_ALGORITHM,
                    "source_health_digest": source["health_digest"],
                    "target_public_key_digest": target["public_key_digest"],
                }),
            })
    return rows


def _markdown(receipt: dict[str, Any]) -> str:
    lines = [
        f"# Commons ML-KEM gauntlet — {receipt['run_id']}",
        "",
        f"- Status: `{receipt['status']}`",
        f"- Receipt digest: `{receipt['receipt_digest']}`",
        f"- Algorithm: `{receipt['algorithm']}`",
        f"- Nodes confirmed: {sum(1 for item in receipt['nodes'] if item['confirmed'])} / {len(receipt['nodes'])}",
        f"- Pairwise transcript edges: {len(receipt['pairwise_transcript_matrix'])}",
        f"- Secret policy: `{receipt['secret_storage_policy']}`",
        "",
    ]
    for node in receipt["nodes"]:
        lines.extend([
            f"## {node['node_id']}",
            "",
            f"- Base URL: `{node['base_url']}`",
            f"- Public key digest: `{node['public_key_digest']}`",
            f"- Ciphertext digest: `{node['ciphertext_digest']}`",
            f"- Confirmation digest: `{node['challenge_confirmation_digest']}`",
            f"- Confirmed: `{node['confirmed']}`",
            "",
        ])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--node", action="append", dest="nodes", help="Commons node base URL; repeatable")
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--evidence-root", default="evidence/commons-ml-kem")
    parser.add_argument(
        "--oqs-helper-container",
        default="",
        help="Optional Commons container name used only for ML-KEM encapsulation; shared secrets are not printed or written.",
    )
    args = parser.parse_args()
    receipt = run_commons_ml_kem_gauntlet(
        nodes=tuple(args.nodes or DEFAULT_NODES),
        run_id=args.run_id,
        evidence_root=args.evidence_root,
        oqs_helper_container=args.oqs_helper_container,
    )
    print(json.dumps({
        "status": receipt["status"],
        "receipt_digest": receipt["receipt_digest"],
        "node_count": receipt["node_count"],
        "evidence_paths": receipt["evidence_paths"],
    }, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()

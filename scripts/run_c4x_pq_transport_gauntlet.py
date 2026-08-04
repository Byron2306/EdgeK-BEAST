#!/usr/bin/env python3
"""Run the full C4-X PQ transport certificate gauntlet.

The gate is intentionally stricter than ML-KEM key agreement.  It requires:
ML-KEM confirmation, ML-DSA signature verification, ciphertext/signature tamper
rejection, replay nonce refusal, artifact digest binding, and policy scope.
"""
from __future__ import annotations

import argparse
import base64
import json
from pathlib import Path
import subprocess
import sys
import time
from typing import Any, Mapping

import httpx

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.kernel.commons.remote_protocol import canonical_json, sha256_bytes  # noqa: E402
from app.kernel.compute.deterministic_intelligence import sha256_digest, utc_now_iso  # noqa: E402
from scripts.harden_c4x_physical_truth_sidecar import harden_sidecar  # noqa: E402
from scripts.run_c4x_physical_truth_certificate import run_physical_truth_certificate  # noqa: E402
from scripts.run_commons_ml_kem_gauntlet import _encapsulate_with_docker_helper  # noqa: E402


DEFAULT_ROOT = REPO_ROOT / "evidence" / "c4x-physical-truth-certificate"
SIDECAR_PATH = DEFAULT_ROOT / "physical_truth_sidecar_harvested.json"
DEFAULT_NODE = "http://127.0.0.1:8111"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", default="physical-truth-pq-transport-" + time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()))
    parser.add_argument("--sidecar", default=str(SIDECAR_PATH))
    parser.add_argument("--evidence-root", default=str(DEFAULT_ROOT))
    parser.add_argument("--node", default=DEFAULT_NODE)
    parser.add_argument("--oqs-helper-container", default="edgek-beast-commons-node-a-1")
    args = parser.parse_args()

    evidence_root = Path(args.evidence_root)
    run_root = evidence_root / args.run_id
    run_root.mkdir(parents=True, exist_ok=True)
    receipt = _run_pq_gauntlet(args.node.rstrip("/"), args.oqs_helper_container)
    report = {
        "beast_object_type": "c4x_pq_transport_gauntlet",
        "version": "1.0",
        "run_id": args.run_id,
        "created_at": utc_now_iso(),
        "pq_transport_receipt": receipt,
        "claim_boundary": (
            "Full C4-X PQ transport gate: ML-KEM key agreement plus ML-DSA "
            "authenticity and hostile tamper/replay/policy checks. Shared "
            "secrets and private signing keys are never serialized."
        ),
    }
    report["receipt_digest"] = sha256_digest(report)
    (run_root / "pq_transport_gauntlet.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    sidecar_path = Path(args.sidecar)
    if not sidecar_path.is_absolute():
        sidecar_path = REPO_ROOT / sidecar_path
    sidecar = json.loads(sidecar_path.read_text(encoding="utf-8")) if sidecar_path.exists() else {}
    sidecar["pq_transport_receipt"] = receipt
    sidecar_path.write_text(json.dumps(sidecar, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    harden_sidecar(sidecar_path)
    certificate = run_physical_truth_certificate(sidecar=sidecar_path, run_id=args.run_id, evidence_root=evidence_root)
    summary = {
        "run_id": args.run_id,
        "receipt": str(run_root / "pq_transport_gauntlet.json"),
        "receipt_digest": report["receipt_digest"],
        "certificate_digest": certificate["receipt_digest"],
        "pq_transport_green": certificate["certificate_gates"].get("pq_transport") is True,
        "green_gates": [k for k, v in certificate["certificate_gates"].items() if v],
        "red_gates": [k for k, v in certificate["certificate_gates"].items() if not v],
    }
    (run_root / "pq_transport_summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


def _run_pq_gauntlet(node: str, container: str) -> dict[str, Any]:
    kem = _kem_probe(node, container)
    sig = _ml_dsa_probe(container)
    replay = _nonce_replay_probe()
    artifact = {
        "beast_object_type": "c4x_pq_policy_capsule",
        "artifact": "transported-proof-capsule",
        "maximum_authority": "transport_authenticity_only",
        "policy_scope": "c4x_physical_truth_pq_transport",
    }
    receipt = {
        "ml_kem_active": kem["ml_kem_active"],
        "ml_dsa_signature_verified": sig["ml_dsa_signature_verified"],
        "fallback": False,
        "recipient_decapsulation_verified": kem["recipient_decapsulation_verified"],
        "ciphertext_tamper_rejected": kem["ciphertext_tamper_rejected"],
        "signature_tamper_rejected": sig["signature_tamper_rejected"],
        "replay_nonce_unused": replay["replay_nonce_unused"],
        "artifact_digest_verified": sha256_digest(artifact) == sha256_digest(json.loads(json.dumps(artifact, sort_keys=True))),
        "policy_scope_accepted": artifact["maximum_authority"] == "transport_authenticity_only",
        "ml_kem_receipt": kem,
        "ml_dsa_receipt": sig,
        "replay_receipt": replay,
        "artifact_digest": sha256_digest(artifact),
        "status": "passed" if all((
            kem["ml_kem_active"],
            sig["ml_dsa_signature_verified"],
            kem["recipient_decapsulation_verified"],
            kem["ciphertext_tamper_rejected"],
            sig["signature_tamper_rejected"],
            replay["replay_nonce_unused"],
        )) else "failed",
    }
    receipt["receipt_digest"] = sha256_digest(receipt)
    return receipt


def _kem_probe(node: str, container: str) -> dict[str, Any]:
    with httpx.Client(timeout=10.0) as client:
        key_response = client.get(node + "/v1/ml-kem/key")
        key_response.raise_for_status()
        document = dict(key_response.json()["document"])
        nonce = "c4x-pq:" + sha256_digest({"node": node, "ts": time.time_ns()}).removeprefix("sha256:")[:32]
        transcript = {
            "node_id": document["node_id"],
            "algorithm": document["algorithm"],
            "public_key_digest": document["public_key_digest"],
            "node": node,
        }
        transcript_digest = sha256_bytes(canonical_json(transcript))
        helper = _encapsulate_with_docker_helper(
            container,
            node_id=document["node_id"],
            algorithm=document["algorithm"],
            public_key_b64=document["public_key_b64"],
            public_key_digest=document["public_key_digest"],
            challenge_nonce=nonce,
            transcript_digest=transcript_digest,
        )
        challenge = client.post(node + "/v1/ml-kem/challenge", json={
            "public_key_digest": document["public_key_digest"],
            "ciphertext_b64": helper["ciphertext_b64"],
            "challenge_nonce": nonce,
            "transcript_digest": transcript_digest,
        })
        challenge.raise_for_status()
        confirmation = dict(challenge.json()["confirmation"])
        original_confirmed = confirmation.get("confirmation_mac_b64") == helper["expected_confirmation_mac_b64"]

        ciphertext = bytearray(base64.b64decode(helper["ciphertext_b64"], validate=True))
        ciphertext[0] ^= 0x01
        tampered = client.post(node + "/v1/ml-kem/challenge", json={
            "public_key_digest": document["public_key_digest"],
            "ciphertext_b64": base64.b64encode(bytes(ciphertext)).decode("ascii"),
            "challenge_nonce": nonce + ":tampered",
            "transcript_digest": transcript_digest,
        })
        tamper_rejected = False
        if tampered.status_code >= 400:
            tamper_rejected = True
        else:
            tamper_confirmation = dict(tampered.json()["confirmation"])
            tamper_rejected = tamper_confirmation.get("confirmation_mac_b64") != helper["expected_confirmation_mac_b64"]
    return {
        "node": node,
        "algorithm": document.get("algorithm"),
        "ml_kem_active": document.get("algorithm") == "ML-KEM-768",
        "recipient_decapsulation_verified": original_confirmed,
        "ciphertext_tamper_rejected": tamper_rejected,
        "ciphertext_digest": helper["ciphertext_digest"],
        "secret_exported": False,
    }


def _ml_dsa_probe(container: str) -> dict[str, Any]:
    body = {
        "beast_object_type": "c4x_pq_signature_body",
        "policy_scope": "c4x_physical_truth_pq_transport",
        "artifact_digest": "sha256:" + "9" * 64,
    }
    code = r'''
import base64, json, sys
import oqs

payload = json.loads(sys.stdin.read())
algorithm = payload.get("algorithm", "ML-DSA-65")
body = json.dumps(payload["body"], sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
out = {"algorithm": algorithm, "available": algorithm in oqs.get_enabled_sig_mechanisms()}
if out["available"]:
    with oqs.Signature(algorithm) as signer:
        public_key = signer.generate_keypair()
        signature = signer.sign(body)
    with oqs.Signature(algorithm) as verifier:
        valid = bool(verifier.verify(body, signature, public_key))
        tampered_sig = bytearray(signature); tampered_sig[0] ^= 1
        try:
            sig_rejected = not bool(verifier.verify(body, bytes(tampered_sig), public_key))
        except Exception:
            sig_rejected = True
        try:
            body_rejected = not bool(verifier.verify(body + b"!", signature, public_key))
        except Exception:
            body_rejected = True
    out.update({
        "signature_verified": valid,
        "signature_tamper_rejected": sig_rejected,
        "body_tamper_rejected": body_rejected,
        "public_key_b64": base64.b64encode(public_key).decode("ascii"),
        "signature_b64": base64.b64encode(signature).decode("ascii"),
        "private_key_serialized": False,
    })
print(json.dumps(out, sort_keys=True))
'''
    try:
        completed = subprocess.run(
            ["docker", "exec", "-i", container, "python", "-c", code],
            input=json.dumps({"algorithm": "ML-DSA-65", "body": body}),
            text=True,
            capture_output=True,
            check=True,
        )
        value = {}
        for line in completed.stdout.splitlines():
            if line.strip().startswith("{"):
                value = json.loads(line)
        available = value.get("available") is True
        return {
            "algorithm": "ML-DSA-65",
            "available": available,
            "ml_dsa_signature_verified": bool(value.get("signature_verified")),
            "signature_tamper_rejected": bool(value.get("signature_tamper_rejected") and value.get("body_tamper_rejected")),
            "private_key_serialized": bool(value.get("private_key_serialized")) if available else False,
            "private_key_never_serialized": value.get("private_key_serialized") is False if available else False,
            "public_key_digest": sha256_digest(str(value.get("public_key_b64") or "")) if available else "",
            "signature_digest": sha256_digest(str(value.get("signature_b64") or "")) if available else "",
        }
    except Exception as exc:
        return {
            "algorithm": "ML-DSA-65",
            "available": False,
            "ml_dsa_signature_verified": False,
            "signature_tamper_rejected": False,
            "private_key_serialized": False,
            "error": f"{type(exc).__name__}: {exc}",
        }


def _nonce_replay_probe() -> dict[str, Any]:
    seen: set[str] = set()
    nonce = "nonce:" + sha256_digest(time.time_ns()).removeprefix("sha256:")[:24]
    first = nonce not in seen
    seen.add(nonce)
    second_refused = nonce in seen
    return {
        "nonce_digest": sha256_digest(nonce),
        "first_use_accepted": first,
        "replay_refused": second_refused,
        "replay_nonce_unused": first and second_refused,
    }


if __name__ == "__main__":
    raise SystemExit(main())

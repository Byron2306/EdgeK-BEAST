import base64
import copy
import json
import os
import shlex
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.kernel.commons.remote_protocol import canonical_json, sha256_bytes


def _document(*, expires_at: float | None = None) -> tuple[dict, Ed25519PrivateKey]:
    key = Ed25519PrivateKey.generate()
    public = base64.b64encode(key.public_key().public_bytes_raw()).decode("ascii")
    subject = {
        "node_id": "commons-node-a",
        "workload_digest": "sha256:" + "a" * 64,
        "node_public_key": public,
        "protocol": "beast-commons-http-signature-v1",
        "capabilities": [
            "bucket_registry",
            "immutable_blobs",
            "signed_revisions",
            "replay_resistant_requests",
        ],
        "maximum_authority": "verify_only",
    }
    subject_digest = sha256_bytes(canonical_json(subject))
    evidence = {
        "beast_object_type": "commons_crystal_lattice_attestation",
        "subject_node_id": "commons-node-a",
        "subject_digest": subject_digest,
        "issued_at": 1_700_000_000.0,
        "expires_at": expires_at if expires_at is not None else 2_000_000_000.0,
        "checkpoint_count": 18,
        "policy_generation": "crystal-lattice:commons-lab-v1",
    }
    descriptor = {
        "beast_object_type": "remote_commons_node_descriptor",
        "schema_version": "1.0",
        **subject,
        "attestation_subject_digest": subject_digest,
        "trust_evidence": [evidence],
        "storage": {"buckets": 0},
    }
    return {
        "descriptor": descriptor,
        "descriptor_digest": sha256_bytes(canonical_json(descriptor)),
        "signature_algorithm": "ed25519",
        "node_signature": base64.b64encode(key.sign(canonical_json(descriptor))).decode("ascii"),
    }, key


def _verify(document: dict, *, now: float = 1_800_000_000.0):
    from app.kernel.commons.node_health import verify_node_health

    return verify_node_health(document, expected_node_id="commons-node-a", now=now)


def test_signed_node_health_accepts_matching_unexpired_verify_only_descriptor():
    result = _verify(_document()[0])
    assert result["ok"] is True
    assert result["node_id"] == "commons-node-a"
    assert result["maximum_authority"] == "verify_only"
    assert result["checkpoint_count"] == 18
    assert result["trust_expires_at"] == 2_000_000_000.0


def test_signed_node_health_rejects_wrong_node_even_with_valid_signature():
    document, key = _document()
    document["descriptor"]["node_id"] = "commons-node-b"
    document["descriptor_digest"] = sha256_bytes(canonical_json(document["descriptor"]))
    document["node_signature"] = base64.b64encode(
        key.sign(canonical_json(document["descriptor"]))
    ).decode("ascii")
    result = _verify(document)
    assert result == {"ok": False, "reason": "node_id_mismatch"}


def test_signed_node_health_rejects_descriptor_mutation_without_matching_signature():
    document, _key = _document()
    document["descriptor"]["storage"] = {"buckets": 99}
    document["descriptor_digest"] = sha256_bytes(canonical_json(document["descriptor"]))
    result = _verify(document)
    assert result == {"ok": False, "reason": "node_signature_invalid"}


def test_signed_node_health_rejects_expired_or_missing_trust_evidence():
    expired, _key = _document(expires_at=1_799_999_999.0)
    assert _verify(expired) == {"ok": False, "reason": "trust_evidence_expired"}

    missing, key = _document()
    missing["descriptor"]["trust_evidence"] = []
    missing["descriptor_digest"] = sha256_bytes(canonical_json(missing["descriptor"]))
    missing["node_signature"] = base64.b64encode(
        key.sign(canonical_json(missing["descriptor"]))
    ).decode("ascii")
    assert _verify(missing) == {"ok": False, "reason": "trust_evidence_missing"}


def test_remote_commons_healthcheck_requires_exact_service_and_signed_descriptor():
    from scripts.check_remote_commons_health import run_healthcheck

    document, _key = _document()
    responses = {
        "/health": {
            "ok": True,
            "service": "beast-remote-commons-node",
            "node_id": "commons-node-a",
        },
        "/v1/node": document,
    }
    result = run_healthcheck(
        base_url="http://127.0.0.1:8000",
        expected_node_id="commons-node-a",
        fetch_json=lambda path: copy.deepcopy(responses[path]),
        now=1_800_000_000.0,
    )
    assert result["ok"] is True

    responses["/health"]["service"] = "pocket-tts"
    refused = run_healthcheck(
        base_url="http://127.0.0.1:8000",
        expected_node_id="commons-node-a",
        fetch_json=lambda path: copy.deepcopy(responses[path]),
        now=time.time(),
    )
    assert refused == {"ok": False, "reason": "service_identity_mismatch"}


def test_docker_health_command_runs_without_pythonpath_and_checks_evidence():
    root = Path(__file__).resolve().parents[1]
    dockerfile = (root / "Dockerfile.commons-node").read_text(encoding="utf-8")
    health_command = dockerfile.split("\nHEALTHCHECK ", 1)[1].split("\n\n", 1)[0].replace("\\\n", " ")
    command = json.loads(health_command.split("CMD ", 1)[1])
    # Mirror the container's WORKDIR with the repository root and no inherited import path.
    assert "/workspace" in shlex.split(dockerfile.split("\nWORKDIR ", 1)[1].splitlines()[0])
    args = [sys.executable, *(arg.replace("/workspace/", f"{root}/") for arg in command[1:])]
    active = _document(expires_at=time.time() + 120)[0]
    expired = _document(expires_at=time.time() - 120)[0]
    responses = {
        "/health": {"ok": True, "service": "beast-remote-commons-node", "node_id": "commons-node-a"},
        "/v1/node": active,
    }

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            body = json.dumps(responses[self.path]).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    env = {key: value for key, value in os.environ.items() if key != "PYTHONPATH"}
    env["BEAST_COMMONS_NODE_ID"] = "commons-node-a"
    with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            args += ["--base-url", f"http://127.0.0.1:{server.server_port}"]
            admitted = subprocess.run(args, cwd=root, env=env, capture_output=True, text=True, timeout=8)
            responses["/v1/node"] = expired
            refused = subprocess.run(args, cwd=root, env=env, capture_output=True, text=True, timeout=8)
        finally:
            server.shutdown()
            worker.join()

    assert admitted.returncode == 0, admitted.stderr
    assert json.loads(admitted.stdout)["ok"] is True
    assert refused.returncode == 1
    assert json.loads(refused.stdout) == {"ok": False, "reason": "trust_evidence_expired"}

import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import urllib.request

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.kernel.execution.guardian_authorization import guardian_operation_digest
from app.kernel.execution.guardian_uvicorn import (
    GuardianListenerUnavailable,
    GuardianOperationCapabilityProvider,
    GuardianStartupError,
    _authorization_headers,
    build_guardian_client_from_environment,
)
from app.kernel.execution.process_identity import LinuxProcessIdentityCollector
from app.kernel.execution.socket_guardian import SocketGuardianClient, SocketGuardianServer


BINDING = {
    "workspace_id": "workspace-guardian-uvicorn",
    "capability_ref": "deployment:beast:1",
    "appraisal_ref": "arda:appraisal:1",
    "policy_generation": "policy:9",
}


def _process_lease(scope="guardian-uvicorn-test"):
    return LinuxProcessIdentityCollector().collect(os.getpid(), owner_scope=scope)


def test_operation_provider_requests_exact_guardian_digest():
    seen = {}

    def authority(request):
        seen.update(request)
        return {
            "allowed": True,
            "capability": {"request_digest": request["request_digest"], "authority": "arda"},
        }

    request = {
        "request_id": "transport-only",
        "op": "recover",
        "lease_id": "lease:1",
        "workspace_id": "workspace-1",
        "policy_generation": "policy:1",
        "appraisal_ref": "appraisal:1",
        "process_lease": {"lease_id": "process:1"},
    }
    capability = GuardianOperationCapabilityProvider(authority)(request)
    assert capability["request_digest"] == guardian_operation_digest(request)
    assert seen["op"] == "recover"
    assert "request_id" not in seen


def test_environment_builder_refuses_placeholder_production_binding(tmp_path):
    receipt = Ed25519PrivateKey.generate()
    receipt_path = tmp_path / "receipt.pub.pem"
    receipt_path.write_bytes(receipt.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo,
    ))
    authority_path = tmp_path / "authority.pub.pem"
    authority_path.write_bytes(Ed25519PrivateKey.generate().public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo,
    ))
    environment = {
        "BEAST_GUARDIAN_CONTROL_SOCKET": str(tmp_path / "guardian.sock"),
        "BEAST_GUARDIAN_RECEIPT_PUBLIC_KEY": str(receipt_path),
        "BEAST_GUARDIAN_AUTHORIZATION_URL": "https://arda.test/authorize",
        "BEAST_GUARDIAN_AUTHORITY_PUBLIC_KEY": str(authority_path),
        "BEAST_GUARDIAN_WORKSPACE_ID": "REPLACE_WITH_WORKSPACE_UUID",
        "BEAST_GUARDIAN_POLICY_GENERATION": "policy:1",
        "BEAST_GUARDIAN_APPRAISAL_REF": "appraisal:1",
    }
    with pytest.raises(GuardianStartupError, match="placeholder"):
        build_guardian_client_from_environment(environment=environment)


def test_guardian_authorization_token_file_must_be_private(tmp_path):
    credential = tmp_path / "guardian.token"
    credential.write_text("secret-value\n", encoding="utf-8")
    credential.chmod(0o644)
    with pytest.raises(GuardianStartupError, match="group/world"):
        _authorization_headers(
            {"BEAST_GUARDIAN_AUTHORIZATION_TOKEN_FILE": str(credential)}
        )
    credential.chmod(0o600)
    assert _authorization_headers(
        {"BEAST_GUARDIAN_AUTHORIZATION_TOKEN_FILE": str(credential)}
    ) == {"Authorization": "Bearer secret-value"}


def test_missing_listener_is_the_only_retryable_selection_failure():
    class EmptyClient:
        @staticmethod
        def snapshot():
            return []

    from app.kernel.execution.guardian_uvicorn import recover_named_listener

    with pytest.raises(GuardianListenerUnavailable):
        recover_named_listener(
            EmptyClient(),
            service_id="beast",
            workspace_id="workspace:1",
            policy_generation="policy:1",
            appraisal_ref="appraisal:1",
        )


def _wait_health(port: int, timeout=20.0):
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=0.5) as response:
                return json.loads(response.read())
        except Exception as exc:
            last = exc
            time.sleep(0.05)
    raise AssertionError(f"Guardian-backed Uvicorn did not become healthy: {last}")


def test_uvicorn_service_process_restarts_on_same_guardian_listener(tmp_path):
    receipt_key = Ed25519PrivateKey.generate()
    public_path = tmp_path / "guardian-receipt.pub.pem"
    public_path.write_bytes(receipt_key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo,
    ))
    server = SocketGuardianServer(
        tmp_path / "guardian.sock",
        tmp_path / "guardian.sqlite3",
        signer=receipt_key,
        authorize=lambda _request: True,
    )
    server.start()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    parent = SocketGuardianClient(
        tmp_path / "guardian.sock",
        process_lease_provider=_process_lease,
        receipt_verifier=receipt_key.public_key(),
    )
    lease = parent.reserve(
        "beast", BINDING["workspace_id"], host="127.0.0.1", port=0,
        authority_ref="arda", capability_ref=BINDING["capability_ref"],
        appraisal_ref=BINDING["appraisal_ref"], policy_generation=BINDING["policy_generation"],
    )
    script = r'''
import os, sys
from fastapi import FastAPI
from cryptography.hazmat.primitives import serialization
from app.kernel.execution.process_identity import LinuxProcessIdentityCollector
from app.kernel.execution.socket_guardian import SocketGuardianClient
from app.kernel.execution.guardian_uvicorn import run_uvicorn_with_guardian

control, public_path = sys.argv[1:3]
public = serialization.load_pem_public_key(open(public_path, "rb").read())
client = SocketGuardianClient(
    control,
    process_lease_provider=lambda: LinuxProcessIdentityCollector().collect(os.getpid(), owner_scope="guardian-uvicorn-subprocess"),
    receipt_verifier=public,
)
app = FastAPI()
@app.get("/health")
async def health():
    return {"ok": True, "pid": os.getpid(), "lease_id": os.environ.get("BEAST_ACTIVE_PORT_LEASE_ID"), "generation": os.environ.get("BEAST_ACTIVE_LISTENER_GENERATION")}
run_uvicorn_with_guardian(
    app, service_id="beast", client=client,
    binding={"workspace_id":"workspace-guardian-uvicorn","appraisal_ref":"arda:appraisal:1","policy_generation":"policy:9"},
    log_level="error",
)
'''

    def launch():
        return subprocess.Popen(
            [sys.executable, "-c", script, str(tmp_path / "guardian.sock"), str(public_path)],
            cwd=Path(__file__).parents[1],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

    first = second = None
    try:
        first = launch()
        first_health = _wait_health(lease.port)
        assert first_health["lease_id"] == lease.lease_id
        assert first_health["generation"] == "1"
        first.terminate()
        first.wait(timeout=10)

        second = launch()
        second_health = _wait_health(lease.port)
        assert second_health["lease_id"] == lease.lease_id
        assert second_health["pid"] != first_health["pid"]
        assert second_health["generation"] == "1"
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline and parent.snapshot()[0].health_state != "healthy":
            time.sleep(0.025)
        assert parent.snapshot()[0].health_state == "healthy"
    finally:
        for process in (first, second):
            if process is not None and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
        try:
            parent.release(lease.lease_id, **BINDING)
        except Exception:
            pass
        server.stop()
        thread.join(timeout=2)

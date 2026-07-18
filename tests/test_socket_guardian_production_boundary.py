import base64
import os
import socket
import subprocess
import sys
import threading
import time
from dataclasses import asdict
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.kernel.execution.guardian_authorization import (
    GUARDIAN_CAPABILITY_AUDIENCE,
    GuardianCapabilityAuthorizer,
    guardian_operation_digest,
)
from app.kernel.execution.process_identity import LinuxProcessIdentityCollector
from app.kernel.execution.socket_guardian import (
    GuardianProtocolError,
    SocketGuardianClient,
    SocketGuardianServer,
)
from app.kernel.integration.one_use_capability import OneUseCapability, OneUseCapabilityLedger


def _run(server):
    server.start()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return thread


def test_guardian_exact_signed_operation_capability_is_one_use(tmp_path):
    authority_key = Ed25519PrivateKey.generate()
    receipt_key = Ed25519PrivateKey.generate()
    ledger = OneUseCapabilityLedger(
        {"arda": authority_key.public_key()}, tmp_path / "operation-capabilities.sqlite3"
    )
    authorizer = GuardianCapabilityAuthorizer(ledger, allowed_authorities={"arda"})
    fixed_process_lease = LinuxProcessIdentityCollector().collect(
        os.getpid(), owner_scope="guardian-production-boundary-test"
    )
    issued = []

    def mint(request):
        unsigned = OneUseCapability(
            capability_id=f"guardian-op:{len(issued) + 1}",
            request_digest=guardian_operation_digest(request),
            authority="arda",
            expires_at=time.time() + 60,
            nonce=f"nonce:{len(issued) + 1}",
            signature="",
            audience=GUARDIAN_CAPABILITY_AUDIENCE,
            policy_generation=str(request["policy_generation"]),
            appraisal_ref=str(request["appraisal_ref"]),
            key_id="arda-test-key",
        )
        result = {
            **asdict(unsigned),
            "signature": base64.b64encode(authority_key.sign(unsigned.body())).decode("ascii"),
        }
        issued.append(result)
        return result

    server = SocketGuardianServer(
        tmp_path / "guardian.sock",
        tmp_path / "guardian.sqlite3",
        signer=receipt_key,
        authorize=authorizer,
    )
    thread = _run(server)
    client = SocketGuardianClient(
        tmp_path / "guardian.sock",
        process_lease_provider=lambda: fixed_process_lease,
        operation_capability_provider=mint,
        receipt_verifier=receipt_key.public_key(),
    )
    binding = {
        "capability_ref": "lease-capability:1",
        "appraisal_ref": "arda-appraisal:1",
        "policy_generation": "arda-policy:7",
    }
    try:
        lease = client.reserve("signed-service", "workspace-1", authority_ref="arda", **binding)
        assert ledger.consumed("guardian-op:1")

        replay = issued[0]
        client.operation_capability_provider = lambda _request: replay
        with pytest.raises(GuardianProtocolError, match="capability"):
            client.mark_health(
                lease.lease_id, healthy=True, workspace_id="workspace-1", **binding
            )

        client.operation_capability_provider = mint
        client.release(lease.lease_id, workspace_id="workspace-1", **binding)
        assert ledger.consumed("guardian-op:2")
    finally:
        server.stop()
        thread.join(timeout=2)


def test_externally_owned_listener_survives_guardian_restart(tmp_path):
    receipt_key = Ed25519PrivateKey.generate()
    supervisor_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    supervisor_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    supervisor_socket.bind(("127.0.0.1", 0))
    supervisor_socket.listen(8)
    binding = {
        "workspace_id": "workspace-1",
        "authority_ref": "systemd.user",
        "capability_ref": "unit:beast.socket",
        "appraisal_ref": "arda:boot-appraisal:1",
        "policy_generation": "policy:7",
    }

    def new_server():
        return SocketGuardianServer(
            tmp_path / "guardian.sock",
            tmp_path / "guardian.sqlite3",
            signer=receipt_key,
            authorize=lambda _request: True,
        )

    server1 = new_server()
    first = server1.adopt_inherited_socket("beast", supervisor_socket, **binding)
    thread1 = _run(server1)
    client1 = SocketGuardianClient(
        tmp_path / "guardian.sock",
        process_lease_provider=lambda: LinuxProcessIdentityCollector().collect(
            os.getpid(), owner_scope="guardian-restart-test"
        ),
        receipt_verifier=receipt_key.public_key(),
    )
    try:
        recovered, duplicate, _receipt = client1.recover(
            first.lease_id,
            workspace_id=binding["workspace_id"],
            capability_ref=binding["capability_ref"],
            appraisal_ref=binding["appraisal_ref"],
            policy_generation=binding["policy_generation"],
        )
        duplicate.close()
        assert recovered.listener_generation == 1
    finally:
        server1.stop()
        thread1.join(timeout=2)

    # The independently owned descriptor still holds the port after the first
    # guardian and every descriptor it owned have closed.
    probe = socket.create_connection(supervisor_socket.getsockname(), timeout=2)
    probe.close()

    server2 = new_server()
    second = server2.adopt_inherited_socket("beast", supervisor_socket, **binding)
    thread2 = _run(server2)
    try:
        assert second.listener_generation == 2
        assert second.port == first.port
        states = {event["next_state"] for event in SocketGuardianClient(
            tmp_path / "guardian.sock",
            process_lease_provider=lambda: LinuxProcessIdentityCollector().collect(
                os.getpid(), owner_scope="guardian-restart-test"
            ),
            receipt_verifier=receipt_key.public_key(),
        ).events(limit=20)}
        assert "orphaned_guardian_restart" in states
        assert "reserved" in states
    finally:
        server2.stop()
        thread2.join(timeout=2)
        supervisor_socket.close()


def test_systemd_listen_fds_environment_adopts_named_descriptor(tmp_path):
    supervisor_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    supervisor_socket.bind(("127.0.0.1", 0))
    supervisor_socket.listen(8)
    script = r'''
import json, os, sys
from app.kernel.execution.socket_guardian import SocketGuardianServer

inherited_fd = int(sys.argv[3])
if inherited_fd != 3:
    os.dup2(inherited_fd, 3)
os.environ["LISTEN_PID"] = str(os.getpid())
os.environ["LISTEN_FDS"] = "1"
os.environ["LISTEN_FDNAMES"] = "beast"
server = SocketGuardianServer(
    sys.argv[1], sys.argv[2], require_authority=False,
    require_process_lease=False,
)
leases = server.adopt_systemd_environment({
    "beast": {
        "workspace_id": "workspace-1",
        "authority_ref": "systemd.user",
        "capability_ref": "unit:beast.socket",
        "appraisal_ref": "arda:boot-appraisal:1",
        "policy_generation": "policy:7",
    }
})
print(json.dumps(leases[0].__dict__, sort_keys=True))
server.stop()
'''
    original_fd = supervisor_socket.fileno()

    try:
        result = subprocess.run(
            [sys.executable, "-c", script, str(tmp_path / "guardian.sock"), str(tmp_path / "guardian.sqlite3"), str(original_fd)],
            cwd=Path(__file__).parents[1],
            pass_fds=(original_fd,),
            text=True,
            capture_output=True,
            check=True,
            timeout=15,
        )
        lease = __import__("json").loads(result.stdout)
        assert lease["service_id"] == "beast"
        assert lease["port"] == supervisor_socket.getsockname()[1]
        assert lease["listener_generation"] == 1
        probe = socket.create_connection(supervisor_socket.getsockname(), timeout=2)
        probe.close()
    finally:
        supervisor_socket.close()

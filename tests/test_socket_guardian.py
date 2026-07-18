import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import threading

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.kernel.execution.process_identity import LinuxProcessIdentityCollector
from app.kernel.execution.socket_guardian import SocketGuardianClient, SocketGuardianServer, GuardianProtocolError
from app.kernel.networking.service_registry import ServiceRegistry
from app.kernel.sensorium.runtime import SensoriumRuntime


def process_lease():
    return LinuxProcessIdentityCollector().collect(os.getpid(), owner_scope="socket-guardian-test")


def start_guardian(tmp_path, *, registry=None, health_probe=None):
    private = Ed25519PrivateKey.generate()
    public_path = tmp_path / "guardian-public.pem"
    public_path.write_bytes(private.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo,
    ))
    authorize = lambda request: request.get("op") in {"snapshot", "events"} or (
        request.get("capability_ref") == "cap:guardian:1"
        and request.get("appraisal_ref") == "appraisal:guardian:1"
        and request.get("policy_generation") == "policy:1"
    )
    server = SocketGuardianServer(
        tmp_path / "guardian.sock", tmp_path / "guardian.sqlite3",
        signer=private, authorize=authorize, service_registry=registry,
        health_probe=health_probe,
    )
    server.start()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    client = SocketGuardianClient(
        tmp_path / "guardian.sock", process_lease_provider=process_lease,
        receipt_verifier=private.public_key(),
    )
    return server, thread, client, public_path


BINDING = {
    "capability_ref": "cap:guardian:1",
    "appraisal_ref": "appraisal:guardian:1",
    "policy_generation": "policy:1",
}


def test_guardian_preserves_socket_across_real_broker_process_restarts(tmp_path):
    server, thread, parent_client, public_path = start_guardian(tmp_path, health_probe=lambda _lease: True)
    script = r'''
import json, os, sys
from cryptography.hazmat.primitives import serialization
from app.kernel.execution import PortLeaseBroker
from app.kernel.execution.process_identity import LinuxProcessIdentityCollector
from app.kernel.execution.socket_guardian import SocketGuardianClient

socket_path, public_path, action = sys.argv[1:4]
public = serialization.load_pem_public_key(open(public_path, "rb").read())
client = SocketGuardianClient(
    socket_path,
    process_lease_provider=lambda: LinuxProcessIdentityCollector().collect(os.getpid(), owner_scope="broker-subprocess"),
    receipt_verifier=public,
)
broker = PortLeaseBroker(guardian_client=client)
binding = {"workspace_id":"workspace-1","capability_ref":"cap:guardian:1","appraisal_ref":"appraisal:guardian:1","policy_generation":"policy:1"}
if action == "reserve":
    lease = broker.reserve("beast-dynamic", "workspace-1", port=0, authority_ref="arda", **{k:v for k,v in binding.items() if k != "workspace_id"})
else:
    lease_id = sys.argv[4]
    lease = next(item for item in broker.snapshot() if item.lease_id == lease_id)
sock, receipt = broker.take_socket_with_receipt(lease.lease_id, **binding)
try:
    address = sock.getsockname()
finally:
    sock.close()
print(json.dumps({"lease":lease.__dict__,"receipt":receipt.__dict__,"address":address}))
'''
    try:
        first = subprocess.run(
            [sys.executable, "-c", script, str(tmp_path / "guardian.sock"), str(public_path), "reserve"],
            cwd=Path(__file__).parents[1], text=True, capture_output=True, check=True, timeout=15,
        )
        first_result = json.loads(first.stdout)
        lease_id = first_result["lease"]["lease_id"]
        port = first_result["lease"]["port"]

        # The first broker process has exited and closed its duplicate. The
        # guardian's original descriptor must still own the listener.
        probe = socket.create_connection(("127.0.0.1", port), timeout=2)
        probe.close()

        second = subprocess.run(
            [sys.executable, "-c", script, str(tmp_path / "guardian.sock"), str(public_path), "recover", lease_id],
            cwd=Path(__file__).parents[1], text=True, capture_output=True, check=True, timeout=15,
        )
        second_result = json.loads(second.stdout)
        assert second_result["lease"]["lease_id"] == lease_id
        assert second_result["lease"]["listener_generation"] == 1
        assert second_result["receipt"]["signature"]

        health = parent_client.probe_health(workspace_id="workspace-1", **BINDING)
        assert health["results"] == [{"lease_id": lease_id, "healthy": True}]
        assert parent_client.snapshot()[0].lifecycle_state == "healthy"
        parent_client.release(lease_id, workspace_id="workspace-1", reason="test_complete", **BINDING)

        replacement = parent_client.reserve(
            "beast-dynamic", "workspace-1", host="127.0.0.1", port=port,
            authority_ref="arda", **BINDING,
        )
        assert replacement.listener_generation == 2
        parent_client.release(replacement.lease_id, workspace_id="workspace-1", reason="test_complete", **BINDING)
        transitions = {event["next_state"] for event in parent_client.events(limit=20)}
        assert {"reserved", "handed_off", "healthy", "released"} <= transitions
        sensorium=SensoriumRuntime(capacity=32,export_root=tmp_path/"outbox",boot_id="guardian-boot")
        events=parent_client.events(limit=20)
        assert sensorium.ingest_guardian_events(events,workspace_by_lease={lease_id:"workspace-1"})==len(events)
        assert sensorium.ingest_guardian_events(events)==0
        assert sensorium.state()["recent_event_types"]["port_lease.transition"]==len(events)
    finally:
        server.stop()
        thread.join(timeout=2)


def test_guardian_rejects_recovery_binding_tampering(tmp_path):
    server, thread, client, _ = start_guardian(tmp_path)
    try:
        lease = client.reserve("dynamic", "workspace-1", authority_ref="arda", **BINDING)
        with pytest.raises(GuardianProtocolError, match="authority"):
            client.recover(
                lease.lease_id, workspace_id="workspace-2",
                capability_ref=BINDING["capability_ref"], appraisal_ref=BINDING["appraisal_ref"],
                policy_generation=BINDING["policy_generation"],
            )
        client.release(lease.lease_id, workspace_id="workspace-1", **BINDING)
    finally:
        server.stop(); thread.join(timeout=2)


def test_guardian_reconciles_authoritative_service_registry(tmp_path):
    temporary = socket.socket()
    temporary.bind(("127.0.0.1", 0))
    port = temporary.getsockname()[1]
    temporary.close()
    registry = ServiceRegistry({
        "beast": {"hostname": "beast.test", "upstream": f"127.0.0.1:{port}", "port": port}
    })
    server, thread, client, _ = start_guardian(tmp_path, registry=registry)
    try:
        lease = client.reserve(
            "beast", "workspace-1", host="127.0.0.1", port=port,
            authority_ref="arda", registry_digest=registry.digest(), **BINDING,
        )
        result = client.reconcile_registry(registry_digest=registry.digest(), workspace_id="workspace-1", **BINDING)
        assert result["reconciled"] == [lease.lease_id]

        drifted = ServiceRegistry({
            "other": {"hostname": "other.test", "upstream": f"127.0.0.1:{port + 1}", "port": port + 1}
        })
        server.service_registry = drifted
        result = client.reconcile_registry(registry_digest=drifted.digest(), workspace_id="workspace-1", **BINDING)
        assert result["revoked"] == [lease.lease_id]
        assert client.snapshot() == ()
        assert any(event["reason"] == "service_registry_drift" for event in client.events())
    finally:
        server.stop(); thread.join(timeout=2)


@pytest.mark.skipif(not socket.has_ipv6, reason="IPv6 is unavailable")
def test_guardian_owns_ipv6_udp_socket(tmp_path):
    server, thread, client, _ = start_guardian(tmp_path)
    try:
        lease = client.reserve(
            "udp-v6", "workspace-1", host="::1", family="AF_INET6", protocol="UDP",
            authority_ref="arda", **BINDING,
        )
        _lease, held, receipt = client.recover(lease.lease_id, workspace_id="workspace-1", **BINDING)
        try:
            assert held.family == socket.AF_INET6
            assert held.type & socket.SOCK_DGRAM == socket.SOCK_DGRAM
            assert receipt.listener_generation == 1
        finally:
            held.close()
        client.release(lease.lease_id, workspace_id="workspace-1", **BINDING)
    finally:
        server.stop(); thread.join(timeout=2)

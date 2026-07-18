import base64
import os
import subprocess
import socket
import sys
import threading
import time
from dataclasses import replace

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.kernel.execution.stale_process_retirement import (
    RETIRE_PROCESS_AUDIENCE,
    RETIRE_PROCESS_AUTHORITY,
    StaleProcessRetirementCoordinator,
    StaleProcessRetirementRequest,
)
from app.kernel.execution.process_supervisor import ProcessLeaseSupervisor
from app.kernel.execution.process_supervisor import ProcessSignalAuthorization
from app.kernel.execution.guardian_retirement_boundary import GuardianStaleListenerBoundary
from app.kernel.execution.process_descendants import LinuxProcessDescendantInspector
from app.kernel.execution.socket_guardian import SocketGuardianClient, SocketGuardianServer
from app.kernel.integration.one_use_capability import OneUseCapabilityLedger
from app.kernel.networking.service_registry import ServiceRegistry
from app.kernel.sensorium.runtime import SensoriumRuntime


def _request(lease):
    return StaleProcessRetirementRequest(
        mission_id="mission-retire",
        lease_id=lease.lease_id,
        executable_digest=lease.executable_digest,
        cgroup_id=lease.cgroup_id,
        pid_namespace_inode=lease.pid_namespace_inode,
        mount_namespace_inode=lease.mount_namespace_inode,
        owner_scope=lease.owner_scope,
        workspace_identity="workspace:sha256:test",
        service_id="service:test",
        registry_digest="sha256:registry",
        listener_generation=7,
        policy_generation="policy:7",
        appraisal_ref="appraisal:retire:7",
        reason="retire confirmed stale BEAST listener",
    )


def _authorities(request, now):
    operator = {
        "approval_receipt_id": "operator:retire:1",
        "approved_by": "test-operator",
        "request_digest": request.request_digest,
        "action": RETIRE_PROCESS_AUTHORITY,
        "destructive": True,
    }
    appraisal = {
        "appraisal_ref": request.appraisal_ref,
        "request_digest": request.request_digest,
        "policy_generation": request.policy_generation,
        "audience": RETIRE_PROCESS_AUDIENCE,
        "state": "verified",
        "expires_at": now + 60,
    }
    capability = {
        "capability_id": "capability:retire:1",
        "request_digest": request.request_digest,
        "authority": RETIRE_PROCESS_AUTHORITY,
        "expires_at": now + 60,
        "nonce": "retire-once",
        "signature": base64.b64encode(b"isolated-test-signature").decode(),
        "audience": RETIRE_PROCESS_AUDIENCE,
        "policy_generation": request.policy_generation,
        "appraisal_ref": request.appraisal_ref,
    }
    return operator, appraisal, capability


@pytest.mark.skipif(
    not hasattr(os, "pidfd_open"), reason="pidfd process retirement is unavailable"
)
def test_owned_stale_process_retirement_is_pidfd_only_one_use_and_verified(tmp_path):
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    supervisor = ProcessLeaseSupervisor()
    ledger = OneUseCapabilityLedger(path=tmp_path / "capabilities.sqlite", require_verifier=False)
    physical = {"retired": False, "replacement": ""}
    try:
        lease = supervisor.acquire(child.pid, owner_scope="beast_service", mission_id="mission-retire")
        request = _request(lease)
        now = time.time()
        operator, appraisal, capability = _authorities(request, now)

        coordinator = StaleProcessRetirementCoordinator(
            supervisor,
            ledger,
            current_registry_digest=lambda: "sha256:registry",
            current_listener_generation=lambda service_id: 7 if service_id == "service:test" else 0,
            listener_is_retired=lambda _request: physical.__setitem__("retired", True) is None,
            start_replacement=lambda _request: physical.__setitem__("replacement", "socket:replacement:8") or physical["replacement"],
            replacement_is_healthy=lambda identity: identity == physical["replacement"],
            orphan_descendants_absent=lambda _request: True,
        )
        receipt = coordinator.retire(
            lease,
            request,
            operator_approval=operator,
            arda_appraisal=appraisal,
            one_use_capability=capability,
            timeout_seconds=3,
            now=now,
        )
        child.wait(timeout=5)

        assert receipt.final_status == "verified_stale_process_retirement"
        assert receipt.targeted_via == "pidfd"
        assert receipt.identity_revalidated is True
        assert receipt.graceful_exit_observed is True
        assert receipt.replacement_listener_identity == "socket:replacement:8"
        assert receipt.replacement_healthy is True
        assert ledger.consumed("capability:retire:1") is True
        receipt.validate()
        with pytest.raises(PermissionError, match="already consumed"):
            ledger.consume(
                capability,
                request_digest=request.request_digest,
                authority=RETIRE_PROCESS_AUTHORITY,
                now=now,
            )
    finally:
        supervisor.close()
        if child.poll() is None:
            child.kill()
        child.wait(timeout=5)


@pytest.mark.skipif(
    not hasattr(os, "pidfd_open"), reason="pidfd process retirement is unavailable"
)
def test_unknown_scope_and_drift_refuse_before_capability_consumption(tmp_path):
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    supervisor = ProcessLeaseSupervisor()
    ledger = OneUseCapabilityLedger(path=tmp_path / "capabilities.sqlite", require_verifier=False)
    try:
        lease = supervisor.acquire(child.pid, owner_scope="external_unknown")
        request = _request(lease)
        now = time.time()
        operator, appraisal, capability = _authorities(request, now)
        coordinator = StaleProcessRetirementCoordinator(
            supervisor,
            ledger,
            current_registry_digest=lambda: "sha256:registry",
            current_listener_generation=lambda _service: 7,
            listener_is_retired=lambda _request: True,
            start_replacement=lambda _request: "socket:replacement:8",
            replacement_is_healthy=lambda _identity: True,
            orphan_descendants_absent=lambda _request: True,
        )

        with pytest.raises(PermissionError, match="owner scope"):
            coordinator.retire(
                lease,
                request,
                operator_approval=operator,
                arda_appraisal=appraisal,
                one_use_capability=capability,
                now=now,
            )
        assert child.poll() is None
        assert ledger.consumed("capability:retire:1") is False

        managed_request = replace(request, owner_scope="beast_service")
        managed_lease = replace(lease, owner_scope="beast_service")
        with pytest.raises(Exception):
            coordinator.retire(
                managed_lease,
                managed_request,
                operator_approval=operator,
                arda_appraisal=appraisal,
                one_use_capability=capability,
                now=now,
            )
        assert child.poll() is None
        assert ledger.consumed("capability:retire:1") is False
    finally:
        supervisor.close()
        if child.poll() is None:
            child.kill()
        child.wait(timeout=5)


@pytest.mark.skipif(
    not hasattr(os, "pidfd_open"), reason="pidfd process retirement is unavailable"
)
def test_identity_drift_immediately_before_signal_leaves_process_running(monkeypatch):
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    supervisor = ProcessLeaseSupervisor()
    try:
        lease = supervisor.acquire(child.pid, owner_scope="beast_service")
        monkeypatch.setattr(supervisor.collector, "still_matches", lambda _lease: False)
        authorization = ProcessSignalAuthorization(
            lease_id=lease.lease_id,
            signal_number=15,
            approved_by="test-operator",
            approval_receipt_id="operator:drift-test",
            reason="must refuse drift",
        )
        with pytest.raises(ProcessLookupError, match="drifted before pidfd signal"):
            supervisor.send_signal(lease.lease_id, 15, authorization)
        assert child.poll() is None
    finally:
        supervisor.close()
        if child.poll() is None:
            child.kill()
        child.wait(timeout=5)


def _start_guardian(tmp_path, registry, *, healthy=True):
    private = Ed25519PrivateKey.generate()
    binding = {
        "capability_ref": "cap:guardian:retirement",
        "appraisal_ref": "appraisal:retirement",
        "policy_generation": "policy:7",
    }
    server = SocketGuardianServer(
        tmp_path / "guardian.sock",
        tmp_path / "guardian.sqlite",
        signer=private,
        authorize=lambda request: request.get("op") in {"snapshot", "events"} or all(
            request.get(key) == value for key, value in binding.items()
        ),
        service_registry=registry,
        health_probe=lambda _lease: healthy,
    )
    server.start()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    client = SocketGuardianClient(
        tmp_path / "guardian.sock",
        process_lease_provider=lambda: supervisor_process_lease(),
        receipt_verifier=private.public_key(),
    )
    return server, thread, client, binding


def supervisor_process_lease():
    from app.kernel.execution.process_identity import LinuxProcessIdentityCollector

    return LinuxProcessIdentityCollector().collect(os.getpid(), owner_scope="beast_service")


@pytest.mark.skipif(
    not hasattr(os, "pidfd_open"), reason="pidfd process retirement is unavailable"
)
@pytest.mark.parametrize("healthy", [True, False])
def test_real_listener_is_replaced_by_guardian_or_rolled_back(tmp_path, healthy):
    probe = socket.socket()
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
    probe.close()
    child = subprocess.Popen(
        [
            sys.executable,
            "-u",
            "-c",
            (
                "import socket,time; "
                f"s=socket.socket(); s.bind(('127.0.0.1',{port})); s.listen(8); "
                "print('ready', flush=True); time.sleep(30)"
            ),
        ],
        stdout=subprocess.PIPE,
        text=True,
    )
    assert child.stdout is not None and child.stdout.readline().strip() == "ready"
    registry = ServiceRegistry({
        "beast": {
            "hostname": "beast.test",
            "upstream": f"127.0.0.1:{port}",
            "port": port,
        }
    })
    server, thread, client, binding = _start_guardian(tmp_path, registry, healthy=healthy)
    supervisor = ProcessLeaseSupervisor()
    boundary = GuardianStaleListenerBoundary(
        client,
        registry,
        workspace_id="workspace:sha256:test",
        guardian_binding=binding,
    )
    ledger = OneUseCapabilityLedger(path=tmp_path / "retirement.sqlite", require_verifier=False)
    sensorium = SensoriumRuntime(capacity=64, export_root=tmp_path / "sensorium", boot_id="boot-retirement")
    try:
        lease = supervisor.acquire(child.pid, owner_scope="beast_service", mission_id="mission-retire")
        request = replace(
            _request(lease),
            service_id="beast",
            registry_digest=registry.digest(),
        )
        now = time.time()
        operator, appraisal, capability = _authorities(request, now)
        coordinator = StaleProcessRetirementCoordinator(
            supervisor,
            ledger,
            current_registry_digest=boundary.registry_digest,
            current_listener_generation=boundary.listener_generation,
            listener_is_retired=boundary.listener_is_retired,
            start_replacement=boundary.start_replacement,
            replacement_is_healthy=boundary.replacement_is_healthy,
            orphan_descendants_absent=lambda _request: True,
            prepare_physical_boundary=boundary.bind_request,
            descendant_inspector=LinuxProcessDescendantInspector(supervisor.collector),
            sensorium=sensorium,
        )
        if healthy:
            receipt = coordinator.retire(
                lease,
                request,
                operator_approval=operator,
                arda_appraisal=appraisal,
                one_use_capability=capability,
                timeout_seconds=3,
                now=now,
            )
            replacement = client.snapshot()[0]
            assert receipt.replacement_listener_identity == replacement.lease_id
            assert replacement.listener_generation == request.listener_generation + 1
            assert replacement.health_state == "healthy"
            connection = socket.create_connection(("127.0.0.1", port), timeout=1)
            connection.close()
            assert boundary.rollback_replacement("test_cleanup") is True
            event_types = {entry.event.event_type for entry in sensorium.sequencer.latest(20)}
            assert {"process.descendants_snapshotted", "process.stale_retirement_verified"} <= event_types
        else:
            with pytest.raises(RuntimeError, match="failed health"):
                coordinator.retire(
                    lease,
                    request,
                    operator_approval=operator,
                    arda_appraisal=appraisal,
                    one_use_capability=capability,
                    timeout_seconds=3,
                    now=now,
                )
            assert client.snapshot() == ()
            assert any(event["reason"] == "replacement_health_rollback" for event in client.events())
    finally:
        supervisor.close()
        if child.poll() is None:
            child.kill()
        child.wait(timeout=5)
        server.stop()
        thread.join(timeout=2)


@pytest.mark.skipif(
    not hasattr(os, "fork") or not hasattr(os, "pidfd_open"),
    reason="retained-listener process race requires Linux fork and pidfd",
)
def test_child_retained_listener_refuses_rebind_after_parent_exit(tmp_path):
    probe = socket.socket()
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
    probe.close()
    script = (
        "import os,socket,time; "
        f"s=socket.socket(); s.bind(('127.0.0.1',{port})); s.listen(8); "
        "child=os.fork(); "
        "print(f'ready {child}',flush=True) if child else None; "
        "time.sleep(30)"
    )
    parent = subprocess.Popen(
        [sys.executable, "-u", "-c", script], stdout=subprocess.PIPE, text=True,
    )
    assert parent.stdout is not None
    ready = parent.stdout.readline().strip().split()
    assert ready[0] == "ready"
    retained_child_pid = int(ready[1])
    registry = ServiceRegistry({
        "beast": {
            "hostname": "beast.test",
            "upstream": f"127.0.0.1:{port}",
            "port": port,
        }
    })
    server, thread, client, binding = _start_guardian(tmp_path, registry)
    supervisor = ProcessLeaseSupervisor()
    boundary = GuardianStaleListenerBoundary(
        client, registry, workspace_id="workspace:sha256:test", guardian_binding=binding,
    )
    ledger = OneUseCapabilityLedger(path=tmp_path / "retirement.sqlite", require_verifier=False)
    try:
        lease = supervisor.acquire(parent.pid, owner_scope="beast_service", mission_id="mission-retire")
        request = replace(_request(lease), service_id="beast", registry_digest=registry.digest())
        now = time.time()
        operator, appraisal, capability = _authorities(request, now)
        coordinator = StaleProcessRetirementCoordinator(
            supervisor,
            ledger,
            current_registry_digest=boundary.registry_digest,
            current_listener_generation=boundary.listener_generation,
            listener_is_retired=boundary.listener_is_retired,
            start_replacement=boundary.start_replacement,
            replacement_is_healthy=boundary.replacement_is_healthy,
            orphan_descendants_absent=lambda _request: False,
            prepare_physical_boundary=boundary.bind_request,
            descendant_inspector=LinuxProcessDescendantInspector(supervisor.collector),
        )
        with pytest.raises(RuntimeError, match="listener remained"):
            coordinator.retire(
                lease,
                request,
                operator_approval=operator,
                arda_appraisal=appraisal,
                one_use_capability=capability,
                timeout_seconds=3,
                now=now,
            )
        parent.wait(timeout=5)
        connection = socket.create_connection(("127.0.0.1", port), timeout=1)
        connection.close()
        assert client.snapshot() == ()
        assert ledger.consumed("capability:retire:1") is True
    finally:
        supervisor.close()
        if parent.poll() is None:
            parent.kill()
        parent.wait(timeout=5)
        try:
            os.kill(retained_child_pid, 9)
        except ProcessLookupError:
            pass
        server.stop()
        thread.join(timeout=2)

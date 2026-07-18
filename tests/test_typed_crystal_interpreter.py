import time
from dataclasses import replace

import pytest

from app.kernel.compute.crystal_replay_lab import default_replay_handlers
from app.kernel.compute.physical_crystal_lifecycle import (
    PhysicalApplicabilityGate,
    RecurrenceContext,
    consume_execution_authority,
)
from app.kernel.compute.typed_crystal_interpreter import TypedCrystalInterpreter
from app.kernel.compute.port_conflict_fixture import start_listener
from app.kernel.compute.socket_inventory import inode_owners, tcp_listeners
from app.kernel.execution.process_identity import LinuxProcessIdentityCollector
from app.kernel.integration.one_use_capability import OneUseCapabilityLedger
from app.kernel.sensorium.contracts import SocketIdentity
from tests.test_physical_crystal_lifecycle import _proof_bundle


def _authorized_recurrence(tmp_path):
    runtime, _candidate, typed, _replay, appraisal, registry, _record, promotion_now = _proof_bundle(tmp_path)
    proc, evidence = start_listener()
    collector = LinuxProcessIdentityCollector()
    lease = collector.collect(proc.pid, owner_scope="typed-recurrence")
    identity = SocketIdentity(
        family="AF_INET", protocol="TCP", local_address_class="loopback",
        local_port=evidence.port, remote_scope="none", owning_process=lease.lease_id,
        service_id="beast-api", workspace_id="workspace:test", cgroup_id=lease.cgroup_id,
        listener_generation=1, opened_at_monotonic_ns=time.monotonic_ns(), policy_class="operator",
    ).with_identity()

    def socket_fresh(value):
        listener = next((item for item in tcp_listeners() if item.port == value.local_port), None)
        return bool(listener and proc.pid in inode_owners(listener.inode))

    gate = PhysicalApplicabilityGate(
        registry, runtime.typed_ir_compiler.registry,
        appraisal_verifier=lambda value: value.get("signature") == "verified-by-test-boundary",
        process_freshness=collector.still_matches, socket_freshness=socket_fresh,
        port_lease_freshness=lambda value: True, proof_ttl_ns=5_000_000_000,
    )
    recurrence = RecurrenceContext(
        parameter_bindings={"requested_port": evidence.port},
        process_leases=(lease,), socket_identities=(identity,), port_leases=(),
        workspace_identity="workspace:test", registry_digest="sha256:" + "d" * 64,
        policy_generation="policy-physical-v1", appraisal=appraisal,
    )
    monotonic = time.monotonic_ns()
    decision = runtime.evaluate_crystal_recurrence(
        typed, recurrence, gate, now=promotion_now + 1, monotonic_ns=monotonic,
    )
    assert decision.allowed and decision.proof
    proof = decision.proof
    ledger = OneUseCapabilityLedger(path=tmp_path / "execution-authority.sqlite", require_verifier=False)
    capability = {
        "capability_id": "capability:typed-recurrence:1",
        "request_digest": proof.execution_request_digest, "authority": "arda",
        "expires_at": promotion_now + 100, "nonce": "typed-recurrence-nonce",
        "signature": "isolated-test-signature", "audience": "beast-runtime",
        "policy_generation": proof.policy_generation, "appraisal_ref": proof.appraisal_ref,
    }
    authorization = consume_execution_authority(
        proof, capability, ledger, authority="arda", audience="beast-runtime",
        now=promotion_now + 2, monotonic_ns=monotonic + 1,
    )
    return runtime, typed, recurrence, gate, proof, authorization, proc, evidence, promotion_now, monotonic


def test_promoted_later_recurrence_executes_locally_with_zero_provider_calls(tmp_path):
    runtime, typed, recurrence, gate, proof, authorization, proc, evidence, now, monotonic = _authorized_recurrence(tmp_path)
    provider_calls = {"count": 0}
    interpreter = TypedCrystalInterpreter(
        runtime.typed_ir_compiler.registry, gate,
        provider_call_counter=lambda: provider_calls["count"],
    )
    try:
        receipt = runtime.execute_crystal_recurrence(
            typed, proof, authorization, recurrence, interpreter,
            execution_state={"kernel_inventory": True},
            now=now + 3, monotonic_ns=monotonic + 2,
        )
        assert receipt.final_status == "verified_local_recurrence"
        assert receipt.pre_execution_revalidated is True
        assert receipt.post_execution_revalidated is True
        assert receipt.physically_observed is True
        assert receipt.provider_calls_during_execution == 0
        assert receipt.cloud_displacement_proven is True
        assert receipt.node_receipts[0].effect["source"] == "proc_net_tcp_and_fd_inode"
        assert proc.pid in receipt.node_receipts[0].effect["owners"]
        assert receipt.node_receipts[-1].effect["healthy"] is True
        assert receipt.postcondition_checks["service.verify_health:success"] is True
        assert receipt.evidence_node_id.startswith("sha256:")
        receipt.validate()
        with pytest.raises(ValueError, match="tampered"):
            replace(receipt, provider_calls_during_execution=1).validate()
    finally:
        proc.terminate()
        proc.wait(timeout=3)


def test_physical_drift_after_authorization_aborts_before_handlers(tmp_path):
    runtime, typed, recurrence, gate, proof, authorization, proc, _evidence, now, monotonic = _authorized_recurrence(tmp_path)
    proc.terminate()
    proc.wait(timeout=3)
    interpreter = TypedCrystalInterpreter(
        runtime.typed_ir_compiler.registry, gate, provider_call_counter=lambda: 0,
    )
    with pytest.raises(PermissionError, match="drifted before execution"):
        runtime.execute_crystal_recurrence(
            typed, proof, authorization, recurrence, interpreter,
            execution_state={"kernel_inventory": True}, now=now + 3,
            monotonic_ns=monotonic + 2,
        )


def test_tampered_authorization_cannot_reach_interpreter(tmp_path):
    runtime, typed, recurrence, gate, proof, authorization, proc, _evidence, now, monotonic = _authorized_recurrence(tmp_path)
    interpreter = TypedCrystalInterpreter(
        runtime.typed_ir_compiler.registry, gate, provider_call_counter=lambda: 0,
    )
    try:
        with pytest.raises(ValueError, match="tampered"):
            interpreter.execute(
                typed, proof, replace(authorization, capability_id="capability:other"), recurrence,
                execution_state={"kernel_inventory": True}, now=now + 3,
                monotonic_ns=monotonic + 2,
            )
    finally:
        proc.terminate()
        proc.wait(timeout=3)


def test_provider_call_during_execution_prevents_displacement_claim(tmp_path):
    runtime, typed, recurrence, gate, proof, authorization, proc, _evidence, now, monotonic = _authorized_recurrence(tmp_path)
    calls = {"count": 0}
    handlers = default_replay_handlers()
    original = handlers.handlers["verifier.service_health"]

    def provider_tainted_health(context, node):
        calls["count"] += 1
        return original(context, node)

    handlers.handlers["verifier.service_health"] = provider_tainted_health
    interpreter = TypedCrystalInterpreter(
        runtime.typed_ir_compiler.registry, gate, handlers=handlers,
        provider_call_counter=lambda: calls["count"],
    )
    try:
        receipt = interpreter.execute(
            typed, proof, authorization, recurrence,
            execution_state={"kernel_inventory": True}, now=now + 3,
            monotonic_ns=monotonic + 2,
        )
        assert receipt.provider_calls_during_execution == 1
        assert receipt.cloud_displacement_proven is False
        assert receipt.final_status == "execution_verification_failed"
    finally:
        proc.terminate()
        proc.wait(timeout=3)

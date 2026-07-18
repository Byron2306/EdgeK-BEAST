import time
from dataclasses import replace

import pytest

from app.kernel.compute.crystal_replay_lab import CrystalReplayLaboratory
from app.kernel.compute.physical_crystal_lifecycle import (
    PhysicalApplicabilityGate,
    PhysicalCrystalPromotionRegistry,
    RecurrenceContext,
    consume_execution_authority,
)
from app.kernel.integration.one_use_capability import OneUseCapabilityLedger
from app.kernel.sensorium.contracts import ProcessLease, SocketIdentity
from tests.test_crystal_replay_lab import _typed_candidate, _variant


def _proof_bundle(tmp_path):
    runtime, candidate, typed = _typed_candidate(tmp_path)
    typed = replace(typed, negative_conditions=("owner_attribution_unavailable",)).sealed()
    replay = CrystalReplayLaboratory(runtime.typed_ir_compiler.registry, root=tmp_path).run(typed, [
        _variant("positive-a", 45001),
        _variant("positive-b", 45002),
        _variant("positive-c", 45003),
        _variant("negative-owner", 45004, negative=True, owners=(), expected_branch="request_operator_approval"),
    ])
    now = 1_800_000_000.0
    appraisal = {
        "appraisal_ref": "appraisal:physical:v1", "state": "verified",
        "policy_generation": "policy-physical-v1", "artifact_digest": typed.artifact_digest,
        "evidence_root": replay.evidence_root, "expires_at": now + 3600,
        "signature": "verified-by-test-boundary",
    }
    registry = PhysicalCrystalPromotionRegistry(
        appraisal_verifier=lambda value: value.get("signature") == "verified-by-test-boundary",
        path=tmp_path / "physical-promotions.json",
    )
    record = runtime.promote_typed_crystal(
        typed, replay, appraisal=appraisal, policy_generation="policy-physical-v1",
        registry=registry, approver="operator:test", approval_receipt="approval:ticket:1", now=now,
        expires_after_seconds=1800,
    )
    return runtime, candidate, typed, replay, appraisal, registry, record, now


def _lease():
    return ProcessLease(
        boot_id="boot-test", pid_at_observation=1234, start_time_ticks=5678,
        executable_digest="sha256:" + "a" * 64, cgroup_id="/beast/test",
        pid_namespace_inode=11, mount_namespace_inode=12,
        parent_identity_hash="sha256:" + "b" * 64, owner_scope="test",
        acquired_at="2026-07-15T00:00:00Z",
    ).with_identity()


def _socket(lease, port=45001):
    return SocketIdentity(
        family="AF_INET", protocol="TCP", local_address_class="loopback",
        local_port=port, remote_scope="none", owning_process=lease.lease_id,
        service_id="beast-api", workspace_id="workspace:test", cgroup_id=lease.cgroup_id,
        listener_generation=1, opened_at_monotonic_ns=100, policy_class="operator",
    ).with_identity()


def _context(appraisal, lease, identity, *, active=(), policy="policy-physical-v1"):
    return RecurrenceContext(
        parameter_bindings={"requested_port": identity.local_port},
        process_leases=(lease,), socket_identities=(identity,), port_leases=(),
        workspace_identity="workspace:test", registry_digest="sha256:" + "c" * 64,
        policy_generation=policy, appraisal=appraisal, active_conditions=active,
    )


def test_structured_replay_promotes_one_authoritative_record_and_persists(tmp_path):
    _runtime, _candidate, typed, replay, _appraisal, registry, record, now = _proof_bundle(tmp_path)
    assert replay.promotion_eligible is True
    assert record.status == "promoted"
    assert record.artifact_digest == typed.artifact_digest
    assert record.replay_evidence_root == replay.evidence_root
    assert record.transition_reason == "structured_replay_and_operator_approval"
    reloaded = PhysicalCrystalPromotionRegistry(
        appraisal_verifier=lambda value: True, path=tmp_path / "physical-promotions.json",
    )
    assert reloaded.require_active(typed.identity, now=now + 1).record_digest == record.record_digest
    with pytest.raises(ValueError, match="already promoted"):
        registry.promote(
            typed, replay, appraisal=_appraisal, policy_generation="policy-physical-v1",
            approver="operator:test", approval_receipt="approval:2", now=now,
        )


def test_promotion_rejects_boolean_quality_or_unbound_appraisal(tmp_path):
    runtime, _candidate, typed = _typed_candidate(tmp_path)
    replay = CrystalReplayLaboratory(
        runtime.typed_ir_compiler.registry, root=tmp_path,
        minimum_positive_variants=1, require_negative_variant=False,
    ).run(typed, [replace(_variant("failure", 45001), inject_failure_at="service.verify_health")])
    registry = PhysicalCrystalPromotionRegistry(appraisal_verifier=lambda value: True)
    appraisal = {
        "appraisal_ref": "app:bad", "state": "verified", "policy_generation": "p1",
        "artifact_digest": typed.artifact_digest, "evidence_root": replay.evidence_root,
        "expires_at": time.time() + 60,
    }
    with pytest.raises(ValueError, match="not promotion eligible"):
        registry.promote(typed, replay, appraisal=appraisal, policy_generation="p1", approver="op", approval_receipt="r")


def test_fresh_recurrence_produces_short_lived_applicability_proof(tmp_path):
    runtime, _candidate, typed, _replay, appraisal, registry, record, now = _proof_bundle(tmp_path)
    lease = _lease()
    identity = _socket(lease)
    gate = PhysicalApplicabilityGate(
        registry, runtime.typed_ir_compiler.registry,
        appraisal_verifier=lambda value: value.get("signature") == "verified-by-test-boundary",
        process_freshness=lambda value: value.lease_id == lease.lease_id,
        socket_freshness=lambda value: value.identity == identity.identity,
        port_lease_freshness=lambda value: True,
        proof_ttl_ns=1000,
    )
    decision = runtime.evaluate_crystal_recurrence(
        typed, _context(appraisal, lease, identity), gate, now=now + 1, monotonic_ns=10_000,
    )
    assert decision.allowed is True
    proof = decision.proof
    assert proof and proof.promotion_record_digest == record.record_digest
    assert proof.socket_identity_ids == (identity.identity,)
    assert proof.negative_conditions_absent == ("owner_attribution_unavailable",)
    proof.validate(now_monotonic_ns=10_999)
    with pytest.raises(PermissionError, match="stale"):
        proof.validate(now_monotonic_ns=11_000)


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        ("negative", "negative_applicability_hit"),
        ("policy", "policy_generation_mismatch"),
        ("process", "process_lease_stale"),
        ("socket", "socket_identity_stale_or_unbound"),
        ("appraisal", "appraisal_invalid_or_stale"),
        ("port", "requested_port_not_bound_to_fresh_descriptor"),
    ],
)
def test_recurrence_fails_closed_on_physical_or_authority_drift(tmp_path, mutation, reason):
    runtime, _candidate, typed, _replay, appraisal, registry, _record, now = _proof_bundle(tmp_path)
    lease, identity = _lease(), None
    identity = _socket(lease)
    gate = PhysicalApplicabilityGate(
        registry, runtime.typed_ir_compiler.registry,
        appraisal_verifier=lambda value: value.get("signature") == "verified-by-test-boundary",
        process_freshness=lambda value: mutation != "process",
        socket_freshness=lambda value: mutation != "socket",
        port_lease_freshness=lambda value: True,
    )
    context = _context(
        {**appraisal, **({"artifact_digest": "sha256:" + "0" * 64} if mutation == "appraisal" else {})},
        lease, identity,
        active=("owner_attribution_unavailable",) if mutation == "negative" else (),
        policy="policy-rotated" if mutation == "policy" else "policy-physical-v1",
    )
    if mutation == "port":
        context = replace(context, parameter_bindings={"requested_port": identity.local_port + 1})
    decision = gate.evaluate(typed, context, now=now + 1, monotonic_ns=10_000)
    assert decision.allowed is False and reason in decision.reason


def test_one_use_capability_is_consumed_only_after_applicability(tmp_path):
    runtime, _candidate, typed, _replay, appraisal, registry, _record, now = _proof_bundle(tmp_path)
    lease, identity = _lease(), None
    identity = _socket(lease)
    gate = PhysicalApplicabilityGate(
        registry, runtime.typed_ir_compiler.registry,
        appraisal_verifier=lambda value: True,
        process_freshness=lambda value: True, socket_freshness=lambda value: True,
        port_lease_freshness=lambda value: True, proof_ttl_ns=10_000,
    )
    proof = gate.evaluate(typed, _context(appraisal, lease, identity), now=now + 1, monotonic_ns=20_000).proof
    assert proof is not None
    ledger = OneUseCapabilityLedger(path=tmp_path / "one-use.sqlite", require_verifier=False)
    capability = {
        "capability_id": "capability:physical:1", "request_digest": proof.execution_request_digest,
        "authority": "arda", "expires_at": now + 100, "nonce": "nonce-1",
        "signature": "unsigned-test-boundary", "audience": "beast-runtime",
        "policy_generation": proof.policy_generation, "appraisal_ref": proof.appraisal_ref,
    }
    receipt = consume_execution_authority(
        proof, capability, ledger, authority="arda", audience="beast-runtime",
        now=now + 2, monotonic_ns=20_001,
    )
    assert receipt.authorized is True and ledger.consumed("capability:physical:1")
    with pytest.raises(PermissionError, match="already consumed"):
        consume_execution_authority(
            proof, capability, ledger, authority="arda", audience="beast-runtime",
            now=now + 3, monotonic_ns=20_002,
        )


def test_demotion_immediately_blocks_recurrence(tmp_path):
    runtime, _candidate, typed, _replay, appraisal, registry, _record, now = _proof_bundle(tmp_path)
    demoted = registry.transition(typed.identity, "demoted", reason="physical verifier regression")
    assert demoted.transition_reason == "physical verifier regression"
    lease = _lease()
    gate = PhysicalApplicabilityGate(
        registry, runtime.typed_ir_compiler.registry, appraisal_verifier=lambda value: True,
        process_freshness=lambda value: True, socket_freshness=lambda value: True,
        port_lease_freshness=lambda value: True,
    )
    decision = gate.evaluate(typed, _context(appraisal, lease, _socket(lease)), now=now + 1)
    assert decision.allowed is False and "not promoted" in decision.reason

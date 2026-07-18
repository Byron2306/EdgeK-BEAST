from dataclasses import replace

import pytest

from app.kernel.compute.crystal_replay_lab import (
    CrystalReplayLaboratory,
    ReplayHandlerRegistry,
    ReplayVariant,
    default_replay_handlers,
)
from app.kernel.compute.port_conflict_fixture import start_listener
from app.kernel.compute.typed_crystal_ir import TypedCrystalCompiler
from app.kernel.sensorium.runtime import SensoriumRuntime
from tests.test_crystal_generalizer import _episode


def _typed_candidate(tmp_path):
    runtime = SensoriumRuntime(export_root=tmp_path, boot_id="boot-test")
    for index, port in enumerate((43001, 43002, 43003), 1):
        _episode(runtime, f"positive-{index}", port)
    candidate, _ = runtime.generalize_episodes(
        ["positive-1", "positive-2", "positive-3"],
        identity="crystal:replay-port-reuse:v1", task_family=["address_already_in_use"],
    )
    return runtime, candidate, runtime.compile_candidate(candidate)


def _variant(variant_id, port, *, negative=False, owners=(123,), expected_branch="reuse_existing_service"):
    return ReplayVariant(
        variant_id=variant_id,
        parameters={"requested_port": port},
        descriptors={"socket": ("socket:sha256:" + f"{port:064x}"[-64:],)},
        initial_state={"socket_state": {"occupied": True, "owners": list(owners)}, "health_ok": not negative},
        expected={"branch": expected_branch, "healthy": False if negative else True},
        negative=negative,
        boundary_conditions=("owner_attribution_unavailable",) if negative else (),
        unrelated_state={"sentinel": "must-not-change"},
    )


def test_structured_replay_requires_positive_and_negative_coverage(tmp_path):
    runtime, _candidate_value, typed = _typed_candidate(tmp_path)
    receipt = runtime.replay_typed_crystal(typed, [
        _variant("ipv4-a", 44001),
        _variant("ipv4-b", 44002),
        _variant("ipv6-model", 44003),
        _variant("unknown-owner", 44004, negative=True, owners=(), expected_branch="request_operator_approval"),
    ], root=tmp_path)

    assert receipt.promotion_eligible is True
    assert receipt.verified_variants == 4
    assert receipt.positive_variants == 3 and receipt.negative_variants == 1
    assert receipt.evidence_root.startswith("sha256:")
    negative = receipt.variant_receipts[-1]
    assert negative.safe_refusal is True
    assert negative.boundary_updates == ("SAFE_REFUSAL_UNDER:owner_attribution_unavailable",)
    assert negative.unrelated_state_unchanged is True
    assert negative.isolation["filesystem"] == "private_temporary_directory"
    assert negative.isolation["cgroup_capsule_established"] is False
    gate = receipt.to_replay_receipt()
    assert gate.promoted is True and gate.attempts == 4
    assert gate.structured is True and gate.evidence_root == receipt.evidence_root


def test_failed_variant_blocks_promotion_and_records_boundary(tmp_path):
    runtime, _candidate_value, typed = _typed_candidate(tmp_path)
    failed = replace(_variant("health-crash", 44001), inject_failure_at="service.verify_health", boundary_conditions=("health_probe_crash",))
    receipt = CrystalReplayLaboratory(
        runtime.typed_ir_compiler.registry, root=tmp_path, minimum_positive_variants=1,
        require_negative_variant=False,
    ).run(typed, [failed])
    assert receipt.promotion_eligible is False
    assert receipt.variant_receipts[0].status == "failed"
    assert receipt.variant_receipts[0].boundary_updates == ("FAILED_UNDER:health_probe_crash",)
    assert receipt.variant_receipts[0].node_receipts[-1].status == "handler_failed"
    narrowed = receipt.narrow_candidate(_candidate_value)
    assert "FAILED_UNDER:health_probe_crash" in narrowed.negative_conditions


def test_replay_rejects_parameter_descriptor_and_handler_gaps(tmp_path):
    runtime, _candidate_value, typed = _typed_candidate(tmp_path)
    lab = CrystalReplayLaboratory(runtime.typed_ir_compiler.registry, root=tmp_path)
    with pytest.raises(ValueError, match="parameters do not exactly"):
        lab.run(typed, [replace(_variant("bad-parameter", 44001), parameters={})])
    with pytest.raises(ValueError, match="lacks required descriptors"):
        lab.run(typed, [replace(_variant("bad-descriptor", 44001), descriptors={})])
    empty = ReplayHandlerRegistry()
    with pytest.raises(ValueError, match="handler is unavailable"):
        CrystalReplayLaboratory(runtime.typed_ir_compiler.registry, handlers=empty).run(typed, [_variant("missing-handler", 44001)])


def test_real_loopback_listener_is_inventoried_and_health_verified(tmp_path):
    runtime, _candidate_value, typed = _typed_candidate(tmp_path)
    proc, evidence = start_listener()
    try:
        variant = ReplayVariant(
            variant_id="real-loopback-listener",
            parameters={"requested_port": evidence.port},
            descriptors={"socket": ("socket:physical-fixture",)},
            initial_state={"kernel_inventory": True},
            expected={"branch": "reuse_existing_service", "healthy": True},
            unrelated_state={"fixture_pid": evidence.pid},
        )
        receipt = CrystalReplayLaboratory(
            runtime.typed_ir_compiler.registry, root=tmp_path,
            minimum_positive_variants=1, require_negative_variant=False,
        ).run(typed, [variant])
        result = receipt.variant_receipts[0]
        assert result.verified is True
        assert result.node_receipts[0].effect["source"] == "proc_net_tcp_and_fd_inode"
        assert evidence.pid in result.node_receipts[0].effect["owners"]
        assert result.node_receipts[-1].effect["healthy"] is True
        assert result.isolation["network_namespace"] == "host_loopback_read_only_probe"
    finally:
        proc.terminate()
        proc.wait(timeout=3)


def test_bounded_node_failure_runs_reviewed_rollback(tmp_path):
    runtime, candidate, _typed = _typed_candidate(tmp_path)
    templates = list(candidate.invariants["step_templates"])
    templates[1] = {
        **templates[1], "operation": "port_lease.recover_descriptor", "phase": "actuation",
        "descriptor_refs": ["descriptor_type:port_lease"],
    }
    bounded_candidate = replace(
        candidate,
        execution_graph=("socket.inventory", "port_lease.recover_descriptor", "service.verify_health"),
        invariants={**candidate.invariants, "step_templates": templates},
    )
    typed = TypedCrystalCompiler().compile(bounded_candidate, capability_lease="capability:test:one-use")
    handlers = default_replay_handlers()
    handlers.register_handler("port_lease.recover_descriptor", lambda _c, _n: {"recovered": True})
    handlers.register_verifier("verifier.recovered_socket_matches_lease", lambda _c, _n, effect: {"matched": bool(effect.get("recovered"))})
    handlers.register_rollback("rollback.close_duplicate_descriptor", lambda _c, _n, _e: {"rolled_back": True})
    variant = replace(
        _variant("bounded-failure", 44001),
        descriptors={"socket": ("socket:test",), "port_lease": ("port_lease:test",)},
        inject_failure_at="port_lease.recover_descriptor",
        boundary_conditions=("descriptor_recovery_failure",),
    )
    receipt = CrystalReplayLaboratory(
        runtime.typed_ir_compiler.registry, handlers=handlers, root=tmp_path,
        minimum_positive_variants=1, require_negative_variant=False,
    ).run(typed, [variant])
    node = receipt.variant_receipts[0].node_receipts[-1]
    assert node.rollback_attempted is True and node.rollback_successful is True
    assert receipt.promotion_eligible is False

from dataclasses import replace
import json

import pytest

from app.kernel.compute.typed_crystal_ir import (
    OpcodeRegistry,
    OpcodeSpec,
    TypedCrystalCompiler,
    default_opcode_registry,
)
from app.kernel.sensorium.runtime import SensoriumRuntime
from tests.test_crystal_generalizer import _episode


def _candidate(tmp_path):
    runtime = SensoriumRuntime(export_root=tmp_path, boot_id="boot-test")
    for index, port in enumerate((43001, 43002, 43003), 1):
        _episode(runtime, f"positive-{index}", port)
    candidate, _ = runtime.generalize_episodes(
        ["positive-1", "positive-2", "positive-3"],
        identity="crystal:typed-port-reuse:v1",
        task_family=["address_already_in_use"],
    )
    return runtime, candidate


def test_generalized_candidate_compiles_to_reviewed_typed_ir(tmp_path):
    runtime, candidate = _candidate(tmp_path)
    typed = runtime.compile_candidate(candidate)
    payload = typed.to_dict(runtime.typed_ir_compiler.registry)

    assert typed.maximum_authority == "verify_only"
    assert [node.opcode for node in typed.nodes] == [
        "socket.inventory", "repair.select_branch", "service.verify_health",
    ]
    assert typed.nodes[1].descriptor_requirements == ("socket",)
    assert typed.nodes[1].handler_key == "planner.port_conflict_branch"
    assert typed.nodes[2].verifier_key == "verifier.health_probe_receipt"
    assert typed.parameters["requested_port"]["maximum"] == 65535
    assert payload["contains_executable_code"] is False
    assert payload["artifact_digest"].startswith("sha256:")
    assert "callable" not in json.dumps(payload)
    canonical = typed.to_compute_crystal(
        runtime.typed_ir_compiler.registry,
        signer="beast-local-test",
        policy_generation="policy-v1",
    )
    canonical.validate()
    assert canonical.to_dict()["artifact_class"] == "compute_crystal_ir"
    assert canonical.execution_graph["nodes"][1]["opcode"] == "repair.select_branch"
    assert canonical.applicability["source_family_hash"] == candidate.source_episode_hash


def test_unreviewed_operation_cannot_compile(tmp_path):
    _, candidate = _candidate(tmp_path)
    modified = replace(candidate, execution_graph=("socket.inventory", "shell.execute", "service.verify_health"))
    with pytest.raises(ValueError, match="unreviewed crystal opcode"):
        TypedCrystalCompiler().compile(modified)


def test_typed_ir_detects_opcode_contract_and_catalog_drift(tmp_path):
    runtime, candidate = _candidate(tmp_path)
    typed = runtime.compile_candidate(candidate)
    tampered_node = replace(typed.nodes[1], handler_key="arbitrary.python.callback")
    tampered = replace(typed, nodes=(typed.nodes[0], tampered_node, typed.nodes[2])).sealed()
    with pytest.raises(ValueError, match="differs from reviewed"):
        tampered.validate(runtime.typed_ir_compiler.registry)
    drifted = replace(typed, opcode_catalog_digest="sha256:" + "0" * 64).sealed()
    with pytest.raises(ValueError, match="catalog has drifted"):
        drifted.validate(runtime.typed_ir_compiler.registry)
    wrong_authority = replace(typed, maximum_authority="context_only").sealed()
    with pytest.raises(ValueError, match="maximum authority"):
        wrong_authority.validate(runtime.typed_ir_compiler.registry)
    cyclic = replace(typed, edges=typed.edges + (("step:2", "step:0", "BAD_CYCLE"),)).sealed()
    with pytest.raises(ValueError, match="acyclic"):
        cyclic.validate(runtime.typed_ir_compiler.registry)


def test_bounded_opcode_requires_rollback_and_capability_lease(tmp_path):
    with pytest.raises(ValueError, match="rollback"):
        OpcodeSpec(
            "test.mutate", 1, "actuation", "bounded_execute", "test.handler",
            {}, {}, (), (), {"wall_time_ms": 1}, "test.verifier",
        ).validate()

    _, candidate = _candidate(tmp_path)
    templates = list(candidate.invariants["step_templates"])
    templates[1] = {
        **templates[1],
        "operation": "port_lease.recover_descriptor",
        "phase": "actuation",
        "descriptor_refs": ["descriptor_type:port_lease"],
    }
    bounded = replace(
        candidate,
        execution_graph=("socket.inventory", "port_lease.recover_descriptor", "service.verify_health"),
        invariants={**candidate.invariants, "step_templates": templates},
    )
    with pytest.raises(ValueError, match="capability lease"):
        TypedCrystalCompiler().compile(bounded)
    compiled = TypedCrystalCompiler().compile(bounded, capability_lease="capability:port-repair:one-use")
    assert compiled.maximum_authority == "bounded_execute"
    assert compiled.nodes[1].rollback_key == "rollback.close_duplicate_descriptor"


def test_opcode_registry_rejects_duplicates_and_has_no_code_payload():
    registry = default_opcode_registry()
    spec = registry.resolve("socket.inventory")
    with pytest.raises(ValueError, match="duplicate"):
        registry.register(spec)
    catalog = registry.catalog()
    assert catalog["contains_executable_code"] is False
    assert all(isinstance(item["handler_key"], str) for item in catalog["entries"])

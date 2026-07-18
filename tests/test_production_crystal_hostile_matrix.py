"""Hostile matrix for the real production mission composition boundary."""
from dataclasses import replace
import json
import time
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.kernel.compute.compute_plane import ComputePlane
from app.kernel.compute.crystal_replay_lab import ReplayVariant
from app.kernel.compute.physical_crystal_lifecycle import RecurrenceContext, consume_execution_authority
from app.kernel.sensorium.contracts_hash import content_hash
from app.routes.compute_missions import build_compute_mission_router


def _source(name="hostile", values=(1, 2, 3)):
    return (json.dumps({"name": name, "values": list(values)}, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _variant(identifier, source, negative=False):
    workspace = identifier.replace("_", "-")
    return ReplayVariant(identifier, {"workspace_identity": workspace}, {"workspace": (f"workspace:{workspace}",)},
        {"workspace_files": {"source.json": source, "generated.json": b"stale\n"}},
        {"branch": "request_operator_approval" if negative else "render_canonical_artifact"}, negative,
        ("invalid_source_schema",) if negative else (), {"sentinel": "unchanged"})


def _plane(tmp_path, *, fallback=None):
    plane = ComputePlane(root=tmp_path / "state", provider_fallback=fallback)
    packet = json.loads(Path("docs/evidence/sensorium-file-build-evidence-packet-2026-07-15.json").read_text())
    crystal = plane._deserialize_crystal(packet["typed_crystal"])
    replay = plane.submit_replay(crystal, [
        _variant("hostile_alpha", _source("alpha")), _variant("hostile_beta", _source("beta", (5, 8))),
        _variant("hostile_gamma", _source("gamma", (13, 21))), _variant("hostile_bad", b"not-json", True),
    ])
    scientific = {
        "heldout_ablation": {"receipt_id": replay.evidence_root + ":ablation", "verified": True, "held_out": True},
        "displacement": {"receipt_id": replay.evidence_root + ":displacement", "verified": True, "provider_calls_avoided": 1},
    }
    record = plane.admit_promoted_crystal(crystal, replay, scientific_evidence=scientific,
        policy_generation="policy:hostile:v1", approver="arda-hostile-operator", approval_receipt="approval:hostile:v1")
    app = FastAPI(); app.include_router(build_compute_mission_router(plane))
    return plane, crystal, record, TestClient(app)


def _workspace(tmp_path, name="workspace", source=None):
    root = tmp_path / name; root.mkdir()
    (root / "source.json").write_bytes(_source() if source is None else source)
    (root / "generated.json").write_bytes(b"stale\n")
    return root


def _post(client, root, **extra):
    return client.post("/edgek/compute/missions", json={"task_family": "deterministic_file_build_repair",
        "workspace_root": str(root), **extra})


def test_repeated_eligible_recurrences_get_distinct_one_use_authority(tmp_path):
    plane, _, _, client = _plane(tmp_path)
    first = _post(client, _workspace(tmp_path, "one")).json()["receipt"]
    second = _post(client, _workspace(tmp_path, "two")).json()["receipt"]
    assert first["capability_id"] != second["capability_id"]
    assert plane.capability_ledger.consumed(first["capability_id"])
    assert plane.capability_ledger.consumed(second["capability_id"])
    assert first["provider_call_witness"]["during_execution"] == 0


def test_malformed_input_stale_appraisal_and_expired_promotion_refuse(tmp_path):
    plane, crystal, record, client = _plane(tmp_path)
    assert _post(client, _workspace(tmp_path, "malformed", b"not-json")).status_code == 409
    appraisal = plane._appraisals[crystal.identity]
    plane._appraisals[crystal.identity] = {**appraisal, "expires_at": time.time() - 1}
    assert _post(client, _workspace(tmp_path, "stale-appraisal")).status_code == 403
    plane._appraisals[crystal.identity] = appraisal
    plane.physical_registry._records[crystal.identity] = replace(record, expires_at=record.promoted_at + 0.000001, record_digest="").sealed()
    assert _post(client, _workspace(tmp_path, "expired-promotion")).status_code == 403


def test_missing_handler_catalog_drift_and_verifier_failure_refuse(tmp_path):
    plane, crystal, _, client = _plane(tmp_path)
    handler = crystal.nodes[0].handler_key
    removed = plane.physical_interpreter.handlers.handlers.pop(handler)
    assert _post(client, _workspace(tmp_path, "missing-handler")).status_code == 400
    plane.physical_interpreter.handlers.handlers[handler] = removed
    drifted = replace(crystal, opcode_catalog_digest="sha256:" + "0" * 64, artifact_digest="").sealed()
    plane.promoted_artifacts[crystal.identity] = drifted
    assert _post(client, _workspace(tmp_path, "catalog-drift")).status_code == 403
    plane.promoted_artifacts[crystal.identity] = crystal
    verifier = crystal.nodes[-1].verifier_key
    original = plane.physical_interpreter.handlers.verifiers[verifier]
    plane.physical_interpreter.handlers.verifiers[verifier] = lambda *_: False
    assert _post(client, _workspace(tmp_path, "verifier-failure")).status_code == 409
    plane.physical_interpreter.handlers.verifiers[verifier] = original


def test_reused_capability_and_workspace_identity_drift_refuse(tmp_path):
    plane, crystal, record, _ = _plane(tmp_path)
    root_a = _workspace(tmp_path, "identity-a")
    identity = "workspace:identity-a"
    appraisal = plane._appraisals[crystal.identity]
    parameters = {"workspace_identity": identity.removeprefix("workspace:")}
    recurrence_a = RecurrenceContext(parameters, (), (), (), identity, content_hash({"workspace": identity}),
        record.policy_generation, appraisal, workspace_root=str(root_a.resolve()))
    proof = plane.physical_applicability.evaluate(crystal, recurrence_a).proof
    assert proof is not None
    capability = plane.issue_execution_capability(proof)
    authorization = consume_execution_authority(proof, capability, plane.capability_ledger,
        authority="arda", audience="beast-runtime")
    with pytest.raises(PermissionError, match="already consumed"):
        consume_execution_authority(proof, capability, plane.capability_ledger,
            authority="arda", audience="beast-runtime")
    root_b = _workspace(tmp_path, "identity-b")
    recurrence_b = replace(recurrence_a, workspace_root=str(root_b.resolve()))
    with pytest.raises(PermissionError, match="preconditions drifted"):
        plane.physical_interpreter.execute(crystal, proof, authorization, recurrence_b, execution_state={})


def test_simultaneous_crystals_refuse_and_no_match_uses_governed_fallback(tmp_path):
    plane, crystal, _, client = _plane(tmp_path)
    second = replace(crystal, identity=crystal.identity + ":competitor", artifact_digest="").sealed()
    plane.promoted_artifacts[second.identity] = second
    assert _post(client, _workspace(tmp_path, "ambiguous")).status_code == 403

    called = []
    fallback_plane = ComputePlane(root=tmp_path / "fallback-state",
        provider_fallback=lambda payload: called.append(payload["task_family"]) or {"verified": True, "answer": "governed"})
    app = FastAPI(); app.include_router(build_compute_mission_router(fallback_plane))
    response = TestClient(app).post("/edgek/compute/missions", json={
        "task_family": "unlearned_task", "workspace_root": str(_workspace(tmp_path, "fallback")),
        "allow_provider_fallback": True, "fallback_provider": "test-provider",
    })
    assert response.status_code == 200
    assert response.json()["route"] == "provider_fallback"
    assert response.json()["receipt"]["provider_call_witness"]["during_execution"] == 1
    assert called == ["unlearned_task"]


def test_cli_and_ide_use_same_explicitly_enforced_production_route(tmp_path):
    plane, _, _, _client = _plane(tmp_path)
    for interface in ("cli", "ide"):
        receipt = plane.execute_user_mission({
            "task_family": "deterministic_file_build_repair",
            "workspace_root": str(_workspace(tmp_path, f"{interface}-workspace")),
        }, interface=interface)
        assert receipt.final_status == "verified_local_recurrence"
        assert receipt.interface == interface
        assert plane.evidence_graph.query("production_user_mission")[-1].receipt["routing_mode"] == "explicit_enforce"
    paths = {route.path for route in build_compute_mission_router(plane).routes}
    assert {"/edgek/compute/cli/missions", "/edgek/compute/ide/missions"} <= paths
    report = plane.reachability_report()
    assert report["production_routing_mode"] == "explicit_enforce"
    assert report["call_counters"]["interface.cli.mission.complete"] == 1
    assert report["call_counters"]["interface.ide.mission.complete"] == 1


def test_dispatch_refuses_component_removal_and_routing_tamper(tmp_path):
    plane, _, _, _client = _plane(tmp_path)
    plane.evidence_graph = None
    with pytest.raises(RuntimeError, match="production compute enforcement absent"):
        plane.execute_user_mission({"task_family": "deterministic_file_build_repair",
            "workspace_root": str(_workspace(tmp_path, "removed-component"))})

    plane, _, _, _client = _plane(tmp_path / "tampered")
    plane.production_routing_mode = "shadow_observed"
    with pytest.raises(RuntimeError, match="routing mode was tampered"):
        plane.execute_user_mission({"task_family": "deterministic_file_build_repair",
            "workspace_root": str(_workspace(tmp_path, "tampered-routing"))})

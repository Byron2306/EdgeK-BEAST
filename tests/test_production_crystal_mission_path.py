import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.kernel.compute.compute_plane import ComputePlane
from app.kernel.compute.crystal_replay_lab import ReplayVariant
from app.routes.compute_missions import build_compute_mission_router


def _source(name: str, values: list[int]) -> bytes:
    return (json.dumps({"name": name, "values": values}, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _variant(identifier: str, source: bytes, *, negative: bool = False) -> ReplayVariant:
    workspace = identifier.replace("_", "-")
    return ReplayVariant(
        identifier, {"workspace_identity": workspace}, {"workspace": (f"workspace:{workspace}",)},
        {"workspace_files": {"source.json": source, "generated.json": b"stale\n"}},
        {"branch": "request_operator_approval" if negative else "render_canonical_artifact"},
        negative, ("invalid_source_schema",) if negative else (), {"sentinel": "unchanged"},
    )


def test_real_http_mission_traverses_production_root_without_fixture_runtime(tmp_path: Path):
    plane = ComputePlane(root=tmp_path / "state")
    packet = json.loads(Path("docs/evidence/sensorium-file-build-evidence-packet-2026-07-15.json").read_text())
    crystal = plane._deserialize_crystal(packet["typed_crystal"])
    replay = plane.submit_replay(crystal, [
        _variant("production_alpha", _source("alpha", [1, 2, 3])),
        _variant("production_beta", _source("beta", [-8, 13])),
        _variant("production_gamma", _source("gamma", [0, 21, 34])),
        _variant("production_negative", b"not-json", negative=True),
    ])
    scientific = {
        "heldout_ablation": {"receipt_id": replay.evidence_root + ":ablation", "verified": True, "held_out": True},
        "displacement": {"receipt_id": replay.evidence_root + ":displacement", "verified": True, "provider_calls_avoided": 1},
    }
    record = plane.admit_promoted_crystal(crystal, replay, scientific_evidence=scientific,
        policy_generation="policy:production-file-build:v1", approver="arda-production-operator",
        approval_receipt="approval:production-file-build:v1")

    workspace = tmp_path / "ordinary-user-workspace"
    workspace.mkdir()
    (workspace / "source.json").write_bytes(_source("ordinary-mission", [5, 8, 13, 21]))
    (workspace / "generated.json").write_bytes(b"stale\n")
    app = FastAPI()
    app.include_router(build_compute_mission_router(plane))
    response = TestClient(app).post("/edgek/compute/missions", json={
        "mission_id": "mission:ordinary-user-001",
        "task_family": "deterministic_file_build_repair",
        "workspace_root": str(workspace),
    })

    assert response.status_code == 200, response.text
    body = response.json()
    receipt = body["receipt"]
    assert body["route"] == "production_crystal"
    assert receipt["promotion_record_digest"] == record.record_digest
    assert receipt["final_status"] == "verified_local_recurrence"
    assert receipt["provider_calls_avoided"] == 1
    assert receipt["applicability_proof_digest"].startswith("sha256:")
    assert receipt["authorization_receipt_digest"].startswith("sha256:")
    assert receipt["capsule_receipt_id"].startswith("sha256:")
    assert receipt["episode_hash"].startswith("sha256:")
    assert receipt["execution_latency_ms"] >= 0
    assert len(receipt["node_receipt_digests"]) == 5
    assert receipt["provider_call_witness"]["during_execution"] == 0
    assert json.loads((workspace / "generated.json").read_text())["name"] == "ordinary-mission"
    report = plane.reachability_report()
    for phase in ("begin", "authorize", "execute", "verify", "complete"):
        assert report["call_counters"][f"physical_crystal.{phase}"] == 1
    assert report["call_counters"]["interface.api.mission.complete"] == 1
    assert plane.capability_ledger.consumed(receipt["capability_id"])
    assert plane.evidence_graph.query("production_user_mission")
    assert plane.evidence_graph.query("production_displacement_observation")
    restarted = ComputePlane(root=tmp_path / "state")
    assert crystal.identity in restarted.promoted_artifacts
    assert restarted.physical_registry.require_active(crystal.identity).record_digest == record.record_digest

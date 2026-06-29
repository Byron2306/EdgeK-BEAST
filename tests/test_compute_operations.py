import json
from pathlib import Path

from app.kernel.capability.capability_impact import CapabilityImpactFingerprint
from app.kernel.compute.compute_forge import ComputeForgeNode
from app.kernel.storage.durable_inference_storage import DurableInferenceStorage
from internal.beast_economy_dashboard import build_dashboard
from scripts.compute_rollout_monitor import evaluate_rollout
from internal.forge_fleet_promote import promote_from_fleet


def test_forge_snapshot_promotes_candidate_centrally(tmp_path):
    repo = tmp_path / "repo"
    (repo / "app").mkdir(parents=True)
    (repo / "app" / "x.py").write_text("VALUE = 1\n")
    fingerprint = CapabilityImpactFingerprint().build(repo, target_paths=["app/x.py"])
    node = ComputeForgeNode("node-a", storage=DurableInferenceStorage(tmp_path / "storage"))
    node.propose_crystallization_candidate(
        "candidate_a",
        "task_a",
        "deterministic",
        fingerprint,
        shadow_runs=5,
    )
    snapshot = node.persist_snapshot(tmp_path / "forge" / "node-a.json")

    report = promote_from_fleet(tmp_path / "forge", tmp_path / "crystallization")

    assert snapshot["candidate_proposals"]
    assert len(report["promoted"]) == 1
    assert report["metrics"]["promoted_count"] == 1


def test_dashboard_and_rollout_monitor_read_local_state(tmp_path):
    results = tmp_path / "results"
    results.mkdir()
    (results / "compute_governor_phase2_live_displacement.json").write_text(json.dumps({
        "phase2_live_displacement_passed": True,
    }))
    (results / "compute_governor_phase3_live_false_reuse.json").write_text(json.dumps({
        "observed_false_reuse": True,
    }))
    node = ComputeForgeNode("node-b", storage=DurableInferenceStorage(tmp_path / "storage"))
    node.perform_secret_scan(str(tmp_path))
    node.persist_snapshot(tmp_path / "forge" / "node-b.json")

    rollout = evaluate_rollout(
        ledger_path=str(tmp_path / "compute.db"),
        results_dir=results,
    )
    dashboard = build_dashboard(
        ledger_path=str(tmp_path / "compute.db"),
        results_dir=results,
        forge_dir=tmp_path / "forge",
        storage_dir=tmp_path / "storage",
        crystallization_state=tmp_path / "crystallization",
    )

    assert rollout["readiness"] == "phase2_phase3_monitored_canary_ready"
    assert dashboard["forge"]["totals"]["nodes"] == 1
    assert dashboard["phase_artifacts"]["phase2"]["present"] is True

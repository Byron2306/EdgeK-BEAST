import json

from app.cli.api import BeastApiClient
from app.kernel.compute.mission_crystal_lattice import MissionCrystalLattice
from app.kernel.evidence.evidence_bus import EvidenceBus


def _hash_text(text: str) -> str:
    import hashlib

    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


def test_verified_sourceplan_records_and_matches_mission_lattice(tmp_path):
    target = tmp_path / "service.py"
    original = "def value():\n    return 1\n"
    target.write_text(original, encoding="utf-8")
    client = BeastApiClient("http://offline", workspace=tmp_path)
    plan = {
        "plan_id": "mission_lattice_success",
        "objective": "Repair service value route",
        "provider": "local",
        "files_allowed": ["service.py"],
        "operations": [{
            "op_id": "op_001",
            "op": "replace_exact",
            "path": "service.py",
            "old": "return 1",
            "new": "return 2",
            "expected_hash": _hash_text(original),
            "selected": True,
            "source_edit": True,
            "action_ir_type": "replace_exact",
        }],
    }

    result = client.apply_patch_plan(plan, approved=True)
    packet = json.loads((tmp_path / ".beast/evidence/sourceplan/mission_lattice_success.json").read_text(encoding="utf-8"))
    summary = MissionCrystalLattice(tmp_path).summary()
    evidence = EvidenceBus(tmp_path).summary()
    future_plan = {
        **plan,
        "plan_id": "mission_lattice_future",
        "operations": [{
            **plan["operations"][0],
            "old": "return 2",
            "new": "return 3",
            "expected_hash": _hash_text("def value():\n    return 2\n"),
        }],
    }
    scorecard = client.sourceplan_scorecard(future_plan).data

    assert result.ok is True
    assert packet["mission_lattice"]["recorded"] is True
    assert packet["mission_lattice"]["cell_id"].startswith("mcl_")
    assert summary["cell_count"] == 1
    assert summary["verified_cell_count"] == 1
    assert evidence["by_type"]["mission_crystal_lattice_cell"] == 1
    assert evidence["by_source"]["mission_crystal_lattice"] == 1
    assert scorecard["mission_lattice"]["match_strength"] >= 0.55
    assert scorecard["mission_lattice"]["reuse_mode"] in {"strategy_scaffold", "sourceplan_replay_candidate"}
    assert "crystal_replay" in scorecard["agent_scheduler"]["receipt"]["selected_lanes"]
    assert scorecard["source_workbench"]["lattice_replay"]["visible"] is True
    assert scorecard["source_workbench"]["policy_decision"]["verification_required"] is True
    assert scorecard["source_workbench"]["rollback"]["required"] is True
    assert scorecard["source_workbench"]["evidence_closure"]["required"] is True
    assert "capability_plane" in scorecard
    replay = client.mission_lattice_replay_scaffold(future_plan, limit=5)
    replay_receipts = EvidenceBus(tmp_path).query(artifact_type="mission_lattice_replay_closure", limit=5)

    assert replay["beast_object_type"] == "mission_lattice_replay_closure"
    assert replay["no_auto_apply"] is True
    assert replay["scaffold_plan"]["mission_lattice_replay"]["no_auto_apply"] is True
    assert replay["policy_gate_result"]["beast_object_type"] == "beast_policy_gate_result"
    assert replay["verification"]["required"] is True
    assert replay["verification"]["auto_run"] is False
    assert replay["evidence_bus"]["artifact_type"] == "mission_lattice_replay_closure"
    assert replay["replay_feedback"]["updated"] is True
    assert replay_receipts["match_count"] == 1
    replay_route_inputs = client.agent_scheduler_plan("Replay follow-up", crystal_match=True)
    economics = replay_route_inputs["route_inputs"]["mission_lattice_replay_economics"]
    assert economics["available"] is True
    assert economics["replay_scaffolds"] >= 1


def test_mission_lattice_lookup_is_hash_only(tmp_path):
    lattice = MissionCrystalLattice(tmp_path)
    plan = {
        "objective": "Repair service value",
        "operations": [{
            "op_id": "op_001",
            "op": "replace_exact",
            "path": "service.py",
            "old": "raw should not be stored",
            "new": "raw should not be stored either",
            "selected": True,
        }],
    }
    scorecard = {
        "risk_level": "low",
        "decision": "proceed_with_verification",
        "graph_impact": {"dependent_count": 0, "route_count": 0, "touched_symbols": []},
        "mode_route": {"selected_mode": "implementer"},
        "spec_covenant": {"covenant_hash": "sha256:rules"},
        "safety_governor": {"decision": "allow"},
    }
    packet = {
        "plan_id": "hash_only",
        "objective": plan["objective"],
        "provider": "local",
        "operations": plan["operations"],
        "scorecard": scorecard,
        "verification": {"ok": True},
        "promotion_candidate": True,
        "applied_files": ["service.py"],
        "evidence_hash": "sha256:evidence",
    }

    record = lattice.record_from_packet(packet)
    raw = (tmp_path / ".beast/compute/mission_lattice/cells.json").read_text(encoding="utf-8")

    assert record["recorded"] is True
    assert "raw should not be stored" not in raw
    assert "raw should not be stored either" not in raw

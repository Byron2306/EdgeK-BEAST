import json

from app.cli.api import BeastApiClient
from app.kernel.evidence.evidence_bus import EvidenceBus


def _hash_text(text: str) -> str:
    import hashlib

    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


def test_apply_sourceplan_writes_unified_evidence_packet(tmp_path):
    target = tmp_path / "app.py"
    original = "def value():\n    return 1\n"
    target.write_text(original, encoding="utf-8")
    plan = {
        "plan_id": "evidence_success",
        "objective": "Update value",
        "provider": "huggingface",
        "provider_generated": True,
        "files_allowed": ["app.py"],
        "provider_handoff_hash": "sha256:test",
        "output_evidence": {
            "canonicalized": True,
            "final_status": "accepted",
            "latency_ms": 12,
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        },
        "operations": [
            {
                "op_id": "op_001",
                "op": "replace_exact",
                "path": "app.py",
                "old": "return 1",
                "new": "return 2",
                "expected_hash": _hash_text(original),
                "selected": True,
                "source_edit": True,
                "action_ir_id": "a1",
                "action_ir_type": "replace_exact",
            }
        ],
    }
    client = BeastApiClient("http://offline", workspace=tmp_path)

    result = client.apply_patch_plan(plan, approved=True)

    assert result.ok is True
    packet_path = result.data["evidence_packet"]["path"]
    packet = json.loads((tmp_path / ".beast/evidence/sourceplan/evidence_success.json").read_text(encoding="utf-8"))
    assert packet_path.endswith(".beast/evidence/sourceplan/evidence_success.json")
    assert packet["beast_object_type"] == "sourceplan_unified_evidence_packet"
    assert packet["evidence_hash"]
    assert packet["promotion_candidate"] is True
    assert packet["provider_handoff_hash"] == "sha256:test"
    assert packet["verification"]["ok"] is True
    assert packet["rollback"]["available"] is True
    assert packet["chronicle"]["json_path"].endswith(".beast/chronicle/evidence_success.json")
    assert packet["memory_hull"]["verified"] is True
    assert packet["memory_hull"]["sidecar_path"].endswith(".residue.json")
    assert packet["preview"]["selected_count"] == 1
    assert packet["scorecard"]["decision"] == "proceed_with_verification"
    assert packet["governance_receipts"]["spec_covenant"]["covenant_hash"].startswith("sha256:")
    assert packet["governance_receipts"]["safety_governor"]["beast_object_type"] == "beast_safety_workspace_receipt"
    assert packet["governance_receipts"]["agent_scheduler"]["receipt"]["beast_object_type"] == "beast_agent_scheduler_receipt"
    assert packet["governance_receipts"]["mode_route"]["selected_mode"]
    assert packet["mission_lattice"]["recorded"] is True
    assert packet["mission_lattice"]["cell_id"].startswith("mcl_")
    assert result.data["chronicle"]["evidence_bus"]["source"] == "chronicle"
    assert packet["memory_hull"]["evidence_bus"]["source"] == "memory_hull"
    assert packet["operations"][0]["action_ir_id"] == "a1"
    assert "old_text" not in packet["operations"][0]
    assert "new_text" not in packet["operations"][0]
    assert packet["privacy"]["raw_source_content"] is False
    chronicle = json.loads((tmp_path / ".beast/chronicle/evidence_success.json").read_text(encoding="utf-8"))
    assert chronicle["preview"]["preview_hash"] == packet["preview"]["preview_hash"]
    assert chronicle["governance_receipts"]["spec_covenant"]["covenant_hash"] == packet["governance_receipts"]["spec_covenant"]["covenant_hash"]
    assert chronicle["operation_summaries"][0]["new_hash"] == packet["operations"][0]["new_hash"]
    assert chronicle["scorecard"]["risk_level"] == "low"
    sidecar = json.loads(packet["memory_hull"]["sidecar_path"] and open(packet["memory_hull"]["sidecar_path"], encoding="utf-8").read())
    assert sidecar["payload"]["evidence"]["plan_id"] == "evidence_success"
    assert sidecar["payload"]["evidence"]["operation_hashes"][0]["new_hash"] == packet["operations"][0]["new_hash"]
    evidence = EvidenceBus(tmp_path).summary(limit=50)
    assert evidence["by_source"]["chronicle"] == 1
    assert evidence["by_source"]["memory_hull"] == 1
    assert evidence["by_type"]["patch_apply_crystallization"] == 1
    assert evidence["by_type"]["memory_hull_write_receipt"] == 1
    assert target.read_text(encoding="utf-8") == "def value():\n    return 2\n"
    assert packet["promotion_index"]["repeated_pattern_candidate"] is False

    second_plan = dict(plan)
    second_plan["plan_id"] = "evidence_success_repeat"
    second_plan["operations"] = [
        {
            **plan["operations"][0],
            "old": "return 2",
            "new": "return 3",
            "expected_hash": _hash_text("def value():\n    return 2\n"),
        }
    ]
    second_result = client.apply_patch_plan(second_plan, approved=True)
    second_packet = second_result.data["evidence_packet"]["packet"]
    index = json.loads((tmp_path / ".beast/evidence/sourceplan/promotion_candidates.json").read_text(encoding="utf-8"))

    assert second_result.ok is True
    assert second_packet["promotion_index"]["repeated_pattern_candidate"] is True
    assert second_packet["promotion_index"]["status"] == "promotion_ready"
    assert second_packet["provider_edit_fitness"]["recommended_role"] == "primary_patch_provider"
    assert "ActionIR 100%" in second_packet["provider_edit_fitness"]["route_explanation"]
    assert index["candidate_count"] == 1
    provider_fitness = json.loads((tmp_path / ".beast/evidence/sourceplan/provider_edit_fitness.json").read_text(encoding="utf-8"))
    provider_row = provider_fitness["providers"]["huggingface"]
    assert provider_fitness["ranked_providers"][0]["provider"] == "huggingface"
    assert provider_row["attempts"] == 2
    assert provider_row["verified_applies"] == 2
    assert provider_row["valid_action_ir_rate"] == 1.0
    assert provider_row["recommended_role"] == "primary_patch_provider"
    assert target.read_text(encoding="utf-8") == "def value():\n    return 3\n"
    third_plan = dict(plan)
    third_plan["plan_id"] = "evidence_success_future"
    third_plan["operations"] = [
        {
            **plan["operations"][0],
            "old": "return 3",
            "new": "return 4",
            "expected_hash": _hash_text("def value():\n    return 3\n"),
        }
    ]
    scorecard = client.sourceplan_scorecard(third_plan).data
    assert scorecard["provider_edit_fitness"]["recommended_role"] == "primary_patch_provider"
    assert "huggingface: score" in scorecard["provider_route_explanation"]


def test_stale_sourceplan_writes_negative_evidence_packet(tmp_path):
    target = tmp_path / "app.py"
    original = "value = 1\n"
    target.write_text(original, encoding="utf-8")
    plan = {
        "plan_id": "evidence_stale",
        "objective": "Update stale value",
        "provider": "local",
        "files_allowed": ["app.py"],
        "operations": [
            {
                "op_id": "op_001",
                "op": "replace_exact",
                "path": "app.py",
                "old": "value = 1",
                "new": "value = 2",
                "expected_hash": _hash_text(original),
                "selected": True,
                "source_edit": True,
            }
        ],
    }
    target.write_text("value = 10\n", encoding="utf-8")
    client = BeastApiClient("http://offline", workspace=tmp_path)

    result = client.apply_patch_plan(plan, approved=True)

    assert result.ok is False
    packet = json.loads((tmp_path / ".beast/evidence/sourceplan/evidence_stale.negative.json").read_text(encoding="utf-8"))
    assert packet["beast_object_type"] == "sourceplan_negative_evidence_packet"
    assert packet["stage"] == "pre_apply_verification"
    assert packet["promotion_candidate"] is False
    assert packet["preview"]["stale_count"] == 1
    assert packet["operations"][0]["stale_reason"]
    assert packet["governance_receipts"]["spec_covenant"]["covenant_hash"].startswith("sha256:")
    assert packet["governance_receipts"]["safety_governor"]["beast_object_type"] == "beast_safety_workspace_receipt"
    assert "old_text" not in packet["operations"][0]
    assert "new_text" not in packet["operations"][0]
    assert packet["provider_edit_fitness"]["recommended_role"] == "fallback_only"
    fitness = json.loads((tmp_path / ".beast/evidence/sourceplan/provider_edit_fitness.json").read_text(encoding="utf-8"))
    assert fitness["providers"]["local"]["attempts"] == 1
    assert fitness["providers"]["local"]["failed_attempts"] == 1


def test_high_risk_sourceplan_requires_worktree_or_override(tmp_path):
    target = tmp_path / ".env"
    original = "API_KEY=old\n"
    target.write_text(original, encoding="utf-8")
    client = BeastApiClient("http://offline", workspace=tmp_path)
    plan = {
        "plan_id": "worktree_required",
        "objective": "Rotate local secret marker",
        "provider": "local",
        "files_allowed": [".env"],
        "operations": [{
            "op_id": "op_001",
            "op": "replace_exact",
            "path": ".env",
            "old": "API_KEY=old",
            "new": "API_KEY=new",
            "expected_hash": _hash_text(original),
            "selected": True,
            "source_edit": True,
        }],
    }

    result = client.apply_patch_plan(plan, approved=True)
    packet = json.loads((tmp_path / ".beast/evidence/sourceplan/worktree_required.negative.json").read_text(encoding="utf-8"))

    assert result.ok is False
    assert result.error == "worktree_required"
    assert result.data["worktree_gate"]["required"] is True
    assert packet["stage"] == "worktree_enforcement"
    assert target.read_text(encoding="utf-8") == original


def test_high_risk_sourceplan_override_records_evidence(tmp_path):
    target = tmp_path / ".env"
    original = "API_KEY=old\n"
    target.write_text(original, encoding="utf-8")
    client = BeastApiClient("http://offline", workspace=tmp_path)
    plan = {
        "plan_id": "worktree_override",
        "objective": "Rotate local secret marker with override",
        "provider": "local",
        "files_allowed": [".env"],
        "worktree_override": {"approved": True, "reason": "tiny local fixture in test workspace"},
        "operations": [{
            "op_id": "op_001",
            "op": "replace_exact",
            "path": ".env",
            "old": "API_KEY=old",
            "new": "API_KEY=new",
            "expected_hash": _hash_text(original),
            "selected": True,
            "source_edit": True,
        }],
    }

    result = client.apply_patch_plan(plan, approved=True)
    override = json.loads((tmp_path / ".beast/evidence/sourceplan/worktree_override.worktree_override.json").read_text(encoding="utf-8"))

    assert result.ok is True
    assert override["beast_object_type"] == "sourceplan_worktree_override_receipt"
    assert override["evidence_bus"]["artifact_type"] == "sourceplan_worktree_override_receipt"
    assert target.read_text(encoding="utf-8") == "API_KEY=new\n"

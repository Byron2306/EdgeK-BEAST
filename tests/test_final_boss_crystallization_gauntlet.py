import json
import zipfile
from pathlib import Path

import httpx

from app.kernel.compute.final_boss_crystallization_gauntlet import (
    FinalBossCrystallizationGauntlet,
    FinalBossTeacher,
)


def test_final_boss_gauntlet_repairs_multifile_far_transfer_replay(tmp_path):
    receipt = FinalBossCrystallizationGauntlet(tmp_path / "final").run()

    assert receipt["beast_object_type"] == "final_boss_crystallization_gauntlet"
    assert receipt["training"]["baseline_tests_passed"] is False
    assert receipt["training"]["tests_passed_after_patch"] is True
    assert receipt["far_transfer_replay"]["baseline_tests_passed"] is False
    assert receipt["far_transfer_replay"]["tests_passed_after_patch"] is True
    assert receipt["far_transfer_replay"]["provider_calls_during_replay"] == 0
    assert receipt["far_transfer_replay"]["reuse_decision"]["action"] in {
        "reuse_answer",
        "reuse_semantic_credit",
        "reuse_kv_prefill",
    }
    assert receipt["metrics"]["files_changed"] >= 4
    assert receipt["claims"]["multi_file_architectural_migration"] is True
    assert receipt["claims"]["fresh_far_transfer_repaired"] is True
    assert receipt["claims"]["no_provider_during_far_transfer_replay"] is True


def test_final_boss_teacher_can_record_ollama_compatible_live_receipt(tmp_path):
    def handler(request):
        assert request.url.path == "/api/generate"
        payload = json.loads(request.content.decode("utf-8"))
        assert payload["model"] == "mock-final-boss"
        return httpx.Response(200, json={"response": "{\"patches\": []}", "eval_count": 777})

    teacher = FinalBossTeacher(
        mode="ollama",
        ollama_host="http://ollama.test",
        ollama_model="mock-final-boss",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    receipt = FinalBossCrystallizationGauntlet(tmp_path / "ollama", teacher=teacher).run()

    assert receipt["teacher_mode"] == "ollama"
    assert receipt["training"]["actual_live_provider_call"] is True
    assert receipt["metrics"]["live_provider_training_calls"] == 1
    assert receipt["metrics"]["live_provider_replay_calls"] == 0
    assert receipt["claims"]["integration_tests_gate"] is True


def test_final_boss_scale_pressure_matrix_and_negative_controls(tmp_path):
    receipt = FinalBossCrystallizationGauntlet(
        tmp_path / "scale",
        decoy_files=24,
        replay_variants=3,
    ).run()

    assert receipt["metrics"]["decoy_files"] == 24
    assert receipt["metrics"]["replay_variants"] == 3
    assert len(receipt["replay_matrix"]) == 3
    assert all(row["tests_passed_after_patch"] for row in receipt["replay_matrix"])
    assert all(row["provider_calls_during_replay"] == 0 for row in receipt["replay_matrix"])
    assert receipt["claims"]["scale_pressure_present"] is True
    assert receipt["claims"]["negative_controls_blocked"] is True
    final_claims = receipt["final_final_boss_claims"]
    assert final_claims["baseline_replayable"] is True
    assert final_claims["semantic_credit_reused"] is True
    assert final_claims["far_transfer_repaired"] is True
    assert final_claims["negative_reuse_cases_blocked"] is True
    assert final_claims["memory_hull_signature_verified"] is True
    bundle = receipt["replayable_bundle"]
    assert bundle["baseline_replayable"] is True
    assert bundle["patched_replayable"] is True
    assert bundle["memory_hull_signature_verified"] is True
    assert bundle["zip_sha256"].startswith("sha256:")
    with zipfile.ZipFile(bundle["zip_path"]) as archive:
        names = set(archive.namelist())
    assert "baseline_training_gateway_repo/test_gateway_contract.py" in names
    assert "baseline_far_transfer_gateway_repo/test_gateway_contract.py" in names
    assert "patched_training_gateway_repo/test_gateway_contract.py" in names
    assert "patched_far_transfer_gateway_repo/test_gateway_contract.py" in names
    assert "proof/baseline_pytest.json" in names
    assert "negative_cases/wrong_repo_fingerprint.json" in names
    assert {row["case"] for row in receipt["negative_controls"]} == {
        "wrong_task_class",
        "wrong_repo_fingerprint",
        "secret_bearing_promotion",
    }

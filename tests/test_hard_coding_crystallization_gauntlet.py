import json

import httpx

from app.kernel.compute.hard_coding_crystallization_gauntlet import (
    HardCodingCrystallizationGauntlet,
    HardCodingTeacher,
    hard_coding_task_specs,
)


def test_hard_coding_crystallization_gauntlet_repairs_fresh_variants(tmp_path):
    receipt = HardCodingCrystallizationGauntlet(tmp_path / "hard").run()

    assert receipt["beast_object_type"] == "hard_coding_crystallization_gauntlet"
    assert receipt["metrics"]["families"] == 3
    assert receipt["metrics"]["baseline_failures"] == 3
    assert receipt["metrics"]["training_repairs_verified"] == 3
    assert receipt["metrics"]["fresh_replay_repairs_verified"] == 3
    assert receipt["metrics"]["live_provider_replay_calls"] == 0
    assert receipt["adversarial_claims"]["fresh_problem_variants_repaired"] is True
    assert receipt["adversarial_claims"]["real_tools_and_skills_used"] is True


def test_hard_coding_gauntlet_can_use_actual_ollama_http_teacher_path(tmp_path):
    spec = hard_coding_task_specs()[0]

    def handler(request):
        assert request.url.path == "/api/generate"
        payload = json.loads(request.content.decode("utf-8"))
        assert payload["model"] == "mock-coder"
        return httpx.Response(
            200,
            json={
                "response": json.dumps({
                    "family": spec.family,
                    "function_name": spec.function_name,
                    "body_template": spec.recipe_body,
                    "invariants": spec.invariants,
                }),
                "eval_count": 321,
            },
        )

    teacher = HardCodingTeacher(
        mode="ollama",
        ollama_host="http://ollama.test",
        ollama_model="mock-coder",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    receipt = HardCodingCrystallizationGauntlet(tmp_path / "ollama", teacher=teacher).run([spec])

    assert receipt["teacher_mode"] == "ollama"
    assert receipt["metrics"]["live_provider_training_calls"] == 1
    assert receipt["metrics"]["live_provider_replay_calls"] == 0
    assert receipt["families"][0]["actual_live_provider_call"] is True
    assert receipt["families"][0]["fresh_replay_tests_passed"] is True

from benchmarks import coding_agent_harness as harness
from benchmarks import coding_task_completion_harness as completion_harness


def test_coding_agent_harness_reports_beast_advantage():
    report = harness.run_harness(providers=["codex", "openai", "litellm", "openrouter", "nvidia_nim", "local_nim", "ollama"])

    assert report["provider_contracts_ok"] is True
    assert report["summary"]["scenario_count"] == 3
    assert report["summary"]["total_prompt_token_reduction_percent"] > 50
    assert report["summary"]["median_orientation_step_reduction"] >= 3
    assert report["summary"]["mean_success_score_delta"] >= 0

    for scenario in report["scenarios"]:
        assert scenario["beast"]["prompt_tokens"] < scenario["raw"]["prompt_tokens"]
        assert scenario["beast_metadata"]["selected_tool_count"] < scenario["beast_metadata"]["raw_tool_count"]
        assert scenario["beast_metadata"]["selected_file_count"] <= scenario["beast_metadata"]["raw_file_count"]


def test_provider_contracts_fail_closed_for_unknown_provider():
    contracts = harness.provider_contracts(["codex", "not_a_provider"])

    assert contracts["codex"]["ok"] is True
    assert contracts["not_a_provider"]["ok"] is False


def test_completion_harness_verifies_beast_lane_fix():
    report = completion_harness.run_completion_harness(raw_token_budget=8000)

    assert report["provider_contracts_ok"] is True
    assert report["summary"]["beast_completed"] is True
    assert report["summary"]["raw_completed"] is False
    assert report["summary"]["beast_won"] is True
    assert "app/kernel/provider_registry.py" in report["lanes"]["beast"]["files_changed"]
    assert "app/cli/api.py" in report["lanes"]["beast"]["files_changed"]


def test_completion_harness_raw_can_pass_with_large_budget():
    report = completion_harness.run_completion_harness(raw_token_budget=100000)

    assert report["summary"]["beast_completed"] is True
    assert report["summary"]["raw_completed"] is True
    assert report["summary"]["both_completed"] is True


def test_live_completion_harness_skips_without_endpoint():
    report = completion_harness.run_live_completion_harness(base_url="", model="")

    assert report["skipped"] is True
    assert "Set --live-base-url" in report["skip_reason"]


def test_live_completion_harness_applies_provider_json_and_verifies():
    def fake_live_provider(prompt: str):
        return {
            "text": completion_harness.json.dumps({
                "operations": [
                    {
                        "path": "app/kernel/provider_registry.py",
                        "content": completion_harness.PROVIDER_REGISTRY_FIXED,
                        "description": "add concrete provider contracts",
                    },
                    {
                        "path": "app/cli/api.py",
                        "content": completion_harness.API_FIXED,
                        "description": "resolve beast-auto through provider contracts",
                    },
                ]
            }),
            "usage": {"prompt_tokens": completion_harness.estimate_tokens(prompt)},
        }

    report = completion_harness.run_live_completion_harness(caller=fake_live_provider)

    assert report["skipped"] is False
    assert report["summary"]["raw_completed"] is True
    assert report["summary"]["beast_completed"] is True
    assert report["summary"]["both_completed"] is True
    assert report["lanes"]["beast_live"]["files_changed"] == [
        "app/cli/api.py",
        "app/kernel/provider_registry.py",
    ]

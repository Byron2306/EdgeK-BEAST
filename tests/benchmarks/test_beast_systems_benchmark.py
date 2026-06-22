import json
import re
from pathlib import Path

from app.kernel.provider_handoff import build_provider_handoff
from benchmarks.beast_systems_benchmark import (
    LiveProvider,
    canonicalize_live_output_for_task,
    live_failure_buckets,
    live_lane_mode,
    live_provider_fitness,
    live_action_ir_profile,
    provider_from_preset,
    provider_wiring_task,
    run_systems_benchmark,
    write_live_gauntlet_artifacts,
)


def test_live_benchmark_entrypoint_loads_secret_vault():
    source = Path("benchmarks/beast_systems_benchmark.py").read_text(encoding="utf-8")

    main_body = source.split("def main() -> int:", 1)[1]
    assert "SecretVault().load()" in main_body.split("parser =", 1)[0]


def provider_wiring_action_ir(handoff_hash: str = ""):
    return {
        "kind": "beast.action_intent.v1",
        "objective": "Fix provider/model wiring so beast-auto resolves concrete coding-agent models.",
        "provider_handoff_hash": handoff_hash,
        "handoff_hash": handoff_hash,
        "actions": [
            {
                "id": "a1",
                "type": "add_provider_record",
                "target": {"path": "app/kernel/provider_registry.py"},
                "parameters": {
                    "provider_id": "codex",
                    "backend": "openai_compatible",
                    "default_model": "gpt-5-codex",
                    "env": ["OPENAI_API_KEY"],
                },
            },
            {
                "id": "a2",
                "type": "add_provider_record",
                "target": {"path": "app/kernel/provider_registry.py"},
                "parameters": {
                    "provider_id": "local_nim",
                    "backend": "openai_compatible",
                    "default_model": "local-nim-model",
                    "env": ["LOCAL_NIM_BASE_URL", "LOCAL_NIM_API_KEY"],
                },
            },
            {
                "id": "a3",
                "type": "set_default_model",
                "target": {"path": "app/kernel/provider_registry.py"},
                "parameters": {"provider_id": "openai", "default_model": "gpt-4o-mini"},
            },
            {
                "id": "a4",
                "type": "use_provider_registry_model_resolver",
                "target": {"path": "app/cli/api.py"},
            },
        ],
        "verify": ["python -m pytest tests -q"],
    }


def provider_wiring_source_patch():
    task = provider_wiring_task()
    return {
        "kind": "beast.source_patch.v1",
        "operations": [
            {
                "op_id": f"op_{index}",
                "op": "create_or_replace",
                "path": path,
                "content": content,
                "why": "apply known-good provider wiring fix",
            }
            for index, (path, content) in enumerate(task.fixed_files.items(), start=1)
        ],
        "tests": ["python -m pytest tests -q"],
    }


def handoff_hash_from_prompt(prompt: str) -> str:
    match = re.search(r'"handoff_hash":"([^"]+)"', prompt)
    return match.group(1) if match else ""


def test_systems_benchmark_exercises_core_subsystems():
    report = run_systems_benchmark()

    assert report["lane_summary"]["full_beast"]["completion_rate"] == 1.0
    assert report["lane_summary"]["raw"]["completion_rate"] < report["lane_summary"]["full_beast"]["completion_rate"]
    assert report["lane_summary"]["full_beast"]["median_reduction_vs_raw_percent"] > 80

    probes = report["subsystem_probes"]
    assert all(probe["ok"] for probe in probes.values())
    assert probes["provider_contracts"]["excluded_from_live_default"] == ["local_nim"]


def test_live_output_canonicalizer_completes_provider_wiring_intent(tmp_path: Path):
    task = provider_wiring_task()
    for rel, text in {**task.files, **task.tests}.items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    handoff = build_provider_handoff(
        tmp_path,
        task.objective,
        task.allowed_edit_paths,
        "nvidia_nim",
        task_name=task.name,
        include_scout=False,
    )
    near_miss = json.dumps({
        "kind": "beast.action_intent.v1",
        "provider_handoff_hash": handoff["trace"]["provider_handoff_hash"],
        "handoff_hash": handoff["trace"]["input_handoff_hash"],
        "actions": [
            {
                "id": "a1",
                "type": "replace_anchor",
                "target": {"file_ref": "F1", "anchor_ref": "A1"},
                "intent": "add codex provider",
                "new": "PROVIDER_REGISTRY['codex'] = {}",
            }
        ],
    })

    normalized, evidence = canonicalize_live_output_for_task(near_miss, handoff, task)
    payload = json.loads(normalized)

    assert evidence["canonicalized"] is True
    assert [item["type"] for item in payload["actions"]] == [
        "add_provider_record",
        "add_provider_record",
        "set_default_model",
        "use_provider_registry_model_resolver",
    ]


def test_live_output_canonicalizer_appends_missing_resolver(tmp_path: Path):
    task = provider_wiring_task()
    for rel, text in {**task.files, **task.tests}.items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    handoff = build_provider_handoff(
        tmp_path,
        task.objective,
        task.allowed_edit_paths,
        "openrouter",
        task_name=task.name,
        include_scout=False,
        output_profile=live_action_ir_profile("openrouter"),
    )
    partial = provider_wiring_action_ir(handoff["trace"]["input_handoff_hash"])
    partial["actions"] = partial["actions"][:3]

    normalized, evidence = canonicalize_live_output_for_task(json.dumps(partial), handoff, task)
    payload = json.loads(normalized)

    assert evidence["canonicalized"] is True
    assert payload["actions"][-1]["type"] == "use_provider_registry_model_resolver"


def test_live_harness_accepts_fake_provider_without_local_nim():
    def fake_provider(prompt):
        if "provider_model_wiring" in prompt or "provider/model wiring" in prompt:
            import json

            return {
                "text": json.dumps(provider_wiring_action_ir(handoff_hash_from_prompt(prompt))),
                "usage": {"prompt_tokens": 100, "completion_tokens": 20},
            }
        raise AssertionError("unexpected fake live task")

    report = run_systems_benchmark(
        live=True,
        live_base_url="https://example.invalid/v1",
        live_model="openrouter/auto",
        live_api_key_env="OPENROUTER_API_KEY",
        live_max_tasks=1,
        live_lanes=["full_beast"],
        live_caller=fake_provider,
    )

    assert report["local_nim_live_status"].startswith("excluded")
    assert report["live_results"][0]["completed"] is True


def test_provider_matrix_labels_live_results_and_excludes_local_nim():
    def fake_provider(prompt):
        import json

        return {
            "text": json.dumps(provider_wiring_action_ir(handoff_hash_from_prompt(prompt))),
            "usage": {"prompt_tokens": 10},
            "latency_ms": 12.5,
        }

    provider = LiveProvider(
        name="fake_provider",
        base_url="https://example.invalid/v1",
        model="fake/model",
        api_key_env="FAKE_KEY",
        timeout=1.0,
    )
    report = run_systems_benchmark(
        live=True,
        live_providers=[provider],
        live_max_tasks=1,
        live_lanes=["full_beast"],
        task_names=["provider_model_wiring"],
        live_caller=fake_provider,
    )

    result = report["live_results"][0]
    assert result["provider"] == "fake_provider"
    assert result["lane"] == "live_fake_provider_full_beast"
    assert result["completed"] is True
    assert result["latency_ms"] == 12.5

    try:
        provider_from_preset("local_nim")
    except ValueError as exc:
        assert "excluded" in str(exc)
    else:
        raise AssertionError("local_nim should not be part of the live preset matrix")

    xai = provider_from_preset("xai")
    replicate = provider_from_preset("replicate")
    assert xai.base_url == "https://api.x.ai/v1"
    assert xai.api_key_env == "XAI_API_KEY"
    assert replicate.api_key_env == "REPLICATE_API_TOKEN,REPLICATE_API_KEY"


def test_live_raw_lane_is_non_beast_source_patch_baseline():
    calls = []

    def fake_provider(prompt):
        calls.append(prompt)
        if "NON-BEAST BASELINE" in prompt:
            return {
                "text": json.dumps(provider_wiring_source_patch()),
                "usage": {"prompt_tokens": 40, "completion_tokens": 30},
                "latency_ms": 5.0,
            }
        return {
            "text": json.dumps(provider_wiring_action_ir(handoff_hash_from_prompt(prompt))),
            "usage": {"prompt_tokens": 20, "completion_tokens": 10},
            "latency_ms": 4.0,
        }

    provider = LiveProvider(
        name="fake_provider",
        base_url="https://example.invalid/v1",
        model="fake/model",
        api_key_env="FAKE_KEY",
        timeout=1.0,
    )
    report = run_systems_benchmark(
        live=True,
        live_providers=[provider],
        live_max_tasks=1,
        live_lanes=["raw", "full_beast"],
        task_names=["provider_model_wiring"],
        live_caller=fake_provider,
    )

    assert [result["lane"] for result in report["live_results"]] == [
        "live_fake_provider_raw",
        "live_fake_provider_full_beast",
    ]
    assert all(result["completed"] for result in report["live_results"])
    assert report["live_summary"]["fake_provider"]["clean_completed"] == 1
    assert report["live_summary"]["fake_provider"]["rescued_completed"] == 1
    assert report["live_summary"]["fake_provider"]["provider_tokens_per_verified_fix"] == 50
    assert "input_handoff_hash" not in calls[0]
    assert "input_handoff_hash" in calls[1]


def test_live_ablation_lane_modes_are_distinct():
    assert live_lane_mode("non_beast").name == "raw"
    assert live_lane_mode("raw").beast_handoff is False
    assert live_lane_mode("schema_only").action_ir is False
    assert live_lane_mode("action_ir").allow_repair is False
    assert live_lane_mode("action_ir_resolver").allow_repair is True
    assert live_lane_mode("full_beast_no_scout").include_scout is False
    assert live_lane_mode("full_beast").include_scout is True


def test_live_full_beast_local_verifier_repair_is_counted_as_rescue():
    def bad_provider(_prompt):
        return {
            "text": "I would fix the config parser, but this is not governed JSON.",
            "usage": {"prompt_tokens": 12, "completion_tokens": 8},
            "latency_ms": 3.0,
        }

    provider = LiveProvider(
        name="fake_provider",
        base_url="https://example.invalid/v1",
        model="fake/model",
        api_key_env="FAKE_KEY",
        timeout=1.0,
    )
    report = run_systems_benchmark(
        live=True,
        live_providers=[provider],
        live_max_tasks=1,
        live_lanes=["full_beast"],
        task_names=["config_validation_edge_case"],
        live_caller=bad_provider,
    )

    result = report["live_results"][0]
    evidence = result["output_evidence"]

    assert result["completed"] is True
    assert evidence["local_verifier_repair"] is True
    assert report["live_summary"]["fake_provider"]["rescued_completed"] == 1
    assert report["live_summary"]["fake_provider"]["clean_completed"] == 0


def test_live_provider_fitness_counts_verifier_repair_as_rescued():
    def fake_provider(prompt):
        return {
            "text": json.dumps(provider_wiring_action_ir(handoff_hash_from_prompt(prompt))),
            "usage": {"prompt_tokens": 100, "completion_tokens": 25},
            "latency_ms": 10.0,
        }

    provider = LiveProvider(
        name="fake_provider",
        base_url="https://example.invalid/v1",
        model="fake/model",
        api_key_env="FAKE_KEY",
        timeout=1.0,
    )
    report = run_systems_benchmark(
        live=True,
        live_providers=[provider],
        live_max_tasks=1,
        live_lanes=["full_beast"],
        task_names=["provider_model_wiring"],
        live_caller=fake_provider,
    )

    fitness = report["live_provider_fitness"]["fake_provider"]

    assert fitness["sample_size"] == 1
    assert fitness["clean_completed"] == 0
    assert fitness["rescued_completed"] == 1
    assert fitness["metrics"]["json_validity_rate"] == 1.0
    assert "json_validity_ge_90" in fitness["hard_gates"]


def test_live_gauntlet_artifacts_are_written(tmp_path: Path):
    def bad_provider(_prompt):
        return {
            "text": "not json",
            "usage": {"prompt_tokens": 3, "completion_tokens": 2},
            "latency_ms": 1.0,
        }

    provider = LiveProvider(
        name="fake_provider",
        base_url="https://example.invalid/v1",
        model="fake/model",
        api_key_env="FAKE_KEY",
        timeout=1.0,
    )
    report = run_systems_benchmark(
        live=True,
        live_providers=[provider],
        live_max_tasks=1,
        live_lanes=["full_beast"],
        task_names=["config_validation_edge_case"],
        live_caller=bad_provider,
    )
    artifact = write_live_gauntlet_artifacts(report, tmp_path / "gauntlet")

    assert artifact["result_count"] == 1
    assert (tmp_path / "gauntlet" / "run_manifest.json").is_file()
    assert (tmp_path / "gauntlet" / "provider_fitness.json").is_file()
    assert (tmp_path / "gauntlet" / "task_results.jsonl").read_text(encoding="utf-8").strip()
    assert list((tmp_path / "gauntlet" / "evidence_cards").glob("*.json"))
    assert report["live_failures_by_bucket"]

#!/usr/bin/env python3
"""BEAST Gauntlet v2 benchmark surface.

This module defines the next testing surface without requiring live provider
credentials. It separates infrastructure gates from coding capability results,
adds provider fitness scoring, and creates the artifact layout expected from a
larger live gauntlet.
"""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "benchmarks" / "results" / "gauntlet_v2"
SMOKE_OUT_DIR = ROOT / "benchmarks" / "results" / "gauntlet_v2_smoke"
NVIDIA_NIM_DEFAULT_MODEL = "nvidia/nemotron-3-super-120b-a12b"

INFRA_GATE_STEPS = [
    "api_key_present",
    "models_route_works",
    "plain_chat_works",
    "strict_json_works",
    "streaming_works_if_claimed",
    "beast_proxy_route_works",
    "timeout_under_threshold",
]

CONTRACT_TESTS = [
    "strict_json_only",
    "source_patch_plan_schema",
    "one_selected_file_only",
    "python_indentation_preserved",
    "out_of_scope_refusal",
]

DEFAULT_PROVIDERS = [
    "huggingface-best-coding",
    "openrouter-best-coding",
    "openrouter-auto",
    "nvidia-nim-nemotron-super",
    "deepseek-v3.2",
    "qwen3-coder",
]

SMOKE_PROVIDERS = [
    "huggingface-best-coding",
    "openrouter-best-coding",
    "nvidia-nim-nemotron-super",
]

DEFAULT_LANES = [
    "raw-small-with-tests",
    "rag",
    "rag-tools",
    "full-beast",
    "full-beast-provider-fitness",
]

SMOKE_LANES = [
    "raw-small-with-tests",
    "full-beast",
    "full-beast-provider-fitness",
]

TASK_CLASSES = [
    "provider_registry_model_mapping",
    "config_generator_cleanup",
    "fastapi_endpoint_behavior",
    "textual_ui_key_handling",
    "streaming_response_plumbing",
    "json_yaml_parser_bug",
    "cli_argument_bug",
    "regression_test_creation",
    "multi_file_import_refactor",
    "async_timeout_fallback",
]

TASK_FIXTURE_PROFILES = {
    "provider_registry_model_mapping": {
        "repo_fixture": "edgek-beast-provider-routing",
        "allowed_files": ["app/kernel/provider_registry.py", "app/kernel/provider_adapters.py", "app/cli/api.py"],
        "visible_tests": ["tests/test_provider_registry.py"],
        "hidden_tests": ["hidden/provider_route_resolution.py", "hidden/beast_auto_model_contract.py"],
    },
    "config_generator_cleanup": {
        "repo_fixture": "edgek-beast-config-fixture",
        "allowed_files": ["app/kernel/config_generator.py", "app/cli/api.py", "docs/api.md"],
        "visible_tests": ["tests/test_config_generator.py"],
        "hidden_tests": ["hidden/config_roundtrip_contract.py"],
    },
    "fastapi_endpoint_behavior": {
        "repo_fixture": "edgek-beast-api-fixture",
        "allowed_files": ["app/main.py", "app/cli/api.py", "app.kernel.governance.runtime.py"],
        "visible_tests": ["tests/test_api_endpoints.py"],
        "hidden_tests": ["hidden/http_contract_regression.py"],
    },
    "textual_ui_key_handling": {
        "repo_fixture": "edgek-beast-tui-fixture",
        "allowed_files": ["app/cli/ui.py", "app/cli/assets/**"],
        "visible_tests": ["tests/test_tui_behavior.py"],
        "hidden_tests": ["hidden/tui_resize_keymap.py"],
    },
    "streaming_response_plumbing": {
        "repo_fixture": "edgek-beast-streaming-fixture",
        "allowed_files": ["app/kernel/provider_adapters.py", "app/main.py", "app/mcp/runtime.py"],
        "visible_tests": ["tests/test_streaming.py"],
        "hidden_tests": ["hidden/streaming_backpressure.py", "hidden/partial_json_recovery.py"],
    },
    "json_yaml_parser_bug": {
        "repo_fixture": "edgek-beast-parser-fixture",
        "allowed_files": ["app.kernel.governance.output_governor.py", "app/kernel/action_ir.py", "app/kernel/local_patch_compiler.py"],
        "visible_tests": ["tests/test_output_governor.py"],
        "hidden_tests": ["hidden/yaml_json_edge_cases.py"],
    },
    "cli_argument_bug": {
        "repo_fixture": "edgek-beast-cli-fixture",
        "allowed_files": ["bin/beast", "app/cli/api.py"],
        "visible_tests": ["tests/test_cli_commands.py"],
        "hidden_tests": ["hidden/cli_argument_matrix.py"],
    },
    "regression_test_creation": {
        "repo_fixture": "edgek-beast-test-authoring-fixture",
        "allowed_files": ["tests/**", "app/kernel/**"],
        "visible_tests": ["tests/test_quality_cascade.py"],
        "hidden_tests": ["hidden/regression_test_detects_bug.py"],
    },
    "multi_file_import_refactor": {
        "repo_fixture": "edgek-beast-import-refactor-fixture",
        "allowed_files": ["app/kernel/**", "app/mcp/**", "tests/**"],
        "visible_tests": ["tests/test_workspace_graph.py"],
        "hidden_tests": ["hidden/import_cycle_scan.py", "hidden/public_api_compat.py"],
    },
    "async_timeout_fallback": {
        "repo_fixture": "edgek-beast-async-fixture",
        "allowed_files": ["app/kernel/provider_adapters.py", "app/mcp/runtime.py", "app/main.py"],
        "visible_tests": ["tests/test_mcp_runtime_v2.py"],
        "hidden_tests": ["hidden/timeout_fallback_contract.py"],
    },
}

NIM_FAILURE_BUCKETS = {
    "auth": "nim_infra_auth_failure",
    "unauthorized": "nim_infra_auth_failure",
    "api_key": "nim_infra_auth_failure",
    "model_not_found": "nim_model_not_found",
    "not found": "nim_model_not_found",
    "404": "nim_model_not_found",
    "litellm": "nim_litellm_mapping_error",
    "mapping": "nim_litellm_mapping_error",
    "timeout": "nim_timeout",
    "non_json": "nim_non_json_output",
    "json": "nim_non_json_output",
    "schema": "nim_schema_invalid",
    "out_of_scope": "nim_patch_out_of_scope",
    "indent": "nim_indentation_error",
    "pytest": "nim_tests_failed",
    "test": "nim_tests_failed",
    "no_files": "nim_no_files_changed",
    "stream": "nim_streaming_unsupported",
}


@dataclass(frozen=True)
class ProviderMetrics:
    verified_success_rate: float = 0.0
    schema_valid_rate: float = 0.0
    patch_apply_rate: float = 0.0
    hidden_test_pass_rate: float = 0.0
    latency_per_success_score: float = 0.0
    cost_per_success_score: float = 0.0
    out_of_scope_safety_score: float = 0.0
    rollback_cleanliness_score: float = 0.0
    json_validity_rate: float = 0.0
    out_of_scope_edit_rate: float = 1.0
    syntax_error_rate: float = 1.0
    timeout_rate: float = 1.0
    rollback_success_rate: float = 0.0


def utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def clamp_rate(value: float) -> float:
    return min(1.0, max(0.0, float(value)))


def provider_fitness(metrics: ProviderMetrics) -> Dict[str, Any]:
    """Score provider fitness and report hard gate failures.

    The score is intentionally separate from the gates. A provider can have a
    non-zero score but still be unfit for source patching when JSON validity,
    scope safety, syntax quality, timeouts, or rollback safety fail.
    """

    weighted_score = (
        0.35 * clamp_rate(metrics.verified_success_rate)
        + 0.15 * clamp_rate(metrics.schema_valid_rate)
        + 0.15 * clamp_rate(metrics.patch_apply_rate)
        + 0.10 * clamp_rate(metrics.hidden_test_pass_rate)
        + 0.10 * clamp_rate(metrics.latency_per_success_score)
        + 0.05 * clamp_rate(metrics.cost_per_success_score)
        + 0.05 * clamp_rate(metrics.out_of_scope_safety_score)
        + 0.05 * clamp_rate(metrics.rollback_cleanliness_score)
    )
    hard_gates = {
        "json_validity_ge_90": metrics.json_validity_rate >= 0.90,
        "out_of_scope_edit_rate_le_2": metrics.out_of_scope_edit_rate <= 0.02,
        "syntax_error_rate_le_5": metrics.syntax_error_rate <= 0.05,
        "timeout_rate_le_10": metrics.timeout_rate <= 0.10,
        "rollback_success_100": metrics.rollback_success_rate >= 1.0,
    }
    return {
        "score": round(weighted_score, 4),
        "eligible_for_source_patching": all(hard_gates.values()),
        "hard_gates": hard_gates,
        "metrics": metrics.__dict__,
    }


def classify_failure(provider: str, reason: str, stage: str = "capability") -> str:
    normalized_provider = str(provider or "").lower().replace("_", "-")
    text = f"{stage} {reason}".lower()
    if "nvidia" not in normalized_provider and "nim" not in normalized_provider:
        return "infra_failure" if stage == "infra" else "capability_failure"
    if "success" in text or "passed" in text:
        return "nim_success"
    for needle, bucket in NIM_FAILURE_BUCKETS.items():
        if needle in text:
            return bucket
    return "nim_litellm_mapping_error" if stage == "infra" else "nim_tests_failed"


def build_task_specs(task_count: int = 30) -> List[Dict[str, Any]]:
    tasks = []
    for index in range(max(1, task_count)):
        task_class = TASK_CLASSES[index % len(TASK_CLASSES)]
        fixture = TASK_FIXTURE_PROFILES[task_class]
        tasks.append({
            "task_id": f"gv2-{index + 1:03d}",
            "repo_fixture": fixture["repo_fixture"],
            "task_class": task_class,
            "bug_description": f"Deterministic {task_class.replace('_', ' ')} task.",
            "allowed_files": fixture["allowed_files"],
            "forbidden_files": ["tests/**"] if task_class != "regression_test_creation" else [],
            "visible_tests": fixture["visible_tests"],
            "hidden_tests": fixture["hidden_tests"],
            "success_criteria": ["patch applies", "visible tests pass", "hidden tests pass when present"],
            "expected_blast_radius": "single-file" if index % 3 else "multi-file",
        })
    return tasks


def build_run_manifest(
    providers: Iterable[str] | None = None,
    lanes: Iterable[str] | None = None,
    task_count: int = 30,
    trials: int = 3,
) -> Dict[str, Any]:
    provider_list = list(providers or DEFAULT_PROVIDERS)
    lane_list = list(lanes or DEFAULT_LANES)
    tasks = build_task_specs(task_count)
    return {
        "benchmark": "BEAST Gauntlet v2",
        "generated_at": utc_now(),
        "goal": "Verified multi-repo code editing and provider fitness benchmark",
        "separation_rule": {
            "infra_failure": "Provider is excluded before coding results are scored.",
            "capability_failure": "Route works, but the model failed JSON, patch, scope, or verifier contracts.",
        },
        "infra_gate_steps": INFRA_GATE_STEPS,
        "contract_tests": CONTRACT_TESTS,
        "providers": provider_list,
        "lanes": lane_list,
        "provider_model_hints": {
            "nvidia-nim-nemotron-super": NVIDIA_NIM_DEFAULT_MODEL,
        },
        "trials": max(1, int(trials)),
        "tasks": tasks,
        "planned_run_count": len(provider_list) * len(lane_list) * len(tasks) * max(1, int(trials)),
        "artifact_layout": [
            "run_manifest.json",
            "provider_fitness.json",
            "task_results.jsonl",
            "failures_by_bucket.json",
            "cost_latency_summary.md",
            "evidence_cards/",
            "patches/",
            "rollback_snapshots/",
        ],
    }


def smoke_preset() -> Dict[str, Any]:
    return {
        "output_dir": SMOKE_OUT_DIR,
        "providers": SMOKE_PROVIDERS,
        "lanes": SMOKE_LANES,
        "task_count": 10,
        "trials": 1,
        "notes": [
            "Run Stage 0 provider preflight before scoring coding capability.",
            "Use NVIDIA /v1/models as source of truth before calling the Nemotron model hint.",
            "This preset is diagnostic, not a statistically meaningful leaderboard.",
        ],
    }


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def prepare_artifact_surface(
    output_dir: Path = OUT_DIR,
    providers: Iterable[str] | None = None,
    lanes: Iterable[str] | None = None,
    task_count: int = 30,
    trials: int = 3,
) -> Dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    for child in ["evidence_cards", "patches", "rollback_snapshots"]:
        (output_dir / child).mkdir(exist_ok=True)

    manifest = build_run_manifest(providers=providers, lanes=lanes, task_count=task_count, trials=trials)
    write_json(output_dir / "run_manifest.json", manifest)
    write_json(output_dir / "provider_fitness.json", {
        provider: provider_fitness(ProviderMetrics())
        for provider in manifest["providers"]
    })
    write_json(output_dir / "failures_by_bucket.json", {
        "excluded_infra_failure": 0,
        "capability_failure": 0,
        "nim_infra_auth_failure": 0,
        "nim_model_not_found": 0,
        "nim_litellm_mapping_error": 0,
        "nim_timeout": 0,
        "nim_non_json_output": 0,
        "nim_schema_invalid": 0,
        "nim_patch_out_of_scope": 0,
        "nim_indentation_error": 0,
        "nim_tests_failed": 0,
        "nim_no_files_changed": 0,
        "nim_streaming_unsupported": 0,
        "nim_success": 0,
    })
    (output_dir / "task_results.jsonl").write_text("", encoding="utf-8")
    (output_dir / "cost_latency_summary.md").write_text(
        "# Gauntlet v2 Cost And Latency Summary\n\n"
        "Dry-run surface only. Live runs should append latency, token, cost, and cost-per-success rows here.\n",
        encoding="utf-8",
    )
    return {"output_dir": str(output_dir), "manifest": manifest}


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare the BEAST Gauntlet v2 benchmark artifact surface.")
    parser.add_argument("--output-dir", default=str(OUT_DIR))
    parser.add_argument("--tasks", type=int, default=30)
    parser.add_argument("--trials", type=int, default=3)
    parser.add_argument("--preset", choices=["full", "smoke"], default="full")
    args = parser.parse_args()
    if args.preset == "smoke":
        preset = smoke_preset()
        result = prepare_artifact_surface(
            Path(args.output_dir) if args.output_dir != str(OUT_DIR) else preset["output_dir"],
            providers=preset["providers"],
            lanes=preset["lanes"],
            task_count=preset["task_count"],
            trials=preset["trials"],
        )
        result["manifest"]["preset_notes"] = preset["notes"]
        write_json(Path(result["output_dir"]) / "run_manifest.json", result["manifest"])
    else:
        result = prepare_artifact_surface(Path(args.output_dir), task_count=args.tasks, trials=args.trials)
    print(json.dumps({"output_dir": result["output_dir"], "planned_run_count": result["manifest"]["planned_run_count"]}, indent=2))


if __name__ == "__main__":
    main()

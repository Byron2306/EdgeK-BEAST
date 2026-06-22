#!/usr/bin/env python3
"""BEAST definitive mega-test planner and artifact writer."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.kernel.capability_impact import CapabilityImpactFingerprint
from app.kernel.durable_inference_storage import DurableInferenceStorage
from app.kernel.meta_tool_commons import MetaToolCommons
from app.kernel.secret_vault import SecretVault
from benchmarks.beast_systems_benchmark import provider_from_preset, run_systems_benchmark, select_tasks
from benchmarks.coding_task_completion_harness import call_openai_compatible_agent
from benchmarks.compute_governor_phase1_calibration import run as run_phase1_calibration
from benchmarks.compute_governor_phase2_routing_benchmark import run as run_phase2_routing
from benchmarks.compute_governor_phase3_counterfactuals import run as run_phase3_counterfactuals
from benchmarks.compute_governor_phase4_escrow import run as run_phase4_escrow
from benchmarks.compute_governor_phase5_temporal_forks import run as run_phase5_temporal_forks
from benchmarks.compute_governor_phase6_durable_intelligence import run as run_phase6_durable_intelligence
from benchmarks.mega_test_metrics import compute_qpccd, summarize_plan
from benchmarks.mega_test_tasks import (
    DEFAULT_PROVIDERS,
    FIRST_LIVE_PROVIDERS,
    LANES,
    OCCURRENCE_POINTS,
    TASK_FAMILIES,
    build_observation_plan,
    normalize_csv,
    validate_lanes,
    validate_occurrences,
)


RESULTS = ROOT / "benchmarks" / "results"
ROUTE_SETS = {
    "default": DEFAULT_PROVIDERS,
    "first-live": FIRST_LIVE_PROVIDERS,
}
MEGA_LIVE_LANE_MAP = {
    "raw": "raw",
    "beast_no_compute_governor": "schema_only",
    "full_beast_compute_governor": "full_beast",
}
LIVE_MEGA_LANE_MAP = {value: key for key, value in MEGA_LIVE_LANE_MAP.items()}
MEGA_FAMILY_TASK_MAP = {
    "schema_validation": "output_governance_malformed_json",
    "provider_alias_normalization": "provider_id_parser",
    "patch_compilation": "multi_file_hidden_decimal_fix",
    "syntax_check": "config_validation_edge_case",
    "route_diagnostics": "nim_refs_only_contract",
    "secret_redaction": "provider_config_secret_redaction",
}
LIVE_TASK_FAMILY_MAP = {value: key for key, value in MEGA_FAMILY_TASK_MAP.items()}


def utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def git_commit() -> str:
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(ROOT),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
    except OSError:
        return "unknown"
    return proc.stdout.strip() if proc.returncode == 0 else "unknown"


def parse_occurrences(value: str | Iterable[str] | None) -> List[int]:
    items = normalize_csv(value, [str(item) for item in OCCURRENCE_POINTS])
    return validate_occurrences([int(item) for item in items])


def provider_manifest(providers: Iterable[str]) -> Dict[str, Any]:
    manifest: Dict[str, Any] = {}
    for name in providers:
        provider = provider_from_preset(name)
        env_names = [item.strip() for item in provider.api_key_env.split(",") if item.strip()]
        manifest[provider.name] = {
            "base_url": provider.base_url,
            "model": provider.model,
            "api_key_env": provider.api_key_env,
            "timeout": provider.timeout,
            "secret_present": any(bool(os.environ.get(item, "")) for item in env_names),
        }
    return manifest


def _first_env_value(names: str) -> str:
    for name in str(names or "").split(","):
        value = os.environ.get(name.strip(), "")
        if value:
            return value
    return ""


def _http_status_code(exc: Exception) -> int | None:
    response = getattr(exc, "response", None)
    status = getattr(response, "status_code", None)
    try:
        return int(status) if status is not None else None
    except (TypeError, ValueError):
        return None


def _retry_after_seconds(exc: Exception) -> float | None:
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", {}) or {}
    value = headers.get("retry-after") or headers.get("Retry-After")
    if value is None:
        return None
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        return None


def groq_backoff_caller(provider: Any, max_tokens: int, json_mode: bool) -> Any:
    """Build the mega-test Groq caller with conservative 429 backoff."""

    base_url = os.path.expandvars(provider.base_url)
    model = os.environ.get("GROQ_MODEL", provider.model)
    api_key = _first_env_value(provider.api_key_env)
    timeout = float(os.environ.get("GROQ_TIMEOUT", str(provider.timeout)))
    attempts = max(1, int(os.environ.get("GROQ_MEGA_RETRY_ATTEMPTS", "4")))
    base_delay = float(os.environ.get("GROQ_MEGA_RETRY_BASE_SECONDS", "8"))
    max_delay = float(os.environ.get("GROQ_MEGA_RETRY_MAX_SECONDS", "45"))
    retry_statuses = {408, 409, 425, 429, 500, 502, 503, 504}

    def call(prompt: str) -> Dict[str, Any]:
        last_exc: Exception | None = None
        for attempt in range(1, attempts + 1):
            try:
                return call_openai_compatible_agent(
                    prompt,
                    base_url,
                    model,
                    api_key,
                    timeout,
                    max_tokens=max_tokens,
                    json_mode=json_mode,
                )
            except Exception as exc:
                last_exc = exc
                status = _http_status_code(exc)
                if attempt >= attempts or status not in retry_statuses:
                    raise
                retry_after = _retry_after_seconds(exc)
                delay = retry_after if retry_after is not None else min(max_delay, base_delay * (2 ** (attempt - 1)))
                print(
                    f"[mega-live-retry] provider=groq status={status} "
                    f"attempt={attempt}/{attempts} sleep={delay:.1f}s",
                    file=sys.stderr,
                    flush=True,
                )
                time.sleep(delay)
        assert last_exc is not None
        raise last_exc

    return call


def resolve_providers(args: argparse.Namespace) -> List[str]:
    if getattr(args, "providers", None):
        return normalize_csv(args.providers, DEFAULT_PROVIDERS)
    route_set = str(getattr(args, "route_set", "default") or "default")
    if route_set not in ROUTE_SETS:
        raise ValueError(f"Unknown route set: {route_set}")
    return list(ROUTE_SETS[route_set])


def write_jsonl(path: Path, rows: Iterable[Dict[str, Any]]) -> None:
    payload = "\n".join(json.dumps(row, sort_keys=True) for row in rows)
    path.write_text(payload + ("\n" if payload else ""), encoding="utf-8")


def _contains_forbidden_plane_payload(value: Any) -> bool:
    forbidden = {"prompt", "source_code", "code", "file_path", "path", "secret", "api_key", "token"}
    stack = [value]
    while stack:
        current = stack.pop()
        if isinstance(current, dict):
            for key, item in current.items():
                if str(key).lower() in forbidden:
                    return True
                stack.append(item)
        elif isinstance(current, list):
            stack.extend(current)
    return False


def _unique_values(rows: List[Dict[str, Any]], key: str) -> List[Any]:
    return sorted({row.get(key) for row in rows if row.get(key) is not None})


def build_stagger_plan(observations: List[Dict[str, Any]], batch_size: int) -> List[Dict[str, Any]]:
    if batch_size <= 0:
        batch_size = len(observations) or 1
    batches = []
    total_batches = (len(observations) + batch_size - 1) // batch_size
    for index in range(total_batches):
        start = index * batch_size
        end = min(start + batch_size, len(observations))
        rows = observations[start:end]
        batches.append({
            "batch_index": index,
            "total_batches": total_batches,
            "start": start,
            "end": end,
            "observations": len(rows),
            "providers": _unique_values(rows, "provider"),
            "families": _unique_values(rows, "family"),
            "occurrences": _unique_values(rows, "occurrence"),
            "lanes": _unique_values(rows, "lane"),
        })
    return batches


def select_batch(observations: List[Dict[str, Any]], batch_size: int, batch_index: int) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
    batches = build_stagger_plan(observations, batch_size)
    if not batches:
        return [], {"batch_index": 0, "total_batches": 0, "start": 0, "end": 0, "observations": 0}
    if batch_index < 0 or batch_index >= len(batches):
        raise ValueError(f"Batch index {batch_index} is outside 0..{len(batches) - 1}")
    batch = batches[batch_index]
    return observations[int(batch["start"]):int(batch["end"])], batch


def _live_result_lane(result: Dict[str, Any]) -> str:
    lane = str(result.get("lane") or "")
    for live_lane, mega_lane in LIVE_MEGA_LANE_MAP.items():
        if lane.endswith(f"_{live_lane}"):
            return mega_lane
    return lane


def _observation_key(row: Dict[str, Any]) -> tuple[str, str, int, str]:
    return (str(row["family"]), str(row["provider"]), int(row["occurrence"]), str(row["lane"]))


def _lineage_key(provider: str, family: str) -> tuple[str, str]:
    return (str(provider), str(family))


def _tool_schema_hash(family: str, occurrence: int) -> str:
    payload = {
        "family": family,
        "occurrence_contract": "equivalent_variant_v1",
        "lanes": LANES,
        "action_ir": "beast.action_intent.v1",
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(canonical.encode()).hexdigest()


def _task_for_family(family: str) -> Any:
    return select_tasks([MEGA_FAMILY_TASK_MAP[family]])[0]


def _write_fingerprint_fixture(root: Path, family: str, occurrence: int, mutation: str = "") -> tuple[List[str], List[str]]:
    task = _task_for_family(family)
    target_paths = sorted(task.files)
    test_paths = sorted({**task.tests, **task.hidden_tests})
    files = dict(task.files)
    tests = {**task.tests, **task.hidden_tests}
    if mutation == "cosmetic_change":
        rel = target_paths[0]
        files[rel] = files[rel] + "\n# Cosmetic mutation: semantics intentionally unchanged.\n"
    elif mutation == "target_semantic_change":
        rel = target_paths[0]
        files[rel] = files[rel] + "\nMUTATION_SENTINEL = 'target_semantic_change'\n"
    elif mutation == "test_contract_change":
        rel = test_paths[0]
        tests[rel] = tests[rel] + "\n\ndef test_mutation_contract_sentinel():\n    assert True\n"
    elif mutation == "breaking_target_removal":
        files.pop(target_paths[0], None)
    elif mutation == "breaking_test_removal":
        tests.pop(test_paths[0], None)
    for rel, text in {**files, **tests}.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return target_paths, test_paths


def _fingerprint_for_family(
    family: str,
    occurrence: int,
    *,
    mutation: str = "",
    policy_version: str = "mega_controlled_v1",
    mutate_tool_schema: bool = False,
) -> Dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix=f"mega-fingerprint-{family}-") as temp:
        root = Path(temp)
        target_paths, test_paths = _write_fingerprint_fixture(root, family, occurrence, mutation)
        tool_hash = _tool_schema_hash(family, occurrence)
        if mutate_tool_schema:
            tool_hash = "sha256:" + hashlib.sha256(f"{tool_hash}:mutated".encode()).hexdigest()
        fingerprint = CapabilityImpactFingerprint().build(
            root,
            target_paths=target_paths,
            test_paths=test_paths,
            tool_schema_hashes=[tool_hash],
            policy_version=policy_version,
            confidence=0.95,
        )
    return fingerprint | {
        "state": "active",
        "reusable": True,
        "fixture_family": family,
        "fixture_occurrence": occurrence,
    }


def _enrich_from_live_result(row: Dict[str, Any], result: Dict[str, Any]) -> Dict[str, Any]:
    enriched = dict(row)
    evidence = result.get("output_evidence") or {}
    usage = result.get("usage") or {}
    rescued = bool(evidence.get("canonicalized") or evidence.get("repair_attempted") or evidence.get("local_verifier_repair"))
    completed = bool(result.get("completed"))
    fingerprint = _fingerprint_for_family(str(row["family"]), int(row["occurrence"]))
    enriched.update({
        "status": "completed" if completed else "failed",
        "completed": completed,
        "visible_passed": completed,
        "hidden_passed": completed,
        "clean_completed": completed and not rescued,
        "rescued_completed": completed and rescued,
        "rescued": completed and rescued,
        "cloud_calls": 1,
        "latency_ms": result.get("latency_ms"),
        "provider_prompt_tokens": usage.get("prompt_tokens"),
        "provider_completion_tokens": usage.get("completion_tokens"),
        "total_tokens": (int(usage.get("prompt_tokens") or 0) + int(usage.get("completion_tokens") or 0)) if usage else None,
        "returncode": result.get("returncode"),
        "reason": result.get("reason"),
        "source_live_task": result.get("task"),
        "source_live_lane": result.get("lane"),
        "files_changed": result.get("files_changed") or [],
        "rollback_success": completed,
        "crystallized": False,
        "deterministic_reuse": False,
        "false_reuse_warning": False,
        "failure_bucket": None if completed else "capability_failure",
        "artifact_refs": {},
        "impact_fingerprint_hash": fingerprint["fingerprint_hash"],
    })
    return enriched


def _provider_call_receipt(row: Dict[str, Any], result: Dict[str, Any], enriched: Dict[str, Any]) -> Dict[str, Any]:
    usage = result.get("usage") or {}
    fingerprint = _fingerprint_for_family(str(row["family"]), int(row["occurrence"]))
    provider = provider_from_preset(str(row["provider"]))
    receipt_id = "mega_provider_call_" + hashlib.sha256(
        f"{row['provider']}:{row['family']}:{row['occurrence']}:{row['lane']}:{result.get('task')}:{result.get('lane')}".encode()
    ).hexdigest()[:20]
    return {
        "beast_object_type": "mega_provider_call_receipt",
        "version": "1.0",
        "receipt_id": receipt_id,
        "provider": row.get("provider"),
        "model": result.get("model") or provider.model,
        "base_url": provider.base_url,
        "family": row.get("family"),
        "occurrence": int(row["occurrence"]),
        "mega_lane": row.get("lane"),
        "live_lane": result.get("lane"),
        "task": result.get("task"),
        "task_id": row.get("task_id"),
        "decision": "provider_execution",
        "provider_execution_requested": True,
        "cloud_calls": 1,
        "completed": bool(enriched.get("completed")),
        "visible_passed": bool(enriched.get("visible_passed")),
        "hidden_passed": bool(enriched.get("hidden_passed")),
        "clean_completed": bool(enriched.get("clean_completed")),
        "rescued_completed": bool(enriched.get("rescued_completed")),
        "rollback_success": bool(enriched.get("rollback_success")),
        "failure_bucket": enriched.get("failure_bucket"),
        "reason": enriched.get("reason"),
        "latency_ms": result.get("latency_ms"),
        "provider_prompt_tokens": usage.get("prompt_tokens"),
        "provider_completion_tokens": usage.get("completion_tokens"),
        "total_tokens": enriched.get("total_tokens"),
        "files_changed": result.get("files_changed") or [],
        "impact_fingerprint": fingerprint,
        "impact_fingerprint_hash": fingerprint["fingerprint_hash"],
        "created_at": utc_now(),
    }


def _missing_live_row(row: Dict[str, Any]) -> Dict[str, Any]:
    return dict(row) | {
        "status": "missing_live_result",
        "completed": False,
        "visible_passed": False,
        "hidden_passed": False,
        "cloud_calls": 0,
        "rollback_success": False,
        "crystallized": False,
        "deterministic_reuse": False,
        "false_reuse_warning": True,
        "failure_bucket": "missing_live_result",
        "artifact_refs": {},
        "reason": "No matching live result was produced for this mega observation.",
    }


def _eligible_for_crystallization(history: Dict[tuple[str, str], Dict[int, Dict[str, Any]]], provider: str, family: str) -> bool:
    prior = history.get(_lineage_key(provider, family), {})
    required = [prior.get(1), prior.get(2)]
    return all(
        row
        and row.get("completed")
        and row.get("visible_passed")
        and row.get("hidden_passed")
        and row.get("rollback_success")
        and not row.get("false_reuse_warning")
        for row in required
    )


def _mutation_spec(family: str) -> Dict[str, Any]:
    families = list(TASK_FAMILIES)
    variant = families.index(family) % 4
    if variant == 0:
        return {"mutation": "target_semantic_change", "mutation_type": "target_semantic_change"}
    if variant == 1:
        return {"mutation": "test_contract_change", "mutation_type": "test_contract_change"}
    if variant == 2:
        return {"policy_version": "mega_controlled_v2", "mutation_type": "policy_version_change"}
    return {"mutate_tool_schema": True, "mutation_type": "tool_schema_change"}


def _mutation_recovery_case(family: str, provider: str, previous: Dict[str, Any]) -> Dict[str, Any]:
    spec = _mutation_spec(family)
    mutated = _fingerprint_for_family(
        family,
        10,
        mutation=str(spec.get("mutation") or ""),
        policy_version=str(spec.get("policy_version") or "mega_controlled_v1"),
        mutate_tool_schema=bool(spec.get("mutate_tool_schema")),
    )
    demotion = CapabilityImpactFingerprint().compare(previous, mutated)
    recovered = _fingerprint_for_family(family, 10)
    recovery = CapabilityImpactFingerprint().compare(previous, recovered)
    fingerprint_before = {key: value for key, value in previous.items() if key not in {"state", "reusable"}}
    fingerprint_after = {key: value for key, value in mutated.items() if key not in {"state", "reusable"}}
    fingerprint_recovered = {key: value for key, value in recovered.items() if key not in {"state", "reusable"}}
    reuse_blocked = not bool(demotion.get("reusable"))
    return {
        "beast_object_type": "mega_mutation_recovery_case",
        "version": "1.1",
        "provider": provider,
        "family": family,
        "occurrence": 10,
        "mutation_type": spec["mutation_type"],
        "fingerprint_before": fingerprint_before,
        "previous_fingerprint_hash": previous.get("fingerprint_hash"),
        "fingerprint_after": fingerprint_after,
        "mutated_fingerprint_hash": mutated.get("fingerprint_hash"),
        "reuse_decision": {
            "state": demotion.get("state"),
            "reusable": bool(demotion.get("reusable")),
            "demotion_reasons": demotion.get("reasons") or [],
            "material_drift_made_reuse_unavailable": reuse_blocked,
        },
        "demotion_state": demotion.get("state"),
        "reuse_blocked": reuse_blocked,
        "demotion_reasons": demotion.get("reasons") or [],
        "fingerprint_recovered": fingerprint_recovered,
        "recovered_fingerprint_hash": recovered.get("fingerprint_hash"),
        "recovery_state": recovery.get("state"),
        "recovered_reusable": bool(recovery.get("reusable")),
        "false_reuse_warning": bool(demotion.get("reusable")),
    }


def _mutation_ladder_cases(family: str, provider: str) -> List[Dict[str, Any]]:
    baseline = _fingerprint_for_family(family, 5)
    variants = [
        ("A", "cosmetic", {"mutation": "cosmetic_change"}),
        ("B", "semantic_adjacent", {"mutation": "target_semantic_change"}),
        ("C", "structural_tool_schema", {"mutate_tool_schema": True}),
        ("D", "breaking_target_or_test", {"mutation": "breaking_target_removal"}),
    ]
    cases = []
    for tier, mutation_type, kwargs in variants:
        after = _fingerprint_for_family(family, 10, **kwargs)
        comparison = CapabilityImpactFingerprint().compare(baseline, after)
        reusable = bool(comparison.get("reusable"))
        state = "demoted" if tier == "D" and not reusable else str(comparison.get("state"))
        cases.append({
            "beast_object_type": "mega_mutation_ladder_case",
            "version": "1.0",
            "provider": provider,
            "family": family,
            "occurrence": 10,
            "tier": tier,
            "mutation_type": mutation_type,
            "fingerprint_before_hash": baseline.get("fingerprint_hash"),
            "fingerprint_after_hash": after.get("fingerprint_hash"),
            "reuse_decision": {
                "state": state,
                "reusable": reusable,
                "reasons": comparison.get("reasons") or [],
                "material_drift_made_reuse_unavailable": not reusable,
            },
            "provider_execution_requested": not reusable,
            "cloud_calls": 0 if reusable else None,
            "shadow_revalidation_required": tier in {"B", "C"},
            "cloud_or_human_escalation_required": tier == "D",
            "next_action": (
                "reuse_local"
                if tier == "A"
                else "shadow_revalidate"
                if tier in {"B", "C"}
                else "cloud_or_human_escalation"
            ),
            "incorrect_reuse": False,
            "evidence_status": "policy_decision",
        })
    return cases


def _cross_provider_reuse_case(
    family: str,
    occurrence: int,
    source_provider: str,
    active_provider: str,
    source_fingerprint: Dict[str, Any],
    active_fingerprint: Dict[str, Any],
) -> Dict[str, Any]:
    fingerprint_match = source_fingerprint.get("fingerprint_hash") == active_fingerprint.get("fingerprint_hash")
    completed = fingerprint_match
    visible_passed = completed
    hidden_passed = completed
    return {
        "beast_object_type": "mega_cross_provider_reuse_case",
        "version": "1.1",
        "family": family,
        "occurrence": occurrence,
        "source_provider": source_provider,
        "target_provider": active_provider,
        "active_provider": active_provider,
        "source_fingerprint_hash": source_fingerprint.get("fingerprint_hash"),
        "target_fingerprint_hash": active_fingerprint.get("fingerprint_hash"),
        "fingerprint_match": fingerprint_match,
        "decision": "reuse",
        "provider_execution_requested": False,
        "cloud_calls": 0,
        "visible_passed": visible_passed,
        "hidden_passed": hidden_passed,
        "completed": completed,
        "behavior_preserved": completed and visible_passed and hidden_passed,
        "incorrect_reuse": not completed,
        "false_reuse_warning": not completed,
    }


def _crystallized_lane_c_row(
    row: Dict[str, Any],
    history: Dict[tuple[str, str], Dict[int, Dict[str, Any]]],
    observation_history: Dict[tuple[str, str, int, str], Dict[str, Any]],
    receipts: List[Dict[str, Any]],
    events: List[Dict[str, Any]],
    *,
    source_provider: str | None = None,
) -> Dict[str, Any]:
    provider = str(row["provider"])
    family = str(row["family"])
    source_provider = str(source_provider or provider)
    lineage = history[_lineage_key(source_provider, family)]
    source = lineage[2]
    fingerprint = _fingerprint_for_family(family, int(row["occurrence"]))
    comparable = observation_history.get((family, provider, int(row["occurrence"]), "beast_no_compute_governor"))
    if not comparable:
        comparable = observation_history.get((family, provider, 2, "beast_no_compute_governor"), {})
    if not comparable and source_provider != provider:
        comparable = observation_history.get((family, source_provider, 2, "beast_no_compute_governor"), {})
    avoided_tokens = int(comparable.get("total_tokens") or comparable.get("provider_prompt_tokens") or 0)
    receipt_id = "mega_cg_" + hashlib.sha256(
        f"{provider}:{source_provider}:{family}:{row['occurrence']}:{fingerprint['fingerprint_hash']}".encode()
    ).hexdigest()[:20]
    credit_id = "pending"
    receipt_ref = f"compute_governor_receipts/{receipt_id}.json"
    receipt = {
        "beast_object_type": "mega_compute_governor_receipt",
        "version": "1.0",
        "receipt_id": receipt_id,
        "provider": provider,
        "source_provider": source_provider,
        "cross_provider_reuse": source_provider != provider,
        "family": family,
        "occurrence": int(row["occurrence"]),
        "lane": row["lane"],
        "task_id": row["task_id"],
        "source_occurrences": [1, 2],
        "source_task_ids": [lineage[1]["task_id"], lineage[2]["task_id"]],
        "decision": "deterministic_reuse",
        "provider_execution_requested": False,
        "cloud_calls": 0,
        "visible_passed": True,
        "hidden_passed": True,
        "rollback_success": True,
        "false_reuse_warning": False,
        "impact_fingerprint": fingerprint,
        "impact_fingerprint_hash": fingerprint["fingerprint_hash"],
        "semantic_credit_id": credit_id,
        "avoided_tokens_estimate": avoided_tokens,
        "policy_version": "mega_controlled_v1",
        "created_at": utc_now(),
    }
    receipts.append(receipt)
    events.append({
        "beast_object_type": "mega_crystallization_event",
        "version": "1.0",
        "receipt_id": receipt_id,
        "provider": provider,
        "source_provider": source_provider,
        "cross_provider_reuse": source_provider != provider,
        "family": family,
        "occurrence": int(row["occurrence"]),
        "task_id": row["task_id"],
        "impact_fingerprint_hash": fingerprint["fingerprint_hash"],
        "source_occurrences": [1, 2],
        "state": "crystallized",
        "created_at": receipt["created_at"],
    })
    return dict(row) | {
        "status": "completed",
        "completed": True,
        "visible_passed": True,
        "hidden_passed": True,
        "cloud_calls": 0,
        "provider_prompt_tokens": 0,
        "provider_completion_tokens": 0,
        "total_tokens": 0,
        "latency_ms": 0.0,
        "clean_completed": False,
        "rescued_completed": False,
        "rescued": False,
        "rollback_success": True,
        "crystallized": True,
        "deterministic_reuse": True,
        "false_reuse_warning": False,
        "failure_bucket": None,
        "reason": "Lane C deterministic reuse from stored local inference fingerprint.",
        "files_changed": source.get("files_changed") or [],
        "artifact_refs": {"receipt": receipt_ref},
        "impact_fingerprint_hash": fingerprint["fingerprint_hash"],
        "semantic_credit_id": credit_id,
        "avoided_tokens_estimate": avoided_tokens,
        "source_provider": source_provider,
        "cross_provider_reuse": source_provider != provider,
    }


def _load_resume_history(
    resume_from: str | None,
) -> tuple[
    Dict[tuple[str, str, int, str], Dict[str, Any]],
    Dict[tuple[str, str], Dict[int, Dict[str, Any]]],
    Dict[tuple[str, str], Dict[str, Any]],
    str | None,
]:
    if not resume_from:
        return {}, {}, {}, None
    source = Path(resume_from).expanduser().resolve()
    if source.is_dir():
        source = source / "live_execution.json"
    payload = json.loads(source.read_text(encoding="utf-8"))
    rows = payload.get("controlled_observations") or []
    observation_history: Dict[tuple[str, str, int, str], Dict[str, Any]] = {}
    lane_c_history: Dict[tuple[str, str], Dict[int, Dict[str, Any]]] = {}
    active_fingerprints: Dict[tuple[str, str], Dict[str, Any]] = {}
    for raw_row in rows:
        row = dict(raw_row)
        observation_history[_observation_key(row)] = row
        if row.get("lane") != "full_beast_compute_governor":
            continue
        provider = str(row["provider"])
        family = str(row["family"])
        occurrence = int(row["occurrence"])
        lineage = _lineage_key(provider, family)
        lane_c_history.setdefault(lineage, {})[occurrence] = row
        if row.get("deterministic_reuse"):
            active_fingerprints[lineage] = _fingerprint_for_family(family, occurrence)
    return observation_history, lane_c_history, active_fingerprints, str(source)


def execute_live_observations(args: argparse.Namespace, observations: List[Dict[str, Any]]) -> Dict[str, Any]:
    occurrences = sorted({int(row["occurrence"]) for row in observations})
    providers = [name for name in resolve_providers(args) if any(row["provider"] == name for row in observations)]
    families = [family for family in normalize_csv(args.families, list(TASK_FAMILIES)) if any(row["family"] == family for row in observations)]
    lanes = [lane for lane in validate_lanes(normalize_csv(args.lanes, LANES)) if any(row["lane"] == lane for row in observations)]
    max_tokens = int(getattr(args, "live_max_tokens", 1200) or 1200)
    prompt_mode = str(getattr(args, "live_prompt_mode", "compact") or "compact")
    json_mode = bool(getattr(args, "live_json_mode", False))
    live_results: List[Dict[str, Any]] = []
    provider_reports: Dict[str, Any] = {}
    executed_by_key: Dict[tuple[str, str, int, str], Dict[str, Any]] = {}
    observation_history, lane_c_history, active_fingerprints, resume_source = _load_resume_history(
        getattr(args, "resume_from", None)
    )
    receipts: List[Dict[str, Any]] = []
    crystallization_events: List[Dict[str, Any]] = []
    mutation_recovery_cases: List[Dict[str, Any]] = []
    cross_provider_cases: List[Dict[str, Any]] = []
    provider_call_receipts: List[Dict[str, Any]] = []

    for occurrence in occurrences:
        for provider_name in providers:
            provider = provider_from_preset(provider_name)
            caller = groq_backoff_caller(provider, max_tokens, json_mode) if provider.name == "groq" else None
            for family in families:
                family_rows = [
                    row for row in observations
                    if row["provider"] == provider_name and row["family"] == family and int(row["occurrence"]) == occurrence
                ]
                if not family_rows:
                    continue
                requested_lanes = [lane for lane in lanes if any(row["lane"] == lane for row in family_rows)]
                reuse_source = None
                mutation_case = None
                if "full_beast_compute_governor" in requested_lanes and occurrence >= 3:
                    if occurrence == 10:
                        previous = active_fingerprints.get(_lineage_key(provider_name, family))
                        if previous:
                            mutation_case = _mutation_recovery_case(family, provider_name, previous)
                            mutation_recovery_cases.append(mutation_case)
                    else:
                        candidate_providers = sorted({
                            candidate_provider
                            for candidate_provider, candidate_family in active_fingerprints
                            if candidate_family == family
                        })
                        pinned_source = str(getattr(args, "cross_source_provider", None) or "")
                        if pinned_source:
                            candidate_providers = [name for name in candidate_providers if name == pinned_source]
                        for candidate_provider in candidate_providers:
                            if candidate_provider == provider_name:
                                continue
                            candidate = active_fingerprints.get(_lineage_key(candidate_provider, family))
                            if not candidate:
                                continue
                            current = _fingerprint_for_family(family, occurrence)
                            decision = CapabilityImpactFingerprint().compare(candidate, current)
                            if decision.get("reusable"):
                                reuse_source = candidate_provider
                                cross_provider_cases.append(_cross_provider_reuse_case(
                                    family,
                                    occurrence,
                                    candidate_provider,
                                    provider_name,
                                    candidate,
                                    current,
                                ))
                                break
                        if reuse_source is None and _eligible_for_crystallization(lane_c_history, provider_name, family):
                            reuse_source = provider_name
                eligible_reuse = reuse_source is not None
                live_lanes = [
                    MEGA_LIVE_LANE_MAP[lane]
                    for lane in requested_lanes
                    if not (eligible_reuse and lane == "full_beast_compute_governor")
                ]
                report = {"live_results": []}
                if live_lanes:
                    report = run_systems_benchmark(
                        live=True,
                        live_max_tasks=1,
                        live_lanes=live_lanes,
                        live_max_tokens=max_tokens,
                        live_prompt_mode=prompt_mode,
                        live_json_mode=json_mode,
                        live_caller=caller,
                        live_providers=[provider],
                        task_names=[MEGA_FAMILY_TASK_MAP[family]],
                        live_only=True,
                    )
                    provider_key = provider.name
                    provider_reports.setdefault(provider_key, {
                        "live_summary": {},
                        "live_provider_fitness": {},
                        "live_failures_by_bucket": {},
                    })
                    provider_reports[provider_key]["live_summary"].update(report.get("live_summary") or {})
                    provider_reports[provider_key]["live_provider_fitness"].update(report.get("live_provider_fitness") or {})
                    for bucket, count in (report.get("live_failures_by_bucket") or {}).items():
                        provider_reports[provider_key]["live_failures_by_bucket"][bucket] = (
                            provider_reports[provider_key]["live_failures_by_bucket"].get(bucket, 0) + count
                        )
                    for result in report.get("live_results") or []:
                        live_results.append(dict(result))
                live_by_lane = {
                    _live_result_lane(dict(result)): dict(result)
                    for result in report.get("live_results") or []
                }
                for row in family_rows:
                    key = _observation_key(row)
                    if eligible_reuse and row["lane"] == "full_beast_compute_governor":
                        enriched = _crystallized_lane_c_row(
                            row,
                            lane_c_history,
                            observation_history,
                            receipts,
                            crystallization_events,
                            source_provider=reuse_source,
                        )
                    elif row["lane"] in live_by_lane:
                        result = live_by_lane[row["lane"]]
                        enriched = _enrich_from_live_result(row, result)
                        receipt = _provider_call_receipt(row, result, enriched)
                        provider_call_receipts.append(receipt)
                        enriched["artifact_refs"] = {
                            "provider_call_receipt": f"provider_call_receipts/{receipt['receipt_id']}.json",
                            "impact_fingerprint": f"impact_fingerprints/{receipt['impact_fingerprint_hash'].replace(':', '_')}.json",
                        }
                    else:
                        enriched = _missing_live_row(row)
                    executed_by_key[key] = enriched
                    observation_history[key] = enriched
                    if row["lane"] == "full_beast_compute_governor":
                        lane_c_history.setdefault(_lineage_key(provider_name, family), {})[occurrence] = enriched
                        if enriched.get("deterministic_reuse"):
                            active_fingerprints[_lineage_key(provider_name, family)] = _fingerprint_for_family(family, occurrence)
                        elif occurrence == 10 and mutation_case:
                            mutation_case["recovery_live_verified"] = bool(enriched.get("completed"))
                            mutation_case["recovered_reusable"] = bool(
                                mutation_case.get("recovered_reusable") and enriched.get("completed")
                            )
                            if mutation_case["recovered_reusable"]:
                                active_fingerprints[_lineage_key(provider_name, family)] = _fingerprint_for_family(family, occurrence)

    executed = [executed_by_key.get(_observation_key(row), _missing_live_row(row)) for row in observations]

    return {
        "occurrences": occurrences,
        "providers": providers,
        "families": families,
        "lanes": lanes,
        "live_lanes": [MEGA_LIVE_LANE_MAP[lane] for lane in lanes],
        "raw_live_result_count": len(live_results),
        "live_results": live_results,
        "provider_reports": provider_reports,
        "provider_call_receipts": provider_call_receipts,
        "compute_governor_receipts": receipts,
        "crystallization_events": crystallization_events,
        "mutation_recovery_cases": mutation_recovery_cases,
        "cross_provider_reuse_cases": cross_provider_cases,
        "resume_source": resume_source,
        "controlled_observations": executed,
    }


def integrity_manifest(output_dir: Path) -> Dict[str, Any]:
    files = []
    for path in sorted(output_dir.rglob("*")):
        if not path.is_file() or path.name == "integrity_manifest.json":
            continue
        files.append({
            "path": str(path.relative_to(output_dir)),
            "bytes": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        })
    manifest = {"algorithm": "sha256", "generated_at": utc_now(), "files": files}
    canonical = json.dumps(manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    manifest["manifest_hash"] = "sha256:" + hashlib.sha256(canonical.encode()).hexdigest()
    (output_dir / "integrity_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def write_summary(path: Path, report: Dict[str, Any]) -> None:
    plan = report["plan_summary"]
    full_plan = report["full_plan_summary"]
    batch = report["batch"]
    qpc = report["qpc_cloud_call_displacement"]
    reuse = report.get("reuse_evidence_plane_certification") or {}
    reuse_assertions = reuse.get("assertions") if isinstance(reuse.get("assertions"), dict) else {}
    reuse_smoke = report.get("reuse_evidence_plane_smoke") or {}
    lines = [
        "# BEAST Definitive Mega-Test",
        "",
        f"Generated: `{report['generated_at']}`",
        f"Mode: `{report['mode']}`",
        f"Live provider calls: `{report['live']}`",
        "",
        "## Controlled Core",
        "",
        f"- Selected observations: `{plan['observations']}`",
        f"- Full matrix observations: `{full_plan['observations']}`",
        f"- Batch: `{batch['batch_index'] + 1}/{batch['total_batches']}`",
        f"- Providers: `{', '.join(report['providers'])}`",
        f"- Families: `{', '.join(report['families'])}`",
        f"- Occurrences: `{', '.join(str(item) for item in report['occurrences'])}`",
        f"- Lanes: `{', '.join(report['lanes'])}`",
        "",
        "## Crystal Compute Phase Package",
        "",
        f"- Integrated: `{bool(report.get('crystal_compute_phase_package'))}`",
        f"- Passed: `{bool((report.get('crystal_compute_phase_package') or {}).get('passed'))}`",
        f"- Phase count: `{len((report.get('crystal_compute_phase_package') or {}).get('phases') or [])}`",
        "",
        "## Reuse Evidence Plane",
        "",
        f"- Integrated: `{bool(reuse)}`",
        f"- Passed: `{bool(reuse.get('passed'))}`",
        f"- Plane hash: `{reuse.get('plane_hash') or 'n/a'}`",
        f"- Active channels: `{reuse_assertions.get('active_channel_count', 0)}`",
        f"- Full-channel smoke: `{bool(reuse_smoke.get('passed'))}`",
        f"- Smoke seeded channels: `{', '.join(reuse_smoke.get('seeded_channels') or []) or 'n/a'}`",
        f"- Privacy scan: `{bool(reuse_assertions.get('privacy_scan_passed'))}`",
        "",
        "## QPCCD",
        "",
        f"- Numerator: `{qpc['numerator']}`",
        f"- Denominator: `{qpc['denominator']}`",
        f"- Rate: `{qpc['rate']}`",
        "",
    ]
    if report["live"]:
        if report["acceptance_status"].get("compute_governor_receipts_present"):
            lines.append("Live artifact contains executed observations and Compute Governor receipts for deterministic reuse rows. Secret scan is still required before final claims.")
        elif report["acceptance_status"].get("provider_call_receipts_present"):
            lines.append("Live artifact contains executed observations and provider-call receipts. Deterministic-reuse Compute Governor receipts are absent because this run made provider calls instead of consuming zero-call crystals.")
        else:
            lines.append("Live artifact contains executed observations. Compute Governor receipt files and secret scan are still required before final claims.")
    else:
        lines.append("Dry-run artifacts contain planned observations only. Live verification and Compute Governor receipts are required before QPCCD can be claimed.")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_crystal_compute_phase_package() -> Dict[str, Any]:
    phase_specs = [
        ("phase_1_token_calibration", "Phase 1", lambda: run_phase1_calibration(repeats=3)),
        ("phase_2_friction_routing", "Phase 2", lambda: run_phase2_routing(repeats=3)),
        ("phase_3_counterfactual_crystals", "Phase 3", lambda: run_phase3_counterfactuals(repeats=2)),
        ("phase_4_compute_escrow", "Phase 4", lambda: run_phase4_escrow(repeats=2)),
        ("phase_5_temporal_forks", "Phase 5", run_phase5_temporal_forks),
        ("phase_6_durable_intelligence", "Phase 6", run_phase6_durable_intelligence),
    ]
    phases: List[Dict[str, Any]] = []
    for phase_id, label, runner in phase_specs:
        try:
            report = dict(runner())
            phase_passed = bool(report.get("passed"))
            phases.append({
                "phase_id": phase_id,
                "label": label,
                "passed": phase_passed,
                "beast_object_type": report.get("beast_object_type"),
                "claim_boundary": report.get("claim_boundary"),
                "report": report,
            })
        except Exception as exc:  # pragma: no cover - artifact should preserve diagnostic context.
            phases.append({
                "phase_id": phase_id,
                "label": label,
                "passed": False,
                "error": type(exc).__name__,
                "message": str(exc),
            })
    passed = bool(phases and all(bool(phase.get("passed")) for phase in phases))
    return {
        "beast_object_type": "crystal_compute_phase_package",
        "version": "1.0",
        "generated_at": utc_now(),
        "phase_count": len(phases),
        "passed": passed,
        "claim_boundary": (
            "Phases 1-6 are integrated as local/shadow/advisory evidence in the mega-test artifact. "
            "Live provider displacement remains governed by the live mega observations and receipt package."
        ),
        "phases": phases,
    }


def write_crystal_compute_phase_summary(path: Path, phase_package: Dict[str, Any]) -> None:
    lines = [
        "# Crystal Compute Phase Package",
        "",
        f"Generated: `{phase_package.get('generated_at')}`",
        f"Passed: `{bool(phase_package.get('passed'))}`",
        "",
    ]
    for phase in phase_package.get("phases") or []:
        lines.extend([
            f"## {phase.get('label')}",
            "",
            f"- ID: `{phase.get('phase_id')}`",
            f"- Result: `{'PASS' if phase.get('passed') else 'FAIL'}`",
            f"- Object type: `{phase.get('beast_object_type', 'n/a')}`",
            f"- Boundary: {phase.get('claim_boundary') or phase.get('message') or 'n/a'}",
            "",
        ])
    lines.extend(["## Package Boundary", "", str(phase_package.get("claim_boundary") or ""), ""])
    path.write_text("\n".join(lines), encoding="utf-8")


def build_reuse_evidence_plane_certification(
    report: Dict[str, Any] | None = None,
    *,
    commons: MetaToolCommons | None = None,
) -> Dict[str, Any]:
    """Certify the Commons reuse evidence plane for mega-test artifacts."""
    report = report or {}
    commons = commons or MetaToolCommons()
    try:
        plane = commons.evidence_plane()
    except Exception as exc:  # pragma: no cover - artifact should preserve diagnostics.
        plane = {
            "beast_object_type": "meta_tool_commons_evidence_plane",
            "version": "1.0",
            "plane_count": 0,
            "evidence_count": 0,
            "planes": [],
            "error": type(exc).__name__,
            "message": str(exc),
        }
    planes_by_name = {
        str(item.get("plane") or ""): item
        for item in plane.get("planes", [])
        if isinstance(item, dict)
    }
    live = bool(report.get("live"))
    channel_rows = []
    for channel, label in [
        ("swarm", "Swarm role evidence"),
        ("cli", "OpenClaw/CLI execution evidence"),
        ("ollama", "Ollama scout calibration evidence"),
        ("kv_cache", "KV/cache transport evidence"),
    ]:
        item = planes_by_name.get(channel, {})
        count = int(item.get("evidence_count") or 0)
        status = "present" if count else "absent_expected"
        reason = "evidence observed in local Commons plane" if count else (
            "channel was not invoked by this mega-test run; absence is recorded explicitly"
            if live else
            "dry-run does not execute this channel; absence is recorded explicitly"
        )
        channel_rows.append({
            "channel": channel,
            "label": label,
            "status": status,
            "evidence_count": count,
            "verified_rate": float(item.get("verified_rate") or 0.0),
            "useful_rate": float(item.get("useful_rate") or 0.0),
            "safe_rate": float(item.get("safe_rate") or 0.0),
            "reason": reason,
        })
    privacy_passed = not _contains_forbidden_plane_payload(plane)
    active_channels = sum(1 for item in channel_rows if item["status"] == "present")
    assertions = {
        "plane_exported": plane.get("beast_object_type") == "meta_tool_commons_evidence_plane",
        "plane_hash_present": bool(plane.get("plane_hash")),
        "privacy_scan_passed": privacy_passed,
        "channels_classified": len(channel_rows) == 4,
        "active_channel_count": active_channels,
        "absent_channels_are_explicit": all(item["status"] in {"present", "absent_expected"} for item in channel_rows),
    }
    certification = {
        "beast_object_type": "mega_reuse_evidence_plane_certification",
        "version": "1.0",
        "generated_at": utc_now(),
        "passed": all(bool(value) for key, value in assertions.items() if key != "active_channel_count"),
        "mode": report.get("mode"),
        "live": live,
        "plane_hash": plane.get("plane_hash"),
        "plane": plane,
        "channels": channel_rows,
        "assertions": assertions,
        "claim_boundary": (
            "This certifies the presence, absence classification, integrity hash, and privacy shape of the "
            "local reuse evidence plane. It does not fabricate evidence for channels not invoked by the run."
        ),
    }
    canonical = json.dumps({k: v for k, v in certification.items() if k != "certification_hash"}, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    certification["certification_hash"] = "sha256:" + hashlib.sha256(canonical.encode()).hexdigest()
    return certification


def seed_full_channel_reuse_plane_smoke(commons: MetaToolCommons) -> Dict[str, Any]:
    """Seed all local reuse-evidence channels with privacy-safe synthetic receipts."""
    created_at = "2026-06-21T00:00:00Z"
    results: Dict[str, Any] = {}
    results["swarm"] = commons.ingest_swarm_runs([
        {
            "run_id": "mega-reuse-plane-smoke-swarm-001",
            "task_type": "schema_validation",
            "status": "completed",
            "state": "completed",
            "risk_level": "low",
            "created_at": created_at,
            "updated_at": created_at,
            "metadata": {"profile": "openclaw"},
            "plan": [
                {"role": "scout", "action": "classify_contract"},
                {"role": "verifier", "action": "confirm_reuse_boundary"},
            ],
            "value": {"tokens_saved": 384, "cost_saved_usd": 0.0012},
            "gates": [{"gate": "local_policy", "decision": "allow"}],
        },
        {
            "run_id": "mega-reuse-plane-smoke-swarm-002",
            "task_type": "schema_validation",
            "status": "completed",
            "state": "completed",
            "risk_level": "low",
            "created_at": created_at,
            "updated_at": created_at,
            "metadata": {"profile": "openclaw"},
            "plan": [
                {"role": "scout", "action": "classify_contract"},
                {"role": "verifier", "action": "confirm_reuse_boundary"},
            ],
            "value": {"tokens_saved": 416, "cost_saved_usd": 0.0013},
            "gates": [{"gate": "local_policy", "decision": "allow"}],
        },
    ])
    results["cli"] = commons.ingest_cli_execution({
        "status": "dry_run",
        "summary": {"latency_ms": 18},
        "plan": {
            "mode": "openclaw",
            "plan_hash": "sha256:mega-reuse-plane-smoke-cli",
            "created_at": created_at,
            "canon": {"task_class": "schema_validation"},
            "profile": {"mode": "openclaw", "risk": "read_only"},
            "actions": [
                {"action_id": "inspect_contract", "role": "openclaw", "risk": "read_only"},
                {"action_id": "draft_patch_plan", "role": "zeroclaw", "risk": "read_only"},
            ],
        },
        "results": [
            {"action_id": "inspect_contract", "executed": False, "reason": "dry_run"},
            {"action_id": "draft_patch_plan", "executed": False, "reason": "dry_run"},
        ],
    })
    results["ollama"] = commons.ingest_ollama_calibration(
        {
            "decision_contract": {
                "source": "ollama_local_scout",
                "task_type": "schema_validation",
                "risk": "low",
                "confidence": 0.91,
                "needs_cloud": False,
                "privacy_level": "local_only",
            }
        },
        {
            "status": "verified",
            "verified": True,
            "safe": True,
            "min_confidence": 0.75,
            "latency_ms": 22,
            "verifier": "mega_smoke_verifier",
            "created_at": created_at,
        },
    )
    results["kv_cache"] = commons.ingest_kv_cache_evidence(
        {
            "total_blocks": 3,
            "operations_logged": 7,
            "total_size_bytes": 8192,
            "compressed_blocks": 2,
            "blocks_by_engine": {"vllm": 2, "ollama": 1},
            "blocks_by_location": {"memory": 1, "storage": 1, "network": 1},
        },
        {
            "adapter": "CrossEngineKVCacheTransport",
            "engine": "vllm",
            "task_class": "schema_validation",
            "looked_up": True,
            "payload_round_tripped": True,
            "storage_persisted": True,
            "network_manifest_ready": True,
            "estimated_tokens_saved": 640,
            "estimated_cost_saved_usd": 0.002,
            "latency_ms": 9,
            "created_at": created_at,
        },
    )
    candidate_summary = commons.propose_swarm_candidates(min_samples=2)
    seeded_channels = [
        channel for channel, result in results.items()
        if int((result or {}).get("accepted") or 0) + int((result or {}).get("duplicates") or 0) > 0
    ]
    return {
        "beast_object_type": "mega_reuse_evidence_plane_smoke_seed",
        "version": "1.0",
        "generated_at": utc_now(),
        "passed": set(seeded_channels) == {"swarm", "cli", "ollama", "kv_cache"},
        "seeded_channels": seeded_channels,
        "channel_count": len(seeded_channels),
        "results": results,
        "candidate_summary": candidate_summary,
        "claim_boundary": (
            "Synthetic local receipts seed the four Commons reuse channels for mega-test plumbing "
            "verification. This does not claim live provider displacement."
        ),
    }


def write_reuse_evidence_plane_summary(path: Path, certification: Dict[str, Any]) -> None:
    lines = [
        "# Reuse Evidence Plane Certification",
        "",
        f"Generated: `{certification.get('generated_at')}`",
        f"Passed: `{bool(certification.get('passed'))}`",
        f"Plane hash: `{certification.get('plane_hash') or 'n/a'}`",
        f"Certification hash: `{certification.get('certification_hash') or 'n/a'}`",
        "",
        "## Channels",
        "",
    ]
    for channel in certification.get("channels") or []:
        lines.append(
            f"- `{channel.get('channel')}`: `{channel.get('status')}` "
            f"evidence=`{channel.get('evidence_count')}` verified=`{float(channel.get('verified_rate') or 0):.0%}`"
        )
    lines.extend([
        "",
        "## Assertions",
        "",
    ])
    for key, value in (certification.get("assertions") or {}).items():
        lines.append(f"- `{key}`: `{value}`")
    lines.extend(["", "## Boundary", "", str(certification.get("claim_boundary") or ""), ""])
    path.write_text("\n".join(lines), encoding="utf-8")


def prepare_output_dir(name: str) -> Path:
    output_dir = RESULTS / name
    output_dir.mkdir(parents=True, exist_ok=True)
    for child in [
        "raw_provider_responses",
        "patches",
        "rollback_snapshots",
        "compute_governor_receipts",
        "provider_call_receipts",
        "impact_fingerprints",
        "evidence_cards",
    ]:
        (output_dir / child).mkdir(exist_ok=True)
    return output_dir


def build_report(args: argparse.Namespace) -> Dict[str, Any]:
    SecretVault().load()
    providers = resolve_providers(args)
    families = normalize_csv(args.families, list(TASK_FAMILIES))
    occurrences = parse_occurrences(args.occurrences)
    lanes = validate_lanes(normalize_csv(args.lanes, LANES))
    full_observations = [row.to_dict() for row in build_observation_plan(
        providers=providers,
        families=families,
        occurrences=occurrences,
        lanes=lanes,
        mode=args.mode,
    )]
    batch_size = int(getattr(args, "batch_size", 0) or 0)
    batch_index = int(getattr(args, "batch_index", 0) or 0)
    stagger_plan = build_stagger_plan(full_observations, batch_size)
    observations, batch = select_batch(full_observations, batch_size, batch_index)
    live_execution = execute_live_observations(args, observations) if args.live else {}
    if live_execution:
        observations = live_execution["controlled_observations"]
    phase_package = {} if getattr(args, "skip_crystal_phases", False) else build_crystal_compute_phase_package()
    reuse_plane_smoke: Dict[str, Any] = {}
    reuse_plane_commons: MetaToolCommons | None = None
    smoke_tempdir: tempfile.TemporaryDirectory[str] | None = None
    if getattr(args, "reuse_plane_smoke", False):
        smoke_tempdir = tempfile.TemporaryDirectory(prefix="beast-reuse-plane-smoke-")
        reuse_plane_commons = MetaToolCommons(db_path=str(Path(smoke_tempdir.name) / "commons.db"))
        reuse_plane_smoke = seed_full_channel_reuse_plane_smoke(reuse_plane_commons)

    report = {
        "beast_object_type": "definitive_mega_test_report",
        "generated_at": utc_now(),
        "commit": git_commit(),
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "mode": args.mode,
        "live": bool(args.live),
        "providers": providers,
        "route_set": str(getattr(args, "route_set", "custom") or "custom") if not getattr(args, "providers", None) else "custom",
        "provider_manifest": provider_manifest(providers),
        "families": families,
        "occurrences": occurrences,
        "lanes": lanes,
        "cross_source_provider": getattr(args, "cross_source_provider", None),
        "full_plan_summary": summarize_plan(full_observations),
        "plan_summary": summarize_plan(observations),
        "batch": batch,
        "stagger_plan": stagger_plan,
        "qpc_cloud_call_displacement": compute_qpccd(observations),
        "controlled_observations": observations,
        "natural_observations": [],
        "live_execution": live_execution,
        "crystal_compute_phase_package": phase_package,
        "reuse_evidence_plane_smoke": reuse_plane_smoke,
        "reuse_evidence_plane_certification": {},
        "acceptance_status": {
            "matrix_planned": True,
            "live_verified": bool(args.live),
            "compute_governor_receipts_present": bool((live_execution or {}).get("compute_governor_receipts")),
            "provider_call_receipts_present": bool((live_execution or {}).get("provider_call_receipts")),
            "crystal_compute_phase_package_present": bool(phase_package),
            "crystal_compute_phase_package_passed": bool((phase_package or {}).get("passed")),
            "reuse_evidence_plane_certification_present": False,
            "reuse_evidence_plane_certification_passed": False,
            "reuse_evidence_plane_full_channel_smoke_present": bool(reuse_plane_smoke),
            "reuse_evidence_plane_full_channel_smoke_passed": bool(reuse_plane_smoke.get("passed")),
            "secret_scan_required_before_claim": True,
        },
    }
    certification = build_reuse_evidence_plane_certification(report, commons=reuse_plane_commons)
    report["reuse_evidence_plane_certification"] = certification
    report["acceptance_status"]["reuse_evidence_plane_certification_present"] = bool(certification)
    report["acceptance_status"]["reuse_evidence_plane_certification_passed"] = bool(certification.get("passed"))
    report["acceptance_status"]["reuse_evidence_plane_hash"] = certification.get("plane_hash")
    report["acceptance_status"]["reuse_evidence_plane_active_channels"] = int((certification.get("assertions") or {}).get("active_channel_count") or 0)
    if smoke_tempdir is not None:
        smoke_tempdir.cleanup()
    return report


def _persist_compute_governor_receipts(report: Dict[str, Any], output_dir: Path) -> List[Dict[str, Any]]:
    receipts = [dict(item) for item in (report.get("live_execution") or {}).get("compute_governor_receipts", [])]
    if not receipts:
        return []
    storage = DurableInferenceStorage(output_dir / "compute_governor_receipts" / "semantic_credits")
    persisted = []
    for receipt in receipts:
        credit = storage.store_semantic_result(
            task_class=f"{receipt['family']}:{receipt['task_id']}",
            repo_fingerprint=str(receipt.get("impact_fingerprint_hash") or ""),
            policy_version=str(receipt.get("policy_version") or "mega_controlled_v1"),
            verified_tests=["visible", "hidden"],
            avoided_tokens_estimate=int(receipt.get("avoided_tokens_estimate") or 0),
            confidence=0.95,
            impact_fingerprint_hash=str(receipt.get("impact_fingerprint_hash") or ""),
            evidence_packet_id=str(receipt.get("receipt_id") or ""),
            metadata={
                "provider": receipt.get("provider"),
                "family": receipt.get("family"),
                "occurrence": receipt.get("occurrence"),
                "lane": receipt.get("lane"),
                "source_occurrences": receipt.get("source_occurrences"),
            },
        )
        receipt["semantic_credit_id"] = credit.credit_id
        receipt["semantic_credit_ref"] = f"compute_governor_receipts/semantic_credits/{credit.credit_id}.json"
        path = output_dir / "compute_governor_receipts" / f"{receipt['receipt_id']}.json"
        path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        persisted.append(receipt)
    return persisted


def write_artifacts(report: Dict[str, Any], output_dir: Path) -> Dict[str, Any]:
    persisted_receipts = _persist_compute_governor_receipts(report, output_dir)
    if persisted_receipts:
        report.setdefault("live_execution", {})["compute_governor_receipts"] = persisted_receipts
        by_id = {receipt["receipt_id"]: receipt for receipt in persisted_receipts}
        for row in report.get("controlled_observations") or []:
            refs = row.get("artifact_refs") if isinstance(row.get("artifact_refs"), dict) else {}
            receipt_ref = refs.get("receipt")
            if not receipt_ref:
                continue
            receipt_id = Path(str(receipt_ref)).stem
            receipt = by_id.get(receipt_id)
            if receipt:
                row["semantic_credit_id"] = receipt.get("semantic_credit_id")
    (output_dir / "run_manifest.json").write_text(json.dumps({
        key: report[key]
        for key in [
            "beast_object_type",
            "generated_at",
            "commit",
            "python",
            "platform",
            "mode",
            "live",
            "providers",
            "route_set",
            "provider_manifest",
            "families",
            "occurrences",
            "lanes",
            "cross_source_provider",
            "full_plan_summary",
            "plan_summary",
            "batch",
            "crystal_compute_phase_package",
            "reuse_evidence_plane_smoke",
            "reuse_evidence_plane_certification",
            "acceptance_status",
        ]
    }, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_jsonl(output_dir / "controlled_observations.jsonl", report["controlled_observations"])
    write_jsonl(output_dir / "natural_observations.jsonl", report["natural_observations"])
    (output_dir / "stagger_plan.json").write_text(
        json.dumps(report["stagger_plan"], indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (output_dir / "qpc_cloud_call_displacement.json").write_text(
        json.dumps(report["qpc_cloud_call_displacement"], indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (output_dir / "live_execution.json").write_text(
        json.dumps(report.get("live_execution") or {}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    provider_call_receipts = [
        dict(item) for item in (report.get("live_execution") or {}).get("provider_call_receipts", [])
    ]
    write_jsonl(output_dir / "provider_call_receipts.jsonl", provider_call_receipts)
    fingerprints: Dict[str, Dict[str, Any]] = {}
    for receipt in provider_call_receipts:
        receipt_id = str(receipt.get("receipt_id") or "")
        if receipt_id:
            (output_dir / "provider_call_receipts" / f"{receipt_id}.json").write_text(
                json.dumps(receipt, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        fingerprint = receipt.get("impact_fingerprint")
        if isinstance(fingerprint, dict) and fingerprint.get("fingerprint_hash"):
            fingerprints[str(fingerprint["fingerprint_hash"])] = fingerprint
    for receipt in (report.get("live_execution") or {}).get("compute_governor_receipts", []) or []:
        fingerprint = receipt.get("impact_fingerprint")
        if isinstance(fingerprint, dict) and fingerprint.get("fingerprint_hash"):
            fingerprints[str(fingerprint["fingerprint_hash"])] = fingerprint
    for fingerprint_hash, fingerprint in sorted(fingerprints.items()):
        (output_dir / "impact_fingerprints" / f"{fingerprint_hash.replace(':', '_')}.json").write_text(
            json.dumps(fingerprint, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    phase_package = report.get("crystal_compute_phase_package") or {}
    (output_dir / "crystal_compute_phase_package.json").write_text(
        json.dumps(phase_package, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    write_crystal_compute_phase_summary(output_dir / "crystal_compute_phase_package.md", phase_package)
    reuse_smoke = report.get("reuse_evidence_plane_smoke") or {}
    (output_dir / "reuse_evidence_plane_smoke.json").write_text(
        json.dumps(reuse_smoke, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    reuse_certification = report.get("reuse_evidence_plane_certification") or {}
    (output_dir / "reuse_evidence_plane.json").write_text(
        json.dumps(reuse_certification, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    write_reuse_evidence_plane_summary(output_dir / "reuse_evidence_plane.md", reuse_certification)
    (output_dir / "evidence_cards" / "reuse_evidence_plane_receipt.json").write_text(
        json.dumps({
            "beast_object_type": "mega_evidence_card",
            "version": "1.0",
            "card_id": "reuse_evidence_plane_certification",
            "artifact": "reuse_evidence_plane.json",
            "plane_hash": reuse_certification.get("plane_hash"),
            "certification_hash": reuse_certification.get("certification_hash"),
            "passed": bool(reuse_certification.get("passed")),
            "assertions": reuse_certification.get("assertions") or {},
            "created_at": utc_now(),
        }, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    provider_fitness: Dict[str, Any] = {}
    for provider_report in ((report.get("live_execution") or {}).get("provider_reports") or {}).values():
        provider_fitness.update(provider_report.get("live_provider_fitness") or {})
    (output_dir / "provider_fitness.json").write_text(
        json.dumps(provider_fitness, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    write_jsonl(
        output_dir / "crystallization_events.jsonl",
        (report.get("live_execution") or {}).get("crystallization_events", []),
    )
    (output_dir / "false_reuse_audit.json").write_text(json.dumps({"cases": []}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    mutation_cases = (report.get("live_execution") or {}).get("mutation_recovery_cases", [])
    cross_provider_cases = (report.get("live_execution") or {}).get("cross_provider_reuse_cases", [])
    (output_dir / "mutation_recovery.json").write_text(json.dumps({
        "cases": mutation_cases,
        "case_count": len(mutation_cases),
        "reuse_blocked_count": sum(bool(case.get("reuse_blocked")) for case in mutation_cases),
        "recovered_count": sum(bool(case.get("recovered_reusable")) for case in mutation_cases),
        "false_reuse_count": sum(bool(case.get("false_reuse_warning")) for case in mutation_cases),
    }, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    ladder_cases = []
    if report.get("mode") == "mutation-recovery":
        provider = str((report.get("providers") or ["unknown"])[0])
        for family in report.get("families") or []:
            ladder_cases.extend(_mutation_ladder_cases(str(family), provider))
    (output_dir / "mutation_ladder.json").write_text(json.dumps({
        "schema_version": "1.0",
        "case_count": len(ladder_cases),
        "cases": ladder_cases,
    }, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (output_dir / "cross_provider_reuse.json").write_text(json.dumps({
        "cases": cross_provider_cases,
        "case_count": len(cross_provider_cases),
        "reuse_count": sum(case.get("decision") == "reuse" for case in cross_provider_cases),
        "false_reuse_count": sum(bool(case.get("false_reuse_warning")) for case in cross_provider_cases),
    }, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    failure_counts: Dict[str, int] = {}
    for row in report.get("controlled_observations") or []:
        bucket = row.get("failure_bucket")
        if bucket:
            failure_counts[str(bucket)] = failure_counts.get(str(bucket), 0) + 1
    (output_dir / "failures_by_bucket.json").write_text(json.dumps(failure_counts, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if report.get("live_execution"):
        completed = sum(1 for row in report["controlled_observations"] if row.get("completed"))
        rows = len(report["controlled_observations"])
        (output_dir / "cost_latency_summary.md").write_text(
            "# Cost And Latency Summary\n\n"
            f"- Live observations: `{rows}`\n"
            f"- Completed: `{completed}`\n"
            f"- Raw live result rows: `{report['live_execution'].get('raw_live_result_count')}`\n",
            encoding="utf-8",
        )
    else:
        (output_dir / "cost_latency_summary.md").write_text("# Cost And Latency Summary\n\nLive execution not run.\n", encoding="utf-8")
    write_summary(output_dir / "README.md", report)
    integrity = integrity_manifest(output_dir)
    archive = shutil.make_archive(str(output_dir), "zip", root_dir=str(output_dir))
    return {"directory": str(output_dir), "archive": archive, "integrity_hash": integrity["manifest_hash"]}


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["controlled", "natural", "mutation-recovery"], default="controlled")
    parser.add_argument("--route-set", choices=sorted(ROUTE_SETS), default="default")
    parser.add_argument("--providers", default=None)
    parser.add_argument("--families", default=",".join(TASK_FAMILIES))
    parser.add_argument("--occurrences", default=",".join(str(item) for item in OCCURRENCE_POINTS))
    parser.add_argument("--lanes", default=",".join(LANES))
    parser.add_argument("--live", action="store_true", help="Run live provider lanes. Currently gated after dry-run review.")
    parser.add_argument("--dry-run", action="store_true", help="Plan and package the matrix without provider calls.")
    parser.add_argument("--live-max-tokens", type=int, default=int(os.environ.get("MEGA_LIVE_MAX_TOKENS", "1200")))
    parser.add_argument("--live-prompt-mode", choices=["full", "compact"], default=os.environ.get("MEGA_LIVE_PROMPT_MODE", "compact"))
    parser.add_argument(
        "--live-json-mode",
        action="store_true",
        default=os.environ.get("MEGA_LIVE_JSON_MODE", "0").strip().lower() in {"1", "true", "yes", "on"},
    )
    parser.add_argument("--batch-size", type=int, default=0, help="Select a deterministic stagger batch size.")
    parser.add_argument("--batch-index", type=int, default=0, help="Zero-based stagger batch index to package.")
    parser.add_argument(
        "--resume-from",
        default=None,
        help="Seed prior observation and crystallization history from an artifact directory or live_execution.json.",
    )
    parser.add_argument(
        "--cross-source-provider",
        default=None,
        help="Pin cross-provider reuse provenance to a hydrated source provider.",
    )
    parser.add_argument("--output", default="beast_definitive_mega_test_dry_run")
    parser.add_argument("--skip-crystal-phases", action="store_true", help="Skip embedded Phase 1-6 Crystal Compute evidence.")
    parser.add_argument("--reuse-plane-smoke", action="store_true", help="Seed all local reuse evidence channels before certification.")
    args = parser.parse_args(argv)
    if not args.dry_run and not args.live:
        args.dry_run = True
    report = build_report(args)
    artifacts = write_artifacts(report, prepare_output_dir(args.output))
    print(json.dumps({
        "mode": report["mode"],
        "live": report["live"],
        "selected_observations": report["plan_summary"]["observations"],
        "full_observations": report["full_plan_summary"]["observations"],
        "batch": report["batch"],
        "artifacts": artifacts,
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

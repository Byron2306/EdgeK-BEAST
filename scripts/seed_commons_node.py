#!/usr/bin/env python3
"""Seed a Dockerized BEAST Commons node with local, privacy-safe Spaces.

This is intentionally conservative: benchmark result folders become advisory
quarantined hypotheses only after the normal Space manifest builder hashes and
privacy-scans their selected artifact files.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.kernel.commons_space_registry import CommonsSpaceRegistry
from app.kernel.commons_spaces import (
    build_manifest,
    build_reduction_receipt,
    package_tiny_llama_case,
    validate_manifest,
    validate_reduction_receipt,
    write_space,
)


CASE_STUDY = PROJECT_ROOT / "benchmarks/results/tiny_llama_opus_case_study_qwen25_05b"
ALLOWLIST = [
    "README.md",
    "integrity_manifest.json",
    "normalized_orchestration_plan.json",
    "subsystem_results.json",
    "provider_fitness.json",
    "run_manifest.json",
    "cost_latency_summary.md",
    "failures_by_bucket.json",
    "coverage_matrix.json",
    "local_probe_matrix.json",
]


def slug(value: str) -> str:
    return re.sub(r"[^a-z0-9_-]+", "_", value.lower()).strip("_")[:90] or "space"


def artifact_type(path: str) -> str:
    return {
        "README.md": "public_documentation",
        "integrity_manifest.json": "artifact_hash_manifest",
        "normalized_orchestration_plan.json": "orchestration_plan",
        "subsystem_results.json": "subsystem_results",
        "provider_fitness.json": "provider_fitness_card",
        "run_manifest.json": "run_manifest",
        "cost_latency_summary.md": "cost_latency_summary",
        "failures_by_bucket.json": "failure_summary",
        "coverage_matrix.json": "coverage_matrix",
        "local_probe_matrix.json": "local_probe_matrix",
    }.get(path, "benchmark_evidence")


def read_json(path: Path) -> Dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def copy_candidate_artifacts(source: Path, destination: Path) -> List[Dict[str, str]]:
    destination.mkdir(parents=True, exist_ok=True)
    artifacts = []
    for name in ALLOWLIST:
        src = source / name
        if not src.is_file():
            continue
        shutil.copy2(src, destination / name)
        artifacts.append({"path": name, "artifact_type": artifact_type(name)})
    return artifacts


def seed_tiny_case(registry: CommonsSpaceRegistry) -> Dict[str, Any]:
    if not CASE_STUDY.exists():
        return {"seeded": False, "reason": "case_study_missing"}
    target = registry.root / "tiny_llama_opus_gateway_repair"
    if (target / "beast_space.json").exists():
        return {"seeded": False, "reason": "already_exists", "space_id": target.name}
    return package_tiny_llama_case(CASE_STUDY, target)


def seed_benchmark_candidate(registry: CommonsSpaceRegistry, candidate: Dict[str, Any]) -> Dict[str, Any]:
    source = PROJECT_ROOT / str(candidate["path"])
    space_id = "bench_" + slug(str(candidate["name"]))
    destination = registry.root / space_id
    if (destination / "beast_space.json").exists():
        return {"seeded": False, "reason": "already_exists", "space_id": space_id}
    artifacts = copy_candidate_artifacts(source, destination)
    if not artifacts:
        shutil.rmtree(destination, ignore_errors=True)
        return {"seeded": False, "reason": "no_allowlisted_artifacts", "space_id": space_id}

    run_manifest = read_json(source / "run_manifest.json")
    provider_fitness = read_json(source / "provider_fitness.json")
    subsystem_results = read_json(source / "subsystem_results.json")
    verifier_passed = bool(
        run_manifest.get("passed")
        or provider_fitness.get("passed")
        or subsystem_results.get("passed")
    )
    try:
        manifest = build_manifest(
            destination,
            space_id=space_id,
            name=str(candidate["name"]).replace("_", " ").title(),
            task_class=str(run_manifest.get("task_class") or "benchmark_replay_candidate"),
            artifacts=artifacts,
            hardware_profile={
                "execution_class": "benchmark_archive_replay",
                "gpu_required": False,
                "local_model": run_manifest.get("model") or None,
            },
            verifier_bundles=[{
                "bundle_id": "deterministic_integrity_replay",
                "commands": [],
                "expected_returncode": 0,
                "artifact_scope": "metadata_only_archive",
            }],
            reduction_claims={
                "cloud_calls_avoided": 0,
                "cloud_calls_evidence": "pending_replay_measurement",
                "tokens_avoided": None,
                "gpu_avoided": False,
                "capability_preserved": verifier_passed,
            },
            safety={
                "risk": "medium",
                "approval_required": True,
                "rollback_required": False,
                "promotion_state": "candidate",
                "adoption_mode": "advisory",
            },
            lineage={
                "case_study": str(candidate["name"]),
                "source_path": str(candidate["path"]),
                "registration_score": candidate.get("registration_score"),
                "signals": candidate.get("signals") or [],
            },
        )
    except ValueError as exc:
        shutil.rmtree(destination, ignore_errors=True)
        return {"seeded": False, "reason": "privacy_or_manifest_blocked", "space_id": space_id, "error": str(exc)}
    receipt = build_reduction_receipt(
        space_manifest=manifest,
        baseline_route={
            "route_id": "unregistered_benchmark_archive",
            "provider": "unknown",
            "status": "not_reusable_without_space_manifest",
            "provider_calls": None,
            "tokens": None,
            "latency_ms": None,
        },
        optimized_route={
            "route_id": "commons_registered_metadata_reuse",
            "provider": "local_beast_commons",
            "status": "quarantined_hypothesis",
            "provider_calls": 0,
            "cloud_provider_calls": 0,
            "tokens": None,
            "latency_ms": None,
        },
        displacement={
            "provider_calls_avoided": 0,
            "tokens_avoided": None,
            "latency_avoided_ms": None,
            "evidence_class": "pending_local_replay",
            "counterfactual": False,
            "notes": "Seeded as a metadata-only registration candidate. No compute-displacement credit is claimed until replay/adoption evidence exists.",
        },
        verifier={
            "passed": verifier_passed,
            "returncode": 0 if verifier_passed else None,
            "command": "deterministic manifest/privacy/receipt validation",
            "latency_ms": None,
        },
        resource_deltas={
            "gpu_avoided": False,
            "measurement_status": "pending_replay_measurement",
        },
        provenance={
            "source_path": str(candidate["path"]),
            "registration_score": candidate.get("registration_score"),
        },
        rollback_available=False,
        approval_required=True,
    )
    write_space(destination, manifest, receipt)
    manifest_validation = validate_manifest(destination, manifest)
    receipt_validation = validate_reduction_receipt(receipt)
    if not manifest_validation.get("valid") or not receipt_validation.get("valid"):
        shutil.rmtree(destination, ignore_errors=True)
        return {
            "seeded": False,
            "reason": "validation_failed",
            "space_id": space_id,
            "manifest": manifest_validation,
            "receipt": receipt_validation,
        }
    replay = registry.replay(space_id, deterministic_only=True, contributor_id=os.environ.get("BEAST_NODE_ID", "seed"))
    return {
        "seeded": True,
        "space_id": space_id,
        "artifact_count": len(artifacts),
        "manifest": manifest_validation,
        "receipt": receipt_validation,
        "replay": {
            "reproduced": replay.get("reproduced"),
            "trust_score": replay.get("trust_score"),
        },
    }


def main() -> None:
    registry = CommonsSpaceRegistry()
    seed_limit = max(0, int(os.environ.get("BEAST_COMMONS_SEED_LIMIT", "6")))
    seed_offset = max(0, int(os.environ.get("BEAST_COMMONS_SEED_OFFSET", "0")))
    result: Dict[str, Any] = {
        "beast_object_type": "commons_node_seed_result",
        "node_id": os.environ.get("BEAST_NODE_ID", "local"),
        "root": str(registry.root),
        "tiny_case": seed_tiny_case(registry),
        "benchmark_candidates": [],
    }
    candidates = registry.registration_candidates(limit=max((seed_limit + seed_offset) * 8, 50)).get("candidates") or []
    candidates = [
        candidate for candidate in candidates
        if str(candidate.get("source") or "") == "benchmarks/results"
        or str(candidate.get("candidate_kind") or "") == "benchmark_result_space"
    ]
    candidates = candidates[seed_offset:]
    seeded = 0
    for candidate in candidates:
        if seeded >= seed_limit:
            break
        item = seed_benchmark_candidate(registry, candidate)
        result["benchmark_candidates"].append(item)
        if item.get("seeded"):
            seeded += 1
    result["seeded_benchmark_count"] = seeded
    result["registry"] = registry.list_spaces().get("scoreboard")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Normalize existing Forge KV and provider-matrix evidence for Truth Arena.

This script does not rerun providers or KV engines. It mines already-written
receipts and emits a sidecar JSON that `benchmarks/c4x_truth_arena.py` can
ingest through `--compute-metrics`.

The boundary is intentionally strict:

- llama.cpp prompt-cache receipts count as engine-local prefix-cache evidence.
- restart-boundary receipts can prove warm-before-restart and cold-after-restart
  behavior, but not portable raw-KV restore.
- ML-KEM KV transport with a test-oracle payload remains hypothesis transport
  evidence, not runtime-native KV reuse.
- provider tournaments/model-fitness/omni/generation receipts become provider
  evidence lanes, not proof-first truth custody.
- C4-X RAG benchmark receipts become RAG War lanes, preserving corpus-poor and
  seeded-pgvector behavior without granting proof-first truth custody.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import statistics
import sys
from typing import Any, Iterable, Mapping

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.kernel.compute.deterministic_intelligence import sha256_digest, utc_now_iso  # noqa: E402


DEFAULT_OUTPUT = REPO_ROOT / "evidence" / "c4x-truth-arena-sidecars" / "existing-evidence-sidecar.json"

DEFAULT_INPUTS = (
    REPO_ROOT / "evidence/forge_kv/llamacpp_prompt_cache_20260720T115125Z.json",
    REPO_ROOT / "evidence/forge_kv/llamacpp_restart_boundary_20260720T131312Z.json",
    REPO_ROOT / "evidence/forge-kv-ml-kem-transport/latest.json",
    REPO_ROOT / "benchmarks/results/provider_tournament_live_smoke_escalated/provider_tournament_gauntlet.json",
    REPO_ROOT / "benchmarks/results/beast_provider_model_fitness_live_free_model_fitness.json",
    REPO_ROOT / "benchmarks/results/beast_nvidia_nemotron_super_120_omni_gauntlet_live/omni_report.json",
    REPO_ROOT / "evidence/generation-gauntlet/2026-08-03T000000-live-gemini-hf-e.json",
    REPO_ROOT / "evidence/c4x-external-breakthrough-benchmark/2026-08-03T-c4x-external-oracle-topology-domain-inrepo/benchmark.json",
    REPO_ROOT / "evidence/c4x-external-breakthrough-benchmark/2026-08-03T-c4x-external-rag-smoke/benchmark.json",
    REPO_ROOT / "evidence/c4x-external-breakthrough-benchmark/pgvector-rag-real-run-002/benchmark.json",
    REPO_ROOT / "evidence/c4x-external-breakthrough-benchmark/pgvector-rag-real-run-005/benchmark.json",
)


def build_sidecar(paths: Iterable[str | Path] = DEFAULT_INPUTS) -> dict[str, Any]:
    systems: dict[str, dict[str, Any]] = {}
    source_receipts: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    for raw_path in paths:
        path = Path(raw_path)
        if not path.is_absolute():
            path = REPO_ROOT / path
        if not path.exists():
            skipped.append({"path": str(path), "reason": "missing"})
            continue
        payload = _load_json(path)
        source_receipts.append(_source_receipt(path, payload))
        systems.update(_extract_lanes(path, payload))

    sidecar_core = {
        "beast_object_type": "c4x_truth_arena_existing_evidence_sidecar",
        "version": "1.0",
        "observed_at": utc_now_iso(),
        "claim_boundary": (
            "Normalizes historical Forge KV, provider tournament, provider fitness, "
            "xAI/Omni, generation gauntlet, and C4-X RAG benchmark receipts into "
            "Truth Arena sidecar metrics. It does not rerun engines/providers or "
            "retrievers and does not grant proof-first custody to provider, KV, or "
            "RAG lanes."
        ),
        "systems": systems,
        "source_receipts": source_receipts,
        "skipped_inputs": skipped,
        "summary": _summary(systems),
    }
    return {**sidecar_core, "receipt_digest": sha256_digest(sidecar_core)}


def _extract_lanes(path: Path, payload: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    kind = str(payload.get("beast_object_type") or "")
    if kind == "forge_kv_llamacpp_prompt_cache_proof":
        return _llamacpp_prompt_cache(path, payload)
    if kind == "forge_kv_llamacpp_restart_boundary_proof":
        return _llamacpp_restart_boundary(path, payload)
    if kind == "forge_kv_ml_kem_transport_gauntlet":
        return _forge_kv_ml_kem(path, payload)
    if kind == "provider_tournament_gauntlet":
        return _provider_tournament(path, payload)
    if kind == "provider_model_fitness_snapshot":
        return _provider_fitness(path, payload)
    if kind == "beast_xai_omni_gauntlet":
        return _omni_provider(path, payload)
    if kind == "generation_gauntlet_receipt":
        return _generation_gauntlet(path, payload)
    if kind == "c4x_external_breakthrough_benchmark":
        return _c4x_rag_benchmark(path, payload)
    return {}


def _llamacpp_prompt_cache(path: Path, payload: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    trials = [trial for trial in payload.get("trials", []) if isinstance(trial, Mapping)]
    baseline = [trial.get("baseline", {}) for trial in trials if isinstance(trial.get("baseline"), Mapping)]
    cached = [trial.get("cached", {}) for trial in trials if isinstance(trial.get("cached"), Mapping)]
    cold_ms = _avg(item.get("prompt_ms") for item in baseline)
    warm_ms = _avg(item.get("prompt_ms") for item in cached)
    cold_tokens = _avg(item.get("prompt_n") for item in baseline)
    warm_tokens = _avg(item.get("prompt_n") for item in cached)
    cache_n = _avg(item.get("cache_n") for item in cached)
    return {
        "kv_llamacpp_prompt_cache": {
            "lane": "kv_reuse",
            "engine": str(payload.get("engine") or "llama.cpp"),
            "runtime_native_kv_state": True,
            "runtime_native_prefix_cache": True,
            "portable_raw_kv": bool(payload.get("portable_raw_kv")),
            "synthetic_payload": False,
            "claim_class": "observed_engine_local_prefix_cache",
            "cold_ttft_ms": cold_ms,
            "warm_ttft_ms": warm_ms,
            "input_tokens": round(cold_tokens or 0),
            "prefill_tokens_computed": round(warm_tokens or 0),
            "cached_tokens_reused": round(cache_n or 0),
            "provider_calls": 0,
            "kv_cases_passed": ("exact_repeated_prefix",),
            "kv_cases_failed": (),
            "source_path": _rel(path),
            "source_receipt_digest": _receipt_digest(payload),
            "boundary": str(payload.get("proof_scope") or "engine-local prompt cache only"),
        }
    }


def _llamacpp_restart_boundary(path: Path, payload: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    before = payload.get("before_restart", {}) if isinstance(payload.get("before_restart"), Mapping) else {}
    baseline = before.get("baseline", {}) if isinstance(before.get("baseline"), Mapping) else {}
    warm = before.get("warm_cache", {}) if isinstance(before.get("warm_cache"), Mapping) else {}
    after = payload.get("after_restart", {}) if isinstance(payload.get("after_restart"), Mapping) else {}
    cache_survived = int(after.get("cache_n") or 0) > 0
    return {
        "kv_llamacpp_restart_boundary": {
            "lane": "kv_reuse",
            "engine": "llama.cpp",
            "runtime_native_kv_state": True,
            "runtime_native_prefix_cache": True,
            "portable_raw_kv": bool(payload.get("portable_raw_kv")),
            "synthetic_payload": False,
            "claim_class": "observed_restart_boundary",
            "cold_ttft_ms": _float(baseline.get("prompt_ms")),
            "warm_ttft_ms": _float(warm.get("prompt_ms")),
            "restart_restored_ttft_ms": _float(after.get("prompt_ms")),
            "input_tokens": int(baseline.get("prompt_n") or 0),
            "prefill_tokens_computed": int(after.get("prompt_n") or 0),
            "cached_tokens_reused": int(warm.get("cache_n") or 0),
            "provider_calls": 0,
            "kv_cases_passed": ("engine_process_restarted",) if cache_survived else (),
            "kv_cases_failed": ("engine_process_restarted",),
            "source_path": _rel(path),
            "source_receipt_digest": _receipt_digest(payload),
            "boundary": "controlled restart showed prompt cache did not survive as portable raw KV restore",
        }
    }


def _forge_kv_ml_kem(path: Path, payload: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    projection = payload.get("normalized_projection", {}) if isinstance(payload.get("normalized_projection"), Mapping) else {}
    transport = payload.get("transport_receipt", {}) if isinstance(payload.get("transport_receipt"), Mapping) else {}
    return {
        "kv_forge_ml_kem_transport": {
            "lane": "kv_reuse",
            "engine": str(projection.get("target_engine") or projection.get("engine") or ""),
            "runtime_native_kv_state": bool(projection.get("engine_specific_proof")),
            "runtime_native_prefix_cache": False,
            "portable_raw_kv": bool(projection.get("portable_raw_kv")),
            "synthetic_payload": projection.get("payload_kind") == "test_oracle",
            "claim_class": str(projection.get("claim_class") or "hypothesis"),
            "transport_verified": bool(projection.get("transport_verified")),
            "payload_bytes_transported": int(projection.get("bytes_transferred_verified") or 0),
            "provider_calls": 0,
            "provider_calls_avoided": int(projection.get("provider_calls_avoided") or 0),
            "cached_tokens_reused": int(projection.get("tokens_avoided_observed") or 0),
            "kv_cases_passed": ("cache_transported_to_second_node",) if projection.get("transport_verified") else (),
            "kv_cases_failed": ("cache_transported_to_second_node",),
            "source_path": _rel(path),
            "source_receipt_digest": str(payload.get("receipt_digest") or transport.get("receipt_digest") or _receipt_digest(payload)),
            "boundary": str(payload.get("claim_boundary") or projection.get("notes") or "ML-KEM-bound transport only"),
        }
    }


def _provider_tournament(path: Path, payload: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    scoreboard = payload.get("scoreboard", {}) if isinstance(payload.get("scoreboard"), Mapping) else {}
    rows = [row for row in payload.get("tournament_rows", []) if isinstance(row, Mapping)]
    live_latencies = [_float(row.get("latency_ms")) for row in rows if _float(row.get("latency_ms")) is not None]
    return {
        "provider_matrix_tournament": {
            "lane": "provider_matrix",
            "provider": "multi_provider_registry",
            "model": "configured_provider_inventory",
            "provider_calls": int(scoreboard.get("live_tests_attempted") or 0),
            "provider_clean_completed": int(scoreboard.get("passed") or 0),
            "provider_rescued_completed": 0,
            "completion_rate": round(int(scoreboard.get("passed") or 0) / max(1, int(scoreboard.get("live_tests_attempted") or 0)), 6),
            "average_latency_ms": _avg(live_latencies),
            "negative_capability_count": len(scoreboard.get("competitor_failed_or_error") or ()),
            "source_path": _rel(path),
            "source_receipt_digest": str(payload.get("receipt_hash") or _receipt_digest(payload)),
            "boundary": "live provider reachability/configuration matrix; not C4-X proof custody",
        }
    }


def _provider_fitness(path: Path, payload: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    lanes: dict[str, dict[str, Any]] = {}
    models = payload.get("models", []) if isinstance(payload.get("models"), list) else []
    for item in models:
        if not isinstance(item, Mapping):
            continue
        provider = str(item.get("provider") or "unknown")
        model = str(item.get("model") or "unknown").replace("/", "_").replace(":", "_")
        lanes[f"provider_fitness_{provider}_{model}"[:120]] = {
            "lane": "live_provider",
            "provider": provider,
            "model": str(item.get("model") or ""),
            "provider_calls": int(item.get("samples") or 0),
            "provider_clean_completed": int(item.get("provider_clean_completed") or item.get("clean_completed") or 0),
            "provider_rescued_completed": int(item.get("provider_rescued_completed") or item.get("rescued_completed") or 0),
            "completion_rate": _float(item.get("completion_rate")),
            "average_latency_ms": _float(item.get("avg_latency_ms")),
            "input_tokens": int(item.get("total_tokens") or 0),
            "negative_capability_count": int(item.get("endpoint_failures") or 0),
            "source_path": _rel(path),
            "source_receipt_digest": _receipt_digest(payload),
            "boundary": "provider model fitness snapshot; not C4-X proof custody",
        }
    return lanes


def _omni_provider(path: Path, payload: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    lanes: dict[str, dict[str, Any]] = {}
    for lane_id, item in (payload.get("live_efficiency_summary") or {}).items():
        if not isinstance(item, Mapping):
            continue
        lanes[f"provider_omni_{lane_id}"] = {
            "lane": "live_provider",
            "provider": str(payload.get("omni_provider") or "omni_provider"),
            "model": str((payload.get("live_settings") or {}).get("model") or ""),
            "provider_calls": int(item.get("tasks") or 0),
            "provider_clean_completed": int(item.get("clean_completed") or 0),
            "provider_rescued_completed": int(item.get("rescued_completed") or 0),
            "completion_rate": _float(item.get("completion_rate")),
            "average_latency_ms": _float(item.get("average_latency_ms")),
            "average_provider_tokens": _float(item.get("average_provider_tokens")),
            "input_tokens": int(round(float(item.get("average_provider_tokens") or 0) * int(item.get("tasks") or 0))),
            "route_confidence": str((payload.get("live_summary") or {}).get(str(payload.get("omni_provider") or ""), {}).get("route_confidence") or ""),
            "source_path": _rel(path),
            "source_receipt_digest": _receipt_digest(payload),
            "boundary": "Omni live provider lane; provider outputs may be rescued by BEAST but do not gain C4-X proof-first custody",
        }
    return lanes


def _generation_gauntlet(path: Path, payload: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    text = payload.get("text", {}) if isinstance(payload.get("text"), Mapping) else {}
    image = payload.get("image", {}) if isinstance(payload.get("image"), Mapping) else {}
    boundary = payload.get("provider_boundary", {}) if isinstance(payload.get("provider_boundary"), Mapping) else {}
    return {
        "provider_teach_replay_generation_gauntlet": {
            "lane": "provider_teach_replay",
            "provider": str(boundary.get("provider_id") or ""),
            "model": f"chat:{boundary.get('chat_provider_id') or ''}|image:{boundary.get('provider_id') or ''}",
            "provider_calls": int(text.get("provider_calls_used") or 0) + int(image.get("provider_calls_used") or 0),
            "provider_calls_avoided": int((payload.get("scorecard_after") or {}).get("provider_calls_avoided") or 0),
            "provider_clean_completed": int(text.get("case_count") or 0) + int(image.get("case_count") or 0) - int(text.get("failed_count") or 0) - int(image.get("failed_count") or 0),
            "provider_rescued_completed": 0,
            "completion_rate": round(
                (int(text.get("case_count") or 0) + int(image.get("case_count") or 0) - int(text.get("failed_count") or 0) - int(image.get("failed_count") or 0))
                / max(1, int(text.get("case_count") or 0) + int(image.get("case_count") or 0)),
                6,
            ),
            "source_path": _rel(path),
            "source_receipt_digest": str(payload.get("receipt_digest") or _receipt_digest(payload)),
            "provider_receipt_digests": tuple(boundary.get("provider_receipt_digests") or ()),
            "boundary": "teach/replay generation lane; proves provider calls can drop after crystal/asset reuse, not C4-X proof custody",
        }
    }


def _c4x_rag_benchmark(path: Path, payload: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    systems = payload.get("systems", {}) if isinstance(payload.get("systems"), Mapping) else {}
    run_id = str(payload.get("run_id") or path.parent.name)
    lanes: dict[str, dict[str, Any]] = {}
    for system_id, score in systems.items():
        if not isinstance(score, Mapping) or not _is_rag_war_system(str(system_id)):
            continue
        chunk_counts: list[int] = []
        retrieved_case_count = 0
        cases = payload.get("cases", {}) if isinstance(payload.get("cases"), Mapping) else {}
        for case in cases.values():
            if not isinstance(case, Mapping):
                continue
            outputs = case.get("baseline_outputs") if isinstance(case.get("baseline_outputs"), Mapping) else {}
            output = outputs.get(system_id) if isinstance(outputs, Mapping) else None
            if not isinstance(output, Mapping):
                continue
            count = output.get("retrieved_chunk_count")
            if isinstance(count, int):
                chunk_counts.append(count)
                retrieved_case_count += int(count > 0)
        lane_id = f"rag_{_safe_id(run_id)}_{_safe_id(str(system_id))}"[:160]
        lanes[lane_id] = {
            "lane": "rag_retrieval",
            "rag_system": str(system_id),
            "retriever": _rag_retriever_type(run_id, str(system_id)),
            "corpus_state": _rag_corpus_state(run_id, str(system_id), score),
            "case_count": int(score.get("case_count") or 0),
            "semantic_correct": int(score.get("semantic_correct") or 0),
            "semantic_accuracy": _float(score.get("semantic_accuracy")),
            "honest_uncertainty": int(score.get("honest_uncertainty") or 0),
            "visual_present": int(score.get("visual_present") or 0),
            "artifact_custody_valid": int(score.get("artifact_custody_valid") or 0),
            "proof_first": int(score.get("proof_first") or 0),
            "provider_calls": int(score.get("provider_calls_used") or 0),
            "retrieved_case_count": retrieved_case_count,
            "average_retrieved_chunks": _avg(chunk_counts),
            "source_path": _rel(path),
            "source_receipt_digest": str(payload.get("receipt_digest") or _receipt_digest(payload)),
            "boundary": "RAG War lane: retrieval/semantic evidence only; no proof-first or artifact-custody credit unless explicitly present",
        }
    return lanes


def _is_rag_war_system(system_id: str) -> bool:
    return system_id in {
        "rag_nearest_exemplar",
        "beast_local_semantic_cache",
        "external_rag_retrieval",
        "cached_named_template",
    }


def _rag_retriever_type(run_id: str, system_id: str) -> str:
    if system_id == "external_rag_retrieval" and "pgvector" in run_id:
        return "aurora_pgvector"
    if system_id == "external_rag_retrieval":
        return "external_rag_command"
    if system_id == "beast_local_semantic_cache":
        return "local_semantic_cache"
    if system_id == "rag_nearest_exemplar":
        return "nearest_exemplar_reference"
    return "cached_template_reference"


def _rag_corpus_state(run_id: str, system_id: str, score: Mapping[str, Any]) -> str:
    if system_id != "external_rag_retrieval":
        return "reference_or_local"
    if "smoke" in run_id:
        return "smoke_adapter"
    if "pgvector-rag-real-run-001" in run_id or "pgvector-rag-real-run-002" in run_id:
        return "live_pgvector_corpus_poor"
    if "pgvector-rag-real-run" in run_id and int(score.get("semantic_correct") or 0) > 0:
        return "live_pgvector_seeded_operational_patterns"
    return "external_unknown"


def _summary(systems: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    return {
        "system_count": len(systems),
        "kv_lane_count": sum(1 for item in systems.values() if item.get("lane") == "kv_reuse"),
        "provider_lane_count": sum(1 for item in systems.values() if str(item.get("lane", "")).startswith("provider") or item.get("lane") == "live_provider"),
        "rag_lane_count": sum(1 for item in systems.values() if item.get("lane") == "rag_retrieval"),
        "provider_calls_observed": sum(int(item.get("provider_calls") or 0) for item in systems.values()),
        "provider_calls_avoided_observed": sum(int(item.get("provider_calls_avoided") or 0) for item in systems.values()),
        "cached_tokens_reused_observed": sum(int(item.get("cached_tokens_reused") or 0) for item in systems.values()),
        "kv_runtime_native_lane_count": sum(1 for item in systems.values() if item.get("lane") == "kv_reuse" and item.get("runtime_native_kv_state") is True),
        "rag_best_semantic_accuracy": max((_float(item.get("semantic_accuracy")) or 0.0 for item in systems.values() if item.get("lane") == "rag_retrieval"), default=0.0),
    }


def _source_receipt(path: Path, payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "path": _rel(path),
        "beast_object_type": str(payload.get("beast_object_type") or ""),
        "receipt_digest": str(payload.get("receipt_digest") or payload.get("receipt_hash") or _receipt_digest(payload)),
        "sha256": _receipt_digest(payload),
    }


def _load_json(path: Path) -> Mapping[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError(f"{path} did not contain a JSON object")
    return payload


def _receipt_digest(payload: Mapping[str, Any]) -> str:
    return sha256_digest(payload)


def _avg(values: Iterable[Any]) -> float | None:
    floats = [_float(value) for value in values]
    floats = [value for value in floats if value is not None]
    if not floats:
        return None
    return round(statistics.mean(floats), 6)


def _float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def _safe_id(value: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in value.lower()).strip("_")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a Truth Arena sidecar from existing evidence.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("inputs", nargs="*", help="Optional evidence JSON paths. Defaults to known Forge KV/provider receipts.")
    args = parser.parse_args()
    sidecar = build_sidecar(args.inputs or DEFAULT_INPUTS)
    output = Path(args.output)
    if not output.is_absolute():
        output = REPO_ROOT / output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(sidecar, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "sidecar_path": str(output),
        "receipt_digest": sidecar["receipt_digest"],
        "system_count": sidecar["summary"]["system_count"],
        "kv_lane_count": sidecar["summary"]["kv_lane_count"],
        "provider_lane_count": sidecar["summary"]["provider_lane_count"],
        "rag_lane_count": sidecar["summary"]["rag_lane_count"],
    }, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

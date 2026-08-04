#!/usr/bin/env python3
"""C4-X three-front Truth Arena.

The arena deliberately separates three questions that should not be averaged
into one flattering number:

1. Truth: did the contender reach the right conclusion under an independent
   oracle, and did it preserve proof-first/text/visual custody?
2. Compute: how much inference/retrieval/cache work did it report needing?
3. Custody/security: did it satisfy hard gates such as proof-first execution,
   artifact custody, oracle independence, and no critical tamper boundary leaks?

This module wraps the existing C4-X external breakthrough benchmark so it does
not create a second oracle. KV-runtime and live-provider measurements can be
attached as sidecar metrics, but this first arena refuses to award KV credit
unless real runtime-native measurements are supplied.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import sys
from typing import Any, Mapping

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.kernel.compute.deterministic_intelligence import sha256_digest, utc_now_iso  # noqa: E402
from scripts.run_c4x_external_breakthrough_benchmark import run_breakthrough_benchmark  # noqa: E402


DEFAULT_EVIDENCE_ROOT = REPO_ROOT / "evidence" / "c4x-truth-arena"

TRUTH_POINTS = {
    "semantic_correct": 4,
    "uncertainty_refusal_correct": 3,
    "proof_graph_before_output": 3,
    "text_artifact_custody": 2,
    "visual_artifact_custody": 2,
    "cross_modal_entailment": 1,
    "independent_oracle_agreement": 1,
}

KV_RUNTIME_CASES = (
    "exact_repeated_prefix",
    "one_token_mutation_at_beginning",
    "one_token_mutation_near_suffix",
    "system_prompt_changed",
    "tokenizer_revision_changed",
    "model_revision_changed",
    "quantization_or_precision_changed",
    "policy_fingerprint_changed",
    "engine_process_restarted",
    "cache_transported_to_second_node",
    "payload_bit_flipped",
    "block_id_collision",
    "cross_tenant_replay_attempt",
    "cache_expired_or_stale",
    "memory_pressure_eviction",
    "concurrent_slots_no_cross_request_contamination",
)

COMPUTE_METRIC_FIELDS = (
    "cold_ttft_ms",
    "warm_ttft_ms",
    "restart_restored_ttft_ms",
    "total_duration_ms",
    "provider_calls",
    "input_tokens",
    "cached_tokens",
    "output_tokens",
    "prefill_tokens_computed",
    "cached_tokens_reused",
    "decode_tokens_per_second",
    "payload_bytes_stored",
    "payload_bytes_transported",
    "store_latency_ms",
    "restore_latency_ms",
    "cpu_ram_bytes",
    "gpu_vram_bytes",
    "network_bytes",
    "cost_usd",
)


def run_truth_arena(
    *,
    evaluator_seed: str,
    case_count_per_family: int = 4,
    evidence_root: str | Path = DEFAULT_EVIDENCE_ROOT,
    run_id: str | None = None,
    external_rag_command: str | None = None,
    compute_metrics_path: str | Path | None = None,
) -> dict[str, Any]:
    run_id = run_id or utc_now_iso().replace(":", "").replace("+", "z")
    evidence_root = Path(evidence_root)
    base_report = run_breakthrough_benchmark(
        evaluator_seed=evaluator_seed,
        case_count_per_family=case_count_per_family,
        evidence_root=evidence_root / "_c4x-breakthrough-subruns",
        run_id=f"{run_id}-c4x",
        external_rag_command=external_rag_command,
    )
    compute_metrics = _load_compute_metrics(compute_metrics_path)
    systems = tuple(sorted(base_report["systems"]))
    truth_scoreboard = {
        system_id: _truth_score(system_id, base_report["systems"][system_id])
        for system_id in systems
    }
    compute_scoreboard = {
        system_id: _compute_score(system_id, base_report["systems"][system_id], compute_metrics.get(system_id, {}))
        for system_id in systems
    }
    custody_scoreboard = {
        system_id: _custody_gate(system_id, base_report["systems"][system_id], base_report)
        for system_id in systems
    }
    kv_reuse_war = _kv_reuse_war(compute_metrics)
    provider_evidence = _provider_evidence(compute_metrics)
    rag_war = _rag_war(compute_metrics)
    truth_winner = max(truth_scoreboard, key=lambda system: truth_scoreboard[system]["truth_points"])
    report_core = {
        "beast_object_type": "c4x_three_front_truth_arena",
        "version": "1.0",
        "run_id": run_id,
        "observed_at": utc_now_iso(),
        "claim_boundary": (
            "Three-front arena over the C4-X independent-oracle benchmark. "
            "Truth points are separate from raw compute measurements and hard "
            "custody/security gates. KV runtime credit is withheld unless "
            "runtime-native measurements are supplied; synthetic bytes are not "
            "accepted as public KV proof."
        ),
        "source_benchmark": {
            "run_id": base_report["run_id"],
            "receipt_digest": base_report["receipt_digest"],
            "evidence_root": base_report["evidence_root"],
            "engine_freeze_digest": base_report["scorecard"]["engine_freeze_digest"],
            "generator_seed_digest": base_report["scorecard"]["generator_seed_digest"],
            "independent_semantic_oracle": base_report["scorecard"]["independent_semantic_oracle"],
        },
        "arena_scorecard": {
            "truth_winner": truth_winner,
            "truth_winner_points": truth_scoreboard[truth_winner]["truth_points"],
            "truth_point_max_per_case": sum(TRUTH_POINTS.values()),
            "heldout_cases": base_report["scorecard"]["heldout_cases"],
            "randomized_topology_shapes": base_report["scorecard"]["randomized_topology_shapes"],
            "heldout_operational_domains": base_report["scorecard"]["heldout_operational_domains"],
            "external_rag_enabled": base_report["scorecard"]["external_rag_enabled"],
            "beast_truth_custody_gate_pass": custody_scoreboard.get("beast_c4x", {}).get("custody_gate_pass", False),
            "critical_custody_failures": {
                system_id: gate["critical_failures"]
                for system_id, gate in custody_scoreboard.items()
                if gate["critical_failures"]
            },
            "kv_runtime_measurements_supplied": bool(kv_reuse_war["runtime_measurements_supplied"]),
            "kv_case_coverage_count": len(kv_reuse_war["covered_case_measurements"]),
            "provider_evidence_lanes": len(provider_evidence["lanes"]),
            "rag_war_lanes": len(rag_war["lanes"]),
            "rag_best_semantic_accuracy": rag_war["best_semantic_accuracy"],
            "compute_points_mixed_into_truth": False,
        },
        "fronts": {
            "truth_gauntlet": {
                "point_contract": TRUTH_POINTS,
                "scoreboard": truth_scoreboard,
            },
            "compute_reuse": {
                "metric_contract": COMPUTE_METRIC_FIELDS,
                "scoreboard": compute_scoreboard,
                "kv_reuse_war": kv_reuse_war,
                "rag_war": rag_war,
                "provider_evidence": provider_evidence,
            },
            "security_and_custody": {
                "hard_gate_contract": _hard_gate_contract(),
                "scoreboard": custody_scoreboard,
            },
        },
        "cases": _case_arena_summary(base_report),
    }
    report = {**report_core, "receipt_digest": sha256_digest(report_core)}
    run_root = evidence_root / run_id
    run_root.mkdir(parents=True, exist_ok=True)
    (run_root / "truth_arena.json").write_text(json.dumps(report, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    (run_root / "truth_arena.md").write_text(_markdown(report), encoding="utf-8")
    _write_checksums(run_root)
    (evidence_root / "latest.json").write_text(json.dumps(report, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    (evidence_root / "latest.md").write_text(_markdown(report), encoding="utf-8")
    return {**report, "evidence_root": str(run_root)}


def _truth_score(system_id: str, score: Mapping[str, Any]) -> dict[str, Any]:
    cases = int(score.get("case_count") or 0)
    semantic = int(score.get("semantic_correct") or 0)
    uncertainty = int(score.get("honest_uncertainty") or 0)
    proof_first = int(score.get("proof_first") or 0)
    artifact_custody = int(score.get("artifact_custody_valid") or 0)
    visual_present = int(score.get("visual_present") or 0)
    visual_custody = min(artifact_custody, visual_present)
    cross_modal = min(proof_first, artifact_custody, visual_present)
    oracle_agreement = semantic
    points = (
        semantic * TRUTH_POINTS["semantic_correct"]
        + uncertainty * TRUTH_POINTS["uncertainty_refusal_correct"]
        + proof_first * TRUTH_POINTS["proof_graph_before_output"]
        + artifact_custody * TRUTH_POINTS["text_artifact_custody"]
        + visual_custody * TRUTH_POINTS["visual_artifact_custody"]
        + cross_modal * TRUTH_POINTS["cross_modal_entailment"]
        + oracle_agreement * TRUTH_POINTS["independent_oracle_agreement"]
    )
    max_points = cases * sum(TRUTH_POINTS.values())
    return {
        "system_id": system_id,
        "case_count": cases,
        "truth_points": points,
        "truth_point_max": max_points,
        "truth_score": round(points / max(1, max_points), 6),
        "semantic_correct": semantic,
        "uncertainty_refusal_correct": uncertainty,
        "proof_graph_before_output": proof_first,
        "text_artifact_custody": artifact_custody,
        "visual_artifact_custody": visual_custody,
        "cross_modal_entailment": cross_modal,
        "independent_oracle_agreement": oracle_agreement,
        "provider_calls_used": int(score.get("provider_calls_used") or 0),
        "compute_points_included": 0,
    }


def _compute_score(system_id: str, score: Mapping[str, Any], supplied: Mapping[str, Any]) -> dict[str, Any]:
    metrics = {field: supplied.get(field) for field in COMPUTE_METRIC_FIELDS if field in supplied}
    provider_calls = int(metrics.get("provider_calls") if metrics.get("provider_calls") is not None else score.get("provider_calls_used") or 0)
    return {
        "system_id": system_id,
        "measurement_class": "reported_runtime_metrics" if metrics else "benchmark_available_only",
        "provider_calls": provider_calls,
        "raw_metrics": metrics,
        "missing_metrics": [field for field in COMPUTE_METRIC_FIELDS if field not in metrics],
        "score_boundary": "raw measurements only; not mixed into truth points",
    }


def _custody_gate(system_id: str, score: Mapping[str, Any], report: Mapping[str, Any]) -> dict[str, Any]:
    cases = int(score.get("case_count") or 0)
    semantic_count = int(score.get("semantic_correct") or 0)
    semantic_all = semantic_count == cases
    proof_first_all = int(score.get("proof_first") or 0) == cases
    custody_all = int(score.get("artifact_custody_valid") or 0) == cases
    visual_all = int(score.get("visual_present") or 0) == cases
    oracle_independent = report["scorecard"].get("independent_semantic_oracle") is True
    critical: list[str] = []
    if not oracle_independent:
        critical.append("independent_oracle_missing")
    if semantic_count > 0 and not proof_first_all:
        critical.append("semantic_without_proof_first")
    if semantic_count > 0 and not custody_all:
        critical.append("semantic_without_artifact_custody")
    gate_pass = oracle_independent and semantic_all and proof_first_all and custody_all
    return {
        "system_id": system_id,
        "custody_gate_pass": gate_pass,
        "independent_oracle": oracle_independent,
        "all_cases_semantic": semantic_all,
        "all_cases_proof_first": proof_first_all,
        "all_cases_artifact_custody": custody_all,
        "all_cases_visual_present": visual_all,
        "critical_failures": critical,
        "gate_boundary": "critical custody failures are reported as hard failures and are not averaged away by compute speed",
    }


def _kv_reuse_war(compute_metrics: Mapping[str, Any]) -> dict[str, Any]:
    kv_entries = {
        system_id: metrics
        for system_id, metrics in compute_metrics.items()
        if isinstance(metrics, Mapping) and (metrics.get("lane") == "kv_reuse" or system_id.startswith("kv_"))
    }
    covered = sorted({
        str(case)
        for entry in kv_entries.values()
        for case in entry.get("kv_cases_passed", ()) or ()
    })
    runtime_supplied = any(entry.get("runtime_native_kv_state") is True for entry in kv_entries.values())
    return {
        "runtime_measurements_supplied": runtime_supplied,
        "case_contract": KV_RUNTIME_CASES,
        "covered_case_measurements": tuple(covered),
        "accepted_runtime_native_evidence_required": True,
        "synthetic_kv_payload_public_credit": False,
        "score_boundary": "KV lanes publish compute reuse measurements only; no arbitrary intelligence points",
        "reported_lanes": {
            system_id: {
                key: value
                for key, value in metrics.items()
                if key in (
                    *COMPUTE_METRIC_FIELDS,
                    "runtime_native_kv_state",
                    "runtime_native_prefix_cache",
                    "portable_raw_kv",
                    "synthetic_payload",
                    "claim_class",
                    "transport_verified",
                    "engine",
                    "model",
                    "tokenizer",
                    "lane",
                    "kv_cases_passed",
                    "kv_cases_failed",
                    "source_receipt_digest",
                    "source_path",
                    "boundary",
                )
            }
            for system_id, metrics in kv_entries.items()
        },
        "missing_case_measurements": tuple(case for case in KV_RUNTIME_CASES if case not in covered),
    }


def _provider_evidence(compute_metrics: Mapping[str, Any]) -> dict[str, Any]:
    lanes = {
        system_id: metrics
        for system_id, metrics in compute_metrics.items()
        if isinstance(metrics, Mapping) and (
            metrics.get("lane") in {"live_provider", "provider_matrix", "provider_teach_replay"}
            or system_id.startswith("provider_")
            or system_id.startswith("live_provider_")
        )
    }
    return {
        "lanes": {
            system_id: {
                key: value
                for key, value in metrics.items()
                if key
                in {
                    "lane",
                    "provider",
                    "model",
                    "provider_calls",
                    "provider_calls_avoided",
                    "provider_clean_completed",
                    "provider_rescued_completed",
                    "clean_completed",
                    "rescued_completed",
                    "completion_rate",
                    "average_latency_ms",
                    "average_provider_tokens",
                    "cached_tokens",
                    "cost_usd",
                    "source_receipt_digest",
                    "source_path",
                    "boundary",
                    "route_confidence",
                    "negative_capability_count",
                    "provider_receipt_digests",
                }
            }
            for system_id, metrics in lanes.items()
        },
        "score_boundary": "provider lanes report route fitness/usage/replay evidence only; they do not inherit proof-first C4-X custody",
    }


def _rag_war(compute_metrics: Mapping[str, Any]) -> dict[str, Any]:
    lanes = {
        system_id: metrics
        for system_id, metrics in compute_metrics.items()
        if isinstance(metrics, Mapping) and (
            metrics.get("lane") == "rag_retrieval"
            or system_id.startswith("rag_")
        )
    }
    best = max((_float(metrics.get("semantic_accuracy")) or 0.0 for metrics in lanes.values()), default=0.0)
    seeded = [
        metrics for metrics in lanes.values()
        if metrics.get("retriever") == "aurora_pgvector"
        and metrics.get("corpus_state") == "live_pgvector_seeded_operational_patterns"
    ]
    corpus_poor = [
        metrics for metrics in lanes.values()
        if metrics.get("retriever") == "aurora_pgvector"
        and metrics.get("corpus_state") == "live_pgvector_corpus_poor"
    ]
    seeded_best = max((_float(item.get("semantic_accuracy")) or 0.0 for item in seeded), default=0.0)
    corpus_poor_best = max((_float(item.get("semantic_accuracy")) or 0.0 for item in corpus_poor), default=0.0)
    return {
        "lanes": {
            system_id: {
                key: value
                for key, value in metrics.items()
                if key
                in {
                    "lane",
                    "rag_system",
                    "retriever",
                    "corpus_state",
                    "case_count",
                    "semantic_correct",
                    "semantic_accuracy",
                    "honest_uncertainty",
                    "visual_present",
                    "artifact_custody_valid",
                    "proof_first",
                    "provider_calls",
                    "retrieved_case_count",
                    "average_retrieved_chunks",
                    "source_receipt_digest",
                    "source_path",
                    "boundary",
                }
            }
            for system_id, metrics in lanes.items()
        },
        "best_semantic_accuracy": best,
        "aurora_pgvector_seeded_best_accuracy": seeded_best,
        "aurora_pgvector_corpus_poor_best_accuracy": corpus_poor_best,
        "aurora_pgvector_seed_gain": round(seeded_best - corpus_poor_best, 6),
        "custody_credit_boundary": "RAG semantic success does not imply proof-first execution or artifact custody",
    }


def _float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _case_arena_summary(report: Mapping[str, Any]) -> dict[str, Any]:
    cases = {}
    for case_id, case in report["cases"].items():
        baselines = case.get("baselines", {})
        systems = {"beast_c4x": case["beast"]["evaluation"], **baselines}
        cases[case_id] = {
            "scenario": case["scenario"],
            "oracle_expected": case["oracle_expected"],
            "truth": {
                system_id: {
                    "semantic_correct": bool(evaluation.get("semantic_correct")),
                    "honest_uncertainty": bool(evaluation.get("honest_uncertainty")),
                    "proof_first": bool(evaluation.get("proof_first")),
                    "artifact_custody_valid": bool(evaluation.get("artifact_custody_valid")),
                    "visual_present": bool(evaluation.get("visual_present")),
                }
                for system_id, evaluation in systems.items()
            },
        }
    return cases


def _load_compute_metrics(path: str | Path | None) -> dict[str, Any]:
    if not path:
        return {}
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(payload, Mapping) and isinstance(payload.get("systems"), Mapping):
        return dict(payload["systems"])
    if isinstance(payload, Mapping):
        return dict(payload)
    raise ValueError("compute metrics must be a JSON object")


def _hard_gate_contract() -> dict[str, Any]:
    return {
        "tamper_rejection": "required for public custody credit; imported from custody sidecars when supplied",
        "wrong_model_rejection": "required for KV/provider custody credit",
        "wrong_tokenizer_rejection": "required for KV custody credit",
        "cross_tenant_refusal": "required for KV custody credit",
        "stale_policy_refusal": "required for current-claim custody credit",
        "residual_scope_enforcement": "required for residual-worker custody credit",
        "guardian_verification": "required for separate-process custody credit",
        "signature_verification": "post-quantum credit only when fallback_used=false",
        "artifact_attestation": "required for public CI/release custody credit",
    }


def _write_checksums(root: Path) -> None:
    rows = []
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.name != "SHA256SUMS.txt":
            rows.append(f"{_file_sha256(path)}  {path.relative_to(root)}")
    (root / "SHA256SUMS.txt").write_text("\n".join(rows) + "\n", encoding="utf-8")


def _file_sha256(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


def _markdown(report: Mapping[str, Any]) -> str:
    score = report["arena_scorecard"]
    truth = report["fronts"]["truth_gauntlet"]["scoreboard"]
    compute = report["fronts"]["compute_reuse"]
    custody = report["fronts"]["security_and_custody"]["scoreboard"]
    lines = [
        f"# C4-X Truth Arena · {report['run_id']}",
        "",
        f"- Receipt: `{report['receipt_digest']}`",
        f"- Source C4-X receipt: `{report['source_benchmark']['receipt_digest']}`",
        f"- Truth winner: `{score['truth_winner']}` ({score['truth_winner_points']} points)",
        f"- Held-out cases: `{score['heldout_cases']}`",
        f"- Topology shapes: `{score['randomized_topology_shapes']}`",
        f"- Operational domains: `{score['heldout_operational_domains']}`",
        f"- External RAG enabled: `{score['external_rag_enabled']}`",
        f"- BEAST custody gate pass: `{score['beast_truth_custody_gate_pass']}`",
        f"- Compute mixed into truth: `{score['compute_points_mixed_into_truth']}`",
        f"- KV runtime measurements supplied: `{score['kv_runtime_measurements_supplied']}`",
        f"- RAG War lanes: `{score['rag_war_lanes']}`",
        f"- Best RAG semantic accuracy: `{score['rag_best_semantic_accuracy']}`",
        "",
        "## Truth scoreboard",
        "",
    ]
    for system_id, row in sorted(truth.items(), key=lambda item: item[1]["truth_points"], reverse=True):
        lines.append(
            f"- `{system_id}`: {row['truth_points']}/{row['truth_point_max']} "
            f"semantic={row['semantic_correct']}/{row['case_count']} "
            f"proof={row['proof_graph_before_output']}/{row['case_count']} "
            f"custody={row['text_artifact_custody']}/{row['case_count']} "
            f"visual_custody={row['visual_artifact_custody']}/{row['case_count']} "
            f"providers={row['provider_calls_used']}"
        )
    lines.extend(["", "## Compute reuse / KV War", ""])
    kv = compute["kv_reuse_war"]
    lines.append(f"- Runtime-native KV measurements supplied: `{kv['runtime_measurements_supplied']}`")
    lines.append(f"- Synthetic KV public credit: `{kv['synthetic_kv_payload_public_credit']}`")
    lines.append(f"- Covered KV cases: `{list(kv['covered_case_measurements'])}`")
    lines.append(f"- Missing KV case count: `{len(kv['missing_case_measurements'])}`")
    for system_id, row in sorted(kv["reported_lanes"].items()):
        lines.append(
            f"- `{system_id}`: class={row.get('claim_class')} engine={row.get('engine')} "
            f"cold={row.get('cold_ttft_ms')}ms warm={row.get('warm_ttft_ms')}ms "
            f"cached_tokens={row.get('cached_tokens_reused')} passed={row.get('kv_cases_passed')} "
            f"failed={row.get('kv_cases_failed')}"
        )
    lines.extend(["", "## RAG War", ""])
    rag = compute["rag_war"]
    lines.append(f"- Best semantic accuracy: `{rag['best_semantic_accuracy']}`")
    lines.append(f"- Aurora pgvector corpus-poor best: `{rag['aurora_pgvector_corpus_poor_best_accuracy']}`")
    lines.append(f"- Aurora pgvector seeded best: `{rag['aurora_pgvector_seeded_best_accuracy']}`")
    lines.append(f"- Aurora pgvector seed gain: `{rag['aurora_pgvector_seed_gain']}`")
    lines.append(f"- Custody boundary: {rag['custody_credit_boundary']}")
    if not rag["lanes"]:
        lines.append("- none supplied")
    for system_id, row in sorted(rag["lanes"].items(), key=lambda item: (str(item[1].get("retriever")), str(item[0]))):
        lines.append(
            f"- `{system_id}`: retriever={row.get('retriever')} corpus={row.get('corpus_state')} "
            f"semantic={row.get('semantic_correct')}/{row.get('case_count')} "
            f"accuracy={row.get('semantic_accuracy')} chunks={row.get('retrieved_case_count')} "
            f"proof={row.get('proof_first')} custody={row.get('artifact_custody_valid')}"
        )
    lines.extend(["", "## Provider evidence lanes", ""])
    provider_lanes = compute["provider_evidence"]["lanes"]
    if not provider_lanes:
        lines.append("- none supplied")
    for system_id, row in sorted(provider_lanes.items()):
        lines.append(
            f"- `{system_id}`: provider={row.get('provider')} model={row.get('model')} "
            f"calls={row.get('provider_calls')} clean={row.get('provider_clean_completed')} "
            f"rescued={row.get('provider_rescued_completed')} avoided={row.get('provider_calls_avoided', 0)} "
            f"negative={row.get('negative_capability_count', 0)}"
        )
    lines.extend(["", "## Custody hard gates", ""])
    for system_id, row in sorted(custody.items()):
        failures = ", ".join(row["critical_failures"]) or "none"
        lines.append(f"- `{system_id}`: pass={row['custody_gate_pass']} failures={failures}")
    lines.extend([
        "",
        "## Boundary",
        "",
        str(report["claim_boundary"]),
    ])
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the C4-X three-front Truth Arena.")
    parser.add_argument("--evaluator-seed", required=True)
    parser.add_argument("--case-count-per-family", type=int, default=4)
    parser.add_argument("--evidence-root", default=str(DEFAULT_EVIDENCE_ROOT))
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--external-rag-command", default=None)
    parser.add_argument("--compute-metrics", default=None)
    args = parser.parse_args()
    report = run_truth_arena(
        evaluator_seed=args.evaluator_seed,
        case_count_per_family=args.case_count_per_family,
        evidence_root=args.evidence_root,
        run_id=args.run_id,
        external_rag_command=args.external_rag_command,
        compute_metrics_path=args.compute_metrics,
    )
    print(json.dumps({
        "truth_arena_pass": report["arena_scorecard"]["beast_truth_custody_gate_pass"],
        "evidence_root": report["evidence_root"],
        "receipt_digest": report["receipt_digest"],
        "truth_winner": report["arena_scorecard"]["truth_winner"],
        "critical_custody_failures": report["arena_scorecard"]["critical_custody_failures"],
    }, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

import json
from pathlib import Path
import sys

from benchmarks.c4x_existing_evidence_sidecar import build_sidecar
from benchmarks.c4x_truth_arena import KV_RUNTIME_CASES, run_truth_arena


def test_truth_arena_separates_truth_compute_and_custody(tmp_path: Path):
    report = run_truth_arena(
        evaluator_seed="pytest-truth-arena",
        case_count_per_family=1,
        evidence_root=tmp_path,
        run_id="pytest-truth-arena",
    )

    assert report["beast_object_type"] == "c4x_three_front_truth_arena"
    assert report["arena_scorecard"]["compute_points_mixed_into_truth"] is False
    assert report["arena_scorecard"]["truth_winner"] == "beast_c4x"
    assert report["arena_scorecard"]["beast_truth_custody_gate_pass"] is True
    assert report["fronts"]["truth_gauntlet"]["scoreboard"]["beast_c4x"]["truth_score"] == 1.0
    assert report["fronts"]["compute_reuse"]["kv_reuse_war"]["synthetic_kv_payload_public_credit"] is False
    assert report["fronts"]["compute_reuse"]["kv_reuse_war"]["missing_case_measurements"] == KV_RUNTIME_CASES
    assert (tmp_path / "pytest-truth-arena" / "truth_arena.json").is_file()
    assert (tmp_path / "pytest-truth-arena" / "truth_arena.md").is_file()
    assert (tmp_path / "pytest-truth-arena" / "SHA256SUMS.txt").is_file()


def test_truth_arena_scores_external_rag_semantics_without_custody(tmp_path: Path):
    rag = tmp_path / "semantic_rag.py"
    rag.write_text(
        "\n".join([
            "import json, sys",
            "req = json.loads(sys.stdin.read())",
            "scenario = req['scenario']",
            "family = scenario['family']",
            "source = scenario['source']",
            "target = scenario['target']",
            "meta = scenario.get('metadata', {})",
            "if meta.get('temporal_state') == 'stale':",
            "    answer = f'cannot establish current state for {source} to {target}'",
            "elif family == 'restart_risk':",
            "    answer = f'{source} to {target} class low'",
            "elif family == 'traffic_shift':",
            "    answer = f'{source} to {target} class safe'",
            "else:",
            "    answer = f'{source} to {target} class safe_to_continue'",
            "print(json.dumps({",
            "  'answer_text': answer,",
            "  'retrieved_chunks': [{'text': answer}],",
            "  'current_claim_valid': meta.get('temporal_state') != 'stale',",
            "  'provider_calls_used': 0,",
            "  'artifact_custody_valid': False,",
            "  'proof_first': False,",
            "}))",
        ]),
        encoding="utf-8",
    )

    report = run_truth_arena(
        evaluator_seed="pytest-truth-arena-external-rag",
        case_count_per_family=1,
        evidence_root=tmp_path / "arena",
        run_id="pytest-truth-arena-external-rag",
        external_rag_command=f"{sys.executable} {rag}",
    )

    rag_truth = report["fronts"]["truth_gauntlet"]["scoreboard"]["external_rag_retrieval"]
    rag_custody = report["fronts"]["security_and_custody"]["scoreboard"]["external_rag_retrieval"]

    assert rag_truth["compute_points_included"] == 0
    assert rag_custody["custody_gate_pass"] is False
    if rag_truth["semantic_correct"]:
        assert "semantic_without_proof_first" in rag_custody["critical_failures"]
        assert "semantic_without_artifact_custody" in rag_custody["critical_failures"]


def test_truth_arena_accepts_compute_sidecar_without_truth_point_leakage(tmp_path: Path):
    metrics = tmp_path / "compute_metrics.json"
    metrics.write_text(
        json.dumps({
            "systems": {
                "kv_llamacpp_prompt_cache": {
                    "lane": "kv_reuse",
                    "engine": "llama.cpp",
                    "model": "fixture.gguf",
                    "tokenizer": "fixture-tokenizer",
                    "runtime_native_kv_state": True,
                    "cold_ttft_ms": 100.0,
                    "warm_ttft_ms": 12.0,
                    "cached_tokens_reused": 256,
                    "payload_bytes_stored": 4096,
                },
                "beast_c4x": {
                    "total_duration_ms": 5.0,
                    "provider_calls": 0,
                },
            }
        }),
        encoding="utf-8",
    )

    report = run_truth_arena(
        evaluator_seed="pytest-truth-arena-compute-sidecar",
        case_count_per_family=1,
        evidence_root=tmp_path / "arena",
        run_id="pytest-truth-arena-compute-sidecar",
        compute_metrics_path=metrics,
    )

    beast_truth = report["fronts"]["truth_gauntlet"]["scoreboard"]["beast_c4x"]
    beast_compute = report["fronts"]["compute_reuse"]["scoreboard"]["beast_c4x"]
    kv = report["fronts"]["compute_reuse"]["kv_reuse_war"]

    assert beast_truth["truth_score"] == 1.0
    assert beast_truth["compute_points_included"] == 0
    assert beast_compute["raw_metrics"]["total_duration_ms"] == 5.0
    assert kv["runtime_measurements_supplied"] is True
    assert "exact_repeated_prefix" in kv["missing_case_measurements"]


def test_existing_evidence_sidecar_normalizes_forge_kv_and_provider_receipts(tmp_path: Path):
    prompt_cache = tmp_path / "prompt_cache.json"
    prompt_cache.write_text(
        json.dumps({
            "beast_object_type": "forge_kv_llamacpp_prompt_cache_proof",
            "engine": "llama.cpp",
            "portable_raw_kv": False,
            "proof_scope": "engine local",
            "validated": True,
            "trials": [{
                "baseline": {"cache_n": 0, "prompt_ms": 100.0, "prompt_n": 50},
                "cached": {"cache_n": 45, "prompt_ms": 10.0, "prompt_n": 5},
            }],
        }),
        encoding="utf-8",
    )
    transport = tmp_path / "transport.json"
    transport.write_text(
        json.dumps({
            "beast_object_type": "forge_kv_ml_kem_transport_gauntlet",
            "claim_boundary": "test transport",
            "receipt_digest": "sha256:" + "a" * 64,
            "normalized_projection": {
                "target_engine": "sglang",
                "engine_specific_proof": False,
                "portable_raw_kv": False,
                "payload_kind": "test_oracle",
                "claim_class": "hypothesis",
                "transport_verified": False,
                "bytes_transferred_verified": 0,
                "provider_calls_avoided": 0,
                "tokens_avoided_observed": 0,
            },
        }),
        encoding="utf-8",
    )
    provider = tmp_path / "provider.json"
    provider.write_text(
        json.dumps({
            "beast_object_type": "provider_tournament_gauntlet",
            "receipt_hash": "sha256:" + "b" * 64,
            "scoreboard": {
                "live_tests_attempted": 3,
                "passed": 1,
                "competitor_failed_or_error": ["groq", "openrouter"],
            },
            "tournament_rows": [{"latency_ms": 50.0}],
        }),
        encoding="utf-8",
    )

    sidecar = build_sidecar((prompt_cache, transport, provider))
    systems = sidecar["systems"]

    assert systems["kv_llamacpp_prompt_cache"]["runtime_native_kv_state"] is True
    assert systems["kv_llamacpp_prompt_cache"]["kv_cases_passed"] == ("exact_repeated_prefix",)
    assert systems["kv_forge_ml_kem_transport"]["claim_class"] == "hypothesis"
    assert systems["kv_forge_ml_kem_transport"]["synthetic_payload"] is True
    assert systems["kv_forge_ml_kem_transport"]["runtime_native_kv_state"] is False
    assert systems["provider_matrix_tournament"]["negative_capability_count"] == 2
    assert sidecar["summary"]["kv_lane_count"] == 2
    assert sidecar["summary"]["provider_lane_count"] == 1


def test_existing_evidence_sidecar_normalizes_rag_benchmark_receipts(tmp_path: Path):
    poor = tmp_path / "pgvector-rag-real-run-002" / "benchmark.json"
    poor.parent.mkdir()
    poor.write_text(
        json.dumps({
            "beast_object_type": "c4x_external_breakthrough_benchmark",
            "run_id": "pgvector-rag-real-run-002",
            "receipt_digest": "sha256:" + "c" * 64,
            "systems": {
                "external_rag_retrieval": {
                    "case_count": 12,
                    "semantic_correct": 0,
                    "semantic_accuracy": 0.0,
                    "honest_uncertainty": 12,
                    "visual_present": 0,
                    "artifact_custody_valid": 0,
                    "proof_first": 0,
                    "provider_calls_used": 0,
                }
            },
            "cases": {},
        }),
        encoding="utf-8",
    )
    seeded = tmp_path / "pgvector-rag-real-run-005" / "benchmark.json"
    seeded.parent.mkdir()
    seeded.write_text(
        json.dumps({
            "beast_object_type": "c4x_external_breakthrough_benchmark",
            "run_id": "pgvector-rag-real-run-005",
            "receipt_digest": "sha256:" + "d" * 64,
            "systems": {
                "external_rag_retrieval": {
                    "case_count": 12,
                    "semantic_correct": 12,
                    "semantic_accuracy": 1.0,
                    "honest_uncertainty": 12,
                    "visual_present": 0,
                    "artifact_custody_valid": 0,
                    "proof_first": 0,
                    "provider_calls_used": 0,
                }
            },
            "cases": {
                "case-1": {
                    "baseline_outputs": {
                        "external_rag_retrieval": {"retrieved_chunk_count": 1}
                    }
                }
            },
        }),
        encoding="utf-8",
    )

    sidecar = build_sidecar((poor, seeded))
    lanes = sidecar["systems"]

    assert sidecar["summary"]["rag_lane_count"] == 2
    assert sidecar["summary"]["rag_best_semantic_accuracy"] == 1.0
    assert lanes["rag_pgvector_rag_real_run_002_external_rag_retrieval"]["corpus_state"] == "live_pgvector_corpus_poor"
    assert lanes["rag_pgvector_rag_real_run_005_external_rag_retrieval"]["corpus_state"] == "live_pgvector_seeded_operational_patterns"
    assert lanes["rag_pgvector_rag_real_run_005_external_rag_retrieval"]["retrieved_case_count"] == 1


def test_truth_arena_ingests_existing_evidence_sidecar_as_compute_and_provider_evidence(tmp_path: Path):
    sidecar_path = tmp_path / "sidecar.json"
    sidecar_path.write_text(
        json.dumps({
            "systems": {
                "kv_llamacpp_prompt_cache": {
                    "lane": "kv_reuse",
                    "engine": "llama.cpp",
                    "runtime_native_kv_state": True,
                    "kv_cases_passed": ["exact_repeated_prefix"],
                    "cold_ttft_ms": 100.0,
                    "warm_ttft_ms": 10.0,
                    "cached_tokens_reused": 45,
                    "provider_calls": 0,
                },
                "provider_matrix_tournament": {
                    "lane": "provider_matrix",
                    "provider": "multi",
                    "provider_calls": 3,
                    "provider_clean_completed": 1,
                    "negative_capability_count": 2,
                },
                "rag_pgvector_poor": {
                    "lane": "rag_retrieval",
                    "rag_system": "external_rag_retrieval",
                    "retriever": "aurora_pgvector",
                    "corpus_state": "live_pgvector_corpus_poor",
                    "case_count": 12,
                    "semantic_correct": 0,
                    "semantic_accuracy": 0.0,
                    "artifact_custody_valid": 0,
                    "proof_first": 0,
                },
                "rag_pgvector_seeded": {
                    "lane": "rag_retrieval",
                    "rag_system": "external_rag_retrieval",
                    "retriever": "aurora_pgvector",
                    "corpus_state": "live_pgvector_seeded_operational_patterns",
                    "case_count": 12,
                    "semantic_correct": 12,
                    "semantic_accuracy": 1.0,
                    "artifact_custody_valid": 0,
                    "proof_first": 0,
                },
            }
        }),
        encoding="utf-8",
    )

    report = run_truth_arena(
        evaluator_seed="pytest-truth-arena-existing-sidecar",
        case_count_per_family=1,
        evidence_root=tmp_path / "arena",
        run_id="pytest-truth-arena-existing-sidecar",
        compute_metrics_path=sidecar_path,
    )

    kv = report["fronts"]["compute_reuse"]["kv_reuse_war"]
    providers = report["fronts"]["compute_reuse"]["provider_evidence"]
    rag = report["fronts"]["compute_reuse"]["rag_war"]

    assert "exact_repeated_prefix" in kv["covered_case_measurements"]
    assert "engine_process_restarted" in kv["missing_case_measurements"]
    assert report["arena_scorecard"]["provider_evidence_lanes"] == 1
    assert providers["lanes"]["provider_matrix_tournament"]["negative_capability_count"] == 2
    assert report["arena_scorecard"]["rag_war_lanes"] == 2
    assert rag["aurora_pgvector_seed_gain"] == 1.0
    assert rag["lanes"]["rag_pgvector_seeded"]["artifact_custody_valid"] == 0

import json
from pathlib import Path
import sys
import types

from scripts.run_c4x_external_breakthrough_benchmark import (
    BASELINES,
    IN_REPO_BASELINES,
    generate_heldout_scenarios,
    run_breakthrough_benchmark,
)
from scripts.run_c4x_rds_rag_adapter import _generate_iam_token, run_rds_rag
from scripts.verify_c4x_external_breakthrough_submission import verify_submission


def test_heldout_generator_uses_post_freeze_seed_and_randomized_names():
    first = generate_heldout_scenarios(
        evaluator_seed="outside-seed-a",
        engine_freeze_digest="sha256:" + "a" * 64,
        case_count_per_family=4,
    )
    second = generate_heldout_scenarios(
        evaluator_seed="outside-seed-b",
        engine_freeze_digest="sha256:" + "a" * 64,
        case_count_per_family=4,
    )

    assert len(first) == 12
    assert {scenario.family.value for scenario in first} == {"restart_risk", "traffic_shift", "deployment_safety"}
    assert {scenario.scenario_id for scenario in first} != {scenario.scenario_id for scenario in second}
    assert not {"BEAST", "Commons", "Aegis"} & {scenario.source for scenario in first}
    assert len({scenario.metadata["topology_shape"] for scenario in first}) >= 3
    assert len({scenario.metadata["operational_domain"] for scenario in first}) >= 3


def test_external_breakthrough_benchmark_compares_baselines_and_writes_receipts(tmp_path: Path):
    report = run_breakthrough_benchmark(
        evaluator_seed="pytest-external-breakthrough",
        case_count_per_family=2,
        evidence_root=tmp_path,
        run_id="pytest-breakthrough",
    )

    assert report["scorecard"]["breakthrough_protocol_pass"] is True
    assert report["scorecard"]["independent_semantic_oracle"] is True
    assert report["scorecard"]["randomized_topology_shapes"] >= 3
    assert report["scorecard"]["heldout_operational_domains"] >= 3
    assert report["scorecard"]["third_party_verifier_ready"] is True
    assert report["scorecard"]["in_repo_baseline_count"] == len(IN_REPO_BASELINES)
    assert report["scorecard"]["beast_beats_all_baselines"] is True
    assert report["scorecard"]["heldout_cases"] == 6
    assert report["scorecard"]["cross_modal_families"] == 3
    assert report["scorecard"]["beast_semantic_correct"] == 6
    assert report["scorecard"]["beast_artifact_custody_valid"] == 6
    assert report["scorecard"]["beast_provider_calls_used"] == 0
    assert set(BASELINES).issubset(report["systems"])
    assert set(IN_REPO_BASELINES).issubset(report["systems"])
    assert report["systems"]["beast_capability_composition_rule_engine"]["semantic_correct"] == 6
    assert report["systems"]["beast_capability_composition_rule_engine"]["artifact_custody_valid"] == 0
    assert report["systems"]["beast_c4x"]["total_score"] > max(
        report["systems"][baseline]["total_score"] for baseline in BASELINES
    )
    for case in report["cases"].values():
        assert "oracle_expected" in case
        assert "expected" not in case
        assert case["oracle_expected"]["oracle_input_digest"].startswith("sha256:")
        public_scenario = case["scenario"]
        assert public_scenario["facts"]
        assert "fact_digest" not in public_scenario["facts"][0]
        assert "rules" in public_scenario
        assert "policies" in public_scenario
        assert case["baseline_outputs"]
        assert case["baseline_outputs"]["rag_nearest_exemplar"]["output_digest"].startswith("sha256:")
    assert (tmp_path / "pytest-breakthrough" / "benchmark.json").is_file()
    assert (tmp_path / "pytest-breakthrough" / "SHA256SUMS.txt").is_file()


def test_third_party_submission_verifier_scores_saved_oracle_without_beast_self_grading(tmp_path: Path):
    report = run_breakthrough_benchmark(
        evaluator_seed="pytest-third-party-verifier",
        case_count_per_family=1,
        evidence_root=tmp_path / "benchmark",
        run_id="pytest-third-party-benchmark",
    )
    submission = {
        "system_id": "external_structured_oracle_probe",
        "outputs": {
            case_id: {
                "answer_text": (
                    f"{case['oracle_expected']['source']} to {case['oracle_expected']['target']} "
                    f"class {case['oracle_expected']['class']}"
                ),
                "visual_present": True,
                "reported_status": case["oracle_expected"]["status"],
                "reported_class": case["oracle_expected"]["class"],
                "reported_current_claim_allowed": case["oracle_expected"]["current_claim_allowed"],
                "provider_calls_used": 1,
                "artifact_custody_valid": False,
                "proof_first": False,
            }
            for case_id, case in report["cases"].items()
        },
    }
    submission_path = tmp_path / "submission.json"
    submission_path.write_text(json.dumps(submission), encoding="utf-8")

    verification = verify_submission(
        benchmark_path=tmp_path / "benchmark" / "pytest-third-party-benchmark" / "benchmark.json",
        submission_path=submission_path,
        evidence_root=tmp_path / "verifications",
        run_id="pytest-third-party-verification",
    )

    assert verification["benchmark_receipt_digest"] == report["receipt_digest"]
    assert verification["score"]["semantic_correct"] == report["scorecard"]["heldout_cases"]
    assert verification["score"]["artifact_custody_valid"] == 0
    assert verification["score"]["provider_calls_used"] == report["scorecard"]["heldout_cases"]
    assert (tmp_path / "verifications" / "pytest-third-party-verification" / "verification.json").is_file()


def test_external_rag_command_is_scored_as_optional_real_competitor(tmp_path: Path):
    rag = tmp_path / "fake_external_rag.py"
    rag.write_text(
        "\n".join([
            "import json, sys",
            "req = json.loads(sys.stdin.read())",
            "assert req['contract']['oracle_expected_not_supplied'] is True",
            "print(json.dumps({",
            "  'retrieved_chunks': [{",
            "    'text': req['source'] + ' and ' + req['target'] + ' retrieved by external RAG without proof custody.'",
            "  }],",
            "  'provider_calls_used': 0,",
            "  'current_claim_valid': True,",
            "  'visual_present': False",
            "}))",
        ]),
        encoding="utf-8",
    )

    report = run_breakthrough_benchmark(
        evaluator_seed="pytest-external-rag",
        case_count_per_family=1,
        evidence_root=tmp_path / "benchmark",
        run_id="pytest-external-rag-benchmark",
        external_rag_command=f"{sys.executable} {rag}",
    )

    assert report["scorecard"]["external_rag_enabled"] is True
    assert report["scorecard"]["external_baseline_count"] == 1
    assert "external_rag_retrieval" in report["systems"]
    assert report["systems"]["external_rag_retrieval"]["case_count"] == report["scorecard"]["heldout_cases"]
    assert report["scorecard"]["beast_beats_all_baselines"] is True


def test_rds_rag_adapter_refuses_cleanly_without_config(monkeypatch):
    for name in ("BEAST_RDS_RAG_DSN", "AMAZON_RDS_DSN", "RDS_DSN", "POSTGRES_DSN"):
        monkeypatch.delenv(name, raising=False)

    output = run_rds_rag({
        "case_id": "case:rds",
        "question": "Could restarting Ari-api destabilize Bex-core?",
        "family": "restart_risk",
        "source": "Ari-api",
        "target": "Bex-core",
    })

    assert output["rds_rag_configured"] is False
    assert output["rds_rag_refusal_reason"] == "missing_rds_dsn"
    assert output["provider_calls_used"] == 0
    assert output["current_claim_valid"] is False


def test_rds_rag_adapter_supports_iam_auth_token_mode(monkeypatch):
    seen = {}

    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, query, params):
            seen["query"] = query
            seen["params"] = params

        def fetchall(self):
            return [{"content": "Ari-api Bex-core supported retrieval", "score": 0.9}]

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def cursor(self):
            return Cursor()

    def connect(**kwargs):
        seen["connect"] = kwargs
        return Connection()

    fake_psycopg = types.SimpleNamespace(connect=connect, rows=types.SimpleNamespace(dict_row=object()))
    monkeypatch.setitem(sys.modules, "psycopg", fake_psycopg)
    monkeypatch.setitem(sys.modules, "psycopg.rows", fake_psycopg.rows)
    monkeypatch.delenv("BEAST_RDS_RAG_DSN", raising=False)
    monkeypatch.delenv("AMAZON_RDS_DSN", raising=False)
    monkeypatch.delenv("RDS_DSN", raising=False)
    monkeypatch.delenv("POSTGRES_DSN", raising=False)
    monkeypatch.setenv("BEAST_RDS_RAG_IAM_AUTH", "1")
    monkeypatch.setenv("BEAST_RDS_RAG_HOST", "database-1.cluster-cz6y6wc4a4v6.eu-north-1.rds.amazonaws.com")
    monkeypatch.setenv("BEAST_RDS_RAG_REGION", "eu-north-1")
    monkeypatch.setenv("BEAST_RDS_RAG_USER", "postgres")
    monkeypatch.setenv("BEAST_RDS_RAG_DBNAME", "postgres")
    monkeypatch.setattr(
        "scripts.run_c4x_rds_rag_adapter._generate_iam_token",
        lambda **_kwargs: "temporary-token",
    )

    output = run_rds_rag({
        "case_id": "case:rds",
        "question": "Could restarting Ari-api destabilize Bex-core?",
        "family": "restart_risk",
        "source": "Ari-api",
        "target": "Bex-core",
    })

    assert seen["connect"]["host"] == "database-1.cluster-cz6y6wc4a4v6.eu-north-1.rds.amazonaws.com"
    assert seen["connect"]["port"] == 5432
    assert seen["connect"]["password"] == "temporary-token"
    assert seen["connect"]["sslmode"] == "require"
    assert output["rds_rag_configured"] is True
    assert output["rds_rag_auth_mode"] == "rds_iam_auth_token"
    assert output["retrieved_chunks"][0]["text"] == "Ari-api Bex-core supported retrieval"


def test_rds_rag_adapter_accepts_existing_pgvector_env_names(monkeypatch):
    seen = {}

    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, query, params):
            seen["query"] = query
            seen["params"] = params

        def fetchall(self):
            return [{"content": "pgvector env retrieved chunk"}]

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def cursor(self):
            return Cursor()

    def connect(**kwargs):
        seen["connect"] = kwargs
        return Connection()

    fake_psycopg = types.SimpleNamespace(connect=connect, rows=types.SimpleNamespace(dict_row=object()))
    monkeypatch.setitem(sys.modules, "psycopg", fake_psycopg)
    monkeypatch.setitem(sys.modules, "psycopg.rows", fake_psycopg.rows)
    for name in ("BEAST_RDS_RAG_DSN", "AMAZON_RDS_DSN", "RDS_DSN", "POSTGRES_DSN"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("BEAST_PGVECTOR_IAM_AUTH", "1")
    monkeypatch.setenv("BEAST_PGVECTOR_HOST", "pgvector.cluster.example.rds.amazonaws.com")
    monkeypatch.setenv("BEAST_PGVECTOR_AWS_REGION", "eu-north-1")
    monkeypatch.setenv("BEAST_PGVECTOR_USER", "postgres")
    monkeypatch.setenv("BEAST_PGVECTOR_DATABASE", "postgres")
    monkeypatch.setenv("BEAST_PGVECTOR_PORT", "5432")
    monkeypatch.setenv("BEAST_PGVECTOR_SSLMODE", "require")
    monkeypatch.setattr(
        "scripts.run_c4x_rds_rag_adapter._generate_iam_token",
        lambda **_kwargs: "temporary-token",
    )

    output = run_rds_rag({
        "case_id": "case:pgvector",
        "question": "Could restarting Ari-api destabilize Bex-core?",
        "family": "restart_risk",
        "source": "Ari-api",
        "target": "Bex-core",
    })

    assert seen["connect"]["host"] == "pgvector.cluster.example.rds.amazonaws.com"
    assert seen["connect"]["port"] == 5432
    assert seen["connect"]["dbname"] == "postgres"
    assert output["rds_rag_configured"] is True
    assert output["retrieved_chunks"][0]["text"] == "pgvector env retrieved chunk"


def test_rds_rag_adapter_synthesizes_from_retrieved_guidance_and_public_facts(monkeypatch):
    seen = {}

    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, query, params):
            seen["query"] = query
            seen["params"] = params

        def fetchall(self):
            return [{
                "content": (
                    "restart_risk guidance requires service health, dependency_topology, "
                    "restart_policy, current_evidence, and restart_destabilization rule."
                )
            }]

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def cursor(self):
            return Cursor()

    def connect(**kwargs):
        seen["connect"] = kwargs
        return Connection()

    fake_psycopg = types.SimpleNamespace(connect=connect, rows=types.SimpleNamespace(dict_row=object()))
    monkeypatch.setitem(sys.modules, "psycopg", fake_psycopg)
    monkeypatch.setitem(sys.modules, "psycopg.rows", fake_psycopg.rows)
    for name in ("BEAST_RDS_RAG_DSN", "AMAZON_RDS_DSN", "RDS_DSN", "POSTGRES_DSN"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("BEAST_RDS_RAG_IAM_AUTH", "1")
    monkeypatch.setenv("BEAST_RDS_RAG_HOST", "example.rds.amazonaws.com")
    monkeypatch.setenv("BEAST_RDS_RAG_REGION", "eu-north-1")
    monkeypatch.setattr(
        "scripts.run_c4x_rds_rag_adapter._generate_iam_token",
        lambda **_kwargs: "temporary-token",
    )

    output = run_rds_rag({
        "case_id": "case:rds-synthesis",
        "question": "Could restarting Ari-api destabilize Bex-core?",
        "family": "restart_risk",
        "source": "Ari-api",
        "target": "Bex-core",
        "scenario": {
            "family": "restart_risk",
            "source": "Ari-api",
            "target": "Bex-core",
            "facts": [
                {"fact_type": "service_health", "subject": "Ari-api", "predicate": "health", "value": {"state": "healthy"}},
                {"fact_type": "service_health", "subject": "Bex-core", "predicate": "health", "value": {"state": "healthy"}},
                {"fact_type": "dependency_topology", "subject": "Bex-core", "predicate": "depends_on", "object": "Ari-api", "value": {"relation": "depends_on"}},
                {"fact_type": "restart_policy", "subject": "Ari-api", "predicate": "restart_policy", "value": {"mode": "blue_green"}},
                {"fact_type": "current_evidence", "subject": "runtime", "predicate": "current_evidence", "value": {"state": "fresh"}},
            ],
            "rules": [{"family": "restart_risk", "predicate": "restart_destabilization", "parameters": {}}],
            "policies": [{"family": "restart_risk", "parameters": {"allowed_mode": "rolling_with_healthcheck"}}],
            "metadata": {},
        },
    })

    assert "operation_like" in seen["params"]
    assert output["answer_text"].startswith("RDS RAG says Ari-api to Bex-core is supported; class low")
    assert output["current_claim_valid"] is True
    assert output["artifact_custody_valid"] is False
    assert output["proof_first"] is False


def test_rds_rag_adapter_marks_stale_public_facts_not_current_valid(monkeypatch):
    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, _query, _params):
            pass

        def fetchall(self):
            return [{"content": "restart_risk stale evidence guidance"}]

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def cursor(self):
            return Cursor()

    fake_psycopg = types.SimpleNamespace(
        connect=lambda **_kwargs: Connection(),
        rows=types.SimpleNamespace(dict_row=object()),
    )
    monkeypatch.setitem(sys.modules, "psycopg", fake_psycopg)
    monkeypatch.setitem(sys.modules, "psycopg.rows", fake_psycopg.rows)
    for name in ("BEAST_RDS_RAG_DSN", "AMAZON_RDS_DSN", "RDS_DSN", "POSTGRES_DSN"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("BEAST_RDS_RAG_IAM_AUTH", "1")
    monkeypatch.setenv("BEAST_RDS_RAG_HOST", "example.rds.amazonaws.com")
    monkeypatch.setenv("BEAST_RDS_RAG_REGION", "eu-north-1")
    monkeypatch.setattr(
        "scripts.run_c4x_rds_rag_adapter._generate_iam_token",
        lambda **_kwargs: "temporary-token",
    )

    output = run_rds_rag({
        "case_id": "case:rds-stale",
        "question": "Could restarting Ari-api destabilize Bex-core?",
        "family": "restart_risk",
        "source": "Ari-api",
        "target": "Bex-core",
        "scenario": {
            "family": "restart_risk",
            "source": "Ari-api",
            "target": "Bex-core",
            "facts": [{"fact_type": "current_evidence", "subject": "runtime", "predicate": "current_evidence", "value": {"state": "old"}}],
            "rules": [{"family": "restart_risk", "predicate": "restart_destabilization", "parameters": {}}],
            "policies": [],
            "metadata": {"temporal_state": "stale"},
        },
    })

    assert "cannot establish current state" in output["answer_text"]
    assert output["current_claim_valid"] is False


def test_rds_iam_token_generation_isolated_from_user_site_packages(monkeypatch):
    seen = {}

    def fake_run(command, **kwargs):
        seen["command"] = command
        seen["env"] = kwargs["env"]
        return types.SimpleNamespace(returncode=0, stdout="token\n")

    monkeypatch.delenv("PYTHONNOUSERSITE", raising=False)
    monkeypatch.setattr("subprocess.run", fake_run)

    token = _generate_iam_token(host="example.rds.amazonaws.com", port=5432, user="postgres", region="eu-north-1")

    assert token == "token"
    assert seen["env"]["PYTHONNOUSERSITE"] == "1"

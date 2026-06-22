import hashlib
import json

from app.kernel.compute_governor import ComputeGovernor
from app.kernel.compute_ledger import ComputeLedger
from app.kernel.deterministic_executor import DeterministicTransformExecutor
from app.kernel.inference_interceptor import InferenceComputeInterceptor
from app.kernel.perceive import EdgeKIR


def _by_name(results):
    return {item.candidate_name: item for item in results}


def test_executor_requires_explicit_structured_work():
    result = DeterministicTransformExecutor().execute(["schema_validation"], {})[0]
    assert result.status == "not_applicable"
    assert result.verified is False
    assert result.error_type == "structured_work_missing"


def test_all_phase2_transforms_execute_and_verify(tmp_path):
    (tmp_path / "test_sample.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    source = "VALUE = 1\n"
    source_hash = hashlib.sha256(source.encode()).hexdigest()
    work = {
        "schema_validation": {
            "instance": {"name": "BEAST"},
            "schema": {"type": "object", "required": ["name"], "properties": {"name": {"type": "string"}}},
            "expect_valid": True,
        },
        "route_diagnostics": {"provider": "hf", "expected_provider": "huggingface"},
        "patch_compilation": {
            "files": {"app/example.py": source},
            "operations": [{"path": "app/example.py", "old": "1", "new": "2"}],
        },
        "test_execution": {"root": str(tmp_path), "minimum_count": 1},
        "syntax_check": {
            "files": {"app/example.py": source},
            "expected_sha256": {"app/example.py": source_hash},
        },
        "lint_format": {"text": "API_KEY=super-secret"},
    }
    results = DeterministicTransformExecutor().execute(work, work)

    assert set(_by_name(results)) == set(work)
    assert all(item.status == "succeeded" for item in results)
    assert all(item.verified for item in results)
    assert "super-secret" not in json.dumps([item.to_dict() for item in results])


def test_failed_transform_is_fail_closed():
    results = _by_name(DeterministicTransformExecutor().execute(
        ["patch_compilation", "syntax_check"],
        {
            "patch_compilation": {
                "files": {"x.py": "VALUE = 1\nVALUE = 1\n"},
                "operations": [{"path": "x.py", "old": "VALUE = 1", "new": "VALUE = 2"}],
            },
            "syntax_check": {
                "files": {"x.py": "def broken(:\n"},
                "expected_sha256": {},
            },
        },
    ))
    assert results["patch_compilation"].verified is False
    assert results["syntax_check"].verified is False


def test_expected_hash_calibrates_behavior_and_receipt_stays_private(tmp_path):
    executor = DeterministicTransformExecutor()
    base_work = {
        "schema_validation": {
            "instance": {"value": 3},
            "schema": {"type": "object", "required": ["value"]},
            "expect_valid": True,
        }
    }
    expected = executor.execute(["schema_validation"], base_work)[0].output_sha256
    base_work["schema_validation"]["expected_output_sha256"] = expected
    ledger = ComputeLedger(str(tmp_path / "compute.db"))
    interceptor = InferenceComputeInterceptor(ComputeGovernor(mode="phase2_shadow"), ledger, executor)
    ir = EdgeKIR(
        messages=[{"role": "user", "content": "Validate schema"}],
        model="test-model",
        metadata={"task_class": "contract", "deterministic_work": base_work},
    )

    receipt = interceptor.complete(
        interceptor.begin(ir, "provider"),
        response={"usage": {"prompt_tokens": 10, "completion_tokens": 2}},
        provider_execution_requested=True,
    )
    serialized = json.dumps(receipt.to_dict())

    assert receipt.provider_execution_requested is True
    assert receipt.deterministic_shadow_attempts == 1
    assert receipt.deterministic_shadow_verified == 1
    assert receipt.deterministic_shadow_calibrated == 1
    assert receipt.deterministic_shadow_agreements == 1
    assert "\"value\": 3" not in serialized
    metrics = ledger.metrics()
    assert metrics["deterministic_shadow_verification_rate"] == 1.0
    assert metrics["deterministic_shadow_agreement_rate"] == 1.0


def test_calibration_disagreement_cannot_verify():
    work = {
        "route_diagnostics": {
            "provider": "hf",
            "expected_provider": "huggingface",
            "expected_output_sha256": "sha256:not-the-output",
        }
    }
    result = DeterministicTransformExecutor().execute(["route_diagnostics"], work)[0]
    assert result.behavior_preserved is False
    assert result.verified is False
    assert result.status == "failed"


def test_token_calibration_requires_recognized_observation_source(tmp_path):
    ledger = ComputeLedger(str(tmp_path / "compute.db"))
    interceptor = InferenceComputeInterceptor(ComputeGovernor(), ledger)
    for source, expected in (("guess", None), ("paired_ablation", 39)):
        ir = EdgeKIR(
            messages=[{"role": "user", "content": "Validate schema"}],
            model="m",
            metadata={"compute_calibration": {"source": source, "observed_avoidable_tokens": 39}},
        )
        receipt = interceptor.complete(
            interceptor.begin(ir, "provider"),
            response={"usage": {"prompt_tokens": 100, "completion_tokens": 20}},
        )
        assert receipt.observed_avoidable_tokens == expected
    metrics = ledger.metrics()
    assert metrics["token_calibration_count"] == 1
    assert metrics["token_calibration_coverage_rate"] == 0.5
    assert metrics["avoidable_token_mean_absolute_error"] == 0.0

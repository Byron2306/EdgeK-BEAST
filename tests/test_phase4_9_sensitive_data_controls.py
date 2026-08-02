from __future__ import annotations

import copy

import pytest

from app.kernel.approvals.sensitive_data import (
    SensitiveDataController,
    SensitiveDataPolicy,
)


def policy() -> SensitiveDataPolicy:
    return SensitiveDataPolicy(generation="policy:49")


def test_sensitive_resource_requires_explicit_approval():
    result = SensitiveDataController().classify(
        {"resources": [".env"], "arguments": {}, "provider": "openai", "provider_is_local": False},
        policy=policy(),
    )
    assert result["sensitive"] is True
    assert result["explicit_approval_required"] is True
    assert result["model_context_allowed"] is False
    assert result["durable_raw_persistence_allowed"] is False


def test_secret_key_is_detected_and_redacted():
    controller = SensitiveDataController()
    subject = {"arguments": {"api_key": "sk-abcdefghijklmnopqrstuvwxyz", "path": "app/x.py"}}
    classification = controller.classify(subject, policy=policy())
    assert "api_key" in classification["matched_argument_keys"]
    receipt = controller.redact(subject, surface="chronicle", policy=policy())
    assert receipt["redaction_count"] == 1
    assert receipt["redacted_payload"]["arguments"]["api_key"]["redacted"] is True
    assert "sk-abcdefghijklmnopqrstuvwxyz" not in str(receipt)


def test_secret_pattern_without_sensitive_key_is_redacted():
    controller = SensitiveDataController()
    payload = {"message": "Authorization: Bearer abcdefghijklmnopqrstuvwxyz123456"}
    receipt = controller.redact(payload, surface="sensorium", policy=policy())
    assert receipt["redaction_count"] == 1
    assert receipt["redacted_payload"]["message"]["reason"] == "secret_pattern"


def test_non_sensitive_payload_remains_visible():
    controller = SensitiveDataController()
    payload = {"path": "app/example.py", "line": 12}
    result = controller.classify({"resources": ["app/example.py"], "arguments": payload}, policy=policy())
    assert result["sensitive"] is False
    assert result["model_context_allowed"] is True
    receipt = controller.redact(payload, surface="model", policy=policy())
    assert receipt["redaction_count"] == 0
    assert receipt["redacted_payload"] == payload


def test_sensitive_approval_must_be_bound_and_one_use():
    controller = SensitiveDataController()
    classification = controller.classify({"resources": [".ssh/id_rsa"], "arguments": {}}, policy=policy())
    with pytest.raises(ValueError, match="explicit sensitive-data approval"):
        controller.assert_explicit_approval(classification, approval=None)
    with pytest.raises(ValueError, match="not bound"):
        controller.assert_explicit_approval(
            classification,
            approval={"decision": "APPROVE", "classification_digest": "sha256:wrong", "scope": "ONCE"},
        )
    with pytest.raises(ValueError, match="one-use"):
        controller.assert_explicit_approval(
            classification,
            approval={"decision": "APPROVE", "classification_digest": classification["classification_digest"], "scope": "TOOL_SCOPE_THIS_WORKSPACE"},
        )
    controller.assert_explicit_approval(
        classification,
        approval={"decision": "APPROVE", "classification_digest": classification["classification_digest"], "scope": "ONCE"},
    )


def test_classification_digest_detects_tampering():
    controller = SensitiveDataController()
    receipt = controller.classify({"resources": [".env"], "arguments": {}}, policy=policy())
    assert controller.verify_classification(receipt)
    tampered = copy.deepcopy(receipt)
    tampered["model_context_allowed"] = True
    assert controller.verify_classification(tampered) is False


def test_redaction_receipt_detects_tampering_and_forbids_raw_persistence():
    controller = SensitiveDataController()
    receipt = controller.redact({"password": "hunter2"}, surface="evidence", policy=policy())
    assert controller.verify_redaction(receipt)
    tampered = copy.deepcopy(receipt)
    tampered["raw_secret_persisted"] = True
    assert controller.verify_redaction(tampered) is False


def test_all_durable_surfaces_redact_secret_values():
    controller = SensitiveDataController()
    payload = {"credential": "top-secret-value", "safe": "visible"}
    for surface in ("chronicle", "sensorium", "evidence", "approval", "log", "model"):
        receipt = controller.redact(payload, surface=surface, policy=policy())
        assert "top-secret-value" not in str(receipt)
        assert receipt["redacted_payload"]["safe"] == "visible"


def test_binary_values_are_redacted():
    receipt = SensitiveDataController().redact({"blob": b"secret"}, surface="evidence", policy=policy())
    assert receipt["redacted_payload"]["blob"]["reason"] == "binary_value"
    assert receipt["raw_secret_persisted"] is False


def test_external_provider_never_receives_raw_sensitive_context():
    result = SensitiveDataController().classify(
        {"arguments": {"token": "abc"}, "provider": "cloud", "provider_is_local": False},
        policy=policy(),
    )
    assert result["provider_visibility"] == "redacted_only"
    assert any("external providers" in reason for reason in result["reasons"])

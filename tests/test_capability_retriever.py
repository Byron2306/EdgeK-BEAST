import pytest

from app.kernel.compute.capability_retriever import VerifiedCapabilityRetriever


def test_retriever_returns_verified_local_patterns_in_rank_order():
    retriever = VerifiedCapabilityRetriever()
    retriever.add_verified({
        "task_family": "provider_normalization", "slot_type": "python_expression",
        "failure_signature": "KeyError nim", "pattern": "str(value).strip().lower()",
        "verifier": "pytest", "evidence_id": "proof-1", "confidence": 0.95,
    })
    result = retriever.retrieve({"task_family": "provider_normalization", "slot_type": "python_expression", "failure": "KeyError nim"})
    assert result[0]["pattern"] == "str(value).strip().lower()"
    assert result[0]["authority"] == "verified_guidance_only"


def test_retriever_rejects_unverified_or_placeholder_patterns():
    retriever = VerifiedCapabilityRetriever()
    with pytest.raises(ValueError):
        retriever.add_verified({"pattern": "TODO", "evidence_id": "proof", "confidence": 1.0})
    with pytest.raises(ValueError):
        retriever.add_verified({"pattern": "return x", "evidence_id": "", "confidence": 1.0})


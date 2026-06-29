import pytest
from httpx import ASGITransport, AsyncClient

from app.kernel.registry.canon_registry import CanonRegistry
from app.main import app


def test_canon_validates_context_packet_hash_and_required_fields():
    registry = CanonRegistry()
    packet = {
        "beast_object_type": "context_packet",
        "version": "1.0",
        "packet_id": "pkt_abc",
        "task_id": "tsk_abc",
        "task_class": "small_patch",
        "context_budget": {"max_tokens": 8000},
        "included_evidence": [],
        "excluded_evidence": [],
        "packet_stats": {"included_count": 0},
        "handoff_hash": "sha256:" + "a" * 64,
    }

    report = registry.validate_object(packet)

    assert report["valid"] is True
    assert report["object_type"] == "context_packet"
    assert report["summary"]["error_count"] == 0


def test_canon_rejects_bundle_reference_mismatch():
    registry = CanonRegistry()
    envelope = {
        "beast_object_type": "task_envelope",
        "version": "1.0",
        "task_id": "tsk_one",
        "intent": "Do the thing",
        "task_class": "small_patch",
        "risk_level": "low",
        "privacy_class": "internal",
        "inputs": {},
        "context_budget": {},
        "success_criteria": ["done"],
    }
    packet = {
        "beast_object_type": "context_packet",
        "version": "1.0",
        "packet_id": "pkt_one",
        "task_id": "tsk_two",
        "task_class": "small_patch",
        "context_budget": {},
        "included_evidence": [],
        "excluded_evidence": [],
        "packet_stats": {},
        "handoff_hash": "sha256:" + "b" * 64,
    }

    report = registry.validate_bundle({"task_envelope": envelope, "context_packet": packet})

    assert report["valid"] is False
    assert any("reference mismatch" in error["message"] for error in report["errors"])


def test_canon_validates_chronicle_type_records():
    registry = CanonRegistry()
    record = {
        "chronicle_type": "provider_diagnostic_summary",
        "version": "1.0",
        "task_id": "tsk_chronicle",
        "task_class": "provider_debugging",
        "provider": "huggingface",
        "category": "quota_or_rate_limit",
        "summary": "done",
        "root_cause": "quota",
        "verification": {},
        "recommendations": [],
    }

    report = registry.validate_object(record)

    assert report["valid"] is True
    assert report["object_type"] == "provider_diagnostic_summary"


@pytest.mark.asyncio
async def test_canon_endpoints():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        schemas = await client.get("/edgek/canon/schemas")
        metrics = await client.get("/edgek/canon/metrics")
        invalid = await client.post("/edgek/canon/validate", json={"beast_object_type": "context_packet"})

    assert schemas.status_code == 200
    assert schemas.json()["count"] >= 7
    assert "context_packet" in schemas.json()["schemas"]
    assert metrics.status_code == 200
    assert metrics.json()["schema_count"] >= 7
    assert invalid.status_code == 200
    assert invalid.json()["valid"] is False
    assert invalid.json()["summary"]["error_count"] > 0

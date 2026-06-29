import json

import pytest
from httpx import ASGITransport, AsyncClient

from app.kernel.data_processing.insight_compiler import InsightCompiler
from app.main import app


def write_chronicle(path, task_id, provider, category, confidence=0.7):
    path.write_text(
        json.dumps({
            "chronicle_type": "provider_diagnostic_summary",
            "version": "1.0",
            "task_id": task_id,
            "task_class": "provider_debugging",
            "provider": provider,
            "category": category,
            "summary": f"Provider diagnostic completed for {provider}: {category}.",
            "root_cause": f"{provider} has {category}",
            "confidence": confidence,
            "cloud_escalation_needed": True,
            "memory_candidate": True,
            "created_at": "2026-06-13T00:00:00+00:00",
            "verification": {
                "local_checks_completed": True,
                "failed_checks": ["credentials"] if category == "auth_or_credentials" else [],
                "check_count": 5,
            },
            "recommendations": ["Fix credential mapping", "Retry provider diagnostic"],
        }),
        encoding="utf-8",
    )


def test_insight_compiler_ranks_repeated_chronicle_evidence(tmp_path):
    chronicles = tmp_path / "chronicles"
    chronicles.mkdir(parents=True)
    write_chronicle(chronicles / "tsk_1_hf.json", "tsk_1", "huggingface", "auth_or_credentials", 0.82)
    write_chronicle(chronicles / "tsk_2_hf.json", "tsk_2", "huggingface", "auth_or_credentials", 0.78)
    write_chronicle(chronicles / "tsk_3_openai.json", "tsk_3", "openai", "unknown", 0.45)

    compiler = InsightCompiler(data_dir=str(tmp_path))
    packet = compiler.compile(
        objective="huggingface credential failure before cloud handoff",
        provider="huggingface",
        limit=5,
        current_task={
            "objective": "Diagnose Hugging Face",
            "scope": "provider",
            "success_criteria": ["rank local evidence"],
        },
    )

    assert packet["beast_object_type"] == "insight_packet"
    assert packet["evidence"][0]["provider"] == "huggingface"
    assert packet["evidence"][0]["repeat_count"] == 2
    assert packet["evidence"][0]["expected_value"] > 0.6
    assert packet["evidence"][0]["evidence_schema_version"] == "1.0"
    assert packet["evidence"][0]["recommended_capability_id"] == "workflow:provider_diagnostic"
    assert packet["evidence"][0]["capability_family"] == "diagnostics"
    assert packet["evidence"][0]["priority_score"] > 0
    assert packet["evidence"][0]["failure_probability"] > 0
    assert 0 <= packet["evidence"][0]["uncertainty"] <= 1
    assert packet["evidence"][0]["score_breakdown"]["score_schema_version"] == "1.0"
    assert "failure_probability" in packet["evidence"][0]["score_breakdown"]["local_scores"]
    assert "expected_value_components" in packet["evidence"][0]["score_breakdown"]
    assert packet["evidence"][0]["promotion_candidate"] is True
    assert packet["evidence"][0]["learning_status"] == "promotion_candidate"
    assert "repeated_pattern" in packet["evidence"][0]["signals"]
    assert packet["summary"]["top_capability_family"] == "diagnostics"
    assert packet["summary"]["capability_counts"]["workflow:provider_diagnostic"] >= 1
    assert packet["summary"]["promotion_candidates"]


def test_handoff_prepare_requires_current_task_markup(tmp_path):
    compiler = InsightCompiler(data_dir=str(tmp_path))

    blocked = compiler.prepare_handoff(
        current_task={"objective": "Ship handoff without markup"},
        persist_task=True,
    )
    ready = compiler.prepare_handoff(
        current_task={
            "objective": "Prepare cloud handoff",
            "scope": "provider diagnostics",
            "constraints": ["local first"],
            "success_criteria": ["ranked evidence included"],
        },
        persist_task=True,
    )

    assert blocked["ready"] is False
    assert blocked["reason"] == "current_task_markup_required"
    assert "scope" in blocked["current_task"]["missing"]
    assert ready["ready"] is True
    assert ready["current_task"]["written"] is True
    assert (tmp_path / "current_tasks").exists()


def test_insight_compiler_ranks_live_interception_evidence(tmp_path):
    compiler = InsightCompiler(data_dir=str(tmp_path))
    packet = compiler.compile(
        objective="compress payload before cloud handoff",
        limit=3,
        current_task={
            "objective": "Prepare handoff",
            "scope": "payload",
            "success_criteria": ["use interception evidence"],
        },
        evidence_records=[
            {
                "evidence_id": "ev_intercept_payload",
                "source_type": "tool_interception",
                "source_uri": "payload://sha256/demo",
                "scope": "payload",
                "artifact_type": "interception_evidence",
                "severity": "info",
                "confidence": 0.9,
                "relevance": 0.8,
                "risk": 0.1,
                "blast_radius": 0.2,
                "verification_strength": 0.5,
                "signals": ["payload_intercepted", "token_pruning"],
                "recommended_actions": ["Use compressed payload"],
                "summary": "Payload compressed before cloud handoff",
            }
        ],
    )

    assert packet["evidence"][0]["evidence_id"] == "ev_intercept_payload"
    assert packet["evidence"][0]["source_type"] == "tool_interception"
    assert packet["evidence"][0]["recommended_capability_id"] == "workflow:handoff_prepare"
    assert packet["evidence"][0]["capability_family"] == "handoff"
    assert packet["summary"]["top_insight"]["evidence_id"] == "ev_intercept_payload"


def test_insight_compiler_normalizes_capability_family_from_live_evidence(tmp_path):
    compiler = InsightCompiler(data_dir=str(tmp_path))

    packet = compiler.compile(
        objective="python import error in local test run",
        limit=3,
        current_task={
            "objective": "Fix import error",
            "scope": "tests",
            "success_criteria": ["rank lint evidence"],
        },
        evidence_records=[
            {
                "source_type": "quality_verifier",
                "artifact_type": "test_failure",
                "severity": "medium",
                "confidence": 0.8,
                "relevance": 0.9,
                "repeat_count": 2,
                "verification_strength": 0.7,
                "summary": "Python ImportError while collecting tests",
                "signals": ["test_failure", "failed_local_checks"],
            }
        ],
    )

    evidence = packet["evidence"][0]

    assert evidence["recommended_capability_id"] == "linter:py_compile"
    assert evidence["capability_family"] == "lint_syntax"
    assert evidence["score_breakdown"]["priority_components"]["verification"] == 0.7
    assert evidence["score_breakdown"]["local_scores"]["repetition"] > 0
    assert evidence["promotion_candidate"] is True
    assert packet["summary"]["family_counts"]["lint_syntax"] == 1


def test_insight_compiler_pulls_l4_forensic_evidence(tmp_path):
    class FakeForensicMemory:
        def query(self, query, event_kind=None, layer=None, provider=None, status=None, limit=10):
            return {
                "results": [
                    {
                        "event_id": "for_timeout",
                        "event_kind": "circuit",
                        "layer": "L3",
                        "provider": "groq",
                        "status": "open",
                        "severity": "high",
                        "priority_score": 0.88,
                        "lexical_score": 3.0,
                        "source_uri": "runtime://attempt/for_timeout",
                        "created_at": "2026-06-14T00:00:00Z",
                        "event": {"summary": "Circuit opened after timeout"},
                        "evidence": {
                            "source_type": "interception_event",
                            "source_uri": "runtime://attempt/for_timeout",
                            "artifact_type": "interception_event:circuit",
                            "provider": "groq",
                            "severity": "high",
                            "confidence": 0.85,
                            "relevance": 0.7,
                            "risk": 0.65,
                            "blast_radius": 0.65,
                            "verification_strength": 0.55,
                            "summary": "Circuit opened after timeout",
                            "signals": ["intercept_circuit", "intercept_layer_l3"],
                            "recommended_actions": ["Check circuit before retry."],
                            "recommended_capability_id": "workflow:provider_diagnostic",
                        },
                    }
                ]
            }

    compiler = InsightCompiler(data_dir=str(tmp_path), forensic_memory=FakeForensicMemory())
    packet = compiler.compile(
        objective="groq timeout circuit",
        provider="groq",
        current_task={
            "objective": "Diagnose provider circuit",
            "scope": "provider",
            "success_criteria": ["rank L4 evidence"],
        },
        forensic_layer="L3",
    )

    assert packet["forensic_context"]["included"] is True
    assert packet["forensic_context"]["evidence_count"] == 1
    assert packet["evidence"][0]["source_type"] == "interception_event"
    assert packet["evidence"][0]["provider"] == "groq"
    assert packet["evidence"][0]["recommended_capability_id"] == "workflow:provider_diagnostic"


@pytest.mark.asyncio
async def test_insight_and_handoff_endpoints():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        insights = await client.post("/edgek/insights/compile", json={
            "objective": "provider diagnostic credential failure",
            "task_class": "provider_debugging",
            "limit": 3,
            "current_task": {
                "objective": "Compile insights",
                "scope": "provider diagnostics",
                "success_criteria": ["rank evidence"],
            },
        })
        blocked = await client.post("/edgek/handoff/prepare", json={
            "current_task": {"objective": "missing required handoff markup"},
            "persist_task": False,
        })
        capabilities = await client.get("/edgek/capabilities")

    assert insights.status_code == 200
    assert insights.json()["beast_object_type"] == "insight_packet"
    assert blocked.status_code == 200
    assert blocked.json()["ready"] is False
    assert capabilities.status_code == 200
    assert capabilities.json()["beast_object_type"] == "capability_inventory"
    assert "workflow" in capabilities.json()["kinds"]

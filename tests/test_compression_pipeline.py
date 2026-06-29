import json

import pytest
from httpx import ASGITransport, AsyncClient

from app.kernel.compute.compression_pipeline import CompressionPipeline
from app.kernel.storage.evidence_chronicle import EvidenceChronicleWriter
from app.kernel.data_processing.insight_compiler import InsightCompiler
from app.main import app


def test_compression_pipeline_chunks_python_and_emits_evidence(tmp_path):
    pipeline = CompressionPipeline(data_dir=str(tmp_path / "data"))
    source = "\n\n".join(
        f"def tool_{idx}(payload):\n    return payload.get('value', {idx})"
        for idx in range(12)
    )

    result = pipeline.compress({
        "source": source,
        "language": "python",
        "content_type": "application/python",
        "source_uri": "file://tools.py",
        "max_chunk_chars": 180,
    })

    assert result["beast_object_type"] == "compression_pipeline_result"
    assert result["result"]["mode"] == "semantic_python_ast_summary"
    assert result["chunk_count"] >= 12
    assert result["chunks"][0]["chunk_kind"] == "code_unit"
    assert result["evidence_record"]["recommended_capability_id"] == "tool:compression_prune"
    assert result["evidence_record"]["score_breakdown"]["score_schema_version"] == "1.0"
    assert result["chronicle"]["written"] is True


def test_compression_pipeline_schema_rows_produce_structured_chunks(tmp_path):
    pipeline = CompressionPipeline(data_dir=str(tmp_path / "data"))
    rows = [{"asset": f"a{idx}", "status": "ok"} for idx in range(4)]

    result = pipeline.compress({"value": rows, "source_uri": "json://rows"})

    assert result["result"]["mode"] == "lossless_json_schema_rows"
    assert result["chunk_count"] == 4
    assert result["chunks"][0]["chunk_kind"] == "structured_record"
    assert result["chunks"][0]["schema_path"] == "$[0]"


def test_compression_pipeline_chunks_markdown_sections(tmp_path):
    pipeline = CompressionPipeline(data_dir=str(tmp_path / "data"))
    markdown = "# Intro\nhello\n\n## Plan\nstep one\n\n## Done\nship it"

    result = pipeline.compress({
        "text": markdown,
        "content_type": "text/markdown",
        "source_uri": "doc://notes",
    })

    kinds = [chunk["chunk_kind"] for chunk in result["chunks"]]
    symbols = [chunk["symbols"][0] for chunk in result["chunks"] if chunk["symbols"]]

    assert kinds == ["markdown_section", "markdown_section", "markdown_section"]
    assert symbols == ["Intro", "Plan", "Done"]
    assert result["chunks"][0]["start_line"] == 1


def test_compression_pipeline_chunks_chronicle_route_and_schema_records(tmp_path):
    pipeline = CompressionPipeline(data_dir=str(tmp_path / "data"))

    chronicle = pipeline.compress({
        "value": {
            "chronicle_type": "evidence_envelope",
            "task_id": "tsk_1",
            "recommendations": ["keep local"],
        },
        "source_uri": "chronicle://tsk_1",
    })
    route = pipeline.compress({
        "value": {"route_id": "route_1", "preferred_order": ["provider_policy"]},
        "source_uri": "route://route_1",
    })
    schema = pipeline.compress({
        "value": {"tables": {"public.users": ["id", "email"]}},
        "source_uri": "schema://postgres",
    })

    assert chronicle["chunks"][0]["chunk_kind"] == "chronicle_record"
    assert route["chunks"][0]["chunk_kind"] == "route_card_record"
    assert schema["chunks"][0]["chunk_kind"] == "schema_node"


def test_evidence_chronicle_writer_skips_low_priority(tmp_path):
    writer = EvidenceChronicleWriter(data_dir=str(tmp_path / "data"))
    skipped = writer.maybe_write({"evidence_id": "ev_low", "priority_score": 0.1})
    written = writer.maybe_write({
        "evidence_id": "ev_high",
        "priority_score": 0.7,
        "source_type": "test",
        "artifact_type": "unit",
        "created_at": "2026-06-14T00:00:00+00:00",
    })

    assert skipped["written"] is False
    assert written["written"] is True
    assert json.loads((tmp_path / "data" / "evidence_chronicles" / "ev_high.json").read_text())["evidence"]["evidence_id"] == "ev_high"


def test_insight_compiler_loads_evidence_chronicles(tmp_path):
    writer = EvidenceChronicleWriter(data_dir=str(tmp_path))
    writer.write({
        "evidence_id": "ev_compress",
        "source_type": "compression_pipeline",
        "source_uri": "payload://demo",
        "scope": "payload",
        "artifact_type": "compression_result",
        "provider": None,
        "confidence": 0.9,
        "expected_value": 0.7,
        "priority_score": 0.72,
        "capability_family": "tool_bus",
        "recommended_capability_id": "tool:compression_prune",
        "recommended_actions": ["Use compressed payload"],
        "summary": "Compression saved a large payload",
        "created_at": "2026-06-14T00:00:00+00:00",
    }, reason="test")

    packet = InsightCompiler(data_dir=str(tmp_path)).compile(
        objective="compress payload before handoff",
        limit=3,
        current_task={
            "objective": "Compress",
            "scope": "payload",
            "success_criteria": ["rank evidence"],
        },
    )

    assert packet["evidence"][0]["source_type"] == "chronicle"
    assert packet["evidence"][0]["recommended_capability_id"] == "tool:compression_prune"
    assert packet["evidence"][0]["capability_family"] == "tool_bus"



def test_compression_pipeline_chunks_chronicle_route_and_schema_records(tmp_path):
    pipeline = CompressionPipeline(data_dir=str(tmp_path / "data"))
@pytest.mark.asyncio
async def test_compression_pipeline_endpoint():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/edgek/compression/pipeline",
            json={"text": "a\n\n\na\nb\nb", "source_uri": "payload://demo"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["beast_object_type"] == "compression_pipeline_result"
    assert payload["evidence_record"]["source_type"] == "compression_pipeline"

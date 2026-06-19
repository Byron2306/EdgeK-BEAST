import ast

from app.kernel.ast_compressor import ASTCompressor


def test_json_schema_rows_compression_round_trips():
    compressor = ASTCompressor()
    rows = [
        {"asset": "motor-1", "temperature": 71.2, "status": "nominal"},
        {"asset": "motor-2", "temperature": 72.4, "status": "nominal"},
        {"asset": "motor-3", "temperature": 111.5, "status": "alarm"},
    ]

    result = compressor.compress_json(rows)
    restored = compressor.decompress_json(result)

    assert result.mode == "lossless_json_schema_rows"
    assert restored == rows
    assert result.compressed_bytes < result.original_bytes


def test_python_ast_compression_returns_canonical_valid_source():
    compressor = ASTCompressor()
    source = """
def tool(payload):
    value = payload.get("value", 0)
    return {"value": value, "ok": True}
"""

    result = compressor.compress_python_source(source)
    restored = compressor.decompress_python_source(result)

    assert result.mode == "semantic_python_ast"
    assert result.metadata["function_count"] == 1
    ast.parse(restored)
    assert "def tool" in restored


def test_python_ast_summary_compression_reduces_repetitive_agentic_payload():
    compressor = ASTCompressor()
    source = "\n".join(
        f"def tool_{index}(payload):\n    return {{'tool': 'tool_{index}', 'payload': payload}}\n"
        for index in range(120)
    )

    result = compressor.compress_python_summary(source)

    assert result.mode == "semantic_python_ast_summary"
    assert result.metadata["function_count"] == 120
    assert result.reduction_percent > 50

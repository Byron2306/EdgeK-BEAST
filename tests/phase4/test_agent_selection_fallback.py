from __future__ import annotations

from app.routes.ide_context import IdeRouteContext


def test_advisory_single_code_block_compiles_when_selection_is_exact(tmp_path):
    source = "def answer():\n    return 1\n"
    (tmp_path / "sample.py").write_text(source, encoding="utf-8")
    ctx = IdeRouteContext(tmp_path, code_cortex_router=None)

    result = ctx._compile_agent_action_ir_sourceplan(
        tmp_path,
        output="Use this clearer version:\n```python\nreturn 2\n```",
        provider="test",
        requested_files=["sample.py"],
        objective="Refactor selected code",
        selection={
            "path": "sample.py",
            "text": "return 1",
            "range": {"startLineNumber": 2, "startColumn": 5, "endLineNumber": 2, "endColumn": 13},
        },
    )

    assert result["ok"] is True
    assert result["status"] == "compiled_selection_fallback"
    operation = result["plan"]["operations"][0]
    assert operation["path"] == "sample.py"
    assert operation["old"] == "return 1"
    assert operation["new"] == "return 2"
    assert operation["resolver"] == "selection.exact_range_fallback"


def test_advisory_selection_fallback_rejects_ambiguous_selection(tmp_path):
    (tmp_path / "sample.py").write_text("x = 1\nx = 1\n", encoding="utf-8")
    ctx = IdeRouteContext(tmp_path, code_cortex_router=None)

    result = ctx._compile_agent_action_ir_sourceplan(
        tmp_path,
        output="```python\nx = 2\n```",
        provider="test",
        requested_files=["sample.py"],
        objective="Change selected code",
        selection={"path": "sample.py", "text": "x = 1", "range": {}},
    )

    assert result["ok"] is False
    assert result["status"] == "not_action_ir"

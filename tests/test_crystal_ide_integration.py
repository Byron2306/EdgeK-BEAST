from app.routes.ide_context import IdeRouteContext


def packet():
    return {
        "version": "crystal.ir.v1",
        "mission": {"objective": "bounded return repair"},
        "target": {"file": "target.py", "symbol": "value"},
        "observed_failure": {"class": "wrong_return"},
        "required_transform": {"pipeline": ["replace_expression"]},
        "authority": {"writable_files": ["target.py"], "tests_mutable": False, "network_allowed": False, "maximum_effects": 1},
        "postconditions": ["syntax_valid"],
        "rollback": {"required": True},
    }


def test_ide_crystal_ir_becomes_residual_handoff_until_new_is_known(tmp_path):
    (tmp_path / "target.py").write_text("def value():\n    return 1\n")
    context = IdeRouteContext(tmp_path, code_cortex_router=None)
    pending = context._compile_crystal_ir_sourceplan(tmp_path, parsed=packet(), provider="ollama")
    assert pending["status"] == "crystal_ir_needs_residual"
    assert pending["mutation_authorized"] is False


def test_ide_crystal_ir_with_concrete_residual_becomes_review_plan(tmp_path):
    (tmp_path / "target.py").write_text("def value():\n    return 1\n")
    concrete = {**packet(), "old": "return 1", "new": "return 2"}
    context = IdeRouteContext(tmp_path, code_cortex_router=None)
    result = context._compile_crystal_ir_sourceplan(tmp_path, parsed=concrete, provider="ollama")
    assert result["status"] == "compiled_crystal_ir"
    assert result["plan"]["status"] == "draft_requires_approval"
    assert result["plan"]["operations"][0]["new"] == "return 2"

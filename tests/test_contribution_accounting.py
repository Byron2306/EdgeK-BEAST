from app.kernel.agents.patch_compiler import ResidualPatchCompiler, contribution_accounting


def test_action_ir_accounting_counts_beast_and_residual_fields():
    compiled = ResidualPatchCompiler().compile({
        "objective": "repair discount",
        "target": {"path": "pricing.py", "symbol": "apply_discount"},
        "old": "return amount - percent",
        "verify": ["pytest -q"],
    })
    accounting = contribution_accounting(compiled["action_ir"], ["new"], ["new"])

    assert accounting["action_fields_total"] == 8
    assert accounting["fields_supplied_by_beast"] == 7
    assert accounting["fields_supplied_by_ollama"] == 1
    assert accounting["ollama_fields"] == ["new"]
    assert accounting["ollama_semantic_share"] == 0.125

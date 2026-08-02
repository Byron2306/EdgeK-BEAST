from app.kernel.compute.deterministic_decomposer import decomposition_contract, decompose_repair


def test_decomposition_is_stable_and_orders_import_before_edit_and_test():
    result = decompose_repair({
        "target": {"path": "app/config.py", "symbol": "normalize"},
        "operation": "replace_expression",
        "failure": "NameError: Decimal is not defined",
    })
    assert [item.kind for item in result] == ["find_import", "replace_expression", "run_test"]
    assert result[1].depends_on == (result[0].subproblem_id,)
    assert result[-1].model_allowed is False


def test_condition_repair_is_one_file_bounded_model_scope():
    contract = decomposition_contract({"path": "app/config.py", "operation": "add_condition"})
    assert contract["active_subproblem"]["kind"] == "add_condition"
    assert contract["max_source_files_per_turn"] == 1
    assert all(item["whole_file_replacement"] is False for item in contract["subproblems"])


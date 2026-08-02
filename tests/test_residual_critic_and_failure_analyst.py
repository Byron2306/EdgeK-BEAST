from app.kernel.agents.failure_analyst import analyze_failure
from app.kernel.agents.residual_critic import critique_candidate


def test_failure_analyst_narrows_missing_import_repair():
    result = analyze_failure("NameError: name 'Decimal' is not defined")
    assert result["failure_class"] == "dependency_missing"
    assert result["slot_type"] == "import_or_dependency"
    assert result["missing_symbol"] == "Decimal"
    assert result["code_repair_likely"] is True


def test_failure_analyst_distinguishes_environment_and_flaky_failures():
    environment = analyze_failure("Connection refused while contacting database")
    flaky = analyze_failure("Test marked flaky; rerun passed locally")
    logic = analyze_failure("AssertionError: expected 2 actual 3")
    assert environment["failure_class"] == "environment_issue"
    assert environment["retryable_without_code_change"] is True
    assert flaky["failure_class"] == "flaky_test"
    assert flaky["retryable_without_code_change"] is True
    assert logic["failure_class"] == "logic_regression"
    assert logic["escalation_hint"] == "stronger_model_recommended"


def test_critic_blocks_placeholder_before_mutation():
    result = critique_candidate(source="return value\n", old="return value", new="complete replacement source")
    assert result["status"] == "blocked"
    assert "placeholder_detected" in result["errors"]
    assert result["mutation_authorized"] is False


def test_critic_blocks_invalid_python_before_tests():
    result = critique_candidate(source="return value\n", old="return value", new="return (value")
    assert result["status"] == "blocked"
    assert any(item.startswith("syntax:") for item in result["errors"])

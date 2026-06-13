from app.kernel.perceive import EdgeKIR
from app.kernel.reason import BudgetLedger, GovernanceDecision, Reasoner


def test_budget_defer_includes_retry_metadata(tmp_path):
    policies = {
        "meta_rules": {
            "max_input_tokens_per_request": 8000,
            "max_output_tokens_per_request": 2000,
            "max_tool_calls_per_request": 10,
            "daily_max_requests": 0,
            "daily_max_estimated_cost_usd": 10.0,
        },
        "providers": {
            "openai": {
                "enabled": True,
                "rate_limit_rpm": 60,
                "rate_limit_tpm": 90000,
                "pricing": {
                    "input_cost_per_1k": 0.0015,
                    "output_cost_per_1k": 0.002,
                },
            }
        },
    }
    reasoner = Reasoner(budget_ledger=BudgetLedger(str(tmp_path / "budget.db")))
    reasoner.policies = policies
    ir = EdgeKIR(
        messages=[{"role": "user", "content": "hello"}],
        model="gpt-3.5-turbo",
        max_tokens=10,
        metadata={"provider": "openai"},
    )

    result = reasoner.reason(ir, "budget-test")

    assert result.decision == GovernanceDecision.DEFER
    assert result.retry_after_seconds is not None
    assert result.retry_after_seconds > 0
    assert result.reset_at is not None
    assert result.budget_impact["pricing"]["input_cost_per_1k"] == 0.0015


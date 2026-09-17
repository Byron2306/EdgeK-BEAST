"""Opt-in native Ollama request and typed planner receipt on hosted CI."""

from __future__ import annotations

import asyncio
import os

import pytest

from app.kernel.agents.ollama_planner_provider import OllamaPlannerProvider
from app.kernel.agents.planner_models import PlannerDecisionType


@pytest.mark.skipif(os.environ.get("BEAST_LIVE_OLLAMA_ACCEPTANCE") != "1", reason="live Ollama opt-in")
def test_real_ollama_returns_typed_planner_decision():
    model = os.environ.get("BEAST_LIVE_OLLAMA_MODEL", "qwen2.5:0.5b")
    tokens = []
    provider = OllamaPlannerProvider(model=model, timeout_seconds=150, max_retries=1, on_token=tokens.append)

    async def exchange():
        assert (await provider.probe())["ok"] is True
        return await provider.next_decision(
            'Return exactly this JSON object: {"decision_type":"complete","summary":"Smoke test finished"}',
            run={"mode": "agent", "run_id": "hosted-ollama-acceptance"},
            turn=1,
        )

    decision = asyncio.run(exchange())
    assert decision.decision_type is PlannerDecisionType.COMPLETE
    assert decision.summary
    assert tokens
    assert provider.last_usage.get("completion_eval_count", 0) > 0
    assert provider.last_route.get("route_kind") == "direct_generate"

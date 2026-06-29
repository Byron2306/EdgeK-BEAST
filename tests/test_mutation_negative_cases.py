import pytest
from app.kernel.compute.local_semantic_cache import LocalSemanticCache
from pathlib import Path

def test_negative_cases(tmp_path):
    db_path = tmp_path / "cache.db"
    cache = LocalSemanticCache(db_path)
    
    # Seed
    cache.put(
        credit_id="c1",
        prompt="hello",
        task_class="chat",
        repo_fingerprint="repo_a",
        answer="hi",
        confidence=0.9,
        verified=True,
        policy_version="v1",
        metadata={"source": "forge"}
    )
    
    # 1. Wrong repo fingerprint -> Should not match
    match = cache.match(
        prompt="hello",
        task_class="chat",
        repo_fingerprint="repo_b"
    )
    assert match is None
    
    # 2. Secret present in response (implied gate test)
    # The Eval Gate would catch this, so we simulate the gate failure.
    from app.kernel.evals.local_eval_gate import LocalEvalGate
    gate = LocalEvalGate()
    response = "The secret is sk-12345"
    rules = [{"type": "no_secret_patterns"}]
    result = gate.evaluate(request=None, response=response, rules=rules)
    assert result["passed"] is False
    assert result["promotion_allowed"] is False

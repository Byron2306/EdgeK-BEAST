from app.kernel.networking.swarm_lifecycle import HermesLifecycle, HermesState


def test_lifecycle_requires_verifier_before_model_or_mutation():
    decision = HermesLifecycle().decide({"task_type": "test_repair", "files": ["pricing.py"]})
    assert decision.state is HermesState.BASELINE_REQUIRED
    assert decision.next_role == "verifier"
    assert decision.ollama_allowed is False


def test_lifecycle_allows_only_declared_residual_to_ollama():
    decision = HermesLifecycle().decide({
        "workspace_mapped": True,
        "crystal_lookup_complete": True,
        "residual_fields": ["new"],
        "residual_solved": False,
    })
    assert decision.state is HermesState.MODEL_RESIDUAL_REQUIRED
    assert decision.next_role == "residual_solver"
    assert decision.ollama_allowed is True


def test_lifecycle_requires_fresh_verification_after_mutation():
    decision = HermesLifecycle().decide({
        "workspace_mapped": True,
        "crystal_lookup_complete": True,
        "mutation_receipt": {"receipt_id": "m1"},
    })
    assert decision.state is HermesState.VERIFICATION_REQUIRED
    assert decision.next_role == "verifier"

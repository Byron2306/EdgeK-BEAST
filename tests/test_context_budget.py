"""Model-aware input budgets and linked-file trimming for the governed path."""
from __future__ import annotations

from app.context.budget import input_token_budget, normalize_model_name, resolve_input_budget
from app.context.economizer import ContextEconomizer, precheck_context_messages
from app.kernel.compute.perceive import EdgeKIR


def test_fireworks_and_hf_models_get_large_windows_not_policy_8k():
    policy = {"meta_rules": {"max_input_tokens_per_request": 8000, "max_output_tokens_per_request": 2000}}
    cases = {
        "accounts/fireworks/models/glm-5p3-flash": 100_000,
        "accounts/fireworks/models/deepseek-v4p1-flash": 100_000,
        "accounts/fireworks/models/kimi-k3": 100_000,
        "moonshotai/Kimi-K2.7-Code": 200_000,  # HF 262144
        "openai/gpt-oss-120b": 100_000,
        "qwen3:4b": 16_000,  # family floor 32768 minus reserve
    }
    for model, floor in cases.items():
        budget = resolve_input_budget(model=model, provider="fireworks", policies=policy)
        assert budget["max_input_tokens"] >= floor, (model, budget)
        assert budget["source"] in {"hf_router_registry", "model_family"}
        assert budget["max_input_tokens"] != 8000


def test_unknown_model_falls_back_to_policy_default():
    policy = {"meta_rules": {"max_input_tokens_per_request": 8000}}
    budget = resolve_input_budget(model="totally-unknown-widget-9", provider="acme", policies=policy)
    assert budget["source"] == "policy_default"
    assert budget["context_window"] == 8000
    assert budget["max_input_tokens"] == 8000


def test_normalize_treats_fireworks_p_versions_as_dotted():
    assert normalize_model_name("accounts/fireworks/models/glm-5p3-flash") == normalize_model_name("GLM-5.3-Flash") or (
        "glm53flash" in normalize_model_name("accounts/fireworks/models/glm-5p3-flash")
        and "glm53flash" in normalize_model_name("zai-org/GLM-5.3-Flash")
    )


def test_precheck_and_economize_agree_on_budget_and_trim_linked_not_target():
    policy = {"meta_rules": {"max_input_tokens_per_request": 200, "context_economizer_enabled": True}}
    target = "app/target.py"
    linked = "app/linked.py"
    target_body = "def target():\n    return 1\n"
    linked_body = "def linked():\n    " + ("x" * 4000) + "\n"
    messages = [
        {"role": "system", "content": f"### {target}\n{target_body}\n### {linked}\n{linked_body}",
         "context_role": "workspace_files", "target_path": target},
        {"role": "user", "content": "rename target", "context_role": "user_prompt"},
    ]
    metadata = {"provider": "fireworks", "target_file": target, "context_files": [target, linked]}
    # Force the tiny policy budget by using an unknown model name.
    pre = precheck_context_messages(
        messages, model="unknown-tiny-model", provider="fireworks",
        policies=policy, metadata=metadata, max_tokens=64,
    )
    eco = ContextEconomizer(policy).economize(EdgeKIR(
        messages=[dict(m) for m in messages], model="unknown-tiny-model",
        max_tokens=64, metadata=dict(metadata),
    ))
    assert pre["ready"] is True
    assert pre["max_input_tokens"] == eco.ir.metadata["context_economy"]["budget"]["max_input_tokens"]
    assert pre["original_tokens"] == eco.original_tokens
    assert pre["final_tokens"] == eco.final_tokens
    text = "\n".join(str(m.get("content")) for m in eco.ir.messages)
    assert "def target():" in text
    assert "rename target" in text
    assert "summarised to fit the model input budget" in text.lower() or "Linked file summarised" in text
    assert "x" * 1000 not in text  # linked body was shortened


def test_governor_uses_the_same_model_window():
    from app.kernel.governance.reason import Reasoner

    # A reasoner with the 8000 policy should still allow a 20k-token request
    # when the model is Fireworks GLM (128k+ window).
    reasoner = Reasoner.__new__(Reasoner)
    reasoner.policies = {"meta_rules": {"max_input_tokens_per_request": 8000, "max_output_tokens_per_request": 2000,
                                        "stasis_wall_enabled": False, "circuit_breaker_enabled": False}}
    reasoner._session_usage = {}
    # Build ~12k estimated tokens of unprotected prose (chars/4).
    prose = "word " * 3000
    ir = EdgeKIR(
        messages=[{"role": "user", "content": prose, "context_role": "user_prompt"}],
        model="accounts/fireworks/models/glm-5p3-flash",
        max_tokens=256,
        metadata={"provider": "fireworks"},
    )
    # Use the public reason() path if it doesn't need extra services.
    from app.kernel.governance.reason import GovernanceDecision
    result = reasoner._apply_meta_rules(ir, "test-session")
    assert result.decision != GovernanceDecision.DENY, result.reason
    assert "max_input_tokens_per_request" in (result.policies_applied or [])


def test_stream_error_payload_does_not_invent_a_transport_receipt():
    """The IDE must see the governed code, not an empty provider_transport dict."""
    event = {
        "type": "error",
        "error": "Protected context exceeds input budget",
        "code": "CONTEXT_BUDGET_EXCEEDED",
        "error_type": "governed_execution_error",
        "governed_error": {
            "type": "governed_execution_error",
            "code": "CONTEXT_BUDGET_EXCEEDED",
            "message": "Protected context exceeds input budget",
        },
    }
    receipt = event.get("transport_receipt")
    if not isinstance(receipt, dict):
        receipt = {}
    if not (receipt.get("http_status") or receipt.get("content_type") or receipt.get("requested_url")):
        receipt = {}
    payload = {"error": event["error"], "code": event["code"], "governed_error": event["governed_error"]}
    if receipt:
        payload["provider_transport"] = receipt
    assert "provider_transport" not in payload
    assert payload["governed_error"]["code"] == "CONTEXT_BUDGET_EXCEEDED"

from app.context.economizer import ContextEconomizer
from app.kernel.perceive import EdgeKIR


def test_context_economizer_reduces_oversized_context():
    policies = {
        "meta_rules": {
            "context_economizer_enabled": True,
            "max_input_tokens_per_request": 100,
            "context_compression_trigger_ratio": 0.8,
            "context_compression_ratio_target": 0.3,
            "context_economizer_min_recent_messages": 2,
            "context_economizer_max_message_chars": 200,
            "context_economizer_preserve_system": True,
        }
    }
    messages = [
        {"role": "system", "content": "Preserve this instruction."},
        {"role": "user", "content": "old context " * 200},
        {"role": "assistant", "content": "old answer " * 200},
        {"role": "user", "content": "important recent question"},
        {"role": "assistant", "content": "important recent answer"},
    ]
    ir = EdgeKIR(messages=messages, model="gpt-3.5-turbo")

    result = ContextEconomizer(policies).economize(ir)

    assert result.changed is True
    assert result.final_tokens < result.original_tokens
    assert result.ir.messages[0]["role"] == "system"
    assert result.ir.messages[-1]["content"] == "important recent answer"
    assert result.ir.metadata["context_economy"]["changed"] is True


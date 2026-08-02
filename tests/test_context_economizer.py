from copy import deepcopy

from app.context.economizer import ContextEconomizer
from app.kernel.compute.perceive import EdgeKIR


def _policies(**overrides):
    meta_rules = {
        "context_economizer_enabled": True,
        "max_input_tokens_per_request": 100,
        "context_compression_trigger_ratio": 0.8,
        "context_compression_ratio_target": 0.3,
        "context_economizer_min_recent_messages": 2,
        "context_economizer_max_message_chars": 200,
        "context_economizer_preserve_system": True,
    }
    meta_rules.update(overrides)
    return {"meta_rules": meta_rules}


def test_context_economizer_reduces_oversized_context():
    messages = [
        {"role": "system", "content": "Preserve this instruction."},
        {"role": "user", "content": "old context " * 200},
        {"role": "assistant", "content": "old answer " * 200},
        {"role": "user", "content": "important recent question"},
        {"role": "assistant", "content": "important recent answer"},
    ]
    ir = EdgeKIR(messages=messages, model="gpt-3.5-turbo")

    result = ContextEconomizer(_policies()).economize(ir)

    assert result.changed is True
    assert result.final_tokens < result.original_tokens
    assert result.ir.messages[0]["role"] == "system"
    assert result.ir.messages[-1]["content"] == "important recent answer"
    assert result.ir.metadata["context_economy"]["changed"] is True


def test_normal_messages_are_not_dropped_during_long_message_scan():
    economizer = ContextEconomizer(_policies())
    messages = [
        {"role": "system", "content": "System instruction"},
        {"role": "user", "content": "Short user message"},
        {"role": "assistant", "content": "Short assistant response"},
    ]

    compressed, removed, _, _ = economizer._compress_messages(
        messages=messages,
        target_tokens=10_000,
        min_recent_messages=2,
        max_message_chars=200,
        preserve_system=True,
    )

    assert removed == 0
    assert compressed == messages


def test_structured_message_content_is_not_silently_dropped():
    economizer = ContextEconomizer(_policies())
    structured_content = [
        {"type": "text", "text": "Inspect this image"},
        {
            "type": "image_url",
            "image_url": {"url": "data:image/png;base64,test"},
        },
    ]
    messages = [
        {"role": "system", "content": "System instruction"},
        {"role": "user", "content": structured_content},
        {"role": "assistant", "content": "Acknowledged"},
    ]

    compressed, removed, _, _ = economizer._compress_messages(
        messages=messages,
        target_tokens=10_000,
        min_recent_messages=2,
        max_message_chars=200,
        preserve_system=True,
    )

    assert removed == 0
    assert any(message.get("content") == structured_content for message in compressed)


def test_oversized_message_is_trimmed_but_retained():
    economizer = ContextEconomizer(_policies())
    long_content = "A" * 500
    messages = [
        {"role": "system", "content": "System instruction"},
        {"role": "user", "content": long_content},
        {"role": "assistant", "content": "Recent response"},
    ]

    compressed, removed, chars_removed, notes = economizer._compress_messages(
        messages=messages,
        target_tokens=10_000,
        min_recent_messages=2,
        max_message_chars=120,
        preserve_system=True,
    )

    assert removed == 0
    assert chars_removed > 0
    assert notes == ["Whitespace and long-message trimming reached target"]
    trimmed = compressed[1]["content"]
    assert "characters omitted from middle" in trimmed
    assert trimmed.startswith("A")
    assert trimmed.endswith("A")


def test_economizer_does_not_mutate_original_messages():
    messages = [
        {"role": "system", "content": "Preserve   internal   spacing"},
        {"role": "user", "content": "old context " * 200},
        {"role": "assistant", "content": "recent response"},
    ]
    original = deepcopy(messages)
    ir = EdgeKIR(messages=messages, model="gpt-3.5-turbo")

    ContextEconomizer(_policies()).economize(ir)

    assert messages == original
    assert ir.messages == original


def test_disabled_economizer_returns_unchanged_result():
    messages = [
        {"role": "system", "content": "System"},
        {"role": "user", "content": "Keep me"},
    ]
    ir = EdgeKIR(messages=messages, model="gpt-3.5-turbo", metadata={})
    policies = _policies(context_economizer_enabled=False)

    result = ContextEconomizer(policies).economize(ir)

    assert result.changed is False
    assert result.strategy == "disabled"
    assert result.ir.messages == messages
    assert result.ir.metadata["context_economy"]["changed"] is False


def test_within_budget_result_is_unchanged():
    messages = [
        {"role": "system", "content": "System"},
        {"role": "user", "content": "A short request"},
    ]
    ir = EdgeKIR(messages=messages, model="gpt-3.5-turbo", metadata={})
    policies = _policies(
        max_input_tokens_per_request=10_000,
        context_compression_trigger_ratio=0.9,
    )

    result = ContextEconomizer(policies).economize(ir)

    assert result.changed is False
    assert result.strategy == "within_budget"
    assert result.ir.messages == messages


def test_system_message_is_preserved_when_compression_removes_old_messages():
    system_content = "Never remove this governing instruction."
    messages = [
        {"role": "system", "content": system_content},
        {"role": "user", "content": "old user context " * 100},
        {"role": "assistant", "content": "old assistant context " * 100},
        {"role": "user", "content": "recent question"},
        {"role": "assistant", "content": "recent answer"},
    ]
    ir = EdgeKIR(messages=messages, model="gpt-3.5-turbo")

    result = ContextEconomizer(_policies()).economize(ir)

    assert result.ir.messages[0]["role"] == "system"
    assert result.ir.messages[0]["content"] == system_content


def test_metadata_records_final_economy_state():
    messages = [
        {"role": "system", "content": "System"},
        {"role": "user", "content": "old context " * 200},
        {"role": "assistant", "content": "recent answer"},
    ]
    ir = EdgeKIR(messages=messages, model="gpt-3.5-turbo", metadata={"trace": "abc"})

    result = ContextEconomizer(_policies()).economize(ir)
    economy = result.ir.metadata["context_economy"]

    assert result.ir.metadata["trace"] == "abc"
    assert economy["changed"] is True
    assert economy["original_tokens"] == result.original_tokens
    assert economy["final_tokens"] == result.final_tokens
    assert economy["messages_removed"] == result.messages_removed
    assert economy["chars_removed"] == result.chars_removed
    assert economy["strategy"] == "deterministic_trim"

"""Model-aware output max_tokens and finish_reason=length continuation."""
from __future__ import annotations

from app.cli.api import (
    BeastApiClient,
    continuation_user_message,
    provider_stream_continuations,
    provider_stream_max_tokens,
)
from app.context.budget import MAX_CODING_OUTPUT, output_token_budget, resolve_output_budget
from app.routes.ide_support.common import pair_programmer_limits


def test_fireworks_kimi_output_budget_is_coding_sized():
    info = resolve_output_budget(
        model="accounts/fireworks/models/kimi-k3",
        provider="fireworks",
        requested=16000,
        input_tokens=22677,
    )
    assert info["max_tokens"] >= 16384
    assert info["max_tokens"] <= MAX_CODING_OUTPUT
    assert info["family_output_cap"] == 32768
    # Must not inherit the provider-lane cost default of 2048.
    assert info["max_tokens"] > 2048
    assert info["max_tokens"] > 3072


def test_family_output_caps_for_glm_deepseek_gpt_oss_and_kimi():
    cases = [
        ("fireworks", "accounts/fireworks/models/glm-5p3-flash"),
        ("fireworks", "accounts/fireworks/models/deepseek-v4p1-flash"),
        ("hf", "moonshotai/Kimi-K2.7-Code:deepinfra"),
        ("hf", "openai/gpt-oss-120b:deepinfra"),
    ]
    for provider, model in cases:
        tokens = output_token_budget(provider=provider, model=model, requested=8000)
        assert tokens >= 16384, (provider, model, tokens)
        assert tokens <= 32768


def test_output_budget_respects_remaining_window():
    info = resolve_output_budget(
        model="accounts/fireworks/models/kimi-k3",
        provider="fireworks",
        requested=32768,
        input_tokens=262000,
    )
    # window 262144 - 262000 leaves little headroom
    assert info["max_tokens"] <= info["headroom"]
    assert info["max_tokens"] >= 256


def test_compact_local_coder_stays_bounded():
    tokens, chars, files = pair_programmer_limits("ollama", "qwen2.5:3b", 9999, 999999)
    assert tokens == 1024
    assert chars == 2400
    assert files == 3


def test_pair_programmer_limits_no_longer_cap_fireworks_at_3072():
    tokens, chars, files = pair_programmer_limits(
        "fireworks", "accounts/fireworks/models/kimi-k3", 16000, 50000
    )
    assert tokens >= 16384
    assert tokens <= 32768
    assert chars >= 12000
    assert files >= 4


def test_stream_helpers_are_model_aware():
    assert provider_stream_max_tokens("fireworks", "accounts/fireworks/models/kimi-k3") >= 16384
    assert provider_stream_continuations("fireworks") >= 3


def test_continuation_message_for_empty_action_ir():
    empty = continuation_user_message(action_ir_required=True, yielded="")
    assert "Action IR" in empty
    assert "reasoning" in empty.lower()
    partial = continuation_user_message(action_ir_required=True, yielded='{"kind":')
    assert "next character" in partial
    chat = continuation_user_message(action_ir_required=False, yielded="hello")
    assert "next word" in chat


def test_extract_stream_reasoning_is_not_treated_as_content():
    client = BeastApiClient.__new__(BeastApiClient)
    chunk = {
        "choices": [{
            "delta": {"reasoning_content": "thinking hard", "content": ""},
            "finish_reason": "length",
        }]
    }
    assert client._extract_stream_delta(chunk) == ""
    assert client._extract_stream_reasoning(chunk) == "thinking hard"
    visible = {"choices": [{"delta": {"content": '{"kind":'}}]}
    assert client._extract_stream_delta(visible) == '{"kind":'
    assert client._extract_stream_reasoning(visible) == ""

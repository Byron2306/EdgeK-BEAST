"""Evidence-gated claim status for Forge KV engine adapters."""
from __future__ import annotations

from typing import Any


OLLAMA_LEGACY_CONTEXT_STATUS: dict[str, Any] = {
    "engine": "ollama_api_generate_context",
    "status": "not_proven",
    "performance_claim_allowed": False,
    "reason": (
        "Live warmed paired measurement on qwen2.5:0.5b supplied and returned "
        "native context but increased median prompt evaluation from 1262 to 1292."
    ),
    "allowed_claim": "Context-array transport was observed; no prompt-work or latency saving is claimed.",
    "required_for_promotion": "A repeatable engine-specific paired proof with lower measured median prompt work.",
}

LLAMACPP_PROMPT_CACHE_STATUS: dict[str, Any] = {
    "engine": "llama_cpp_server_prompt_cache",
    "status": "proven_engine_local",
    "performance_claim_allowed": True,
    "reason": (
        "Live llama.cpp receipts show a warm prompt-cache hit and a cold restart boundary: "
        "649 prompt tokens fell to 7 with cache_n=642, then returned to 649 with cache_n=0 after restart."
    ),
    "allowed_claim": "Prompt-work savings are proven only within one local llama.cpp server lifetime.",
    "portable_raw_kv": False,
    "required_for_promotion": "A separate, explicitly authorized proof for any broader cache persistence or sharing claim.",
}


def claim_status(*, engine: str, native_context_supplied: bool) -> dict[str, Any]:
    if engine == "ollama_api_generate_context":
        return {**OLLAMA_LEGACY_CONTEXT_STATUS, "native_context_supplied": native_context_supplied}
    if engine == "llama_cpp_server_prompt_cache":
        return {**LLAMACPP_PROMPT_CACHE_STATUS, "native_context_supplied": native_context_supplied}
    return {
        "engine": engine,
        "status": "unassessed",
        "performance_claim_allowed": False,
        "native_context_supplied": native_context_supplied,
        "allowed_claim": "No performance claim until live paired evidence exists.",
    }

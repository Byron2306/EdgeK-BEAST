"""Model-aware input token budgets for the governed path.

The policy default ``max_input_tokens_per_request`` (8000) is a conservative
fallback for unknown models. It is far below the context windows of the
models BEAST actually routes to (Fireworks GLM / DeepSeek / Kimi, HF router
siblings, local Ollama).  This helper resolves a real window from the
registry (HF ``context_length``), a family table, or request metadata, then
reserves output tokens so the economizer and the governor share one number.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

POLICY_DEFAULT_INPUT = 8000
DEFAULT_OUTPUT_RESERVE = 4096
MIN_INPUT_BUDGET = 1024

# Conservative floors when a family is recognised but no registry window is known.
# Prefer the published HF-router context_length when available (often 128k–1M).
FAMILY_WINDOWS = (
    ("kimi", 262144),
    ("deepseek", 131072),
    ("glm", 131072),
    ("gpt-oss", 131072),
    ("gptoss", 131072),
    ("llama-3.3", 131072),
    ("llama3.3", 131072),
    ("qwen", 32768),
)

_LANES_DIR = Path(__file__).resolve().parents[1] / "kernel" / "compute"


def normalize_model_name(name: str) -> str:
    """Lowercase, drop slashes/accounts prefixes, treat 5p3 as 5.3."""
    raw = str(name or "").strip()
    raw = re.sub(r"(?i)(\d)p(\d)", r"\1.\2", raw)
    raw = raw.split(":")[0]  # ollama tag: qwen3:4b -> qwen3
    raw = raw.rsplit("/", 1)[-1]
    raw = raw.replace("accounts/fireworks/models/", "")
    return re.sub(r"[^a-z0-9]+", "", raw.lower())


def _family_window(model: str) -> Optional[int]:
    lowered = str(model or "").lower()
    lowered = re.sub(r"(?i)(\d)p(\d)", r"\1.\2", lowered)
    for token, window in FAMILY_WINDOWS:
        if token in lowered:
            return int(window)
    return None


@lru_cache(maxsize=1)
def _hf_router_windows() -> Dict[str, int]:
    path = _LANES_DIR / "hf_router_lanes.json"
    out: Dict[str, int] = {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return out
    for model in data.get("models") or []:
        if not isinstance(model, dict):
            continue
        name = str(model.get("model") or "")
        lengths = [
            int(route["context_length"])
            for route in (model.get("routes") or [])
            if isinstance(route, dict) and str(route.get("context_length") or "").isdigit()
        ]
        # context_length may already be int
        for route in model.get("routes") or []:
            if isinstance(route, dict) and isinstance(route.get("context_length"), int):
                lengths.append(int(route["context_length"]))
        if name and lengths:
            out[normalize_model_name(name)] = max(lengths)
            # also index the short leaf name
            leaf = name.rsplit("/", 1)[-1]
            out[normalize_model_name(leaf)] = max(lengths)
    return out


def _window_from_registry(model: str) -> Optional[int]:
    if not model:
        return None
    index = _hf_router_windows()
    key = normalize_model_name(model)
    if key in index:
        return index[key]
    # fuzzy: glm5p3flash vs glm53flash already normalised; also substring
    for stored, window in index.items():
        if key and stored and (key in stored or stored in key):
            return window
    return None


def _window_from_metadata(metadata: Optional[Mapping[str, Any]]) -> Optional[int]:
    if not metadata:
        return None
    for key in ("context_window", "context_length", "max_input_tokens", "model_context_window"):
        value = metadata.get(key)
        try:
            number = int(value)
        except (TypeError, ValueError):
            continue
        if number >= MIN_INPUT_BUDGET:
            return number
    return None


def resolve_input_budget(
    *,
    model: str = "",
    provider: str = "",
    policies: Optional[Mapping[str, Any]] = None,
    metadata: Optional[Mapping[str, Any]] = None,
    max_output_tokens: Optional[int] = None,
) -> Dict[str, Any]:
    """Return the input budget the economizer and governor must both use."""
    policies = policies or {}
    meta_rules = policies.get("meta_rules") if isinstance(policies.get("meta_rules"), dict) else {}
    policy_default = int(meta_rules.get("max_input_tokens_per_request", POLICY_DEFAULT_INPUT) or POLICY_DEFAULT_INPUT)
    source = "policy_default"
    window = _window_from_metadata(metadata)
    if window:
        source = "request_metadata"
    else:
        window = _window_from_registry(model)
        if window:
            source = "hf_router_registry"
        else:
            window = _family_window(model) or _family_window(provider)
            if window:
                source = "model_family"
            else:
                window = policy_default
                source = "policy_default"
    reserve_cap = int(max_output_tokens or meta_rules.get("max_output_tokens_per_request") or DEFAULT_OUTPUT_RESERVE)
    reserve = max(0, min(reserve_cap, DEFAULT_OUTPUT_RESERVE, max(0, int(window) // 8)))
    if source == "policy_default":
        # Historical contract: the policy number is the input cap.
        max_input = max(1, int(window))
        reserve = 0
    else:
        max_input = max(MIN_INPUT_BUDGET, int(window) - reserve)
    return {
        "context_window": int(window),
        "max_input_tokens": int(max_input),
        "reserved_output_tokens": int(reserve),
        "source": source,
        "model": model or "",
        "provider": provider or "",
        "policy_default": policy_default,
    }


def input_token_budget(
    *,
    model: str = "",
    provider: str = "",
    policies: Optional[Mapping[str, Any]] = None,
    metadata: Optional[Mapping[str, Any]] = None,
    max_output_tokens: Optional[int] = None,
) -> int:
    return int(resolve_input_budget(
        model=model, provider=provider, policies=policies, metadata=metadata,
        max_output_tokens=max_output_tokens,
    )["max_input_tokens"])



# Published / conservative max *output* tokens for coding families.
# Never treat provider-lane max_tokens (often 2048, a cost default) as this cap.
DEFAULT_CODING_OUTPUT = 16384
MAX_CODING_OUTPUT = 32768
MIN_CODING_OUTPUT = 256
FAMILY_OUTPUT_CAPS = (
    ("kimi", 32768),
    ("deepseek", 32768),
    ("glm", 32768),
    ("gpt-oss", 32768),
    ("gptoss", 32768),
    ("llama-3.3", 16384),
    ("llama3.3", 16384),
    ("qwen", 16384),
)


def _family_output_cap(model: str, provider: str = "") -> Optional[int]:
    blob = f"{model or ''} {provider or ''}".lower()
    blob = re.sub(r"(?i)(\d)p(\d)", r"\1.\2", blob)
    for token, cap in FAMILY_OUTPUT_CAPS:
        if token in blob:
            return int(cap)
    return None


def resolve_output_budget(
    *,
    model: str = "",
    provider: str = "",
    requested: Optional[int] = None,
    input_tokens: Optional[int] = None,
    metadata: Optional[Mapping[str, Any]] = None,
    compact_local: bool = False,
    policies: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Return the output max_tokens for an Agent Coder / live stream turn.

    Coding turns need a high default (16k–32k), capped by the model's output
    limit and by remaining context (window minus input). Provider-lane
    ``max_tokens: 2048`` values are cost defaults, not model limits, and are
    not used as the cap.
    """
    window_info = resolve_input_budget(model=model, provider=provider, policies=policies, metadata=metadata)
    window = int(window_info["context_window"])
    family_cap = _family_output_cap(model, provider) or MAX_CODING_OUTPUT
    # Leave room for the already-assembled prompt when we know it.
    headroom = window
    if input_tokens is not None:
        try:
            used = max(0, int(input_tokens))
        except (TypeError, ValueError):
            used = 0
        headroom = max(MIN_CODING_OUTPUT, window - used)
    cap = min(MAX_CODING_OUTPUT, int(family_cap), int(headroom))
    if compact_local:
        cap = min(cap, 1024)
    if requested is None:
        target = min(DEFAULT_CODING_OUTPUT, cap) if not compact_local else min(1024, cap)
    else:
        try:
            target = int(requested)
        except (TypeError, ValueError):
            target = DEFAULT_CODING_OUTPUT
    # For full-size coding models, never let a small requested/policy value
    # (or the old 3072 route cap) under-budget a turn that can legally use
    # the family output cap. Compact local models stay tightly bounded.
    if not compact_local:
        target = max(target, min(DEFAULT_CODING_OUTPUT, cap))
    max_tokens = max(MIN_CODING_OUTPUT, min(int(target), int(cap)))
    return {
        "max_tokens": int(max_tokens),
        "context_window": int(window),
        "family_output_cap": int(family_cap),
        "headroom": int(headroom),
        "source": window_info.get("source") or "default",
        "model": model or "",
        "provider": provider or "",
        "compact_local": bool(compact_local),
    }


def output_token_budget(**kwargs: Any) -> int:
    return int(resolve_output_budget(**kwargs)["max_tokens"])

__all__ = [
    "POLICY_DEFAULT_INPUT",
    "DEFAULT_CODING_OUTPUT",
    "MAX_CODING_OUTPUT",
    "input_token_budget",
    "normalize_model_name",
    "output_token_budget",
    "resolve_input_budget",
    "resolve_output_budget",
]

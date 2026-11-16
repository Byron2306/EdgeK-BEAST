"""Schema-forced output for every provider lane BEAST governs.

"Ask for JSON in the prompt and parse free text" is the root of the agent
coding JSON failures (qwen3 prose in thinking mode, NIM truncated reasoning,
markdown fences).  Each serving stack has a decoder-level way to force a JSON
schema; this module builds the request body for each so callers never have to
know the dialect:

* Ollama native ``/api/chat`` / ``/api/generate``: ``format: <json schema>``
  plus ``think: false`` (qwen3 / deepseek-r1 thinking off) and
  ``options.num_predict`` as the hard output budget.
* NVIDIA NIM (OpenAI-compatible): ``response_format`` json_schema, with
  ``nvext.guided_json`` as the NIM-native fallback dialect, and
  ``chat_template_kwargs`` to disable thinking.
* Hugging Face Inference Providers router and other OpenAI-compatible
  servers: ``response_format: {type: json_schema, json_schema: {...}}``.
* TGI Messages API: ``response_format: {type: json_object, value: schema}``;
  TGI ``/generate``: ``parameters.grammar: {type: json, value: schema}``.
* vLLM / SGLang: ``guided_json`` (extra body) as well as ``response_format``.

Dialects are ordered so a 400 from one can fall back to the next and finally
to ``prompt_only`` (recorded so the scorecard learns which lanes really
constrain).  Pure functions; no I/O; never touches credentials.
"""
from __future__ import annotations

import copy
from typing import Any, Dict, List, Mapping

DIALECTS: Dict[str, List[str]] = {
    "ollama": ["ollama_format", "prompt_only"],
    "nim": ["openai_json_schema", "nim_guided_json", "prompt_only"],
    "hf_router": ["openai_json_schema", "openai_json_object", "prompt_only"],
    "openai": ["openai_json_schema", "openai_json_object", "prompt_only"],
    "gemini": ["openai_json_schema", "openai_json_object", "prompt_only"],
    "tgi": ["tgi_json_object", "prompt_only"],
    "tgi_generate": ["tgi_grammar", "prompt_only"],
    "vllm": ["vllm_guided_json", "openai_json_schema", "prompt_only"],
}

# Models whose chat template thinks by default; thinking burns the output
# budget before the JSON starts and leaks <think> prose into content.
THINKING_MODEL_HINTS = ("qwen3", "deepseek-r1", "deepseek-v", "nemotron", "gpt-oss", "qwq", "magistral", "phi4-reasoning", "glm-5")


def is_reasoning_model(model: str) -> bool:
    low = (model or "").lower()
    return any(h in low for h in THINKING_MODEL_HINTS)


def output_budget(model: str, *, base: int = 1024, reasoning_budget: int = 4096, thinking_disabled: bool = True) -> int:
    """Hard output-token budget sized for the model class.

    Reasoning models that cannot (or will not) turn thinking off need room for
    the hidden reasoning before the JSON; NIM's truncation failures in the
    2026-11-16 gauntlet came from 2048-token caps on such models.
    """
    if is_reasoning_model(model) and not thinking_disabled:
        return max(base, reasoning_budget)
    if is_reasoning_model(model):
        return max(base, reasoning_budget // 2)
    return base


def dialects_for(kind: str) -> List[str]:
    return list(DIALECTS.get(kind, ["openai_json_schema", "prompt_only"]))


def _schema_name(name: str) -> str:
    cleaned = "".join(c if c.isalnum() or c in "_-" else "_" for c in name)[:64]
    return cleaned or "beast_action"


def constrain_body(kind: str, body: Mapping[str, Any], schema: Mapping[str, Any], *, dialect: str | None = None,
                   name: str = "beast_action", max_tokens: int | None = None, disable_thinking: bool = True,
                   stream: bool = True) -> Dict[str, Any]:
    """Return a copy of ``body`` with schema forcing for ``kind`` in ``dialect``.

    ``kind`` names the wire protocol (ollama, nim, hf_router, openai, tgi,
    tgi_generate, vllm).  ``dialect`` defaults to the first preference.
    """
    out: Dict[str, Any] = copy.deepcopy(dict(body))
    schema = copy.deepcopy(dict(schema))
    dialect = dialect or dialects_for(kind)[0]
    model = str(out.get("model") or "")
    if kind == "tgi_generate":
        params = out.setdefault("parameters", {})
        if dialect == "tgi_grammar":
            params["grammar"] = {"type": "json", "value": schema}
        if max_tokens:
            params["max_new_tokens"] = int(max_tokens)
        out["stream"] = bool(stream)
        return out
    if kind == "ollama":
        if dialect == "ollama_format":
            out["format"] = schema
        if disable_thinking:
            out["think"] = False
        options = out.setdefault("options", {})
        if max_tokens:
            options["num_predict"] = int(max_tokens)
        options.setdefault("temperature", 0)
        out["stream"] = bool(stream)
        return out
    # OpenAI-compatible family.
    out["stream"] = bool(stream)
    if stream:
        out.setdefault("stream_options", {"include_usage": True})
    if max_tokens:
        out["max_tokens"] = int(max_tokens)
    out.setdefault("temperature", 0)
    if dialect == "openai_json_schema":
        out["response_format"] = {"type": "json_schema",
                                  "json_schema": {"name": _schema_name(name), "schema": schema, "strict": True}}
    elif dialect == "openai_json_object":
        out["response_format"] = {"type": "json_object"}
    elif dialect == "nim_guided_json":
        out.pop("response_format", None)
        out["nvext"] = {**dict(out.get("nvext") or {}), "guided_json": schema}
    elif dialect == "tgi_json_object":
        out["response_format"] = {"type": "json_object", "value": schema}
    elif dialect == "vllm_guided_json":
        out["guided_json"] = schema
    if disable_thinking and kind == "gemini":
        # Gemini OpenAI-compat: thinking off for 2.5 flash-class models (stripped on 400 by strip_unsupported)
        out.setdefault("reasoning_effort", "none")
    if disable_thinking and kind in {"nim", "vllm", "hf_router", "openai"} and is_reasoning_model(model):
        low = model.lower()
        if "gpt-oss" in low:
            out.setdefault("reasoning_effort", "low")
        elif "deepseek" in low:
            out.setdefault("chat_template_kwargs", {"thinking": False})
        else:
            out.setdefault("chat_template_kwargs", {"enable_thinking": False})
    return out


def strip_unsupported(body: Mapping[str, Any], error_text: str) -> Dict[str, Any]:
    """Drop optional knobs a server rejected (400) so the next dialect retry is clean."""
    out = dict(body)
    low = (error_text or "").lower()
    for key in ("chat_template_kwargs", "reasoning_effort", "stream_options"):
        if key in low and key in out:
            out.pop(key)
    if "thinking" in low and ("not supported" in low or "unsupported" in low):
        # thinking-only models (e.g. GLM-5.3 on Fireworks) reject any thinking-off knob, whatever its name
        out.pop("chat_template_kwargs", None)
        out.pop("reasoning_effort", None)
    return out


__all__ = ["DIALECTS", "constrain_body", "dialects_for", "is_reasoning_model", "output_budget", "strip_unsupported"]

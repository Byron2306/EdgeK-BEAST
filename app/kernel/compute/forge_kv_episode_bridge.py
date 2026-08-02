"""Metadata-only Sensorium bridge for Forge KV economics."""
from __future__ import annotations
from typing import Any, Mapping


def episode_economics_payload(result: Mapping[str, Any]) -> dict[str, Any]:
    economics = dict(result.get("economics") or {})
    value = dict(result.get("value") or {})
    pressure = dict(result.get("pressure") or {})
    return {
        "beast_object_type": "forge_kv_episode_economics",
        "version": "1.0",
        "cache_identity": str(result.get("cache_identity") or ""),
        "reuse_mode": str(economics.get("reuse_mode") or "miss"),
        "prompt_eval_count": int(economics.get("prompt_eval_count") or 0),
        "prompt_tokens_avoided": int(economics.get("prompt_tokens_avoided") or 0),
        "prompt_eval_ms_avoided": float(economics.get("prompt_eval_ms_avoided") or 0),
        "net_latency_saved_ms": float(economics.get("net_latency_saved_ms") or 0),
        "estimated_context_bytes": int(economics.get("estimated_context_bytes") or 0),
        "value_score": float(value.get("score") or 0),
        "pressure_state": str(pressure.get("state") or "unknown"),
        "paired_baseline_present": bool(economics.get("paired_baseline_present")),
        "raw_prompt_retained": False,
        "native_context_exported": False,
        "authority": "observation_only",
    }

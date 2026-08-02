"""Operational control-plane adapters for external KV-aware serving stacks.

BEAST never serializes its own ``KVCacheBlock`` into a foreign engine.  The
engine/LMCache pair owns its tensors; BEAST owns admission, identity hashes,
health, metrics, and receipts.  This keeps a cache hit from becoming an
unverified cross-model restore claim.
"""
from __future__ import annotations

import os
import re
import time
from typing import Any, Dict, Optional

import httpx


def _truthy(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


class LMCacheControlPlane:
    """Use LMCache MP's documented HTTP control surface, when configured."""

    def __init__(self, client: Optional[httpx.Client] = None) -> None:
        self.client = client or httpx.Client()

    @property
    def endpoint(self) -> str:
        return os.environ.get("LMCACHE_HTTP_URL", "").rstrip("/")

    def state(self, *, probe: bool = False, timeout_seconds: float = 1.5) -> Dict[str, Any]:
        configured = bool(self.endpoint)
        result: Dict[str, Any] = {
            "beast_object_type": "lmcache_control_plane_state",
            "version": "1.0",
            "configured": configured,
            "http_endpoint": self.endpoint,
            "zmq_endpoint": os.environ.get("LMCACHE_ZMQ_URL", ""),
            "mode": os.environ.get("LMCACHE_MODE", "mp"),
            "authority": "external_engine_owned_kv_only",
            "portable_raw_kv": False,
            "claim_boundary": "Health and Prometheus metrics are live evidence; BEAST does not restore raw foreign KV tensors.",
        }
        if not probe:
            return {**result, "ready": False, "reason": "probe_not_requested"}
        if not configured:
            return {**result, "ready": False, "reason": "http_endpoint_not_configured"}
        started = time.perf_counter()
        try:
            health = self.client.get(self.endpoint + "/healthcheck", timeout=timeout_seconds)
            health.raise_for_status()
            status = self.client.get(self.endpoint + "/status", timeout=timeout_seconds)
            status.raise_for_status()
            metrics = self.client.get(self.endpoint + "/metrics", timeout=timeout_seconds)
            metrics.raise_for_status()
            return {
                **result,
                "ready": str(health.json().get("status", "")).lower() == "healthy",
                "reason": "lmcache_mp_healthcheck_passed",
                "latency_ms": round((time.perf_counter() - started) * 1000, 3),
                "status": status.json(),
                "metrics": self._interesting_metrics(metrics.text),
            }
        except (httpx.HTTPError, ValueError) as exc:
            return {**result, "ready": False, "reason": type(exc).__name__, "latency_ms": round((time.perf_counter() - started) * 1000, 3)}

    def clear_cache(self, *, approved: bool = False, timeout_seconds: float = 5.0) -> Dict[str, Any]:
        if not approved:
            raise PermissionError("LMCache clear requires approved=true")
        if not self.endpoint:
            raise RuntimeError("LMCACHE_HTTP_URL is not configured")
        response = self.client.post(self.endpoint + "/cache/clear", timeout=timeout_seconds)
        response.raise_for_status()
        return {"beast_object_type": "lmcache_clear_receipt", "version": "1.0", "approved": True, "result": response.json()}

    @staticmethod
    def _interesting_metrics(payload: str) -> Dict[str, float]:
        values: Dict[str, float] = {}
        for line in payload.splitlines():
            if not line or line.startswith("#") or "lmcache" not in line.lower():
                continue
            match = re.match(r"^([^\s{]+)(?:\{[^}]*\})?\s+([-+0-9.eE]+)$", line)
            if match:
                try:
                    values[match.group(1)] = float(match.group(2))
                except ValueError:
                    pass
        return values


def accelerator_execution_enabled() -> bool:
    """Explicit operator opt-in; endpoint configuration alone never enables GPUs."""
    return _truthy(os.environ.get("BEAST_ACCELERATOR_ENABLED", "false"))

"""Media generation lanes (fal queue API). Separate from the coding scorecard by design.

fal is an image/video/audio host. ``FalMediaLane.generate`` submits to ``https://queue.fal.run/{model}`` with
``Authorization: Key $FAL_KEY`` (read from env or .beast/provider_secrets.env by name; never logged), polls the
returned ``status_url`` and fetches ``response_url``. Results and errors are redacted; the key value is never
written to receipts. Off unless BEAST_MEDIA_LANES=1 (or ``force=True`` for an explicit smoke test).
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Mapping, Optional

import httpx

from app.kernel.compute.governed_client import PROVIDER_SECRETS_ENV, dotenv_value, redact

FAL_QUEUE = "https://queue.fal.run"
# USD per megapixel (fal pricing page, 2026-11-16) for cost estimates of known cheap models
FAL_PRICES_PER_MP = {"fal-ai/flux/schnell": 0.003}


def enabled(env: Mapping[str, str] | None = None) -> bool:
    env = os.environ if env is None else env
    return str(env.get("BEAST_MEDIA_LANES", "0")).strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class MediaResult:
    ok: bool
    model: str
    status: str
    latency_ms: float = 0.0
    est_cost_usd: float = 0.0
    outputs: list = field(default_factory=list)
    request_id: str = ""
    error: str = ""

    def public(self) -> Dict[str, Any]:
        return {"ok": self.ok, "model": self.model, "status": self.status, "latency_ms": round(self.latency_ms, 1),
                "est_cost_usd": round(self.est_cost_usd, 6), "outputs": self.outputs, "request_id": self.request_id,
                "error": self.error, "lane": "media", "counts_in_coding_scorecard": False}


class FalMediaLane:
    def __init__(self, *, key_env: str = "FAL_KEY", dotenv: Optional[str] = None, base: str = FAL_QUEUE,
                 transport: httpx.BaseTransport | None = None, poll_s: float = 1.0, timeout_s: float = 120.0):
        self.key_env, self.dotenv, self.base = key_env, PROVIDER_SECRETS_ENV if dotenv is None else dotenv, base.rstrip("/")
        self.transport, self.poll_s, self.timeout_s = transport, poll_s, timeout_s

    def _key(self) -> str:
        return os.environ.get(self.key_env) or (dotenv_value(self.dotenv, self.key_env) if self.dotenv else "")

    def available(self) -> bool:
        return bool(self._key())

    def generate(self, model: str, payload: Mapping[str, Any], *, force: bool = False) -> MediaResult:
        if not (force or enabled()):
            return MediaResult(False, model, "disabled", error="BEAST_MEDIA_LANES off")
        key = self._key()
        if not key:
            return MediaResult(False, model, "no_key", error=f"{self.key_env} not set")
        headers = {"Authorization": f"Key {key}", "Content-Type": "application/json"}
        started = time.perf_counter()
        with httpx.Client(transport=self.transport, trust_env=False, timeout=30) as c:
            try:
                r = c.post(f"{self.base}/{model}", json=dict(payload), headers=headers)
                if r.status_code >= 400:
                    return MediaResult(False, model, "http_error", (time.perf_counter() - started) * 1000,
                                       error=redact(f"{r.status_code}:{r.text[:300]}", [key]))
                sub = r.json()
                rid, status_url, resp_url = sub.get("request_id", ""), sub.get("status_url"), sub.get("response_url")
                deadline = time.perf_counter() + self.timeout_s
                status = sub.get("status", "IN_QUEUE")
                while status not in {"COMPLETED", "FAILED", "ERROR"} and time.perf_counter() < deadline:
                    time.sleep(self.poll_s)
                    status = c.get(status_url, headers=headers).json().get("status", status)
                if status != "COMPLETED":
                    return MediaResult(False, model, status.lower(), (time.perf_counter() - started) * 1000, request_id=rid)
                body = c.get(resp_url, headers=headers).json()
            except httpx.HTTPError as exc:
                return MediaResult(False, model, "transport_error", (time.perf_counter() - started) * 1000,
                                   error=redact(f"{type(exc).__name__}: {exc}", [key]))
        imgs = body.get("images") or []
        mp = sum((i.get("width") or 0) * (i.get("height") or 0) for i in imgs) / 1e6
        return MediaResult(True, model, "completed", (time.perf_counter() - started) * 1000,
                           est_cost_usd=mp * FAL_PRICES_PER_MP.get(model, 0.0),
                           outputs=[{k: i.get(k) for k in ("url", "width", "height", "content_type")} for i in imgs], request_id=rid)


__all__ = ["FalMediaLane", "MediaResult", "enabled", "FAL_QUEUE"]

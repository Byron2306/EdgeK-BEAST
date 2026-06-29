"""Bounded live NVIDIA NIM smoke probe.

This module is intentionally outside the local crystal reuse hot path. It gives
operators a governed way to prove cloud reachability without making cloud
execution a default runtime dependency.
"""

from __future__ import annotations

import hashlib
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

import httpx

from app.kernel.registry.provider_registry import ProviderRegistry
from app.kernel.security.secret_vault import SecretVault


DEFAULT_NIM_MODELS = [
    "nvidia/nemotron-3-super-120b-a12b",
    "nvidia/llama-3.1-nemotron-ultra-253b-v1",
    "meta/llama-3.1-8b-instruct",
    "meta/llama-3.1-70b-instruct",
]


@dataclass(frozen=True)
class NIMProbeConfig:
    base_url: str
    model_candidates: List[str]
    timeout_seconds: float = 30.0
    max_tokens: int = 32


class NvidiaNIMLiveProbe:
    def __init__(
        self,
        *,
        registry: Optional[ProviderRegistry] = None,
        secret_vault: Optional[SecretVault] = None,
        client: Optional[httpx.Client] = None,
    ) -> None:
        self.registry = registry or ProviderRegistry()
        self.secret_vault = secret_vault or SecretVault()
        self.client = client or httpx.Client()

    def config(self, *, requested_model: str = "", timeout_seconds: float = 30.0, max_tokens: int = 32) -> NIMProbeConfig:
        record = next((item for item in self.registry.records(include_disabled=True) if item.provider_id == "nvidia_nim"), None)
        base_url = (os.environ.get("NVIDIA_NIM_BASE_URL") or (record.base_url if record else "") or "https://integrate.api.nvidia.com/v1").rstrip("/")
        registry_default = (record.default_model if record else "") or ""
        candidates = self._dedupe([requested_model, registry_default, *DEFAULT_NIM_MODELS])
        return NIMProbeConfig(
            base_url=base_url,
            model_candidates=candidates,
            timeout_seconds=max(3.0, min(float(timeout_seconds), 120.0)),
            max_tokens=max(1, min(int(max_tokens), 256)),
        )

    def run(
        self,
        *,
        prompt: str = "Return exactly: BEAST_NIM_LIVE_OK",
        requested_model: str = "",
        timeout_seconds: float = 30.0,
        max_tokens: int = 32,
        discover_models: bool = True,
    ) -> Dict[str, Any]:
        self.secret_vault.load(override=False)
        api_key = os.environ.get("NVIDIA_API_KEY", "")
        cfg = self.config(requested_model=requested_model, timeout_seconds=timeout_seconds, max_tokens=max_tokens)
        started = time.perf_counter()
        receipt: Dict[str, Any] = {
            "beast_object_type": "nvidia_nim_live_probe_receipt",
            "version": "1.0",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "provider": "nvidia_nim",
            "base_url": cfg.base_url,
            "requested_model": requested_model,
            "attempted_models": [],
            "secret": self._secret_status(api_key),
            "live_call_attempted": False,
            "status": "not_run",
            "claim_boundary": "Explicit live NIM smoke only; BEAST local CPU path remains default.",
        }
        if not api_key:
            receipt.update({"status": "missing_secret", "reason": "NVIDIA_API_KEY not loaded"})
            return self._finish(receipt, started)

        candidates = list(cfg.model_candidates)
        if discover_models:
            discovered = self.discover_chat_models(cfg, api_key)
            receipt["model_discovery"] = discovered
            candidates = self._dedupe([*candidates, *discovered.get("candidate_models", [])])

        for model in candidates:
            attempt = self._complete(cfg, api_key, model, prompt)
            receipt["live_call_attempted"] = True
            receipt["attempted_models"].append(attempt)
            if attempt.get("status") == "ok":
                receipt.update(
                    {
                        "status": "ok",
                        "model": model,
                        "latency_ms": attempt.get("latency_ms"),
                        "finish_reason": attempt.get("finish_reason"),
                        "response_preview": attempt.get("response_preview"),
                        "usage": attempt.get("usage"),
                    }
                )
                return self._finish(receipt, started)
            if attempt.get("retryable") is False and attempt.get("status_code") in {401, 403}:
                receipt.update({"status": "auth_failed", "reason": attempt.get("reason")})
                return self._finish(receipt, started)

        receipt.update({"status": "failed", "reason": "all_model_attempts_failed"})
        return self._finish(receipt, started)

    def discover_chat_models(self, cfg: NIMProbeConfig, api_key: str) -> Dict[str, Any]:
        started = time.perf_counter()
        try:
            response = self.client.get(
                cfg.base_url + "/models",
                headers=self._headers(api_key),
                timeout=min(cfg.timeout_seconds, 20.0),
            )
            body = response.json() if response.content else {}
            models = [str(item.get("id") or "") for item in body.get("data", []) if isinstance(item, dict)]
            candidates = [
                model
                for model in models
                if model
                and not any(skip in model.lower() for skip in ("embed", "rerank", "retriev", "audio", "vision"))
                and any(hint in model.lower() for hint in ("llama", "nemotron", "mistral", "qwen"))
            ]
            return {
                "status": "ok" if response.status_code < 400 else "http_error",
                "status_code": response.status_code,
                "model_count": len(models),
                "candidate_models": candidates[:12],
                "latency_ms": round((time.perf_counter() - started) * 1000, 3),
            }
        except Exception as exc:
            return {
                "status": "error",
                "reason": type(exc).__name__,
                "candidate_models": [],
                "latency_ms": round((time.perf_counter() - started) * 1000, 3),
            }

    def _complete(self, cfg: NIMProbeConfig, api_key: str, model: str, prompt: str) -> Dict[str, Any]:
        started = time.perf_counter()
        try:
            response = self.client.post(
                cfg.base_url + "/chat/completions",
                headers=self._headers(api_key),
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": "You are a concise health-check responder."},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0,
                    "max_tokens": cfg.max_tokens,
                    "stream": False,
                },
                timeout=cfg.timeout_seconds,
            )
            latency = round((time.perf_counter() - started) * 1000, 3)
            body = response.json() if response.content else {}
            if response.status_code >= 400:
                return {
                    "model": model,
                    "status": "http_error",
                    "status_code": response.status_code,
                    "reason": self._safe_error(body),
                    "retryable": response.status_code not in {401, 403},
                    "latency_ms": latency,
                }
            choice = (body.get("choices") or [{}])[0]
            message = choice.get("message") if isinstance(choice, dict) else {}
            text = str((message or {}).get("content") or "")
            return {
                "model": model,
                "status": "ok",
                "status_code": response.status_code,
                "finish_reason": choice.get("finish_reason") if isinstance(choice, dict) else None,
                "response_preview": text[:240],
                "response_sha256": "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest(),
                "usage": body.get("usage") if isinstance(body.get("usage"), dict) else {},
                "latency_ms": latency,
            }
        except Exception as exc:
            return {
                "model": model,
                "status": "error",
                "reason": type(exc).__name__,
                "retryable": True,
                "latency_ms": round((time.perf_counter() - started) * 1000, 3),
            }

    @staticmethod
    def _headers(api_key: str) -> Dict[str, str]:
        return {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    @staticmethod
    def _safe_error(body: Any) -> str:
        if not isinstance(body, dict):
            return "non_json_error"
        error = body.get("error")
        if isinstance(error, dict):
            return str(error.get("message") or error.get("code") or "provider_error")[:240]
        return str(body.get("message") or body.get("detail") or "provider_error")[:240]

    @staticmethod
    def _secret_status(api_key: str) -> Dict[str, Any]:
        return {
            "env_name": "NVIDIA_API_KEY",
            "present": bool(api_key),
            "length": len(api_key),
            "fingerprint": hashlib.sha256(api_key.encode("utf-8")).hexdigest()[:12] if api_key else "",
        }

    @staticmethod
    def _dedupe(values: Iterable[str]) -> List[str]:
        result: List[str] = []
        seen = set()
        for value in values:
            item = str(value or "").strip()
            if item and item not in seen:
                seen.add(item)
                result.append(item)
        return result

    @staticmethod
    def _finish(receipt: Dict[str, Any], started: float) -> Dict[str, Any]:
        receipt["total_latency_ms"] = round((time.perf_counter() - started) * 1000, 3)
        receipt["receipt_hash"] = "sha256:" + hashlib.sha256(
            repr(sorted(receipt.items())).encode("utf-8", errors="replace")
        ).hexdigest()
        return receipt

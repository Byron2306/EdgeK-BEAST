"""Shared planner resilience builders for local and remote model routes."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from app.kernel.agents.nim_planner_provider import NIMPlannerProvider
from app.kernel.agents.ollama_planner_provider import OllamaPlannerProvider
from app.kernel.agents.planner_provider import FallbackPlannerProvider, HeuristicPlannerProvider, StickyFallbackPlannerProvider


def _classify_timeout(provider: str, reason: str) -> str:
    lowered = str(reason or "").casefold()
    if "timeout" in lowered or "timed out" in lowered or "dampened" in lowered:
        return f"{provider}_timeout"
    return f"{provider}_instability"


def build_resilient_ollama_provider(
    *,
    primary: OllamaPlannerProvider,
    nim_fallback_enabled: bool,
    nim_kwargs: dict[str, Any] | None = None,
    sticky_after: int,
    slow_ms: float,
    on_provider_fallback: Callable[[str, str, str], None] | None = None,
    on_sticky_fallback: Callable[[str, str, str, float], None] | None = None,
) -> FallbackPlannerProvider:
    heuristic = HeuristicPlannerProvider()
    model_provider: Any = primary
    if nim_fallback_enabled:
        model_provider = FallbackPlannerProvider(
            primary,
            NIMPlannerProvider(**(nim_kwargs or {})),
            on_fallback=(
                lambda reason: on_provider_fallback("ollama", "nvidia_nim", reason)
                if on_provider_fallback is not None else None
            ),
        )
    sticky_model = StickyFallbackPlannerProvider(
        model_provider,
        heuristic,
        sticky_after=sticky_after,
        slow_latency_ms=slow_ms,
        classify_reason=lambda reason: _classify_timeout("ollama", reason),
        on_sticky=(
            lambda reason: on_sticky_fallback("ollama", "heuristic", reason, slow_ms)
            if on_sticky_fallback is not None else None
        ),
    )
    return FallbackPlannerProvider(
        heuristic,
        sticky_model,
        on_fallback=(
            lambda reason: on_provider_fallback(
                "heuristic",
                "model" if nim_fallback_enabled else "ollama",
                reason,
            )
            if on_provider_fallback is not None else None
        ),
    )


def build_resilient_nim_provider(
    *,
    primary: NIMPlannerProvider,
    sticky_after: int,
    slow_ms: float,
    on_sticky_fallback: Callable[[str, str, str, float], None] | None = None,
) -> StickyFallbackPlannerProvider:
    return StickyFallbackPlannerProvider(
        primary,
        HeuristicPlannerProvider(),
        sticky_after=sticky_after,
        slow_latency_ms=slow_ms,
        classify_reason=lambda reason: _classify_timeout("nim", reason),
        on_sticky=(
            lambda reason: on_sticky_fallback("nvidia_nim", "heuristic", reason, slow_ms)
            if on_sticky_fallback is not None else None
        ),
    )

from app.kernel.agents.planner_provider import FallbackPlannerProvider, HeuristicPlannerProvider, StickyFallbackPlannerProvider
from app.kernel.agents.planner_resilience import build_resilient_nim_provider


class _FakeNIM:
    last_route = {"provider": "nvidia_nim"}


class _FakeOllama:
    last_route = {"provider": "ollama"}


def test_resilient_nim_provider_uses_ollama_before_heuristic():
    provider = build_resilient_nim_provider(
        primary=_FakeNIM(),  # type: ignore[arg-type]
        sticky_after=2,
        slow_ms=15000,
        ollama_fallback=_FakeOllama(),  # type: ignore[arg-type]
    )
    assert isinstance(provider, StickyFallbackPlannerProvider)
    assert isinstance(provider.fallback, FallbackPlannerProvider)
    assert provider.fallback.primary is not None
    assert isinstance(provider.fallback.fallback, HeuristicPlannerProvider)


def test_resilient_nim_provider_can_skip_ollama():
    provider = build_resilient_nim_provider(
        primary=_FakeNIM(),  # type: ignore[arg-type]
        sticky_after=2,
        slow_ms=15000,
        ollama_fallback=False,
    )
    assert isinstance(provider.fallback, HeuristicPlannerProvider)

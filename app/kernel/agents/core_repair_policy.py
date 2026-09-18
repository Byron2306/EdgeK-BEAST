"""Recovery Phase 3 core planner policy.

This module owns deterministic planner lifecycle budgeting without importing
FastAPI, provider adapters or UI surfaces. Explicit operator limits remain
authoritative; defaults must be long enough to complete the mandatory clean
mutation lifecycle.
"""

from __future__ import annotations

from typing import Any


MUTATING_MODES = {"agent", "edit", "implementer"}


def planner_lifecycle_minimum(run: dict[str, Any]) -> int:
    mode = str(run.get("mode") or "").strip().lower()
    # inspect -> bind -> authoritative read -> mutate -> verify -> SourcePlan
    # -> complete, plus one bounded schema-correction turn.
    return 8 if mode in MUTATING_MODES else 3


def planner_turn_budget(run: dict[str, Any], request_payload: dict[str, Any] | None = None) -> dict[str, Any]:
    request_payload = request_payload if isinstance(request_payload, dict) else {}
    raw_budget = run.get("budget") if isinstance(run.get("budget"), dict) else {}
    requested = raw_budget.get("max_turns")
    source = "run_budget"
    if requested is None:
        requested = request_payload.get("max_turns")
        source = "request"

    provider = str(run.get("provider") or "").strip().lower()
    mode = str(run.get("mode") or "").strip().lower()
    minimum = planner_lifecycle_minimum(run)

    if requested is not None:
        effective = max(1, min(int(requested), 64))
        defaulted = False
    elif provider in {"ollama", "local_ollama"} and mode in MUTATING_MODES:
        effective = 12
        source = "local_mutation_default"
        defaulted = True
    elif mode in MUTATING_MODES:
        effective = 10
        source = "mutation_default"
        defaulted = True
    else:
        effective = 8
        source = "analysis_default"
        defaulted = True

    return {
        "requested": int(requested) if requested is not None else None,
        "effective": effective,
        "lifecycle_minimum": minimum,
        "below_lifecycle_minimum": effective < minimum,
        "source": source,
        "defaulted": defaulted,
    }

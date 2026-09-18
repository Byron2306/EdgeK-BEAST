"""Phase 3 policy-profile budgets for durable BEAST AgentRuns.

The run record already owns a durable budget object. This module interprets
that object as policy without creating a competing store, derives usage from the
hash-chained AgentRun event ledger, and returns deterministic receipts before a
model/tool action may consume more budget.
"""

from __future__ import annotations

import hashlib
import json
import time
from typing import Any

from app.kernel.agents.tool_models import ToolEffect, ToolSpec


class RunBudgetExceeded(RuntimeError):
    """Raised when a requested action would exceed a declared run budget."""

    def __init__(self, receipt: dict[str, Any]):
        self.receipt = dict(receipt)
        violations = self.receipt.get("violations") if isinstance(self.receipt.get("violations"), list) else []
        message = "; ".join(str(item.get("reason") or "") for item in violations if isinstance(item, dict))
        super().__init__(message or "AgentRun budget exhausted")


PROFILE_LIMITS: dict[str, dict[str, float]] = {
    "compact": {
        "max_model_turns": 8,
        "max_tool_calls": 24,
        "max_mutating_tool_calls": 8,
        "max_verification_cycles": 3,
        "max_files_changed": 12,
        "max_lines_changed": 800,
        "max_wall_seconds": 900,
        "max_input_tokens": 60000,
        "max_output_tokens": 12000,
        "max_cloud_cost": 1.0,
        "max_parallel_subagents": 1,
    },
    "balanced": {
        "max_model_turns": 24,
        "max_tool_calls": 60,
        "max_mutating_tool_calls": 20,
        "max_verification_cycles": 5,
        "max_files_changed": 20,
        "max_lines_changed": 2000,
        "max_wall_seconds": 1800,
        "max_input_tokens": 180000,
        "max_output_tokens": 40000,
        "max_cloud_cost": 5.0,
        "max_parallel_subagents": 3,
    },
    "extended": {
        "max_model_turns": 48,
        "max_tool_calls": 120,
        "max_mutating_tool_calls": 40,
        "max_verification_cycles": 8,
        "max_files_changed": 40,
        "max_lines_changed": 5000,
        "max_wall_seconds": 3600,
        "max_input_tokens": 360000,
        "max_output_tokens": 80000,
        "max_cloud_cost": 10.0,
        "max_parallel_subagents": 5,
    },
}

_LIMIT_BOUNDS: dict[str, tuple[float, float]] = {
    "max_model_turns": (1, 64),
    "max_tool_calls": (1, 500),
    "max_mutating_tool_calls": (0, 200),
    "max_verification_cycles": (0, 32),
    "max_files_changed": (1, 500),
    "max_lines_changed": (1, 100000),
    "max_wall_seconds": (10, 86400),
    "max_input_tokens": (1, 5000000),
    "max_output_tokens": (1, 1000000),
    "max_cloud_cost": (0, 10000),
    "max_parallel_subagents": (0, 32),
}

_ALIASES = {"max_turns": "max_model_turns"}


def _bounded_limit(name: str, value: Any, fallback: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return float(fallback)
    lower, upper = _LIMIT_BOUNDS[name]
    return max(lower, min(parsed, upper))


def resolve_budget_policy(run: dict[str, Any]) -> dict[str, Any]:
    raw = run.get("budget") if isinstance(run.get("budget"), dict) else {}
    requested_profile = str(raw.get("policy_profile") or raw.get("profile") or "balanced").strip().lower()
    profile = requested_profile if requested_profile in PROFILE_LIMITS else "balanced"
    limits = dict(PROFILE_LIMITS[profile])
    nested = raw.get("limits") if isinstance(raw.get("limits"), dict) else {}
    overrides = {**nested}
    for key in _LIMIT_BOUNDS:
        if key in raw:
            overrides[key] = raw[key]
    for alias, canonical in _ALIASES.items():
        if alias in raw and canonical not in overrides:
            overrides[canonical] = raw[alias]
    for name, fallback in list(limits.items()):
        if name in overrides:
            limits[name] = _bounded_limit(name, overrides[name], fallback)
    for name in limits:
        if name != "max_cloud_cost":
            limits[name] = int(limits[name])
    return {
        "beast_object_type": "agent_run_budget_policy",
        "version": "1.0",
        "profile": profile,
        "requested_profile": requested_profile,
        "limits": limits,
    }


def _line_units(arguments: dict[str, Any], tool_id: str) -> int:
    if tool_id == "worktree.write_file":
        content = str(arguments.get("content") or "")
        return max(1, len(content.splitlines())) if content else 0
    if tool_id == "worktree.replace_exact":
        old_text = str(arguments.get("old_text") or "")
        new_text = str(arguments.get("new_text") or "")
        return max(len(old_text.splitlines()), len(new_text.splitlines()), 1) if old_text or new_text else 0
    return 0


def _normalized_token_value(payload: dict[str, Any], *keys: str) -> int:
    candidates = [payload]
    nested = payload.get("usage") if isinstance(payload.get("usage"), dict) else {}
    if nested:
        candidates.append(nested)
    for source in candidates:
        for key in keys:
            value = source.get(key)
            try:
                if value is not None:
                    return max(0, int(value))
            except (TypeError, ValueError):
                continue
    return 0


def _normalized_cost_value(payload: dict[str, Any]) -> float:
    candidates = [payload]
    nested = payload.get("usage") if isinstance(payload.get("usage"), dict) else {}
    if nested:
        candidates.append(nested)
    for source in candidates:
        for key in ("cloud_cost", "cloud_cost_usd", "cost_usd", "estimated_cost_usd", "cost"):
            value = source.get(key)
            try:
                if value is not None:
                    return max(0.0, float(value))
            except (TypeError, ValueError):
                continue
    return 0.0


def normalized_model_usage(provider_usage: dict[str, Any] | None) -> dict[str, Any]:
    usage = provider_usage if isinstance(provider_usage, dict) else {}
    return {
        "input_tokens": _normalized_token_value(
            usage, "input_tokens", "prompt_tokens", "prompt_eval_count", "input_token_count"
        ),
        "output_tokens": _normalized_token_value(
            usage, "output_tokens", "completion_tokens", "completion_eval_count", "eval_count", "output_token_count"
        ),
        "cloud_cost": _normalized_cost_value(usage),
    }


def usage_from_events(run: dict[str, Any], events: list[dict[str, Any]]) -> dict[str, Any]:
    tool_calls = 0
    mutating_calls = 0
    verification_cycles = 0
    planner_turns = 0
    input_tokens = 0
    output_tokens = 0
    cloud_cost = 0.0
    changed_paths: set[str] = set()
    lines_changed = 0

    for event in events:
        event_type = str(event.get("event_type") or "")
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        if event_type == "agent.planner.turn.started":
            planner_turns += 1
        elif event_type == "agent.model.usage":
            input_tokens += _normalized_token_value(payload, "input_tokens", "prompt_tokens", "prompt_eval_count")
            output_tokens += _normalized_token_value(payload, "output_tokens", "completion_tokens", "completion_eval_count", "eval_count")
            cloud_cost += _normalized_cost_value(payload)
        elif event_type == "agent.tool.started":
            tool_calls += 1
            tool_id = str(payload.get("tool_id") or "")
            arguments = payload.get("arguments") if isinstance(payload.get("arguments"), dict) else {}
            authority = payload.get("authority_receipt") if isinstance(payload.get("authority_receipt"), dict) else {}
            authority_class = str(authority.get("authority_class") or "")
            effect = str(payload.get("effect") or "")
            if authority_class == "C_ISOLATED_MUTATION" or effect == ToolEffect.ISOLATED_MUTATION.value:
                mutating_calls += 1
                path = str(arguments.get("path") or "").strip()
                if path:
                    changed_paths.add(path)
                lines_changed += _line_units(arguments, tool_id)
            if tool_id == "worktree.verify":
                verification_cycles += 1

    created_at = float(run.get("created_at") or time.time())
    return {
        "model_turns": planner_turns,
        "tool_calls": tool_calls,
        "mutating_tool_calls": mutating_calls,
        "verification_cycles": verification_cycles,
        "files_changed": len(changed_paths),
        "changed_paths": sorted(changed_paths),
        "lines_changed": lines_changed,
        "wall_seconds": max(0.0, time.time() - created_at),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cloud_cost": round(cloud_cost, 8),
    }


def _violation(metric: str, used: float, requested: float, limit: float) -> dict[str, Any]:
    return {
        "metric": metric,
        "used": used,
        "requested": requested,
        "projected": used + requested,
        "limit": limit,
        "reason": f"{metric} budget would be exceeded: projected {used + requested:g} > limit {limit:g}",
    }


def _receipt(
    run: dict[str, Any],
    *,
    action: str,
    usage: dict[str, Any],
    policy: dict[str, Any],
    prospective: dict[str, float] | None = None,
) -> dict[str, Any]:
    prospective = dict(prospective or {})
    limits = policy["limits"]
    metric_map = {
        "model_turns": "max_model_turns",
        "tool_calls": "max_tool_calls",
        "mutating_tool_calls": "max_mutating_tool_calls",
        "verification_cycles": "max_verification_cycles",
        "files_changed": "max_files_changed",
        "lines_changed": "max_lines_changed",
        "wall_seconds": "max_wall_seconds",
        "input_tokens": "max_input_tokens",
        "output_tokens": "max_output_tokens",
        "cloud_cost": "max_cloud_cost",
    }
    violations: list[dict[str, Any]] = []
    for metric, limit_name in metric_map.items():
        requested = float(prospective.get(metric) or 0)
        used = float(usage.get(metric) or 0)
        limit = float(limits[limit_name])
        if used + requested > limit:
            violations.append(_violation(metric, used, requested, limit))

    body = {
        "run_id": str(run.get("run_id") or ""),
        "action": action,
        "profile": policy["profile"],
        "limits": limits,
        "usage": usage,
        "prospective": prospective,
        "allowed": not violations,
        "violations": violations,
    }
    digest = hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()
    return {
        "beast_object_type": "agent_run_budget_receipt",
        "version": "1.0",
        "receipt_id": f"budget_{digest[:20]}",
        "receipt_hash": f"sha256:{digest}",
        "issued_at": time.time(),
        **body,
    }


def budget_snapshot(run: dict[str, Any], events: list[dict[str, Any]]) -> dict[str, Any]:
    policy = resolve_budget_policy(run)
    usage = usage_from_events(run, events)
    return _receipt(run, action="snapshot", usage=usage, policy=policy)


def planner_turn_receipt(run: dict[str, Any], events: list[dict[str, Any]]) -> dict[str, Any]:
    policy = resolve_budget_policy(run)
    usage = usage_from_events(run, events)
    return _receipt(run, action="planner_turn", usage=usage, policy=policy, prospective={"model_turns": 1})


def tool_budget_receipt(
    run: dict[str, Any],
    events: list[dict[str, Any]],
    spec: ToolSpec,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    policy = resolve_budget_policy(run)
    usage = usage_from_events(run, events)
    prospective: dict[str, float] = {"tool_calls": 1}
    if spec.effect is ToolEffect.ISOLATED_MUTATION:
        prospective["mutating_tool_calls"] = 1
        path = str(arguments.get("path") or "").strip()
        if path and path not in set(usage.get("changed_paths") or []):
            prospective["files_changed"] = 1
        prospective["lines_changed"] = _line_units(arguments, spec.tool_id)
    if spec.tool_id == "worktree.verify":
        prospective["verification_cycles"] = 1
    return _receipt(
        run,
        action=f"tool:{spec.tool_id}",
        usage=usage,
        policy=policy,
        prospective=prospective,
    )


def post_model_usage_receipt(run: dict[str, Any], events: list[dict[str, Any]]) -> dict[str, Any]:
    policy = resolve_budget_policy(run)
    usage = usage_from_events(run, events)
    return _receipt(run, action="post_model_usage", usage=usage, policy=policy)


def planner_turn_limit(run: dict[str, Any], requested: int) -> int:
    policy = resolve_budget_policy(run)
    return max(1, min(int(requested), int(policy["limits"]["max_model_turns"])))

"""Provider-neutral next-action adapters for the BEAST planner loop."""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Protocol

from app.kernel.agents.planner_models import PlannerDecision, PlannerDecisionType
from app.kernel.agents.provider_quality import ProviderQualityLedger
from app.kernel.agents.verification_planner import MUTATION_TOOLS, plan_verification


class PlannerProvider(Protocol):
    async def next_decision(self, prompt: str, *, run: dict[str, Any], turn: int) -> PlannerDecision: ...


class PlannerDecisionError(ValueError):
    pass


def parse_planner_decision(value: Any) -> PlannerDecision:
    if isinstance(value, PlannerDecision):
        return value
    payload = value
    if isinstance(value, str):
        text = value.strip()
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not match:
            raise PlannerDecisionError("planner response did not contain a JSON object")
        try:
            payload = json.loads(match.group(0))
        except json.JSONDecodeError as exc:
            raise PlannerDecisionError(f"invalid planner JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise PlannerDecisionError("planner decision must be an object")
    action_payload = payload.get("action") if isinstance(payload.get("action"), dict) else {}
    params_payload = payload.get("params") if isinstance(payload.get("params"), dict) else {}
    if not payload.get("decision_type") and isinstance(payload.get("action"), dict):
        action = action_payload
        payload = {
            "decision_type": "tool",
            "tool_id": action.get("tool_id") or action.get("name") or payload.get("tool_id") or "",
            "arguments": action.get("arguments") if isinstance(action.get("arguments"), dict) else payload.get("arguments") or {},
            "execution_target": action.get("execution_target") or payload.get("execution_target") or "local",
            "approval_id": action.get("approval_id") or payload.get("approval_id") or "",
            "rationale": payload.get("rationale") or payload.get("reason") or "",
        }
    raw_type = str(payload.get("decision_type") or payload.get("type") or "").strip().lower()
    function_payload = payload.get("function") if isinstance(payload.get("function"), dict) else {}
    tool_id = str(
        payload.get("tool_id")
        or payload.get("tool")
        or payload.get("name")
        or action_payload.get("tool_id")
        or action_payload.get("tool")
        or action_payload.get("name")
        or function_payload.get("name")
        or ""
    ).strip()
    if not raw_type and tool_id:
        raw_type = "tool"
    if raw_type in {"tool_call", "function_call", "call", "action", "execute", "inspect", "observe", "read"}:
        raw_type = "tool"
    if raw_type in {"finish", "final", "answer", "done"}:
        raw_type = "complete"
    if raw_type in {"refuse", "reject", "stop", "error"}:
        raw_type = "blocked"
    # Tiny models invent descriptive enum values (for example
    # ``inspect_workspace``). If the packet contains a concrete tool, prefer
    # the bounded tool contract over rejecting an otherwise usable decision.
    if raw_type not in {"tool", "complete", "blocked"} and tool_id:
        raw_type = "tool"
    if raw_type not in {"tool", "complete", "blocked"} and str(payload.get("summary") or "").strip():
        raw_type = "complete"
    try:
        decision_type = PlannerDecisionType(raw_type)
    except ValueError as exc:
        raise PlannerDecisionError("decision_type must be tool, complete, or blocked") from exc
    arguments = payload.get("arguments") if isinstance(payload.get("arguments"), dict) else payload.get("args") if isinstance(payload.get("args"), dict) else payload.get("parameters") if isinstance(payload.get("parameters"), dict) else params_payload if isinstance(params_payload, dict) else action_payload.get("arguments") if isinstance(action_payload.get("arguments"), dict) else function_payload.get("arguments") if isinstance(function_payload.get("arguments"), dict) else {}
    arguments = dict(arguments) if isinstance(arguments, dict) else {}
    if tool_id == "workspace.read_range":
        if "line_count" not in arguments and arguments.get("start_line") is not None and arguments.get("end_line") is not None:
            try:
                start = int(arguments.get("start_line"))
                end = int(arguments.get("end_line"))
            except (TypeError, ValueError):
                pass
            else:
                if end >= start:
                    arguments["line_count"] = (end - start) + 1
    if decision_type is PlannerDecisionType.TOOL and not tool_id:
        raise PlannerDecisionError("tool decisions require tool_id")
    if decision_type is not PlannerDecisionType.TOOL and tool_id:
        raise PlannerDecisionError("only tool decisions may include tool_id")
    summary = str(payload.get("summary") or "").strip()
    blocker = str(payload.get("blocker") or "").strip()
    if decision_type is PlannerDecisionType.COMPLETE and not summary:
        raise PlannerDecisionError("complete decisions require summary")
    if decision_type is PlannerDecisionType.BLOCKED and not blocker:
        raise PlannerDecisionError("blocked decisions require blocker")
    return PlannerDecision(
        decision_type=decision_type,
        rationale=str(payload.get("rationale") or "").strip(),
        tool_id=tool_id,
        arguments=arguments,
        execution_target=str(payload.get("execution_target") or "local").strip() or "local",
        approval_id=str(payload.get("approval_id") or "").strip(),
        summary=summary,
        blocker=blocker,
    )


class ScriptedPlannerProvider:
    """Deterministic adapter used for simulation, tests, and offline proofs."""

    def __init__(self, decisions: list[dict[str, Any] | PlannerDecision]):
        self._decisions = list(decisions)
        self.last_route = {"provider": "scripted", "engine": "scripted", "route_kind": "scripted", "reason": "test_script"}

    async def next_decision(self, prompt: str, *, run: dict[str, Any], turn: int) -> PlannerDecision:
        if not self._decisions:
            return PlannerDecision(
                decision_type=PlannerDecisionType.BLOCKED,
                blocker="scripted planner exhausted without completion",
            )
        return parse_planner_decision(self._decisions.pop(0))


class CallbackPlannerProvider:
    def __init__(self, callback: Callable[[str, dict[str, Any], int], Awaitable[Any]]):
        self._callback = callback
        self.last_route = {"provider": "callback", "engine": "callback", "route_kind": "callback", "reason": "callback_provider"}

    async def next_decision(self, prompt: str, *, run: dict[str, Any], turn: int) -> PlannerDecision:
        return parse_planner_decision(await self._callback(prompt, run, turn))


class FallbackPlannerProvider:
    """Switch providers after a bounded primary failure and expose the handoff."""

    def __init__(self, primary: PlannerProvider, fallback: PlannerProvider, *, on_fallback: Callable[[str], None] | None = None):
        self.primary = primary
        self.fallback = fallback
        self.on_fallback = on_fallback
        self.last_provider = "primary"
        self.last_route = {"provider": "primary", "engine": "", "route_kind": "primary", "reason": ""}

    async def next_decision(self, prompt: str, *, run: dict[str, Any], turn: int) -> PlannerDecision:
        try:
            decision = await self.primary.next_decision(prompt, run=run, turn=turn)
            self.last_provider = "primary"
            route = getattr(self.primary, "last_route", None)
            if isinstance(route, dict):
                self.last_route = dict(route)
            return decision
        except Exception as exc:
            self.last_provider = "fallback"
            if self.on_fallback is not None:
                self.on_fallback(f"{type(exc).__name__}: {exc}")
            decision = await self.fallback.next_decision(prompt, run=run, turn=turn)
            route = getattr(self.fallback, "last_route", None)
            if isinstance(route, dict):
                self.last_route = dict(route)
                self.last_route.setdefault("reason", f"{type(exc).__name__}: {exc}")
            else:
                self.last_route = {"provider": "fallback", "engine": "", "route_kind": "fallback", "reason": f"{type(exc).__name__}: {exc}"}
            return decision


@dataclass(frozen=True)
class CapabilityRoute:
    name: str
    provider: PlannerProvider
    capability_score: float = 0.5
    cost_score: float = 0.5


class CapabilityScoredPlannerProvider:
    """Route planner turns by task hardness, repair pressure, and route health."""

    def __init__(
        self,
        routes: list[CapabilityRoute | dict[str, Any]],
        *,
        hard_edit_threshold: float = 0.7,
        on_switch: Callable[[str, str, str], None] | None = None,
        quality_ledger: ProviderQualityLedger | None = None,
        task_type_resolver: Callable[[dict[str, Any]], str] | None = None,
    ) -> None:
        normalized: list[CapabilityRoute] = []
        for index, route in enumerate(routes):
            if isinstance(route, CapabilityRoute):
                normalized.append(route)
            elif isinstance(route, dict):
                provider = route.get("provider")
                if provider is None:
                    raise ValueError("capability route requires provider")
                normalized.append(CapabilityRoute(
                    name=str(route.get("name") or f"route-{index}"),
                    provider=provider,
                    capability_score=float(route.get("capability_score", 0.5)),
                    cost_score=float(route.get("cost_score", 0.5)),
                ))
            else:
                raise TypeError("routes must be CapabilityRoute or dict")
        if not normalized:
            raise ValueError("CapabilityScoredPlannerProvider requires at least one route")
        self.routes = normalized
        self.hard_edit_threshold = max(0.0, min(float(hard_edit_threshold), 1.0))
        self.on_switch = on_switch
        self.quality_ledger = quality_ledger
        self.task_type_resolver = task_type_resolver
        self.health: dict[str, float] = {route.name: 1.0 for route in self.routes}
        self.last_route = {"provider": self.routes[0].name, "engine": "", "route_kind": "capability_scored", "reason": "initial"}
        self.last_provider = self.routes[0].name

    @staticmethod
    def _planner(run: dict[str, Any]) -> dict[str, Any]:
        checkpoint = run.get("checkpoint") if isinstance(run.get("checkpoint"), dict) else {}
        return checkpoint.get("planner") if isinstance(checkpoint.get("planner"), dict) else {}

    @classmethod
    def task_hardness(cls, run: dict[str, Any]) -> float:
        request = run.get("request") if isinstance(run.get("request"), dict) else {}
        planner = cls._planner(run)
        observations = planner.get("observations") if isinstance(planner.get("observations"), list) else []
        failures = planner.get("verification_failures") if isinstance(planner.get("verification_failures"), list) else []
        semantic_risk = request.get("semantic_risk") if isinstance(request.get("semantic_risk"), dict) else {}
        objective = str(run.get("objective") or "").casefold()
        context_files = request.get("context_files") if isinstance(request.get("context_files"), list) else []
        changed_paths = {
            str((item.get("result") or {}).get("path") or "")
            for item in observations
            if isinstance(item, dict) and str(item.get("tool_id") or "") in MUTATION_TOOLS and isinstance(item.get("result"), dict)
        }
        score = 0.15
        if bool(semantic_risk.get("high")):
            score += 0.34
        try:
            score += min(0.25, max(0.0, float(semantic_risk.get("score") or 0.0)) * 0.05)
        except (TypeError, ValueError):
            pass
        if len(context_files) >= 4 or len(changed_paths) >= 3:
            score += 0.25
        if any(term in objective for term in ("large", "architecture", "monorepo", "cross-cutting", "ambiguous", "refactor", "hard patch", "complex patch", "many files", "deep repair", "debug failing tests")):
            score += 0.25
        if int(planner.get("repair_cycles") or 0) > 0:
            score += min(0.25, 0.12 * int(planner.get("repair_cycles") or 0))
        if failures:
            latest = failures[-1] if isinstance(failures[-1], dict) else {}
            analysis = latest.get("analysis") if isinstance(latest.get("analysis"), dict) else {}
            if str(analysis.get("failure_class") or "") in {"logic_regression", "unknown", "dependency_missing", "bad_patch"}:
                score += 0.2
            if not bool(analysis.get("retryable_without_code_change")):
                score += 0.1
        route_failures = [
            item for item in observations[-8:]
            if isinstance(item, dict) and str(item.get("status") or "") == "failed"
        ]
        if len(route_failures) >= 2:
            score += 0.15
        return max(0.0, min(score, 1.0))

    def _task_type(self, run: dict[str, Any]) -> str:
        if callable(self.task_type_resolver):
            try:
                return str(self.task_type_resolver(run) or "general")
            except Exception:
                return "general"
        return ProviderQualityLedger.task_type(run)

    @classmethod
    def _latest_failure(cls, run: dict[str, Any]) -> dict[str, Any]:
        checkpoint = run.get("checkpoint") if isinstance(run.get("checkpoint"), dict) else {}
        planner = checkpoint.get("planner") if isinstance(checkpoint.get("planner"), dict) else {}
        failures = planner.get("verification_failures") if isinstance(planner.get("verification_failures"), list) else []
        latest = failures[-1] if failures and isinstance(failures[-1], dict) else {}
        return dict(latest) if latest else {}

    @classmethod
    def _failure_pressure(cls, run: dict[str, Any]) -> dict[str, Any]:
        latest = cls._latest_failure(run)
        analysis = latest.get("analysis") if isinstance(latest.get("analysis"), dict) else {}
        failure_class = str(analysis.get("failure_class") or "")
        escalation_hint = str(analysis.get("escalation_hint") or "")
        execution_target = str(latest.get("execution_target") or "")
        target_execution = str(latest.get("target_execution") or "")
        repair_cycle = max(0, int(latest.get("repair_cycle") or 0))
        hard_failure = failure_class in {"logic_regression", "unknown", "dependency_missing", "bad_patch"}
        remote_failure = execution_target in {"ssh", "container", "devcontainer"} or target_execution.startswith("remote_")
        strong_route_recommended = escalation_hint == "stronger_model_recommended" or (hard_failure and repair_cycle > 0)
        return {
            "failure_class": failure_class,
            "escalation_hint": escalation_hint,
            "execution_target": execution_target,
            "target_execution": target_execution,
            "repair_cycle": repair_cycle,
            "hard_failure": hard_failure,
            "remote_failure": remote_failure,
            "strong_route_recommended": strong_route_recommended,
        }

    def _ranked_routes(self, run: dict[str, Any]) -> list[tuple[float, CapabilityRoute]]:
        hardness = self.task_hardness(run)
        task_type = self._task_type(run)
        failure_pressure = self._failure_pressure(run)
        ranked: list[tuple[float, CapabilityRoute]] = []
        for route in self.routes:
            health = self.health.get(route.name, 1.0)
            quality = self.quality_ledger.score(route.name, task_type) if self.quality_ledger is not None else 0.5
            # Easy turns bias toward cheap/fast routes; hard turns bias toward capability.
            if hardness >= self.hard_edit_threshold:
                score = (route.capability_score * 0.58) + (quality * 0.22) + (health * 0.17) + (route.cost_score * 0.03)
            else:
                score = (route.cost_score * 0.36) + (quality * 0.24) + (health * 0.25) + (route.capability_score * 0.15)
            if failure_pressure["strong_route_recommended"]:
                score += route.capability_score * (0.14 if failure_pressure["remote_failure"] else 0.1)
                score -= route.cost_score * 0.08
            if failure_pressure["hard_failure"] and route.capability_score < 0.55:
                score -= 0.12 if failure_pressure["remote_failure"] else 0.08
            if failure_pressure["repair_cycle"] >= 2 and route.capability_score < 0.7:
                score -= 0.08
            ranked.append((score, route))
        return sorted(ranked, key=lambda item: item[0], reverse=True)

    async def next_decision(self, prompt: str, *, run: dict[str, Any], turn: int) -> PlannerDecision:
        errors: list[str] = []
        ranked = self._ranked_routes(run)
        previous = self.last_provider
        task_type = self._task_type(run)
        failure_pressure = self._failure_pressure(run)
        for _score, route in ranked:
            started = time.perf_counter()
            try:
                decision = await route.provider.next_decision(prompt, run=run, turn=turn)
                usage = getattr(route.provider, "last_usage", None)
                latency_ms = usage.get("latency_ms") if isinstance(usage, dict) else (time.perf_counter() - started) * 1000.0
                quality_score = self.quality_ledger.score(route.name, task_type) if self.quality_ledger is not None else 0.5
                if self.quality_ledger is not None:
                    self.quality_ledger.record(route.name, task_type, ok=True, latency_ms=latency_ms)
                self.health[route.name] = min(1.0, self.health.get(route.name, 1.0) + 0.08)
                inner = getattr(route.provider, "last_route", None)
                reason = "hard_edit_escalation" if self.task_hardness(run) >= self.hard_edit_threshold else "capability_score"
                self.last_route = {
                    **(dict(inner) if isinstance(inner, dict) else {}),
                    "provider": route.name,
                    "engine": str((inner or {}).get("engine") if isinstance(inner, dict) else route.name),
                    "route_kind": "capability_scored",
                    "reason": "failure_pressure_escalation" if failure_pressure["strong_route_recommended"] else reason,
                    "capability_score": route.capability_score,
                    "quality_score": quality_score,
                    "route_health": self.health[route.name],
                    "task_hardness": self.task_hardness(run),
                    "task_type": task_type,
                    "failure_pressure": failure_pressure,
                }
                self.last_provider = route.name
                if previous != route.name and self.on_switch is not None:
                    self.on_switch(previous, route.name, reason)
                return decision
            except Exception as exc:
                reason = f"{type(exc).__name__}: {exc}"
                errors.append(f"{route.name}: {reason}")
                self.health[route.name] = max(0.0, self.health.get(route.name, 1.0) - 0.35)
                if self.quality_ledger is not None:
                    failure_class = "timeout" if isinstance(exc, TimeoutError) or "timeout" in reason.casefold() else "provider_error"
                    self.quality_ledger.record(
                        route.name,
                        task_type,
                        ok=False,
                        latency_ms=(time.perf_counter() - started) * 1000.0,
                        failure_class=failure_class,
                        reason=reason,
                    )
        raise PlannerDecisionError("all capability-scored planner routes failed: " + " | ".join(errors))


class HeuristicPlannerProvider:
    """Low-latency deterministic fast-path for obvious bounded planner turns."""

    _MUTATION_TOOLS = MUTATION_TOOLS

    def __init__(self) -> None:
        self.last_route = {"provider": "heuristic", "engine": "deterministic", "route_kind": "heuristic", "reason": "deterministic_fast_path"}

    @staticmethod
    def _tool_ids(run: dict[str, Any]) -> list[str]:
        checkpoint = run.get("checkpoint") if isinstance(run.get("checkpoint"), dict) else {}
        planner = checkpoint.get("planner") if isinstance(checkpoint.get("planner"), dict) else {}
        observations = planner.get("observations") if isinstance(planner.get("observations"), list) else []
        return [
            str(item.get("tool_id") or "")
            for item in observations
            if isinstance(item, dict) and str(item.get("tool_id") or "")
        ]

    @classmethod
    def _latest_status(cls, run: dict[str, Any], tool_id: str) -> str:
        checkpoint = run.get("checkpoint") if isinstance(run.get("checkpoint"), dict) else {}
        planner = checkpoint.get("planner") if isinstance(checkpoint.get("planner"), dict) else {}
        observations = planner.get("observations") if isinstance(planner.get("observations"), list) else []
        for item in reversed(observations):
            if isinstance(item, dict) and str(item.get("tool_id") or "") == tool_id:
                return str(item.get("status") or "")
        return ""

    @classmethod
    def _latest_failure_analysis(cls, run: dict[str, Any]) -> dict[str, Any]:
        checkpoint = run.get("checkpoint") if isinstance(run.get("checkpoint"), dict) else {}
        planner = checkpoint.get("planner") if isinstance(checkpoint.get("planner"), dict) else {}
        failures = planner.get("verification_failures") if isinstance(planner.get("verification_failures"), list) else []
        if not failures:
            return {}
        latest = failures[-1] if isinstance(failures[-1], dict) else {}
        analysis = latest.get("analysis") if isinstance(latest.get("analysis"), dict) else {}
        return analysis

    @classmethod
    def _default_verify_command(cls, run: dict[str, Any]) -> list[str] | None:
        command = plan_verification(run).get("command")
        return command if isinstance(command, list) and command else None

    async def next_decision(self, prompt: str, *, run: dict[str, Any], turn: int) -> PlannerDecision:
        mode = str(run.get("mode") or "").strip().lower()
        if mode not in {"agent", "edit", "implementer"}:
            raise PlannerDecisionError("heuristic planner unavailable for non-mutating mode")
        observed = self._tool_ids(run)
        approvals = run.get("approvals") if isinstance(run.get("approvals"), list) else []
        if not observed:
            return PlannerDecision(
                decision_type=PlannerDecisionType.TOOL,
                tool_id="workspace.index",
                arguments={"limit": 1200, "include_symbols": True},
                rationale="Fast-path first bounded workspace index.",
            )
        if "worktree.bind" not in observed:
            return PlannerDecision(
                decision_type=PlannerDecisionType.TOOL,
                tool_id="worktree.bind",
                arguments={"objective": str(run.get("objective") or "Bounded agent implementation"), "provider": str(run.get("provider") or ""), "risk": "high"},
                rationale="Fast-path isolated worktree bind before mutation.",
            )
        if any(tool in observed for tool in self._MUTATION_TOOLS):
            verify_status = self._latest_status(run, "worktree.verify")
            if verify_status != "completed":
                analysis = self._latest_failure_analysis(run)
                if verify_status == "failed" and analysis and not bool(analysis.get("retryable_without_code_change")):
                    raise PlannerDecisionError("heuristic planner defers code-repair verifier failures to a model route")
                command = self._default_verify_command(run)
                if command:
                    return PlannerDecision(
                        decision_type=PlannerDecisionType.TOOL,
                        tool_id="worktree.verify",
                        arguments={"command": command},
                        rationale="Fast-path verifier after bounded mutation.",
                    )
            if "worktree.sourceplan_draft" not in observed and verify_status == "completed":
                return PlannerDecision(
                    decision_type=PlannerDecisionType.TOOL,
                    tool_id="worktree.sourceplan_draft",
                    arguments={},
                    rationale="Fast-path SourcePlan handoff after successful verification.",
                )
            if "worktree.sourceplan_draft" in observed and verify_status == "completed":
                return PlannerDecision(
                    decision_type=PlannerDecisionType.COMPLETE,
                    arguments={},
                    summary="Deterministic worktree mutation, verification, and SourcePlan handoff completed.",
                    rationale="Fast-path completion after verified SourcePlan handoff.",
                )
        return PlannerDecision(
            decision_type=PlannerDecisionType.BLOCKED,
            arguments={},
            blocker="Heuristic fallback found no further deterministic step; stronger planner route required.",
            rationale="Deterministic fallback exhausted bounded safe actions.",
        )


class StickyFallbackPlannerProvider:
    """Switch to fallback permanently after repeated primary instability."""

    def __init__(
        self,
        primary: PlannerProvider,
        fallback: PlannerProvider,
        *,
        sticky_after: int = 2,
        slow_latency_ms: float = 15000.0,
        classify_reason: Callable[[str], str] | None = None,
        on_sticky: Callable[[str], None] | None = None,
    ) -> None:
        self.primary = primary
        self.fallback = fallback
        self.sticky_after = max(1, int(sticky_after))
        self.slow_latency_ms = max(250.0, float(slow_latency_ms))
        self.classify_reason = classify_reason
        self.on_sticky = on_sticky
        self.primary_failures = 0
        self.force_fallback = False
        self.last_route = {"provider": "primary", "engine": "", "route_kind": "primary", "reason": ""}

    async def next_decision(self, prompt: str, *, run: dict[str, Any], turn: int) -> PlannerDecision:
        if self.force_fallback:
            decision = await self.fallback.next_decision(prompt, run=run, turn=turn)
            route = getattr(self.fallback, "last_route", None)
            if isinstance(route, dict):
                self.last_route = {**dict(route), "route_kind": "sticky_fallback", "reason": "run_scoped_sticky_fallback"}
            else:
                self.last_route = {"provider": "fallback", "engine": "", "route_kind": "sticky_fallback", "reason": "run_scoped_sticky_fallback"}
            return decision
        try:
            decision = await self.primary.next_decision(prompt, run=run, turn=turn)
            route = getattr(self.primary, "last_route", None)
            if isinstance(route, dict):
                self.last_route = dict(route)
            latency_ms = getattr(self.primary, "last_usage", {}).get("latency_ms") if isinstance(getattr(self.primary, "last_usage", None), dict) else None
            if isinstance(latency_ms, (int, float)) and latency_ms >= self.slow_latency_ms:
                self.primary_failures += 1
            else:
                self.primary_failures = 0
            if self.primary_failures >= self.sticky_after:
                self.force_fallback = True
                if self.on_sticky is not None:
                    self.on_sticky("primary_latency_budget_exhausted")
            return decision
        except Exception as exc:
            reason = f"{type(exc).__name__}: {exc}"
            classifier = self.classify_reason(reason) if callable(self.classify_reason) else reason
            self.primary_failures += 1
            if self.primary_failures >= self.sticky_after:
                self.force_fallback = True
                if self.on_sticky is not None:
                    self.on_sticky(classifier)
            mode = str(run.get("mode") or "").strip().lower()
            if isinstance(self.fallback, HeuristicPlannerProvider) and mode not in {"agent", "edit", "implementer"}:
                self.last_route = {
                    "provider": "primary",
                    "engine": "",
                    "route_kind": "fallback_unavailable",
                    "reason": classifier,
                }
                raise
            decision = await self.fallback.next_decision(prompt, run=run, turn=turn)
            route = getattr(self.fallback, "last_route", None)
            if isinstance(route, dict):
                self.last_route = {**dict(route), "route_kind": "fallback", "reason": classifier}
            else:
                self.last_route = {"provider": "fallback", "engine": "", "route_kind": "fallback", "reason": classifier}
            return decision

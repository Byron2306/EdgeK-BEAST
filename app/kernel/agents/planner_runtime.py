"""Durable bounded model -> tool -> observation loop for BEAST AgentRuns."""

from __future__ import annotations

import asyncio
import json
import os
import uuid
from dataclasses import replace
from typing import Any

from app.kernel.agents.failure_analyst import analyze_failure
from app.kernel.agents.planning_integrations import PlanningIntegrationRuntime
from app.kernel.agents.planner_models import PlannerDecision, PlannerDecisionType, PlannerState
from app.kernel.agents.planner_provider import HeuristicPlannerProvider, PlannerDecisionError, PlannerProvider, parse_planner_decision
from app.kernel.agents.run_state import AgentRunState, TERMINAL_STATES, normalize_state
from app.kernel.agents.semantic_context import semantic_context_contract
from app.kernel.agents.tool_runtime import ToolExecutionFailed
from app.kernel.agents.verification_planner import plan_verification


class PlannerBudgetExhausted(RuntimeError):
    pass


class AgentPlannerRuntime:
    def __init__(self, engine: Any, provider: PlannerProvider, *, max_turns: int = 8, observation_limit: int = 12, max_repair_cycles: int = 3, context_packet_builder: Any = None, execution_gateway: Any = None, compute_governor: Any = None):
        self.engine = engine
        self.provider = provider
        self.max_turns = max(1, min(int(max_turns), 64))
        self.observation_limit = max(1, min(int(observation_limit), 50))
        self.max_repair_cycles = max(0, min(int(max_repair_cycles), 16))
        self.context_packet_builder = context_packet_builder
        self.execution_gateway = execution_gateway
        self.compute_governor = compute_governor
        self._context_cache: dict[str, Any] = {}
        self.planning_integrations = PlanningIntegrationRuntime(str(engine.workspace_root))

    @staticmethod
    def _is_local_ollama_provider(run: dict[str, Any]) -> bool:
        provider = str(run.get("provider") or "").strip().lower()
        return provider in {"ollama", "local_ollama"}

    @staticmethod
    def _is_compact_planner_provider(run: dict[str, Any]) -> bool:
        provider = str(run.get("provider") or "").strip().lower()
        return provider in {"ollama", "local_ollama", "nvidia_nim", "nim", "local_nim"}

    def _checkpoint(self, run_id: str) -> dict[str, Any]:
        run = self.engine.store.get_run(run_id) or {}
        checkpoint = run.get("checkpoint") if isinstance(run.get("checkpoint"), dict) else {}
        return dict(checkpoint)

    @staticmethod
    def _execution_target_payload(run: dict[str, Any], target: str) -> dict[str, Any]:
        request = run.get("request") if isinstance(run.get("request"), dict) else {}
        payload = request.get("execution_target_payload")
        if not isinstance(payload, dict):
            return {}
        normalized_target = str(target or "local").strip().lower() or "local"
        payload_target = str(payload.get("kind") or payload.get("target_kind") or request.get("execution_target") or "").strip().lower()
        if payload_target and payload_target != normalized_target:
            return {}
        return dict(payload)

    def _active_plan_step_id(self, run_id: str, tool_id: str = "") -> str:
        current = self.planning_integrations.objective_plan.current(run_id)
        plan = current.get("plan") if isinstance(current.get("plan"), dict) else {}
        active_step_id = str(plan.get("active_step_id") or "").strip()
        if active_step_id:
            return active_step_id
        return self.planning_integrations._telemetry_step_id(str(tool_id or ""), active_step_id)

    @staticmethod
    def _decision_timeout_seconds(run: dict[str, Any]) -> float:
        request = run.get("request") if isinstance(run.get("request"), dict) else {}
        planner = request.get("planner") if isinstance(request.get("planner"), dict) else {}
        raw = (
            planner.get("decision_timeout_ms")
            or request.get("decision_timeout_ms")
            or request.get("planner_decision_timeout_ms")
            or 0
        )
        try:
            timeout_ms = float(raw or 0)
        except (TypeError, ValueError):
            timeout_ms = 0.0
        if timeout_ms <= 0:
            import os
            timeout_ms = float(os.environ.get("BEAST_AGENT_PLANNER_DECISION_TIMEOUT_MS", "45000"))
        return max(3.0, min(timeout_ms / 1000.0, 180.0))

    @staticmethod
    def _heuristic_continuation_allowed(run: dict[str, Any]) -> bool:
        mode = str(run.get("mode") or "").strip().lower()
        provider = str(run.get("provider") or "").strip().lower()
        return mode in {"agent", "edit", "implementer"} and provider in {"ollama", "local_ollama", "nvidia_nim", "nim", "local_nim"}

    @staticmethod
    def _strong_reentry_allowed(run: dict[str, Any], state: PlannerState) -> bool:
        mode = str(run.get("mode") or "").strip().lower()
        provider = str(run.get("provider") or "").strip().lower()
        if mode not in {"agent", "edit", "implementer"}:
            return False
        if provider not in {"nvidia_nim", "nim", "local_nim", "ollama", "local_ollama"}:
            return False
        return bool(state.repair_cycles > 0 or state.verification_failures or state.turn >= 2)

    @staticmethod
    def _compact_retry_prompt(prompt: str) -> str:
        contract = (
            "\n\nRETRY MODE: Return one valid planner JSON object only. "
            "Prefer continuing the current mutation or repair path. "
            "Do not repeat prior invalid schema. Keep arguments minimal and exact."
        )
        budget = 2200
        if len(prompt) <= budget:
            return prompt + contract
        return prompt[-budget:] + contract

    @staticmethod
    def _partial_structured_decision(run: dict[str, Any], partial_text: str) -> PlannerDecision | None:
        text = str(partial_text or "").strip()
        if not text:
            return None
        try:
            decision = parse_planner_decision(text)
        except PlannerDecisionError:
            return None
        except Exception:
            return None
        mode = str(run.get("mode") or "").strip().lower()
        if mode in {"agent", "edit", "implementer"} and decision.decision_type is PlannerDecisionType.COMPLETE:
            return None
        return decision

    @classmethod
    def _provider_partial_text(cls, provider: Any, *, _seen: set[int] | None = None) -> str:
        seen = _seen or set()
        if provider is None:
            return ""
        marker = id(provider)
        if marker in seen:
            return ""
        seen.add(marker)
        text = str(getattr(provider, "last_partial_text", "") or "").strip()
        if text:
            return text
        for attr in ("primary", "fallback", "provider"):
            nested = getattr(provider, attr, None)
            nested_text = cls._provider_partial_text(nested, _seen=seen)
            if nested_text:
                return nested_text
        return ""

    def _recent_model_delta_text(self, run_id: str, *, limit: int = 12) -> str:
        try:
            events = self.engine.store.events(run_id, limit=limit)
        except Exception:
            return ""
        chunks: list[str] = []
        for event in reversed(events):
            if str(event.get("event_type") or "") != "agent.model.delta":
                if chunks:
                    break
                continue
            payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
            text = str(payload.get("text") or "").strip()
            if text:
                chunks.append(text)
        return "".join(chunks).strip()

    @classmethod
    def _salvage_partial_decision_from_provider(
        cls,
        run: dict[str, Any],
        provider: Any,
        partial_text: str = "",
        decision: PlannerDecision | None = None,
    ) -> PlannerDecision | None:
        partial_text = str(partial_text or "").strip() or cls._provider_partial_text(provider)
        if not partial_text:
            return None
        salvaged = cls._partial_structured_decision(run, partial_text)
        if salvaged is None:
            return None
        if (
            isinstance(decision, PlannerDecision)
            and decision.decision_type is PlannerDecisionType.BLOCKED
            and salvaged.decision_type is not PlannerDecisionType.BLOCKED
        ):
            return salvaged
        if decision is None:
            return salvaged
        return None

    @classmethod
    def _primary_retry_provider(cls, provider: Any, *, _seen: set[int] | None = None) -> Any:
        seen = _seen or set()
        if provider is None:
            return None
        marker = id(provider)
        if marker in seen:
            return provider
        seen.add(marker)
        primary = getattr(provider, "primary", None)
        if primary is not None:
            return cls._primary_retry_provider(primary, _seen=seen)
        return provider

    @staticmethod
    def _invalid_mutation_reason(decision: PlannerDecision) -> str:
        if decision.decision_type is not PlannerDecisionType.TOOL:
            return ""
        if decision.tool_id == "worktree.replace_exact":
            path = str(decision.arguments.get("path") or "").strip()
            old_text = str(decision.arguments.get("old_text") or "")
            new_text = str(decision.arguments.get("new_text") or "")
            if not path:
                return "replace_exact requires a target path."
            if old_text == "" and new_text == "":
                return "replace_exact requires exact old_text and new_text; empty placeholders are not allowed."
            if old_text == new_text:
                return "replace_exact requires a real bounded change; old_text and new_text cannot be identical."
        if decision.tool_id == "worktree.write_file":
            path = str(decision.arguments.get("path") or "").strip()
            content = str(decision.arguments.get("content") or "")
            if not path:
                return "write_file requires a target path."
            if content == "":
                return "write_file requires non-empty content."
        return ""

    @classmethod
    def _inspected_paths(cls, state: PlannerState) -> set[str]:
        paths: set[str] = set()
        for item in state.observations:
            if not isinstance(item, dict):
                continue
            if str(item.get("status") or "") != "completed":
                continue
            if str(item.get("tool_id") or "") != "workspace.read_range":
                continue
            result = item.get("result") if isinstance(item.get("result"), dict) else {}
            path = str(result.get("path") or "").strip()
            if path:
                paths.add(path)
        return paths

    @classmethod
    def _invalid_retry_recovery_reason(cls, decision: PlannerDecision, state: PlannerState) -> str:
        if decision.decision_type is not PlannerDecisionType.TOOL:
            return ""
        inspected_paths = cls._inspected_paths(state)
        if decision.tool_id == "workspace.read_range":
            path = str(decision.arguments.get("path") or "").strip()
            start_line = decision.arguments.get("start_line")
            line_count = decision.arguments.get("line_count")
            if not path:
                return "workspace.read_range retry recovery requires an exact target path."
            if inspected_paths and path not in inspected_paths:
                return "workspace.read_range retry recovery must stay within the already inspected target file set."
            try:
                start = int(start_line)
                count = int(line_count)
            except (TypeError, ValueError):
                return "workspace.read_range retry recovery requires exact start_line and line_count arguments."
            if start < 1 or count < 1:
                return "workspace.read_range retry recovery requires positive start_line and line_count values."
            return ""
        if decision.tool_id == "worktree.replace_exact":
            path = str(decision.arguments.get("path") or "").strip()
            old_text = str(decision.arguments.get("old_text") or "")
            if inspected_paths and path not in inspected_paths:
                return "worktree.replace_exact retry recovery must stay within the already inspected target file set."
            if old_text == "":
                return "worktree.replace_exact retry recovery requires non-empty old_text for existing files."
            return cls._invalid_mutation_reason(decision)
        if decision.tool_id == "worktree.write_file":
            path = str(decision.arguments.get("path") or "").strip()
            if inspected_paths and path and path not in inspected_paths:
                return "worktree.write_file retry recovery must stay within the already inspected target file set."
        return cls._invalid_mutation_reason(decision)

    @staticmethod
    def _mutation_argument_retry_prompt(prompt: str, decision: PlannerDecision, reason: str) -> str:
        tool_id = decision.tool_id or "worktree.replace_exact"
        path = str(decision.arguments.get("path") or "").strip()
        contract = (
            "\n\nEXACT MUTATION REQUIRED: The last mutation payload was structurally incomplete. "
            f"{reason} "
            f"Return one valid planner JSON object for {tool_id} with exact bounded arguments for {path or 'the target file'}. "
            "Do not use empty strings for placeholder edit text. "
            "If you cannot produce exact mutation text, choose workspace.read_range only for the specific target file once, or block with a precise reason."
        )
        budget = 2600
        if len(prompt) <= budget:
            return prompt + contract
        return prompt[-budget:] + contract

    @staticmethod
    def _post_bind_duplicate_read(decision: PlannerDecision, state: PlannerState) -> bool:
        if decision.decision_type is not PlannerDecisionType.TOOL or decision.tool_id != "workspace.read_range":
            return False
        if AgentPlannerRuntime._latest_index(state, {"worktree.bind"}, completed_only=True) < 0:
            return False
        if AgentPlannerRuntime._latest_index(state, {"worktree.write_file", "worktree.replace_exact"}, completed_only=True) >= 0:
            return False
        path = str(decision.arguments.get("path") or "").strip()
        if not path:
            return False
        read_paths = {
            str(((item.get("result") if isinstance(item.get("result"), dict) else {}).get("path")) or "").strip()
            for item in state.observations
            if isinstance(item, dict)
            and str(item.get("status") or "") == "completed"
            and str(item.get("tool_id") or "") == "workspace.read_range"
        }
        return path in read_paths

    @staticmethod
    def _mutation_retry_prompt(prompt: str, path: str) -> str:
        contract = (
            "\n\nMUTATION REQUIRED: worktree.bind is already completed and this file was already inspected. "
            f"Do not issue workspace.read_range for {path} again. "
            "Return one valid planner JSON object that advances mutation with worktree.replace_exact or worktree.write_file, "
            "or a verifier/handoff step if mutation already occurred."
        )
        budget = 2400
        if len(prompt) <= budget:
            return prompt + contract
        return prompt[-budget:] + contract

    @classmethod
    def _latest_completed_read(cls, state: PlannerState) -> dict[str, Any] | None:
        for item in reversed(state.observations):
            if not isinstance(item, dict):
                continue
            if str(item.get("tool_id") or "") != "workspace.read_range":
                continue
            if str(item.get("status") or "") != "completed":
                continue
            result = item.get("result") if isinstance(item.get("result"), dict) else {}
            path = str(result.get("path") or "").strip()
            content = str(result.get("content") or "")
            if path and content:
                return item
        return None

    @classmethod
    def _can_attempt_first_mutation_reentry(cls, run: dict[str, Any], state: PlannerState) -> bool:
        if not cls._strong_reentry_allowed(run, state):
            return False
        if cls._latest_index(state, {"worktree.bind"}, completed_only=True) < 0:
            return False
        if cls._latest_index(state, {"worktree.write_file", "worktree.replace_exact"}, completed_only=True) >= 0:
            return False
        return cls._latest_completed_read(state) is not None

    @classmethod
    def _first_mutation_retry_prompt(cls, prompt: str, state: PlannerState) -> str:
        latest = cls._latest_completed_read(state)
        if not latest:
            return cls._compact_retry_prompt(prompt)
        result = latest.get("result") if isinstance(latest.get("result"), dict) else {}
        path = str(result.get("path") or "").strip()
        content = str(result.get("content") or "")
        snippet = content[:1800]
        contract = (
            "\n\nFIRST MUTATION REQUIRED: worktree.bind is complete and exact file contents are already available. "
            f"Do not inspect again. Return one valid planner JSON object that makes one bounded edit in {path} "
            "using worktree.replace_exact with exact old_text copied from the file and exact new_text. "
            "If the file does not need changes, choose worktree.verify or blocked with a precise reason.\n"
            f"TARGET FILE: {path}\n"
            f"CURRENT CONTENT:\n{snippet}"
        )
        budget = 3200
        if len(prompt) <= budget:
            return prompt + contract
        return prompt[-budget:] + contract

    async def _retry_primary_for_first_mutation(
        self,
        provider: PlannerProvider,
        prompt: str,
        run: dict[str, Any],
        state: PlannerState,
        *,
        turn: int,
        reason: str,
    ) -> PlannerDecision | None:
        if not self._can_attempt_first_mutation_reentry(run, state):
            return None
        target_provider = self._primary_retry_provider(provider)
        retry_timeout = max(2.0, min(10.0, self._decision_timeout_seconds(run) * 0.45))
        retry_prompt = self._first_mutation_retry_prompt(prompt, state)
        latest = self._latest_completed_read(state)
        latest_result = latest.get("result") if isinstance(latest, dict) and isinstance(latest.get("result"), dict) else {}
        self.engine.emit(run.get("run_id") or "", "agent.provider.first_mutation_retry", {
            "turn": turn,
            "provider": str(run.get("provider") or ""),
            "model": str(run.get("model") or ""),
            "reason": reason,
            "path": str(latest_result.get("path") or ""),
            "timeout_ms": int(retry_timeout * 1000),
        })
        try:
            return await asyncio.wait_for(
                target_provider.next_decision(retry_prompt, run=run, turn=turn),
                timeout=retry_timeout,
            )
        except Exception as exc:
            self.engine.emit(run.get("run_id") or "", "agent.provider.first_mutation_retry_failed", {
                "turn": turn,
                "provider": str(run.get("provider") or ""),
                "model": str(run.get("model") or ""),
                "reason": f"{type(exc).__name__}: {exc}",
            })
            return None

    @classmethod
    def _preferred_tool_ids(cls, state: PlannerState) -> list[str]:
        bound = cls._latest_index(state, {"worktree.bind"}, completed_only=True) >= 0
        mutated = cls._latest_index(state, {"worktree.write_file", "worktree.replace_exact"}, completed_only=True) >= 0
        inspected_file = cls._latest_index(state, {"workspace.read_range"}, completed_only=True) >= 0
        if bound and not mutated and inspected_file:
            return [
                "worktree.replace_exact",
                "worktree.write_file",
                "worktree.verify",
                "worktree.sourceplan_draft",
            ]
        return [
            "workspace.index", "workspace.list", "workspace.search_text", "workspace.read_range",
            "worktree.bind", "worktree.sourceplan_draft", "worktree.replace_exact",
            "worktree.write_file", "worktree.verify",
        ]

    async def _retry_primary_after_heuristic_block(
        self,
        provider: PlannerProvider,
        prompt: str,
        run: dict[str, Any],
        state: PlannerState,
        *,
        turn: int,
        reason: str,
    ) -> PlannerDecision | None:
        if not self._strong_reentry_allowed(run, state):
            return None
        target_provider = self._primary_retry_provider(provider)
        retry_timeout = max(2.0, min(12.0, self._decision_timeout_seconds(run) * 0.5))
        retry_prompt = self._compact_retry_prompt(prompt)
        self.engine.emit(run.get("run_id") or "", "agent.provider.strong_retry", {
            "turn": turn,
            "provider": str(run.get("provider") or ""),
            "model": str(run.get("model") or ""),
            "reason": reason,
            "timeout_ms": int(retry_timeout * 1000),
        })
        try:
            return await asyncio.wait_for(
                target_provider.next_decision(retry_prompt, run=run, turn=turn),
                timeout=retry_timeout,
            )
        except Exception as exc:
            self.engine.emit(run.get("run_id") or "", "agent.provider.strong_retry_failed", {
                "turn": turn,
                "provider": str(run.get("provider") or ""),
                "model": str(run.get("model") or ""),
                "reason": f"{type(exc).__name__}: {exc}",
            })
            return None

    def _load_state(self, run_id: str) -> PlannerState:
        checkpoint = self._checkpoint(run_id)
        raw = checkpoint.get("planner") if isinstance(checkpoint.get("planner"), dict) else {}
        return PlannerState(
            run_id=run_id,
            turn=max(0, int(raw.get("turn") or 0)),
            max_turns=max(1, int(raw.get("max_turns") or self.max_turns)),
            status=str(raw.get("status") or "ready"),
            last_decision=raw.get("last_decision") if isinstance(raw.get("last_decision"), dict) else {},
            observations=raw.get("observations") if isinstance(raw.get("observations"), list) else [],
            final_summary=str(raw.get("final_summary") or ""),
            blocker=str(raw.get("blocker") or ""),
            repair_cycles=max(0, int(raw.get("repair_cycles") or 0)),
            max_repair_cycles=max(0, int(raw.get("max_repair_cycles") if raw.get("max_repair_cycles") is not None else self.max_repair_cycles)),
            verification_failures=raw.get("verification_failures") if isinstance(raw.get("verification_failures"), list) else [],
            post_bind_read_retry_failed=bool(raw.get("post_bind_read_retry_failed")),
        )

    def _save_state(self, state: PlannerState) -> None:
        checkpoint = self._checkpoint(state.run_id)
        checkpoint["planner"] = state.as_dict()
        self.engine.checkpoint(state.run_id, checkpoint)

    @staticmethod
    def _bootstrap_agent_decision(run: dict[str, Any], state: PlannerState, decision: PlannerDecision | None = None):
        """Guarantee a real observation before a coding agent may summarize.

        Small local models sometimes describe the required first inspection in
        their rationale but incorrectly serialize it as ``complete``.  The
        initial workspace index is read-only and bounded, so it is safe to
        make that prerequisite deterministic instead of trusting a model's
        first JSON enum.
        """
        if str(run.get("mode") or "").strip().lower() != "agent" or state.observations:
            return None
        if isinstance(decision, PlannerDecision):
            if decision.decision_type is PlannerDecisionType.TOOL:
                return None
        return PlannerDecision(
            decision_type=PlannerDecisionType.TOOL,
            tool_id="workspace.index",
            arguments={"limit": 1200, "include_symbols": True},
            rationale="Mandatory bounded workspace index before agent planning.",
        )

    def _prompt(self, run: dict[str, Any], state: PlannerState) -> str:
        all_tools = {
            str(tool.get("tool_id") or ""): tool
            for tool in self.engine.list_tools()
            if str(tool.get("tool_id") or "") != "git.status"
        }
        # Small models do better when the action vocabulary is narrow. After a
        # file has already been inspected and the worktree is bound, hide
        # exploratory tools so the next turn stays mutation-first.
        preferred = self._preferred_tool_ids(state)
        tools = [all_tools[key] for key in preferred if key in all_tools]
        if not tools:
            tools = list(all_tools.values())[:8]
        compact_tools = []
        for tool in tools:
            schema = tool.get("input_schema") if isinstance(tool.get("input_schema"), dict) else {}
            properties = schema.get("properties") if isinstance(schema.get("properties"), dict) else {}
            compact_tools.append({
                "tool_id": tool.get("tool_id"),
                "requires_approval": bool(tool.get("requires_approval")),
                "requires_worktree": bool(tool.get("requires_worktree")),
                "required_arguments": schema.get("required") if isinstance(schema.get("required"), list) else [],
                "optional_arguments": sorted(str(key) for key in properties.keys() if key not in set(schema.get("required") or [])),
            })
        compact_provider = self._is_compact_planner_provider(run)
        late_compact_turn = compact_provider and state.turn >= 3
        latest_failure = self._latest_failure_contract(state)
        if compact_provider and latest_failure is not None:
            compact_seed: list[dict[str, Any]] = []
            latest_bind = self._latest_completed_observation(state, "worktree.bind")
            latest_mutation = (
                self._latest_observation(state, "worktree.replace_exact")
                or self._latest_observation(state, "worktree.write_file")
            )
            if latest_bind is not None:
                compact_seed.append(latest_bind)
            if latest_mutation is not None:
                compact_seed.append(latest_mutation)
            compact_seed.append(latest_failure)
            observations = [self._compact_observation(item) for item in compact_seed if isinstance(item, dict)]
        else:
            visible_observations = 2 if late_compact_turn else 4 if compact_provider else min(self.observation_limit, 6)
            observations = [self._compact_observation(item) for item in state.observations[-visible_observations:]]
        repair_contract = ""
        if latest_failure is not None:
            compact_failure = self._compact_observation(latest_failure)
            repair_contract = (
                "\nREPAIR CONTRACT: The latest worktree.verify failed. Do not summarize or rewrite a whole file. "
                "Inspect the exact failure, make one bounded replace_exact or other smallest safe correction, "
                "then run worktree.verify again. Treat the verifier diagnostic as authoritative. "
                f"LATEST FAILURE: {json.dumps(compact_failure, sort_keys=True, default=str, separators=(',', ':'))}"
            )
        context_contract = self._context_contract(run)
        semantic_contract = semantic_context_contract(run, state, char_limit=500 if late_compact_turn else 900 if compact_provider else 1600)
        plan_brief = {}
        try:
            plan_brief = self.planning_integrations.current_plan_brief(str(run.get("run_id") or state.run_id))
        except Exception:
            plan_brief = {}
        plan_contract = ""
        if plan_brief.get("steps"):
            plan_contract = f"\nDURABLE PLAN: {json.dumps(plan_brief, sort_keys=True, default=str, separators=(',', ':'))}"
        approved = [item for item in self.engine.store.approvals(str(run.get("run_id") or "")) if item.get("status") == "approved"]
        authority_contract = ""
        if approved:
            authority_contract = (
                "\nAPPROVED ONE-USE AUTHORITY: include this approval_id when selecting the matching approved tool: "
                f"{approved[-1].get('approval_id', '')}\n"
            )
        tool_contract = "\n".join(
            f"- {item['tool_id']}({','.join(item['required_arguments']) or '-'})"
            + (" [APPROVAL]" if item["requires_approval"] else "")
            + (" [WORKTREE]" if item["requires_worktree"] else "")
            for item in compact_tools
        )
        objective = str(run.get("objective") or "").strip()
        mode = str(run.get("mode") or "analysis").strip().lower()
        request_payload = run.get("request") if isinstance(run.get("request"), dict) else {}
        target = str(request_payload.get("execution_target") or "local").strip() or "local"
        target_payload = request_payload.get("execution_target_payload") if isinstance(request_payload.get("execution_target_payload"), dict) else {}
        target_hint = ""
        if target_payload:
            label = str(target_payload.get("label") or target_payload.get("sessionId") or target_payload.get("host") or target)
            target_hint = f"\nEXECUTION TARGET: {target} ({label})"
        else:
            target_hint = f"\nEXECUTION TARGET: {target}"
        observed_tools = [str(item.get("tool_id") or "") for item in state.observations if isinstance(item, dict)]
        verification_hint = ""
        verifier_plan = plan_verification(run)
        if isinstance(verifier_plan.get("command"), list) and verifier_plan.get("command"):
            compact_plan = {
                "command": verifier_plan.get("command"),
                "reason": verifier_plan.get("reason"),
                "scope": verifier_plan.get("scope"),
                "changed_paths": verifier_plan.get("changed_paths", [])[:8],
                "execution_target": verifier_plan.get("execution_target"),
                "target_execution": verifier_plan.get("target_execution"),
                "strategy": verifier_plan.get("strategy"),
                "catalog_matches": verifier_plan.get("catalog_matches", []),
            }
            verification_hint = f"\nVERIFICATION HINT: {json.dumps(compact_plan, sort_keys=True, default=str, separators=(',', ':'))}"
        if mode in {"agent", "edit", "implementer"}:
            if not observed_tools:
                next_phase = "NEXT REQUIRED: choose workspace.index, workspace.list, workspace.search_text, or workspace.read_range. Do not edit yet."
            elif "worktree.bind" not in observed_tools:
                next_phase = "NEXT REQUIRED: inspect/index evidence is present; choose worktree.bind before any mutation."
            elif latest_failure is not None:
                failure_class = str(latest_failure.get("analysis", {}).get("failure_class") or "unknown")
                retryable = bool(latest_failure.get("analysis", {}).get("retryable_without_code_change"))
                target_paths = latest_failure.get("target_paths") if isinstance(latest_failure.get("target_paths"), list) else []
                failure_execution = str(latest_failure.get("target_execution") or latest_failure.get("execution_target") or "").strip()
                target_clause = f" in {', '.join(str(path) for path in target_paths[:2])}" if target_paths else ""
                transport_clause = f" on {failure_execution}" if failure_execution else ""
                if retryable:
                    next_phase = (
                        "NEXT REQUIRED: latest verifier failure appears retryable/environmental; rerun worktree.verify once "
                        f"or inspect the environment before editing code{transport_clause}. Failure class: {failure_class}."
                    )
                else:
                    next_phase = (
                        "NEXT REQUIRED: repair the latest verifier failure with one bounded edit"
                        f"{target_clause}, then rerun worktree.verify{transport_clause}. Failure class: {failure_class}."
                    )
            elif not any(tool in observed_tools for tool in {"worktree.replace_exact", "worktree.write_file"}):
                next_phase = "NEXT REQUIRED: choose one bounded worktree.replace_exact edit. Never rewrite a whole file."
            elif not any(tool == "worktree.verify" and str(item.get("status") or "") == "completed" for item in state.observations if isinstance(item, dict)):
                next_phase = "NEXT REQUIRED: choose worktree.verify. A failed verify requires one smallest repair, not completion."
            elif not any(tool == "worktree.sourceplan_draft" and str(item.get("status") or "") == "completed" for item in state.observations if isinstance(item, dict)):
                next_phase = "NEXT REQUIRED: choose worktree.sourceplan_draft before complete."
            else:
                next_phase = "NEXT REQUIRED: complete with a concise summary of verified physical changes."
        else:
            next_phase = "NEXT REQUIRED: gather enough read-only evidence, then complete with only observed facts."
        prompt = (
            "BEAST ACTION PLANNER. Controller only.\n"
            "Return ONE JSON object on ONE line. No markdown, prose, arrays, comments, or code.\n"
            "decision_type is exactly tool, complete, or blocked.\n"
            'TOOL: {"decision_type":"tool","tool_id":"workspace.read_range","arguments":{"path":"app/main.py","start_line":1,"line_count":40},"summary":""}\n'
            'DONE: {"decision_type":"complete","arguments":{},"summary":"Inspected files."}\n'
            'BLOCK: {"decision_type":"blocked","arguments":{},"blocker":"Evidence unavailable."}\n'
            "Use one listed tool and exact arguments. Never include tool_id for done/block. Never claim unobserved work. For edits: inspect, bind, bounded replace, verify, sourceplan. Never emit whole-file source; never request promotion authority.\n"
            f"MODE: {mode}\n"
            f"{target_hint}\n"
            f"OBJECTIVE: {objective}\n"
            f"TURN: {state.turn + 1}/{state.max_turns}; REPAIRS: {state.repair_cycles}/{state.max_repair_cycles}\n"
            f"{next_phase}{verification_hint}\n"
            f"ALLOWED TOOLS:\n{tool_contract}\n"
            f"OBSERVATIONS: {json.dumps(observations, sort_keys=True, default=str, separators=(',', ':'))}"
            f"{authority_contract}"
            f"{context_contract}{semantic_contract}{plan_contract}{repair_contract}"
        )
        if compact_provider:
            return prompt[:(3600 if late_compact_turn else 4800)]
        return prompt

    async def _await_tool_approval(self, run_id: str, approval_id: str, *, timeout_seconds: float = 3600.0) -> bool:
        """Pause the planner until the IDE resolves a capability request."""
        deadline = asyncio.get_running_loop().time() + max(1.0, float(timeout_seconds))
        while asyncio.get_running_loop().time() < deadline:
            self.engine.raise_if_cancelled(run_id)
            approval = self.engine.store.get_approval(run_id, approval_id) or {}
            status = str(approval.get("status") or "pending").lower()
            if status == "approved":
                return True
            if status in {"rejected", "declined", "expired"}:
                return False
            await asyncio.sleep(0.25)
        return False

    @staticmethod
    def _approval_capability_ids(approval: dict[str, Any]) -> set[str]:
        request = approval.get("request") if isinstance(approval.get("request"), dict) else {}
        capabilities = request.get("capabilities") if isinstance(request.get("capabilities"), list) else []
        return {
            str(item.get("id") or "").strip()
            for item in capabilities
            if isinstance(item, dict) and str(item.get("id") or "").strip()
        }

    @classmethod
    def _approval_satisfies_tool(cls, approval: dict[str, Any], tool_id: str) -> bool:
        request = approval.get("request") if isinstance(approval.get("request"), dict) else {}
        if str(request.get("tool_id") or "").strip() == tool_id:
            return True
        capability_ids = cls._approval_capability_ids(approval)
        if tool_id in {"worktree.bind", "worktree.write_file", "worktree.replace_exact"}:
            return "worktree_mutation" in capability_ids
        if tool_id == "worktree.verify":
            return bool({"worktree_mutation", "run_isolated_verifier"} & capability_ids)
        if tool_id == "sourceplan.promote":
            return "sourceplan.promote" in capability_ids
        return False

    async def _authorize_tool(self, run: dict[str, Any], run_id: str, decision: PlannerDecision) -> PlannerDecision | None:
        """Create and await an approval card instead of treating it as a tool error."""
        try:
            spec = self.engine.tool_registry.get(decision.tool_id)
        except Exception:
            return decision
        if not getattr(spec, "requires_approval", False):
            return decision
        approvals = self.engine.store.approvals(run_id)
        existing = next(
            (
                item for item in reversed(approvals)
                if item.get("status") == "approved"
                and self._approval_satisfies_tool(item, decision.tool_id)
            ),
            None,
        )
        if existing:
            return replace(decision, approval_id=str(existing.get("approval_id") or ""))
        approval_id = f"approval-{uuid.uuid4().hex[:16]}"
        paths = []
        for key in ("path", "target_path"):
            value = decision.arguments.get(key)
            if value:
                paths.append(str(value))
        request = {
            "request_id": approval_id,
            "run_id": run_id,
            "tool_id": decision.tool_id,
            "summary": f"Approve governed agent tool: {getattr(spec, 'title', decision.tool_id)}",
            "risk_class": getattr(getattr(spec, "risk", None), "value", "governed"),
            "execution_target": decision.execution_target,
            "capabilities": [{
                "id": decision.tool_id,
                "label": getattr(spec, "title", decision.tool_id),
                "paths": paths,
            }],
            "safe_arguments": decision.arguments,
            "affected_files": paths,
            "expected_side_effects": ["The agent may perform only this bounded tool step; SourcePlan remains required for promotion."],
        }
        step_id = self._active_plan_step_id(run_id, decision.tool_id)
        self.engine.merge_checkpoint(run_id, {
            "suspended_step": {
                "step_id": step_id,
                "approval_id": approval_id,
                "tool_id": decision.tool_id,
            },
            "suspended_step_id": step_id,
            "suspended_approval_id": approval_id,
        })
        self.engine.store.create_approval(run_id, request)
        self.engine.emit(run_id, "agent.approval.requested", request)
        try:
            self.planning_integrations.sync_phase6_approval(run_id, "agent.approval.requested", {
                "approval_id": approval_id,
                "tool_id": decision.tool_id,
                "step_id": step_id,
            })
        except Exception as exc:
            self.engine.emit(run_id, "agent.plan.integration.failed", {
                "integration_id": "phase6_approval_pause_resume",
                "reason": f"{type(exc).__name__}: {exc}",
                "event_type": "agent.approval.requested",
                "tool_id": decision.tool_id,
            })
        self.engine.store.transition(run_id, AgentRunState.WAITING_FOR_APPROVAL)
        request_payload = run.get("request") if isinstance(run.get("request"), dict) else {}
        approved = await self._await_tool_approval(
            run_id,
            approval_id,
            timeout_seconds=float(request_payload.get("approval_timeout_seconds") or 3600),
        )
        if not approved:
            return None
        self.engine.store.transition(run_id, AgentRunState.PLANNING)
        try:
            self.planning_integrations.sync_phase6_approval(run_id, "agent.approval.capability_consumed", {
                "approval_id": approval_id,
                "tool_id": decision.tool_id,
                "step_id": step_id,
                "resume_state": AgentRunState.PLANNING.value,
            })
        except Exception as exc:
            self.engine.emit(run_id, "agent.plan.integration.failed", {
                "integration_id": "phase6_approval_pause_resume",
                "reason": f"{type(exc).__name__}: {exc}",
                "event_type": "agent.approval.capability_consumed",
                "tool_id": decision.tool_id,
            })
        return replace(decision, approval_id=approval_id)

    def _context_contract(self, run: dict[str, Any]) -> str:
        """Attach one bounded Code Cortex/context packet to the planner.

        The packet is deliberately built once per run. Rebuilding semantic
        context every turn would spend CPU to save no model tokens.
        """
        if self.context_packet_builder is None:
            return ""
        if self._is_compact_planner_provider(run):
            checkpoint = run.get("checkpoint") if isinstance(run.get("checkpoint"), dict) else {}
            planner = checkpoint.get("planner") if isinstance(checkpoint.get("planner"), dict) else {}
            observations = planner.get("observations") if isinstance(planner.get("observations"), list) else []
            if observations:
                return ""
        key = str(run.get("run_id") or run.get("objective") or "context")
        if key not in self._context_cache:
            try:
                packet = self.context_packet_builder.build(
                    {
                        "objective": str(run.get("objective") or ""),
                        "prompt": str(run.get("objective") or ""),
                        "context_budget": {"max_files": 2, "max_tokens": 500, "allow_full_files": False},
                    },
                    workspace_root=str(run.get("root_path") or run.get("workspace_root") or "."),
                    semantic_limit=4,
                    include_content=False,
                    max_files=4,
                )
                encoded = json.dumps(packet, sort_keys=True, default=str, separators=(",", ":"))
                self._context_cache[key] = encoded[:1200]
            except Exception as exc:
                self._context_cache[key] = json.dumps({"status": "unavailable", "reason": type(exc).__name__})
        return f"\nCTX:{self._context_cache[key]}"

    @staticmethod
    def _is_mutating_mode(run: dict[str, Any]) -> bool:
        return str(run.get("mode") or "").strip().lower() in {"agent", "edit", "implementer"}

    @staticmethod
    def _observed_tool_ids(state: PlannerState) -> list[str]:
        return [
            str(item.get("tool_id") or "")
            for item in state.observations
            if isinstance(item, dict) and str(item.get("tool_id") or "")
        ]

    @classmethod
    def _latest_completed_observation(cls, state: PlannerState, tool_id: str) -> dict[str, Any] | None:
        for item in reversed(state.observations):
            if not isinstance(item, dict):
                continue
            if str(item.get("tool_id") or "") == tool_id and str(item.get("status") or "") == "completed":
                return item
        return None

    @classmethod
    def _latest_observation(cls, state: PlannerState, tool_id: str) -> dict[str, Any] | None:
        for item in reversed(state.observations):
            if not isinstance(item, dict):
                continue
            if str(item.get("tool_id") or "") == tool_id:
                return item
        return None

    @staticmethod
    def _latest_index(state: PlannerState, tool_ids: set[str], *, completed_only: bool = False) -> int:
        for index in range(len(state.observations) - 1, -1, -1):
            item = state.observations[index]
            if not isinstance(item, dict):
                continue
            if str(item.get("tool_id") or "") not in tool_ids:
                continue
            if completed_only and str(item.get("status") or "") != "completed":
                continue
            return index
        return -1

    @classmethod
    def _latest_mutation_paths(cls, state: PlannerState) -> list[str]:
        paths: list[str] = []
        for item in state.observations:
            if not isinstance(item, dict):
                continue
            if str(item.get("status") or "") != "completed":
                continue
            if str(item.get("tool_id") or "") not in {"worktree.write_file", "worktree.replace_exact"}:
                continue
            result = item.get("result") if isinstance(item.get("result"), dict) else {}
            path = str(result.get("path") or "")
            if path and path not in paths:
                paths.append(path)
        return paths

    @staticmethod
    def _targeted_read_path(run: dict[str, Any]) -> str:
        request = run.get("request") if isinstance(run.get("request"), dict) else {}
        semantic = request.get("semantic_context") if isinstance(request.get("semantic_context"), dict) else {}
        for key in ("active_file", "selected_file", "target_file"):
            value = str(semantic.get(key) or "").strip()
            if value:
                return value
        context_files = request.get("context_files") if isinstance(request.get("context_files"), list) else []
        for item in context_files:
            value = str(item or "").strip()
            if value:
                return value
        files = run.get("files") if isinstance(run.get("files"), list) else []
        for item in files:
            value = str(item or "").strip()
            if value:
                return value
        return ""

    @classmethod
    def _default_verification_command(cls, state: PlannerState) -> list[str]:
        changed = cls._latest_mutation_paths(state)
        python_files = [path for path in changed if path.endswith(".py")]
        js_files = [path for path in changed if path.endswith((".js", ".jsx", ".mjs", ".cjs"))]
        ts_files = [path for path in changed if path.endswith((".ts", ".tsx"))]
        if python_files:
            return ["python", "-m", "py_compile", *python_files[:12]]
        if js_files:
            return ["node", "--check", *js_files[:12]]
        if ts_files:
            return ["npx", "tsc", "--noEmit", *ts_files[:12]]
        return ["git", "diff", "--check"]

    @classmethod
    def _latest_failure_contract(cls, state: PlannerState) -> dict[str, Any] | None:
        if not state.verification_failures:
            return None
        latest_verify = cls._latest_observation(state, "worktree.verify")
        if isinstance(latest_verify, dict) and str(latest_verify.get("status") or "") == "completed":
            return None
        latest = state.verification_failures[-1]
        if not isinstance(latest, dict):
            return None
        contract = dict(latest)
        if not contract.get("target_paths"):
            paths = cls._latest_mutation_paths(state)
            if paths:
                contract["target_paths"] = paths[:4]
        return contract

    @classmethod
    def _required_phase_decision(cls, run: dict[str, Any], state: PlannerState, decision: PlannerDecision | None = None) -> PlannerDecision | None:
        if not cls._is_mutating_mode(run):
            return None
        observed = cls._observed_tool_ids(state)
        if not observed:
            return None
        inspected = any(tool in observed for tool in {"workspace.index", "workspace.list", "workspace.search_text", "workspace.read_range"})
        if not inspected and "worktree.bind" not in observed:
            return PlannerDecision(
                decision_type=PlannerDecisionType.TOOL,
                tool_id="workspace.index",
                arguments={"limit": 1200, "include_symbols": True},
                rationale="Mutating agent runs require an evidence index before worktree binding.",
            )
        if "worktree.bind" not in observed:
            return PlannerDecision(
                decision_type=PlannerDecisionType.TOOL,
                tool_id="worktree.bind",
                arguments={
                    "objective": str(run.get("objective") or "Bounded agent implementation"),
                    "provider": str(run.get("provider") or ""),
                    "risk": "high",
                },
                rationale="Mutating agent runs require an isolated worktree before any file mutation.",
            )
        inspected_paths = cls._inspected_paths(state)
        if not inspected_paths:
            targeted_path = cls._targeted_read_path(run)
            if targeted_path:
                return PlannerDecision(
                    decision_type=PlannerDecisionType.TOOL,
                    tool_id="workspace.read_range",
                    arguments={"path": targeted_path, "start_line": 1, "line_count": 220},
                    rationale="A bounded file read is required after bind when no exact file contents have been inspected yet.",
                )
        mutation_paths = cls._latest_mutation_paths(state)
        latest_mutation_index = cls._latest_index(state, {"worktree.write_file", "worktree.replace_exact"}, completed_only=True)
        latest_verify_index = cls._latest_index(state, {"worktree.verify"})
        latest_verify = cls._latest_observation(state, "worktree.verify")
        if mutation_paths and (latest_verify_index < 0 or latest_mutation_index > latest_verify_index):
            request = run.get("request") if isinstance(run.get("request"), dict) else {}
            objective = str(run.get("objective") or "").casefold()
            broad_wave = bool(request.get("long_horizon") or request.get("monorepo") or request.get("architecture_planning") or any(term in objective for term in ("large", "monorepo", "cross-cutting", "many files")))
            if (
                broad_wave
                and isinstance(decision, PlannerDecision)
                and decision.decision_type is PlannerDecisionType.TOOL
                and decision.tool_id in {"worktree.write_file", "worktree.replace_exact"}
                and len(set(mutation_paths)) < 32
            ):
                return None
            return PlannerDecision(
                decision_type=PlannerDecisionType.TOOL,
                tool_id="worktree.verify",
                arguments={"command": cls._default_verification_command(state)},
                rationale="A bounded verifier must run after the latest mutation before BEAST can prepare SourcePlan evidence.",
            )
        latest_sourceplan_index = cls._latest_index(state, {"worktree.sourceplan_draft"}, completed_only=True)
        if (
            isinstance(latest_verify, dict)
            and str(latest_verify.get("status") or "") == "completed"
            and latest_verify_index >= 0
            and latest_sourceplan_index < latest_verify_index
        ):
            return PlannerDecision(
                decision_type=PlannerDecisionType.TOOL,
                tool_id="worktree.sourceplan_draft",
                arguments={},
                rationale="A verified worktree diff must be materialized into SourcePlan before completion.",
            )
        return None

    @staticmethod
    def _completion_ready(run: dict[str, Any], state: PlannerState) -> bool:
        """Only allow completion after fresh verification and handoff evidence."""
        mode = str(run.get("mode") or "").strip().lower()
        mutation_tools = {"worktree.bind", "worktree.write_file", "worktree.replace_exact", "worktree.verify", "worktree.sourceplan_draft"}
        mutated = mode in {"agent", "edit", "implementer"} or any(
            str(item.get("tool_id") or "") in mutation_tools
            for item in state.observations
            if isinstance(item, dict)
        )
        if not mutated:
            return True
        latest_mutation_index = AgentPlannerRuntime._latest_index(state, {"worktree.write_file", "worktree.replace_exact"}, completed_only=True)
        latest_verify_index = AgentPlannerRuntime._latest_index(state, {"worktree.verify"}, completed_only=True)
        latest_sourceplan_index = AgentPlannerRuntime._latest_index(state, {"worktree.sourceplan_draft"}, completed_only=True)
        return latest_verify_index >= latest_mutation_index >= 0 and latest_sourceplan_index >= latest_verify_index >= 0

    @classmethod
    def _completion_summary_from_state(cls, run: dict[str, Any], state: PlannerState) -> str:
        changed = cls._latest_mutation_paths(state)
        verify = cls._latest_completed_observation(state, "worktree.verify")
        sourceplan = cls._latest_completed_observation(state, "worktree.sourceplan_draft")
        if changed:
            joined = ", ".join(changed[:4])
            if verify is not None and sourceplan is not None:
                return f"Completed bounded changes in {joined}; verification passed and SourcePlan evidence is ready."
            if verify is not None:
                return f"Completed bounded changes in {joined}; verification passed."
            return f"Completed bounded changes in {joined}."
        objective = str(run.get("objective") or "").strip()
        if objective:
            return f"Completed: {objective}"
        return "Completed bounded agent run."

    @staticmethod
    def _compact_observation(observation: Any) -> dict[str, Any]:
        """Project tool output into planner evidence without replaying payloads."""
        if not isinstance(observation, dict):
            return {"status": "unknown", "summary": str(observation)[:800]}
        projected: dict[str, Any] = {}
        for key in ("observation_id", "tool_id", "status", "error", "duration_ms"):
            if key in observation and observation[key] not in {None, ""}:
                projected[key] = observation[key]
        result = observation.get("result") if isinstance(observation.get("result"), dict) else {}
        compact_result: dict[str, Any] = {}
        for key, value in result.items():
            if isinstance(value, (str, int, float, bool)) or value is None:
                text = str(value) if isinstance(value, str) else value
                marker = "[truncated]"
                compact_result[key] = text[: 2400 - len(marker)] + marker if isinstance(text, str) and len(text) > 2400 else text
            elif key in {"matches", "entries", "files", "symbols", "tests", "diagnostics", "codeActions", "code_actions"} and isinstance(value, list):
                # Preserve navigable evidence, not a second copy of the
                # repository. The full result remains durable in the ledger.
                compact_result[key] = [
                    {
                        field: item.get(field)
                        for field in ("path", "file", "name", "kind", "line", "match", "language", "severity", "code", "message", "title")
                        if isinstance(item, dict) and item.get(field) not in {None, ""}
                    }
                    if isinstance(item, dict) else str(item)[:180]
                    for item in value[:12]
                ]
            elif key in {"semantic", "navigation", "diagnostics", "refactor", "renamePreview", "rename_preview"} and isinstance(value, dict):
                compact_result[key] = {
                    field: value.get(field)
                    for field in ("ok", "status", "count", "symbolCount", "referenceCount", "importEdgeCount", "codeActionCount", "supportsRenamePreview", "supportsCodeActions", "editCount", "fileCount")
                    if value.get(field) is not None and value.get(field) != ""
                }
            elif key in {"summary"} and isinstance(value, dict):
                compact_result[key] = {
                    field: value.get(field)
                    for field in ("file_count", "symbol_count", "import_count", "test_file_count", "languages", "symbol_kinds", "reference_count", "import_edge_count", "diagnostic_count")
                    if value.get(field) is not None and value.get(field) != ""
                }
        if compact_result:
            projected["result"] = compact_result
        encoded = json.dumps(projected, sort_keys=True, default=str, separators=(",", ":"))
        if len(encoded) > 3000:
            projected["result"] = {"summary": encoded[:2800] + "[truncated]", "truncated": True}
        return projected

    async def run(self, run_id: str) -> dict[str, Any]:
        run = self.engine.store.get_run(run_id)
        if not run:
            raise KeyError(f"unknown agent run: {run_id}")
        current = normalize_state(str(run.get("state") or "created"))
        if current in TERMINAL_STATES:
            return run
        self.engine.attach_current_task(run_id)
        state = self._load_state(run_id)
        state.max_turns = self.max_turns
        state.max_repair_cycles = self.max_repair_cycles
        state.status = "running"
        self._save_state(state)
        try:
            self.planning_integrations.ensure_phase1_plan(run_id, run)
        except Exception as exc:
            self.engine.emit(run_id, "agent.plan.integration.failed", {
                "integration_id": "phase1_multi_file_execution_planning",
                "reason": f"{type(exc).__name__}: {exc}",
            })
        try:
            self.planning_integrations.sync_phase5_resume(run_id, run)
        except Exception as exc:
            self.engine.emit(run_id, "agent.plan.integration.failed", {
                "integration_id": "phase5_resume_continuity",
                "reason": f"{type(exc).__name__}: {exc}",
            })
        self.engine.emit(run_id, "agent.planner.started", {
            "turn": state.turn,
            "max_turns": state.max_turns,
            "observation_count": len(state.observations),
        })

        while state.turn < state.max_turns:
            self.engine.raise_if_cancelled(run_id)
            self.engine.store.transition(run_id, AgentRunState.PLANNING)
            run = self.engine.store.get_run(run_id) or run
            prompt = self._prompt(run, state)
            self.engine.emit(run_id, "agent.planner.turn.started", {
                "turn": state.turn + 1,
                "max_turns": state.max_turns,
                "observation_count": len(state.observations),
            })
            try:
                self.planning_integrations.sync_phase3_telemetry(run_id, "agent.planner.turn.started", {
                    "turn": state.turn + 1,
                    "max_turns": state.max_turns,
                })
            except Exception as exc:
                self.engine.emit(run_id, "agent.plan.integration.failed", {
                    "integration_id": "phase3_latency_observability",
                    "reason": f"{type(exc).__name__}: {exc}",
                    "event_type": "agent.planner.turn.started",
                })
            decision_timeout = self._decision_timeout_seconds(run)
            original_provider = self.provider
            decision_task = asyncio.create_task(
                self.provider.next_decision(prompt, run=run, turn=state.turn + 1)
            )
            try:
                decision = await asyncio.wait_for(
                    asyncio.shield(decision_task),
                    timeout=decision_timeout,
                )
            except asyncio.TimeoutError:
                self.engine.emit(run_id, "agent.provider.decision_timeout", {
                    "turn": state.turn + 1,
                    "provider": str(run.get("provider") or ""),
                    "model": str(run.get("model") or ""),
                    "timeout_ms": int(decision_timeout * 1000),
                    "fallback": "heuristic" if self._heuristic_continuation_allowed(run) else "unavailable",
                })
                mode = str(run.get("mode") or "").strip().lower()
                if mode in {"chat", "analysis", "ask"}:
                    grace_seconds = max(0.25, min(3.0, float(os.environ.get("BEAST_AGENT_PARTIAL_COMPLETION_GRACE_SECONDS", "1.5"))))
                    try:
                        decision = await asyncio.wait_for(asyncio.shield(decision_task), timeout=grace_seconds)
                    except asyncio.TimeoutError:
                        pass
                    except Exception:
                        pass
                partial_text = self._provider_partial_text(self.provider) or self._recent_model_delta_text(run_id)
                if mode in {"chat", "analysis", "ask"} and partial_text:
                    decision = PlannerDecision(
                        decision_type=PlannerDecisionType.COMPLETE,
                        arguments={},
                        summary=partial_text,
                        rationale="Completed from partial streamed provider text after planner decision timeout.",
                    )
                    self.engine.emit(run_id, "agent.provider.partial_completion", {
                        "turn": state.turn + 1,
                        "provider": str(run.get("provider") or ""),
                        "model": str(run.get("model") or ""),
                        "chars": len(partial_text),
                    })
                else:
                    partial_decision = self._partial_structured_decision(run, partial_text)
                    if partial_decision is not None:
                        decision = partial_decision
                        self.engine.emit(run_id, "agent.provider.partial_decision_salvaged", {
                            "turn": state.turn + 1,
                            "provider": str(run.get("provider") or ""),
                            "model": str(run.get("model") or ""),
                            "decision_type": decision.decision_type.value,
                            "tool_id": decision.tool_id,
                            "chars": len(partial_text),
                        })
                    else:
                        decision_task.cancel()
                        if not self._heuristic_continuation_allowed(run):
                            raise TimeoutError(f"planner provider decision exceeded {int(decision_timeout * 1000)} ms before a usable decision")
                        heuristic = HeuristicPlannerProvider()
                        try:
                            decision = await heuristic.next_decision(prompt, run=run, turn=state.turn + 1)
                            self.engine.emit(run_id, "agent.provider.sticky_fallback", {
                                "from": str(run.get("provider") or ""),
                                "to": "heuristic",
                                "reason": "planner_decision_timeout",
                                "slow_ms": int(decision_timeout * 1000),
                            })
                        except Exception as exc:
                            retried = await self._retry_primary_after_heuristic_block(
                                original_provider,
                                prompt,
                                run,
                                state,
                                turn=state.turn + 1,
                                reason=f"heuristic_failure_after_timeout:{type(exc).__name__}",
                            )
                            if retried is None:
                                raise
                            decision = retried
                            self.engine.emit(run_id, "agent.provider.strong_retry_recovered", {
                                "turn": state.turn + 1,
                                "provider": str(run.get("provider") or ""),
                                "model": str(run.get("model") or ""),
                                "decision_type": decision.decision_type.value,
                            })
            except Exception:
                decision_task.cancel()
                raise
            provider_decision = True
            try:
                route = getattr(self.provider, "last_route", None)
                usage = getattr(self.provider, "last_usage", None)
                route_provider = str((route or {}).get("provider") or getattr(self.provider, "last_provider", "") or "primary")
                route_engine = str((route or {}).get("engine") or "")
                route_reason = str((route or {}).get("reason") or "")
                route_kind = str((route or {}).get("route_kind") or route_provider)
                if isinstance(usage, dict):
                    if not route_engine:
                        route_engine = str(usage.get("engine") or "")
                    if isinstance(usage.get("crystal_reuse"), dict):
                        route_kind = "crystal_reuse"
                        if not route_reason:
                            route_reason = str(usage["crystal_reuse"].get("action") or "")
                    elif isinstance(usage.get("forge_kv"), dict):
                        route_kind = "native_context"
                        if not route_reason:
                            route_reason = str(usage["forge_kv"].get("mode") or "")
                    elif isinstance(usage.get("execution_gateway"), dict):
                        route_kind = "execution_gateway"
                        if not route_reason:
                            route_reason = str(usage["execution_gateway"].get("mode") or "")
                self.planning_integrations.sync_phase4_route(run_id, {
                    "provider": route_provider,
                    "engine": route_engine,
                    "route_kind": route_kind,
                    "reason": route_reason or "planner_decision",
                    "turn": state.turn + 1,
                    "task_type": (route or {}).get("task_type") if isinstance(route, dict) else "",
                    "task_hardness": (route or {}).get("task_hardness") if isinstance(route, dict) else None,
                    "capability_score": (route or {}).get("capability_score") if isinstance(route, dict) else None,
                    "quality_score": (route or {}).get("quality_score") if isinstance(route, dict) else None,
                    "route_health": (route or {}).get("route_health") if isinstance(route, dict) else None,
                })
                self.engine.emit(run_id, "agent.provider.route", {
                    "turn": state.turn + 1,
                    "provider": route_provider,
                    "engine": route_engine,
                    "route_kind": route_kind,
                    "reason": route_reason or "planner_decision",
                    "task_type": (route or {}).get("task_type") if isinstance(route, dict) else "",
                    "task_hardness": (route or {}).get("task_hardness") if isinstance(route, dict) else None,
                    "capability_score": (route or {}).get("capability_score") if isinstance(route, dict) else None,
                    "quality_score": (route or {}).get("quality_score") if isinstance(route, dict) else None,
                    "route_health": (route or {}).get("route_health") if isinstance(route, dict) else None,
                })
            except Exception as exc:
                self.engine.emit(run_id, "agent.plan.integration.failed", {
                    "integration_id": "phase4_model_routing",
                    "reason": f"{type(exc).__name__}: {exc}",
                    "event_type": "planner_route",
                })
            usage = getattr(self.provider, "last_usage", None)
            if isinstance(usage, dict) and usage:
                # Keep latency and token evidence next to the decision.
                self.engine.emit(run_id, "agent.model.usage", {
                    "turn": state.turn + 1,
                    "engine": usage.get("engine"),
                    "model": usage.get("model"),
                    "prompt_chars": usage.get("prompt_chars", 0),
                    "completion_chars": usage.get("completion_chars", 0),
                    "latency_ms": usage.get("latency_ms"),
                    "usage": usage.get("usage") if isinstance(usage.get("usage"), dict) else {},
                    "finish_reason": usage.get("finish_reason"),
                })
                try:
                    self.planning_integrations.sync_phase3_telemetry(run_id, "agent.model.usage", {
                        "turn": state.turn + 1,
                        "model": usage.get("model"),
                        "latency_ms": usage.get("latency_ms"),
                        "prompt_chars": usage.get("prompt_chars", 0),
                        "completion_chars": usage.get("completion_chars", 0),
                    })
                except Exception as exc:
                    self.engine.emit(run_id, "agent.plan.integration.failed", {
                        "integration_id": "phase3_latency_observability",
                        "reason": f"{type(exc).__name__}: {exc}",
                        "event_type": "agent.model.usage",
                    })
            provider_partial = self._provider_partial_text(self.provider)
            delta_partial = self._recent_model_delta_text(run_id)
            salvaged_decision = self._salvage_partial_decision_from_provider(
                run,
                self.provider,
                partial_text=provider_partial or delta_partial,
                decision=decision,
            )
            if salvaged_decision is not None:
                decision = salvaged_decision
                self.engine.emit(run_id, "agent.provider.partial_decision_salvaged", {
                    "turn": state.turn + 1,
                    "provider": str(run.get("provider") or ""),
                    "model": str(run.get("model") or ""),
                    "decision_type": decision.decision_type.value,
                    "tool_id": decision.tool_id,
                    "chars": len(provider_partial or delta_partial),
                    "reason": "wrapped_provider_fallback_salvage",
                })
            bootstrapped = self._bootstrap_agent_decision(run, state, decision)
            if bootstrapped is not None:
                decision = bootstrapped
            required = self._required_phase_decision(run, state, decision)
            if required is not None:
                if decision.decision_type is not PlannerDecisionType.TOOL or decision.tool_id != required.tool_id:
                    if provider_decision:
                        self.engine.emit(run_id, "agent.planner.phase_enforced", {
                            "turn": state.turn + 1,
                            "required_tool_id": required.tool_id,
                            "replaced_decision": decision.as_dict(),
                            "reason": required.rationale,
                        })
                    decision = required
            if self._post_bind_duplicate_read(decision, state) and self._strong_reentry_allowed(run, state):
                duplicate_path = str(decision.arguments.get("path") or "").strip()
                self.engine.emit(run_id, "agent.provider.post_bind_read_retry", {
                    "turn": state.turn + 1,
                    "provider": str(run.get("provider") or ""),
                    "model": str(run.get("model") or ""),
                    "path": duplicate_path,
                })
                retry_timeout = max(2.0, min(12.0, self._decision_timeout_seconds(run) * 0.5))
                try:
                    retried = await asyncio.wait_for(
                        original_provider.next_decision(
                            self._mutation_retry_prompt(prompt, duplicate_path),
                            run=run,
                            turn=state.turn + 1,
                        ),
                        timeout=retry_timeout,
                    )
                except Exception as exc:
                    state.post_bind_read_retry_failed = True
                    self._save_state(state)
                    self.engine.emit(run_id, "agent.provider.post_bind_read_retry_failed", {
                        "turn": state.turn + 1,
                        "provider": str(run.get("provider") or ""),
                        "model": str(run.get("model") or ""),
                        "path": duplicate_path,
                        "reason": f"{type(exc).__name__}: {exc}",
                    })
                else:
                    if (
                        retried.decision_type is not PlannerDecisionType.BLOCKED
                        and not self._post_bind_duplicate_read(retried, state)
                    ):
                        decision = retried
                        state.post_bind_read_retry_failed = False
                        self.engine.emit(run_id, "agent.provider.strong_retry_recovered", {
                            "turn": state.turn + 1,
                            "provider": str(run.get("provider") or ""),
                            "model": str(run.get("model") or ""),
                            "decision_type": decision.decision_type.value,
                        })
                    else:
                        state.post_bind_read_retry_failed = True
                        self._save_state(state)
                        self.engine.emit(run_id, "agent.provider.post_bind_read_retry_failed", {
                            "turn": state.turn + 1,
                            "provider": str(run.get("provider") or ""),
                            "model": str(run.get("model") or ""),
                            "path": duplicate_path,
                            "reason": "retry_did_not_advance_mutation",
                        })
            if state.post_bind_read_retry_failed and self._post_bind_duplicate_read(decision, state):
                blocked_path = str(decision.arguments.get("path") or "")
                decision = PlannerDecision(
                    decision_type=PlannerDecisionType.BLOCKED,
                    arguments={},
                    blocker="Provider could not produce a bounded mutation plan after bind; repeated read-only turns are no longer allowed.",
                    rationale="Post-bind read-only loop persisted after a mutation-focused retry.",
                )
                self.engine.emit(run_id, "agent.provider.read_loop_blocked", {
                    "turn": state.turn + 1,
                    "provider": str(run.get("provider") or ""),
                    "model": str(run.get("model") or ""),
                    "path": blocked_path,
                })
            mutation_reason = self._invalid_mutation_reason(decision)
            if mutation_reason and self._strong_reentry_allowed(run, state):
                self.engine.emit(run_id, "agent.provider.invalid_mutation_retry", {
                    "turn": state.turn + 1,
                    "provider": str(run.get("provider") or ""),
                    "model": str(run.get("model") or ""),
                    "tool_id": decision.tool_id,
                    "reason": mutation_reason,
                    "path": str(decision.arguments.get("path") or ""),
                })
                retry_timeout = max(2.0, min(12.0, self._decision_timeout_seconds(run) * 0.5))
                try:
                    retried = await asyncio.wait_for(
                        original_provider.next_decision(
                            self._mutation_argument_retry_prompt(prompt, decision, mutation_reason),
                            run=run,
                            turn=state.turn + 1,
                        ),
                        timeout=retry_timeout,
                    )
                except Exception as exc:
                    decision = PlannerDecision(
                        decision_type=PlannerDecisionType.BLOCKED,
                        arguments={},
                        blocker=f"{mutation_reason} Retry failed: {type(exc).__name__}: {exc}",
                        rationale="Invalid mutation payload could not be repaired before tool execution.",
                    )
                    self.engine.emit(run_id, "agent.provider.invalid_mutation_retry_failed", {
                        "turn": state.turn + 1,
                        "provider": str(run.get("provider") or ""),
                        "model": str(run.get("model") or ""),
                        "tool_id": decision.tool_id,
                        "reason": mutation_reason,
                        "error": f"{type(exc).__name__}: {exc}",
                    })
                else:
                    retried_reason = self._invalid_retry_recovery_reason(retried, state)
                    if not retried_reason:
                        decision = retried
                        self.engine.emit(run_id, "agent.provider.invalid_mutation_recovered", {
                            "turn": state.turn + 1,
                            "provider": str(run.get("provider") or ""),
                            "model": str(run.get("model") or ""),
                            "tool_id": decision.tool_id,
                        })
                    else:
                        decision = PlannerDecision(
                            decision_type=PlannerDecisionType.BLOCKED,
                            arguments={},
                            blocker=retried_reason,
                            rationale="Mutation payload remained incomplete after bounded retry.",
                        )
                        self.engine.emit(run_id, "agent.provider.invalid_mutation_retry_failed", {
                            "turn": state.turn + 1,
                            "provider": str(run.get("provider") or ""),
                            "model": str(run.get("model") or ""),
                            "tool_id": retried.tool_id,
                            "reason": retried_reason,
                            "error": "retry_returned_invalid_mutation",
                        })
            state.turn += 1
            state.last_decision = decision.as_dict()
            self.engine.emit(run_id, "agent.planner.decision", {
                "turn": state.turn,
                "decision": decision.as_dict(),
            })
            self._save_state(state)

            if decision.decision_type is PlannerDecisionType.COMPLETE:
                if not self._completion_ready(run, state):
                    state.observations.append({
                        "observation_id": "planner-completion-gate",
                        "tool_id": "planner.completion_gate",
                        "status": "failed",
                        "error": "completion requires passing worktree.verify and worktree.sourceplan_draft observations",
                        "result": {"verification_required": True, "handoff_required": True},
                    })
                    state.observations = state.observations[-self.observation_limit:]
                    self.engine.emit(run_id, "agent.planner.completion_rejected", {
                        "turn": state.turn,
                        "reason": "fresh verification and sourceplan handoff evidence are required",
                    })
                    self._save_state(state)
                    continue
                state.status = "completed"
                state.final_summary = decision.summary
                record_verified = getattr(self.provider, "record_verified_decision", None)
                if callable(record_verified):
                    try:
                        record_verified(
                            prompt=prompt,
                            decision=decision,
                            run=run,
                            evidence={"observations": state.observations[-self.observation_limit:]},
                        )
                    except Exception as exc:
                        self.engine.emit(run_id, "agent.planner.crystal_record_failed", {
                            "turn": state.turn,
                            "reason": f"{type(exc).__name__}: {exc}",
                        })
                self.engine.store.transition(run_id, AgentRunState.FINALIZING)
                self.engine.emit(run_id, "agent.planner.completed", {
                    "turns": state.turn,
                    "summary": decision.summary,
                    "observation_count": len(state.observations),
                })
                self._save_state(state)
                self.engine.store.transition(run_id, AgentRunState.COMPLETED)
                return self.engine.store.get_run(run_id) or {}

            if decision.decision_type is PlannerDecisionType.BLOCKED:
                route = getattr(self.provider, "last_route", None)
                route_kind = str((route or {}).get("route_kind") or "")
                blocked_on_heuristic_dead_end = (
                    route_kind == "heuristic"
                    and "stronger planner route required" in str(decision.blocker or "").casefold()
                )
                first_mutation_retried = False
                if (
                    (route_kind in {"sticky_fallback", "fallback", "fallback_unavailable"} or blocked_on_heuristic_dead_end)
                    and self._strong_reentry_allowed(run, state)
                ):
                    mutation_retry = await self._retry_primary_for_first_mutation(
                        original_provider,
                        prompt,
                        run,
                        state,
                        turn=state.turn,
                        reason=decision.blocker or route_kind or "first_mutation_blocked",
                    )
                    if mutation_retry is not None and mutation_retry.decision_type is not PlannerDecisionType.BLOCKED:
                        decision = mutation_retry
                        state.last_decision = decision.as_dict()
                        first_mutation_retried = True
                        self.engine.emit(run_id, "agent.provider.strong_retry_recovered", {
                            "turn": state.turn,
                            "provider": str(run.get("provider") or ""),
                            "model": str(run.get("model") or ""),
                            "decision_type": decision.decision_type.value,
                            "recovery_kind": "first_mutation_retry",
                        })
                    else:
                        self.provider = original_provider
                if (
                    not first_mutation_retried
                    and (route_kind in {"sticky_fallback", "fallback", "fallback_unavailable"} or blocked_on_heuristic_dead_end)
                    and self._strong_reentry_allowed(run, state)
                ):
                    retried = await self._retry_primary_after_heuristic_block(
                        original_provider,
                        prompt,
                        run,
                        state,
                        turn=state.turn,
                        reason=decision.blocker or route_kind or "heuristic_blocked",
                    )
                    if retried is not None and retried.decision_type is not PlannerDecisionType.BLOCKED:
                        decision = retried
                        state.last_decision = decision.as_dict()
                        self.engine.emit(run_id, "agent.provider.strong_retry_recovered", {
                            "turn": state.turn,
                            "provider": str(run.get("provider") or ""),
                            "model": str(run.get("model") or ""),
                            "decision_type": decision.decision_type.value,
                        })
                    else:
                        self.provider = original_provider
                if decision.decision_type is not PlannerDecisionType.BLOCKED:
                    pass
                else:
                    state.status = "blocked"
                    state.blocker = decision.blocker
                    self.engine.emit(run_id, "agent.planner.blocked", {
                        "turn": state.turn,
                        "blocker": decision.blocker,
                    })
                    self._save_state(state)
                    self.engine.store.transition(run_id, AgentRunState.POLICY_BLOCKED, error=decision.blocker)
                    return self.engine.store.get_run(run_id) or {}

            self.engine.store.transition(run_id, AgentRunState.EXECUTING_TOOL)
            authorized = await self._authorize_tool(run, run_id, decision)
            if authorized is None:
                state.status = "blocked"
                state.blocker = f"operator did not approve {decision.tool_id}"
                self._save_state(state)
                self.engine.store.transition(run_id, AgentRunState.POLICY_BLOCKED, error=state.blocker)
                return self.engine.store.get_run(run_id) or {}
            decision = authorized
            try:
                observation = await self.engine.execute_tool(
                    run_id,
                    decision.tool_id,
                    decision.arguments,
                    execution_target=decision.execution_target,
                    execution_target_payload=self._execution_target_payload(run, decision.execution_target),
                    approval_id=decision.approval_id,
                )
            except ToolExecutionFailed as exc:
                observation = exc.observation.as_dict()
            except Exception as exc:
                observation = {
                    "observation_id": "",
                    "run_id": run_id,
                    "tool_id": decision.tool_id,
                    "status": "failed",
                    "error": str(exc),
                    "arguments": decision.arguments,
                    "result": {},
                }

            if decision.tool_id == "worktree.verify" and observation.get("status") != "completed":
                result = observation.get("result") if isinstance(observation.get("result"), dict) else {}
                analysis = analyze_failure("\n".join(
                    part for part in (
                        str(observation.get("error") or ""),
                        str(result.get("stderr") or ""),
                        str(result.get("stdout") or ""),
                        str(result.get("diagnostic") or ""),
                    )
                    if part
                ))
                target_paths = self._latest_mutation_paths(state)[:4]
                result["analysis"] = analysis
                result["target_paths"] = target_paths
                observation["result"] = result
                state.repair_cycles += 1
                failure = {
                    "turn": state.turn,
                    "repair_cycle": state.repair_cycles,
                    "observation_id": observation.get("observation_id", ""),
                    "error": observation.get("error", ""),
                    "result": result,
                    "analysis": analysis,
                    "target_paths": target_paths,
                    "command": list(result.get("command") or []),
                    "resolved_command": list(result.get("resolved_command") or []),
                    "returncode": result.get("returncode"),
                    "execution_target": str(result.get("execution_target") or decision.execution_target or ""),
                    "execution_target_payload": dict(result.get("execution_target_payload") or self._execution_target_payload(run, decision.execution_target)),
                    "target_execution": str(result.get("target_execution") or ""),
                    "transport": str(result.get("transport") or ""),
                }
                state.verification_failures.append(failure)
                state.verification_failures = state.verification_failures[-self.max_repair_cycles or 1:]
                self.engine.emit(run_id, "agent.verification.failed", failure)
                if state.repair_cycles > state.max_repair_cycles:
                    state.status = "repair_exhausted"
                    state.blocker = f"verification repair budget exhausted after {state.max_repair_cycles} cycle(s)"
                    self.engine.emit(run_id, "agent.repair.budget_exhausted", {
                        "repair_cycles": state.repair_cycles,
                        "max_repair_cycles": state.max_repair_cycles,
                        "last_failure": failure,
                    })
                    self._save_state(state)
                    self.engine.store.transition(run_id, AgentRunState.BUDGET_EXHAUSTED, error=state.blocker)
                    return self.engine.store.get_run(run_id) or {}
                self.engine.emit(run_id, "agent.repair.required", {
                    "repair_cycle": state.repair_cycles,
                    "remaining_repairs": max(0, state.max_repair_cycles - state.repair_cycles),
                    "verification_observation": failure,
                    "failure_analysis": analysis,
                    "target_paths": failure["target_paths"],
                })
            elif decision.tool_id == "worktree.verify" and observation.get("status") == "completed":
                self.engine.emit(run_id, "agent.verification.passed", {
                    "turn": state.turn,
                    "repair_cycles": state.repair_cycles,
                    "observation_id": observation.get("observation_id", ""),
                    "evidence_digest": observation.get("evidence_digest", ""),
                })
            state.observations.append(observation)
            state.observations = state.observations[-self.observation_limit:]
            self.engine.store.transition(run_id, AgentRunState.UPDATING_PLAN)
            self.engine.emit(run_id, "agent.planner.observation.accepted", {
                "turn": state.turn,
                "observation_id": observation.get("observation_id"),
                "tool_id": observation.get("tool_id"),
                "status": observation.get("status"),
                "evidence_digest": observation.get("evidence_digest", ""),
            })
            try:
                self.planning_integrations.sync_phase1_progress(run_id, observation)
            except Exception as exc:
                self.engine.emit(run_id, "agent.plan.integration.failed", {
                    "integration_id": "phase1_multi_file_execution_planning",
                    "reason": f"{type(exc).__name__}: {exc}",
                    "tool_id": observation.get("tool_id"),
                })
            try:
                self.planning_integrations.sync_phase3_telemetry(run_id, "agent.plan.telemetry.observation", {
                    "tool_id": observation.get("tool_id"),
                    "status": observation.get("status"),
                    "duration_ms": observation.get("duration_ms"),
                })
            except Exception as exc:
                self.engine.emit(run_id, "agent.plan.integration.failed", {
                    "integration_id": "phase3_latency_observability",
                    "reason": f"{type(exc).__name__}: {exc}",
                    "event_type": "agent.plan.telemetry.observation",
                    "tool_id": observation.get("tool_id"),
                })
            self._save_state(state)

        if self._is_mutating_mode(run) and self._completion_ready(run, state):
            state.status = "completed"
            state.final_summary = self._completion_summary_from_state(run, state)
            self.engine.store.transition(run_id, AgentRunState.FINALIZING)
            self.engine.emit(run_id, "agent.planner.completed", {
                "turns": state.turn,
                "summary": state.final_summary,
                "observation_count": len(state.observations),
                "completion_mode": "budget_edge_autofinalize",
            })
            self._save_state(state)
            self.engine.store.transition(run_id, AgentRunState.COMPLETED)
            return self.engine.store.get_run(run_id) or {}
        state.status = "budget_exhausted"
        state.blocker = f"planner turn budget exhausted at {state.max_turns} turns"
        self.engine.emit(run_id, "agent.planner.budget_exhausted", {
            "turns": state.turn,
            "max_turns": state.max_turns,
        })
        self._save_state(state)
        self.engine.store.transition(run_id, AgentRunState.BUDGET_EXHAUSTED, error=state.blocker)
        return self.engine.store.get_run(run_id) or {}

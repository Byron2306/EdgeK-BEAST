"""Durable bounded model -> tool -> observation loop for BEAST AgentRuns."""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import pathlib
import re
import shlex
import subprocess
import time
import uuid
from dataclasses import replace
from typing import Any

from app.kernel.agents.failure_analyst import analyze_failure
from app.kernel.agents.file_review import (
    ReviewEvidence, ReviewPacketError, collect_review_evidence, explains_attached_files, review_paths, review_timeout_seconds,
)
from app.kernel.agents.post_session_graduation import assess as assess_post_session_graduation
from app.kernel.agents.post_session_quality import verify as verify_post_session_quality
from app.kernel.agents.planning_integrations import PlanningIntegrationRuntime
from app.kernel.agents.planner_models import PlannerDecision, PlannerDecisionType, PlannerState
from app.kernel.agents.planner_provider import HeuristicPlannerProvider, PlannerDecisionError, PlannerProvider, normalize_editor_tool_dialect, parse_planner_decision
from app.kernel.agents.run_state import AgentRunState, TERMINAL_STATES, normalize_state
from app.kernel.agents.semantic_context import semantic_context_contract
from app.kernel.agents.tool_models import ToolEffect, is_read_only_run
from app.kernel.agents.tool_runtime import ToolExecutionFailed, h12_approval_authorizes, local_binding_error, local_binding_identity
from app.kernel.agents.verification_planner import plan_verification, verified_handoff_command
from app.kernel.agents.worktree_apply import ApplyBlocked, apply_workspace_files, read_worktree_diff
from app.kernel.compute.coding_crystals import REVIEWED_TOOLS as CRYSTAL_REVIEWED_TOOLS
from app.kernel.compute.crystal_autopromotion_daemon import CrystalAutopromotionDaemon
from app.kernel.sensorium.episode_envelope import EpisodeEnvelopeBuilder, RunBudgetTracker


class PlannerBudgetExhausted(RuntimeError):
    pass


class ApprovalDeferred(RuntimeError):
    """Raised when a turn-based call must hand an approval card back to the operator.

    Turn-based execution never blocks on a human. The approval card is created
    and persisted, the run is parked in WAITING_FOR_APPROVAL, and control
    returns to the caller. The next turn reuses the resolved card.
    """

    def __init__(self, approval_id: str, tool_id: str) -> None:
        super().__init__(f"approval deferred: {tool_id}:{approval_id}")
        self.approval_id = approval_id
        self.tool_id = tool_id


class ToolCorrectionRequired(ValueError):
    """A bounded model action was refused but the run may safely retry."""


class AgentPlannerRuntime:
    # Workspace-bounded tools an autopilot run may execute without a human
    # round-trip. Everything else still parks on a real approval card.
    AUTOPILOT_TOOLS = frozenset({
        "worktree.bind",
        "worktree.write_file",
        "worktree.replace_exact",
        "worktree.read_file",
        "worktree.list",
        "worktree.search_text",
        "worktree.run",
        "worktree.verify",
        "worktree.sourceplan_draft",
        "worktree.diff",
    })

    def __init__(self, engine: Any, provider: PlannerProvider, *, max_turns: int = 8, observation_limit: int = 12, max_repair_cycles: int = 3, context_packet_builder: Any = None, execution_gateway: Any = None, compute_governor: Any = None, budget_tracker: Any = None, envelope_store: Any = None, crystal_planner: Any = None, crystal_learner: Any = None, adaptive_router: Any = None, governor: Any = None, memory_reader: Any = None, integration_coordinator: Any = None):
        self.engine = engine
        # D5: every real provider call, tool call and wall-clock slice is metered into the run budget.
        self.budget_tracker = budget_tracker or RunBudgetTracker(engine.store, emit=engine.emit)
        self.envelope_store = envelope_store
        self._supplied_decisions: dict[str, tuple[str, str]] = {}
        # D6: optional reviewed coding-crystal planner; it only supplies decisions, the loop still authorizes and executes.
        self.crystal_planner = crystal_planner
        self.crystal_learner = crystal_learner
        # D9: optional proposal-only router (BEAST_ADAPTIVE_ROUTER); it can only withhold crystal activation.
        self.adaptive_router = adaptive_router
        self._crystal_nominations: dict[str, str] = {}
        self.governor = governor  # Compute Governor spine: crystal proposals activate only behind admit
        self.memory_reader = memory_reader  # 4-tier memory contract: nominations feed admit, never grant
        self._crystal_sessions: dict[str, Any] = {}
        self._crystal_succeeded: dict[str, Any] = {}
        self.provider = provider
        self.max_turns = max(1, min(int(max_turns), 64))
        self.observation_limit = max(1, min(int(observation_limit), 50))
        self.max_repair_cycles = max(0, min(int(max_repair_cycles), 16))
        self.context_packet_builder = context_packet_builder
        self.execution_gateway = execution_gateway
        self.compute_governor = compute_governor
        self._context_cache: dict[str, Any] = {}
        self.planning_integrations = PlanningIntegrationRuntime(str(engine.workspace_root))
        if integration_coordinator is None:
            from app.kernel.agents.coder_integrations import CoderIntegrationCoordinator

            integration_coordinator = CoderIntegrationCoordinator(engine.workspace_root)
        self.integration_coordinator = integration_coordinator
        self._integration_packets: dict[str, dict[str, Any]] = {}
        # Phase 3: lifecycle transitions have a single owner (EffectAgentRuntime).
        self._lifecycle: Any = None

    def _transition(self, run_id: str, state: AgentRunState, *, error: str = "") -> None:
        """Apply a lifecycle transition through the Effect runtime owner."""
        if self._lifecycle is None:
            self._lifecycle = self.engine.effect_agent(run_id)
        self._lifecycle.advance(state, error=error)

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
            # CPU inference on 7B models needs 2-3 minutes per decision.
            # 180000ms = 3 minutes; max is capped at 180s (3 minutes) anyway.
            timeout_ms = float(os.environ.get("BEAST_AGENT_PLANNER_DECISION_TIMEOUT_MS", "180000"))
        # Autopilot tolerates a slower hosted/self-hosted model rather than
        # cutting a productive run off mid-edit.
        ceiling = 300.0 if AgentPlannerRuntime._autopilot(run) else 180.0
        return max(10.0, min(timeout_ms / 1000.0, ceiling))

    @staticmethod
    def _autopilot(run: dict[str, Any]) -> bool:
        """True when the operator delegated routine approvals to the runtime.

        Autopilot is an efficiency contract, not a reduction in evidence: every
        mutating tool still produces an approval record and a receipt. It only
        removes the human round-trip and a few bookkeeping detours that used to
        stall small models mid-edit.
        """
        request = run.get("request") if isinstance(run.get("request"), dict) else {}
        value = str(
            request.get("autonomy")
            or request.get("agent_autonomy")
            or os.environ.get("BEAST_AGENT_AUTONOMY")
            or ""
        ).strip().lower()
        if value in {"autopilot", "auto", "autonomous", "full_auto", "full-auto", "yolo"}:
            return True
        if value in {"manual", "governed", "supervised", "off", "interactive"}:
            return False
        # Legacy explicit opt-ins.
        return bool(request.get("full_auto") or request.get("auto_approve_tools"))

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

    def _get_mutation_retry_provider(self, original_provider: Any, run: dict[str, Any]) -> Any:
        """
        Return a stronger provider for mutation retries when the original provider failed.

        Prefers an explicitly configured NIM retry. Otherwise hosted models stay on their original provider.
        This gives the retry a better chance of producing valid structured output.

        For test/mock providers, falls back to original_provider to avoid
        trying to connect to real services.
        """
        # Detect test/mock providers - they typically don't have the standard provider classes
        provider_class_name = type(original_provider).__name__
        if provider_class_name in {"PlaceholderThenExact", "AlwaysPlaceholder", "PlaceholderThenBadRead", "StubOllama"}:
            return original_provider

        # If we have a NIM fallback configured, use it for the retry
        nim_model = str(os.environ.get("BEAST_NIM_MODEL") or "").strip()
        nim_base_url = str(os.environ.get("NVIDIA_NIM_BASE_URL") or "").strip()
        if nim_model and nim_base_url:
            try:
                from app.kernel.agents.nim_planner_provider import NIMPlannerProvider
                return NIMPlannerProvider(
                    model=nim_model,
                    base_url=nim_base_url,
                    route_dampener=self._get_route_dampener(run, "nim"),
                    route_id=f"nim:{nim_model}",
                    on_token=lambda t: None,
                    on_reasoning=lambda text: self.engine.emit(str(run.get("run_id") or ""), "agent.model.reasoning", {"text": text}),
                )
            except Exception:
                pass

        model_name = str(run.get("model") or "").strip()
        provider_name = str(run.get("provider") or "").strip().lower()
        if provider_name in {"nvidia_nim", "nim", "local_nim"} or (
            model_name.lower().startswith("nvidia/") or "nemotron" in model_name.lower()
        ):
            return original_provider

        # Try to construct a fresh Ollama provider with stricter settings
        try:
            from app.kernel.agents.ollama_planner_provider import OllamaPlannerProvider
            run_request = run.get("request") if isinstance(run.get("request"), dict) else {}
            base_url = str(run_request.get("ollama_base_url") or os.environ.get("BEAST_OLLAMA_BASE_URL") or os.environ.get("OLLAMA_HOST") or "http://127.0.0.1:11434")
            # Skip if model is a test model
            if model_name in {"planner-test", "test-model", "mock-model"}:
                return original_provider
            return OllamaPlannerProvider(
                model=model_name,
                base_url=base_url,
                timeout_seconds=max(60.0, float(os.environ.get("BEAST_OLLAMA_MUTATION_DECISION_TIMEOUT", "120"))),
                max_retries=1,
                temperature=0.0,
                seed=731947,
                route_dampener=self._get_route_dampener(run, "ollama"),
                route_id=f"ollama-retry:{model_name or 'default'}",
                on_token=lambda t: None,
            )
        except Exception:
            pass

        return original_provider

    def _get_route_dampener(self, run: dict[str, Any], kind: str) -> Any:
        from app.kernel.commons.route_damping import RouteFlapDampener
        from pathlib import Path
        root = Path(self.engine.workspace_root)
        if kind == "nim":
            return RouteFlapDampener(
                path=root / ".beast" / "agent_runs" / "nim_route_damping.json",
                suppress_at=float(os.environ.get("BEAST_NIM_ROUTE_SUPPRESS_AT", "400")),
                half_life_seconds=float(os.environ.get("BEAST_NIM_ROUTE_HALF_LIFE_SECONDS", "1800")),
            )
        return RouteFlapDampener(
            path=root / ".beast" / "agent_runs" / "ollama_route_damping.json",
            suppress_at=float(os.environ.get("BEAST_OLLAMA_ROUTE_SUPPRESS_AT", "400")),
            half_life_seconds=float(os.environ.get("BEAST_OLLAMA_ROUTE_HALF_LIFE_SECONDS", "1800")),
        )

    @staticmethod
    def _r323_contract_compact(prompt: str, budget: int) -> str:
        """Preserve decision grammar and meaningful prompt ends across compaction.

        Never grant authority or synthesize an executable tool decision here.
        """
        # BEAST_R323_CANONICAL_PROMPT_INTEGRITY
        grammar = (
            "BEAST ACTION PLANNER. Controller only.\n"
            "Return EXACTLY ONE JSON object; no top-level arrays, markdown, or multiple objects. Nested argument arrays are allowed.\n"
            "decision_type must be exactly tool, complete, or blocked.\n"
            "TOOL DECISION: decision_type=tool, tool_id must name one allowed tool; "
            "arguments must match its schema exactly and be based on observed files.\n"
            'DONE: {"decision_type":"complete","arguments":{},"summary":"Verified work complete."}\n'
            'BLOCK: {"decision_type":"blocked","arguments":{},"blocker":"Precise cause."}\n'
            "Never infer paths or replacement text from instructions. "
            "Only observed source and operator-scoped targets authorize tool arguments.\n"
        )
        # Keep the task header and most recent observations/authority rather than
        # slicing away either end. Avoid copying large, stale middle sections.
        space = max(0, int(budget) - len(grammar) - 2)
        if len(prompt) <= space:
            return grammar + "\n" + prompt
        if "OBSERVATIONS:" in prompt and "ALLOWED TOOLS:" in prompt:
            # The task, next phase and tool schemas are executable contracts.
            # Head/tail slicing used to remove all three from the middle.
            header, observations = prompt.split("OBSERVATIONS:", 1)
            # Observations have already been bounded by _compact_observation.
            # Cutting their JSON here loses the latest tool outcome and can
            # make the controller repeat an edit that already succeeded.
            return grammar + "\n" + header + "OBSERVATIONS:" + observations
        head = min(space // 4, 650)
        tail = max(0, space - head)
        return grammar + "\n" + prompt[:head] + "\n" + (prompt[-tail:] if tail else "")

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
        return AgentPlannerRuntime._r323_contract_compact(prompt, budget) + contract

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

    def _recent_model_delta_text(self, run_id: str, *, limit: int = 256) -> str:
        """Recover only model output emitted during the current planner turn."""
        try:
            events = self.engine.store.events(run_id, limit=limit)
        except Exception:
            return ""

        chunks: list[str] = []
        for event in reversed(events):
            event_type = str(event.get("event_type") or "")

            if event_type == "agent.planner.turn.started":
                break

            if event_type != "agent.model.delta":
                continue

            payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
            text = str(payload.get("text") or "")
            if text:
                chunks.append(text)

        return "".join(reversed(chunks)).strip()

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
    def _primary_retry_provider(cls, provider: Any, *, run: dict[str, Any] | None = None, _seen: set[int] | None = None) -> Any:
        """Resolve the exact requested inference provider, never a heuristic wrapper.

        Inspect only already-constructed provider objects. A missing or ambiguous
        route fails closed rather than falling through to deterministic planning.
        """
        # BEAST_R322_EXACT_PROVIDER_RESOLVER
        requested = str((run or {}).get("provider") or "").strip().lower()
        model = str((run or {}).get("model") or "").strip()
        if requested not in {"ollama", "local_ollama", "nim", "nvidia_nim", "local_nim"} or not model:
            return None
        wanted = "OllamaPlannerProvider" if requested in {"ollama", "local_ollama"} else "NIMPlannerProvider"
        seen: set[int] = set()
        matches: list[Any] = []

        def visit(node: Any) -> None:
            if node is None or id(node) in seen:
                return
            seen.add(id(node))
            if any(c.__name__ == wanted for c in type(node).__mro__):
                if str(getattr(node, "model", "")) == model:
                    matches.append(node)
                return
            for attribute in ("primary", "fallback"):
                visit(getattr(node, attribute, None))
            routes = getattr(node, "routes", None)
            if isinstance(routes, (list, tuple)):
                for route in routes:
                    nested = route.get("provider") if isinstance(route, dict) else getattr(route, "provider", None)
                    visit(nested)

        visit(provider)
        return matches[0] if len(matches) == 1 else None


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
    def _missing_mutation_fields(cls, decision: PlannerDecision) -> list[str]:
        """Return a list of required field names that are missing from the mutation decision."""
        missing: list[str] = []
        if decision.tool_id == "worktree.replace_exact":
            if not str(decision.arguments.get("path") or "").strip():
                missing.append("path")
            if str(decision.arguments.get("old_text") or "") == "":
                missing.append("old_text")
            if str(decision.arguments.get("new_text") or "") == "":
                missing.append("new_text")
        elif decision.tool_id == "worktree.write_file":
            if not str(decision.arguments.get("path") or "").strip():
                missing.append("path")
            if str(decision.arguments.get("content") or "") == "":
                missing.append("content")
        elif decision.tool_id == "worktree.bind":
            if not str(decision.arguments.get("path") or "").strip():
                missing.append("path")
        return missing

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
    def _invalid_retry_recovery_reason(cls, decision: PlannerDecision, state: PlannerState, workspace_root: str = "") -> str:
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
                # Also allow if the path exists under the workspace root,
                # so the agent isn't blocked on first-time file operations.
                # workspace_root defaults to empty string; if non-empty, check containment.
                if workspace_root:
                    target = pathlib.Path(path).resolve()
                    try:
                        wr = pathlib.Path(workspace_root).resolve()
                        if not (wr in target.parents and target.is_relative_to(wr)):
                            return "worktree.replace_exact retry recovery must stay within the already inspected target file set."
                    except Exception:
                        pass  # if workspace_root is invalid, skip the check
                else:
                    # No workspace_root constraint; only inspected_paths check applies
                    pass
            if old_text == "":
                return "worktree.replace_exact retry recovery requires non-empty old_text for existing files."
            return cls._invalid_mutation_reason(decision)
        if decision.tool_id == "worktree.write_file":
            path = str(decision.arguments.get("path") or "").strip()
            if inspected_paths and path and path not in inspected_paths:
                # Also allow if the path exists under the workspace root,
                # so the agent isn't blocked on first-time file operations.
                workspace_root = pathlib.Path(state.workspace_root).resolve()
                target = pathlib.Path(path).resolve()
                if not (workspace_root in target.parents and target.is_relative_to(workspace_root)):
                    return "worktree.write_file retry recovery must stay within the already inspected target file set."
        return cls._invalid_mutation_reason(decision)

    @classmethod
    def _mutation_argument_retry_prompt(cls, prompt: str, decision: PlannerDecision, reason: str, state: PlannerState) -> str:
        tool_id = decision.tool_id or "worktree.replace_exact"
        path = str(decision.arguments.get("path") or "").strip()
        latest = cls._latest_completed_read(state)
        result = latest.get("result") if isinstance(latest, dict) and isinstance(latest.get("result"), dict) else {}
        inspected_path = str(result.get("path") or "").strip()
        inspected_content = str(result.get("content") or "")[:1800]

        # Explicitly list missing fields
        missing = cls._missing_mutation_fields(decision)
        missing_str = f" MISSING FIELDS: {', '.join(missing)}" if missing else ""

        contract = (
            "\n\nEXACT MUTATION REQUIRED: The last mutation payload was structurally incomplete. "
            f"{reason}"
            f"{missing_str} "
            f"Return one valid planner JSON object for {tool_id} with exact bounded arguments for {path or inspected_path or 'the target file'}. "
            "Do not use empty strings for placeholder edit text. "
            "Every required field MUST be present and non-empty. "
            "If you cannot produce exact mutation text, choose workspace.read_range only for the specific target file once, or block with a precise reason."
            f"\nINSPECTED TARGET: {inspected_path}\nINSPECTED CONTENT:\n{inspected_content}"
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
        args = decision.arguments
        start, count = args.get("start_line", 1), args.get("line_count", 200)
        if not isinstance(start, int) or not isinstance(count, int) or start < 1 or count < 1:
            return False
        end = start + min(count, 1000) - 1
        coverage: list[tuple[int, int]] = []
        digest = None
        total_lines = None
        for item in reversed(state.observations):
            if (not isinstance(item, dict) or item.get("status") != "completed"
                    or item.get("tool_id") != "workspace.read_range" or item.get("truncated")):
                continue
            result = item.get("result") or {}
            scope = result.get("source_scope")
            if (str(result.get("path") or "").strip() != path or scope == "workspace_checkout"
                    or (not scope and result.get("target_execution") == "local_snapshot")):
                continue
            observed_digest = result.get("sha256")
            if digest is not None and digest != observed_digest:
                break
            if observed_digest:
                digest = observed_digest
            if total_lines is None and isinstance(result.get("total_lines"), int):
                total_lines = result["total_lines"]
            old_args = item.get("arguments") or {}
            requested_symbols = args.get("outline_symbols")
            old_symbols = old_args.get("outline_symbols")
            if args.get("include_outline") and (
                not old_args.get("include_outline")
                or (isinstance(requested_symbols, list) and
                    not all(symbol in (old_symbols if isinstance(old_symbols, list) else [])
                            for symbol in requested_symbols))
            ):
                continue
            first, last = result.get("start_line"), result.get("end_line")
            if result.get("content") and isinstance(first, int) and isinstance(last, int) and 1 <= first <= last:
                coverage.append((first, last))
            elif isinstance(total_lines, int) and start > total_lines and first == start:
                # The same out-of-range read already returned no lines.
                return True
        if isinstance(total_lines, int):
            end = min(end, total_lines)
        if end < start:
            return False
        next_line = start
        for first, last in sorted(coverage):
            if first > next_line:
                break
            next_line = max(next_line, last + 1)
            if next_line > end:
                return True
        return False

    def _covered_bound_ranges(self, state: PlannerState, path: str) -> list[tuple[int, int]]:
        ranges = []
        for observation in state.observations:
            if observation.get("tool_id") != "workspace.read_range" or observation.get("status") != "completed" or observation.get("truncated"):
                continue
            result = observation.get("result") or {}
            if result.get("path") != path or result.get("source_scope") != "bound_worktree":
                continue
            first, last = result.get("start_line"), result.get("end_line")
            if type(first) is int and type(last) is int and 1 <= first <= last and result.get("content"):
                ranges.append((first, last))
        return sorted(set(ranges))

    async def _help_duplicate_read(self, run: dict[str, Any], state: PlannerState, path: str) -> str:
        """Use existing read-only tools for one targeted lookup, not another blind read."""
        covered = self._covered_bound_ranges(state, path)
        hint = "Covered ranges: " + (", ".join(f"{a}–{b}" for a, b in covered[-8:]) or "(unknown)")
        if not self._local_binding_identity(run) or not covered:
            return hint
        objective = str(run.get("objective") or "")
        # Only use terms explicitly supplied by the operator, e.g. /copy
        # or a quoted identifier. No model call is needed for navigation.
        needle = re.search(r"(?:^|\s)/([a-zA-Z][a-zA-Z0-9_-]{1,31})(?=\s|[.,:!?]|$)|`([a-zA-Z_][a-zA-Z0-9_]{1,63})`", objective)
        if needle is None:
            return hint
        term = next(group for group in needle.groups() if group)
        search = {"path": path, "query": term, "limit": 24}
        try:
            matches = await self.engine.execute_tool(state.run_id, "workspace.search_text", search)
        except (ToolExecutionFailed, PermissionError, ValueError):
            return hint
        self._record_tool_budget(state.run_id, PlannerDecision(
            decision_type=PlannerDecisionType.TOOL, tool_id="workspace.search_text", arguments=search,
        ), matches, runtime_supplied=True)
        found = matches.get("result") or {}
        if found.get("source_scope") != "bound_worktree":
            return hint
        candidates = [m for m in found.get("matches", []) if isinstance(m, dict)
                      and m.get("path") == path and type(m.get("line")) is int
                      and not any(first <= m["line"] <= last for first, last in covered)]
        if not candidates:
            return hint
        # Prefer definitions over uses, then clip to the nearest evidence
        # boundaries so not one already-inspected line has to be read again.
        match = min(candidates, key=lambda item: (
            not bool(re.match(r"\s*(?:async\s+)?(?:def|class|function)\s+", str(item.get("preview") or ""))),
            item["line"],
        ))
        line = match["line"]
        start = max(1, line - 8, *(last + 1 for _, last in covered if last < line))
        end = min(line + 36, min((first - 1 for first, _ in covered if first > line), default=line + 36))
        arguments = {"path": path, "start_line": start, "line_count": end - start + 1}
        try:
            observation = await self.engine.execute_tool(state.run_id, "workspace.read_range", arguments)
        except (ToolExecutionFailed, PermissionError, ValueError):
            return hint
        self._record_tool_budget(state.run_id, PlannerDecision(
            decision_type=PlannerDecisionType.TOOL, tool_id="workspace.read_range", arguments=arguments,
        ), observation, runtime_supplied=True)
        result = observation.get("result") or {}
        if result.get("source_scope") != "bound_worktree" or result.get("path") != path:
            return hint
        state.observations.append(observation)
        state.observations = state.observations[-self.observation_limit:]
        self._save_state(state)
        return (f"{hint}. New bound-worktree evidence {path}:{result.get('start_line')}–"
                f"{result.get('end_line')}:\n{str(result.get('content') or '')[:2200]}")

    @staticmethod
    def _mutation_retry_prompt(prompt: str, path: str, help_text: str, objective: str) -> str:
        return (
            prompt[-2400:] + "\n\nCONTINUE THIS BOUND WORKTREE. No need to bind again. "
            f"Original objective: {objective[:900]}\n"
            f"Skipped an already covered read of {path}. {help_text}\n"
            "Use the exact evidence for a bounded edit, ask for a new range if needed, "
            "or report what evidence or authority is missing."
        )

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
        return cls._r323_contract_compact(prompt, budget) + contract

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
        target_provider = self._primary_retry_provider(provider, run=run)
        if target_provider is None:
            raise PlannerDecisionError(
                f"BEAST R3.22 REFUSE: exact inference provider unavailable or ambiguous for "
                f"{run.get('provider')}/{run.get('model')}"
            )
        retry_timeout = max(10.0, min(180.0, float(os.environ.get("BEAST_OLLAMA_MUTATION_DECISION_TIMEOUT", "90"))))
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
            model_decision = await asyncio.wait_for(
                self._metered_decision(target_provider, retry_prompt, run=run, turn=turn),
                timeout=retry_timeout,
            )
            self.engine.emit(run.get("run_id") or "", "agent.provider.mutation_decision_returned", {
                "turn": turn, "model": str(run.get("model") or ""),
                "decision_type": model_decision.decision_type.value,
                "tool_id": model_decision.tool_id,
                "blocker": model_decision.blocker if model_decision.decision_type is PlannerDecisionType.BLOCKED else "",
            })
            return model_decision
        except Exception as exc:
            self.engine.emit(run.get("run_id") or "", "agent.provider.first_mutation_retry_failed", {
                "turn": turn,
                "provider": str(run.get("provider") or ""),
                "model": str(run.get("model") or ""),
                "reason": f"{type(exc).__name__}: {exc}",
            })
            return None

    @classmethod
    def _preferred_tool_ids(cls, state: PlannerState, *, bound: bool = False) -> list[str]:
        bound = bound or cls._latest_index(state, {"worktree.bind"}, completed_only=True) >= 0
        mutated = cls._latest_index(state, {"worktree.write_file", "worktree.replace_exact"}, completed_only=True) >= 0
        inspected_file = cls._latest_index(state, {"workspace.read_range"}, completed_only=True) >= 0
        handoff_ready = bool(cls._passing_verification(state)) and bool(cls._latest_mutation_paths(state))
        if bound and not mutated and inspected_file:
            return [
                "worktree.replace_exact",
                "worktree.write_file",
                "workspace.read_range",
                "worktree.verify",
                *(["worktree.sourceplan_draft"] if handoff_ready else []),
            ]
        return [
            "workspace.index", "workspace.list", "workspace.search_text", "workspace.read_range",
            *([] if bound else ["worktree.bind"]), "worktree.sourceplan_draft", "worktree.replace_exact",
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
        target_provider = self._primary_retry_provider(provider, run=run)
        if target_provider is None:
            raise PlannerDecisionError(
                f"BEAST R3.22 REFUSE: exact inference provider unavailable or ambiguous for "
                f"{run.get('provider')}/{run.get('model')}"
            )
        retry_timeout = max(10.0, min(180.0, float(os.environ.get("BEAST_OLLAMA_MUTATION_DECISION_TIMEOUT", "90"))))
        retry_prompt = self._compact_retry_prompt(prompt)
        self.engine.emit(run.get("run_id") or "", "agent.provider.strong_retry", {
            "turn": turn,
            "provider": str(run.get("provider") or ""),
            "model": str(run.get("model") or ""),
            "reason": reason,
            "timeout_ms": int(retry_timeout * 1000),
        })
        try:
            model_decision = await asyncio.wait_for(
                self._metered_decision(target_provider, retry_prompt, run=run, turn=turn),
                timeout=retry_timeout,
            )
            self.engine.emit(run.get("run_id") or "", "agent.provider.mutation_decision_returned", {
                "turn": turn, "model": str(run.get("model") or ""),
                "decision_type": model_decision.decision_type.value,
                "tool_id": model_decision.tool_id,
                "blocker": model_decision.blocker if model_decision.decision_type is PlannerDecisionType.BLOCKED else "",
            })
            return model_decision
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
        if AgentPlannerRuntime._autopilot(run) and AgentPlannerRuntime._is_mutating_mode(run):
            # Autopilot goes straight to the isolated worktree; the mandatory
            # index pass only delays the first real edit.
            return None
        if isinstance(decision, PlannerDecision):
            if decision.decision_type == PlannerDecisionType.TOOL or str(decision.decision_type) == "tool":
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
            and (not is_read_only_run(run) or (
                tool.get("effect") == ToolEffect.READ.value and not tool.get("requires_worktree")
            ))
        }
        # Small models do better when the action vocabulary is narrow. After a
        # file has already been inspected and the worktree is bound, hide
        # exploratory tools so the next turn stays mutation-first.
        durable_bound = self._local_binding_identity(run) is not None
        preferred = self._preferred_tool_ids(state, bound=durable_bound)
        tools = [] if is_read_only_run(run) else [all_tools[key] for key in preferred if key in all_tools]
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
        integration_contract = self._integration_contract(run)
        semantic_contract = semantic_context_contract(run, state, char_limit=500 if late_compact_turn else 900 if compact_provider else 1600)
        plan_brief = {}
        try:
            plan_brief = self.planning_integrations.current_plan_brief(str(run.get("run_id") or state.run_id))
        except Exception:
            plan_brief = {}
        if late_compact_turn and plan_brief.get("steps"):
            # Small/compact models on late turns: keep the durable plan to step ids, statuses and the
            # active step's title so the prompt stays inside the compact budget.
            active_step = str(plan_brief.get("active_step_id") or "")
            plan_brief = {
                "active_step_id": active_step,
                "steps": [
                    {"step_id": step.get("step_id", ""), "status": step.get("status", ""),
                     **({"title": step.get("title", "")} if step.get("step_id") == active_step else {})}
                    for step in plan_brief.get("steps", [])
                ],
            }
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
            f"- {item['tool_id']}({','.join(item['required_arguments'])})"
            + (f" optional({','.join(item['optional_arguments'])})" if item['optional_arguments'] else "")
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
            if self._autopilot(run):
                if not durable_bound and "worktree.bind" not in observed_tools:
                    next_phase = (
                        "AUTOPILOT: the isolated worktree will be created automatically on the next turn. "
                        "Do not ask for approval."
                    )
                elif latest_failure is not None:
                    failure_class = str(latest_failure.get("analysis", {}).get("failure_class") or "unknown")
                    target_paths = latest_failure.get("target_paths") if isinstance(latest_failure.get("target_paths"), list) else []
                    target_clause = f" in {', '.join(str(path) for path in target_paths[:3])}" if target_paths else ""
                    next_phase = (
                        "AUTOPILOT REPAIR: the last verification failed"
                        f"{target_clause}. Read the failure, fix the smallest cause, and run the check again. "
                        f"You may keep editing other files if needed. Failure class: {failure_class}."
                    )
                else:
                    next_phase = (
                        "AUTOPILOT AGENT LOOP: you own this run. Inspect with worktree.read_file, worktree.list "
                        "or worktree.search_text; edit with worktree.replace_exact or worktree.write_file; run tests, "
                        "linters and builds with worktree.run. Iterate across as many files and edits as the objective "
                        "needs, and fix your own failures. When the work is really complete, run worktree.verify (the "
                        "authoritative gate), then choose complete. The runtime applies only a verified diff."
                    )
            elif not observed_tools and not durable_bound and not self._autopilot(run):
                next_phase = "NEXT REQUIRED: choose workspace.index, workspace.list, workspace.search_text, or workspace.read_range. Do not edit yet."
            elif not durable_bound and "worktree.bind" not in observed_tools and not self._autopilot(run):
                next_phase = "NEXT REQUIRED: inspect/index evidence is present; choose worktree.bind before any mutation."
            elif latest_failure is not None:
                failure_class = str(latest_failure.get("analysis", {}).get("failure_class") or "unknown")
                failure_label = (
                    "syntax"
                    if str(latest_failure.get("analysis", {}).get("slot_type") or "") == "syntax_region"
                    else failure_class
                )
                retryable = bool(latest_failure.get("analysis", {}).get("retryable_without_code_change"))
                target_paths = latest_failure.get("target_paths") if isinstance(latest_failure.get("target_paths"), list) else []
                failure_execution = str(latest_failure.get("target_execution") or latest_failure.get("execution_target") or "").strip()
                target_clause = f" in {', '.join(str(path) for path in target_paths[:2])}" if target_paths else ""
                transport_clause = f" on {failure_execution}" if failure_execution else ""
                if retryable:
                    next_phase = (
                        "NEXT REQUIRED: latest verifier failure appears retryable/environmental; rerun worktree.verify once "
                        f"or inspect the environment before editing code{transport_clause}. Failure class: {failure_label}."
                    )
                else:
                    next_phase = (
                        "NEXT REQUIRED: repair the latest verifier failure with one bounded edit"
                        f"{target_clause}, then rerun worktree.verify{transport_clause}. Failure class: {failure_label}."
                    )
            elif not any(tool in observed_tools for tool in {"worktree.replace_exact", "worktree.write_file"}):
                next_phase = ("NEXT REQUIRED: choose one bounded worktree.replace_exact edit. If exact old text is not observed, "
                              "read just the missing lines with workspace.read_range. Never rewrite a whole file.")
            elif not any(tool == "worktree.verify" and str(item.get("status") or "") == "completed" for item in state.observations if isinstance(item, dict)):
                next_phase = "NEXT REQUIRED: choose worktree.verify. A failed verify requires one smallest repair, not completion."
            elif not any(tool == "worktree.sourceplan_draft" and str(item.get("status") or "") == "completed" for item in state.observations if isinstance(item, dict)):
                next_phase = "NEXT REQUIRED: choose worktree.sourceplan_draft before complete."
            else:
                next_phase = "NEXT REQUIRED: complete with a concise summary of verified physical changes."
        else:
            next_phase = (
                "NEXT REQUIRED: read the attached files with workspace.read_range, then put your actual "
                "findings and inspection limits in the complete decision's summary. "
                "Use only observed facts and never request worktree tools."
            )
        bind_hint = ""
        if durable_bound and self._is_mutating_mode(run):
            identity = self._local_binding_identity(run)
            bind_hint = f"BIND DONE at {identity[3][:12]}. Ignore bind instructions already satisfied. "
        if bind_hint and self._local_tli_review(run):
            if not self._latest_mutation_paths(state):
                next_phase += (
                    ' Do not draft a handoff without a diff. If already implemented, complete with usage and '
                    'arguments={"no_change":{"observation_id":"bound read id","quote":"exact source"}}.'
                )
            elif not self._passing_verification(state):
                next_phase += " Use the user's requested test argv, not a substitute syntax check."
        prompt = (
            "BEAST ACTION PLANNER. Controller only.\n"
            "Return ONE JSON object on ONE line. No markdown, prose, top-level arrays, comments, or code.\n"
            "decision_type is exactly tool, complete, or blocked.\n"
            "STRICT TOOL SCHEMAS: required and optional argument keys listed below are the ONLY permitted keys. "
            "workspace.index accepts limit and include_symbols, NEVER path; use workspace.read_range to inspect a named file.\n"
            'worktree.verify command MUST be an argv array, e.g. ["python","-m","pytest","-q"], never a shell string.\n'
            "TOOL DECISION: use an allowed tool and an indexed, requested, or observed path. Never copy example paths or retry a missing file without new evidence.\n"
            'DONE: {"decision_type":"complete","arguments":{},"summary":"One sentence summary here."}\n'
            'BLOCK: {"decision_type":"blocked","arguments":{},"blocker":"Specific reason why you cannot proceed (not this template)."}\n'
            "Use exact arguments. No tool_id for done/block. Claim only observed work. "
            + (
                "For edits: inspect freely, edit every file the objective needs, run checks with worktree.run, "
                "then verify and complete. Never emit whole-file source for existing files; use bounded replacements. "
                "Never request promotion authority.\n"
                if self._autopilot(run)
                else "For edits: inspect, bind, replace, verify, sourceplan. Never emit whole-file source or request promotion authority.\n"
            )
            + f"MODE: {mode}\n"
            f"{target_hint}\n"
            f"OBJECTIVE: {objective}\n"
            f"TURN: {state.turn + 1}/{state.max_turns}; REPAIRS: {state.repair_cycles}/{state.max_repair_cycles}\n"
            f"{bind_hint}{next_phase}{verification_hint}\n"
            f"ALLOWED TOOLS:\n{tool_contract}\n"
            f"OBSERVATIONS: {json.dumps(observations, sort_keys=True, default=str, separators=(',', ':'))}"
            f"{authority_contract}"
            f"{context_contract}{integration_contract}{semantic_contract}{plan_contract}{repair_contract}"
        )
        if compact_provider:
            budget = 8000 if late_compact_turn else 12000
            return prompt if len(prompt) <= budget else self._r323_contract_compact(prompt, budget)
        return prompt

    @staticmethod
    def _integration_source_files(state: PlannerState) -> dict[str, str]:
        source_files: dict[str, str] = {}
        for item in state.observations:
            if not isinstance(item, dict) or item.get("status") != "completed":
                continue
            if item.get("tool_id") != "workspace.read_range":
                continue
            result = item.get("result") if isinstance(item.get("result"), dict) else {}
            path = str(result.get("path") or "").strip()
            content = str(result.get("content") or "")
            if path and content and path not in source_files:
                source_files[path] = content[:16000]
            if len(source_files) >= 6:
                break
        return source_files

    @staticmethod
    def _integration_diagnostics(state: PlannerState) -> str:
        failures = [
            AgentPlannerRuntime._compact_observation(item)
            for item in state.observations
            if isinstance(item, dict) and str(item.get("status") or "") != "completed"
        ]
        return json.dumps(failures[-6:], sort_keys=True, default=str, separators=(",", ":"))[:12000]

    @staticmethod
    def _bounded_integration_packet(result: dict[str, Any], advisory: list[dict[str, Any]]) -> dict[str, Any]:
        files = result.get("source_files") if isinstance(result.get("source_files"), dict) else {}
        return {
            "source_context": str(result.get("source_context") or "")[:12000],
            "diagnostic_context": str(result.get("diagnostic_context") or "")[:8000],
            "repo_map": str(result.get("repo_map") or "")[:6000],
            "source_files": {
                str(path)[:300]: str(content)[:8000]
                for path, content in list(files.items())[:6]
            },
            "advisory_context": [dict(item) for item in advisory[:8] if isinstance(item, dict)],
        }

    def _integration_contract(self, run: dict[str, Any]) -> str:
        run_id = str(run.get("run_id") or "")
        packet = self._integration_packets.get(run_id)
        if packet is None:
            checkpoint = run.get("checkpoint") if isinstance(run.get("checkpoint"), dict) else {}
            integration = checkpoint.get("coder_integrations") if isinstance(checkpoint.get("coder_integrations"), dict) else {}
            packet = integration.get("packet") if isinstance(integration.get("packet"), dict) else None
        if not packet:
            return ""
        rendered = json.dumps(packet, sort_keys=True, default=str, separators=(",", ":"))
        return f"\nCODER INTEGRATIONS: {rendered[:18000]}"

    def _emit_integration_events(self, run_id: str, events: Any) -> int:
        emitted = 0
        for event in events if isinstance(events, list) else []:
            if not isinstance(event, dict):
                continue
            event_type = str(event.get("event_type") or "agent.integration.failed")
            payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
            self.engine.emit(run_id, event_type, {**payload, "run_id": run_id})
            emitted += 1
        return emitted

    async def _prepare_coder_integrations(self, run: dict[str, Any], state: PlannerState) -> None:
        if not state.observations:
            return
        run_id = str(run.get("run_id") or state.run_id)
        checkpoint = run.get("checkpoint") if isinstance(run.get("checkpoint"), dict) else {}
        existing = checkpoint.get("coder_integrations") if isinstance(checkpoint.get("coder_integrations"), dict) else {}
        if existing.get("preflight_completed"):
            packet = existing.get("packet") if isinstance(existing.get("packet"), dict) else {}
            if packet:
                self._integration_packets[run_id] = packet
            return
        source_files = self._integration_source_files(state)
        source_context = "\n\n".join(source_files.values())
        request = run.get("request") if isinstance(run.get("request"), dict) else {}
        if request.get("transport") == "beast_coder_tli_v1" and not source_files:
            # A file index is not source evidence. Do not burn the once-per-run
            # preflight on it before the first successful file read.
            return
        try:
            result = await asyncio.to_thread(
                self.integration_coordinator.prepare,
                objective=str(run.get("objective") or ""),
                source_context=source_context,
                diagnostic_context=self._integration_diagnostics(state),
                source_files=source_files,
                task_metadata={
                    "provider": str(run.get("provider") or ""),
                    "model": str(run.get("model") or ""),
                    "run_id": run_id,
                    "task_name": "typed_agent_planner",
                    "read_only": is_read_only_run(run),
                    "files": list(source_files),
                    "implementation_target": request.get("implementation_target") or "",
                    "max_tokens": request.get("max_tokens", 8000),
                },
            )
            packet = self._bounded_integration_packet(
                result if isinstance(result, dict) else {},
                list(getattr(self.integration_coordinator, "advisory_context", []) or []),
            )
            emitted = self._emit_integration_events(run_id, result.get("events") if isinstance(result, dict) else [])
            self._integration_packets[run_id] = packet
            self.engine.merge_checkpoint(run_id, {
                "coder_integrations": {
                    **existing,
                    "preflight_completed": True,
                    "preflight_event_count": emitted,
                    "packet": packet,
                },
            })
        except Exception as exc:
            self.engine.emit(run_id, "agent.integration.failed", {
                "capability": "coder_integration_preflight",
                "status": "failed",
                "stage": "preflight",
                "operation": "prepare",
                "mode": "typed_planner",
                "reason": type(exc).__name__,
                "authority": "advisory_or_existing_gate_only",
                "run_id": run_id,
            })
            self.engine.merge_checkpoint(run_id, {
                "coder_integrations": {
                    **existing,
                    "preflight_completed": True,
                    "preflight_failed": type(exc).__name__,
                    "packet": {},
                },
            })

    @classmethod
    def _has_verified_sourceplan(cls, state: PlannerState) -> bool:
        verified = cls._latest_completed_observation(state, "worktree.verify") is not None
        sourceplan = cls._latest_completed_observation(state, "worktree.sourceplan_draft") is not None
        return verified and sourceplan

    async def _complete_coder_integrations(self, run_id: str) -> None:
        run = self.engine.store.get_run(run_id) or {}
        checkpoint = run.get("checkpoint") if isinstance(run.get("checkpoint"), dict) else {}
        existing = checkpoint.get("coder_integrations") if isinstance(checkpoint.get("coder_integrations"), dict) else {}
        if existing.get("postflight_completed"):
            return
        state = self._load_state(run_id)
        if normalize_state(str(run.get("state") or "")) is not AgentRunState.COMPLETED:
            return
        if not self._has_verified_sourceplan(state):
            return
        try:
            result = await asyncio.to_thread(
                self.integration_coordinator.complete,
                run_id=run_id,
                objective=str(run.get("objective") or ""),
                verified=True,
            )
            emitted = self._emit_integration_events(run_id, result.get("events") if isinstance(result, dict) else [])
            self.engine.merge_checkpoint(run_id, {
                "coder_integrations": {
                    **existing,
                    "postflight_completed": True,
                    "postflight_event_count": emitted,
                },
            })
        except Exception as exc:
            self.engine.emit(run_id, "agent.integration.failed", {
                "capability": "coder_integration_postflight",
                "status": "failed",
                "stage": "postflight",
                "operation": "complete",
                "mode": "typed_planner",
                "reason": type(exc).__name__,
                "authority": "advisory_or_existing_gate_only",
                "run_id": run_id,
            })
            self.engine.merge_checkpoint(run_id, {
                "coder_integrations": {
                    **existing,
                    "postflight_completed": True,
                    "postflight_failed": type(exc).__name__,
                },
            })

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

    async def _one_schema_correction(
        self, run: dict[str, Any], run_id: str, decision: PlannerDecision, turn: int,
        *, state: PlannerState | None = None,
    ) -> tuple[PlannerDecision | None, str]:
        """Ask the model once to fix a rejected schema, without executing or granting authority.
        """
        try:
            spec = self.engine.tool_registry.get(decision.tool_id)
        except Exception:
            # Unknown-tool handling remains with the existing tool runtime.
            return decision, ""

        schema = spec.input_schema if isinstance(spec.input_schema, dict) else {}
        properties = schema.get("properties") if isinstance(schema.get("properties"), dict) else {}
        allowed = sorted(properties)
        required = schema.get("required") if isinstance(schema.get("required"), list) else []
        def validate(args: dict[str, Any]) -> None:
            normalized = self.engine.tool_registry.validate_arguments(spec, args)
            # Accept normalization that only adds defaults or reorders keys;
            # reject only if it drops or changes user-supplied values.
            for key, value in args.items():
                if key not in normalized:
                    raise ValueError(f"normalization dropped required key: {key}")
                if normalized[key] != value:
                    raise ValueError(f"normalization altered key {key}: {value} -> {normalized[key]}")
            # Ensure all schema-required keys are present in the arguments.
            for key in required:
                if key not in args:
                    raise ValueError(f"missing required argument: {key}")

        try:
            validate(decision.arguments)
            return decision, ""
        except Exception as exc:
            first_error = f"{type(exc).__name__}: {exc}"
        self.engine.emit(run_id, "agent.planner.tool_arguments_refused", {
            "tool_id": decision.tool_id,
            "arguments": decision.arguments,
            "reason": first_error,
            "approval_created": False,
            "retry_available": True,
        })
        mutation = decision.tool_id in {"worktree.replace_exact", "worktree.write_file"}
        evidence = [
            item["result"] for item in (state.observations if state is not None and mutation else [])
            if isinstance(item, dict) and item.get("tool_id") == "workspace.read_range"
            and item.get("status") == "completed" and isinstance(item.get("result"), dict)
        ]
        evidence_paths = sorted({item["path"] for item in evidence if isinstance(item.get("path"), str)})
        mutation_context = (
            f"OBSERVED MUTATION PATHS: {json.dumps(evidence_paths)}\n"
            "Preserve any supplied path and copy exact old_text from observed source.\n"
            if mutation else ""
        )
        repair_prompt = (
            "BEAST TOOL-SCHEMA CORRECTION. Your previous tool decision was REJECTED "
            "before execution and before approval. Return exactly ONE JSON object "
            "with decision_type=tool, the SAME tool_id, and a validated arguments object. "
            "Do not change tools, execution target, or expand scope. "
            "Never invent paths, contents, permissions, or source changes. "
            f"TOOL_ID: {decision.tool_id}\n"
            f"ALLOWED_ARGUMENT_KEYS: {json.dumps(allowed)}\n"
            f"REQUIRED_ARGUMENT_KEYS: {json.dumps(required)}\n"
            f"ARGUMENT_SCHEMA: {json.dumps(schema, sort_keys=True)}\n"
            f"PREVIOUS_ARGUMENTS: {json.dumps(decision.arguments, sort_keys=True, default=str)}\n"
            f"REJECTION: {first_error}\n"
            f"{mutation_context}"
            f"OBJECTIVE: {str(run.get('objective') or '')[:500]}\n"
            "FORMAT: {\"decision_type\":\"tool\",\"tool_id\":\"<same ID>\","
            "\"arguments\":{...}}"
        )
        self.engine.emit(run_id, "agent.provider.tool_schema_retry", {
            "tool_id": decision.tool_id, "turn": turn, "original_reason": first_error,
            "permitted_keys": allowed, "required_keys": required,
        })
        try:
            candidate = await asyncio.wait_for(
                self._metered_decision(self.provider, repair_prompt, run=run, turn=turn),
                timeout=max(4.0, min(16.0, self._decision_timeout_seconds(run) / 2.0)),
            )
            if candidate.decision_type is not PlannerDecisionType.TOOL or candidate.tool_id != decision.tool_id:
                raise ValueError("correction changed the tool identity or decision type")
            if candidate.execution_target not in {"local", decision.execution_target}:
                raise ValueError("correction attempted to change the locked execution target")
            validate(candidate.arguments)
            if mutation:
                path = candidate.arguments.get("path")
                original_path = decision.arguments.get("path")
                if path is not None:
                    if evidence_paths and path not in evidence_paths:
                        raise ValueError("correction did not preserve an observed mutation path")
                    if original_path and path != original_path:
                        raise ValueError("correction changed the mutation path")
                if candidate.tool_id == "worktree.replace_exact":
                    old_text = candidate.arguments.get("old_text")
                    if not isinstance(old_text, str) or not old_text:
                        raise ValueError("correction requires non-empty old_text for existing files.")
                    if evidence_paths and path is not None:
                        if not any(
                            item.get("path") == path and old_text in str(item.get("content") or "") for item in evidence
                        ):
                            raise ValueError("correction requires exact old_text from the observed file")
                invalid = self._invalid_mutation_reason(candidate)
                if invalid:
                    raise ValueError(invalid)
        except Exception as exc:
            error = (
                f"REFUSE_INVALID_TOOL_ARGUMENTS:{decision.tool_id}: {first_error}; "
                f"bounded schema correction refused: {type(exc).__name__}: {exc}"
            )
            self.engine.emit(run_id, "agent.provider.tool_schema_retry_refused", {
                "tool_id": decision.tool_id, "turn": turn,
                "reason": f"{type(exc).__name__}: {exc}", "approval_created": False,
            })
            return None, error

        recovered = replace(candidate, execution_target=decision.execution_target, approval_id="")
        self.engine.emit(run_id, "agent.provider.tool_schema_retry_recovered", {
            "tool_id": decision.tool_id, "turn": turn,
            "original_arguments": decision.arguments, "recovered_arguments": recovered.arguments,
            "approval_created": False,
        })
        return recovered, ""

    def _create_autopilot_approval_record(self, run_id: str, run: dict[str, Any], decision: PlannerDecision, spec: Any) -> None:
        """Create and immediately resolve an auditable autopilot approval record.

        The record exists for auditability; the runtime never parks for
        operator approval on workspace-bounded worktree tools.
        """
        try:
            from app.kernel.agents.tool_models import ToolRisk
            risk_class = getattr(getattr(spec, "risk", None), "value", "governed")
        except Exception:
            risk_class = "governed"
        paths = [str(decision.arguments.get(key)) for key in ("path", "target_path") if decision.arguments.get(key)]
        approval_request = {
            "request_id": f"approval-{uuid.uuid4().hex[:16]}",
            "run_id": run_id,
            "tool_id": decision.tool_id,
            "summary": f"Autopilot authority: {getattr(spec, 'title', decision.tool_id)}",
            "risk_class": risk_class,
            "execution_target": decision.execution_target,
            "safe_arguments": decision.arguments,
            "affected_files": paths,
            "expected_side_effects": [
                "Bounded tool step inside the run's isolated worktree; nothing is applied to the main checkout."
            ],
            "autonomy": "autopilot",
        }
        self.engine.store.create_approval(run_id, approval_request)
        self.engine.store.resolve_approval(run_id, approval_request["request_id"], {
            "approved": True, "scope": "run", "operator": "autopilot",
            "reason": "operator_delegated_workspace_bounded_tools",
        })
        self.engine.emit(run_id, "agent.approval.autopilot_granted", {
            "approval_id": approval_request["request_id"],
            "tool_id": decision.tool_id,
            "scope": "run",
        })

    async def _authorize_tool(self, run: dict[str, Any], run_id: str, decision: PlannerDecision, *, defer: bool = False,
                              resume_approval_id: str = "") -> PlannerDecision | None:
        """Create and await an approval card instead of treating it as a tool error."""
        handoff_command = (
            verified_handoff_command(run)
            if decision.tool_id == "worktree.verify" and self._is_mutating_mode(run)
            else None
        )
        if handoff_command is not None and decision.arguments != {"command": handoff_command}:
            raise ValueError("REFUSE_UNBOUND_VERIFIED_HANDOFF_COMMAND")
        try:
            spec = self.engine.tool_registry.get(decision.tool_id)
        except Exception:
            if resume_approval_id:
                raise ValueError("DEFERRED_APPROVAL_TOOL_UNAVAILABLE")
            return decision
        if is_read_only_run(run) and (spec.effect != ToolEffect.READ or spec.requires_worktree):
            # /ask and /review are read-only conversations. Never hard-block a
            # mutation request — that strangles the model and ends the run as
            # policy_blocked. Emit guidance so the model can re-task with read
            # tools instead. The run stays alive.
            self.engine.emit(run_id, "agent.planner.read_only_guidance", {
                "tool_id": spec.tool_id,
                "reason": f"{spec.tool_id} is not available in read-only mode. "
                          f"Use workspace.read_range, workspace.list, workspace.search_text, "
                          f"or workspace.index to inspect files instead.",
            })
            return decision
        # H13.2: reject malformed functional tool arguments before
        # creating or reusing any operator approval.
        try:
            validated_args = self.engine.tool_registry.validate_arguments(
                spec, decision.arguments
            )
        except Exception as exc:
            # Never hard-block on bad arguments — guide the model to fix them.
            self.engine.emit(run_id, "agent.planner.tool_arguments_refused", {
                "tool_id": decision.tool_id,
                "arguments": decision.arguments,
                "reason": f"{type(exc).__name__}: {exc}",
                "approval_created": False,
            })
            return decision
        if validated_args != decision.arguments:
            # Normalize arguments but don't block — the runtime passes the
            # normalized arguments through to the tool.
            decision = replace(decision, arguments=validated_args)
        if resume_approval_id:
            approval = self.engine.store.get_approval(run_id, resume_approval_id)
            if not self._exact_deferred_approval_matches(run, decision, approval):
                raise ValueError("DEFERRED_APPROVAL_MISMATCH")
            return replace(decision, approval_id=resume_approval_id)
        if not getattr(spec, "requires_approval", False):
            # No per-call approval required, but still leave an auditable
            # autopilot grant record so the operator can see what ran.
            if self._autopilot(run):
                self._create_autopilot_approval_record(run_id, run, decision, spec)
            return decision
        # /permission off nukes all per-call approval prompts — the runtime
        # still writes audit records but never parks for operator approval.
        request = run.get("request") if isinstance(run.get("request"), dict) else {}
        if str(request.get("permission_mode") or "").strip().lower() == "nuked":
            self.engine.emit(run_id, "agent.permission.nuked_grant", {
                "tool_id": decision.tool_id,
                "scope": "run",
                "operator": "permission_nuked",
            })
            return replace(decision, approval_id=f"approval-nuked-{uuid.uuid4().hex[:8]}")
        if self._autopilot(run) and decision.tool_id in self.AUTOPILOT_TOOLS:
            # The operator delegated routine, workspace-bounded actions. Keep an
            # approval record so the audit trail and h12 authority check are
            # unchanged; the runtime simply grants it in the same turn.
            approval_id = f"approval-{uuid.uuid4().hex[:16]}"
            paths = [str(decision.arguments.get(key)) for key in ("path", "target_path") if decision.arguments.get(key)]
            approval_request = {
                "request_id": approval_id,
                "run_id": run_id,
                "tool_id": decision.tool_id,
                "summary": f"Autopilot authority: {getattr(spec, 'title', decision.tool_id)}",
                "risk_class": getattr(getattr(spec, "risk", None), "value", "governed"),
                "execution_target": decision.execution_target,
                "execution_target_payload": self._execution_target_payload(run, decision.execution_target),
                "capabilities": [{
                    "id": decision.tool_id,
                    "label": getattr(spec, "title", decision.tool_id),
                    "paths": paths,
                }],
                "safe_arguments": decision.arguments,
                "affected_files": paths,
                "expected_side_effects": [
                    "Bounded tool step inside the run's isolated worktree; nothing is applied to the main checkout."
                ],
                "autonomy": "autopilot",
            }
            self.engine.store.create_approval(run_id, approval_request)
            self.engine.store.resolve_approval(run_id, approval_id, {
                "approved": True,
                "scope": "run",
                "operator": "autopilot",
                "reason": "operator_delegated_workspace_bounded_tools",
            })
            self.engine.emit(run_id, "agent.approval.autopilot_granted", {
                "approval_id": approval_id,
                "tool_id": decision.tool_id,
                "scope": "run",
            })
            return replace(decision, approval_id=approval_id)
        approvals = self.engine.store.approvals(run_id)
        existing = next(
            (
                item for item in reversed(approvals)
                if item.get("status") == "approved" and not item.get("resume_claimed")
                and (
                    handoff_command is None
                    or ((item.get("request") or {}).get("tool_id") == decision.tool_id
                        and (item.get("request") or {}).get("safe_arguments") == decision.arguments)
                )
                and h12_approval_authorizes(
                    item, decision.tool_id, decision.arguments, decision.execution_target,
                    self._execution_target_payload(run, decision.execution_target),
                )
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
            "execution_target_payload": self._execution_target_payload(run, decision.execution_target),
            "capabilities": [{
                "id": decision.tool_id,
                "label": getattr(spec, "title", decision.tool_id),
                "paths": paths,
            }],
            "safe_arguments": decision.arguments,
            "affected_files": paths,
            "expected_side_effects": ["The agent may perform only this bounded tool step; SourcePlan remains required for promotion."],
        }
        deferred_action = {
            "decision": decision.as_dict(),
            "target_payload": request["execution_target_payload"],
        } if defer else None
        # Commit the approval and its resumable action together, before exposing the card.
        self.engine.store.create_approval(run_id, request, deferred_action=deferred_action)
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
        self._transition(run_id, AgentRunState.WAITING_FOR_APPROVAL)
        request_payload = run.get("request") if isinstance(run.get("request"), dict) else {}
        if deferred_action is not None:
            # Keep the checkpoint projection for older clients. The store owns the action.
            self.engine.merge_checkpoint(run_id, {"planner_deferred_approval": {
                "approval_id": approval_id, **deferred_action,
            }})
            raise ApprovalDeferred(approval_id, decision.tool_id)
        approved = await self._await_tool_approval(
            run_id,
            approval_id,
            timeout_seconds=float(request_payload.get("approval_timeout_seconds") or 3600),
        )
        if not approved:
            return None
        self._transition(run_id, AgentRunState.PLANNING)
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

    def _exact_deferred_approval_matches(self, run, decision, approval) -> bool:
        request = (approval or {}).get("request") or {}
        locked_target = str((run.get("request") or {}).get("execution_target") or "local")
        target = self._execution_target_payload(run, locked_target)
        return bool(
            approval and approval.get("run_id") == run.get("run_id")
            and decision.decision_type is PlannerDecisionType.TOOL
            and decision.execution_target == locked_target
            and request.get("tool_id") == decision.tool_id
            and request.get("safe_arguments") == decision.arguments
            and request.get("execution_target") == locked_target
            and request.get("execution_target_payload") == target
            and h12_approval_authorizes(approval, decision.tool_id, decision.arguments, locked_target, target)
        )

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

    @staticmethod
    def _is_broad_wave(run: dict[str, Any]) -> bool:
        request = run.get("request") if isinstance(run.get("request"), dict) else {}
        objective = str(run.get("objective") or "").casefold()
        return bool(request.get("long_horizon") or request.get("monorepo") or request.get("architecture_planning")
                    or any(term in objective for term in ("large", "monorepo", "cross-cutting", "many files")))

    @classmethod
    def _broad_wave_mutation_open(cls, run: dict[str, Any], state: PlannerState) -> bool:
        """A broad multi-file wave may keep mutating before verify; the model, not pre-enforcement, decides."""
        return cls._is_broad_wave(run) and 0 < len(set(cls._latest_mutation_paths(state))) < 32

    _local_binding_identity = staticmethod(local_binding_identity)

    def _normalize_model_tool_dialect(
        self,
        run: dict[str, Any],
        run_id: str,
        decision: PlannerDecision,
    ) -> PlannerDecision:
        roots: list[str | pathlib.Path] = [self.engine.workspace_root]
        identity = self._local_binding_identity(run)
        if identity is not None and identity[0]:
            roots.insert(0, identity[0])
        normalized = normalize_editor_tool_dialect(decision, roots=roots)
        if normalized != decision:
            self.engine.emit(run_id, "agent.provider.tool_dialect_normalized", {
                "source_tool_id": decision.tool_id,
                "source_arguments": decision.arguments,
                "tool_id": normalized.tool_id,
                "arguments": normalized.arguments,
                "reason": "known_coder_editor_protocol",
            })
        return normalized

    def _local_binding_error(self, identity: tuple[str, str, str, str]) -> str:
        return local_binding_error(self.engine.workspace_root, identity)

    @staticmethod
    def _local_tli_review(run: dict[str, Any]) -> bool:
        request = run.get("request") or {}
        return (
            AgentPlannerRuntime._is_mutating_mode(run)
            and request.get("transport") == "beast_coder_tli_v1"
            and str(request.get("execution_target") or "local") == "local"
            and request.get("post_session_closure") != "verified_handoff"
        )

    @classmethod
    def _passing_verification(cls, state: PlannerState) -> dict[str, Any]:
        latest = cls._latest_observation(state, "worktree.verify") or {}
        result = latest.get("result") or {}
        command = result.get("command")
        return result if (
            latest.get("status") == "completed" and result.get("ok") is True
            and result.get("returncode") == 0 and isinstance(command, list) and command
            and all(isinstance(arg, str) for arg in command)
        ) else {}

    def _no_change_evidence(self, run: dict[str, Any], state: PlannerState,
                            decision: PlannerDecision) -> dict[str, Any] | None:
        if not self._local_tli_review(run) or not self._local_binding_identity(run):
            return None
        if self._latest_mutation_paths(state) or (run.get("checkpoint") or {}).get("worktree_mutation_epoch"):
            return None
        claim = decision.arguments.get("no_change")
        if not isinstance(claim, dict) or not isinstance(decision.summary, str) or not decision.summary.strip():
            return None
        obs_id, quote = claim.get("observation_id"), claim.get("quote")
        if not isinstance(obs_id, str) or not obs_id or not isinstance(quote, str) or not 6 <= len(quote.strip()) <= 320:
            return None
        for item in reversed(state.observations):
            if (item.get("observation_id") != obs_id or item.get("status") != "completed"
                    or item.get("tool_id") != "workspace.read_range" or item.get("truncated")):
                continue
            result = item.get("result") or {}
            content = result.get("content")
            if result.get("source_scope") != "bound_worktree" or not isinstance(content, str) or quote not in content:
                return None
            root, _, _, base = self._local_binding_identity(run)
            git = ["git", "--no-optional-locks", "-C", root]
            try:
                clean = subprocess.run(
                    [*git, "status", "--porcelain", "--untracked-files=normal"],
                    capture_output=True, check=True, timeout=5,
                ).stdout == b""
                head = subprocess.run(
                    [*git, "rev-parse", "HEAD"], capture_output=True, check=True, timeout=5,
                ).stdout.decode().strip()
            except (OSError, subprocess.SubprocessError, UnicodeError):
                return None
            if clean and head == base:
                return {"observation_id": obs_id, "path": result.get("path")}
        return None

    def _finish_local_tli_review(self, state: PlannerState, summary: str, completion_mode: str,
                                 **receipt: Any) -> dict[str, Any]:
        state.status = "completed"
        state.blocker = ""
        state.final_summary = summary
        self._save_state(state)
        self._transition(state.run_id, AgentRunState.FINALIZING)
        self.engine.emit(state.run_id, "agent.run.advisory", {"text": summary})
        self.engine.emit(state.run_id, "agent.planner.completed", {
            "turns": state.turn, "summary": summary, "completion_mode": completion_mode,
            "promotion_authorized": False, **receipt,
        })
        self._transition(state.run_id, AgentRunState.COMPLETED)
        return self.engine.store.get_run(state.run_id) or {}

    def _finish_tli_diff(self, state: PlannerState) -> dict[str, Any]:
        verify = self._passing_verification(state)
        sourceplan = self._latest_completed_observation(state, "worktree.sourceplan_draft") or {}
        plan = (sourceplan.get("result") or {}).get("plan") or {}
        files = plan.get("files") if isinstance(plan.get("files"), list) else []
        files = [str(item) for item in files] or self._latest_mutation_paths(state)
        command = verify.get("command") or []
        summary = (
            f"Changes left in the isolated worktree for review: {', '.join(files[:8]) or 'no files'}. "
            f"Verification: {shlex.join(command)} (exit {verify.get('returncode')}). Nothing was applied to the main checkout."
        )
        return self._finish_local_tli_review(state, summary, "isolated_review", changed_files=files,
                                             verification={"command": command, "returncode": verify.get("returncode")})

    def _emit_worktree_diff(self, run: dict[str, Any], state: PlannerState) -> dict[str, Any]:
        """Publish the unified diff so the TLI can render it in red/green."""
        run_id = str(run.get("run_id") or state.run_id)
        current_run = self.engine.store.get_run(run_id) or run
        checkpoint = current_run.get("checkpoint") if isinstance(current_run.get("checkpoint"), dict) else {}
        worktree_root = str(checkpoint.get("worktree_root") or "").strip()
        if not worktree_root or checkpoint.get("worktree_remote"):
            return {}
        sourceplan = self._latest_completed_observation(state, "worktree.sourceplan_draft") or {}
        plan = (sourceplan.get("result") or {}).get("plan") or {}
        files = plan.get("files") if isinstance(plan.get("files"), list) else []
        files = [str(item) for item in files] or self._latest_mutation_paths(state)
        patch = read_worktree_diff(worktree_root, files)
        if not patch.get("diff"):
            return {}
        self.engine.emit(run_id, "agent.worktree.diff_ready", {
            "files": files,
            "worktree": worktree_root,
            "diff": patch["diff"],
            "added": patch.get("added", 0),
            "removed": patch.get("removed", 0),
            "truncated": bool(patch.get("truncated")),
        })
        return patch

    def _finish_tli_completion(self, run: dict[str, Any], state: PlannerState) -> dict[str, Any]:
        """Deliver the verified diff, or leave it isolated when delivery is unsafe.

        Autopilot's whole point is that the operator's file actually changes.
        When delivery is not requested, or a safety check blocks it, the run
        still completes as an isolated review so nothing is lost.
        """
        self._emit_worktree_diff(run, state)
        if not self._apply_on_completion(run):
            return self._finish_tli_diff(state)
        applied = self._apply_verified_worktree(run, state)
        if not applied.get("ok"):
            return self._finish_tli_diff(state)
        return self._finish_applied_diff(run, state, applied)

    @staticmethod
    def _apply_on_completion(run: dict[str, Any]) -> bool:
        """Autopilot delivers the verified diff; manual runs stay isolated."""
        request = run.get("request") if isinstance(run.get("request"), dict) else {}
        raw = request.get("apply_on_completion")
        if raw is None:
            return AgentPlannerRuntime._autopilot(run)
        return bool(raw)

    def _apply_verified_worktree(self, run: dict[str, Any], state: PlannerState) -> dict[str, Any]:
        """Write the verified SourcePlan diff into the operator workspace."""
        run_id = str(run.get("run_id") or state.run_id)
        current_run = self.engine.store.get_run(run_id) or run
        checkpoint = current_run.get("checkpoint") if isinstance(current_run.get("checkpoint"), dict) else {}
        worktree_root = str(checkpoint.get("worktree_root") or "").strip()
        base_commit = str(checkpoint.get("worktree_base_commit") or "").strip()
        sourceplan = self._latest_completed_observation(state, "worktree.sourceplan_draft") or {}
        plan = (sourceplan.get("result") or {}).get("plan") or {}
        files = plan.get("files") if isinstance(plan.get("files"), list) else []
        receipt = {
            "run_id": run_id,
            "worktree": worktree_root,
            "base_commit": base_commit,
            "files": [str(item) for item in files],
            "sourceplan_id": str(plan.get("plan_id") or ""),
        }
        if checkpoint.get("worktree_remote"):
            reason = "remote worktrees require an operator promotion step"
            self.engine.emit(run_id, "agent.worktree.apply_blocked", {**receipt, "reason": reason})
            return {"ok": False, "reason": reason, **receipt}
        if not worktree_root:
            reason = "run has no bound worktree"
            self.engine.emit(run_id, "agent.worktree.apply_blocked", {**receipt, "reason": reason})
            return {"ok": False, "reason": reason, **receipt}
        try:
            result = apply_workspace_files(
                workspace_root=self.engine.workspace_root,
                worktree_root=worktree_root,
                base_commit=base_commit,
                files=files,
            )
        except ApplyBlocked as exc:
            reason = str(exc)
            self.engine.emit(run_id, "agent.worktree.apply_blocked", {**receipt, "reason": reason})
            return {"ok": False, "reason": reason, **receipt}
        applied = [item["path"] for item in result.get("applied", [])]
        deleted = list(result.get("deleted") or [])
        self.engine.merge_checkpoint(run_id, {"workspace_apply": {
            "status": "applied",
            "workspace": result.get("workspace"),
            "worktree": result.get("worktree"),
            "files": applied,
            "deleted": deleted,
            "sourceplan_id": receipt["sourceplan_id"],
        }})
        self.engine.emit(run_id, "agent.worktree.applied", {
            **receipt,
            "workspace": result.get("workspace"),
            "applied": result.get("applied", []),
            "deleted": deleted,
        })
        # Autopromote the verified compute into the crystal lattice so the
        # operator sees crystal reuse and lattice compounding naturally.
        try:
            daemon = CrystalAutopromotionDaemon(self.engine.workspace_root)
            daemon_run = daemon.run_once()
            self.engine.emit(run_id, "agent.crystal.autopromotion", {
                "scanned": daemon_run.get("scanned", 0),
                "promoted_count": daemon_run.get("promoted_count", 0),
                "rejected_count": daemon_run.get("rejected_count", 0),
                "created_at": daemon_run.get("created_at"),
            })
        except Exception as exc:  # pragma: no cover - defensive surface
            self.engine.emit(run_id, "agent.crystal.autopromotion", {
                "scanned": 0,
                "promoted_count": 0,
                "rejected_count": 0,
                "created_at": None,
                "error": f"autopromotion: {type(exc).__name__}: {exc}"[:240],
            })
        return {"ok": True, **result, **receipt}

    def _finish_applied_diff(self, run: dict[str, Any], state: PlannerState, applied: dict[str, Any]) -> dict[str, Any]:
        verify = self._passing_verification(state)
        files = [str(item.get("path") or "") for item in applied.get("applied", []) if item.get("path")]
        deleted = list(applied.get("deleted") or [])
        command = verify.get("command") or []
        summary = f"Applied verified changes to the workspace: {', '.join(files[:8]) or 'no file content'}"
        if deleted:
            summary += f"; deleted {', '.join(deleted[:8])}"
        summary += f". Verification: {shlex.join(command)} (exit {verify.get('returncode')})."
        return self._finish_local_tli_review(
            state, summary, "applied_to_workspace",
            promotion_authorized=True,
            changed_files=files,
            deleted_files=deleted,
            verification={"command": command, "returncode": verify.get("returncode")},
            apply_receipt={
                "workspace": applied.get("workspace"),
                "worktree": applied.get("worktree"),
                "sourceplan_id": applied.get("sourceplan_id"),
            },
        )

    @classmethod
    def _autopilot_phase_decision(cls, run: dict[str, Any], state: PlannerState, decision: PlannerDecision | None = None) -> PlannerDecision | None:
        """Runtime bookkeeping for an autonomous run.

        The model owns *what* to change. The runtime owns the isolated worktree,
        the verifier and the review handoff, because those are mechanical and
        should never cost a model turn. Unlike the governed phase contract this
        does not force a redundant index pass or a post-bind read: the model may
        inspect and edit in whatever order it prefers.
        """
        observed = cls._observed_tool_ids(state)
        durable_bound = cls._local_binding_identity(run) is not None
        if not observed and not durable_bound:
            return None
        if not durable_bound and "worktree.bind" not in observed:
            return PlannerDecision(
                decision_type=PlannerDecisionType.TOOL,
                tool_id="worktree.bind",
                arguments={},
                rationale="Autopilot binds an isolated worktree once so edits are reviewable and reversible.",
            )
        mutation_paths = cls._latest_mutation_paths(state)
        if not mutation_paths:
            return None
        latest_mutation_index = cls._latest_index(state, {"worktree.write_file", "worktree.replace_exact"}, completed_only=True)
        latest_verify_index = cls._latest_index(state, {"worktree.verify"}, completed_only=True)
        latest_sourceplan_index = cls._latest_index(state, {"worktree.sourceplan_draft"}, completed_only=True)
        wants_completion = decision is None or decision.decision_type is PlannerDecisionType.COMPLETE
        # Agentic loop: while the model is actively choosing tools we never
        # interrupt it. It may read, edit many files, run tests, repair, and
        # keep iterating for as long as it wants.
        if not wants_completion:
            return None
        # The model asked to finish. Only mechanical bookkeeping remains.
        if latest_verify_index < latest_mutation_index:
            return PlannerDecision(
                decision_type=PlannerDecisionType.TOOL,
                tool_id="worktree.verify",
                arguments={"command": cls._autopilot_verification_command(state)},
                rationale="Autopilot verifies the isolated diff before closing the run.",
            )
        if not cls._passing_verification(state):
            # The verifier failed. Do not re-run the same failing command:
            # hand control back to the model so it can repair, then re-verify.
            return None
        if latest_sourceplan_index < latest_verify_index:
            return PlannerDecision(
                decision_type=PlannerDecisionType.TOOL,
                tool_id="worktree.sourceplan_draft",
                arguments={},
                rationale="Autopilot materializes the verified diff as the reviewable handoff.",
            )
        if cls._completion_ready(run, state):
            return PlannerDecision(
                decision_type=PlannerDecisionType.COMPLETE,
                arguments={},
                summary=cls._completion_summary_from_state(run, state),
                rationale="Autopilot closed the run after a verified, reviewable diff.",
            )
        return None

    @classmethod
    def _autopilot_verification_command(cls, state: PlannerState) -> list[str]:
        """Prefer the model's own test command over a generic syntax check."""
        prefixes = (
            ("python", "-m", "pytest"), ("python3", "-m", "pytest"), ("pytest",),
            ("python", "-m", "unittest"), ("npm", "test"), ("npm", "run", "test"),
            ("yarn", "test"), ("pnpm", "test"), ("bun", "test"),
            ("cargo", "test"), ("go", "test"), ("node", "--test"),
            ("dotnet", "test"), ("mvn", "test"), ("gradle", "test"),
            ("ruff", "check"), ("eslint",), ("tsc",),
        )
        for item in reversed(state.observations):
            if not isinstance(item, dict) or item.get("status") != "completed":
                continue
            if item.get("tool_id") not in {"worktree.run", "worktree.verify"}:
                continue
            result = item.get("result") if isinstance(item.get("result"), dict) else {}
            command = result.get("command")
            if not isinstance(command, list) or not command:
                continue
            parts = tuple(str(part) for part in command)
            if any(parts[: len(prefix)] == prefix for prefix in prefixes):
                return [str(part) for part in command]
        return cls._default_verification_command(state)

    @classmethod
    def _required_phase_decision(cls, run: dict[str, Any], state: PlannerState, decision: PlannerDecision | None = None) -> PlannerDecision | None:
        if not cls._is_mutating_mode(run):
            return None
        if cls._autopilot(run):
            return cls._autopilot_phase_decision(run, state, decision)
        observed = cls._observed_tool_ids(state)
        durable_bound = cls._local_binding_identity(run) is not None  # validated by _run_loop
        if not observed and not durable_bound:
            return None
        inspected = any(tool in observed for tool in {"workspace.index", "workspace.list", "workspace.search_text", "workspace.read_range"})
        if not inspected and not durable_bound and "worktree.bind" not in observed:
            return PlannerDecision(
                decision_type=PlannerDecisionType.TOOL,
                tool_id="workspace.index",
                arguments={"limit": 1200, "include_symbols": True},
                rationale="Mutating agent runs require an evidence index before worktree binding.",
            )
        if not durable_bound and "worktree.bind" not in observed:
            return PlannerDecision(
                decision_type=PlannerDecisionType.TOOL,
                tool_id="worktree.bind",
                arguments={},
                rationale="Mutating agent runs require an isolated worktree before any file mutation.",
            )
        inspected_paths = cls._inspected_paths(state)
        # A completed bounded mutation proves that the target path was already
        # resolved well enough to edit.  Do not spend the following turn on a
        # redundant source-workspace read; the isolated worktree must be
        # verified next, especially when the run is at its turn budget edge.
        if not inspected_paths and not cls._latest_mutation_paths(state):
            targeted_path = cls._targeted_read_path(run)
            if (
                isinstance(decision, PlannerDecision)
                and decision.decision_type is PlannerDecisionType.TOOL
                and decision.tool_id in {"worktree.replace_exact", "worktree.write_file"}
                and str(decision.arguments.get("path") or "").strip() == targeted_path
                and not cls._invalid_mutation_reason(decision)
            ):
                return None
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
            # Review-only TLI runs may need a second file edit and a specific
            # user-requested verifier. Don't replace that choice with py_compile.
            if cls._local_tli_review(run):
                return None
            if (
                cls._is_broad_wave(run)
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
            mutation_paths
            and isinstance(latest_verify, dict)
            and cls._passing_verification(state)
            and latest_verify_index >= 0
            and latest_sourceplan_index < latest_verify_index
        ):
            return PlannerDecision(
                decision_type=PlannerDecisionType.TOOL,
                tool_id="worktree.sourceplan_draft",
                arguments={},
                rationale="A verified worktree diff must be materialized into SourcePlan before completion.",
            )
        if (
            mutation_paths
            and latest_verify_index >= latest_mutation_index
            and latest_sourceplan_index >= latest_verify_index
            and cls._completion_ready(run, state)
        ):
            return PlannerDecision(
                decision_type=PlannerDecisionType.COMPLETE,
                arguments={},
                summary="Completed bounded changes; verification passed and SourcePlan evidence is ready.",
                rationale="Fresh verification and handoff evidence satisfy the coding loop completion contract.",
            )
        return None

    @classmethod
    def _ground_read_only_completion(
        cls, run: dict[str, Any], state: PlannerState, decision: PlannerDecision,
    ) -> PlannerDecision:
        """Do not report a review of an attachment without a successful file read."""
        if not is_read_only_run(run) or decision.decision_type is not PlannerDecisionType.COMPLETE:
            return decision
        request = run.get("request") if isinstance(run.get("request"), dict) else {}
        files = request.get("context_files")
        if not isinstance(files, list):
            return decision
        inspected = cls._inspected_paths(state)
        for path in files:
            if not isinstance(path, str) or not path.strip() or path in inspected:
                continue
            reads = [item for item in state.observations if isinstance(item, dict)
                     and item.get("tool_id") == "workspace.read_range"
                     and (item.get("arguments") or {}).get("path") == path]
            if any(item.get("status") == "completed" for item in reads):
                continue
            if reads:
                return PlannerDecision(
                    decision_type=PlannerDecisionType.BLOCKED, arguments={},
                    blocker=f"Could not read attached file {path}: {reads[-1].get('error') or 'read failed'}",
                )
            return PlannerDecision(
                decision_type=PlannerDecisionType.TOOL, tool_id="workspace.read_range",
                arguments={"path": path, "start_line": 1, "line_count": 80},
                rationale="Inspect the attached file before reporting review findings.",
            )
        return decision

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
        if not (latest_verify_index > latest_mutation_index >= 0 and latest_sourceplan_index > latest_verify_index):
            return False
        if not AgentPlannerRuntime._passing_verification(state):
            return False
        if AgentPlannerRuntime._local_tli_review(run):
            sourceplan = state.observations[latest_sourceplan_index]
            plan = (sourceplan.get("result") or {}).get("plan") or {}
            files = plan.get("files")
            return isinstance(files, list) and bool(set(files) & set(AgentPlannerRuntime._latest_mutation_paths(state)))
        return True

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

    def _review_incomplete(self, state: PlannerState, reason: str, coverage: str) -> dict[str, Any]:
        run_id = state.run_id
        state.status = "review_incomplete"
        state.final_summary = ""
        state.blocker = reason
        self._save_state(state)
        self.engine.emit(run_id, "agent.planner.review_incomplete", {
            "state": "failed", "ok": False, "completion_mode": "read_only_review_incomplete",
            "error": reason, "coverage": coverage,
        })
        self._transition(run_id, AgentRunState.FAILED, error=reason)
        return self.engine.store.get_run(run_id) or {}

    def _emit_stream_interception(self, run: dict[str, Any], usage: dict[str, Any], turn: int) -> None:
        run_id = str(run.get("run_id") or "")
        interception = usage.get("stream_interception")
        if isinstance(interception, dict):
            self.engine.emit(run_id, "agent.stream.interception", {
                "turn": turn,
                "provider": run.get("provider"),
                "model": run.get("model"),
                "stop_reason": str(interception.get("stop_reason") or ""),
                "tokens_emitted": int(interception.get("tokens_emitted") or 0),
                "raw_chunks_seen": int(interception.get("raw_chunks_seen") or 0),
                "upstream_cancel_requested": bool(interception.get("upstream_cancel_requested")),
                "upstream_cancel_calls": int(interception.get("upstream_cancel_calls") or 0),
                "savings": interception.get("savings") if isinstance(interception.get("savings"), dict) else {},
            })

    async def _finish_file_review(
        self, run: dict[str, Any], state: PlannerState, evidence: ReviewEvidence,
    ) -> dict[str, Any]:
        run_id = state.run_id
        coverage = evidence.coverage()
        if evidence.blocker:
            return self._review_incomplete(state, evidence.blocker, coverage)
        if not any(evidence.visible.values()) and any(evidence.totals.values()):
            return self._review_incomplete(state, "No complete source lines fit in the review context.", coverage)
        # Use the selected Ollama model directly when it can be resolved,
        # rather than allowing a heuristic or a different model to answer.
        provider = self._primary_retry_provider(self.provider, run=run) or self.provider
        reason = ""
        timeout = review_timeout_seconds(run)
        explain = explains_attached_files(run)
        native = not explain and getattr(provider, "supports_native_file_review", False) is True
        for attempt in (1, 2):
            self.engine.raise_if_cancelled(run_id)
            # Focused explanations use the numbered source as the only input
            # evidence. Do not append the unrelated initial preflight excerpt.
            integration_context = "" if evidence.symbol_focused else self._integration_contract(run)
            self.engine.emit(run_id, "agent.planner.review_attempt", {
                "attempt": attempt, "coverage": coverage, "timeout_seconds": timeout,
                "source_mode": "symbol_focused" if evidence.symbol_focused else "file_ranges",
                "integration_context_appended": bool(integration_context),
            })
            objective = str(run.get("objective") or "")
            prompt = evidence.explanation_prompt(objective, reason) if explain else evidence.prompt(objective, reason, native=native)
            prompt += integration_context
            started = time.monotonic()
            text = ""
            try:
                answer = await asyncio.wait_for(
                    self._metered_decision(provider, prompt, run=run, turn=state.turn + attempt),
                    timeout=timeout,
                )
                text, reason = evidence.explanation_answer(answer) if explain else evidence.answer(answer, native=native)
                outcome = "accepted" if text else "evidence_rejected"
            except TimeoutError:
                outcome, reason = "timeout", "Ollama review generation timed out." if native else "Review generation timed out."
            except ReviewPacketError as exc:
                outcome, reason = "invalid_packet", str(exc)
            except PlannerDecisionError as exc:
                outcome, reason = "provider_refused", str(exc)[:300]
            except OSError:
                outcome, reason = "transport_error", "Review provider did not return a usable response."
            self.engine.raise_if_cancelled(run_id)
            route = getattr(provider, "last_route", {}) or {}
            usage = getattr(provider, "last_usage", {}) or {}
            if isinstance(usage, dict):
                self._emit_stream_interception(run, usage, state.turn + attempt)
            retry = attempt == 1 and outcome in {"evidence_rejected", "invalid_packet"}
            self.engine.emit(run_id, "agent.planner.review_result", {
                "attempt": attempt, "accepted": bool(text), "provider": run.get("provider"),
                "model": run.get("model"), "route": route.get("route_kind"),
                "outcome": outcome, "reason": reason, "retry_available": retry,
                "elapsed_ms": round((time.monotonic() - started) * 1000),
                "timeout_seconds": timeout,
                **{key: usage.get(key) for key in (
                    "num_ctx", "num_predict", "done_reason", "eval_count", "prompt_eval_count",
                )},
            })
            if text:
                state.status = "completed"
                state.final_summary = text
                state.last_decision = answer.as_dict()
                self._save_state(state)
                self._transition(run_id, AgentRunState.FINALIZING)
                self.engine.emit(run_id, "agent.run.advisory", {
                    "text": text, "message": "Read-only review delivered. No files were changed.",
                    "coverage": coverage,
                })
                self.engine.emit(run_id, "agent.planner.completed", {
                    "turns": state.turn, "summary": text, "completion_mode": "read_only_advisory",
                    "observation_count": len(state.observations), "coverage": coverage,
                })
                self._transition(run_id, AgentRunState.COMPLETED)
                return self.engine.store.get_run(run_id) or {}
            self.engine.emit(run_id, "agent.planner.review_answer_rejected", {
                "attempt": attempt, "outcome": outcome, "reason": reason, "retry_available": retry,
            })
            if not retry:
                break
        suffix = " after one retry" if attempt == 2 else ""
        kind = "explanation" if explain else "review"
        detail = f"File read succeeded, but no grounded {kind} was produced{suffix}. {reason}"
        return self._review_incomplete(state, detail, coverage)

    async def _metered_decision(self, provider: Any, prompt: str, *, run: dict[str, Any], turn: int) -> PlannerDecision:
        decision = await provider.next_decision(prompt, run=run, turn=turn)
        run_id = str(run.get("run_id") or "")
        if run_id:
            try:
                usage = getattr(provider, "last_usage", None)
                self.budget_tracker.record_model_turn(
                    run_id, prompt=str(prompt or ""), decision=decision,
                    usage=usage if isinstance(usage, dict) else None,
                )
            except Exception as exc:
                self.engine.emit(run_id, "agent.budget.failed", {"stage": "model_turn", "reason": type(exc).__name__})
        return decision

    async def _recover_exact_edit_with_swarm(
        self, run: dict[str, Any], state: PlannerState, original: PlannerDecision, failure: str,
    ) -> PlannerDecision | None:
        from app.kernel.agents.swarm_specialist import specialist_enabled

        read_loop = failure == "post_bind_read_loop" and original.tool_id == "workspace.read_range"
        if not specialist_enabled() or (not read_loop and original.tool_id != "worktree.replace_exact") or is_read_only_run(run):
            return None
        run_id = state.run_id
        current = self.engine.store.get_run(run_id) or {}
        identity = self._local_binding_identity(current)
        if identity is None or await asyncio.to_thread(self._local_binding_error, identity):
            return None
        if original.execution_target != "local":
            return None

        from app.kernel.agents.swarm_recovery import recover, snapshot_refresh_arguments

        # Claim before dispatch so a paused or resumed run cannot repeat it.
        if not self.engine.store.claim_swarm_recovery(run_id):
            return None
        try:
            target = "" if read_loop else str(original.arguments.get("path") or "").strip()
            root = pathlib.Path(identity[0]).resolve()
            refresh = await asyncio.to_thread(snapshot_refresh_arguments, root, state.observations, target)
            if refresh:
                read = PlannerDecision(decision_type=PlannerDecisionType.TOOL,
                                       tool_id="workspace.read_range", arguments=refresh)
                try:
                    observation = await self.engine.execute_tool(run_id, read.tool_id, read.arguments)
                except ToolExecutionFailed as exc:
                    observation = exc.observation.as_dict()
                self._record_tool_budget(run_id, read, observation, runtime_supplied=True)
                result = observation.get("result") or {}
                if result.get("path") == refresh["path"] and result.get("source_scope") == "bound_worktree":
                    state.observations.append(observation)
                    state.observations = state.observations[-self.observation_limit:]
                    self._save_state(state)
            args, reason, receipt = await recover(
                workspace=pathlib.Path(self.engine.workspace_root).resolve(),
                root=root,
                observations=state.observations,
                target=target,
                objective=str(run.get("objective") or ""),
                cause=failure,
                run_id=run_id,
                env=os.environ,
                circuits=getattr(getattr(self.integration_coordinator, "runtime_governor", None), "circuit_state", None),
                timeout=60,
            )
        except Exception as exc:
            args, reason, receipt = None, f"recovery_error:{type(exc).__name__}", {}
        status = "fired" if args else "skipped"
        self.engine.emit(run_id, f"agent.integration.{status}", {
            **receipt,
            "capability": "swarm_recovery",
            "status": status,
            "stage": "proposal",
            "trigger": failure,
            "turn": state.turn + 1,
            "reason": reason,
            "authority": "advisory_or_existing_gate_only",
            "effect_committed": False,
        })
        if receipt.get("generated"):
            try:
                self.budget_tracker.record_model_turn(run_id, prompt="", decision=args or {},
                                                      usage=receipt.get("usage"))
            except Exception as exc:
                self.engine.emit(run_id, "agent.budget.failed", {"stage": "swarm_recovery", "reason": type(exc).__name__})
        if args:
            return PlannerDecision(decision_type=PlannerDecisionType.TOOL,
                                   tool_id="worktree.replace_exact", arguments=args,
                                   rationale="Local swarm proposed an evidence-grounded exact edit.")
        return None

    def _record_tool_budget(
        self, run_id: str, decision: PlannerDecision, observation: dict[str, Any], *, runtime_supplied: bool = False,
    ) -> None:
        supplied = None if runtime_supplied else self._supplied_decisions.pop(run_id, None)
        source = supplied[0] if supplied and supplied[1] == decision.tool_id else "runtime"
        try:
            self.budget_tracker.record_tool_call(
                run_id, tool_id=str(decision.tool_id or ""), status=str(observation.get("status") or "failed"), source=source,
            )
        except Exception as exc:
            self.engine.emit(run_id, "agent.budget.failed", {"stage": "tool_call", "reason": type(exc).__name__})

    def _crystal_decision(self, run_id: str, run: dict[str, Any], state: PlannerState) -> PlannerDecision | None:
        if self.crystal_planner is None:
            return None
        if run_id not in self._crystal_sessions and not self._route_allows_crystal(run_id, run):
            self._crystal_sessions[run_id] = None
        if run_id not in self._crystal_sessions:
            try:
                nominated = self._crystal_nominations.pop(run_id, "")
                session = (self.crystal_planner.activate(run, run_id, engine=self.engine, nominated_crystal_id=nominated)
                           if nominated else self.crystal_planner.activate(run, run_id, engine=self.engine))
            except Exception as exc:
                self.engine.emit(run_id, "agent.crystal.refused", {"reason": f"activation_error:{type(exc).__name__}"})
                session = None
            self._crystal_sessions[run_id] = session
        session = self._crystal_sessions.get(run_id)
        if session is None:
            return None
        try:
            decision = session.next_decision(run, state)
        except Exception as exc:
            decision = None
            with contextlib.suppress(Exception):
                session.abort(f"session_error:{type(exc).__name__}")
        if decision is None:
            if getattr(session, "aborted", "") or getattr(session, "succeeded", False):
                self._crystal_sessions[run_id] = None
            return None
        if decision.decision_type is PlannerDecisionType.TOOL and decision.tool_id not in CRYSTAL_REVIEWED_TOOLS:
            # Fail closed: a crystal may only drive reviewed coding ops, whatever its recipe claims.
            with contextlib.suppress(Exception):
                session.abort("unreviewed_tool")
            self.engine.emit(run_id, "agent.crystal.refused", {"reason": "unreviewed_tool", "tool_id": str(decision.tool_id or "")})
            self._crystal_sessions[run_id] = None
            return None
        return decision

    def _route_allows_crystal(self, run_id: str, run: dict[str, Any]) -> bool:
        governor = getattr(self, "governor", None)
        if self.adaptive_router is None:
            # An enforcing governor has no route to admit, so no crystal proposal runs.
            return governor is None or not getattr(governor, "enforce", False)
        try:
            decision = self.adaptive_router.route_run(run)
        except Exception as exc:
            self.engine.emit(run_id, "agent.route.failed", {"reason": type(exc).__name__})
            return False  # fail closed: no route, no crystal proposal
        body = decision.to_dict()
        self.engine.emit(run_id, "agent.route.decision", {key: body[key] for key in (
            "route", "band", "similarity", "fingerprint_compatible", "crystal_id", "envelope_digest",
            "demotion_signal", "verifier", "proposal_only", "execution_granted", "digest")})
        if body["route"] != "crystal_replay":
            return False
        if governor is not None and not self._governor_admits_crystal(run_id, body):
            self._crystal_nominations.pop(run_id, None)  # a stale nomination never outlives a refusal
            return False
        self._crystal_nominations[run_id] = str(body["crystal_id"])  # D6 still validates and gates this crystal
        return True

    def _governor_admits_crystal(self, run_id: str, route: dict[str, Any]) -> bool:
        from app.kernel.governance.governor_spine import Episode, Proposal

        history = self.__dict__.setdefault("_governor_signatures", {}).setdefault(run_id, [])
        memory = None
        reader = getattr(self, "memory_reader", None)  # governor_spine memory contract (Perceive, cheapest-first)
        if reader is not None:
            try:
                read = reader.read({"crystal_id": str(route["crystal_id"]), "run_id": run_id})
                memory = read.admission_inputs()
                self.engine.emit(run_id, "agent.memory.read", read.task_envelope_fields())
            except Exception as exc:
                self.engine.emit(run_id, "agent.memory.failed", {"reason": type(exc).__name__})
        proposal = Proposal(kind="crystal", crystal_id=str(route["crystal_id"]), route_decision=route, memory=memory)
        try:
            decision = self.governor.admit(Episode(run_id=run_id, signatures=tuple(history)), proposal)
        except Exception as exc:
            self.engine.emit(run_id, "agent.governor.failed", {"reason": type(exc).__name__})
            return False  # fail closed
        history.append(proposal.signature())
        self.engine.emit(run_id, "agent.governor.decision", {
            "outcome": decision.outcome, "reasons": list(decision.reasons), "enforced": decision.enforced,
            "receipt_id": decision.receipt_id, "crystal_id": proposal.crystal_id})
        return decision.permits()

    def _seal_episode(self, run_id: str) -> None:
        try:
            envelope = EpisodeEnvelopeBuilder().build(self.engine.store, run_id)
            stored = False
            if self.envelope_store is not None:
                self.envelope_store.put(envelope)
                stored = True
            self.engine.emit(run_id, "agent.episode.sealed", {
                "envelope_digest": envelope.envelope_digest,
                "task_family": envelope.task_family,
                "verification": dict(envelope.verification),
                "budget": dict(envelope.budget),
                "stored": stored,
            })
        except Exception as exc:
            self._crystal_succeeded.pop(run_id, None)
            self.engine.emit(run_id, "agent.episode.seal_failed", {"reason": f"{type(exc).__name__}: {exc}"[:240]})
            return
        session = self._crystal_succeeded.pop(run_id, None)
        if session is None or not hasattr(self.crystal_planner, "on_reuse_sealed"):
            return
        try:
            accounted = self.crystal_planner.on_reuse_sealed(session, envelope)
            if accounted:
                self.engine.emit(run_id, "agent.crystal.reduction_receipt", {
                    "receipt_id": accounted["receipt"]["receipt_id"], "kind": accounted["receipt"]["provenance"]["kind"],
                    "credited": bool(accounted["entry"].get("credited")), "units": accounted["entry"].get("units", 0.0),
                    "reason": accounted["entry"].get("reason", ""),
                })
        except Exception as exc:
            self.engine.emit(run_id, "agent.crystal.reduction_failed", {"reason": f"{type(exc).__name__}: {exc}"[:240]})

    async def _learn_crystal(self, run_id: str) -> None:
        if self.crystal_learner is None:
            return
        try:
            result = await asyncio.to_thread(self.crystal_learner.learn, run_id, engine=self.engine)
        except Exception as exc:
            self.engine.emit(run_id, "agent.crystal.formation_failed", {
                "reason": f"{type(exc).__name__}: {exc}"[:240],
            })
            return
        if not isinstance(result, dict):
            return
        event_type = "agent.crystal.formed" if result.get("status") == "promoted" else "agent.crystal.formation_refused"
        self.engine.emit(run_id, event_type, result)

    async def run(self, run_id: str, max_turns_this_call: int | None = None, *, defer_approval: bool = False) -> dict[str, Any]:
        run = self.engine.store.get_run(run_id)
        if not run:
            return await self._run_loop(run_id, max_turns_this_call=max_turns_this_call, defer_approval=defer_approval)
        _terminal_str = {s.value for s in TERMINAL_STATES}
        if str(run.get("state") or "created") in _terminal_str:
            return run
        self.budget_tracker.start(run_id)
        if max_turns_this_call is None and self._autopilot(run):
            try:
                max_turns_this_call = max(1, int(os.environ.get("BEAST_AGENT_AUTOPILOT_MAX_TURNS", "48")))
            except ValueError:
                max_turns_this_call = 48
        try:
            result = await self._run_loop(run_id, max_turns_this_call=max_turns_this_call, defer_approval=defer_approval)
        finally:
            self._supplied_decisions.pop(run_id, None)
            session = self._crystal_sessions.pop(run_id, None)
            if session is not None and hasattr(session, "sync"):
                try:
                    session.sync(self._load_state(run_id))  # runtime-enforced closure steps still settle the crystal
                    if getattr(session, "succeeded", False):
                        self._crystal_succeeded[run_id] = session
                except Exception as exc:
                    self.engine.emit(run_id, "agent.crystal.aborted", {"reason": f"final_sync_error:{type(exc).__name__}"})
            try:
                self.budget_tracker.mark_wall(run_id)
            except Exception as exc:
                self.engine.emit(run_id, "agent.budget.failed", {"stage": "wall", "reason": type(exc).__name__})
        latest = self.engine.store.get_run(run_id) or result
        if normalize_state(str(latest.get("state") or "")) in TERMINAL_STATES:
            self._seal_episode(run_id)
            await self._learn_crystal(run_id)
            await self._complete_coder_integrations(run_id)
            latest = self.engine.store.get_run(run_id) or latest
        self._crystal_succeeded.pop(run_id, None)
        return latest if isinstance(result, dict) else result

    async def run_one_turn(self, run_id: str) -> dict[str, Any]:
        """Execute exactly one planner turn and return.

        Unlike run(), which loops until terminal, run_one_turn() executes a
        single decide→execute→observe cycle and returns control to the caller.
        This enables OpenCode-style turn-based interaction where the operator
        inspects state between turns.
        """
        return await self.run(run_id, max_turns_this_call=1, defer_approval=True)

    async def run_turns(self, run_id: str, max_turns: int | None = None) -> dict[str, Any]:
        """Execute planner turns until terminal or max_turns is reached."""
        return await self.run(run_id, max_turns_this_call=max_turns)

    async def _run_loop(self, run_id: str, max_turns_this_call: int | None = None, *, defer_approval: bool = False) -> dict[str, Any]:
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
        if max_turns_this_call is not None:
            state.max_turns = state.turn + max_turns_this_call
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

        checked_local_binding = None
        while state.turn < state.max_turns:
            self.engine.raise_if_cancelled(run_id)
            self._transition(run_id, AgentRunState.PLANNING)
            run = self.engine.store.get_run(run_id) or run
            local_binding = self._local_binding_identity(run) if self._is_mutating_mode(run) else None
            if local_binding is not None and local_binding != checked_local_binding:
                binding_error = self._local_binding_error(local_binding)
                if binding_error:
                    state.status = "blocked"
                    state.blocker = binding_error
                    self.engine.emit(run_id, "agent.planner.blocked", {
                        "turn": state.turn, "blocker": binding_error, "tool_id": "worktree.bind",
                    })
                    self._save_state(state)
                    self._transition(run_id, AgentRunState.POLICY_BLOCKED, error=binding_error)
                    return self.engine.store.get_run(run_id) or {}
                checked_local_binding = local_binding
            resumed_decision, resume_approval_id = None, ""
            checkpoint = run.get("checkpoint") or {}
            cached_action = checkpoint.get("planner_deferred_approval")
            durable_action = self.engine.store.pending_deferred_action(run_id)
            suspended_id = str(checkpoint.get("suspended_approval_id") or "")
            deferred_record = cached_action if cached_action is not None else durable_action
            problem = ""
            if deferred_record is None and suspended_id and self.engine.store.was_deferred_approval(run_id, suspended_id):
                problem = "DEFERRED_APPROVAL_ACTION_MISSING"
                resume_approval_id = suspended_id
            elif deferred_record is not None:
                try:
                    resume_approval_id = str(deferred_record["approval_id"])
                    if ((durable_action is not None and deferred_record != durable_action)
                            or (suspended_id and suspended_id != resume_approval_id)):
                        raise ValueError("DEFERRED_APPROVAL_MISMATCH")
                    resumed_decision = parse_planner_decision(deferred_record["decision"])
                    approval = self.engine.store.get_approval(run_id, resume_approval_id)
                    status = (approval or {}).get("status")
                    if status == "pending":
                        state.status = "waiting_for_approval"
                        self._save_state(state)
                        self._transition(run_id, AgentRunState.WAITING_FOR_APPROVAL)
                        return self.engine.store.get_run(run_id) or {}
                    if status == "rejected":
                        problem = "DEFERRED_APPROVAL_REJECTED"
                    elif not approval:
                        problem = "DEFERRED_APPROVAL_MISSING"
                    elif (not self._exact_deferred_approval_matches(run, resumed_decision, approval)
                          or deferred_record["target_payload"] != self._execution_target_payload(
                              run, resumed_decision.execution_target)):
                        problem = "DEFERRED_APPROVAL_MISMATCH"
                    elif approval.get("resume_claimed"):
                        self.engine.emit(run_id, "agent.planner.approval_resume_refused", {
                            "approval_id": resume_approval_id, "reason": "DEFERRED_APPROVAL_ALREADY_CLAIMED",
                        })
                        return self.engine.store.get_run(run_id) or {}
                except ValueError as exc:
                    problem = ("DEFERRED_APPROVAL_MISMATCH" if str(exc) == "DEFERRED_APPROVAL_MISMATCH"
                               else "DEFERRED_APPROVAL_MALFORMED")
                except (KeyError, TypeError):
                    problem = "DEFERRED_APPROVAL_MALFORMED"
            if problem:
                state.status, state.blocker = "blocked", problem
                self._save_state(state)
                self.engine.emit(run_id, "agent.planner.approval_resume_refused", {
                    "approval_id": resume_approval_id, "reason": problem,
                })
                self._transition(run_id, AgentRunState.POLICY_BLOCKED, error=problem)
                return self.engine.store.get_run(run_id) or {}
            if state.observations and self.integration_coordinator is not None:
                # Advisory preflight (compression/KV/swarm). Bounded so a slow
                # coordinator can never stall a turn; the checkpoint guard keeps
                # it once-per-run.
                try:
                    await asyncio.wait_for(
                        self._prepare_coder_integrations(run, state),
                        timeout=float(os.environ.get("BEAST_INTEGRATION_PREPARE_TIMEOUT", "20")),
                    )
                except asyncio.TimeoutError:
                    self.engine.emit(run_id, "agent.integration.failed", {
                        "capability": "coder_integration_preflight",
                        "status": "failed",
                        "stage": "preflight",
                        "operation": "prepare",
                        "mode": "typed_planner",
                        "reason": "TimeoutError",
                        "authority": "advisory_or_existing_gate_only",
                        "run_id": run_id,
                    })
                except Exception as exc:
                    self.engine.emit(run_id, "agent.integration.failed", {
                        "capability": "coder_integration_preflight",
                        "status": "failed",
                        "stage": "preflight",
                        "operation": "prepare",
                        "mode": "typed_planner",
                        "reason": type(exc).__name__,
                        "authority": "advisory_or_existing_gate_only",
                        "run_id": run_id,
                    })
            paths = review_paths(run)
            # File-review evidence only applies to read-only /ask and /review
            # modes. Agent/edit/implementer runs manage their own lifecycle
            # through worktree bind → edit → verify → sourceplan → complete.
            if paths and is_read_only_run(run):
                evidence = collect_review_evidence(
                    paths, state.observations, explain=explains_attached_files(run),
                    objective=str(run.get("objective") or ""),
                )
                if evidence.blocker or not evidence.next_read:
                    return await self._finish_file_review(run, state, evidence)
            prompt = self._prompt(run, state) if not paths else ""
            saved_guidance = (run.get("checkpoint") or {}).get("planner_tool_guidance") or {}
            pending_guidance = saved_guidance.get("turn") == state.turn
            if pending_guidance:
                prompt += "\nCORRECTION: " + str(saved_guidance.get("message") or "")
            phase_decision = self._required_phase_decision(run, state) if not paths else None
            pre_enforced = phase_decision if (
                isinstance(phase_decision, PlannerDecision)
                and (
                    phase_decision.decision_type is PlannerDecisionType.COMPLETE
                    # Autopilot bookkeeping never costs a model call: bind is
                    # deterministic and the runtime owns it.
                    or (self._autopilot(run) and phase_decision.tool_id == "worktree.bind")
                )
            ) else None
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
            async def next_step() -> PlannerDecision:
                if resumed_decision is not None:
                    self._supplied_decisions[run_id] = ("runtime", resumed_decision.tool_id)
                    return resumed_decision
                if pre_enforced is not None:
                    self._supplied_decisions[run_id] = ("runtime", str(pre_enforced.tool_id or ""))
                    return pre_enforced
                # File-review evidence only applies to read-only /ask and /review
                # modes. Agent/edit/implementer runs manage their own lifecycle.
                if paths and is_read_only_run(run):
                    self._supplied_decisions[run_id] = ("runtime", "workspace.read_range")
                    return PlannerDecision(
                        decision_type=PlannerDecisionType.TOOL, tool_id="workspace.read_range",
                        arguments=evidence.next_read, rationale="Read the next range of an attached review file.",
                    )
                crystal_decision = self._crystal_decision(run_id, run, state)
                if crystal_decision is not None:
                    self._supplied_decisions[run_id] = ("crystal", str(crystal_decision.tool_id or ""))
                    return crystal_decision
                supplied = await self._metered_decision(self.provider, prompt, run=run, turn=state.turn + 1)
                self._supplied_decisions[run_id] = ("model", str(supplied.tool_id or ""))
                return supplied

            decision_task = asyncio.create_task(next_step())
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
                partial_text = self._recent_model_delta_text(run_id)

                if mode in {"chat", "analysis", "ask"}:
                    parsed = self._partial_structured_decision(run, partial_text)
                    decision_task.cancel()

                    if (
                        parsed is None
                        or parsed.decision_type is not PlannerDecisionType.COMPLETE
                        or not str(parsed.summary or "").strip()
                    ):
                        raise TimeoutError(
                            f"planner provider decision exceeded {int(decision_timeout * 1000)} ms "
                            "without a validated read-only completion"
                        )

                    decision = parsed
                    self.engine.emit(run_id, "agent.provider.partial_decision_salvaged", {
                        "turn": state.turn + 1,
                        "provider": str(run.get("provider") or ""),
                        "model": str(run.get("model") or ""),
                        "decision_type": decision.decision_type.value,
                        "chars": len(partial_text),
                    })
                else:
                    partial_text = self._provider_partial_text(self.provider) or partial_text
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
            except PlannerDecisionError as exc:
                decision_task.cancel()
                # A malformed or exhausted provider packet must never strand
                # an AgentRun in PLANNING after a successful worktree edit.
                state.status = "blocked"
                state.blocker = f"REFUSE_PLANNER_PROVIDER_DECISION: {exc}"
                self.engine.emit(run_id, "agent.provider.decision_refused", {
                    "turn": state.turn + 1,
                    "reason": str(exc)[:1000],
                    "usage": {
                        key: getattr(self.provider, "last_usage", {}).get(key)
                        for key in ("done_reason", "response_chars", "num_predict", "attempt")
                        if isinstance(getattr(self.provider, "last_usage", None), dict)
                    },
                })
                self._save_state(state)
                self._transition(run_id, AgentRunState.POLICY_BLOCKED, error=state.blocker)
                return self.engine.store.get_run(run_id) or {}
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
                route_model = (route or {}).get("model")
                if isinstance(usage, dict):
                    route_model = route_model or usage.get("model")
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
                    "model": str(route_model) if route_model else None,
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
                    "stream_interception": usage.get("stream_interception")
                    if isinstance(usage.get("stream_interception"), dict) else {},
                })
                self._emit_stream_interception(run, usage, state.turn + 1)
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
            provider_partial = self._provider_partial_text(self.provider) if not paths and not resumed_decision else ""
            delta_partial = self._recent_model_delta_text(run_id) if not paths and not resumed_decision else ""
            salvaged_decision = self._salvage_partial_decision_from_provider(
                run,
                self.provider,
                partial_text=provider_partial or delta_partial,
                decision=decision,
            )
            if salvaged_decision is not None and resumed_decision is None:
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
            if resumed_decision is None:
                decision = self._normalize_model_tool_dialect(run, run_id, decision)
            bootstrapped = self._bootstrap_agent_decision(run, state, decision)
            if bootstrapped is not None:
                decision = bootstrapped
            required = self._required_phase_decision(run, state, decision) if resumed_decision is None else None
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
            if (resumed_decision is None and not state.post_bind_read_retry_failed
                    and self._post_bind_duplicate_read(decision, state) and self._strong_reentry_allowed(run, state)):
                duplicate_path = str(decision.arguments.get("path") or "").strip()
                help_text = await self._help_duplicate_read(run, state, duplicate_path)
                retry_timeout = self._decision_timeout_seconds(run)
                self.engine.emit(run_id, "agent.provider.post_bind_read_retry", {
                    "turn": state.turn + 1,
                    "provider": str(run.get("provider") or ""),
                    "model": str(run.get("model") or ""),
                    "path": duplicate_path,
                    "timeout_seconds": retry_timeout,
                })
                try:
                    retried = await asyncio.wait_for(
                        self._metered_decision(
                            original_provider,
                            self._mutation_retry_prompt(prompt, duplicate_path, help_text, str(run.get("objective") or "")),
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
                    retried = self._normalize_model_tool_dialect(run, run_id, retried)
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
            recovery_exhausted = False
            if resumed_decision is None and state.post_bind_read_retry_failed and self._post_bind_duplicate_read(decision, state):
                repeated_read = decision
                blocked_path = str(decision.arguments.get("path") or "")
                self.engine.emit(run_id, "agent.provider.post_bind_read_stalled", {
                    "turn": state.turn + 1,
                    "provider": str(run.get("provider") or ""),
                    "model": str(run.get("model") or ""),
                    "path": blocked_path,
                })
                recovered = await self._recover_exact_edit_with_swarm(run, state, repeated_read, "post_bind_read_loop")
                if recovered is not None:
                    decision = recovered
                elif self._autopilot(run):
                    # Autopilot never parks on a redundant read. Re-task the
                    # model next turn with the exact next action instead.
                    guidance = (
                        f"You already inspected {blocked_path or 'that range'} in this run. "
                        "Do not read it again. The contents are in your observation history. "
                        "Choose the smallest bounded mutation (worktree.replace_exact or worktree.write_file) "
                        "that satisfies the objective, or worktree.verify if the edit is already complete."
                    )
                    # This was still a consumed provider turn. Advance the
                    # durable counter so the correction is visible on the next
                    # prompt and repeated redirects remain budget-bounded.
                    state.turn += 1
                    self.engine.merge_checkpoint(run_id, {
                        "planner_tool_guidance": {"turn": state.turn, "message": guidance},
                    })
                    state.last_decision = repeated_read.as_dict()
                    self._save_state(state)
                    self.engine.emit(run_id, "agent.provider.read_loop_redirected", {
                        "turn": state.turn,
                        "path": blocked_path,
                        "guidance": guidance,
                    })
                    self._transition(run_id, AgentRunState.UPDATING_PLAN)
                    continue
                else:
                    state.turn += 1
                    state.status = "paused"
                    state.last_decision = repeated_read.as_dict()
                    state.blocker = ""
                    self._save_state(state)
                    self.engine.emit(run_id, "agent.provider.read_loop_paused", {"turn": state.turn, "path": blocked_path})
                    self.engine.emit(run_id, "agent.run.advisory", {
                        "text": f"Paused on an already inspected range in {blocked_path}. Worktree preserved. "
                                "No edit was made by this turn.",
                    })
                    self._transition(run_id, AgentRunState.PAUSED)
                    return self.engine.store.get_run(run_id) or {}
            mutation_reason = self._invalid_mutation_reason(decision)
            if mutation_reason and resumed_decision is None and self._strong_reentry_allowed(run, state):
                failed_edit = decision
                recovery_cause = ""
                # Build an explicit field-level error message for the retry prompt
                missing_fields = self._missing_mutation_fields(decision)
                explicit_reason = mutation_reason
                if missing_fields:
                    explicit_reason = f"{mutation_reason} Missing required fields: {', '.join(missing_fields)}."

                self.engine.emit(run_id, "agent.provider.invalid_mutation_retry", {
                    "turn": state.turn + 1,
                    "provider": str(run.get("provider") or ""),
                    "model": str(run.get("model") or ""),
                    "tool_id": decision.tool_id,
                    "reason": explicit_reason,
                    "path": str(decision.arguments.get("path") or ""),
                    "missing_fields": missing_fields,
                })

                # Use a longer timeout for CPU inference retries (up to 60s, not 12s)
                retry_timeout = max(15.0, min(60.0, self._decision_timeout_seconds(run) * 0.7))

                # Prefer a stronger provider for the retry if available
                retry_provider = self._get_mutation_retry_provider(original_provider, run)

                try:
                    retried = await asyncio.wait_for(
                        self._metered_decision(
                            retry_provider,
                            self._mutation_argument_retry_prompt(prompt, decision, explicit_reason, state),
                            run=run,
                            turn=state.turn + 1,
                        ),
                        timeout=retry_timeout,
                    )
                except Exception as exc:
                    recovery_cause = "route_dampened" if "dampened" in str(exc).lower() else "planner_retry_error"
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
                        "tool_id": failed_edit.tool_id,
                        "reason": mutation_reason,
                        "error": f"{type(exc).__name__}: {exc}",
                    })
                else:
                    retried_reason = self._invalid_retry_recovery_reason(retried, state, getattr(self.engine, "workspace_root", ""))
                    if not retried_reason and retried.decision_type is not PlannerDecisionType.BLOCKED:
                        decision = retried
                        self.engine.emit(run_id, "agent.provider.invalid_mutation_recovered", {
                            "turn": state.turn + 1,
                            "provider": str(run.get("provider") or ""),
                            "model": str(run.get("model") or ""),
                            "tool_id": decision.tool_id,
                        })
                    else:
                        recovery_cause = "planner_retry_blocked" if not retried_reason else "planner_retry_invalid_edit"
                        retried_reason = retried_reason or str(retried.blocker or "Planner retry returned blocked.")
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
                if recovery_cause:
                    recovered = await self._recover_exact_edit_with_swarm(
                        run, state, failed_edit, recovery_cause,
                    )
                    if recovered is not None:
                        decision = recovered
                    else:
                        recovery_exhausted = self.engine.store.swarm_recovery_claimed(run_id)
            if decision.decision_type is PlannerDecisionType.BLOCKED and not recovery_exhausted:
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
                        turn=state.turn + 1,
                        reason=decision.blocker or route_kind or "first_mutation_blocked",
                    )
                    if mutation_retry is not None and mutation_retry.decision_type is not PlannerDecisionType.BLOCKED:
                        decision = mutation_retry
                        first_mutation_retried = True
                        self.engine.emit(run_id, "agent.provider.strong_retry_recovered", {
                            "turn": state.turn + 1,
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
                        turn=state.turn + 1,
                        reason=decision.blocker or route_kind or "heuristic_blocked",
                    )
                    if retried is not None and retried.decision_type is not PlannerDecisionType.BLOCKED:
                        decision = retried
                        self.engine.emit(run_id, "agent.provider.strong_retry_recovered", {
                            "turn": state.turn + 1,
                            "provider": str(run.get("provider") or ""),
                            "model": str(run.get("model") or ""),
                            "decision_type": decision.decision_type.value,
                        })
                    else:
                        self.provider = original_provider
            decision = self._ground_read_only_completion(run, state, decision)
            guidance, replacement_tool_id = "", ""
            if decision.decision_type == PlannerDecisionType.TOOL or str(decision.decision_type) == "tool":
                if decision.tool_id == "worktree.read_range":
                    replacement_tool_id = "workspace.read_range"
                    guidance = ("worktree.read_range is unregistered. Use workspace.read_range with a relative path. "
                                "For a bound local edit, it reads the isolated worktree.")
                elif decision.tool_id == "worktree.bind" and local_binding is not None and resumed_decision is None:
                    guidance = f"Bind is satisfied at {local_binding[3][:12]}. Continue without rebinding."
                elif (decision.tool_id == "worktree.sourceplan_draft" and self._is_mutating_mode(run)
                      and not self._latest_mutation_paths(state) and resumed_decision is None):
                    guidance = "No edit exists to hand off. Inspect or edit next, or report an evidence-backed no-change result."
            elif (decision.decision_type is PlannerDecisionType.BLOCKED and local_binding is not None
                  and "worktree.bind" in decision.blocker.lower()):
                guidance = f"Bind is already satisfied at {local_binding[3][:12]}. Inspect or edit that worktree."
            if guidance:
                state.turn += 1
                self.engine.emit(run_id, "agent.planner.tool_guidance", {
                    "turn": state.turn, "tool_id": decision.tool_id, "reason": guidance,
                    "replacement_tool_id": replacement_tool_id, "approval_created": False,
                })
                if pending_guidance:
                    state.status = "blocked"
                    state.blocker = guidance
                    self._save_state(state)
                    self._transition(run_id, AgentRunState.POLICY_BLOCKED, error=guidance)
                    return self.engine.store.get_run(run_id) or {}
                # Guidance is planner control state, not tool evidence. Keep it out
                # of the reviewed observation stream used for crystal extraction.
                self.engine.merge_checkpoint(run_id, {
                    "planner_tool_guidance": {"turn": state.turn, "message": guidance},
                })
                self._save_state(state)
                self._transition(run_id, AgentRunState.UPDATING_PLAN)
                continue
            if decision.decision_type == PlannerDecisionType.TOOL or str(decision.decision_type) == "tool":
                run_request = run.get("request") if isinstance(run.get("request"), dict) else {}
                locked_target = str(run_request.get("execution_target") or "local")
                if locked_target not in {"local", "ssh", "container"}:
                    raise PermissionError("AgentRun has an invalid locked execution target")
                if decision.execution_target != locked_target:
                    # The model may omit execution_target (parsed as local),
                    # but only the operator's durable run chooses its destination.
                    self.engine.emit(run_id, "agent.planner.target_bound", {
                        "model_target": decision.execution_target,
                        "locked_target": locked_target,
                        "tool_id": decision.tool_id,
                    })
                    decision = replace(decision, execution_target=locked_target)
                if decision.decision_type == PlannerDecisionType.TOOL or str(decision.decision_type) == "tool":
                    run_request = run.get("request") if isinstance(run.get("request"), dict) else {}
                locked_target = str(run_request.get("execution_target") or "local")
                if locked_target not in {"local", "ssh", "container"}:
                    raise PermissionError("AgentRun has an invalid locked execution target")
                if decision.execution_target != locked_target:
                    self.engine.emit(run_id, "agent.planner.target_bound", {
                        "turn": state.turn + 1,
                        "command": handoff_command,
                        "execution_target": decision.execution_target,
                        "source": "durable_run_request",
                    })
                    decision = replace(decision, execution_target=locked_target)
                original_decision = decision
                # Both provider-selected and phase-inserted verification enter
                # here, after target locking and before schema/approval.
                try:
                    handoff_command = (
                        verified_handoff_command(run)
                        if decision.tool_id == "worktree.verify" and self._is_mutating_mode(run)
                        else None
                    )
                except ValueError as exc:
                    decision, schema_error = None, str(exc)
                else:
                    if handoff_command is not None:
                        decision = replace(decision, arguments={"command": handoff_command}, approval_id="")
                        self.engine.emit(run_id, "agent.planner.handoff_verifier_bound", {
                            "turn": state.turn + 1,
                            "command": handoff_command,
                            "execution_target": decision.execution_target,
                            "source": "durable_run_request",
                        })
                decision, schema_error = await self._one_schema_correction(
                        run, run_id, decision, state.turn + 1, state=state,
                    )
                if decision is None:
                    # Schema correction failed — proceed with the original
                    # decision anyway. The tool will fail naturally if its
                    # arguments are invalid, and the model can correct on the
                    # next turn. This keeps the run alive instead of blocking.
                    decision = original_decision

            self.engine.emit(run_id, "agent.planner.decision", {
                "turn": state.turn,
                "decision": decision.as_dict(),
            })
            self._save_state(state)

            if decision.decision_type is PlannerDecisionType.COMPLETE:
                if "no_change" in decision.arguments:
                    evidence = await asyncio.to_thread(self._no_change_evidence, run, state, decision)
                    if evidence is not None:
                        return self._finish_local_tli_review(
                            state, f"No files changed. {decision.summary}", "evidence_backed_no_change",
                            evidence=evidence,
                        )
                    # A fabricated no_change claim (quote doesn't match observed
                    # source) must be rejected — the run cannot close on false
                    # evidence.
                    state.observations.append({
                        "observation_id": "planner-completion-gate",
                        "tool_id": "planner.completion_gate",
                        "status": "failed",
                        "error": "No-change claim rejected: quoted text not found in observed source.",
                        "result": {"verification_required_for_edit": True, "handoff_required_for_edit": True},
                    })
                    state.observations = state.observations[-self.observation_limit:]
                    self.engine.emit(run_id, "agent.planner.completion_rejected", {
                        "turn": state.turn,
                        "reason": "no_change claim rejected - quoted text not in observed source",
                    })
                    self._save_state(state)
                    continue
                    # Completion requires verification only when files were
                    # actually mutated. If nothing changed, there is nothing
                    # to verify — accept completion without a gate.
                    if self._latest_mutation_paths(state):
                        if self._autopilot(run) and self._latest_mutation_paths(state):
                            # Agentic repair loop: a failed or stale verification
                            # never closes the run and never touches the operator's
                            # workspace. The model gets a bounded repair turn.
                            attempts = int((run.get("checkpoint") or {}).get("autopilot_repair_attempts") or 0)
                            max_attempts = max(1, self.max_repair_cycles)
                            if attempts >= max_attempts:
                                self._emit_worktree_diff(run, state)
                                summary = (
                                    f"Autopilot stopped after {attempts} repair attempt(s): verification did not pass. "
                                    "The isolated worktree and its diff are preserved; nothing was applied to your workspace."
                                )
                                return self._finish_local_tli_review(
                                    state, summary, "unverified_repair_exhausted",
                                    changed_files=self._latest_mutation_paths(state),
                                    verification_failures=len(state.verification_failures),
                                )
                            failure = self._latest_failure_contract(state)
                            guidance = (
                                "Completion was rejected because the isolated diff is not verified. "
                                "Repair the failing check with the smallest edit, then run worktree.verify again. "
                                "If the verifier itself is wrong, run the correct command with worktree.run, then verify."
                            )
                            if failure:
                                compact_failure = {
                                    "command": failure.get("command"),
                                    "returncode": failure.get("returncode"),
                                    "error": str(failure.get("error") or "")[:800],
                                    "analysis": failure.get("analysis"),
                                }
                                guidance += " LATEST FAILURE: " + json.dumps(
                                    compact_failure, sort_keys=True, default=str, separators=(",", ":")
                                )
                            self.engine.merge_checkpoint(run_id, {
                                "autopilot_repair_attempts": attempts + 1,
                                "planner_tool_guidance": {"turn": state.turn + 1, "message": guidance},
                            })
                            self.engine.emit(run_id, "agent.autopilot.repair_requested", {
                                "turn": state.turn,
                                "attempt": attempts + 1,
                                "max_attempts": max_attempts,
                                "failure": failure,
                            })
                            self._save_state(state)
                            continue
                        state.observations.append({
                            "observation_id": "planner-completion-gate",
                            "tool_id": "planner.completion_gate",
                            "status": "failed",
                            "error": "Completion needs a changed, verified diff or a supported no-change claim.",
                            "result": {"verification_required_for_edit": True, "handoff_required_for_edit": True},
                        })
                        state.observations = state.observations[-self.observation_limit:]
                        self.engine.emit(run_id, "agent.planner.completion_rejected", {
                            "turn": state.turn,
                            "reason": "no verified diff or supported no-change evidence",
                        })
                        self._save_state(state)
                        continue
                if is_read_only_run(run):
                    state.status = "completed"
                    state.final_summary = decision.summary
                    self._save_state(state)
                    self._transition(run_id, AgentRunState.FINALIZING)
                    self.engine.emit(run_id, "agent.run.advisory", {
                        "text": state.final_summary,
                        "message": "Read-only review complete. No files were changed.",
                    })
                    self.engine.emit(run_id, "agent.planner.completed", {
                        "turns": state.turn,
                        "summary": state.final_summary,
                        "completion_mode": "read_only_advisory",
                        "observation_count": len(state.observations),
                    })
                    self._transition(run_id, AgentRunState.COMPLETED)
                    return self.engine.store.get_run(run_id) or {}
                if self._local_tli_review(run):
                    return self._finish_tli_completion(run, state)
                # No mutations were made — nothing to verify or graduate.
                # Complete directly without the post-session gate.
                if not self._latest_mutation_paths(state):
                    state.status = "completed"
                    state.final_summary = decision.summary
                    self._save_state(state)
                    self._transition(run_id, AgentRunState.FINALIZING)
                    self.engine.emit(run_id, "agent.planner.completed", {
                        "turns": state.turn,
                        "summary": decision.summary,
                        "completion_mode": "no_changes_completed",
                        "observation_count": len(state.observations),
                    })
                    self._save_state(state)
                    self._transition(run_id, AgentRunState.COMPLETED)
                    return self.engine.store.get_run(run_id) or {}
                current_run = self.engine.store.get_run(run_id) or run
                quality = verify_post_session_quality(current_run, state.observations)
                self.engine.emit(run_id, "agent.post_session.quality", quality)
                graduation = assess_post_session_graduation(current_run, state.observations, quality)
                self.engine.emit(run_id, "agent.graduation.assessed", graduation)
                if graduation["graduation_status"] != "READY_FOR_HUMAN_APPROVAL":
                    state.status = "session_complete_graduation_refused" if graduation["graduation_status"] == "REFUSE" else "session_complete_needs_review"
                    state.blocker = "; ".join(graduation["reasons"])
                    self._save_state(state)
                    self._transition(run_id, AgentRunState.POLICY_BLOCKED, error=state.blocker)
                    return self.engine.store.get_run(run_id) or {}
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
                self._transition(run_id, AgentRunState.FINALIZING)
                self.engine.emit(run_id, "agent.planner.completed", {
                    "turns": state.turn,
                    "summary": decision.summary,
                    "observation_count": len(state.observations),
                })
                self._save_state(state)
                self._transition(run_id, AgentRunState.COMPLETED)
                return self.engine.store.get_run(run_id) or {}

            if decision.decision_type is PlannerDecisionType.BLOCKED:
                if is_read_only_run(run):
                    # Read-only mode: never policy_block on a blocked decision.
                    # Complete gracefully with what was observed.
                    state.status = "completed"
                    state.final_summary = f"Read-only review complete. {decision.blocker or ''}"
                    self._save_state(state)
                    self._transition(run_id, AgentRunState.FINALIZING)
                    self.engine.emit(run_id, "agent.planner.completed", {
                        "turns": state.turn,
                        "summary": state.final_summary,
                        "completion_mode": "read_only_completed",
                        "observation_count": len(state.observations),
                    })
                    self._save_state(state)
                    self._transition(run_id, AgentRunState.COMPLETED)
                    return self.engine.store.get_run(run_id) or {}
                state.status = "blocked"
                state.blocker = decision.blocker
                self.engine.emit(run_id, "agent.planner.blocked", {
                    "turn": state.turn, "blocker": decision.blocker,
                })
                self._save_state(state)
                self._transition(run_id, AgentRunState.POLICY_BLOCKED, error=decision.blocker)
                return self.engine.store.get_run(run_id) or {}

            # H12.2: Never re-execute an identical failed workspace read
            # without intervening evidence. Preserve the original failure
            # receipt and refuse the duplicate before authorization/execution.
            if (
                decision.decision_type is PlannerDecisionType.TOOL
                and decision.tool_id == "workspace.read_range"
            ):
                proposed = json.dumps(
                    decision.arguments, sort_keys=True, default=str,
                )
                for previous in reversed(state.observations):
                    if not isinstance(previous, dict):
                        continue
                    if (
                        previous.get("tool_id") == decision.tool_id
                        and previous.get("status") == "failed"
                        and json.dumps(
                            previous.get("arguments") or {},
                            sort_keys=True, default=str,
                        ) == proposed
                    ):
                        blocker = (
                            "REFUSE_DUPLICATE_FAILED_READ: "
                            f"{decision.arguments.get('path', '')}"
                        )
                        self.engine.emit(run_id, "agent.planner.duplicate_failed_action", {
                            "turn": state.turn,
                            "tool_id": decision.tool_id,
                            "arguments": decision.arguments,
                            "previous_observation_id": previous.get("observation_id", ""),
                            "reason": blocker,
                        })
                        state.status = "blocked"
                        state.blocker = blocker
                        self._save_state(state)
                        self._transition(
                            run_id, AgentRunState.POLICY_BLOCKED, error=blocker,
                        )
                        return self.engine.store.get_run(run_id) or {}

            self._transition(run_id, AgentRunState.EXECUTING_TOOL)
            try:
                if resumed_decision is not None and decision != resumed_decision:
                    raise ValueError("DEFERRED_APPROVAL_DECISION_CHANGED")
                if resume_approval_id:
                    authorized = await self._authorize_tool(
                        run, run_id, decision, defer=defer_approval, resume_approval_id=resume_approval_id,
                    )
                else:
                    authorized = await self._authorize_tool(run, run_id, decision, defer=defer_approval)
            except ApprovalDeferred as deferred:
                state.status = "waiting_for_approval"
                state.blocker = f"operator approval required for {deferred.tool_id}"
                state.last_decision = decision.as_dict()
                self._save_state(state)
                self.engine.emit(run_id, "agent.planner.approval_deferred", {
                    "turn": state.turn + 1,
                    "approval_id": deferred.approval_id,
                    "tool_id": deferred.tool_id,
                    "state": AgentRunState.WAITING_FOR_APPROVAL.value,
                })
                return self.engine.store.get_run(run_id) or {}
            except ToolCorrectionRequired as exc:
                state.turn += 1
                guidance = (
                    f"The proposed {decision.tool_id} action was not executed: {exc}. "
                    "Use the exact content already observed from the target file and return the smallest valid "
                    "bounded correction. Do not repeat the rejected payload."
                )
                self.engine.merge_checkpoint(run_id, {
                    "planner_tool_guidance": {"turn": state.turn, "message": guidance},
                })
                state.last_decision = decision.as_dict()
                state.status = "running"
                self._save_state(state)
                self.engine.emit(run_id, "agent.planner.tool_correction_required", {
                    "turn": state.turn,
                    "tool_id": decision.tool_id,
                    "reason": str(exc),
                    "guidance": guidance,
                })
                self._transition(run_id, AgentRunState.UPDATING_PLAN)
                continue
            except ValueError as exc:
                # Defense in depth: a schema change between preflight and
                # approval must end cleanly without an orphaned executing run.
                state.status = "blocked"
                state.blocker = f"REFUSE_TOOL_AUTHORIZATION:{type(exc).__name__}: {exc}"
                self.engine.emit(run_id, "agent.planner.blocked", {
                    "turn": state.turn, "blocker": state.blocker,
                    "tool_id": decision.tool_id,
                })
                self._save_state(state)
                self._transition(run_id, AgentRunState.POLICY_BLOCKED, error=state.blocker)
                return self.engine.store.get_run(run_id) or {}
            if authorized is None:
                state.status = "blocked"
                state.blocker = f"operator did not approve {decision.tool_id}"
                self._save_state(state)
                self._transition(run_id, AgentRunState.POLICY_BLOCKED, error=state.blocker)
                return self.engine.store.get_run(run_id) or {}
            decision = authorized
            if resume_approval_id:
                if not self.engine.store.claim_deferred_approval(run_id, resume_approval_id):
                    self.engine.emit(run_id, "agent.planner.approval_resume_refused", {
                        "approval_id": resume_approval_id, "reason": "DEFERRED_APPROVAL_NOT_CLAIMED",
                    })
                    return self.engine.store.get_run(run_id) or {}
                state.blocker = ""
                self.engine.emit(run_id, "agent.planner.approval_resumed", {
                    "approval_id": resume_approval_id, "tool_id": decision.tool_id, "turn": state.turn,
                })
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

            if resume_approval_id:
                self.engine.store.finish_deferred_action(run_id, resume_approval_id)
                self.engine.merge_checkpoint(run_id, {"planner_deferred_approval": None,
                    "suspended_step": None, "suspended_step_id": "", "suspended_approval_id": ""})
            self._record_tool_budget(run_id, decision, observation)

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
                    self._transition(run_id, AgentRunState.BUDGET_EXHAUSTED, error=state.blocker)
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
            # Review coverage is cumulative. Dropping old reads would reopen
            # already inspected ranges on a larger review or after reconnect.
            keep = max(self.observation_limit, state.max_turns) if paths else self.observation_limit
            state.observations = state.observations[-keep:]
            self._transition(run_id, AgentRunState.UPDATING_PLAN)
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

            # Operator opt-in only: after a verified SourcePlan handoff, close
            # deterministically rather than asking a small model for another
            # edit. The independent post-session quality gate still runs and
            # can refuse; no SourcePlan promotion authority is introduced.
            request = run.get("request") if isinstance(run.get("request"), dict) else {}
            if (request.get("post_session_closure") == "verified_handoff"
                    and decision.tool_id == "worktree.sourceplan_draft"
                    and observation.get("status") == "completed"
                    and self._is_mutating_mode(run)
                    and self._completion_ready(run, state)):
                self.engine.emit(run_id, "agent.planner.verified_handoff_requested", {
                    "turn": state.turn,
                    "reason": "operator_opt_in_after_sourceplan",
                    "model_completion_decision": False,
                })
                current_run = self.engine.store.get_run(run_id) or run
                quality = verify_post_session_quality(current_run, state.observations)
                self.engine.emit(run_id, "agent.post_session.quality", quality)
                graduation = assess_post_session_graduation(current_run, state.observations, quality)
                self.engine.emit(run_id, "agent.graduation.assessed", graduation)
                if graduation["graduation_status"] != "READY_FOR_HUMAN_APPROVAL":
                    state.status = "session_complete_graduation_refused"
                    state.blocker = "; ".join(graduation["reasons"])
                    self._save_state(state)
                    self._transition(run_id, AgentRunState.POLICY_BLOCKED, error=state.blocker)
                    return self.engine.store.get_run(run_id) or {}
                state.status = "completed"
                state.final_summary = self._completion_summary_from_state(run, state)
                self._transition(run_id, AgentRunState.FINALIZING)
                self.engine.emit(run_id, "agent.planner.completed", {
                    "turns": state.turn,
                    "summary": state.final_summary,
                    "observation_count": len(state.observations),
                    "completion_mode": "operator_opt_in_verified_sourceplan_handoff",
                })
                self._save_state(state)
                self._transition(run_id, AgentRunState.COMPLETED)
                return self.engine.store.get_run(run_id) or {}

        paths = review_paths(run)
        # File-review evidence only applies to read-only /ask and /review
        # modes. Agent/edit/implementer runs manage their own lifecycle
        # through worktree bind → edit → verify → sourceplan → complete.
        if paths and is_read_only_run(run):
            evidence = collect_review_evidence(
                paths, state.observations, explain=explains_attached_files(run),
                objective=str(run.get("objective") or ""),
            )
            if not evidence.blocker and evidence.next_read:
                # A UI turn is only one call slice, not the full read budget.
                # Let the client advance to the remaining source ranges.
                if max_turns_this_call is not None and state.turn < self.max_turns:
                    return self.engine.store.get_run(run_id) or {}
                if not any(evidence.visible.values()):
                    return self._review_incomplete(state, "No attached source could be read within the review budget.", evidence.coverage())
            return await self._finish_file_review(run, state, evidence)
        if self._is_mutating_mode(run) and self._completion_ready(run, state):
            if self._local_tli_review(run):
                return self._finish_tli_completion(run, state)
            current_run = self.engine.store.get_run(run_id) or run
            quality = verify_post_session_quality(current_run, state.observations)
            self.engine.emit(run_id, "agent.post_session.quality", quality)
            graduation = assess_post_session_graduation(current_run, state.observations, quality)
            self.engine.emit(run_id, "agent.graduation.assessed", graduation)
            if graduation["graduation_status"] != "READY_FOR_HUMAN_APPROVAL":
                state.status = "session_complete_graduation_refused" if graduation["graduation_status"] == "REFUSE" else "session_complete_needs_review"
                state.blocker = "; ".join(graduation["reasons"])
                self._save_state(state)
                self._transition(run_id, AgentRunState.POLICY_BLOCKED, error=state.blocker)
                return self.engine.store.get_run(run_id) or {}
            state.status = "completed"
            state.final_summary = self._completion_summary_from_state(run, state)
            self._transition(run_id, AgentRunState.FINALIZING)
            self.engine.emit(run_id, "agent.planner.completed", {
                "turns": state.turn,
                "summary": state.final_summary,
                "observation_count": len(state.observations),
                "completion_mode": "budget_edge_autofinalize",
            })
            self._save_state(state)
            self._transition(run_id, AgentRunState.COMPLETED)
            return self.engine.store.get_run(run_id) or {}
        # After the while loop, we may have exited because:
        # 1. A terminal state was reached (returned inside the loop)
        # 2. The per-call turn limit was reached (max_turns_this_call)
        # In case 2, return the non-terminal run state so the caller
        # can decide whether to invoke another turn.
        # Note: state.status may be "running" which is not a valid AgentRunState
        # enum value, so compare against terminal state strings directly.
        if max_turns_this_call is not None:
            self._save_state(state)
            return self.engine.store.get_run(run_id) or {}

        state.status = "budget_exhausted"
        state.blocker = f"planner turn budget exhausted at {state.max_turns} turns"
        self.engine.emit(run_id, "agent.planner.budget_exhausted", {
            "turns": state.turn,
            "max_turns": state.max_turns,
        })
        self._save_state(state)
        self._transition(run_id, AgentRunState.BUDGET_EXHAUSTED, error=state.blocker)
        return self.engine.store.get_run(run_id) or {}

# BEAST_R321_MUTATION_INFERENCE: bounded native Ollama mutation decision budgets and observable results.

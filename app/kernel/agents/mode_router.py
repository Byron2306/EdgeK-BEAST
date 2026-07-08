"""BEAST mode routing.

Mode Router maps task phases and risk to bounded role lanes. It is intentionally
small and deterministic so TUI, MCP, SourcePlan, and evidence packets can all
explain the same permission decision.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional

from app.kernel.policy.policy_gate import from_mode_tool_decision


MODE_ORDER = ["scout", "architect", "implementer", "reviewer", "evidence_logger"]


@dataclass(frozen=True)
class ModeDefinition:
    mode: str
    purpose: str
    tool_profile: str
    allowed_categories: List[str]
    mutation_permission: str
    context_budget_tokens: int
    escalation_threshold: str
    allowed_tools: List[str]
    blocked_tools: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "mode": self.mode,
            "purpose": self.purpose,
            "tool_profile": self.tool_profile,
            "allowed_categories": list(self.allowed_categories),
            "mutation_permission": self.mutation_permission,
            "context_budget_tokens": self.context_budget_tokens,
            "escalation_threshold": self.escalation_threshold,
            "allowed_tools": list(self.allowed_tools),
            "blocked_tools": list(self.blocked_tools),
        }


MODE_DEFINITIONS: Dict[str, ModeDefinition] = {
    "scout": ModeDefinition(
        "scout",
        "Find files, symbols, tests, routes, and contracts.",
        "readonly",
        ["context", "audit", "task", "planning"],
        "no_writes",
        6000,
        "ask_before_provider_or_shell",
        ["beast_prepare_task", "beast_context_packet", "beast_code_cortex_status", "beast_code_cortex_search_symbols", "beast_code_cortex_dependents"],
        ["beast_sourceplan_apply_selected", "beast_openclaw_execute"],
    ),
    "architect": ModeDefinition(
        "architect",
        "Produce plan, risks, and SourcePlan outline.",
        "readonly",
        ["context", "audit", "task", "planning"],
        "no_writes",
        9000,
        "escalate_for_implementation",
        ["beast_prepare_task", "beast_sourceplan_prepare", "beast_sourceplan_scorecard", "beast_sourceplan_preview_hunks"],
        ["beast_sourceplan_apply_selected", "beast_openclaw_execute"],
    ),
    "debugger": ModeDefinition(
        "debugger",
        "Read traces, run safe diagnostics, and localize faults.",
        "readonly",
        ["context", "audit", "task", "planning", "observability"],
        "diagnostics_only",
        10000,
        "require_receipt_for_command_execution",
        ["beast_run_quality_cascade", "beast_sourceplan_scorecard", "beast_code_cortex_search_symbols"],
        ["beast_sourceplan_apply_selected"],
    ),
    "implementer": ModeDefinition(
        "implementer",
        "Generate Action IR and governed SourcePlan operations.",
        "edit",
        ["context", "audit", "task", "planning", "sourceplan"],
        "sourceplan_only",
        12000,
        "preview_and_approval_required",
        ["beast_sourceplan_prepare", "beast_sourceplan_preview_hunks", "beast_symbol_surgeon_plan", "beast_sourceplan_scorecard"],
        ["beast_openclaw_execute"],
    ),
    "reviewer": ModeDefinition(
        "reviewer",
        "Inspect diffs, risks, tests, and style before approval.",
        "readonly",
        ["context", "audit", "planning", "sourceplan"],
        "no_writes",
        8000,
        "block_on_stale_or_high_risk",
        ["beast_sourceplan_preview_hunks", "beast_sourceplan_scorecard", "beast_code_cortex_dependents"],
        ["beast_sourceplan_apply_selected", "beast_openclaw_execute"],
    ),
    "security_gate": ModeDefinition(
        "security_gate",
        "Inspect commands, scripts, hooks, secrets, and dependency risk.",
        "ops",
        ["audit", "observability", "planning", "governance"],
        "blocks_unsafe_execution",
        8000,
        "approval_required_for_bootstrap",
        ["beast_sourceplan_scorecard", "beast_tool_profile"],
        ["beast_openclaw_execute", "beast_plugin_marketplace_install"],
    ),
    "evidence_logger": ModeDefinition(
        "evidence_logger",
        "Write Chronicle, Memory Hull, and promotion receipts.",
        "evidence",
        ["audit", "governance", "observability"],
        "evidence_only",
        5000,
        "source_writes_forbidden",
        ["beast_publish_chronicle", "beast_check_promotion", "beast_tool_profile"],
        ["beast_sourceplan_apply_selected", "beast_openclaw_execute"],
    ),
    "budget_controller": ModeDefinition(
        "budget_controller",
        "Choose local, cloud, provider, and crystal-replay routes.",
        "ops",
        ["audit", "planning", "governance", "observability"],
        "no_source_writes",
        5000,
        "prefer_local_until_evidence_exhausted",
        ["beast_provider_economist_select", "beast_tool_laziness_recommend_tools", "beast_tool_profile"],
        ["beast_sourceplan_apply_selected"],
    ),
}


class ModeRouter:
    """Select and explain BEAST role lanes."""

    def definitions(self) -> Dict[str, Any]:
        return {
            "beast_object_type": "beast_mode_router_catalog",
            "version": "1.0",
            "modes": {key: value.to_dict() for key, value in MODE_DEFINITIONS.items()},
            "default_transition_path": list(MODE_ORDER),
        }

    def select(
        self,
        *,
        phase: str = "",
        risk: str = "",
        requested_mode: str = "",
        provider: str = "",
        sourceplan: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        normalized = self._mode_for(phase, risk, requested_mode, sourceplan or {})
        definition = MODE_DEFINITIONS[normalized]
        reason = self._reason(normalized, phase, risk, requested_mode, sourceplan or {})
        return {
            "beast_object_type": "beast_mode_route",
            "version": "1.0",
            "selected_mode": normalized,
            "definition": definition.to_dict(),
            "phase": phase or "unspecified",
            "risk": risk or "unknown",
            "provider": provider,
            "why": reason,
            "transition_path": self.transition_path("scout", normalized),
            "receipt": self.receipt(normalized, reason),
        }

    def transition_path(self, current: str, target: str) -> List[str]:
        if current not in MODE_ORDER or target not in MODE_ORDER:
            return [target] if target in MODE_DEFINITIONS else []
        start = MODE_ORDER.index(current)
        end = MODE_ORDER.index(target)
        if end < start:
            return [current, target]
        return MODE_ORDER[start : end + 1]

    def tool_allowed(self, mode: str, tool_name: str, category: str = "") -> Dict[str, Any]:
        definition = MODE_DEFINITIONS.get(mode) or MODE_DEFINITIONS["scout"]
        explicit_block = tool_name in definition.blocked_tools
        category_ok = not category or category in definition.allowed_categories
        explicit_allow = tool_name in definition.allowed_tools
        allowed = not explicit_block and (explicit_allow or category_ok)
        decision = {
            "beast_object_type": "beast_mode_tool_decision",
            "mode": definition.mode,
            "tool": tool_name,
            "category": category,
            "allowed": allowed,
            "reason": "explicitly blocked" if explicit_block else "allowed by mode" if allowed else "category outside mode profile",
            "tool_profile": definition.tool_profile,
        }
        decision["policy_gate"] = from_mode_tool_decision(decision)
        return decision

    def receipt(self, mode: str, reason: str) -> Dict[str, Any]:
        return {
            "beast_object_type": "beast_mode_transition_receipt",
            "version": "1.0",
            "mode": mode,
            "reason": reason,
            "timestamp": time.time(),
        }

    def _mode_for(self, phase: str, risk: str, requested_mode: str, sourceplan: Dict[str, Any]) -> str:
        requested = str(requested_mode or "").strip().lower()
        if requested in MODE_DEFINITIONS:
            return requested
        phase_key = str(phase or "").strip().lower()
        risk_key = str(risk or sourceplan.get("risk_level") or "").strip().lower()
        decision = str(sourceplan.get("decision") or "").strip().lower()
        if phase_key in MODE_DEFINITIONS:
            return phase_key
        if "security" in phase_key or "bootstrap" in phase_key:
            return "security_gate"
        if "review" in phase_key or decision.startswith("block"):
            return "reviewer"
        if "implement" in phase_key or "edit" in phase_key or "sourceplan" in phase_key:
            return "implementer"
        if "debug" in phase_key or "diagnostic" in phase_key:
            return "debugger"
        if risk_key == "high":
            return "reviewer"
        if risk_key == "medium":
            return "architect"
        return "scout"

    def _reason(self, mode: str, phase: str, risk: str, requested_mode: str, sourceplan: Dict[str, Any]) -> str:
        if requested_mode:
            return f"requested mode {requested_mode}"
        if sourceplan.get("decision"):
            return f"SourcePlan decision {sourceplan.get('decision')} with risk {risk or sourceplan.get('risk_level') or 'unknown'}"
        if phase:
            return f"phase {phase} routed to {mode}"
        if risk:
            return f"risk {risk} routed to {mode}"
        return "default scout orientation"

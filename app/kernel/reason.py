"""
EdgeK BEAST Gateway - Reason Phase of PREC Cycle
Responsible for applying governance policies (L0-L4) to the normalized request
"""

import yaml
import calendar
import copy
import sqlite3
import time
from pathlib import Path
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from enum import Enum
import logging

from .perceive import EdgeKIR
from .workspace_graph import WorkspaceGraph

logger = logging.getLogger(__name__)


class GovernanceDecision(Enum):
    ALLOW = "allow"
    MODIFY = "modify"
    DENY = "deny"
    DEFER = "defer"


@dataclass
class GovernanceResult:
    """Result of applying governance policies"""
    decision: GovernanceDecision
    modified_ir: Optional[EdgeKIR] = None
    reason: str = ""
    policies_applied: List[str] = None
    budget_impact: Dict[str, Any] = None
    retry_after_seconds: Optional[int] = None
    reset_at: Optional[str] = None
    
    def __post_init__(self):
        if self.policies_applied is None:
            self.policies_applied = []
        if self.budget_impact is None:
            self.budget_impact = {}


class BudgetLedger:
    """SQLite-backed request and token budget ledger."""

    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            db_path = Path(__file__).resolve().parents[2] / "data" / "budget.db"
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self):
        return sqlite3.connect(str(self.db_path))

    def _init_db(self):
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS usage_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    model TEXT NOT NULL,
                    input_tokens INTEGER NOT NULL,
                    output_tokens INTEGER NOT NULL,
                    total_tokens INTEGER NOT NULL,
                    estimated_cost_usd REAL NOT NULL,
                    created_at REAL NOT NULL,
                    day TEXT NOT NULL
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_usage_day_session ON usage_events(day, session_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_usage_provider_time ON usage_events(provider, created_at)")

    def daily_totals(self, session_id: str, day: Optional[str] = None) -> Dict[str, Any]:
        day = day or time.strftime("%Y-%m-%d", time.gmtime())
        with self._connect() as conn:
            row = conn.execute("""
                SELECT COUNT(*), COALESCE(SUM(total_tokens), 0), COALESCE(SUM(estimated_cost_usd), 0.0)
                FROM usage_events
                WHERE session_id = ? AND day = ?
            """, (session_id, day)).fetchone()
        return {
            "requests": row[0] or 0,
            "tokens": row[1] or 0,
            "estimated_cost_usd": row[2] or 0.0
        }

    def window_totals(self, provider: str, window_seconds: int = 60) -> Dict[str, Any]:
        since = time.time() - window_seconds
        with self._connect() as conn:
            row = conn.execute("""
                SELECT COUNT(*), COALESCE(SUM(total_tokens), 0), MIN(created_at)
                FROM usage_events
                WHERE provider = ? AND created_at >= ?
            """, (provider, since)).fetchone()
        oldest = row[2]
        retry_after_seconds = 0
        if oldest:
            retry_after_seconds = max(1, int((oldest + window_seconds) - time.time()))
        return {
            "requests": row[0] or 0,
            "tokens": row[1] or 0,
            "oldest_event_at": oldest,
            "retry_after_seconds": retry_after_seconds
        }

    def provider_windows(self, providers: List[str], window_seconds: int = 60) -> Dict[str, Any]:
        """Return rolling-window totals for providers."""
        return {
            provider: self.window_totals(provider, window_seconds)
            for provider in providers
        }

    def usage_summary(self, session_id: str) -> Dict[str, Any]:
        """Return daily and rolling budget state."""
        providers = ["openai", "anthropic", "google", "huggingface", "tgi", "litellm"]
        return {
            "daily": self.daily_totals(session_id),
            "rolling_60s": self.provider_windows(providers)
        }

    def record(self, session_id: str, provider: str, model: str, budget_impact: Dict[str, Any]):
        created_at = time.time()
        day = time.strftime("%Y-%m-%d", time.gmtime(created_at))
        input_tokens = int(budget_impact.get("estimated_input_tokens", 0))
        output_tokens = int(budget_impact.get("estimated_output_tokens", 0))
        total_tokens = int(budget_impact.get("estimated_total_tokens", input_tokens + output_tokens))
        estimated_cost = float(budget_impact.get("estimated_cost_usd", 0.0))

        with self._connect() as conn:
            conn.execute("""
                INSERT INTO usage_events
                (session_id, provider, model, input_tokens, output_tokens, total_tokens, estimated_cost_usd, created_at, day)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                session_id,
                provider,
                model,
                input_tokens,
                output_tokens,
                total_tokens,
                estimated_cost,
                created_at,
                day
            ))


class Reasoner:
    """Applies L0-L4 governance policies to EdgeK IR"""
    
    def __init__(
        self,
        policy_path: Optional[str] = None,
        budget_ledger: Optional[BudgetLedger] = None,
        workspace_graph: Optional[WorkspaceGraph] = None
    ):
        if policy_path is None:
            policy_path = Path(__file__).resolve().parents[2] / "policies" / "default.yaml"
        self.policy_path = str(policy_path)
        self.policies = self._load_policies()
        self.budget_ledger = budget_ledger or BudgetLedger()
        self.workspace_graph = workspace_graph or WorkspaceGraph()
        
    def _load_policies(self) -> Dict[str, Any]:
        """Load policies from YAML file"""
        try:
            with open(self.policy_path, 'r') as f:
                return yaml.safe_load(f)
        except FileNotFoundError:
            logger.warning(f"Policy file not found: {self.policy_path}")
            return self._get_default_policies()
        except Exception as e:
            logger.error(f"Error loading policies: {e}")
            return self._get_default_policies()
    
    def _get_default_policies(self) -> Dict[str, Any]:
        """Return default policies if file loading fails"""
        return {
            "meta_rules": {
                "protocol_unification": True,
                "context_economy": True,
                "mcp_tool_governance": True,
                "runtime_control": True,
                "forensic_observability": True,
                "max_input_tokens_per_request": 8000,
                "max_output_tokens_per_request": 2000,
                "max_tool_calls_per_request": 10,
                "daily_max_requests": 1000,
                "daily_max_estimated_cost_usd": 10.0,
                "stasis_wall_enabled": True,
                "stasis_wall_max_concurrent": 5,
                "circuit_breaker_enabled": True,
                "circuit_breaker_failure_threshold": 5,
                "circuit_breaker_timeout_seconds": 60,
                "context_economizer_enabled": True,
                "context_compression_ratio_target": 0.3,
                "mcp_tool_governance_enabled": True,
                "mcp_tool_budgeting_enabled": True,
                "telemetry_enabled": True,
                "metrics_collection_enabled": True,
                "trace_collection_enabled": True
            },
            "providers": {
                "openai": {
                    "enabled": True,
                    "base_url": "https://api.openai.com/v1",
                    "default_model": "gpt-3.5-turbo",
                    "rate_limit_rpm": 60,
                    "rate_limit_tpm": 90000,
                    "pricing": {
                        "input_cost_per_1k": 0.0015,
                        "output_cost_per_1k": 0.002
                    }
                }
            }
        }
    
    def reason(self, ir: EdgeKIR, session_id: str = "default") -> GovernanceResult:
        """
        Apply governance policies to the EdgeK IR
        
        Args:
            ir: The normalized internal representation
            session_id: Identifier for the session (for budgeting, etc.)
            
        Returns:
            GovernanceResult: Decision and any modifications
        """
        policies_applied = []
        modified_ir = ir
        decision = GovernanceDecision.ALLOW
        reason_parts = []
        retry_after_seconds = None
        reset_at = None
        
        # Apply L0 meta rules
        meta_result = self._apply_meta_rules(ir, session_id)
        policies_applied.extend(meta_result.policies_applied)
        if meta_result.decision != GovernanceDecision.ALLOW:
            decision = meta_result.decision
            reason_parts.append(meta_result.reason)
            if meta_result.modified_ir:
                modified_ir = meta_result.modified_ir
        
        # If still allowed, apply provider-specific policies
        if decision == GovernanceDecision.ALLOW:
            provider_result = self._apply_provider_policies(ir, session_id)
            policies_applied.extend(provider_result.policies_applied)
            if provider_result.decision != GovernanceDecision.ALLOW:
                if decision == GovernanceDecision.ALLOW:  # Only override if not already denied
                    decision = provider_result.decision
                reason_parts.append(provider_result.reason)
                if provider_result.modified_ir:
                    modified_ir = provider_result.modified_ir

        if decision in (GovernanceDecision.ALLOW, GovernanceDecision.MODIFY):
            semantic_result = self._apply_semantic_risk_rules(modified_ir, session_id)
            policies_applied.extend(semantic_result.policies_applied)
            if semantic_result.decision != GovernanceDecision.ALLOW:
                decision = semantic_result.decision
                reason_parts.append(semantic_result.reason)
                if semantic_result.modified_ir:
                    modified_ir = semantic_result.modified_ir

        if decision in (GovernanceDecision.ALLOW, GovernanceDecision.MODIFY):
            modified_ir, workspace_policy = self._attach_workspace_graph_context(modified_ir)
            if workspace_policy:
                policies_applied.append(workspace_policy)
        
        budget_impact = self._calculate_budget_impact(modified_ir, session_id)
        if decision in (GovernanceDecision.ALLOW, GovernanceDecision.MODIFY):
            budget_result = self._apply_budget_rules(modified_ir, session_id, budget_impact)
            policies_applied.extend(budget_result.policies_applied)
            if budget_result.decision != GovernanceDecision.ALLOW:
                decision = budget_result.decision
                reason_parts.append(budget_result.reason)
                retry_after_seconds = budget_result.retry_after_seconds
                reset_at = budget_result.reset_at

        # TODO: Apply deeper L1-L4 semantic policies as their stores mature.
        
        final_reason = "; ".join(reason_parts) if reason_parts else "No policy violations"
        policies_applied = list(dict.fromkeys(policies_applied))
        
        return GovernanceResult(
            decision=decision,
            modified_ir=modified_ir,
            reason=final_reason,
            policies_applied=policies_applied,
            budget_impact=budget_impact,
            retry_after_seconds=retry_after_seconds,
            reset_at=reset_at
        )
    
    def _apply_meta_rules(self, ir: EdgeKIR, session_id: str) -> GovernanceResult:
        """Apply L0 meta rules from policy"""
        meta_rules = self.policies.get("meta_rules", {})
        policies_applied = []
        
        # Check input token limits
        max_input = meta_rules.get("max_input_tokens_per_request", 8000)
        estimated_input = self._estimate_tokens(ir.messages)
        
        if estimated_input > max_input:
            return GovernanceResult(
                decision=GovernanceDecision.DENY,
                reason=f"Input tokens ({estimated_input}) exceed maximum ({max_input})",
                policies_applied=["max_input_tokens_per_request"]
            )
        
        policies_applied.append("max_input_tokens_per_request")
        
        # Check output token limits
        max_output = meta_rules.get("max_output_tokens_per_request", 2000)
        requested_output = ir.max_tokens or max_output
        
        if requested_output > max_output:
            # Modify the request to comply with limits
            modified_ir = EdgeKIR(
                messages=ir.messages,
                model=ir.model,
                max_tokens=max_output,
                temperature=ir.temperature,
                top_p=ir.top_p,
                stream=ir.stream,
                tools=ir.tools,
                tool_choice=ir.tool_choice,
                stop=ir.stop,
                metadata=ir.metadata
            )
            return GovernanceResult(
                decision=GovernanceDecision.MODIFY,
                modified_ir=modified_ir,
                reason=f"Output tokens reduced from {requested_output} to {max_output}",
                policies_applied=["max_output_tokens_per_request"]
            )
        
        policies_applied.append("max_output_tokens_per_request")
        
        # Check tool call limits
        max_tools = meta_rules.get("max_tool_calls_per_request", 10)
        tool_count = len(ir.tools) if ir.tools else 0
        
        if tool_count > max_tools:
            return GovernanceResult(
                decision=GovernanceDecision.DENY,
                reason=f"Tool calls ({tool_count}) exceed maximum ({max_tools})",
                policies_applied=["max_tool_calls_per_request"]
            )
        
        if tool_count > 0:
            policies_applied.append("max_tool_calls_per_request")
        
        # Check daily request budget (simplified)
        daily_max = meta_rules.get("daily_max_requests", 1000)
        # In production, this would check actual daily usage from storage
        # For now, we'll just note the policy
        policies_applied.append("daily_max_requests")
        
        return GovernanceResult(
            decision=GovernanceDecision.ALLOW,
            reason="Meta rules passed",
            policies_applied=policies_applied
        )
    
    def _apply_provider_policies(self, ir: EdgeKIR, session_id: str) -> GovernanceResult:
        """Apply provider-specific policies"""
        provider_name = ir.metadata.get("provider", "unknown")
        if provider_name == "gemini":
            provider_name = "google"
        if provider_name == "unknown":
            # Try to infer from model
            if ir.model.startswith("gpt"):
                provider_name = "openai"
            elif ir.model.startswith("claude"):
                provider_name = "anthropic"
            elif ir.model.startswith("gemini"):
                provider_name = "gemini"
        
        provider_config = self.policies.get("providers", {}).get(provider_name, {})
        if not provider_config.get("enabled", False):
            return GovernanceResult(
                decision=GovernanceDecision.DENY,
                reason=f"Provider {provider_name} is disabled",
                policies_applied=[f"provider_{provider_name}_enabled"]
            )
        
        policies_applied = [f"provider_{provider_name}_enabled"]
        
        # Apply rate limiting (simplified - in production would use token bucket or similar)
        # For now, just note that rate limiting policy exists
        policies_applied.extend([
            f"provider_{provider_name}_rate_limit_rpm",
            f"provider_{provider_name}_rate_limit_tpm"
        ])
        
        return GovernanceResult(
            decision=GovernanceDecision.ALLOW,
            reason=f"Provider {provider_name} policies passed",
            policies_applied=policies_applied
        )

    def _apply_semantic_risk_rules(self, ir: EdgeKIR, session_id: str) -> GovernanceResult:
        """Apply deterministic semantic safety checks for obvious high-risk prompts."""
        meta_rules = self.policies.get("meta_rules", {})
        if not meta_rules.get("semantic_risk_governance_enabled", True):
            return GovernanceResult(
                decision=GovernanceDecision.ALLOW,
                reason="Semantic risk governance disabled",
                policies_applied=["semantic_risk_governance_disabled"]
            )

        content = " ".join(str(message.get("content", "")) for message in (ir.messages or [])).lower()
        checks = [
            (
                "prompt_injection_resistance",
                ["ignore previous", "override policy", "reveal hidden control"],
                "Prompt injection or policy override attempt blocked",
            ),
            (
                "secret_exfiltration_block",
                [".env", "api key", "secret"],
                "Secret exfiltration request blocked",
            ),
            (
                "destructive_operation_block",
                ["rm -rf", "drop table", "chmod 777"],
                "Destructive operation request blocked",
            ),
            (
                "high_stakes_financial_advice_block",
                ["all my savings", "stock options to buy today", "exactly what stock"],
                "High-stakes financial instruction request blocked",
            ),
        ]

        policies_applied = []
        for policy_name, needles, reason in checks:
            policies_applied.append(policy_name)
            if any(needle in content for needle in needles):
                return GovernanceResult(
                    decision=GovernanceDecision.DENY,
                    reason=reason,
                    policies_applied=policies_applied
                )

        return GovernanceResult(
            decision=GovernanceDecision.ALLOW,
            reason="Semantic risk rules passed",
            policies_applied=policies_applied
        )

    def _apply_budget_rules(
        self,
        ir: EdgeKIR,
        session_id: str,
        budget_impact: Dict[str, Any]
    ) -> GovernanceResult:
        """Apply daily budget and provider rate rules."""
        meta_rules = self.policies.get("meta_rules", {})
        provider_name = self._provider_name(ir)
        provider_config = self.policies.get("providers", {}).get(provider_name, {})
        policies_applied = []

        daily_totals = self.budget_ledger.daily_totals(session_id)
        projected_requests = daily_totals["requests"] + 1
        projected_cost = daily_totals["estimated_cost_usd"] + budget_impact.get("estimated_cost_usd", 0.0)

        daily_max_requests = meta_rules.get("daily_max_requests", 1000)
        policies_applied.append("daily_max_requests")
        if projected_requests > daily_max_requests:
            return GovernanceResult(
                decision=GovernanceDecision.DEFER,
                reason=f"Daily request budget exceeded ({projected_requests}/{daily_max_requests})",
                policies_applied=policies_applied,
                budget_impact=budget_impact,
                retry_after_seconds=self._seconds_until_utc_midnight(),
                reset_at=self._utc_midnight_iso()
            )

        daily_max_cost = meta_rules.get("daily_max_estimated_cost_usd", 10.0)
        policies_applied.append("daily_max_estimated_cost_usd")
        if projected_cost > daily_max_cost:
            return GovernanceResult(
                decision=GovernanceDecision.DEFER,
                reason=f"Daily estimated cost budget exceeded (${projected_cost:.4f}/${daily_max_cost:.4f})",
                policies_applied=policies_applied,
                budget_impact=budget_impact,
                retry_after_seconds=self._seconds_until_utc_midnight(),
                reset_at=self._utc_midnight_iso()
            )

        window_totals = self.budget_ledger.window_totals(provider_name)

        rpm_limit = provider_config.get("rate_limit_rpm")
        if rpm_limit:
            policies_applied.append(f"provider_{provider_name}_rate_limit_rpm")
            if window_totals["requests"] + 1 > rpm_limit:
                return GovernanceResult(
                    decision=GovernanceDecision.DEFER,
                    reason=f"Provider RPM limit exceeded for {provider_name}",
                    policies_applied=policies_applied,
                    budget_impact=budget_impact,
                    retry_after_seconds=window_totals["retry_after_seconds"],
                    reset_at=self._reset_at_iso(window_totals["retry_after_seconds"])
                )

        tpm_limit = provider_config.get("rate_limit_tpm")
        if tpm_limit:
            policies_applied.append(f"provider_{provider_name}_rate_limit_tpm")
            if window_totals["tokens"] + budget_impact.get("estimated_total_tokens", 0) > tpm_limit:
                return GovernanceResult(
                    decision=GovernanceDecision.DEFER,
                    reason=f"Provider TPM limit exceeded for {provider_name}",
                    policies_applied=policies_applied,
                    budget_impact=budget_impact,
                    retry_after_seconds=window_totals["retry_after_seconds"],
                    reset_at=self._reset_at_iso(window_totals["retry_after_seconds"])
                )

        return GovernanceResult(
            decision=GovernanceDecision.ALLOW,
            reason="Budget rules passed",
            policies_applied=policies_applied,
            budget_impact=budget_impact
        )

    def record_usage(self, ir: EdgeKIR, session_id: str, budget_impact: Dict[str, Any]):
        """Record an accepted request after execution."""
        self.budget_ledger.record(
            session_id=session_id,
            provider=self._provider_name(ir),
            model=ir.model,
            budget_impact=budget_impact
        )

    def _provider_name(self, ir: EdgeKIR) -> str:
        provider_name = ir.metadata.get("provider", "unknown")
        if provider_name == "gemini":
            provider_name = "google"
        if provider_name == "unknown":
            if ir.model.startswith("gpt"):
                provider_name = "openai"
            elif ir.model.startswith("claude"):
                provider_name = "anthropic"
            elif ir.model.startswith("gemini"):
                provider_name = "google"
            elif ir.model.startswith(("hf/", "huggingface/")):
                provider_name = "huggingface"
            elif ir.model.startswith(("tgi/", "llamacpp/")):
                provider_name = "tgi"
            elif ir.model.startswith("litellm/"):
                provider_name = "litellm"
        return provider_name

    def _attach_workspace_graph_context(self, ir: EdgeKIR) -> tuple[EdgeKIR, Optional[str]]:
        meta_rules = self.policies.get("meta_rules", {})
        if not meta_rules.get("workspace_graph_context_enabled", True):
            return ir, None

        graph_context = self.workspace_graph.context_for_ir({
            "model": ir.model,
            "messages": ir.messages,
            "metadata": ir.metadata
        })
        if graph_context["matched_node_count"] == 0 and not graph_context["mentioned_files"]:
            return ir, None

        metadata = copy.deepcopy(ir.metadata or {})
        metadata["workspace_graph_context"] = graph_context
        return EdgeKIR(
            messages=ir.messages,
            model=ir.model,
            max_tokens=ir.max_tokens,
            temperature=ir.temperature,
            top_p=ir.top_p,
            stream=ir.stream,
            tools=ir.tools,
            tool_choice=ir.tool_choice,
            stop=ir.stop,
            metadata=metadata
        ), "workspace_graph_context"
    
    def _estimate_tokens(self, messages: list) -> int:
        """Rough token estimation - in production would use proper tokenizer"""
        # Simple approximation: 4 characters per token
        total_chars = sum(len(str(msg.get("content", ""))) for msg in messages)
        return max(1, total_chars // 4)
    
    def _calculate_budget_impact(self, ir: EdgeKIR, session_id: str) -> Dict[str, Any]:
        """Calculate estimated budget impact"""
        input_tokens = self._estimate_tokens(ir.messages)
        output_tokens = ir.max_tokens or 2000  # Default
        provider_name = self._provider_name(ir)
        provider_config = self.policies.get("providers", {}).get(provider_name, {})
        pricing = provider_config.get("pricing", {})
        input_cost_per_1k = float(pricing.get("input_cost_per_1k", 0.002))
        output_cost_per_1k = float(pricing.get("output_cost_per_1k", 0.002))
        
        estimated_cost = (
            (input_tokens / 1000.0) * input_cost_per_1k
            + (output_tokens / 1000.0) * output_cost_per_1k
        )
        
        return {
            "estimated_input_tokens": input_tokens,
            "estimated_output_tokens": output_tokens,
            "estimated_total_tokens": input_tokens + output_tokens,
            "estimated_cost_usd": round(estimated_cost, 6),
            "provider": provider_name,
            "pricing": {
                "input_cost_per_1k": input_cost_per_1k,
                "output_cost_per_1k": output_cost_per_1k
            }
        }

    def _seconds_until_utc_midnight(self) -> int:
        now = time.time()
        return max(1, int(self._next_utc_midnight_epoch(now) - now))

    def _utc_midnight_iso(self) -> str:
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(self._next_utc_midnight_epoch(time.time())))

    def _reset_at_iso(self, retry_after_seconds: int) -> str:
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + max(1, retry_after_seconds)))

    def _next_utc_midnight_epoch(self, now: float) -> float:
        current_day = time.strftime("%Y-%m-%d", time.gmtime(now))
        midnight = calendar.timegm(time.strptime(current_day + " 00:00:00", "%Y-%m-%d %H:%M:%S"))
        return midnight + 86400


# Global reasoner instance
reasoner = Reasoner()

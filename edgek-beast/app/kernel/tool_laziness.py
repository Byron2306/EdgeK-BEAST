"""
Learning tool/provider laziness model.

The learner records tool outcomes and recommends skipping low-value repeated
calls. It is intentionally deterministic and auditable for edge governance.
"""

import sqlite3
import time
import json
from pathlib import Path
from typing import Any, Dict, Optional


class ToolLazinessLearner:
    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            db_path = Path(__file__).resolve().parents[2] / "data" / "tool_laziness.db"
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self):
        return sqlite3.connect(str(self.db_path))

    def _init_db(self):
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tool_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tool_name TEXT NOT NULL,
                    scenario TEXT NOT NULL,
                    called INTEGER NOT NULL,
                    useful INTEGER NOT NULL,
                    tokens_spent INTEGER NOT NULL,
                    cost_usd REAL NOT NULL,
                    latency_ms REAL NOT NULL,
                    value_score REAL NOT NULL DEFAULT 0.0,
                    created_at REAL NOT NULL
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_tool_events_tool_scenario ON tool_events(tool_name, scenario)")
            columns = {
                row[1] for row in conn.execute("PRAGMA table_info(tool_events)").fetchall()
            }
            if "value_score" not in columns:
                conn.execute("ALTER TABLE tool_events ADD COLUMN value_score REAL NOT NULL DEFAULT 0.0")

    def record(
        self,
        tool_name: str,
        scenario: str,
        called: bool,
        useful: bool,
        tokens_spent: int = 0,
        cost_usd: float = 0.0,
        latency_ms: float = 0.0,
        value_score: float = 0.0,
    ) -> Dict[str, Any]:
        with self._connect() as conn:
            conn.execute("""
                INSERT INTO tool_events
                (tool_name, scenario, called, useful, tokens_spent, cost_usd, latency_ms, value_score, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                tool_name,
                scenario,
                1 if called else 0,
                1 if useful else 0,
                int(tokens_spent),
                float(cost_usd),
                float(latency_ms),
                float(value_score),
                time.time(),
            ))
        return self.recommend(tool_name, scenario)

    def recommend(
        self,
        tool_name: str,
        scenario: str,
        min_samples: int = 3,
        skip_usefulness_threshold: float = 0.25,
        call_usefulness_threshold: float = 0.5,
        high_value_threshold: float = 0.35,
        critical_success_threshold: float = 0.8,
    ) -> Dict[str, Any]:
        stats = self.stats(tool_name, scenario)
        if stats["samples"] < min_samples:
            return {**stats, "decision": "learn_more", "reason": "insufficient samples"}
        if stats["usefulness_rate"] >= call_usefulness_threshold:
            return {**stats, "decision": "call", "reason": "learned useful"}
        if stats["max_success_value_score"] >= critical_success_threshold:
            return {**stats, "decision": "call", "reason": "rare critical success observed"}
        if stats["expected_value_score"] >= high_value_threshold:
            return {**stats, "decision": "call", "reason": "low frequency but high expected value"}
        if stats["usefulness_rate"] <= skip_usefulness_threshold and stats["average_tokens_spent"] > 0:
            avoided = {
                "tokens": round(stats["average_tokens_spent"], 2),
                "cost_usd": round(stats["average_cost_usd"], 8),
                "latency_ms": round(stats["average_latency_ms"], 3),
            }
            return {**stats, "decision": "skip", "reason": "low learned usefulness", "estimated_avoidance": avoided}
        return {**stats, "decision": "call", "reason": "learned useful or low cost"}

    def semantic_recommend(
        self,
        tool_name: str,
        scenario: str,
        objective: str,
        workspace_graph: Any,
        min_similarity: float = 0.55,
    ) -> Dict[str, Any]:
        """Blend learned call/skip history with semantic workspace evidence."""
        recommendation = self.recommend(tool_name, scenario)
        context = workspace_graph.semantic_context(objective, limit=5, include_content=False) if workspace_graph and objective else {
            "results": [],
            "semantic_available": False,
        }
        best = max((item.get("similarity", 0.0) for item in context.get("results", [])), default=0.0)
        semantic_decision = recommendation["decision"]
        reason = recommendation["reason"]
        if recommendation["decision"] == "skip" and best >= min_similarity:
            semantic_decision = "call"
            reason = "semantic workspace evidence suggests value despite learned skip"
        elif recommendation["decision"] in ("learn_more", "call") and context.get("semantic_available") and best < (min_similarity * 0.6):
            semantic_decision = "skip"
            reason = "semantic workspace evidence is weak for this objective"
        return {
            **recommendation,
            "decision": semantic_decision,
            "reason": reason,
            "semantic": {
                "available": bool(context.get("semantic_available")),
                "best_similarity": round(best, 5),
                "matches": context.get("results", []),
                "threshold": min_similarity,
            },
        }

    def stats(self, tool_name: Optional[str] = None, scenario: Optional[str] = None) -> Dict[str, Any]:
        clauses = []
        params: list[Any] = []
        if tool_name:
            clauses.append("tool_name = ?")
            params.append(tool_name)
        if scenario:
            clauses.append("scenario = ?")
            params.append(scenario)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._connect() as conn:
            row = conn.execute(f"""
                SELECT COUNT(*), COALESCE(SUM(called), 0), COALESCE(SUM(useful), 0),
                       COALESCE(AVG(tokens_spent), 0), COALESCE(AVG(cost_usd), 0),
                       COALESCE(AVG(latency_ms), 0), COALESCE(SUM(tokens_spent), 0),
                       COALESCE(SUM(cost_usd), 0), COALESCE(AVG(value_score), 0),
                       COALESCE(SUM(CASE WHEN useful = 1 THEN value_score ELSE 0 END), 0),
                       COALESCE(MAX(CASE WHEN useful = 1 THEN value_score ELSE 0 END), 0)
                FROM tool_events
                {where}
            """, params).fetchone()
        samples = row[0] or 0
        useful = row[2] or 0
        usefulness_rate = round(useful / samples, 4) if samples else 0.0
        expected_value = (row[9] or 0.0) / samples if samples else 0.0
        return {
            "tool_name": tool_name,
            "scenario": scenario,
            "samples": samples,
            "calls": row[1] or 0,
            "useful": useful,
            "usefulness_rate": usefulness_rate,
            "average_tokens_spent": row[3] or 0.0,
            "average_cost_usd": row[4] or 0.0,
            "average_latency_ms": row[5] or 0.0,
            "total_tokens_spent": row[6] or 0,
            "total_cost_usd": row[7] or 0.0,
            "average_value_score": round(row[8] or 0.0, 4),
            "expected_value_score": round(expected_value, 4),
            "max_success_value_score": round(row[10] or 0.0, 4),
        }

    def benchmark_learning(self) -> Dict[str, Any]:
        stamp = int(time.time() * 1000)
        scenario = f"redundant_lookup_{stamp}"
        tool_name = "provider_call"
        observations = [
            (True, False, 65, 0.00065, 1300, 0.0),
            (True, False, 62, 0.00062, 1180, 0.0),
            (True, False, 58, 0.00058, 1210, 0.0),
            (True, True, 60, 0.00060, 1160, 0.2),
            (True, False, 64, 0.00064, 1250, 0.0),
        ]
        recommendations = [
            self.record(tool_name, scenario, called, useful, tokens, cost, latency, value_score)
            for called, useful, tokens, cost, latency, value_score in observations
        ]
        final = recommendations[-1]
        critical_scenario = f"rare_high_value_lookup_{stamp}"
        critical_observations = [
            (True, False, 90, 0.0009, 1500, 0.0),
            (True, False, 92, 0.00092, 1480, 0.0),
            (True, True, 95, 0.00095, 1550, 1.0),
            (True, False, 89, 0.00089, 1450, 0.0),
        ]
        critical_recommendations = [
            self.record(tool_name, critical_scenario, called, useful, tokens, cost, latency, value_score)
            for called, useful, tokens, cost, latency, value_score in critical_observations
        ]
        projected_100_calls = {
            "tokens_avoided": round(final.get("estimated_avoidance", {}).get("tokens", 0) * 100, 2),
            "cost_avoided_usd": round(final.get("estimated_avoidance", {}).get("cost_usd", 0) * 100, 8),
            "latency_avoided_ms": round(final.get("estimated_avoidance", {}).get("latency_ms", 0) * 100, 3),
        }
        return {
            "scenario": scenario,
            "observations": len(observations),
            "final_recommendation": final,
            "critical_scenario": critical_scenario,
            "critical_final_recommendation": critical_recommendations[-1],
            "projected_100_redundant_calls": projected_100_calls,
        }

    def benchmark_schema_laziness(
        self,
        tool_count: int = 72,
        turns: int = 36,
        relevant_tools_per_turn: int = 5,
    ) -> Dict[str, Any]:
        """Measure high-token MCP tool-schema laziness.

        Static mode injects every tool schema into every turn. Lazy mode exposes
        only intent-relevant tools and then applies learned skip/call decisions
        for redundant provider/tool calls.
        """
        catalog = self._synthetic_tool_catalog(tool_count)
        intents = ["read", "edit", "test", "search", "git", "provider", "memory", "forensics"]
        static_schema_tokens = sum(self._estimate_tokens(tool) for tool in catalog)
        lazy_schema_tokens = 0
        static_call_tokens = 0
        lazy_call_tokens = 0
        skipped_calls = 0
        called_calls = 0
        decisions = []
        scenario_prefix = f"schema_laziness_{int(time.time() * 1000)}"

        for turn in range(turns):
            intent = intents[turn % len(intents)]
            relevant = self._select_relevant_tools(catalog, intent, relevant_tools_per_turn)
            lazy_schema_tokens += sum(self._estimate_tokens(tool) for tool in relevant)

            # Static agents tend to call a provider/tool every turn because the
            # tool is always visible. Lazy agents learn repeated low-value calls.
            call_tokens = 900 + (turn % 7) * 45
            static_call_tokens += call_tokens
            useful = turn in {3, 17, 29} or intent in {"edit", "test"} and turn % 5 == 0
            value_score = 0.95 if turn in {17, 29} else (0.55 if useful else 0.0)
            scenario = f"{scenario_prefix}:{intent}"
            recommendation = self.record(
                tool_name="provider_call",
                scenario=scenario,
                called=True,
                useful=useful,
                tokens_spent=call_tokens,
                cost_usd=call_tokens * 0.00001,
                latency_ms=850 + (turn % 6) * 120,
                value_score=value_score,
            )
            decision = recommendation["decision"]
            if decision == "skip":
                skipped_calls += 1
            else:
                called_calls += 1
                lazy_call_tokens += call_tokens
            decisions.append({
                "turn": turn,
                "intent": intent,
                "useful": useful,
                "decision": decision,
                "reason": recommendation["reason"],
                "tokens": call_tokens,
            })

        static_total = (static_schema_tokens * turns) + static_call_tokens
        lazy_total = lazy_schema_tokens + lazy_call_tokens
        latency_avoided_ms = skipped_calls * 970.0
        return {
            "tool_count": tool_count,
            "turns": turns,
            "relevant_tools_per_turn": relevant_tools_per_turn,
            "static_schema_tokens_per_turn": static_schema_tokens,
            "static_schema_tokens_total": static_schema_tokens * turns,
            "lazy_schema_tokens_total": lazy_schema_tokens,
            "static_call_tokens_total": static_call_tokens,
            "lazy_call_tokens_total": lazy_call_tokens,
            "static_total_tokens": static_total,
            "lazy_total_tokens": lazy_total,
            "tokens_avoided": static_total - lazy_total,
            "token_reduction_percent": self._percent(static_total - lazy_total, static_total),
            "skipped_calls": skipped_calls,
            "called_calls": called_calls,
            "latency_avoided_ms": round(latency_avoided_ms, 3),
            "estimated_cost_avoided_usd": round((static_total - lazy_total) * 0.00001, 6),
            "sample_decisions": decisions[:12],
        }

    def _synthetic_tool_catalog(self, count: int) -> list[Dict[str, Any]]:
        families = ["read", "edit", "test", "search", "git", "provider", "memory", "forensics"]
        tools = []
        for index in range(count):
            family = families[index % len(families)]
            tools.append({
                "type": "function",
                "function": {
                    "name": f"{family}_tool_{index:03d}",
                    "description": (
                        f"{family} capability for governed agentic coding. "
                        "Use only when the active objective explicitly requires this family. "
                        "Includes policy notes, failure handling, audit metadata, retry guidance, "
                        "security constraints, examples, and verbose MCP schema prose. "
                    ) * 6,
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "Task-specific query or command intent."},
                            "path": {"type": "string", "description": "Workspace path when applicable."},
                            "risk": {"type": "string", "enum": ["low", "medium", "high"]},
                        },
                        "required": ["query"],
                    },
                    "x-edgek-family": family,
                },
            })
        return tools

    def _select_relevant_tools(self, catalog: list[Dict[str, Any]], intent: str, limit: int) -> list[Dict[str, Any]]:
        relevant = [
            tool for tool in catalog
            if tool.get("function", {}).get("x-edgek-family") == intent
        ]
        return relevant[:limit]

    def _estimate_tokens(self, value: Any) -> int:
        return max(1, len(json.dumps(value, separators=(",", ":"), sort_keys=True)) // 4)

    def _percent(self, numerator: float, denominator: float) -> float:
        if not denominator:
            return 0.0
        return round((numerator / denominator) * 100.0, 4)

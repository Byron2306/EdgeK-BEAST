"""Catalog-level MCP recommendations for avoiding low-value tool calls."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List

from app.kernel.data_processing.tool_laziness import ToolLazinessLearner


class ToolLazinessPlugin:
    """Turn learned tool outcomes into explicit call/skip recommendations."""

    def __init__(self, learner: ToolLazinessLearner):
        self.learner = learner

    def recommend_tools(
        self,
        candidate_tools: Iterable[Any],
        scenario: str,
        *,
        required_tools: Iterable[str] = (),
        min_samples: int = 3,
    ) -> Dict[str, Any]:
        required = {str(item) for item in required_tools}
        tools = self._normalize_tools(candidate_tools)
        decisions: List[Dict[str, Any]] = []
        for tool in tools:
            recommendation = self.learner.recommend(tool["name"], scenario, min_samples=max(1, min_samples))
            if tool["name"] in required:
                recommendation = {
                    **recommendation,
                    "decision": "call",
                    "reason": "required by active workflow",
                    "estimated_avoidance": {},
                }
            decisions.append({**tool, **recommendation})

        do_not_call = [item for item in decisions if item["decision"] == "skip"]
        call = [item for item in decisions if item["decision"] == "call"]
        observe = [item for item in decisions if item["decision"] == "learn_more"]
        return {
            "beast_object_type": "tool_laziness_recommendation",
            "version": "1.0",
            "scenario": scenario,
            "tools_not_to_call": do_not_call,
            "tools_to_call": call,
            "tools_to_observe": observe,
            "summary": {
                "candidate_count": len(decisions),
                "skip_count": len(do_not_call),
                "call_count": len(call),
                "learn_more_count": len(observe),
                "estimated_tokens_avoided": round(sum(self._avoided(item, "tokens") for item in do_not_call), 2),
                "estimated_cost_avoided_usd": round(sum(self._avoided(item, "cost_usd") for item in do_not_call), 8),
                "estimated_latency_avoided_ms": round(sum(self._avoided(item, "latency_ms") for item in do_not_call), 3),
            },
            "policy": {
                "required_tools_never_skipped": True,
                "unknown_tools": "learn_more",
                "minimum_samples": max(1, min_samples),
            },
        }

    @staticmethod
    def _normalize_tools(candidate_tools: Iterable[Any]) -> List[Dict[str, str]]:
        normalized = []
        seen = set()
        for raw in candidate_tools:
            if isinstance(raw, dict):
                name = str(raw.get("name") or raw.get("tool_name") or raw.get("id") or "").strip()
                reason = str(raw.get("purpose") or raw.get("description") or "")[:500]
            else:
                name = str(raw).strip()
                reason = ""
            if name and name not in seen:
                normalized.append({"name": name, "purpose": reason})
                seen.add(name)
        return normalized

    @staticmethod
    def _avoided(item: Dict[str, Any], key: str) -> float:
        try:
            return float((item.get("estimated_avoidance") or {}).get(key) or 0.0)
        except (TypeError, ValueError):
            return 0.0


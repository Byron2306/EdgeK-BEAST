"""
EdgeK BEAST V2 promotion loop.

Detects repeated verified artifacts and proposes approval-gated promotion into
route cards, workflow cards, skill recipes, or diagnostic playbooks.
"""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


class PromotionLoop:
    """Create and promote V2 workflow/diagnostic promotion candidates."""

    PROMOTION_STATUSES = [
        "observed",
        "candidate",
        "validated",
        "approved",
        "promoted",
        "degraded",
        "retired",
    ]

    def __init__(
        self,
        task_envelope_builder: Any = None,
        conductor_workflow_builder: Any = None,
        canon_registry: Any = None,
        tool_laziness_learner: Any = None,
        skill_registry: Any = None,
        data_dir: Optional[str] = None,
    ):
        self.task_envelope_builder = task_envelope_builder
        self.conductor_workflow_builder = conductor_workflow_builder
        self.canon_registry = canon_registry
        self.tool_laziness_learner = tool_laziness_learner
        self.skill_registry = skill_registry
        if data_dir is None:
            data_dir = Path(__file__).resolve().parents[2] / "data"
        self.data_dir = Path(data_dir)
        self.candidate_dir = self.data_dir / "promotion_candidates"

    def check(
        self,
        artifacts: Optional[Dict[str, Any]] = None,
        task_class: Optional[str] = None,
        provider: Optional[str] = None,
        category: Optional[str] = None,
        route_id: Optional[str] = None,
        min_repetitions: int = 2,
        persist: bool = True,
    ) -> Dict[str, Any]:
        """Build an approval-gated promotion candidate from current evidence."""
        artifacts = artifacts or {}
        evidence = self._collect_evidence(
            artifacts=artifacts,
            task_class=task_class,
            provider=provider,
            category=category,
            route_id=route_id,
        )
        scenario = self._scenario(evidence, artifacts, task_class, provider, category, route_id)
        laziness = self._tool_laziness_signal(scenario, evidence)
        canon = self._canon_signal(artifacts)
        repetition_count = evidence["chronicle_count"] + evidence["workflow_count"] + evidence["route_card_count"]
        repetition_count += evidence.get("insight_promotion_count", 0)
        target = self._promotion_target(evidence, artifacts)
        eligible = (
            repetition_count >= max(1, int(min_repetitions))
            and canon["valid"]
            and not evidence["has_unresolved_approval_gate"]
        )
        confidence = self._confidence(repetition_count, canon, laziness, evidence)
        ranking = self._ranking_signal(repetition_count, canon, laziness, evidence)
        ranking_metrics = self._ranking_metrics(repetition_count, canon, laziness, evidence)

        candidate = {
            "beast_object_type": "promotion_candidate",
            "version": "1.0",
            "candidate_id": "",
            "candidate_type": target,
            "scenario": scenario,
            "task_class": evidence.get("task_class"),
            "provider": evidence.get("provider"),
            "category": evidence.get("category"),
            "route_id": evidence.get("route_id"),
            "workflow_id": evidence.get("workflow_id"),
            "eligible": eligible,
            "approval_status": "pending_approval" if eligible else "needs_more_evidence",
            "confidence": confidence,
            "priority_score": ranking["priority_score"],
            "ranking": ranking,
            "ranking_metrics": ranking_metrics,
            "promotion_status": "candidate" if eligible else "observed",
            "allowed_promotion_statuses": list(self.PROMOTION_STATUSES),
            "evidence": evidence,
            "canon": canon,
            "tool_laziness": laziness,
            "recommendations": self._recommendations(eligible, target, evidence, canon, laziness),
            "promotion_action": self._promotion_action(target, evidence, artifacts),
            "created_at": self._utc_now(),
            "candidate_hash": "",
        }
        digest = self._hash(candidate)
        candidate["candidate_id"] = f"promo_{digest[:16]}"
        candidate["candidate_hash"] = f"sha256:{digest}"
        if persist:
            candidate["artifact"] = self._write_candidate(candidate)
        return candidate

    def promote(
        self,
        candidate: Optional[Dict[str, Any]] = None,
        candidate_id: Optional[str] = None,
        approved_by: str = "user",
        require_eligible: bool = True,
    ) -> Dict[str, Any]:
        """Promote an approved V2 candidate into the existing skill registry."""
        candidate = candidate or self.get_candidate(str(candidate_id))
        if not candidate:
            raise ValueError("promotion candidate is required")
        if require_eligible and not candidate.get("eligible"):
            raise ValueError("candidate is not eligible for promotion")
        if not self.skill_registry:
            raise ValueError("skill registry is unavailable")

        skill = self.skill_registry.register_skill(
            name=candidate["candidate_type"],
            category="v2_promotion",
            pattern={
                "scenario": candidate.get("scenario"),
                "task_class": candidate.get("task_class"),
                "provider": candidate.get("provider"),
                "category": candidate.get("category"),
                "route_id": candidate.get("route_id"),
            },
            action=candidate.get("promotion_action") or {},
            metadata={
                "candidate_id": candidate.get("candidate_id"),
                "approved_by": approved_by,
                "confidence": candidate.get("confidence"),
                "canon": candidate.get("canon"),
                "tool_laziness": candidate.get("tool_laziness"),
                "candidate_hash": candidate.get("candidate_hash"),
            },
        )
        promoted = dict(candidate)
        promoted["approval_status"] = "promoted"
        promoted["promotion_status"] = "promoted"
        promoted["promoted_at"] = self._utc_now()
        promoted["approved_by"] = approved_by
        promoted["skill"] = self._skill_to_dict(skill)
        self._write_candidate(promoted)
        return {
            "promoted": True,
            "candidate": promoted,
            "skill": promoted["skill"],
        }

    def list_candidates(self, limit: int = 20) -> Dict[str, Any]:
        self.candidate_dir.mkdir(parents=True, exist_ok=True)
        candidates = []
        for path in self.candidate_dir.glob("*.json"):
            try:
                candidates.append(json.loads(path.read_text(encoding="utf-8")))
            except (OSError, json.JSONDecodeError):
                continue
        candidates.sort(key=lambda item: (float(item.get("priority_score") or 0.0), item.get("created_at", "")), reverse=True)
        bounded = candidates[: max(1, min(int(limit), 100))]
        return {
            "promotion_candidates": bounded,
            "count": len(bounded),
            "total_matches": len(candidates),
            "candidate_dir": str(self.candidate_dir),
        }

    def get_candidate(self, candidate_id: str) -> Dict[str, Any]:
        self.candidate_dir.mkdir(parents=True, exist_ok=True)
        path = self.candidate_dir / f"{candidate_id}.json"
        if not path.exists():
            raise ValueError(f"Promotion candidate not found: {candidate_id}")
        return json.loads(path.read_text(encoding="utf-8"))

    def _collect_evidence(
        self,
        artifacts: Dict[str, Any],
        task_class: Optional[str],
        provider: Optional[str],
        category: Optional[str],
        route_id: Optional[str],
    ) -> Dict[str, Any]:
        envelope = artifacts.get("task_envelope") or artifacts.get("envelope") or {}
        diagnostic = artifacts.get("provider_diagnostic") or {}
        workflow = artifacts.get("workflow") or artifacts.get("workflow_card") or {}
        route_card = artifacts.get("route_card") or {}
        scorecard = artifacts.get("forge_scorecard") or {}
        insight = artifacts.get("insight_packet") or artifacts.get("insight") or {}
        insight_summary = insight.get("summary") if isinstance(insight, dict) else {}
        insight_evidence = insight.get("evidence") if isinstance(insight, dict) else []
        if not isinstance(insight_summary, dict):
            insight_summary = {}
        if not isinstance(insight_evidence, list):
            insight_evidence = []
        top_insight = insight_summary.get("top_insight") or (insight_evidence[0] if insight_evidence else {})
        if not isinstance(top_insight, dict):
            top_insight = {}
        resolved_task_class = task_class or envelope.get("task_class") or workflow.get("task_class")
        resolved_provider = provider or diagnostic.get("provider") or route_card.get("provider") or (envelope.get("inputs") or {}).get("provider")
        resolved_category = category or diagnostic.get("failure_category")
        resolved_route = route_id or route_card.get("route_id") or workflow.get("route_id") or scorecard.get("route_id")

        chronicles = {"count": 0, "chronicles": []}
        routes = {"count": 0, "route_cards": []}
        workflows = {"count": 0, "workflow_cards": []}
        if self.task_envelope_builder:
            try:
                chronicles = self.task_envelope_builder.list_chronicles(
                    task_class=resolved_task_class,
                    provider=resolved_provider,
                    category=resolved_category,
                    limit=100,
                )
            except Exception:
                chronicles = {"count": 0, "chronicles": []}
            try:
                routes = self.task_envelope_builder.list_route_cards(
                    task_class=resolved_task_class,
                    provider=resolved_provider,
                    limit=100,
                )
            except Exception:
                routes = {"count": 0, "route_cards": []}
        if self.conductor_workflow_builder:
            try:
                workflows = self.conductor_workflow_builder.list_workflows(
                    task_class=resolved_task_class,
                    limit=100,
                )
            except Exception:
                workflows = {"count": 0, "workflow_cards": []}

        unresolved_gate = False
        for gate in workflow.get("required_gates") or []:
            if gate.get("decision") in ("approval_required", "block"):
                unresolved_gate = True
                break

        return {
            "task_class": resolved_task_class,
            "provider": resolved_provider,
            "category": resolved_category,
            "route_id": resolved_route,
            "workflow_id": workflow.get("workflow_id"),
            "chronicle_count": int(chronicles.get("count", 0) or 0),
            "route_card_count": int(routes.get("count", 0) or 0),
            "workflow_count": int(workflows.get("count", 0) or 0),
            "insight_evidence_count": len(insight_evidence),
            "insight_promotion_count": len([
                item for item in insight_evidence
                if isinstance(item, dict) and item.get("promotion_candidate")
            ]),
            "top_insight_evidence_id": top_insight.get("evidence_id"),
            "top_capability_family": insight_summary.get("top_capability_family") or top_insight.get("capability_family"),
            "recommended_capability_id": top_insight.get("recommended_capability_id"),
            "top_priority_score": float(top_insight.get("priority_score") or 0.0),
            "family_counts": insight_summary.get("family_counts") or {},
            "capability_counts": insight_summary.get("capability_counts") or {},
            "sample_chronicles": chronicles.get("chronicles", [])[:5],
            "sample_route_cards": routes.get("route_cards", [])[:5],
            "sample_workflows": workflows.get("workflow_cards", [])[:5],
            "sample_insight_evidence": insight_evidence[:5],
            "has_unresolved_approval_gate": unresolved_gate,
            "canon_object_count": len([value for value in artifacts.values() if isinstance(value, dict)]),
        }

    def _tool_laziness_signal(self, scenario: str, evidence: Dict[str, Any]) -> Dict[str, Any]:
        if not self.tool_laziness_learner:
            return {"available": False, "decision": "unknown", "reason": "tool laziness learner unavailable"}
        value_score = 0.65 if evidence["chronicle_count"] or evidence["workflow_count"] else 0.2
        recommendation = self.tool_laziness_learner.record(
            tool_name="promotion_candidate",
            scenario=scenario,
            called=True,
            useful=evidence["chronicle_count"] > 0 or evidence["workflow_count"] > 0,
            tokens_spent=120,
            cost_usd=0.0,
            latency_ms=15.0,
            value_score=value_score,
        )
        return {"available": True, **recommendation}

    def _canon_signal(self, artifacts: Dict[str, Any]) -> Dict[str, Any]:
        if not artifacts:
            return {"valid": True, "status": "not_supplied", "errors": [], "warnings": []}
        if not self.canon_registry:
            return {"valid": False, "status": "unavailable", "errors": [{"message": "canon registry unavailable"}], "warnings": []}
        report = self.canon_registry.validate_bundle(self._canon_artifacts(artifacts))
        return {
            "valid": bool(report.get("valid")),
            "status": report.get("status"),
            "errors": report.get("errors", []),
            "warnings": report.get("warnings", []),
            "summary": report.get("summary", {}),
        }

    def _canon_artifacts(self, artifacts: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "task_envelope": artifacts.get("task_envelope") or artifacts.get("envelope"),
            "route_card": artifacts.get("route_card"),
            "quality_report": artifacts.get("quality_report"),
            "context_packet": artifacts.get("context_packet"),
            "forge_scorecard": artifacts.get("forge_scorecard"),
            "workflow": artifacts.get("workflow") or artifacts.get("workflow_card"),
        }

    def _promotion_target(self, evidence: Dict[str, Any], artifacts: Dict[str, Any]) -> str:
        if evidence.get("category") and evidence.get("provider"):
            return "diagnostic_playbook"
        family = evidence.get("top_capability_family")
        if family in ("debugging", "lint_syntax", "tool_bus", "parsing", "vector"):
            return "meta_tool_recipe"
        if family in ("skill", "agentic_cli", "swarm"):
            return "skill_recipe"
        if artifacts.get("workflow") or artifacts.get("workflow_card") or evidence.get("workflow_count"):
            return "workflow_card"
        if artifacts.get("route_card") or evidence.get("route_card_count"):
            return "route_card"
        return "skill_recipe"

    def _confidence(self, repetitions: int, canon: Dict[str, Any], laziness: Dict[str, Any], evidence: Dict[str, Any]) -> float:
        score = min(0.45, repetitions * 0.12)
        if canon.get("valid"):
            score += 0.25
        if laziness.get("decision") in ("call", "skip"):
            score += 0.15
        score += min(0.12, float(evidence.get("top_priority_score") or 0.0) * 0.12)
        if evidence.get("insight_promotion_count"):
            score += 0.08
        if evidence.get("has_unresolved_approval_gate"):
            score -= 0.2
        return round(max(0.0, min(score, 1.0)), 3)

    def _ranking_signal(
        self,
        repetitions: int,
        canon: Dict[str, Any],
        laziness: Dict[str, Any],
        evidence: Dict[str, Any],
    ) -> Dict[str, Any]:
        repetition_score = min(1.0, repetitions / 5.0)
        verification_score = 0.85 if canon.get("valid") else 0.2
        expected_value = float(evidence.get("top_priority_score") or 0.0)
        tool_value = float(laziness.get("expected_value_score") or laziness.get("average_value_score") or 0.0)
        approval_friction = 1.0 if evidence.get("has_unresolved_approval_gate") else 0.0
        safety_score = 1.0 - approval_friction
        priority = (
            expected_value * 0.32
            + verification_score * 0.22
            + repetition_score * 0.18
            + tool_value * 0.12
            + safety_score * 0.16
        )
        if evidence.get("recommended_capability_id"):
            priority += 0.04
        priority = round(max(0.0, min(priority, 1.0)), 5)
        return {
            "priority_score": priority,
            "status": self._ranking_status(priority),
            "components": {
                "expected_value": round(expected_value, 5),
                "verification_score": round(verification_score, 5),
                "repetition_score": round(repetition_score, 5),
                "tool_value": round(tool_value, 5),
                "safety_score": round(safety_score, 5),
                "approval_friction": approval_friction,
                "capability_binding_bonus": 0.04 if evidence.get("recommended_capability_id") else 0.0,
            },
            "weights": {
                "expected_value": 0.32,
                "verification_score": 0.22,
                "repetition_score": 0.18,
                "tool_value": 0.12,
                "safety_score": 0.16,
                "capability_binding_bonus": 0.04,
            },
            "recommendation": self._ranking_recommendation(priority, evidence),
        }

    def _ranking_metrics(
        self,
        repetitions: int,
        canon: Dict[str, Any],
        laziness: Dict[str, Any],
        evidence: Dict[str, Any],
    ) -> Dict[str, Any]:
        samples = int(laziness.get("samples") or 0)
        usefulness_rate = float(laziness.get("usefulness_rate") or 0.0)
        average_latency_ms = float(laziness.get("average_latency_ms") or 0.0)
        estimated_avoidance = laziness.get("estimated_avoidance") or {}
        if not isinstance(estimated_avoidance, dict):
            estimated_avoidance = {}
        return {
            "success_rate": usefulness_rate,
            "failure_rate_after_promotion": 0.0,
            "median_verification_confidence": 0.85 if canon.get("valid") else 0.2,
            "average_tokens_saved": float(estimated_avoidance.get("tokens") or 0.0),
            "average_time_saved_ms": float(estimated_avoidance.get("latency_ms") or 0.0),
            "avoided_cloud_calls": 1 if evidence.get("top_capability_family") in ("tool_bus", "debugging", "lint_syntax") else 0,
            "avoided_risky_tool_calls": 1 if evidence.get("has_unresolved_approval_gate") else 0,
            "recency_weighted_usage": min(1.0, repetitions / 8.0),
            "provider_tool_reliability": usefulness_rate if samples else (0.8 if canon.get("valid") else 0.2),
            "required_approval_rate": 1.0 if evidence.get("has_unresolved_approval_gate") else 0.0,
            "rollback_or_rejection_count": 0,
            "stable_output_schema": bool(canon.get("valid")),
            "sample_count": samples,
            "average_latency_ms": average_latency_ms,
        }

    def _ranking_status(self, priority: float) -> str:
        if priority >= 0.75:
            return "promote_next"
        if priority >= 0.55:
            return "prioritize"
        if priority >= 0.35:
            return "observe"
        return "deprioritize"

    def _ranking_recommendation(self, priority: float, evidence: Dict[str, Any]) -> str:
        if evidence.get("has_unresolved_approval_gate"):
            return "Resolve approval/block gates before promotion."
        if priority >= 0.75:
            return "Prioritize this candidate for approval-gated promotion."
        if priority >= 0.55:
            return "Keep near the top of the promotion queue and gather one more verification signal."
        return "Keep observing until value, repetition, or verification improves."

    def _recommendations(
        self,
        eligible: bool,
        target: str,
        evidence: Dict[str, Any],
        canon: Dict[str, Any],
        laziness: Dict[str, Any],
    ) -> List[str]:
        recs = []
        if eligible:
            recs.append(f"Promote as approval-gated {target}; do not auto-execute.")
        else:
            recs.append("Keep observing until repetitions, Canon validity, and gates are clean.")
        if not canon.get("valid"):
            recs.append("Resolve Canon validation errors before promotion.")
        if evidence.get("has_unresolved_approval_gate"):
            recs.append("Do not promote workflows with unresolved approval/block gates.")
        if evidence.get("recommended_capability_id"):
            recs.append(f"Preserve capability binding {evidence['recommended_capability_id']} in the promoted recipe.")
        if evidence.get("top_capability_family"):
            recs.append(f"Prioritize family {evidence['top_capability_family']} when selecting future tools or skills.")
        if laziness.get("decision") == "skip":
            recs.append("Tool Laziness suggests this pattern can avoid repeated low-value work.")
        elif laziness.get("decision") == "learn_more":
            recs.append("Tool Laziness needs more observations before strong routing decisions.")
        return recs

    def _promotion_action(self, target: str, evidence: Dict[str, Any], artifacts: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "type": target,
            "mode": "approval_gated_reuse",
            "route_id": evidence.get("route_id"),
            "workflow_id": evidence.get("workflow_id"),
            "provider": evidence.get("provider"),
            "category": evidence.get("category"),
            "recommended_capability_id": evidence.get("recommended_capability_id"),
            "capability_family": evidence.get("top_capability_family"),
            "priority_score": evidence.get("top_priority_score"),
            "source_artifacts": {
                key: value.get("beast_object_type") or value.get("chronicle_type")
                for key, value in artifacts.items()
                if isinstance(value, dict)
            },
        }

    def _scenario(
        self,
        evidence: Dict[str, Any],
        artifacts: Dict[str, Any],
        task_class: Optional[str],
        provider: Optional[str],
        category: Optional[str],
        route_id: Optional[str],
    ) -> str:
        parts = [
            task_class or evidence.get("task_class") or "task",
            provider or evidence.get("provider") or "provider",
            category or evidence.get("category") or "category",
            route_id or evidence.get("route_id") or "route",
        ]
        return ":".join(str(part) for part in parts)

    def _write_candidate(self, candidate: Dict[str, Any]) -> Dict[str, Any]:
        self.candidate_dir.mkdir(parents=True, exist_ok=True)
        path = self.candidate_dir / f"{candidate['candidate_id']}.json"
        path.write_text(json.dumps(candidate, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return {"written": True, "path": str(path)}

    def _hash(self, candidate: Dict[str, Any]) -> str:
        stable = dict(candidate)
        stable["candidate_id"] = ""
        stable["candidate_hash"] = ""
        stable.pop("artifact", None)
        serialized = json.dumps(stable, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def _skill_to_dict(self, skill: Any) -> Dict[str, Any]:
        return {
            "id": skill.id,
            "name": skill.name,
            "category": skill.category,
            "pattern": skill.pattern,
            "action": skill.action,
            "success_rate": skill.success_rate,
            "usage_count": skill.usage_count,
            "created_at": skill.created_at,
            "updated_at": skill.updated_at,
            "metadata": skill.metadata,
        }

    def _utc_now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

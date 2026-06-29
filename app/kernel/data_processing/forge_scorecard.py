"""
EdgeK BEAST Forge Scorecards.

Scores proposed implementation/refactor work before edits happen. The first
version is deterministic and local: it uses a task envelope plus optional context
packet/quality report evidence to estimate risk, benefit, and verification needs.
"""

import hashlib
import json
import re
from typing import Any, Dict, List, Optional


class ForgeScorecardBuilder:
    """Build a pre-edit implementation scorecard from BEAST task artifacts."""

    DEPENDENCY_FILES = {
        "package.json",
        "package-lock.json",
        "requirements.txt",
        "pyproject.toml",
        "poetry.lock",
        "go.mod",
        "go.sum",
        "Cargo.toml",
        "Cargo.lock",
    }
    ADAPTER_TERMS = {"adapter", "provider", "router", "route", "gateway", "client"}
    BROAD_REFACTOR_TERMS = {"refactor", "rewrite", "redesign", "architecture", "migrate", "overhaul"}
    BENEFIT_TERMS = {"fix", "diagnose", "test", "verify", "reduce", "local", "safe", "bounded", "quality"}

    def build(
        self,
        envelope: Dict[str, Any],
        context_packet: Optional[Dict[str, Any]] = None,
        quality_report: Optional[Dict[str, Any]] = None,
        route_card: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        request_text = self._request_text(envelope)
        sources = self._evidence_sources(context_packet)
        risk_factors = self._risk_factors(envelope, request_text, sources, quality_report)
        benefit_factors = self._benefit_factors(envelope, request_text, context_packet, quality_report)
        scores = self._scores(risk_factors, benefit_factors, context_packet, quality_report)
        gates = self._gates(scores, risk_factors, envelope)
        recommendations = self._recommendations(scores, gates, risk_factors, benefit_factors)

        scorecard = {
            "beast_object_type": "forge_scorecard",
            "version": "1.0",
            "scorecard_id": "",
            "task_id": envelope.get("task_id"),
            "task_class": envelope.get("task_class"),
            "route_id": (route_card or {}).get("route_id") or (context_packet or {}).get("route_id"),
            "context_packet_id": (context_packet or {}).get("packet_id"),
            "risk_level": envelope.get("risk_level", "medium"),
            "scores": scores,
            "risk_factors": risk_factors,
            "benefit_factors": benefit_factors,
            "required_gates": gates,
            "recommendations": recommendations,
            "decision": self._decision(scores, gates),
            "minimal_patch_first": scores["overall_risk_score"] >= 0.45 or risk_factors["broad_refactor_requested"],
            "compatibility_tests_required": bool(gates.get("compatibility_tests_required")),
            "evidence_summary": {
                "source_count": len(sources),
                "sources": sources[:12],
                "context_packet_hash": (context_packet or {}).get("handoff_hash"),
                "quality_status": (quality_report or {}).get("status"),
            },
            "scorecard_hash": "",
        }
        digest = self._hash(scorecard)
        scorecard["scorecard_id"] = f"forge_{digest[:16]}"
        scorecard["scorecard_hash"] = f"sha256:{digest}"
        return scorecard

    def _risk_factors(
        self,
        envelope: Dict[str, Any],
        request_text: str,
        sources: List[str],
        quality_report: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        lower = request_text.lower()
        dependency_files = [source for source in sources if source.rsplit("/", 1)[-1] in self.DEPENDENCY_FILES]
        adapter_files = [
            source for source in sources
            if any(term in source.lower() for term in self.ADAPTER_TERMS)
        ]
        broad_refactor = any(term in lower for term in self.BROAD_REFACTOR_TERMS)
        risky_verbs = [term for term in ("delete", "remove", "replace", "force", "migration") if term in lower]
        failed_checks = 0
        warnings = 0
        if quality_report:
            summary = quality_report.get("summary") or {}
            failed_checks = int(summary.get("failed", 0) or 0)
            warnings = int(summary.get("warnings", 0) or 0)
        return {
            "broad_refactor_requested": broad_refactor,
            "dependency_files_touched": dependency_files,
            "adapter_or_router_files_touched": adapter_files,
            "risky_verbs": risky_verbs,
            "envelope_risk_level": envelope.get("risk_level", "medium"),
            "quality_failed_checks": failed_checks,
            "quality_warnings": warnings,
            "multi_file_scope": len(sources) > 3,
        }

    def _benefit_factors(
        self,
        envelope: Dict[str, Any],
        request_text: str,
        context_packet: Optional[Dict[str, Any]],
        quality_report: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        lower = request_text.lower()
        success_criteria = envelope.get("success_criteria") or []
        packet_stats = (context_packet or {}).get("packet_stats") or {}
        quality_status = (quality_report or {}).get("status")
        return {
            "clear_success_criteria": len(success_criteria) >= 2,
            "bounded_context_available": int(packet_stats.get("included_count", 0) or 0) > 0,
            "local_quality_available": quality_status in ("passed", "warning", "failed"),
            "benefit_terms": [term for term in self.BENEFIT_TERMS if term in lower],
            "task_class": envelope.get("task_class"),
        }

    def _scores(
        self,
        risk_factors: Dict[str, Any],
        benefit_factors: Dict[str, Any],
        context_packet: Optional[Dict[str, Any]],
        quality_report: Optional[Dict[str, Any]],
    ) -> Dict[str, float]:
        scope_risk = 0.18
        if risk_factors["multi_file_scope"]:
            scope_risk += 0.22
        if risk_factors["broad_refactor_requested"]:
            scope_risk += 0.28
        if risk_factors["risky_verbs"]:
            scope_risk += 0.12

        dependency_risk = min(1.0, 0.12 + len(risk_factors["dependency_files_touched"]) * 0.28)
        compatibility_risk = min(1.0, 0.16 + len(risk_factors["adapter_or_router_files_touched"]) * 0.16)
        if risk_factors["broad_refactor_requested"] and risk_factors["adapter_or_router_files_touched"]:
            compatibility_risk += 0.18

        verification_readiness = 0.25
        if benefit_factors["bounded_context_available"]:
            verification_readiness += 0.2
        if benefit_factors["clear_success_criteria"]:
            verification_readiness += 0.2
        if benefit_factors["local_quality_available"]:
            verification_readiness += 0.2
        if quality_report and quality_report.get("status") == "failed":
            verification_readiness -= 0.12

        benefit_score = 0.25 + len(benefit_factors["benefit_terms"]) * 0.08
        if benefit_factors["clear_success_criteria"]:
            benefit_score += 0.15
        if benefit_factors["bounded_context_available"]:
            benefit_score += 0.12

        quality_penalty = min(0.25, risk_factors["quality_failed_checks"] * 0.12 + risk_factors["quality_warnings"] * 0.04)
        overall_risk = (
            min(scope_risk, 1.0) * 0.38
            + min(dependency_risk, 1.0) * 0.22
            + min(compatibility_risk, 1.0) * 0.28
            + quality_penalty
        )
        if (context_packet or {}).get("excluded_evidence"):
            overall_risk += min(0.12, len(context_packet["excluded_evidence"]) * 0.03)

        return {
            "scope_risk": round(min(scope_risk, 1.0), 3),
            "dependency_risk": round(min(dependency_risk, 1.0), 3),
            "compatibility_risk": round(min(compatibility_risk, 1.0), 3),
            "verification_readiness": round(max(0.0, min(verification_readiness, 1.0)), 3),
            "benefit_score": round(min(benefit_score, 1.0), 3),
            "overall_risk_score": round(min(overall_risk, 1.0), 3),
        }

    def _gates(
        self,
        scores: Dict[str, float],
        risk_factors: Dict[str, Any],
        envelope: Dict[str, Any],
    ) -> Dict[str, Any]:
        compatibility_required = (
            scores["compatibility_risk"] >= 0.48
            or bool(risk_factors["adapter_or_router_files_touched"])
            or risk_factors["broad_refactor_requested"]
        )
        return {
            "compatibility_tests_required": compatibility_required,
            "dependency_review_required": bool(risk_factors["dependency_files_touched"]),
            "human_approval_required": scores["overall_risk_score"] >= 0.72 or envelope.get("risk_level") == "high",
            "minimal_patch_required": scores["scope_risk"] >= 0.5,
            "chronicle_required": True,
        }

    def _recommendations(
        self,
        scores: Dict[str, float],
        gates: Dict[str, Any],
        risk_factors: Dict[str, Any],
        benefit_factors: Dict[str, Any],
    ) -> List[str]:
        recommendations = []
        if gates["minimal_patch_required"]:
            recommendations.append("Use a minimal patch before broad refactor; keep behavior surface stable.")
        if gates["compatibility_tests_required"]:
            recommendations.append("Run adapter/router compatibility tests before accepting the change.")
        if gates["dependency_review_required"]:
            recommendations.append("Review dependency or manifest changes with explicit approval.")
        if scores["verification_readiness"] < 0.55:
            recommendations.append("Add or select verification checks before editing.")
        if not recommendations:
            recommendations.append("Proceed with a small, locally verified implementation path.")
        if benefit_factors["bounded_context_available"]:
            recommendations.append("Use the context packet evidence as the edit boundary.")
        if risk_factors["quality_failed_checks"]:
            recommendations.append("Resolve failed local quality checks before promotion.")
        return recommendations

    def _decision(self, scores: Dict[str, float], gates: Dict[str, Any]) -> str:
        if gates["human_approval_required"]:
            return "approval_required"
        if (
            scores["overall_risk_score"] >= 0.58
            or gates["compatibility_tests_required"]
            or gates["dependency_review_required"]
            or gates["minimal_patch_required"]
        ):
            return "proceed_with_constraints"
        if scores["verification_readiness"] < 0.45:
            return "needs_more_evidence"
        return "proceed"

    def _request_text(self, envelope: Dict[str, Any]) -> str:
        inputs = envelope.get("inputs") or {}
        return "\n".join(
            str(part)
            for part in (envelope.get("intent"), inputs.get("user_request"))
            if part
        )

    def _evidence_sources(self, context_packet: Optional[Dict[str, Any]]) -> List[str]:
        if not context_packet:
            return []
        sources = []
        for item in context_packet.get("included_evidence") or []:
            source = item.get("source")
            if source and item.get("kind") in ("file_snippet", "semantic_match"):
                sources.append(str(source))
        return self._dedupe(sources)

    def _hash(self, scorecard: Dict[str, Any]) -> str:
        stable = dict(scorecard)
        stable["scorecard_id"] = ""
        stable["scorecard_hash"] = ""
        serialized = json.dumps(stable, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def _dedupe(self, values: List[str]) -> List[str]:
        seen = set()
        output = []
        for value in values:
            normalized = re.sub(r"\s+", " ", value).strip()
            if normalized and normalized not in seen:
                seen.add(normalized)
                output.append(normalized)
        return output

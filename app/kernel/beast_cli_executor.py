"""
BEAST agentic CLI executor.

Openclaw is the local-first reasoning and read-only execution profile.
Nemoclaw is the gated high-risk profile for future write/destructive actions.
The executor binds Conductor workflow cards to Ollama-first thinking and
governed MCP requests without bypassing approval policy.
"""

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.kernel.swarm import PROFILE_BINDINGS, ROLE_LANES


class BeastCLIExecutor:
    """Execute workflow recommendations through local inference and MCP gates."""

    SAFE_STEP_IDS = {
        "prepare_task",
        "apply_governance_gates",
        "pack_context",
        "score_patch_shape",
        "select_route",
        "respect_quality_report",
        "run_verification",
        "publish_chronicle",
    }

    def __init__(
        self,
        ollama_scout: Any = None,
        mcp_broker: Any = None,
        canon_registry: Any = None,
        runtime_governor: Any = None,
        tool_laziness_learner: Any = None,
    ):
        self.ollama_scout = ollama_scout
        self.mcp_broker = mcp_broker
        self.canon_registry = canon_registry
        self.runtime_governor = runtime_governor
        self.tool_laziness_learner = tool_laziness_learner

    def plan(
        self,
        objective: str,
        workflow: Optional[Dict[str, Any]] = None,
        context_packet: Optional[Dict[str, Any]] = None,
        insight_packet: Optional[Dict[str, Any]] = None,
        mode: str = "openclaw",
        workspace_root: str = ".",
        use_ollama: bool = True,
        scout_options: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Create a local-first execution plan without executing actions."""
        profile = self._profile(mode)
        scout = self._think(objective, workspace_root, use_ollama, scout_options or {})
        insight = self._insight_summary(insight_packet or {})
        actions = self._actions_from_workflow(workflow or {}, context_packet or {}, profile, insight_packet or {})
        canon = self._canon(workflow, context_packet)
        plan = {
            "beast_object_type": "beast_cli_plan",
            "version": "1.0",
            "mode": profile["mode"],
            "profile": profile,
            "objective": objective,
            "local_inference": scout,
            "local_insight": insight,
            "swarm_binding": self._swarm_binding(workflow or {}, profile),
            "swarm_governance": self._swarm_governance(profile),
            "canon": canon,
            "actions": actions,
            "ready": canon.get("valid", True) and not self._has_blocking_workflow_gate(workflow or {}),
            "created_at": self._utc_now(),
            "plan_hash": "",
        }
        plan["plan_hash"] = self._hash(plan)
        return plan

    def execute(
        self,
        objective: str,
        workflow: Optional[Dict[str, Any]] = None,
        context_packet: Optional[Dict[str, Any]] = None,
        insight_packet: Optional[Dict[str, Any]] = None,
        mode: str = "openclaw",
        workspace_root: str = ".",
        dry_run: bool = True,
        approved: bool = False,
        use_ollama: bool = True,
        scout_options: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Execute allowed workflow actions through MCP, defaulting to dry-run."""
        plan = self.plan(
            objective=objective,
            workflow=workflow,
            context_packet=context_packet,
            insight_packet=insight_packet,
            mode=mode,
            workspace_root=workspace_root,
            use_ollama=use_ollama,
            scout_options=scout_options or {},
        )
        if not plan["ready"]:
            return self._execution_result(plan, [], "blocked", "Canon or workflow gates are not ready")

        results = []
        for action in plan["actions"]:
            if plan["profile"]["mode"] == "zeroclaw":
                results.append({**action, "executed": False, "reason": "zeroclaw_planning_only"})
                continue
            if dry_run:
                results.append({**action, "executed": False, "reason": "dry_run"})
                continue
            if action["risk"] != "read_only" and not approved:
                results.append({**action, "executed": False, "reason": "approval_required"})
                continue
            if action["kind"] == "mcp_request":
                if approved:
                    action = {**action, "request": {**(action.get("request") or {}), "approved": True}}
                results.append(self._execute_mcp_action(action, workspace_root))
            else:
                results.append({**action, "executed": False, "reason": "no executor binding for action kind"})
        status = "succeeded" if any(item.get("executed") for item in results) else ("dry_run" if dry_run else "blocked")
        return self._execution_result(plan, results, status, "BEAST CLI executor completed")

    def _actions_from_workflow(
        self,
        workflow: Dict[str, Any],
        context_packet: Dict[str, Any],
        profile: Dict[str, Any],
        insight_packet: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        actions: List[Dict[str, Any]] = []
        actions.extend(self._actions_from_insight(insight_packet, profile))
        if profile["mode"] != "zeroclaw":
            for evidence in context_packet.get("included_evidence") or []:
                if evidence.get("kind") == "file_snippet" and evidence.get("source"):
                    actions.append({
                        "action_id": f"read_{self._slug(evidence['source'])}",
                        "kind": "mcp_request",
                        "role": "cartographer",
                        "risk": "read_only",
                        "request": {
                            "server_class": "local_read_only",
                            "tool_name": "read_file",
                            "action": "read",
                            "target": evidence["source"],
                            "max_bytes": 12000,
                        },
                    })
        if profile["mode"] == "hermes":
            for role in (workflow.get("swarm") or {}).get("roles", [])[:6]:
                actions.append({
                    "action_id": f"swarm_{self._slug(str(role))}",
                    "kind": "advisory_step",
                    "role": str(role),
                    "risk": "advisory",
                    "summary": f"Hermes coordinates swarm role: {role}",
                })
        if not actions:
            for step in workflow.get("steps", []):
                if profile["mode"] == "nemoclaw" and step.get("step_id") in {"write_file", "patch_file"}:
                    actions.append({
                        "action_id": step.get("step_id"),
                        "kind": "mcp_request",
                        "role": step.get("role", "nemoclaw"),
                        "risk": "gated",
                        "summary": step.get("action", "Write approved file content"),
                        "request": {
                            "server_class": "local_write",
                            "tool_name": "write_file",
                            "action": "write",
                            "target": step.get("target"),
                            "content": step.get("content", ""),
                        },
                    })
                elif step.get("step_id") in self.SAFE_STEP_IDS:
                    actions.append({
                        "action_id": step.get("step_id"),
                        "kind": "advisory_step",
                        "role": step.get("role"),
                        "risk": "advisory",
                        "summary": step.get("action"),
                    })
        if profile["mode"] == "nemoclaw":
            actions.append({
                "action_id": "nemoclaw_requires_explicit_approval",
                "kind": "approval_gate",
                "role": "sentinel",
                "risk": "gated",
                "summary": "Nemoclaw profile requires explicit approval before write/shell execution.",
            })
        return actions[:12]

    def _actions_from_insight(self, insight_packet: Dict[str, Any], profile: Dict[str, Any]) -> List[Dict[str, Any]]:
        if not insight_packet or profile["mode"] == "zeroclaw":
            return []
        actions: List[Dict[str, Any]] = []
        evidence_items = insight_packet.get("evidence") or []
        for idx, evidence in enumerate(evidence_items[:3], start=1):
            provider = evidence.get("provider") or "unknown"
            severity = evidence.get("severity") or "info"
            summary = evidence.get("summary") or evidence.get("evidence_id") or "ranked local evidence"
            role = "sentinel" if severity in ("high", "critical") else "cartographer"
            action_dict = {
                "action_id": f"inspect_insight_{idx}_{self._slug(str(evidence.get('evidence_id') or summary))}",
                "kind": "advisory_step",
                "role": role,
                "risk": "advisory",
                "summary": f"Use ranked local insight for {provider}: {summary}",
                "evidence_id": evidence.get("evidence_id"),
                "expected_value": evidence.get("expected_value"),
                "recommended_actions": evidence.get("recommended_actions", [])[:4],
            }
            # Add capability ID if available from evidence
            capability_id = evidence.get("recommended_capability_id")
            if capability_id:
                action_dict["capability_id"] = capability_id
            actions.append(action_dict)
        top = evidence_items[0] if evidence_items else None
        if top and top.get("recommended_actions"):
            action_dict = {
                "action_id": f"recommend_fix_{self._slug(str(top.get('evidence_id') or top.get('summary')))}",
                "kind": "advisory_step",
                "role": "openclaw" if profile["mode"] == "openclaw" else "hermes",
                "risk": "advisory",
                "summary": str(top["recommended_actions"][0]),
                "evidence_id": top.get("evidence_id"),
            }
            # Add capability ID if available from evidence
            capability_id = top.get("recommended_capability_id")
            if capability_id:
                action_dict["capability_id"] = capability_id
            actions.append(action_dict)
        if insight_packet.get("summary", {}).get("evidence_count", 0):
            actions.append({
                "action_id": "publish_ranked_insight_chronicle",
                "kind": "advisory_step",
                "role": "scribe",
                "risk": "advisory",
                "summary": "Write Chronicle and promotion signals for ranked insight outcome.",
            })
        return actions

    def _insight_summary(self, insight_packet: Dict[str, Any]) -> Dict[str, Any]:
        if not insight_packet:
            return {"available": False, "evidence_count": 0, "top_insight": None}
        summary = insight_packet.get("summary") or {}
        evidence = insight_packet.get("evidence") or []
        return {
            "available": True,
            "ranked": bool(insight_packet.get("ranked")),
            "evidence_count": len(evidence),
            "top_insight": summary.get("top_insight") or (evidence[0] if evidence else None),
            "handoff_recommendation": summary.get("handoff_recommendation"),
        }

    def _swarm_binding(self, workflow: Dict[str, Any], profile: Dict[str, Any]) -> Dict[str, Any]:
        swarm = workflow.get("swarm") or {}
        roles = swarm.get("roles") or []
        return {
            "available": bool(swarm),
            "used": bool(swarm.get("used")),
            "status": swarm.get("status", "not_supplied" if not swarm else "unknown"),
            "execution_capability": swarm.get("execution_capability", "advisory"),
            "roles": roles,
            "role_lanes": {
                role: ROLE_LANES[role]
                for role in ("cartographer", "compressor", "sentinel", "verifier", "scribe", "critic")
            },
            "profile_binding": {
                "mode": profile["mode"],
                "coordinator": "hermes" if profile["mode"] == "hermes" else profile["mode"],
                "model_policy": "ollama_first",
                "mcp_policy": "brokered_read_only_or_approved",
            },
        }

    def _swarm_governance(self, profile: Dict[str, Any]) -> Dict[str, Any]:
        mode = profile["mode"]
        return {
            "profile": PROFILE_BINDINGS.get(mode, PROFILE_BINDINGS["openclaw"]),
            "role_lanes": {
                role: ROLE_LANES[role]
                for role in ("cartographer", "compressor", "sentinel", "verifier", "scribe", "critic")
            },
            "routing": {
                "coordinator": "hermes",
                "local_first": mode in ("openclaw", "hermes", "zeroclaw"),
                "planning_only": mode == "zeroclaw",
                "approval_required": mode == "nemoclaw",
            },
        }

    def _think(self, objective: str, workspace_root: str, use_ollama: bool, scout_options: Dict[str, Any]) -> Dict[str, Any]:
        if not self.ollama_scout:
            return {"available": False, "source": "none", "summary": "Ollama scout unavailable"}
        try:
            result = self.ollama_scout.scout(
                {
                    "task": objective,
                    "use_ollama": use_ollama,
                    "context_limit": 6,
                    "tool_limit": 6,
                    "include_postgres_schema": False,
                    "include_github_context": False,
                    **(scout_options or {}),
                },
                workspace_root=workspace_root,
            )
            packet = result.get("packet", {})
            analysis = packet.get("local_analysis", {})
            forensic_context = packet.get("forensic_context") or {}
            chronicle_summary = packet.get("chronicle_summary") or {}
            return {
                "available": True,
                "source": analysis.get("source", "ollama_or_fallback"),
                "ready_for_cloud": result.get("ready_for_cloud"),
                "selected_tools": result.get("selected_tools", []),
                "decision_contract": result.get("decision_contract", {}),
                "summary": analysis.get("summary"),
                "risk": analysis.get("risk"),
                "confidence": analysis.get("confidence"),
                "ranked_chunks": packet.get("ranked_chunks", [])[:6],
                "chronicle_summary": {
                    "available": bool(chronicle_summary.get("available")),
                    "record_count": chronicle_summary.get("record_count", 0),
                    "summary": chronicle_summary.get("summary"),
                    "records": (chronicle_summary.get("records") or [])[:4],
                },
                "forensic_context": {
                    "available": bool(forensic_context.get("available")),
                    "result_count": forensic_context.get("result_count", 0),
                    "filters": forensic_context.get("filters", {}),
                    "results": (forensic_context.get("results") or [])[:4],
                },
                "fallback_recommendations": packet.get("fallback_recommendations", [])[:6],
                "packet_stats": packet.get("packet_stats", {}),
                "ollama": packet.get("ollama", {}),
            }
        except Exception as exc:
            return {"available": False, "source": "error", "summary": str(exc)}

    def _execute_mcp_action(self, action: Dict[str, Any], workspace_root: str) -> Dict[str, Any]:
        if not self.mcp_broker:
            return {**action, "executed": False, "reason": "MCP broker unavailable"}
        request = action.get("request") or {}
        result = self.mcp_broker.execute(request, workspace_root=workspace_root)
        return {**action, "mcp_result": result, "executed": bool(result.get("executed"))}

    def _canon(self, workflow: Optional[Dict[str, Any]], context_packet: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        if not self.canon_registry:
            return {"valid": True, "status": "unavailable"}
        artifacts = {}
        if workflow:
            artifacts["workflow"] = workflow
        if context_packet:
            artifacts["context_packet"] = context_packet
        if not artifacts:
            return {"valid": True, "status": "not_supplied"}
        report = self.canon_registry.validate_bundle(artifacts)
        return {
            "valid": bool(report.get("valid")),
            "status": report.get("status"),
            "summary": report.get("summary", {}),
            "errors": report.get("errors", []),
        }

    def _has_blocking_workflow_gate(self, workflow: Dict[str, Any]) -> bool:
        for gate in workflow.get("required_gates") or []:
            if gate.get("decision") in ("approval_required", "block"):
                return True
        return False

    def _profile(self, mode: str) -> Dict[str, Any]:
        normalized = str(mode or "openclaw").lower()
        if normalized == "nemoclaw":
            return {
                "mode": "nemoclaw",
                "local_inference_first": True,
                "default_execution": "approval_gated",
                "allowed_risks": ["read_only", "advisory", "gated"],
                "description": "High-risk BEAST role execution profile; write/shell actions require explicit approval.",
            }
        if normalized == "hermes":
            return {
                "mode": "hermes",
                "local_inference_first": True,
                "default_execution": "swarm_coordinated_read_only_or_dry_run",
                "allowed_risks": ["read_only", "advisory"],
                "description": "Swarm coordination profile for planning, role routing, and governed read-only MCP actions.",
            }
        if normalized == "zeroclaw":
            return {
                "mode": "zeroclaw",
                "local_inference_first": True,
                "default_execution": "planning_only",
                "allowed_risks": ["advisory"],
                "description": "Zero-execution profile for local reasoning, task memory retrieval, and dry planning only.",
            }
        return {
            "mode": "openclaw",
            "local_inference_first": True,
            "default_execution": "read_only_or_dry_run",
            "allowed_risks": ["read_only", "advisory"],
            "description": "Local-first BEAST CLI profile for reasoning, planning, and safe read-only execution.",
        }

    def _execution_result(self, plan: Dict[str, Any], results: List[Dict[str, Any]], status: str, reason: str) -> Dict[str, Any]:
        executed = len([item for item in results if item.get("executed")])
        return {
            "beast_object_type": "beast_cli_execution",
            "version": "1.0",
            "status": status,
            "reason": reason,
            "plan": plan,
            "results": results,
            "summary": {
                "action_count": len(results),
                "executed_count": executed,
                "blocked_count": len(results) - executed,
            },
        }

    def _slug(self, value: str) -> str:
        slug = re.sub(r"[^A-Za-z0-9]+", "_", value).strip("_").lower()
        digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:8]
        return f"{slug[:36]}_{digest}"

    def _hash(self, value: Dict[str, Any]) -> str:
        clone = dict(value)
        clone["plan_hash"] = ""
        return "sha256:" + hashlib.sha256(json.dumps(clone, sort_keys=True, default=str).encode("utf-8")).hexdigest()

    def _utc_now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

"""BEAST Agent Scheduler.

This scheduler is a routing brain, not a process runner. It decides which local
or provider lane should be attempted first and records route receipts so the
Provider Economist and cockpit can explain local/cloud split over time.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional
from app.kernel.compute.resource_executor import ResourceExecutor, WorkloadProfile
from app.kernel.compute.interference_buckets import classify as classify_interference


@dataclass(frozen=True)
class AgentLane:
    lane_id: str
    role: str
    locality: str
    cost_rank: int
    latency_rank: int
    capabilities: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "lane_id": self.lane_id,
            "role": self.role,
            "locality": self.locality,
            "cost_rank": self.cost_rank,
            "latency_rank": self.latency_rank,
            "capabilities": list(self.capabilities),
        }


LANES = [
    AgentLane("local_cpu_scout", "scout", "local", 1, 1, ["grep", "files", "rules", "safety"]),
    AgentLane("code_cortex_retriever", "scout", "local", 1, 1, ["symbols", "dependents", "context"]),
    AgentLane("local_verifier", "verifier", "local", 1, 2, ["py_compile", "pytest", "syntax"]),
    AgentLane("local_summarizer", "summarizer", "local", 1, 1, ["compression", "context_digest"]),
    AgentLane("crystal_replay", "implementer", "local", 0, 1, ["replay", "reused_solution"]),
    AgentLane("provider_architect", "architect", "cloud", 5, 4, ["planning", "design"]),
    AgentLane("provider_implementer", "implementer", "cloud", 6, 5, ["action_ir", "sourceplan"]),
    AgentLane("parallel_reviewer", "reviewer", "mixed", 4, 4, ["review", "risk", "verification"]),
]


class AgentScheduler:
    """Route work across BEAST local, replay, and provider lanes."""

    def __init__(self, workspace_root: str | Path):
        self.workspace_root = Path(workspace_root).expanduser().resolve()
        self.store_dir = self.workspace_root / ".beast" / "compute"
        self.receipts_path = self.store_dir / "agent_scheduler_receipts.json"
        self.resource_executor = ResourceExecutor(max_workers=4)

    def lanes(self) -> Dict[str, Any]:
        return {
            "beast_object_type": "beast_agent_scheduler_lanes",
            "version": "1.0",
            "workspace_root": str(self.workspace_root),
            "lanes": [lane.to_dict() for lane in LANES],
        }

    def plan(
        self,
        *,
        objective: str,
        phase: str = "",
        risk: str = "",
        graph_confidence: float = 0.0,
        provider_fitness: float = 0.0,
        crystal_match: bool = False,
        verification_failed: bool = False,
        high_value: bool = False,
        route_inputs: Optional[Dict[str, Any]] = None,
        cpu_pressure: float = 0.0,
        memory_pressure: float = 0.0,
        io_pressure: float = 0.0,
        trust: str = "verified",
    ) -> Dict[str, Any]:
        route_inputs = route_inputs if isinstance(route_inputs, dict) else self.collect_route_inputs(
            objective=objective,
            phase=phase,
            risk=risk,
            provider_fitness=provider_fitness,
            crystal_match=crystal_match,
        )
        selected: List[str] = []
        reasons: List[str] = []
        phase_key = str(phase or "").lower()
        risk_key = str(risk or "").lower()
        if crystal_match:
            selected.append("crystal_replay")
            reasons.append("crystal replay candidate available")
        if ((route_inputs.get("adaptive_dispatcher") or {}) if isinstance(route_inputs.get("adaptive_dispatcher"), dict) else {}).get("local_specialist_available"):
            selected.append("local_verifier")
            reasons.append("adaptive dispatcher reports local specialist candidate")
        if ((route_inputs.get("local_route_optimizer") or {}) if isinstance(route_inputs.get("local_route_optimizer"), dict) else {}).get("recommended_engine"):
            selected.append("local_verifier")
            reasons.append("local route optimizer has prior engine signal")
        if phase_key in {"", "scout", "architect", "debugger"}:
            selected.extend(["local_cpu_scout", "code_cortex_retriever", "local_summarizer"])
            reasons.append("local orientation lanes run before provider escalation")
        if phase_key in {"implement", "implementer", "sourceplan"}:
            selected.extend(["code_cortex_retriever", "local_verifier"])
            if graph_confidence < 0.55 or provider_fitness >= 0.65:
                selected.append("provider_implementer")
                reasons.append("implementation lane requires provider support or low graph confidence")
            else:
                reasons.append("local graph confidence keeps implementation local-first")
        if phase_key in {"review", "reviewer"} or risk_key == "high":
            selected.extend(["local_verifier", "parallel_reviewer"])
            reasons.append("high-risk/review path adds verifier and reviewer lane")
        if verification_failed:
            selected.extend(["local_verifier", "provider_implementer"])
            reasons.append("verification failure enables repair lane")
        if high_value and risk_key in {"medium", "high"}:
            selected.append("parallel_reviewer")
            reasons.append("high-value risky mission gets parallel review")
        if not selected:
            selected.extend(["local_cpu_scout", "code_cortex_retriever"])
            reasons.append("default local scout route")
        selected = list(dict.fromkeys(selected))
        lane_map = {lane.lane_id: lane for lane in LANES}
        selected_lanes = [lane_map[lane_id].to_dict() for lane_id in selected if lane_id in lane_map]
        resource_lane = self._resource_lane(selected, risk_key)
        interference = classify_interference(cpu_pressure=cpu_pressure, memory_pressure=memory_pressure, io_pressure=io_pressure, trust=trust, lane=resource_lane)
        resource_profile = WorkloadProfile(
            resource_lane,
            interference.cpu_weight,
            max(128, interference.memory_concurrency * 256),
            180,
            "sandbox" if resource_lane == "hazardous" else "thread",
        )
        local_count = sum(1 for lane in selected_lanes if lane.get("locality") == "local")
        cloud_count = sum(1 for lane in selected_lanes if lane.get("locality") == "cloud")
        receipt = {
            "beast_object_type": "beast_agent_scheduler_receipt",
            "version": "1.0",
            "route_id": self._route_id(objective, selected),
            "objective": objective,
            "phase": phase,
            "risk": risk,
            "selected_lanes": selected,
            "local_lane_count": local_count,
            "cloud_lane_count": cloud_count,
            "local_first": local_count > 0 and (not selected_lanes or selected_lanes[0].get("locality") == "local"),
            "cost_avoided_estimate": max(0, local_count - cloud_count),
            "reasons": reasons,
            "route_inputs": route_inputs,
            "timestamp": time.time(),
            "resource_profile": resource_profile.__dict__,
            "interference": interference.__dict__,
        }
        self.record(receipt)
        return {
            "beast_object_type": "beast_agent_schedule_plan",
            "version": "1.0",
            "workspace_root": str(self.workspace_root),
            "selected_lanes": selected_lanes,
            "route_explanation": "; ".join(reasons),
            "route_inputs": route_inputs,
            "receipt": receipt,
            "resource_profile": resource_profile.__dict__,
            "interference": interference.__dict__,
        }

    def execute(self, plan: Dict[str, Any], fn, *args, approved: bool = False, sandboxed: bool = False, **kwargs):
        """Execute a scheduled callable through the selected resource lane."""
        profile = WorkloadProfile(**dict(plan.get("resource_profile") or {}))
        return self.resource_executor.submit(profile, fn, *args, approved=approved, sandboxed=sandboxed, **kwargs)

    @staticmethod
    def _resource_lane(selected: List[str], risk: str) -> str:
        if risk in {"high", "critical"}: return "hazardous"
        if "crystal_replay" in selected or "provider_implementer" in selected: return "inference"
        if "local_verifier" in selected: return "cpu"
        if "code_cortex_retriever" in selected: return "io"
        return "interactive"

    def collect_route_inputs(
        self,
        *,
        objective: str = "",
        phase: str = "",
        risk: str = "",
        provider_fitness: float = 0.0,
        crystal_match: bool = False,
    ) -> Dict[str, Any]:
        """Summarize legacy route engines as scheduler inputs, not peer planners."""
        inputs: Dict[str, Any] = {
            "beast_object_type": "beast_agent_scheduler_route_inputs",
            "version": "1.0",
            "workspace_root": str(self.workspace_root),
            "objective": objective,
            "phase": phase,
            "risk": risk,
        }
        inputs["adaptive_dispatcher"] = self._adaptive_dispatcher_input()
        inputs["local_route_optimizer"] = self._local_route_optimizer_input(phase=phase)
        inputs["crystal_runtime_boundary"] = {
            "source": "crystal_runtime_boundary",
            "advisory": True,
            "crystal_match": bool(crystal_match),
            "role": "route_input",
        }
        inputs["inference_engine_fabric"] = self._inference_fabric_input()
        inputs["provider_economist"] = {
            "source": "provider_economist",
            "role": "route_input",
            "provider_fitness": float(provider_fitness or 0.0),
            "escalation_signal": bool(float(provider_fitness or 0.0) >= 0.65),
        }
        inputs["capability_plane"] = self._capability_plane_input(objective=objective, phase=phase, risk=risk)
        inputs["mission_lattice_replay_economics"] = self._mission_lattice_replay_economics_input()
        return inputs

    def summary(self, limit: int = 20) -> Dict[str, Any]:
        receipts = self._load_receipts()
        recent = receipts[: max(1, limit)]
        local = sum(int(item.get("local_lane_count") or 0) for item in recent)
        cloud = sum(int(item.get("cloud_lane_count") or 0) for item in recent)
        return {
            "beast_object_type": "beast_agent_scheduler_summary",
            "version": "1.0",
            "workspace_root": str(self.workspace_root),
            "lane_count": len(LANES),
            "recent_count": len(recent),
            "local_lane_total": local,
            "cloud_lane_total": cloud,
            "local_cloud_split": {"local": local, "cloud": cloud},
            "cost_avoided_estimate": sum(int(item.get("cost_avoided_estimate") or 0) for item in recent),
            "recent_receipts": recent,
            "lanes": [lane.to_dict() for lane in LANES],
        }

    def record(self, receipt: Dict[str, Any]) -> None:
        receipts = self._load_receipts()
        receipts.insert(0, dict(receipt))
        self.store_dir.mkdir(parents=True, exist_ok=True)
        self.receipts_path.write_text(json.dumps(receipts[:250], indent=2, sort_keys=True) + "\n", encoding="utf-8")
        try:
            from app.kernel.evidence.evidence_bus import EvidenceBus

            EvidenceBus(self.workspace_root).register_agent_scheduler_receipt(receipt, receipt_path=self.receipts_path)
        except Exception:
            pass

    def _load_receipts(self) -> List[Dict[str, Any]]:
        try:
            payload = json.loads(self.receipts_path.read_text(encoding="utf-8"))
        except Exception:
            payload = []
        return [item for item in payload if isinstance(item, dict)]

    def _route_id(self, objective: str, selected: List[str]) -> str:
        body = json.dumps({"objective": objective, "lanes": selected, "time": time.time()}, sort_keys=True)
        return "sched_" + hashlib.sha1(body.encode("utf-8")).hexdigest()[:12]

    def _adaptive_dispatcher_input(self) -> Dict[str, Any]:
        path = self.workspace_root / "benchmarks" / "results" / "adapter_candidate_evaluation_latest.json"
        try:
            payload = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
        except Exception:
            payload = {}
        decision = str(payload.get("decision") or "")
        return {
            "source": "adaptive_dispatcher",
            "role": "route_input",
            "evaluation_path": str(path),
            "evaluation_present": bool(payload),
            "decision": decision,
            "local_specialist_available": decision == "candidate_ready_for_local_training",
        }

    def _local_route_optimizer_input(self, *, phase: str = "") -> Dict[str, Any]:
        db_path = self.workspace_root / ".beast" / "compute" / "routes.sqlite"
        recommended = ""
        if db_path.exists():
            try:
                import sqlite3

                task_class = str(phase or "general")
                with sqlite3.connect(db_path) as conn:
                    rows = conn.execute(
                        "SELECT engine_id, successes, failures, avg_latency_ms FROM route_scores WHERE task_class = ?",
                        (task_class,),
                    ).fetchall()
                if rows:
                    def score(row: Any) -> float:
                        _engine, successes, failures, latency = row
                        reliability = float(successes or 0) / max(1.0, float((successes or 0) + (failures or 0)))
                        latency_penalty = min(0.3, float(latency or 0) / 100000.0)
                        return reliability - latency_penalty

                    recommended = str(sorted(rows, key=score, reverse=True)[0][0])
            except Exception:
                recommended = ""
        return {
            "source": "local_route_optimizer",
            "role": "route_input",
            "db_path": str(db_path),
            "available": db_path.exists(),
            "recommended_engine": recommended,
        }

    def _inference_fabric_input(self) -> Dict[str, Any]:
        try:
            from app.kernel.compute.inference_engine_fabric import InferenceEngineFabric

            profiles = [item.to_dict() for item in InferenceEngineFabric().profiles()]
            configured = [item.get("engine_id") for item in profiles if item.get("configured")]
            cpu = [item.get("engine_id") for item in profiles if item.get("configured") and item.get("cpu_supported")]
        except Exception as exc:
            return {
                "source": "inference_engine_fabric",
                "role": "route_input",
                "available": False,
                "error": str(exc),
            }
        return {
            "source": "inference_engine_fabric",
            "role": "route_input",
            "available": True,
            "configured_engines": configured,
            "configured_cpu_engines": cpu,
        }

    def _capability_plane_input(self, *, objective: str = "", phase: str = "", risk: str = "") -> Dict[str, Any]:
        try:
            from app.kernel.capability.capability_plane import CapabilityPlane

            plane = CapabilityPlane(workspace_root=str(self.workspace_root))
            summary = plane.summary(limit=30)
            local = plane.query(text=objective or phase, local=True, reusable=True, limit=8)
            risky = plane.query(risk=risk, limit=8) if risk else {"capabilities": [], "count": 0}
            return {
                "source": "capability_plane",
                "role": "route_input",
                "available": True,
                "capability_count": int(summary.get("capability_count") or 0),
                "local_count": int(summary.get("local_count") or 0),
                "verified_count": int(summary.get("verified_count") or 0),
                "reusable_count": int(summary.get("reusable_count") or 0),
                "local_reusable_matches": [
                    item.get("capability_id")
                    for item in (local.get("capabilities") or [])[:8]
                    if isinstance(item, dict)
                ],
                "risk_matches": [
                    item.get("capability_id")
                    for item in (risky.get("capabilities") or [])[:8]
                    if isinstance(item, dict)
                ],
            }
        except Exception as exc:
            return {
                "source": "capability_plane",
                "role": "route_input",
                "available": False,
                "error": str(exc),
            }

    def _mission_lattice_replay_economics_input(self) -> Dict[str, Any]:
        path = self.workspace_root / ".beast" / "evidence" / "mission_lattice" / "replay_feedback.json"
        try:
            payload = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
            if not isinstance(payload, dict):
                payload = {}
        except Exception as exc:
            return {
                "source": "mission_lattice_replay_feedback",
                "role": "route_input",
                "available": False,
                "index_path": str(path),
                "error": str(exc),
            }
        summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
        return {
            "source": "mission_lattice_replay_feedback",
            "role": "route_input",
            "available": bool(payload),
            "index_path": str(path),
            "replay_scaffolds": int(summary.get("replay_scaffolds") or 0),
            "ready_for_manual_verification": int(summary.get("ready_for_manual_verification") or 0),
            "local_lane_total": int(summary.get("local_lane_total") or 0),
            "cloud_lane_total": int(summary.get("cloud_lane_total") or 0),
            "local_first_signal": int(summary.get("local_lane_total") or 0) >= int(summary.get("cloud_lane_total") or 0),
        }

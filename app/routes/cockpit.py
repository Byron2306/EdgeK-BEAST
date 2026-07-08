"""Mission cockpit, lattice, and evidence route family."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter

from app.cli.api import BeastApiClient
from app.kernel.compute.agent_scheduler import AgentScheduler
from app.kernel.compute.mission_crystal_lattice import MissionCrystalLattice
from app.kernel.evidence.evidence_bus import EvidenceBus
from app.kernel.workspaces.mission_cockpit import MissionCockpit


def build_cockpit_router(default_root: str | Path) -> APIRouter:
    router = APIRouter()
    fallback_root = Path(default_root).expanduser().resolve()

    def _root(value: Any = None) -> Path:
        return Path(value or fallback_root).expanduser().resolve()

    @router.get("/edgek/agent-scheduler/lanes")
    async def edgek_agent_scheduler_lanes(root_path: str = None):
        root = _root(root_path)
        return AgentScheduler(root).lanes()

    @router.post("/edgek/agent-scheduler/plan")
    async def edgek_agent_scheduler_plan(payload: Dict[str, Any] = None):
        payload = payload or {}
        root = _root(payload.get("root_path"))
        return AgentScheduler(root).plan(
            objective=str(payload.get("objective") or ""),
            phase=str(payload.get("phase") or ""),
            risk=str(payload.get("risk") or ""),
            graph_confidence=float(payload.get("graph_confidence") or 0.0),
            provider_fitness=float(payload.get("provider_fitness") or 0.0),
            crystal_match=bool(payload.get("crystal_match", False)),
            verification_failed=bool(payload.get("verification_failed", False)),
            high_value=bool(payload.get("high_value", False)),
        )

    @router.get("/edgek/agent-scheduler/summary")
    async def edgek_agent_scheduler_summary(root_path: str = None, limit: int = 20):
        root = _root(root_path)
        return AgentScheduler(root).summary(limit=max(1, min(int(limit), 100)))

    @router.get("/edgek/mission-cockpit/summary")
    async def edgek_mission_cockpit_summary(root_path: str = None, objective: str = "", phase: str = "scout", risk: str = ""):
        root = _root(root_path)
        return MissionCockpit(root).summary(objective=objective, phase=phase, risk=risk)

    @router.get("/edgek/mission-lattice/summary")
    async def edgek_mission_lattice_summary(root_path: str = None, limit: int = 8):
        root = _root(root_path)
        return MissionCrystalLattice(root).summary(limit=max(1, min(int(limit), 100)))

    @router.post("/edgek/mission-lattice/lookup")
    async def edgek_mission_lattice_lookup(payload: Dict[str, Any] = None):
        payload = payload or {}
        root = _root(payload.get("root_path"))
        plan = payload.get("plan") if isinstance(payload.get("plan"), dict) else {}
        scorecard = payload.get("scorecard") if isinstance(payload.get("scorecard"), dict) else None
        return MissionCrystalLattice(root).lookup(plan, scorecard=scorecard, limit=max(1, min(int(payload.get("limit", 5)), 50)))

    @router.post("/edgek/mission-lattice/replay-scaffold")
    async def edgek_mission_lattice_replay_scaffold(payload: Dict[str, Any] = None):
        payload = payload or {}
        root = _root(payload.get("root_path"))
        plan = payload.get("plan") if isinstance(payload.get("plan"), dict) else {}
        scorecard = payload.get("scorecard") if isinstance(payload.get("scorecard"), dict) else None
        return BeastApiClient(workspace=root).mission_lattice_replay_scaffold(
            plan,
            scorecard=scorecard,
            limit=max(1, min(int(payload.get("limit", 5)), 50)),
        )

    @router.get("/edgek/evidence-bus/summary")
    async def edgek_evidence_bus_summary(root_path: str = None, limit: int = 20):
        root = _root(root_path)
        return EvidenceBus(root).summary(limit=max(1, min(int(limit), 250)))

    @router.get("/edgek/evidence-bus/query")
    async def edgek_evidence_bus_query(
        root_path: str = None,
        task_id: str = "",
        artifact_type: str = "",
        source: str = "",
        status: str = "",
        plan_id: str = "",
        receipt_id: str = "",
        limit: int = 50,
    ):
        root = _root(root_path)
        return EvidenceBus(root).query(
            task_id=task_id,
            artifact_type=artifact_type,
            source=source,
            status=status,
            plan_id=plan_id,
            receipt_id=receipt_id,
            limit=max(1, min(int(limit), 250)),
        )

    @router.get("/edgek/evidence-bus/related/{key}")
    async def edgek_evidence_bus_related(key: str, root_path: str = None, limit: int = 50):
        root = _root(root_path)
        return EvidenceBus(root).related(key, limit=max(1, min(int(limit), 250)))

    return router

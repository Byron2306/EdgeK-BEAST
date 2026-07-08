"""IDE shell route family.

These routes are intentionally presentation-friendly facades over existing
BEAST kernel owners. The VS Code extension should not rebuild Mission Cockpit,
Code Cortex, Evidence Bus, and ADR state by hand.
"""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.kernel.compute.mission_crystal_lattice import MissionCrystalLattice
from app.kernel.evidence.evidence_bus import EvidenceBus
from app.kernel.policy.architecture_decisions import architecture_decision_register
from app.kernel.workspaces.mission_cockpit import MissionCockpit


def build_ide_router(default_root: str | Path, *, code_cortex_router: Any) -> APIRouter:
    router = APIRouter()
    fallback_root = Path(default_root).expanduser().resolve()

    def _root(value: Any = None) -> Path:
        return Path(value or fallback_root).expanduser().resolve()

    @router.get("/edgek/ide/snapshot")
    async def edgek_ide_snapshot(
        root_path: str = None,
        active_file: str = "",
        objective: str = "",
        phase: str = "scout",
        risk: str = "",
        evidence_limit: int = 12,
    ):
        root = _root(root_path)
        query = objective or active_file or "BEAST IDE mission"
        cockpit = MissionCockpit(root).summary(objective=query, phase=phase, risk=risk)
        code_cortex = code_cortex_router.get_editing_context(root, query, limit=12)
        if isinstance(code_cortex, dict):
            code_cortex = {"front_door": "code_cortex", **code_cortex}
        evidence = EvidenceBus(root).summary(limit=max(1, min(int(evidence_limit), 50)))
        lattice = MissionCrystalLattice(root).summary(limit=8)
        architecture = architecture_decision_register()
        return {
            "beast_object_type": "beast_ide_snapshot",
            "version": "1.0",
            "phase": "phase_1_vscode_shell",
            "workspace_root": str(root),
            "active_file": active_file,
            "objective": query,
            "look_and_feel": {
                "source": "beast_tui",
                "palette": {
                    "background": "#050607",
                    "panel": "#0b1113",
                    "border": "#1f3a3d",
                    "acid": "#a6ff3f",
                    "cyan": "#33f6ff",
                    "warning": "#ffd166",
                    "danger": "#ff4d6d",
                    "text": "#d7fbe8",
                    "muted": "#7a8c8d",
                },
            },
            "mission_cockpit": cockpit,
            "sourceplan_queue": cockpit.get("sourceplan_queue") or [],
            "worktrees": cockpit.get("worktrees") if isinstance(cockpit.get("worktrees"), dict) else {},
            "policy": {
                "mode_route": cockpit.get("mode_route") if isinstance(cockpit.get("mode_route"), dict) else {},
                "reintegration_health": cockpit.get("reintegration_health") if isinstance(cockpit.get("reintegration_health"), dict) else {},
                "architecture_decisions": architecture,
            },
            "code_cortex": code_cortex,
            "evidence_bus": evidence,
            "mission_lattice": lattice,
            "operator_actions": [
                "edgekBeast.sourcePlanFromSelection",
                "edgekBeast.scoreCurrentPlan",
                "edgekBeast.openSourceWorkbench",
                "edgekBeast.showEvidence",
                "edgekBeast.createWorktreeMission",
                "edgekBeast.replayLatticeCandidate",
            ],
        }

    def _event(event_type: str, payload: dict[str, Any]) -> str:
        data = {
            "beast_object_type": "beast_ide_event",
            "version": "1.0",
            "event_type": event_type,
            "created_at": int(time.time()),
            "payload": payload,
        }
        return f"event: {event_type}\ndata: {json.dumps(data, sort_keys=True)}\n\n"

    @router.get("/edgek/ide/events")
    async def edgek_ide_events(
        root_path: str = None,
        active_file: str = "",
        objective: str = "",
        phase: str = "scout",
        risk: str = "",
        interval: float = 2.0,
        once: bool = False,
    ):
        async def generate():
            root = _root(root_path)
            query = objective or active_file or "BEAST IDE mission"
            last_payloads: dict[str, str] = {}
            while True:
                cockpit = MissionCockpit(root).summary(objective=query, phase=phase, risk=risk)
                code_cortex = code_cortex_router.get_editing_context(root, query, limit=12)
                if isinstance(code_cortex, dict):
                    code_cortex = {"front_door": "code_cortex", **code_cortex}
                evidence = EvidenceBus(root).summary(limit=12)
                lattice = MissionCrystalLattice(root).summary(limit=8)
                policy = {
                    "mode_route": cockpit.get("mode_route") if isinstance(cockpit.get("mode_route"), dict) else {},
                    "reintegration_health": cockpit.get("reintegration_health") if isinstance(cockpit.get("reintegration_health"), dict) else {},
                    "architecture_decisions": architecture_decision_register(),
                }
                events = {
                    "sourceplan": {"queue": cockpit.get("sourceplan_queue") or []},
                    "policy": policy,
                    "evidence": evidence,
                    "context": {"active_file": active_file, "objective": query, "code_cortex": code_cortex},
                    "worktree": cockpit.get("worktrees") if isinstance(cockpit.get("worktrees"), dict) else {},
                    "lattice": lattice,
                }
                for event_type, payload in events.items():
                    encoded = json.dumps(payload, sort_keys=True, default=str)
                    if once or last_payloads.get(event_type) != encoded:
                        last_payloads[event_type] = encoded
                        yield _event(event_type, payload)
                if once:
                    break
                await asyncio.sleep(max(0.5, min(float(interval), 30.0)))

        return StreamingResponse(generate(), media_type="text/event-stream")

    return router

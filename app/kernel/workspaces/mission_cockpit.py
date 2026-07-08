"""Mission cockpit summary aggregation."""

from __future__ import annotations

import time
import json
from pathlib import Path
from typing import Any, Dict, List

from app.kernel.agents.mode_router import ModeRouter
from app.kernel.capability.capability_plane import CapabilityPlane
from app.kernel.compute.agent_scheduler import AgentScheduler
from app.kernel.compute.mission_crystal_lattice import MissionCrystalLattice
from app.kernel.data_processing.code_cortex import CodeCortexRouter
from app.kernel.evidence.evidence_bus import EvidenceBus
from app.kernel.policy.spec_covenant import SpecCovenantCompiler
from app.kernel.security.safety_governor import SafetyGovernor
from app.kernel.workspaces.worktree_forge import WorktreeForge


COMPAT_SHIM_MODULES = {
    "app.kernel.task_envelope",
    "app.kernel.ollama_scout",
    "app.kernel.commons_spaces",
    "app.kernel.canon_registry",
    "app.kernel.forensic_memory",
    "app.kernel.insight_compiler",
    "app.kernel.beast_cli_executor",
}

COMPAT_SHIM_PATHS = {
    Path("app/kernel/task_envelope.py"),
    Path("app/kernel/ollama_scout.py"),
    Path("app/kernel/commons_spaces.py"),
    Path("app/kernel/canon_registry.py"),
    Path("app/kernel/forensic_memory.py"),
    Path("app/kernel/insight_compiler.py"),
    Path("app/kernel/beast_cli_executor.py"),
}

EXPECTED_EVIDENCE_TYPES = {
    "sourceplan_unified_evidence_packet",
    "sourceplan_negative_evidence_packet",
    "patch_apply_crystallization",
    "memory_hull_write_receipt",
    "beast_agent_scheduler_receipt",
    "beast_safety_command_receipt",
    "beast_safety_workspace_receipt",
    "beast_spec_covenant_receipt",
    "beast_worktree_forge_receipt",
    "beast_worktree_test_receipt",
    "beast_worktree_promotion_receipt",
    "mission_crystal_lattice_cell",
}


class MissionCockpit:
    """Read-only cockpit summary for TUI/web surfaces."""

    def __init__(self, workspace_root: str | Path):
        self.workspace_root = Path(workspace_root).expanduser().resolve()

    def summary(self, *, objective: str = "", phase: str = "scout", risk: str = "") -> Dict[str, Any]:
        mode = ModeRouter().select(phase=phase, risk=risk, sourceplan={"risk_level": risk} if risk else {})
        worktrees = WorktreeForge(self.workspace_root).list()
        scheduler = AgentScheduler(self.workspace_root).summary(limit=12)
        mission_lattice = MissionCrystalLattice(self.workspace_root).summary(limit=8)
        evidence_bus = EvidenceBus(self.workspace_root).summary(limit=12)
        safety = SafetyGovernor(self.workspace_root).scan_workspace(max_files=80)
        covenant = SpecCovenantCompiler(self.workspace_root).compile(
            objective=objective or "Mission cockpit orientation",
            files=[],
            mode=str(mode.get("selected_mode") or ""),
            max_rules=8,
        )
        code_cortex = CodeCortexRouter().status(self.workspace_root)
        capability_plane = CapabilityPlane(workspace_root=str(self.workspace_root)).summary(limit=40)
        cards = [
            self._card("mode", "Agent Mode", mode.get("selected_mode"), mode.get("why"), "ok"),
            self._card("worktrees", "Worktrees", worktrees.get("count"), "isolated mission workspaces", "warn" if worktrees.get("count") else "ok"),
            self._card("safety", "Safety Governor", safety.get("decision"), f"{safety.get('finding_count')} finding(s)", "warn" if safety.get("decision") != "allow" else "ok"),
            self._card("spec", "Spec Covenant", covenant.get("included_count"), covenant.get("covenant_hash"), "warn" if covenant.get("lint", {}).get("severity") == "warn" else "ok"),
            self._card("compute", "Agent Scheduler", scheduler.get("recent_count"), f"local {scheduler.get('local_lane_total')} / cloud {scheduler.get('cloud_lane_total')}", "ok"),
            self._card("mission_lattice", "Mission Lattice", mission_lattice.get("cell_count"), f"{mission_lattice.get('verified_cell_count')} verified / {mission_lattice.get('promotion_cell_count')} promotion", "ok" if mission_lattice.get("cell_count") else "warn"),
            self._card("evidence_bus", "Evidence Bus", evidence_bus.get("receipt_count"), "canonical receipt pointer index", "ok" if evidence_bus.get("receipt_count") else "warn"),
            self._card("code_cortex", "Code Cortex", code_cortex.get("active_adapter"), "context adapters and fallback state", "ok"),
            self._card("capability_plane", "Capability Plane", capability_plane.get("capability_count"), f"{capability_plane.get('verified_count')} verified / {capability_plane.get('local_count')} local", "ok" if capability_plane.get("capability_count") else "warn"),
        ]
        sourceplans = self._sourceplan_queue()
        evidence = self._evidence_stream()
        reintegration = self._reintegration_health(evidence_bus=evidence_bus)
        cards.append(self._card("sourceplans", "SourcePlans", len(sourceplans), "recent patch plans", "warn" if any(item.get("status") == "draft_requires_approval" for item in sourceplans) else "ok"))
        cards.append(self._card("evidence", "Evidence", len(evidence), "recent SourcePlan evidence packets", "ok" if evidence else "warn"))
        cards.append(self._card("reintegration", "Reintegration", reintegration.get("status"), reintegration.get("summary"), "ok" if reintegration.get("status") == "ok" else "warn"))
        blockers = [
            card for card in cards
            if card.get("status") == "warn"
        ]
        return {
            "beast_object_type": "beast_mission_cockpit_summary",
            "version": "1.0",
            "workspace_root": str(self.workspace_root),
            "objective": objective,
            "phase": phase,
            "risk": risk,
            "cards": cards,
            "blockers": blockers,
            "mode_route": mode,
            "worktrees": worktrees,
            "scheduler": scheduler,
            "mission_lattice": mission_lattice,
            "evidence_bus": evidence_bus,
            "safety": safety,
            "reintegration_health": reintegration,
            "sourceplan_queue": sourceplans,
            "evidence_stream": evidence,
            "spec_covenant": {
                "covenant_hash": covenant.get("covenant_hash"),
                "included_count": covenant.get("included_count"),
                "pruned_count": covenant.get("pruned_count"),
                "lint": covenant.get("lint"),
            },
            "code_cortex": code_cortex,
            "capability_plane": capability_plane,
            "timestamp": time.time(),
        }

    def _card(self, card_id: str, title: str, value: Any, detail: Any, status: str) -> Dict[str, Any]:
        return {
            "card_id": card_id,
            "title": title,
            "value": value,
            "detail": detail,
            "status": status,
        }

    def _sourceplan_queue(self, limit: int = 12) -> List[Dict[str, Any]]:
        root = self.workspace_root / ".beast" / "patch_plans"
        rows: List[Dict[str, Any]] = []
        for path in sorted(root.glob("*.json"), key=lambda item: item.stat().st_mtime if item.exists() else 0, reverse=True)[:limit]:
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if not isinstance(payload, dict):
                continue
            rows.append({
                "plan_id": payload.get("plan_id") or path.stem,
                "status": payload.get("status") or "",
                "objective": payload.get("objective") or "",
                "provider": payload.get("provider") or "",
                "path": str(path),
                "preview_hash": payload.get("preview_hash") or "",
                "applied_files": payload.get("applied_files") or [],
            })
        return rows

    def _reintegration_health(self, *, evidence_bus: Dict[str, Any]) -> Dict[str, Any]:
        shim_imports = self._deprecated_shim_imports()
        evidence_coverage = self._evidence_coverage(evidence_bus)
        route_ownership = self._route_ownership_coverage()
        issues: List[str] = []
        if shim_imports:
            issues.append(f"{len(shim_imports)} deprecated shim import(s)")
        if evidence_coverage.get("missing_types"):
            issues.append(f"{len(evidence_coverage.get('missing_types') or [])} missing evidence type(s)")
        if route_ownership.get("unowned_count"):
            issues.append(f"{route_ownership.get('unowned_count')} route family gap(s)")
        status = "warn" if issues else "ok"
        return {
            "beast_object_type": "beast_reintegration_health",
            "version": "1.0",
            "status": status,
            "summary": "; ".join(issues) if issues else "canonical owners and evidence index look aligned",
            "deprecated_shim_imports": shim_imports,
            "duplicate_shim_import_count": len(shim_imports),
            "evidence_coverage": evidence_coverage,
            "route_ownership": route_ownership,
            "orphaned_receipt_count": len(evidence_coverage.get("unexpected_types") or []),
        }

    def _deprecated_shim_imports(self) -> List[Dict[str, Any]]:
        offenders: List[Dict[str, Any]] = []
        roots = [self.workspace_root / "app", self.workspace_root / "tests"]
        ignored = {(self.workspace_root / path).resolve() for path in COMPAT_SHIM_PATHS}
        for root in roots:
            if not root.exists():
                continue
            for path in root.rglob("*.py"):
                try:
                    if path.resolve() in ignored or "__pycache__" in path.parts:
                        continue
                    text = path.read_text(encoding="utf-8", errors="replace")
                except Exception:
                    continue
                for module in sorted(COMPAT_SHIM_MODULES):
                    if f"from {module} import" in text or f"import {module}" in text:
                        offenders.append({
                            "path": path.relative_to(self.workspace_root).as_posix(),
                            "module": module,
                        })
        return offenders[:50]

    def _evidence_coverage(self, evidence_bus: Dict[str, Any]) -> Dict[str, Any]:
        by_type = evidence_bus.get("by_type") if isinstance(evidence_bus.get("by_type"), dict) else {}
        present = {str(key) for key, value in by_type.items() if int(value or 0) > 0}
        missing = sorted(EXPECTED_EVIDENCE_TYPES - present)
        unexpected = sorted(present - EXPECTED_EVIDENCE_TYPES)
        return {
            "expected_types": sorted(EXPECTED_EVIDENCE_TYPES),
            "present_types": sorted(present),
            "missing_types": missing,
            "unexpected_types": unexpected,
            "coverage_ratio": round((len(EXPECTED_EVIDENCE_TYPES) - len(missing)) / max(1, len(EXPECTED_EVIDENCE_TYPES)), 4),
        }

    def _route_ownership_coverage(self) -> Dict[str, Any]:
        doc = self.workspace_root / "docs" / "beast-canonical-ownership.md"
        ownership_patterns: List[str] = []
        try:
            text = doc.read_text(encoding="utf-8", errors="replace")
            for line in text.splitlines():
                if line.startswith("| `/edgek/"):
                    cell = line.split("|")[1].strip()
                    ownership_patterns.extend(part.strip(" `") for part in cell.split(","))
        except Exception:
            text = ""
        route_prefixes = self._route_prefixes()
        unowned = [
            prefix for prefix in route_prefixes
            if not self._route_has_owner(prefix, ownership_patterns)
        ]
        return {
            "ownership_doc": str(doc),
            "documented_family_count": len(ownership_patterns),
            "route_prefix_count": len(route_prefixes),
            "unowned_count": len(unowned),
            "unowned_prefixes": unowned[:50],
        }

    def _route_prefixes(self) -> List[str]:
        main = self.workspace_root / "app" / "main.py"
        prefixes = set()
        try:
            text = main.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return []
        for line in text.splitlines():
            if "@app." not in line or "\"/edgek/" not in line:
                continue
            try:
                route = line.split("\"", 2)[1]
            except Exception:
                continue
            parts = route.strip("/").split("/")
            if len(parts) >= 2:
                prefixes.add("/" + "/".join(parts[:2]))
        return sorted(prefixes)

    def _route_has_owner(self, prefix: str, patterns: List[str]) -> bool:
        for pattern in patterns:
            if not pattern.startswith("/edgek/"):
                continue
            base = pattern.replace("*", "").rstrip("/")
            if base and prefix.startswith(base.rstrip("/")):
                return True
            if "," not in pattern and pattern.startswith(prefix):
                return True
        return False

    def _evidence_stream(self, limit: int = 12) -> List[Dict[str, Any]]:
        root = self.workspace_root / ".beast" / "evidence" / "sourceplan"
        rows: List[Dict[str, Any]] = []
        for path in sorted(root.glob("*.json"), key=lambda item: item.stat().st_mtime if item.exists() else 0, reverse=True)[:limit]:
            if path.name in {"provider_edit_fitness.json", "promotion_candidates.json"}:
                continue
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if not isinstance(payload, dict):
                continue
            rows.append({
                "plan_id": payload.get("plan_id") or path.stem,
                "type": payload.get("beast_object_type") or "",
                "provider": payload.get("provider") or "",
                "promotion_candidate": bool(payload.get("promotion_candidate")),
                "evidence_hash": payload.get("evidence_hash") or "",
                "path": str(path),
                "stage": payload.get("stage") or "",
                "reason": payload.get("reason") or "",
            })
        return rows

"""Read-only adapter that projects BEAST's existing memory organs into Phase 6.

This module creates no competing memory authority. It queries canonical stores
and hands bounded advisory records to memory_architecture.build_memory_context.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.kernel.agents.memory_architecture import build_memory_context
from app.kernel.capability.skill_tree import skill_tree
from app.kernel.evidence.evidence_bus import EvidenceBus
from app.kernel.storage.forensic_memory import ForensicMemory
from app.kernel.storage.memory_hull import MemoryHull


class AgentMemoryRuntime:
    def __init__(self, workspace_root: str | Path, *, workspace_graph: Any = None):
        self.workspace_root = Path(workspace_root).expanduser().resolve()
        self.workspace_graph = workspace_graph
        self.memory_hull = MemoryHull(self.workspace_root / ".beast" / "vault")
        self.evidence_bus = EvidenceBus(self.workspace_root)
        # These are the existing canonical process-wide durable stores.
        self.skill_tree = skill_tree
        self.forensic_memory = ForensicMemory()

    @staticmethod
    def _objective(run: dict[str, Any]) -> str:
        return str(run.get("objective") or "").strip()

    @staticmethod
    def _safe(callable_: Any, fallback: Any) -> Any:
        try:
            return callable_()
        except Exception:
            return fallback

    def project(self, run: dict[str, Any], state: Any, *, limit: int = 4) -> dict[str, Any]:
        objective = self._objective(run)
        run_id = str(run.get("run_id") or getattr(state, "run_id", "") or "")

        episodic = self._safe(
            lambda: self.memory_hull.search(objective, limit=limit) if objective else self.memory_hull.list_residue(limit=limit),
            [],
        )

        durable: list[dict[str, Any]] = []
        if self.workspace_graph is not None and objective:
            durable.extend(self._safe(lambda: self.workspace_graph.search_nodes(objective, limit=limit), []))
        durable.extend(
            self._safe(
                lambda: [
                    {
                        "skill_id": item.get("skill_id") or item.get("id") or "",
                        "name": item.get("name") or "",
                        "category": item.get("category") or "",
                        "source": "skill_tree",
                    }
                    for item in self.skill_tree.list_skills(limit=limit)
                    if isinstance(item, dict)
                ],
                [],
            )
        )
        durable = durable[:limit]

        evidence_query = self._safe(
            lambda: self.evidence_bus.query(task_id=run_id, limit=limit),
            {"receipts": []},
        )
        evidence = list(evidence_query.get("receipts") or [])
        if not evidence and objective:
            related = self._safe(lambda: self.evidence_bus.related(objective, limit=limit), {"receipts": []})
            evidence = list(related.get("receipts") or [])

        forensic_query = self._safe(
            lambda: self.forensic_memory.query(objective, limit=limit),
            {"results": []},
        )
        forensic = list(forensic_query.get("results") or [])

        return build_memory_context(
            run,
            state,
            episodic=episodic,
            durable=durable,
            evidence=evidence,
            forensic=forensic,
            per_role_limit=limit,
        )


def render_memory_context(packet: dict[str, Any], *, char_limit: int = 1800) -> str:
    import json

    compact = json.dumps(packet, sort_keys=True, default=str, separators=(",", ":"))
    limit = max(600, int(char_limit))
    if len(compact) <= limit:
        return "\nMEMORY_CONTEXT:" + compact
    # Preserve the authority/promotion boundary even when retrieval detail is shed.
    minimal = {
        "beast_object_type": packet.get("beast_object_type"),
        "version": packet.get("version"),
        "run_id": packet.get("run_id"),
        "working": packet.get("working"),
        "episodic": list(packet.get("episodic") or [])[:1],
        "durable": list(packet.get("durable") or [])[:1],
        "evidence": list(packet.get("evidence") or [])[:1],
        "forensic": list(packet.get("forensic") or [])[:1],
        "promotion_boundary": packet.get("promotion_boundary"),
        "memory_contract_digest": packet.get("memory_contract_digest"),
        "context_digest": packet.get("context_digest"),
        "compacted": True,
        "authority_preserved": True,
    }
    encoded = json.dumps(minimal, sort_keys=True, default=str, separators=(",", ":"))
    if len(encoded) > limit:
        for role in ("episodic", "durable", "evidence", "forensic"):
            minimal[role] = []
        encoded = json.dumps(minimal, sort_keys=True, default=str, separators=(",", ":"))
    return "\nMEMORY_CONTEXT:" + encoded[:limit]

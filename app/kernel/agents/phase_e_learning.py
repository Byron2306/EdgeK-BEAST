"""Phase E episode compilation and causal evidence archival."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable, Dict, Iterable, Optional

from app.kernel.compute.unified_evidence_packet import UnifiedEvidencePacket


class Scribe:
    """Classify an episode for learning without promoting anything."""

    def compile_episode(
        self,
        *,
        task_class: str,
        events: Iterable[Dict[str, Any]],
        execution: Optional[Dict[str, Any]] = None,
        verification: Optional[Dict[str, Any]] = None,
        critic: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        rows = [dict(item) for item in events if isinstance(item, dict)]
        execution = execution or {}
        verification = verification or {}
        critic = critic or {}
        verified = verification.get("status") == "passed" and critic.get("status", "passed") == "passed"
        classifications = ["repair_pattern" if verified else "negative_evidence"]
        if execution.get("status") == "blocked":
            classifications.append("refusal_pattern")
        if verified and len(rows) >= 4:
            classifications.extend(("execution_candidate", "skill_candidate"))
        episode = {
            "task_class": task_class,
            "episode_status": "verified" if verified else "unverified",
            "classifications": classifications,
            "events": rows,
            "evidence": [str(item.get("details", {}).get("receipt_id") or item.get("decision") or "") for item in rows],
            "promotion_candidate": bool(verified),
            "promotion_authorized": False,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        return episode


class Archivist:
    """Create a unified causal packet and optionally hand it to an evidence writer."""

    def __init__(self, writer: Optional[Callable[[Dict[str, Any]], Any]] = None) -> None:
        self.writer = writer

    def archive(self, episode: Dict[str, Any], *, execution: Optional[Dict[str, Any]] = None, verification: Optional[Dict[str, Any]] = None, critic: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        packet = UnifiedEvidencePacket(
            task_class=str(episode.get("task_class") or "general"),
            request={"episode_status": episode.get("episode_status"), "classifications": episode.get("classifications", [])},
            runtime={"execution_status": (execution or {}).get("status"), "promotion_authorized": False},
            forge=execution or {},
            eval_gate=verification or {},
            trace={"events": episode.get("events", [])},
            negative_cases=[] if episode.get("episode_status") == "verified" else [{"reason": "episode did not close with verified proof"}],
            metrics={"event_count": len(episode.get("events") or []), "critic_status": (critic or {}).get("status", "not_run")},
        ).to_dict()
        receipt = {"packet_hash": packet["packet_hash"], "written": False}
        if self.writer is not None:
            self.writer(packet)
            receipt["written"] = True
        return {"packet": packet, "receipt": receipt, "promotion_authorized": False}

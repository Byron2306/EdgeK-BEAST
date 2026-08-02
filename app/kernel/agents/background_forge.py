"""Phase F asynchronous Forge preparation coordinator."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, Optional


class BackgroundForgeCoordinator:
    """Prepare reusable artifacts without foreground authority or mutation."""

    def __init__(self, node: Any, scheduler: Any = None) -> None:
        self.node = node
        self.scheduler = scheduler

    def prepare(
        self,
        *,
        repo_path: str,
        target_paths: Optional[Iterable[str]] = None,
        test_paths: Optional[Iterable[str]] = None,
        task_class: str = "general",
        route_card: Optional[Dict[str, Any]] = None,
        context_packet: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Run only read/preparation work and return bounded receipts."""
        target_paths = [str(item) for item in target_paths or []]
        test_paths = [str(item) for item in test_paths or []]
        receipts = {
            "fingerprint": self.node.watch_repo(repo_path, target_paths=target_paths),
            "test_impact": self.node.update_test_impact_map(repo_path, test_paths),
            "secret_scan": self.node.perform_secret_scan(repo_path),
        }
        if route_card is not None and context_packet is not None:
            receipts["handoff"] = self.node.prepare_handoff_packet(task_class, route_card, context_packet)
        digest = "sha256:" + hashlib.sha256(json.dumps(receipts, sort_keys=True, default=str).encode()).hexdigest()
        return {
            "beast_object_type": "background_forge_preparation_receipt",
            "version": "1.0",
            "repo_path": repo_path,
            "task_class": task_class,
            "receipts": receipts,
            "preparation_digest": digest,
            "foreground_authority": False,
            "mutation_applied": False,
            "promotion_authorized": False,
            "prepared_at": datetime.now(timezone.utc).isoformat(),
        }

    def submit(self, *, work_type: str, repo_path: str, priority: int = 5, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if self.scheduler is None:
            return {"status": "not_scheduled", "reason": "no background scheduler is bound", "foreground_authority": False}
        item = self.scheduler.submit_work(work_type, repo_path, priority=priority, metadata={**(metadata or {}), "background_only": True, "requires_isolation": False})
        return {"status": "queued", "work_item": item, "foreground_authority": False, "mutation_applied": False}

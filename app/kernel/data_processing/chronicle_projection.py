"""
Governed Chronicle projection adapters.

Drafts are always local. Publish is dry-run unless explicitly approved, so
external systems do not receive side effects by accident.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


class ChronicleProjectionPublisher:
    """Create local projection drafts for Chronicle records."""

    TARGETS = {
        "jira": {"network": True, "format": "adf_or_markdown"},
        "linear": {"network": True, "format": "markdown"},
        "notion": {"network": True, "format": "blocks"},
        "confluence": {"network": True, "format": "storage_or_markdown"},
        "mermaid": {"network": False, "format": "mermaid"},
        "pr_summary": {"network": False, "format": "markdown"},
        "release_note": {"network": False, "format": "markdown"},
    }

    def draft(
        self,
        chronicle: Dict[str, Any],
        *,
        targets: Optional[List[str]] = None,
        approved: bool = False,
        dry_run: bool = True,
    ) -> Dict[str, Any]:
        record = chronicle.get("record") if "record" in chronicle else chronicle
        if not isinstance(record, dict):
            record = {}
        targets = targets or ["pr_summary", "release_note", "mermaid"]
        projections = []
        for target in targets:
            normalized = self._normalize_target(target)
            spec = self.TARGETS.get(normalized)
            if not spec:
                projections.append({
                    "target": target,
                    "status": "unsupported",
                    "requires_approval": True,
                    "content": "",
                })
                continue
            content = self._content_for(normalized, record)
            requires_approval = bool(spec["network"])
            projections.append({
                "target": normalized,
                "status": "draft",
                "format": spec["format"],
                "requires_approval": requires_approval,
                "approved": bool(approved),
                "publishable": bool((not requires_approval or approved) and not dry_run),
                "content": content,
                "content_hash": "sha256:" + hashlib.sha256(content.encode("utf-8")).hexdigest(),
            })
        return {
            "beast_object_type": "chronicle_projection_packet",
            "version": "1.0",
            "mode": "draft" if dry_run else "publish_ready",
            "dry_run": dry_run,
            "approved": approved,
            "chronicle_ref": {
                "task_id": record.get("task_id"),
                "chronicle_type": record.get("chronicle_type"),
                "provider": record.get("provider"),
                "category": record.get("category"),
            },
            "projections": projections,
            "created_at": self._utc_now(),
        }

    def publish(
        self,
        chronicle: Dict[str, Any],
        *,
        targets: Optional[List[str]] = None,
        approved: bool = False,
        dry_run: bool = True,
    ) -> Dict[str, Any]:
        packet = self.draft(chronicle, targets=targets, approved=approved, dry_run=dry_run)
        results = []
        for projection in packet["projections"]:
            if projection["status"] == "unsupported":
                results.append({**projection, "published": False, "reason": "unsupported_target"})
            elif dry_run:
                results.append({**projection, "published": False, "reason": "dry_run"})
            elif projection["requires_approval"] and not approved:
                results.append({**projection, "published": False, "reason": "approval_required"})
            else:
                # Connector writes are intentionally not live yet. This is a
                # governed adapter contract that can later bind to real clients.
                results.append({**projection, "published": False, "reason": "connector_not_configured"})
        return {**packet, "mode": "publish", "results": results}

    def _content_for(self, target: str, record: Dict[str, Any]) -> str:
        if target == "mermaid":
            return self._mermaid(record)
        if target == "release_note":
            return self._release_note(record)
        if target in {"jira", "linear", "notion", "confluence", "pr_summary"}:
            return self._markdown(record, target)
        return json.dumps(record, indent=2, sort_keys=True)

    def _markdown(self, record: Dict[str, Any], target: str) -> str:
        title = record.get("summary") or f"BEAST Chronicle {record.get('task_id', '')}".strip()
        lines = [
            f"# {title}",
            "",
            f"- Target: `{target}`",
            f"- Task: `{record.get('task_id', 'unknown')}`",
            f"- Type: `{record.get('chronicle_type', 'unknown')}`",
            f"- Provider: `{record.get('provider', 'unknown')}`",
            f"- Category: `{record.get('category', 'unknown')}`",
            f"- Confidence: `{record.get('confidence', 'unknown')}`",
            "",
            "## Root Cause",
            "",
            str(record.get("root_cause") or "Not recorded."),
            "",
            "## Recommendations",
            "",
        ]
        for item in record.get("recommendations") or []:
            lines.append(f"- {item}")
        if not record.get("recommendations"):
            lines.append("- No recommendation recorded.")
        return "\n".join(lines) + "\n"

    def _release_note(self, record: Dict[str, Any]) -> str:
        return (
            f"- {record.get('summary') or 'BEAST task completed'} "
            f"({record.get('task_id', 'unknown')}; {record.get('category', 'uncategorized')}).\n"
        )

    def _mermaid(self, record: Dict[str, Any]) -> str:
        task = self._mermaid_label(record.get("task_id") or "task")
        category = self._mermaid_label(record.get("category") or "category")
        return "\n".join([
            "flowchart TD",
            f"  A[{task}] --> B[Local checks]",
            f"  B --> C[{category}]",
            "  C --> D[Recommendations]",
            "  D --> E[Chronicle]",
            "",
        ])

    def _normalize_target(self, target: str) -> str:
        value = str(target or "").strip().lower().replace("-", "_")
        aliases = {"pr": "pr_summary", "pull_request": "pr_summary", "release": "release_note"}
        return aliases.get(value, value)

    def _mermaid_label(self, value: Any) -> str:
        return str(value).replace("[", "(").replace("]", ")").replace("\n", " ")[:80]

    def _utc_now(self) -> str:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

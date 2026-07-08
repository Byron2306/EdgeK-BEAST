"""Canonical evidence pointer index.

The Evidence Bus stores small, privacy-safe pointers to durable BEAST proof
artifacts. It does not replace Chronicle, Memory Hull, SourcePlan evidence, or
crystal stores; it gives cockpit/MCP/API surfaces one place to discover them.
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional


class EvidenceBus:
    """Append/update a compact evidence pointer index for one workspace."""

    def __init__(self, workspace_root: str | Path):
        self.workspace_root = Path(workspace_root).expanduser().resolve()
        self.store_dir = self.workspace_root / ".beast" / "evidence"
        self.index_path = self.store_dir / "evidence_bus.json"

    def register(
        self,
        *,
        artifact_type: str,
        artifact_path: str | Path,
        artifact_hash: str = "",
        source: str = "",
        task_id: str = "",
        status: str = "",
        summary: str = "",
        relationships: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        path_text = str(artifact_path)
        rel_path = self._relative_or_text(path_text)
        receipt = {
            "beast_object_type": "beast_evidence_bus_receipt",
            "version": "1.0",
            "receipt_id": self._receipt_id(artifact_type, rel_path, artifact_hash, task_id),
            "workspace_root": str(self.workspace_root),
            "artifact_type": str(artifact_type or "unknown"),
            "artifact_path": rel_path,
            "artifact_hash": str(artifact_hash or ""),
            "source": str(source or ""),
            "task_id": str(task_id or ""),
            "status": str(status or ""),
            "summary": str(summary or "")[:500],
            "relationships": relationships or {},
            "metadata": self._safe_metadata(metadata or {}),
            "created_at": int(time.time()),
        }
        receipts = self._load_receipts()
        by_id = {str(item.get("receipt_id") or ""): item for item in receipts if isinstance(item, dict)}
        existing = by_id.get(receipt["receipt_id"])
        if existing:
            receipt["first_seen"] = existing.get("first_seen") or existing.get("created_at") or receipt["created_at"]
            receipt["created_at"] = existing.get("created_at") or receipt["created_at"]
            receipt["updated_at"] = int(time.time())
        else:
            receipt["first_seen"] = receipt["created_at"]
            receipt["updated_at"] = receipt["created_at"]
        by_id[receipt["receipt_id"]] = receipt
        self._write_index(list(by_id.values()))
        return receipt

    def register_sourceplan_packet(self, packet: Dict[str, Any], *, packet_path: str | Path) -> Dict[str, Any]:
        is_negative = str(packet.get("beast_object_type") or "").endswith("negative_evidence_packet")
        verification = packet.get("verification") if isinstance(packet.get("verification"), dict) else {}
        preview = packet.get("preview") if isinstance(packet.get("preview"), dict) else {}
        relationships = {
            "chronicle": packet.get("chronicle") if isinstance(packet.get("chronicle"), dict) else {},
            "memory_hull": packet.get("memory_hull") if isinstance(packet.get("memory_hull"), dict) else {},
            "mission_lattice": packet.get("mission_lattice") if isinstance(packet.get("mission_lattice"), dict) else {},
            "governance_receipts": {
                key: True for key, value in ((packet.get("governance_receipts") or {}) if isinstance(packet.get("governance_receipts"), dict) else {}).items()
                if value
            },
        }
        status = (
            "negative"
            if is_negative
            else "verified" if verification.get("ok") else "recorded"
        )
        return self.register(
            artifact_type="sourceplan_negative_evidence_packet" if is_negative else "sourceplan_unified_evidence_packet",
            artifact_path=packet_path,
            artifact_hash=str(packet.get("evidence_hash") or ""),
            source="sourceplan",
            task_id=str(packet.get("plan_id") or ""),
            status=status,
            summary=str(packet.get("reason") or packet.get("objective") or ""),
            relationships=relationships,
            metadata={
                "provider": packet.get("provider") or "",
                "promotion_candidate": bool(packet.get("promotion_candidate")),
                "selected_count": preview.get("selected_count") or 0,
                "stale_count": preview.get("stale_count") or 0,
                "stage": packet.get("stage") or "apply",
            },
        )

    def register_agent_scheduler_receipt(self, receipt: Dict[str, Any], *, receipt_path: str | Path) -> Dict[str, Any]:
        selected_lanes = receipt.get("selected_lanes") if isinstance(receipt.get("selected_lanes"), list) else []
        return self.register(
            artifact_type="beast_agent_scheduler_receipt",
            artifact_path=receipt_path,
            artifact_hash=self._hash_payload(receipt),
            source="agent_scheduler",
            task_id=str(receipt.get("route_id") or ""),
            status="local_first" if receipt.get("local_first") else "planned",
            summary=str(receipt.get("objective") or ""),
            relationships={
                "selected_lanes": [str(item) for item in selected_lanes[:20]],
            },
            metadata={
                "phase": receipt.get("phase") or "",
                "risk": receipt.get("risk") or "",
                "local_lane_count": int(receipt.get("local_lane_count") or 0),
                "cloud_lane_count": int(receipt.get("cloud_lane_count") or 0),
                "cost_avoided_estimate": int(receipt.get("cost_avoided_estimate") or 0),
            },
        )

    def register_mission_lattice_cell(self, cell: Dict[str, Any], *, cells_path: str | Path) -> Dict[str, Any]:
        objective_terms = cell.get("objective_terms") if isinstance(cell.get("objective_terms"), list) else []
        return self.register(
            artifact_type="mission_crystal_lattice_cell",
            artifact_path=cells_path,
            artifact_hash=str(cell.get("fingerprint_hash") or ""),
            source="mission_crystal_lattice",
            task_id=str(cell.get("cell_id") or cell.get("plan_id") or ""),
            status="verified" if cell.get("verification_ok") else "recorded",
            summary=" ".join(str(term) for term in objective_terms[:12]),
            relationships={
                "sourceplan": {
                    "plan_id": str(cell.get("plan_id") or ""),
                    "evidence_hash": str(cell.get("evidence_hash") or ""),
                    "evidence_packet_path": str(cell.get("evidence_packet_path") or ""),
                },
            },
            metadata={
                "provider": cell.get("provider") or "",
                "promotion_candidate": bool(cell.get("promotion_candidate")),
                "occurrence_count": int(cell.get("occurrence_count") or 0),
                "applied_files_count": int(cell.get("applied_files_count") or 0),
            },
        )

    def register_spec_covenant(self, covenant: Dict[str, Any], *, covenant_path: str | Path) -> Dict[str, Any]:
        receipt = covenant.get("receipt") if isinstance(covenant.get("receipt"), dict) else {}
        lint = covenant.get("lint") if isinstance(covenant.get("lint"), dict) else {}
        return self.register(
            artifact_type="beast_spec_covenant_receipt",
            artifact_path=covenant_path,
            artifact_hash=str(covenant.get("covenant_hash") or ""),
            source="spec_covenant",
            task_id=str(covenant.get("covenant_hash") or ""),
            status=str(lint.get("severity") or "ok"),
            summary=str(covenant.get("objective") or ""),
            relationships={
                "receipt": {
                    "covenant_hash": str(receipt.get("covenant_hash") or covenant.get("covenant_hash") or ""),
                    "source_count": int(receipt.get("source_count") or 0),
                    "rule_count": int(receipt.get("rule_count") or 0),
                },
            },
            metadata={
                "mode": covenant.get("mode") or "",
                "included_count": int(covenant.get("included_count") or 0),
                "pruned_count": int(covenant.get("pruned_count") or 0),
                "unsafe_rule_count": len(lint.get("unsafe_rules") or []),
                "duplicate_rule_count": len(lint.get("duplicate_rules") or []),
            },
        )

    def register_safety_receipt(self, receipt: Dict[str, Any], *, receipt_path: str | Path) -> Dict[str, Any]:
        object_type = str(receipt.get("beast_object_type") or "beast_safety_receipt")
        return self.register(
            artifact_type=object_type,
            artifact_path=receipt_path,
            artifact_hash=self._hash_payload(receipt),
            source="safety_governor",
            task_id=str(receipt.get("task_id") or receipt.get("receipt_id") or ""),
            status=str(receipt.get("decision") or "allow"),
            summary=str(receipt.get("command") or f"{receipt.get('finding_count', 0)} finding(s)"),
            relationships={
                "reasons": receipt.get("reasons") if isinstance(receipt.get("reasons"), list) else [],
            },
            metadata={
                "risk_level": receipt.get("risk_level") or "",
                "finding_count": int(receipt.get("finding_count") or 0),
                "mode": receipt.get("mode") or "",
            },
        )

    def register_worktree_receipt(self, receipt: Dict[str, Any], *, registry_path: str | Path) -> Dict[str, Any]:
        return self.register(
            artifact_type=str(receipt.get("beast_object_type") or "beast_worktree_forge_receipt"),
            artifact_path=registry_path,
            artifact_hash=self._hash_payload(receipt),
            source="worktree_forge",
            task_id=str(receipt.get("task_id") or ""),
            status="ok" if receipt.get("ok") else "failed",
            summary=str(receipt.get("action") or receipt.get("beast_object_type") or ""),
            relationships={
                "branch": str(receipt.get("branch") or receipt.get("source_branch") or ""),
                "worktree_path": str(receipt.get("worktree_path") or ""),
            },
            metadata={
                "action": receipt.get("action") or "",
                "approved": bool(receipt.get("approved")),
            },
        )

    def register_chronicle_record(self, record: Dict[str, Any], *, json_path: str | Path, md_path: str | Path = "") -> Dict[str, Any]:
        return self.register(
            artifact_type=str(record.get("artifact_type") or record.get("chronicle_type") or "chronicle_record"),
            artifact_path=json_path,
            artifact_hash=self._hash_payload(record),
            source="chronicle",
            task_id=str(record.get("task_id") or record.get("chronicle_id") or ""),
            status=str(record.get("status") or record.get("category") or "recorded"),
            summary=str(record.get("objective") or record.get("summary") or ""),
            relationships={
                "chronicle_id": str(record.get("chronicle_id") or ""),
                "markdown_path": self._relative_or_text(str(md_path)) if md_path else "",
            },
            metadata={
                "provider": record.get("provider") or "",
                "provider_role": record.get("provider_role") or "",
                "pytest_status": record.get("pytest_status") or "",
                "validation_status": record.get("validation_status") or "",
            },
        )

    def register_memory_hull_receipt(self, receipt: Dict[str, Any]) -> Dict[str, Any]:
        return self.register(
            artifact_type=str(receipt.get("beast_object_type") or "memory_hull_write_receipt"),
            artifact_path=str(receipt.get("sidecar_path") or receipt.get("markdown_path") or receipt.get("index_path") or ""),
            artifact_hash=self._hash_payload(receipt),
            source="memory_hull",
            task_id=str(receipt.get("residue_id") or ""),
            status="verified" if receipt.get("verified") else "failed",
            summary=str(receipt.get("section") or ""),
            relationships={
                "markdown_path": self._relative_or_text(str(receipt.get("markdown_path") or "")),
                "sidecar_path": self._relative_or_text(str(receipt.get("sidecar_path") or "")),
            },
            metadata={
                "section": receipt.get("section") or "",
                "verified": bool(receipt.get("verified")),
            },
        )

    def summary(self, limit: int = 20) -> Dict[str, Any]:
        receipts = sorted(
            self._load_receipts(),
            key=lambda item: int(item.get("updated_at") or item.get("created_at") or 0),
            reverse=True,
        )
        by_type: Dict[str, int] = {}
        by_source: Dict[str, int] = {}
        by_status: Dict[str, int] = {}
        for item in receipts:
            by_type[str(item.get("artifact_type") or "unknown")] = by_type.get(str(item.get("artifact_type") or "unknown"), 0) + 1
            by_source[str(item.get("source") or "unknown")] = by_source.get(str(item.get("source") or "unknown"), 0) + 1
            by_status[str(item.get("status") or "unknown")] = by_status.get(str(item.get("status") or "unknown"), 0) + 1
        return {
            "beast_object_type": "beast_evidence_bus_summary",
            "version": "1.0",
            "workspace_root": str(self.workspace_root),
            "receipt_count": len(receipts),
            "by_type": by_type,
            "by_source": by_source,
            "by_status": by_status,
            "recent": receipts[: max(1, int(limit or 1))],
            "index_path": str(self.index_path),
        }

    def query(
        self,
        *,
        task_id: str = "",
        artifact_type: str = "",
        source: str = "",
        status: str = "",
        plan_id: str = "",
        receipt_id: str = "",
        limit: int = 50,
    ) -> Dict[str, Any]:
        filters = {
            "task_id": str(task_id or ""),
            "artifact_type": str(artifact_type or ""),
            "source": str(source or ""),
            "status": str(status or ""),
            "plan_id": str(plan_id or ""),
            "receipt_id": str(receipt_id or ""),
        }
        receipts = [
            item for item in self._sorted_receipts()
            if self._matches_filters(item, filters)
        ]
        return {
            "beast_object_type": "beast_evidence_bus_query",
            "version": "1.0",
            "workspace_root": str(self.workspace_root),
            "filters": {key: value for key, value in filters.items() if value},
            "match_count": len(receipts),
            "receipts": receipts[: max(1, int(limit or 1))],
            "index_path": str(self.index_path),
        }

    def related(self, key: str, *, limit: int = 50) -> Dict[str, Any]:
        needle = str(key or "").strip()
        receipts = [
            item for item in self._sorted_receipts()
            if needle and self._receipt_contains(item, needle)
        ]
        grouped: Dict[str, int] = {}
        for item in receipts:
            grouped[str(item.get("artifact_type") or "unknown")] = grouped.get(str(item.get("artifact_type") or "unknown"), 0) + 1
        return {
            "beast_object_type": "beast_evidence_bus_related",
            "version": "1.0",
            "workspace_root": str(self.workspace_root),
            "key": needle,
            "match_count": len(receipts),
            "by_type": grouped,
            "receipts": receipts[: max(1, int(limit or 1))],
            "index_path": str(self.index_path),
        }

    def _relative_or_text(self, value: str) -> str:
        try:
            path = Path(value).expanduser().resolve()
            if path == self.workspace_root or self.workspace_root in path.parents:
                return str(path.relative_to(self.workspace_root))
        except Exception:
            pass
        return str(value)

    def _receipt_id(self, artifact_type: str, path: str, artifact_hash: str, task_id: str) -> str:
        body = json.dumps({
            "artifact_type": artifact_type,
            "path": path,
            "artifact_hash": artifact_hash,
            "task_id": task_id,
        }, sort_keys=True, default=str)
        return "evb_" + hashlib.sha256(body.encode("utf-8")).hexdigest()[:18]

    def _hash_payload(self, payload: Dict[str, Any]) -> str:
        body = json.dumps(payload, sort_keys=True, default=str)
        return "sha256:" + hashlib.sha256(body.encode("utf-8", errors="replace")).hexdigest()

    def _safe_metadata(self, metadata: Dict[str, Any]) -> Dict[str, Any]:
        safe: Dict[str, Any] = {}
        for key, value in metadata.items():
            if isinstance(value, (str, int, float, bool)) or value is None:
                safe[str(key)] = value
            elif isinstance(value, list):
                safe[str(key)] = [item for item in value if isinstance(item, (str, int, float, bool))][:20]
            elif isinstance(value, dict):
                safe[str(key)] = {str(k): v for k, v in value.items() if isinstance(v, (str, int, float, bool))}
        return safe

    def _load_receipts(self) -> List[Dict[str, Any]]:
        try:
            payload = json.loads(self.index_path.read_text(encoding="utf-8"))
        except Exception:
            payload = {}
        receipts = payload.get("receipts") if isinstance(payload, dict) else payload
        return [item for item in (receipts or []) if isinstance(item, dict)]

    def _sorted_receipts(self) -> List[Dict[str, Any]]:
        return sorted(
            self._load_receipts(),
            key=lambda item: int(item.get("updated_at") or item.get("created_at") or 0),
            reverse=True,
        )

    def _matches_filters(self, item: Dict[str, Any], filters: Dict[str, str]) -> bool:
        for key, value in filters.items():
            if not value:
                continue
            if key == "plan_id":
                if not self._receipt_contains(item, value):
                    return False
                continue
            if str(item.get(key) or "") != value:
                return False
        return True

    def _receipt_contains(self, item: Dict[str, Any], needle: str) -> bool:
        if not needle:
            return False
        haystacks = [
            item.get("receipt_id"),
            item.get("task_id"),
            item.get("artifact_path"),
            item.get("artifact_hash"),
            item.get("summary"),
        ]
        relationships = item.get("relationships") if isinstance(item.get("relationships"), dict) else {}
        metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        haystacks.append(json.dumps(relationships, sort_keys=True, default=str))
        haystacks.append(json.dumps(metadata, sort_keys=True, default=str))
        return any(needle in str(value or "") for value in haystacks)

    def _write_index(self, receipts: List[Dict[str, Any]]) -> None:
        receipts = sorted(
            receipts,
            key=lambda item: int(item.get("updated_at") or item.get("created_at") or 0),
            reverse=True,
        )[:2000]
        self.store_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "beast_object_type": "beast_evidence_bus_index",
            "version": "1.0",
            "workspace_root": str(self.workspace_root),
            "updated_at": int(time.time()),
            "receipt_count": len(receipts),
            "receipts": receipts,
        }
        self.index_path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")

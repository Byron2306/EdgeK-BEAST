"""Persistent IDE agent sessions for BEAST."""

from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional


def _now() -> float:
    return time.time()


def _safe_slug(value: str, fallback: str = "agent") -> str:
    slug = re.sub(r"[^a-zA-Z0-9._-]+", "-", str(value or "").strip().lower()).strip("-._")
    return (slug or fallback)[:64]


class AgentSessionStore:
    """Store resumable agent workspaces without granting direct mutation rights."""

    def __init__(self, workspace_root: str | Path):
        self.workspace_root = Path(workspace_root).expanduser().resolve()
        self.store_dir = self.workspace_root / ".beast" / "agent_sessions"
        self.registry_path = self.store_dir / "sessions.json"

    def list(self) -> Dict[str, Any]:
        sessions = self._load().get("sessions") or []
        return {
            "beast_object_type": "beast_agent_session_registry",
            "version": "1.0",
            "workspace_root": str(self.workspace_root),
            "count": len(sessions),
            "sessions": sessions,
        }

    def create(
        self,
        *,
        objective: str,
        mode: str = "architect",
        budget: Optional[Dict[str, Any]] = None,
        tools: Optional[List[str]] = None,
        files: Optional[List[str]] = None,
        agent_id: str = "",
        provider: str = "",
        model: str = "",
    ) -> Dict[str, Any]:
        seed = f"{agent_id}:{objective}:{_now()}"
        session_id = f"{_safe_slug(agent_id or mode or 'agent')}-{hashlib.sha1(seed.encode('utf-8')).hexdigest()[:8]}"
        record = {
            "beast_object_type": "beast_agent_session",
            "version": "1.0",
            "session_id": session_id,
            "agent_id": agent_id or session_id,
            "objective": objective,
            "mode": mode or "architect",
            "provider": provider,
            "model": model,
            "status": "active",
            "budget": budget or {"tokens": 0, "seconds": 0, "cost_usd": 0.0},
            "tools": [str(item) for item in (tools or [])],
            "files": [str(item) for item in (files or [])],
            "evidence": [],
            "outputs": [],
            "created_at": _now(),
            "updated_at": _now(),
        }
        record["receipt"] = self._receipt("create", record, True)
        self._upsert(record)
        self._register_receipt(record["receipt"])
        return {"ok": True, "session": record}

    def get(self, session_id: str) -> Dict[str, Any]:
        record = self._find(session_id)
        if not record:
            return {"ok": False, "error": f"unknown agent session: {session_id}"}
        return {"ok": True, "session": record}

    def update(
        self,
        session_id: str,
        *,
        status: str = "",
        evidence: Optional[List[Dict[str, Any]]] = None,
        output: Optional[Dict[str, Any]] = None,
        files: Optional[List[str]] = None,
        tools: Optional[List[str]] = None,
        budget_delta: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        record = self._find(session_id)
        if not record:
            return {"ok": False, "error": f"unknown agent session: {session_id}"}
        record = dict(record)
        if status:
            record["status"] = status
        if files is not None:
            record["files"] = [str(item) for item in files]
        if tools is not None:
            record["tools"] = [str(item) for item in tools]
        if evidence:
            record.setdefault("evidence", []).extend(evidence)
        if output:
            output_record = dict(output)
            output_record.setdefault("timestamp", _now())
            record.setdefault("outputs", []).append(output_record)
        if budget_delta:
            budget = record.get("budget") if isinstance(record.get("budget"), dict) else {}
            for key, value in budget_delta.items():
                try:
                    budget[key] = float(budget.get(key) or 0) + float(value)
                except (TypeError, ValueError):
                    budget[key] = value
            record["budget"] = budget
        record["updated_at"] = _now()
        record["receipt"] = self._receipt("update", record, True)
        self._upsert(record)
        self._register_receipt(record["receipt"])
        return {"ok": True, "session": record}

    def pause(self, session_id: str) -> Dict[str, Any]:
        return self.update(session_id, status="paused")

    def resume(self, session_id: str) -> Dict[str, Any]:
        return self.update(session_id, status="active")

    def cancel(self, session_id: str, reason: str = "") -> Dict[str, Any]:
        result = self.update(session_id, status="cancelled", evidence=[{
            "beast_object_type": "beast_agent_session_cancel_receipt",
            "session_id": session_id,
            "reason": reason,
            "timestamp": _now(),
        }])
        if result.get("ok"):
            result["session"]["cancel_reason"] = reason
            self._upsert(result["session"])
        return result

    def sourceplan_draft(self, session_id: str, output: str = "") -> Dict[str, Any]:
        record = self._find(session_id)
        if not record:
            return {"ok": False, "error": f"unknown agent session: {session_id}"}
        text = output or self._latest_output_text(record)
        plan_id = f"agent-session-{session_id}"
        plan = {
            "beast_object_type": "sourceplan",
            "version": "1.0",
            "plan_id": plan_id,
            "objective": record.get("objective") or "Convert agent output to governed SourcePlan",
            "status": "draft",
            "source": "agent_session_workspace",
            "agent_session_id": session_id,
            "mode": record.get("mode"),
            "provider": record.get("provider"),
            "files": record.get("files") or [],
            "selected_files": record.get("files") or [],
            "agent_output_summary": text[:2000],
            "operations": [],
            "requires_operator_translation": True,
            "governance_note": "Agent output is advisory. Add explicit operations, preview, approve, verify, and apply through SourcePlan.",
        }
        receipt = self._receipt("sourceplan_draft", record, True)
        receipt["plan_id"] = plan_id
        self._register_receipt(receipt)
        return {"ok": True, "plan": plan, "receipt": receipt}

    def _latest_output_text(self, record: Dict[str, Any]) -> str:
        outputs = record.get("outputs") if isinstance(record.get("outputs"), list) else []
        for item in reversed(outputs):
            if isinstance(item, dict):
                return str(item.get("text") or item.get("summary") or item.get("content") or "")
        return ""

    def _load(self) -> Dict[str, Any]:
        try:
            payload = json.loads(self.registry_path.read_text(encoding="utf-8"))
        except Exception:
            payload = {}
        sessions = payload.get("sessions") if isinstance(payload.get("sessions"), list) else []
        return {"beast_object_type": "beast_agent_session_registry", "version": "1.0", "sessions": sessions}

    def _save(self, payload: Dict[str, Any]) -> None:
        self.store_dir.mkdir(parents=True, exist_ok=True)
        tmp = self.registry_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        tmp.replace(self.registry_path)

    def _upsert(self, record: Dict[str, Any]) -> None:
        registry = self._load()
        sessions = [item for item in registry.get("sessions", []) if item.get("session_id") != record.get("session_id")]
        sessions.append(record)
        sessions.sort(key=lambda item: float(item.get("updated_at") or 0), reverse=True)
        registry["sessions"] = sessions
        self._save(registry)

    def _find(self, session_id: str) -> Optional[Dict[str, Any]]:
        for record in self._load().get("sessions", []):
            if str(record.get("session_id") or "") == str(session_id or ""):
                return record
        return None

    def _receipt(self, action: str, record: Dict[str, Any], ok: bool) -> Dict[str, Any]:
        return {
            "beast_object_type": "beast_agent_session_receipt",
            "version": "1.0",
            "action": action,
            "ok": bool(ok),
            "session_id": record.get("session_id"),
            "agent_id": record.get("agent_id"),
            "mode": record.get("mode"),
            "status": record.get("status"),
            "timestamp": _now(),
        }

    def _register_receipt(self, receipt: Dict[str, Any]) -> None:
        if not receipt:
            return
        try:
            from app.kernel.evidence.evidence_bus import EvidenceBus

            EvidenceBus(self.workspace_root).register(
                artifact_type="agent_session_receipt",
                artifact_path=self.registry_path,
                artifact_hash=hashlib.sha1(json.dumps(receipt, sort_keys=True, default=str).encode("utf-8")).hexdigest(),
                source="agent_session_store",
                task_id=str(receipt.get("session_id") or ""),
                status="ok" if receipt.get("ok") else "failed",
                summary=f"{receipt.get('action') or 'session'} {receipt.get('status') or ''}".strip(),
                relationships={"agent": {"agent_id": receipt.get("agent_id") or "", "mode": receipt.get("mode") or ""}},
                metadata={"action": receipt.get("action") or ""},
            )
        except Exception:
            pass

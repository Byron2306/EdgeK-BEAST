"""Unified tool and approval cards for the Phase 5 operations console."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from app.kernel.agents.run_store import AgentRunStore
from app.kernel.approvals.cards import DurableApprovalCardStore
from app.kernel.approvals.capability_runtime import CapabilityConsumptionStore
from app.kernel.approvals.revocation import RevocationPolicyStore
from app.kernel.operations_console.event_projection import DurableConsoleEventProjection

VERSION = "5.8"
OBJECT_TYPE = "beast_tool_approval_cards_console"
TOOL_STATES = {"PLANNED", "WAITING_FOR_APPROVAL", "APPROVED", "CAPABILITY_ISSUED", "EXECUTING", "SUCCEEDED", "FAILED", "DENIED", "EXPIRED", "REVOKED", "CONSUMED"}


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str).encode()


def _digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical(value)).hexdigest()


class ToolApprovalCardsConsole:
    """Projects durable tool activity and approval authority into reviewable cards."""

    def __init__(self, workspace_root: str | Path):
        self.workspace_root = Path(workspace_root).expanduser().resolve()
        self.runs = AgentRunStore(self.workspace_root)
        self.events = DurableConsoleEventProjection(self.workspace_root)
        self.cards = DurableApprovalCardStore(self.workspace_root)
        self.consumption = CapabilityConsumptionStore(self.workspace_root)
        self.revocations = RevocationPolicyStore(self.workspace_root)

    def build(self, run_id: str, *, status: str = "", query: str = "", limit: int = 200) -> dict[str, Any]:
        run = self.runs.get_run(run_id)
        if not run:
            raise KeyError(f"unknown agent run: {run_id}")
        wanted = status.strip().upper()
        if wanted and wanted not in TOOL_STATES:
            raise ValueError(f"unsupported tool card status: {wanted}")
        needle = query.strip().lower()
        page = self.events.page(run_id, limit=max(1, min(int(limit), 500)), view="expanded")
        tool_events = [event for event in page["events"] if event.get("category") == "tool"]
        approval_cards = self.cards.list(run_id=run_id, limit=500)
        cards = self._merge(tool_events, approval_cards)
        visible = []
        for card in cards:
            if wanted and card["status"] != wanted:
                continue
            if needle and needle not in json.dumps(card, sort_keys=True, default=str).lower():
                continue
            visible.append(card)
        result = {
            "version": VERSION,
            "beast_object_type": OBJECT_TYPE,
            "run_id": run_id,
            "run_state": str(run.get("state") or "unknown").lower(),
            "summary": {
                "total_cards": len(cards),
                "visible_cards": len(visible),
                "pending_approvals": sum(1 for c in cards if c["status"] == "WAITING_FOR_APPROVAL"),
                "active_tools": sum(1 for c in cards if c["status"] == "EXECUTING"),
                "failed_tools": sum(1 for c in cards if c["status"] == "FAILED"),
                "consumed_capabilities": sum(1 for c in cards if c["capability"]["consumed"]),
            },
            "filters": {"status": wanted, "query": query},
            "cards": visible,
            "projection_head_digest": page["projection_head_digest"],
            "authority": "tool_approval_cards_console_read_only",
            "grants_execution_authority": False,
            "grants_workspace_mutation": False,
            "grants_promotion_authority": False,
        }
        result["console_digest"] = _digest(result)
        return result

    def verify(self, console: dict[str, Any]) -> bool:
        if console.get("beast_object_type") != OBJECT_TYPE:
            return False
        claimed = str(console.get("console_digest") or "")
        semantic = dict(console); semantic.pop("console_digest", None)
        return claimed == _digest(semantic)

    def _merge(self, events: list[dict[str, Any]], approval_cards: list[dict[str, Any]]) -> list[dict[str, Any]]:
        merged: dict[str, dict[str, Any]] = {}
        for event in events:
            detail = event.get("detail") if isinstance(event.get("detail"), dict) else {}
            compact = event.get("compact") if isinstance(event.get("compact"), dict) else {}
            step_id = str(event.get("step_id") or detail.get("step_id") or "")
            tool_id = str(compact.get("tool_id") or detail.get("tool_id") or "unknown")
            key = f"{step_id}:{tool_id}"
            card = merged.setdefault(key, self._empty_card(step_id, tool_id))
            card["timeline_event_ids"].append(event["projection_event_id"])
            card["latest_event_digest"] = event["projection_digest"]
            card["summary"] = str(event.get("summary") or card["summary"])
            card["tool_version"] = str(detail.get("tool_version") or card["tool_version"])
            card["safe_arguments"] = detail.get("argument_view") or detail.get("arguments") or card["safe_arguments"]
            card["reason"] = str(detail.get("reason") or card["reason"])
            card["target"] = str(detail.get("execution_target") or detail.get("target") or card["target"])
            card["affected_files"] = list(detail.get("affected_files") or card["affected_files"])
            card["command"] = str(detail.get("command") or card["command"])
            card["url"] = str(detail.get("url") or card["url"])
            card["expected_side_effects"] = list(detail.get("expected_side_effects") or card["expected_side_effects"])
            card["risk_class"] = str(detail.get("risk_class") or card["risk_class"])
            card["permission_mode"] = str(detail.get("permission_mode") or card["permission_mode"])
            card["status"] = self._tool_status(event)
        for approval in approval_cards:
            envelope = approval.get("envelope") or {}
            request = envelope.get("approval_request") or {}
            classification = envelope.get("classification") or {}
            step_id = str(approval.get("step_id") or request.get("step_id") or "")
            tool_id = str(request.get("tool_id") or "unknown")
            key = f"{step_id}:{tool_id}"
            card = merged.setdefault(key, self._empty_card(step_id, tool_id))
            card["approval"] = {
                "approval_id": approval.get("approval_id", ""),
                "card_id": approval.get("card_id", ""),
                "state": approval.get("state", ""),
                "scope": (approval.get("decision") or {}).get("scope", ""),
                "decision": (approval.get("decision") or {}).get("decision", ""),
                "expires_at": approval.get("expires_at", ""),
                "request_digest": approval.get("request_digest", ""),
                "card_digest": approval.get("card_digest", ""),
            }
            card["tool_version"] = str(request.get("tool_version") or card["tool_version"])
            card["safe_arguments"] = envelope.get("argument_view") or card["safe_arguments"]
            card["reason"] = str(envelope.get("reason") or request.get("reason") or card["reason"])
            card["target"] = str(request.get("execution_target") or card["target"])
            card["affected_files"] = list(envelope.get("affected_files") or card["affected_files"])
            card["command"] = str((envelope.get("commands") or [card["command"]])[0] if envelope.get("commands") else card["command"])
            card["url"] = str((envelope.get("urls") or [card["url"]])[0] if envelope.get("urls") else card["url"])
            card["expected_side_effects"] = list(envelope.get("expected_side_effects") or card["expected_side_effects"])
            card["risk_class"] = str(classification.get("risk_class") or card["risk_class"])
            card["permission_mode"] = str(request.get("permission_mode") or card["permission_mode"])
            card["status"] = self._approval_status(str(approval.get("state") or ""), card["status"])
            revoked = self.revocations.check({
                "approval_id": str(approval.get("approval_id") or ""),
                "card_id": str(approval.get("card_id") or ""),
                "run_id": str(approval.get("run_id") or ""),
                "tool_id": tool_id,
                "policy_generation": str(request.get("policy_generation") or ""),
            })
            card["revoked"] = not bool(revoked.get("active", True))
            if card["revoked"]:
                card["status"] = "REVOKED"
        for card in merged.values():
            card["valid_actions"] = self._valid_actions(card)
            card["card_digest"] = _digest({k: v for k, v in card.items() if k != "card_digest"})
        return sorted(merged.values(), key=lambda item: (item["step_id"], item["tool_id"]))

    @staticmethod
    def _empty_card(step_id: str, tool_id: str) -> dict[str, Any]:
        return {"step_id": step_id, "tool_id": tool_id, "tool_version": "", "summary": "", "safe_arguments": {}, "reason": "", "target": "", "affected_files": [], "command": "", "url": "", "expected_side_effects": [], "risk_class": "", "permission_mode": "", "status": "PLANNED", "approval": {}, "capability": {"issued": False, "consumed": False, "revoked": False}, "revoked": False, "timeline_event_ids": [], "latest_event_digest": "", "valid_actions": [], "authority": "tool_approval_card_display_only"}

    @staticmethod
    def _tool_status(event: dict[str, Any]) -> str:
        text = " ".join([str(event.get("event_type") or ""), str(event.get("summary") or ""), json.dumps(event.get("detail") or {})]).lower()
        if "fail" in text or "error" in text: return "FAILED"
        if "denied" in text: return "DENIED"
        if "execut" in text or "started" in text: return "EXECUTING"
        if "succeed" in text or "completed" in text or "passed" in text: return "SUCCEEDED"
        return "PLANNED"

    @staticmethod
    def _approval_status(state: str, fallback: str) -> str:
        value = state.upper()
        return {"PENDING": "WAITING_FOR_APPROVAL", "APPROVED": "APPROVED", "EDITED_AND_APPROVED": "APPROVED", "REJECTED": "DENIED", "PERMANENTLY_DENIED": "DENIED", "EXPIRED": "EXPIRED"}.get(value, fallback)

    @staticmethod
    def _valid_actions(card: dict[str, Any]) -> list[str]:
        status = card["status"]
        if status == "WAITING_FOR_APPROVAL": return ["APPROVE_ONCE", "EDIT_AND_APPROVE_ONCE", "REJECT", "REQUEST_REPLAN"]
        if status == "APPROVED": return ["ISSUE_REQUEST_BOUND_CAPABILITY", "REVOKE"]
        if status == "CAPABILITY_ISSUED": return ["CONSUME_AND_RESUME", "REVOKE"]
        if status == "FAILED": return ["RETRY_WITHIN_SCOPE", "REQUEST_REPLAN", "CANCEL_RUN"]
        if status in {"PLANNED", "DENIED", "EXPIRED"}: return ["REQUEST_APPROVAL", "REPLAN", "CANCEL_RUN"]
        if status == "EXECUTING": return ["PAUSE_RUN", "CANCEL_RUN"]
        return []

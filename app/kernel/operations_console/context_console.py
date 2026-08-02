from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any, Mapping

from app.kernel.approvals.digests import semantic_payload, sha256_digest
from app.kernel.operations_console.context_manifest import ContextManifestStore

VERSION = "5.6"
CONSOLE_TYPE = "beast_context_manifest_console_projection"

_STATUS_ACTIONS: dict[str, tuple[str, ...]] = {
    "DISCOVERED": ("ACCEPTED", "REJECTED", "EXCLUDED"),
    "SUGGESTED_UNSELECTED": ("ACCEPTED", "REJECTED", "EXCLUDED"),
    "ACCEPTED": ("ADMITTED", "REDACTED", "EXCLUDED"),
    "REDACTED": ("ADMITTED", "EXCLUDED"),
    "ADMITTED": ("EXCLUDED",),
    "REJECTED": (),
    "EXCLUDED": (),
    "STALE": (),
}


class ContextManifestConsole:
    """Read-only operator projection over the durable context manifest.

    Decisions remain delegated to ContextManifestStore so this projection can
    never create model-admission authority by presentation alone.
    """

    def __init__(self, workspace_root: str | Path):
        self.workspace_root = Path(workspace_root).resolve()
        self.store = ContextManifestStore(self.workspace_root)

    def build(
        self,
        run_id: str,
        *,
        status: str = "",
        privacy: str = "",
        visibility: str = "",
        query: str = "",
    ) -> dict[str, Any]:
        manifest = self.store.manifest(run_id)
        filters = {
            "status": str(status or "").upper(),
            "privacy": str(privacy or "").upper(),
            "visibility": str(visibility or "").upper(),
            "query": str(query or "").strip().lower(),
        }
        cards = [self._card(item) for item in manifest.get("items", [])]
        filtered = [card for card in cards if self._matches(card, filters)]
        status_counts = Counter(card["status"] for card in cards)
        privacy_counts = Counter(card["privacy_level"] for card in cards)
        visibility_counts = Counter(card["provider_visibility"] for card in cards)
        selected_tokens = sum(
            int(card.get("token_estimate") or 0)
            for card in cards
            if card["status"] in {"ACCEPTED", "ADMITTED", "REDACTED"}
        )
        total_tokens = sum(int(card.get("token_estimate") or 0) for card in cards)
        projection: dict[str, Any] = {
            "version": VERSION,
            "beast_object_type": CONSOLE_TYPE,
            "run_id": run_id,
            "conversation_first": True,
            "summary": {
                "item_count": len(cards),
                "visible_count": len(filtered),
                "selected_count": sum(card["selected"] for card in cards),
                "admitted_count": status_counts.get("ADMITTED", 0),
                "suggested_unselected_count": status_counts.get("SUGGESTED_UNSELECTED", 0),
                "stale_count": status_counts.get("STALE", 0),
                "sensitive_count": sum(card["privacy_level"] in {"SENSITIVE", "RESTRICTED"} for card in cards),
                "selected_token_estimate": selected_tokens,
                "total_token_estimate": total_tokens,
            },
            "facets": {
                "status": dict(sorted(status_counts.items())),
                "privacy": dict(sorted(privacy_counts.items())),
                "provider_visibility": dict(sorted(visibility_counts.items())),
            },
            "filters": filters,
            "cards": filtered,
            "manifest_digest": manifest.get("manifest_digest", ""),
            "operator_rules": {
                "suggestions_default_unselected": True,
                "acceptance_does_not_admit": True,
                "sensitive_requires_redaction": True,
                "provider_visibility_enforced": True,
                "source_content_not_embedded": True,
            },
            "authority": "context_manifest_console_read_only",
            "grants_model_admission": False,
            "grants_execution_authority": False,
            "grants_workspace_mutation": False,
        }
        projection["projection_digest"] = sha256_digest(projection)
        return projection

    def verify(self, projection: Mapping[str, Any]) -> bool:
        value = dict(projection)
        claimed = str(value.get("projection_digest") or "")
        return bool(claimed) and sha256_digest(
            semantic_payload(value, exclude={"projection_digest"})
        ) == claimed

    @staticmethod
    def _matches(card: Mapping[str, Any], filters: Mapping[str, str]) -> bool:
        if filters["status"] and card.get("status") != filters["status"]:
            return False
        if filters["privacy"] and card.get("privacy_level") != filters["privacy"]:
            return False
        if filters["visibility"] and card.get("provider_visibility") != filters["visibility"]:
            return False
        needle = filters["query"]
        if needle:
            haystack = " ".join(
                [
                    str(card.get("path") or ""),
                    str(card.get("source") or ""),
                    " ".join(card.get("retrieval_reasons") or []),
                ]
            ).lower()
            if needle not in haystack:
                return False
        return True

    @staticmethod
    def _card(item: Mapping[str, Any]) -> dict[str, Any]:
        status = str(item.get("status") or "DISCOVERED").upper()
        privacy = str(item.get("privacy_level") or "INTERNAL").upper()
        visibility = str(item.get("provider_visibility") or "LOCAL_ONLY").upper()
        line_range = item.get("line_range") or {}
        source_ref = str(item.get("path") or item.get("source") or "unbound context")
        start = int(line_range.get("start") or 0)
        end = int(line_range.get("end") or 0)
        if start or end:
            source_ref = f"{source_ref}:{start or 1}-{end or start or 1}"
        warnings: list[str] = []
        if status == "SUGGESTED_UNSELECTED":
            warnings.append("Suggestion is not selected and will not enter the context packet.")
        if status == "STALE":
            warnings.append("Content hash drift detected. Re-selection is required.")
        if privacy in {"SENSITIVE", "RESTRICTED"} and not item.get("redaction_digest"):
            warnings.append("Sensitive context requires a redaction receipt before provider admission.")
        if visibility == "LOCAL_ONLY":
            warnings.append("This item may be admitted only to a local provider.")
        return {
            "item_id": item.get("item_id"),
            "source": item.get("source"),
            "path": item.get("path"),
            "source_reference": source_ref,
            "line_range": line_range,
            "content_hash": item.get("content_hash"),
            "retrieval_reasons": list(item.get("retrieval_reasons") or []),
            "selection_origin": item.get("selection_origin"),
            "token_estimate": int(item.get("token_estimate") or 0),
            "privacy_level": privacy,
            "provider_visibility": visibility,
            "status": status,
            "selected": status in {"ACCEPTED", "ADMITTED", "REDACTED"},
            "admitted": status == "ADMITTED",
            "admitted_provider": item.get("admitted_provider") or "",
            "redacted": status == "REDACTED" or bool(item.get("redaction_digest")),
            "redaction_digest": item.get("redaction_digest") or "",
            "warnings": warnings,
            "valid_actions": list(_STATUS_ACTIONS.get(status, ())),
            "item_digest": item.get("item_digest"),
            "authority": "context_card_presentation_only",
            "grants_model_admission": False,
        }

"""Normalize BEAST subsystem receipts into crystal promotion source evidence."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List


SOURCE_WEIGHTS = {
    "tool_interceptor": 0.12,
    "context_packet": 0.12,
    "tool_laziness": 0.10,
    "provider_economist": 0.12,
    "swarm_openclaw": 0.14,
    "capability_registry": 0.10,
    "meta_tool_commons": 0.14,
    "compute_forge": 0.16,
}


@dataclass(frozen=True)
class CrystalPromotionEvidenceSource:
    source: str
    present: bool
    verified: bool
    useful: bool = True
    weight: float = 0.0
    summary: str = ""
    receipt_hash: str = ""
    signals: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "beast_object_type": "crystal_promotion_evidence_source",
            "version": "1.0",
            "source": self.source,
            "present": self.present,
            "verified": self.verified,
            "useful": self.useful,
            "weight": self.weight,
            "summary": self.summary,
            "receipt_hash": self.receipt_hash,
            "signals": self.signals,
        }


class CrystalPromotionEvidenceSources:
    """Score whether the wider BEAST system actually contributed to a crystal."""

    def __init__(self, weights: Dict[str, float] | None = None) -> None:
        self.weights = dict(SOURCE_WEIGHTS)
        self.weights.update(weights or {})

    def evaluate(self, receipts: Dict[str, Any]) -> Dict[str, Any]:
        sources = [self._source(name, receipts.get(name)) for name in self.weights]
        present = [item for item in sources if item.present]
        verified = [item for item in present if item.verified and item.useful]
        score = round(sum(item.weight for item in verified), 6)
        receipt = {
            "beast_object_type": "crystal_promotion_evidence_sources",
            "version": "1.0",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "source_count": len(sources),
            "present_count": len(present),
            "verified_count": len(verified),
            "score": min(1.0, score),
            "sources": [item.to_dict() for item in sources],
            "missing_sources": [item.source for item in sources if not item.present],
            "unverified_sources": [item.source for item in present if not item.verified or not item.useful],
        }
        receipt["receipt_hash"] = self._hash(receipt)
        return receipt

    def from_packet_and_receipts(self, packet: Dict[str, Any], receipts: Dict[str, Any]) -> Dict[str, Any]:
        combined = dict(receipts)
        if packet.get("tools"):
            combined.setdefault("tool_interceptor", {"verified": True, "summary": "tools recorded in packet"})
        if packet.get("route_optimizer"):
            combined.setdefault("provider_economist", packet.get("route_optimizer"))
        if packet.get("forge"):
            combined.setdefault("compute_forge", packet.get("forge"))
        if packet.get("skills"):
            combined.setdefault("capability_registry", {"verified": True, "summary": "skills recorded in packet"})
        return self.evaluate(combined)

    def _source(self, name: str, receipt: Any) -> CrystalPromotionEvidenceSource:
        present = isinstance(receipt, dict) and bool(receipt)
        if not present:
            return CrystalPromotionEvidenceSource(
                source=name,
                present=False,
                verified=False,
                useful=False,
                weight=float(self.weights.get(name, 0.0)),
                summary="missing",
            )
        verified = self._truthy_any(receipt, ("verified", "tests_passed", "approved", "success", "ready", "adopted", "promotion_candidate_staged"))
        if name == "compute_forge" and isinstance(receipt.get("receipts"), list) and receipt.get("receipts"):
            verified = True
        if name == "provider_economist" and (receipt.get("runtime_engine") or receipt.get("engine_id")):
            verified = True
        if name in {"tool_interceptor", "capability_registry"} and receipt.get("summary"):
            verified = True
        if "blocked" in receipt:
            verified = verified and not bool(receipt.get("blocked"))
        useful = not bool(receipt.get("unsafe") or receipt.get("secret_detected") or receipt.get("failed"))
        return CrystalPromotionEvidenceSource(
            source=name,
            present=True,
            verified=bool(verified),
            useful=bool(useful),
            weight=float(self.weights.get(name, 0.0)),
            summary=str(receipt.get("summary") or receipt.get("reason") or receipt.get("status") or "present")[:240],
            receipt_hash=self._hash(receipt),
            signals={key: receipt.get(key) for key in sorted(receipt) if key not in {"raw", "prompt", "source", "response"}},
        )

    @staticmethod
    def _truthy_any(receipt: Dict[str, Any], keys: Iterable[str]) -> bool:
        for key in keys:
            if receipt.get(key) is True:
                return True
            if isinstance(receipt.get(key), str) and receipt.get(key) in {"ready", "succeeded", "accepted", "passed"}:
                return True
        return False

    @staticmethod
    def _hash(payload: Any) -> str:
        return "sha256:" + hashlib.sha256(
            json.dumps(payload, sort_keys=True, default=str, separators=(",", ":")).encode("utf-8")
        ).hexdigest()

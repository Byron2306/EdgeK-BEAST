"""Semantic acceptance checks for crystal reuse integration export bundles."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional


Validator = Callable[[Dict[str, Any]], Dict[str, Any]]


@dataclass(frozen=True)
class IntegrationAcceptanceResult:
    integration: str
    configured: bool
    exportable: bool
    semantically_accepted: bool
    live_service_accepted: bool
    checks: Dict[str, bool] = field(default_factory=dict)
    reason: str = ""
    claim_boundary: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "beast_object_type": "crystal_reuse_integration_acceptance_result",
            "version": "1.0",
            "integration": self.integration,
            "configured": self.configured,
            "exportable": self.exportable,
            "semantically_accepted": self.semantically_accepted,
            "live_service_accepted": self.live_service_accepted,
            "checks": self.checks,
            "reason": self.reason,
            "claim_boundary": self.claim_boundary,
        }


class CrystalIntegrationAcceptanceProbe:
    """Validate adapter payload semantics without pretending services are live."""

    def __init__(self, *, live_receipts: Optional[Dict[str, Dict[str, Any]]] = None) -> None:
        self.live_receipts = live_receipts or {}
        self.validators: Dict[str, Validator] = {
            "lmcache": self._lmcache,
            "gptcache": self._gptcache,
            "litellm": self._litellm,
            "openllmetry": self._openllmetry,
            "langfuse": self._langfuse,
            "tensorzero": self._tensorzero,
            "promptfoo": self._promptfoo,
            "vllm": self._vllm,
            "sglang": self._sglang,
        }

    def run(self, bundle: Dict[str, Any]) -> Dict[str, Any]:
        results = []
        for name, validator in self.validators.items():
            payload = self._payload_for(name, bundle)
            semantic = validator(payload)
            live = self._live_status(name)
            result = IntegrationAcceptanceResult(
                integration=name,
                configured=bool(payload),
                exportable=bool(payload),
                semantically_accepted=bool(semantic.get("accepted")),
                live_service_accepted=bool(live.get("accepted")),
                checks=semantic.get("checks") or {},
                reason=str(semantic.get("reason") or live.get("reason") or ""),
                claim_boundary=(
                    "Semantic export contract accepted locally. Live service acceptance requires an explicit "
                    f"{name} receipt."
                ),
            )
            results.append(result.to_dict())
        accepted = sum(1 for item in results if item["semantically_accepted"])
        live = sum(1 for item in results if item["live_service_accepted"])
        receipt = {
            "beast_object_type": "crystal_reuse_integration_acceptance_probe",
            "version": "1.0",
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "integration_count": len(results),
            "semantically_accepted_count": accepted,
            "live_service_accepted_count": live,
            "results": results,
            "claim_boundary": "Local semantic contract validation only unless live service receipts are supplied.",
        }
        receipt["receipt_hash"] = "sha256:" + hashlib.sha256(
            json.dumps(receipt, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()
        return receipt

    def _payload_for(self, name: str, bundle: Dict[str, Any]) -> Dict[str, Any]:
        if name == "vllm":
            return self._engine_payload(bundle, "vllm")
        if name == "sglang":
            return self._engine_payload(bundle, "sglang")
        payload = bundle.get(name)
        return payload if isinstance(payload, dict) else {}

    def _engine_payload(self, bundle: Dict[str, Any], engine: str) -> Dict[str, Any]:
        prefix = bundle.get("local_prefix_kv_store")
        prefix = prefix if isinstance(prefix, dict) else {}
        block = prefix.get("kv_cache_block")
        block = block if isinstance(block, dict) else {}
        return {
            "beast_object_type": f"{engine}_prefix_cache_capability_card",
            "version": "1.0",
            "engine": engine,
            "decision_id": bundle.get("decision_id"),
            "prefix_manifest": prefix,
            "kv_cache_block": block,
            "restore_identity_guard": bool(prefix.get("cache_key")),
        }

    def _live_status(self, name: str) -> Dict[str, Any]:
        receipt = self.live_receipts.get(name) if isinstance(self.live_receipts, dict) else None
        if not isinstance(receipt, dict):
            return {"accepted": False, "reason": "live_service_receipt_not_supplied"}
        return {
            "accepted": bool(receipt.get("accepted") or receipt.get("ready") or receipt.get("status") == "accepted"),
            "reason": str(receipt.get("reason") or "live_receipt_supplied"),
        }

    @staticmethod
    def _lmcache(payload: Dict[str, Any]) -> Dict[str, Any]:
        checks = {
            "manifest_type": payload.get("beast_object_type") == "lmcache_reuse_manifest",
            "cache_key_present": bool(payload.get("cache_key")),
            "reuse_flag_boolean": isinstance(payload.get("reuse_allowed"), bool),
        }
        return {"accepted": all(checks.values()), "checks": checks, "reason": "lmcache_manifest_semantics"}

    @staticmethod
    def _gptcache(payload: Dict[str, Any]) -> Dict[str, Any]:
        checks = {
            "record_type": payload.get("beast_object_type") == "gptcache_semantic_record",
            "prompt_hash_present": str(payload.get("prompt_hash") or "").startswith("sha256:"),
            "confidence_valid": 0.0 <= float(payload.get("confidence") or 0.0) <= 1.0,
            "cache_hit_boolean": isinstance(payload.get("cache_hit"), bool),
        }
        return {"accepted": all(checks.values()), "checks": checks, "reason": "gptcache_semantic_record_semantics"}

    @staticmethod
    def _litellm(payload: Dict[str, Any]) -> Dict[str, Any]:
        metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
        checks = {
            "metadata_type": payload.get("beast_object_type") == "litellm_crystal_metadata",
            "decision_id_present": bool(metadata.get("beast_crystal_decision_id")),
            "governance_layer": metadata.get("beast_governance_layer") == "BEAST",
            "cloud_used_boolean": isinstance(metadata.get("cloud_used"), bool),
        }
        return {"accepted": all(checks.values()), "checks": checks, "reason": "litellm_metadata_semantics"}

    @staticmethod
    def _openllmetry(payload: Dict[str, Any]) -> Dict[str, Any]:
        attrs = payload.get("attributes") if isinstance(payload.get("attributes"), dict) else {}
        checks = {
            "span_name": bool(payload.get("name")),
            "span_kind": payload.get("kind") == "internal",
            "action_attribute": bool(attrs.get("beast.crystal.action")),
            "confidence_attribute": attrs.get("beast.crystal.confidence") is not None,
        }
        return {"accepted": all(checks.values()), "checks": checks, "reason": "openllmetry_span_semantics"}

    @staticmethod
    def _langfuse(payload: Dict[str, Any]) -> Dict[str, Any]:
        metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
        scores = payload.get("scores") if isinstance(payload.get("scores"), list) else []
        checks = {
            "observation_type": payload.get("type") == "GENERATION",
            "decision_id_present": bool(metadata.get("decision_id")),
            "local_only": metadata.get("local_only") is True,
            "score_present": bool(scores),
        }
        return {"accepted": all(checks.values()), "checks": checks, "reason": "langfuse_observation_semantics"}

    @staticmethod
    def _tensorzero(payload: Dict[str, Any]) -> Dict[str, Any]:
        checks = {
            "candidate_type": payload.get("beast_object_type") == "tensorzero_feedback_candidate",
            "episode_id_present": bool(payload.get("episode_id")),
            "metric_name_present": bool(payload.get("metric_name")),
            "value_valid": 0.0 <= float(payload.get("value") or 0.0) <= 1.0,
        }
        return {"accepted": all(checks.values()), "checks": checks, "reason": "tensorzero_feedback_semantics"}

    @staticmethod
    def _promptfoo(payload: Dict[str, Any]) -> Dict[str, Any]:
        metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
        checks = {
            "assertion_type": payload.get("type") == "local_eval_gate",
            "value_present": bool(payload.get("value")),
            "assertion_metadata": metadata.get("beast_object_type") == "promptfoo_crystal_reuse_assertion",
            "decision_id_present": bool(metadata.get("decision_id")),
        }
        return {"accepted": all(checks.values()), "checks": checks, "reason": "promptfoo_assertion_semantics"}

    @staticmethod
    def _vllm(payload: Dict[str, Any]) -> Dict[str, Any]:
        return CrystalIntegrationAcceptanceProbe._engine_card(payload, "vllm")

    @staticmethod
    def _sglang(payload: Dict[str, Any]) -> Dict[str, Any]:
        return CrystalIntegrationAcceptanceProbe._engine_card(payload, "sglang")

    @staticmethod
    def _engine_card(payload: Dict[str, Any], engine: str) -> Dict[str, Any]:
        prefix = payload.get("prefix_manifest") if isinstance(payload.get("prefix_manifest"), dict) else {}
        checks = {
            "card_type": payload.get("beast_object_type") == f"{engine}_prefix_cache_capability_card",
            "engine_match": payload.get("engine") == engine,
            "decision_id_present": bool(payload.get("decision_id")),
            "restore_identity_guard": payload.get("restore_identity_guard") is True,
            "prefix_manifest_present": bool(prefix.get("beast_object_type")),
        }
        return {"accepted": all(checks.values()), "checks": checks, "reason": f"{engine}_prefix_cache_card_semantics"}

"""Compatibility shim for the retired external crystal integration registry.

The old registry advertised optional public services and env-var probes. BEAST
now exposes local, CPU-first capabilities through LocalCapabilityRegistry. This
module keeps historical imports working while returning only local capability
contracts.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Dict, List

from app.kernel.compute.local_capabilities import LocalCapabilityProfile, LocalCapabilityRegistry


INTEGRATION_VERSION = "1.0"
CrystalIntegrationProfile = LocalCapabilityProfile


class CrystalIntegrationRegistry(LocalCapabilityRegistry):
    """Backward-compatible name for the BEAST local capability registry."""

    def profiles(self) -> List[LocalCapabilityProfile]:
        return super().profiles()

    def health(self, *, probe: bool = False, timeout_seconds: float = 0.45) -> Dict[str, Any]:
        return super().health(probe=probe, timeout_seconds=timeout_seconds)

    def export_bundle(self, decision: Dict[str, Any]) -> Dict[str, Any]:
        payload = json.dumps(decision, sort_keys=True, default=str)
        request = ((decision.get("payload") or {}).get("request") or {})
        reuse = ((decision.get("payload") or {}).get("reuse") or {})
        reuse_payload = reuse.get("payload") if isinstance(reuse, dict) else {}
        return {
            "beast_object_type": "beast_local_capability_export_bundle",
            "version": INTEGRATION_VERSION,
            "decision_id": decision.get("decision_id"),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "local_semantic_cache": {
                "beast_object_type": "local_semantic_cache_record",
                "prompt_hash": request.get("prompt_hash"),
                "cache_hit": decision.get("action") in {"reuse_answer", "reuse_semantic_credit"},
                "confidence": decision.get("confidence"),
                "answer": (reuse_payload or {}).get("answer") or (reuse_payload or {}).get("response"),
            },
            "local_prefix_kv_store": {
                "beast_object_type": "local_prefix_kv_manifest",
                "reuse_allowed": decision.get("action") == "reuse_kv_prefill",
                "payload_sha256": "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest(),
            },
            "local_execution_gateway": {
                "beast_object_type": "local_execution_route_metadata",
                "route": "local_cpu",
                "cloud_used": False,
            },
            "local_trace_ledger": self.openllmetry_span(decision),
            "local_route_optimizer": self.tensorzero_feedback(decision),
            "local_eval_gate": self.promptfoo_assertion(decision),
        }

    @staticmethod
    def openllmetry_span(decision: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "name": "beast.local_crystal_reuse",
            "kind": "internal",
            "attributes": {
                "beast.decision_id": decision.get("decision_id"),
                "beast.crystal.action": decision.get("action"),
                "beast.crystal.source": decision.get("source"),
                "beast.local_only": True,
            },
        }

    @staticmethod
    def langfuse_observation(decision: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "type": "GENERATION",
            "name": "BEAST local crystal reuse",
            "metadata": {"decision_id": decision.get("decision_id"), "local_only": True},
            "scores": [{"name": "crystal_reuse_confidence", "value": float(decision.get("confidence") or 0.0)}],
        }

    @staticmethod
    def tensorzero_feedback(decision: Dict[str, Any]) -> Dict[str, Any]:
        payload = json.dumps(decision, sort_keys=True, default=str)
        return {
            "beast_object_type": "local_route_feedback_candidate",
            "episode_id": decision.get("decision_id"),
            "metric_name": "beast_local_crystal_reuse",
            "value": float(decision.get("confidence") or 0.0),
            "payload_sha256": "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest(),
        }

    @staticmethod
    def promptfoo_assertion(decision: Dict[str, Any], *, min_confidence: float = 0.80) -> Dict[str, Any]:
        return {
            "type": "local_eval_gate",
            "value": f"confidence >= {float(min_confidence):.3f}",
            "metadata": {
                "beast_object_type": "local_eval_gate_assertion",
                "decision_id": decision.get("decision_id"),
            },
        }

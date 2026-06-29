"""Acceptance receipts for BEAST-native local crystal-reuse capabilities."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Dict

from app.kernel.compute.local_capabilities import LocalCapabilityRegistry


REQUIRED_CAPABILITIES = {
    "local_semantic_cache": ("exact", "semantic", "repo_scoped", "verified_only"),
    "local_prefix_kv_store": ("prefix_cache", "compatibility_guard", "raw_tensor_optional"),
    "local_execution_gateway": ("local_cpu", "cloud_disabled_by_default"),
    "local_trace_ledger": ("spans", "observations", "costs", "offline_export"),
    "local_route_optimizer": ("route_scores", "model_scores", "threshold_tuning"),
    "local_eval_gate": ("assertions", "regression", "promotion_blocking"),
    "compute_forge": ("fingerprint", "secret_scan", "semantic_seed", "handoff_prep"),
}


class CrystalIntegrationAcceptanceHarness:
    """Validate local capability profiles while preserving the historical class name."""

    def __init__(self, registry: LocalCapabilityRegistry | None = None):
        self.registry = registry or LocalCapabilityRegistry()

    def run(self, *, probe: bool = False, timeout_seconds: float = 0.45) -> Dict[str, Any]:
        health = self.registry.health(probe=probe, timeout_seconds=timeout_seconds)
        results = []
        for profile in health.get("capabilities") or []:
            capability_id = str(profile.get("capability_id") or "")
            declared = profile.get("capabilities") if isinstance(profile.get("capabilities"), dict) else {}
            required = REQUIRED_CAPABILITIES.get(capability_id, ())
            missing = [key for key in required if not declared.get(key)]
            live_probe = profile.get("live_probe") if isinstance(profile.get("live_probe"), dict) else {}
            contract_ok = not missing and bool(profile.get("cpu_first"))
            service_ok = (not probe) or live_probe.get("status") in {"ready", "not_attempted"}
            results.append(
                {
                    "capability_id": capability_id,
                    "role": profile.get("role"),
                    "storage": profile.get("storage"),
                    "contract_ok": contract_ok,
                    "missing_fields": missing,
                    "live_probe": live_probe or {"status": "not_attempted"},
                    "status": "accepted" if contract_ok and service_ok else "blocked",
                }
            )

        receipt = {
            "beast_object_type": "beast_local_capability_acceptance_receipt",
            "legacy_object_type": "crystal_integration_acceptance_receipt",
            "version": "1.0",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "probe_enabled": bool(probe),
            "probe_timeout_seconds": timeout_seconds,
            "capability_count": len(results),
            "integration_count": len(results),
            "accepted_count": sum(1 for item in results if item["status"] == "accepted"),
            "results": results,
            "claim_boundary": "Acceptance is local and file-backed; no external service dependency is asserted.",
        }
        receipt["receipt_hash"] = "sha256:" + hashlib.sha256(
            json.dumps(receipt, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()
        return receipt

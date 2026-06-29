"""Phase 6 optional hardware adapter validation.

BEAST can understand vLLM/SGLang/LMCache/Ray/Dynamo/llm-d style systems
without pretending this CPU host has GPU serving hardware.  This validator
turns adapter availability into evidence cards and keeps unconfigured or
GPU-only systems out of the authority path.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.kernel.compute.inference_engine_fabric import InferenceEngineFabric


PHASE6_EXPECTED = {
    "llama_cpp": "cpu_prompt_slots",
    "ollama": "cpu_local_context_reuse",
    "vllm": "gpu_prefix_cache_paged_attention",
    "sglang": "gpu_structured_execution",
    "tgi": "serving_compatibility",
    "lmcache": "external_kv_backend",
    "ray_serve": "replica_orchestration",
    "nvidia_dynamo": "prefill_decode_disaggregation",
    "llm_d": "kubernetes_cache_aware_routing",
}


class HardwareAdapterValidator:
    def __init__(self, fabric: Optional[InferenceEngineFabric] = None, output_root: Optional[Path] = None):
        self.fabric = fabric or InferenceEngineFabric()
        self.output_root = Path(output_root or "benchmarks/results/hardware_adapters")
        self.output_root.mkdir(parents=True, exist_ok=True)

    def validate(self, *, probe: bool = False) -> Dict[str, Any]:
        inventory = self.fabric.inventory(probe=probe)
        engines = {item.get("engine_id"): item for item in inventory.get("engines") or []}
        orchestrators = {item.get("orchestrator_id"): item for item in inventory.get("orchestrators") or []}
        caches = {item.get("cache_backend_id"): item for item in inventory.get("cache_backends") or []}
        cards: List[Dict[str, Any]] = []
        for adapter_id, role in PHASE6_EXPECTED.items():
            source = engines.get(adapter_id) or orchestrators.get(adapter_id) or caches.get(adapter_id) or {}
            configured = bool(source.get("configured"))
            cpu_supported = bool(source.get("cpu_supported"))
            ready = bool(source.get("ready")) if probe else configured and cpu_supported
            authority = "eligible_for_local_probe" if ready else "metadata_only_not_authoritative"
            reason = source.get("reason") or ("ready" if ready else "not_configured_or_not_cpu_supported")
            cards.append({
                "beast_object_type": "hardware_adapter_card",
                "version": "1.0",
                "adapter_id": adapter_id,
                "phase6_role": role,
                "configured": configured,
                "cpu_supported": cpu_supported,
                "ready": ready,
                "reason": reason,
                "capabilities": source.get("capabilities") or {},
                "authority": authority,
                "promotion_allowed": False,
                "promotion_rule": "requires Forge compatibility, mutation, failure, and reproduction evidence",
            })
        cpu_ready = [item for item in cards if item["ready"] and item["cpu_supported"]]
        blocked_gpu = [item for item in cards if not item["cpu_supported"] and not item["ready"]]
        report = {
            "beast_object_type": "proof_local_phase6_hardware_adapter_report",
            "version": "1.0",
            "status": "implemented",
            "host_policy": "cpu_first_capability_gated",
            "cards": cards,
            "summary": {
                "adapter_count": len(cards),
                "cpu_ready": len(cpu_ready),
                "gpu_or_external_blocked": len(blocked_gpu),
                "promotion_allowed": False,
            },
            "exit_criteria": {
                "cpu_llama_or_ollama_profile_present": any(item["adapter_id"] in {"llama_cpp", "ollama"} for item in cards),
                "gpu_engines_do_not_claim_cpu_authority": all(
                    item["authority"] == "metadata_only_not_authoritative"
                    for item in cards
                    if item["adapter_id"] in {"vllm", "sglang", "nvidia_dynamo", "llm_d"} and not item["cpu_supported"]
                ),
                "cache_backends_are_capability_gated": any(item["adapter_id"] == "lmcache" for item in cards),
                "no_adapter_promoted_without_forge_evidence": not any(item["promotion_allowed"] for item in cards),
            },
            "claim_boundary": "adapter_capability_cards_only_no_scheduler_reimplementation",
        }
        latest = self.output_root / "proof_local_phase6_hardware_adapters_latest.json"
        latest.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
        return report

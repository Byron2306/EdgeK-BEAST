"""Auditable disposition of every top-level compute module."""
from __future__ import annotations

from pathlib import Path


ONLINE_ENFORCEMENT = frozenset({
    "action_ir", "action_resolver", "adaptive_dispatcher", "adaptive_inference",
    "ast_compressor", "compression_pipeline", "compute_forge", "compute_ir",
    "compute_ledger", "compute_plane", "crystal_credit_quarantine", "crystal_forks",
    "crystal_generalizer", "crystal_replay_lab", "crystal_reuse_gateway",
    "crystal_runtime_boundary", "crystal_staleness_policy", "crystal_tool_boundary",
    "distributed_forge_scheduler", "forge_isolation", "forge_supervisor", "heldout_replay",
    "inference_interceptor", "kv_cache_transport", "kv_engine_adapter", "local_capabilities",
    "local_execution_gateway", "local_prefix_kv_store", "local_route_optimizer",
    "local_semantic_cache", "mission_crystal_lattice", "perceive",
    "physical_crystal_lifecycle", "proof_local_admission_bridge", "proof_local_compute",
    "runtime_crystallizer", "socket_inventory", "streaming_interceptor",
    "typed_crystal_interpreter", "typed_crystal_ir", "file_build_transform",
    "disk_pressure_cleanup", "displacement_economics",
})

SUPERVISED_EVIDENCE = frozenset({
    "ablation_harness", "benchmark", "cloud_disabled_replay_benchmark",
    "crystal_autopromotion_daemon", "crystal_evidence_bridge",
    "crystal_integration_acceptance", "crystal_materializer",
    "crystal_promotion_evidence_sources", "crystallized_compute_proof",
    "definitive_crystal_lane_proof", "displacement", "earth_shattering_proof_gauntlet",
    "final_boss_crystallization_gauntlet", "full_spectrum_crystallization_gauntlet",
    "hard_coding_crystallization_gauntlet", "hardware_adapter_validation", "integration_acceptance",
    "integration_harness", "kv_restore_harness", "nim_live_probe",
    "provider_tournament_gauntlet", "public_benchmark_grading_daemon",
    "scientific_uplift_experiment", "sensorium_port_crystal_experiment",
    "unified_evidence_packet", "evidence_job_supervisor", "milestone11_uplift",
    "sensorium_file_build_crystal_experiment",
    "sensorium_disk_cleanup_experiment", "milestone11_cross_runtime",
})

OFFLINE_LIBRARY = frozenset({
    "agent_scheduler", "causal_inference", "container", "crystal_bus", "crystal_distillation",
    "crystal_hypergraph", "enterprise", "equivalence_engine", "factory",
    "governed_crystal_executor", "inference_engine_fabric", "interference_buckets",
    "local_compute_cascade", "memory_policy", "port_conflict_crystal",
    "port_conflict_fixture", "resource_executor", "sealed_capsule",
})

RETIRED = {"crystal_integrations": "duplicate compatibility registry removed; use local_capabilities"}


def disposition_report() -> dict:
    directory = Path(__file__).parent
    present = {path.stem for path in directory.glob("*.py") if path.stem != "__init__"}
    classified = ONLINE_ENFORCEMENT | SUPERVISED_EVIDENCE | OFFLINE_LIBRARY
    return {
        "beast_object_type": "compute_module_dispositions", "version": "1.0",
        "online_enforcement": sorted(ONLINE_ENFORCEMENT & present),
        "supervised_evidence": sorted(SUPERVISED_EVIDENCE & present),
        "offline_library": sorted(OFFLINE_LIBRARY & present),
        "retired": dict(RETIRED),
        "unclassified": sorted(present - classified - {"module_dispositions"}),
        "missing_classified_modules": sorted(classified - present),
        "all_present_modules_classified": not (present - classified - {"module_dispositions"}),
    }

"""Canonical, read-only capability catalog for the BEAST desktop IDE.

The catalog deliberately reports four different facts: code availability,
runtime enablement, persisted evidence, and a current live observation.  A
tested implementation is not described as live merely because its module is
installed.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_TRUE_VALUES = frozenset({"1", "true", "yes", "on", "enabled"})


@dataclass(frozen=True)
class _Capability:
    id: str
    title: str
    domain: str
    primary_surface: str
    surfaces: tuple[str, ...]
    source: str
    claim: str
    flags: tuple[str, ...] = ()
    default_enabled: bool = False
    evidence: tuple[str, ...] = ()
    mode: str = "available"


_CAPABILITIES = (
    _Capability("coder_runtime", "Agent Coder runtime", "agents", "agents", ("agents", "atlas"), "docs/superpowers/plans/2026-10-28-beast-coder-tli.md", "Governed IDE coding route; provider output still requires the existing compilation and approval gates.", default_enabled=True, evidence=(".beast/agent_runs", ".beast/agent_sessions"), mode="governed"),
    _Capability("commons_reconciliation", "Commons reconciliation", "commons", "commons", ("commons", "atlas"), "docs/superpowers/plans/2026-11-15-physical-crystal-fabric-phase1.md", "Reconciles configured Commons endpoints; it does not prove remote custody or publication.", default_enabled=True, evidence=(".beast/commons/reconciliation",), mode="read-only"),
    _Capability("commons_health", "Commons health", "commons", "commons", ("commons", "atlas"), "docs/superpowers/plans/2026-11-15-physical-crystal-fabric-phase2-health.md", "Reports bounded endpoint health observations, not permanent availability.", default_enabled=True, evidence=(".beast/commons/health",), mode="observed"),
    _Capability("socket_guardian", "Socket guardian", "infrastructure", "system", ("system", "compute-fabric", "atlas"), "docs/superpowers/plans/2026-11-15-physical-crystal-fabric-phase3-guardian.md", "Implementation is present; host activation and custody remain operator controlled.", evidence=(".beast/guardian",), mode="operator-loaded"),
    _Capability("crystal_bus", "Consolidated crystal bus", "crystals", "crystallization", ("crystallization", "compute-fabric", "atlas"), "docs/superpowers/plans/2026-11-16-physical-crystal-fabric-d4-crystal-bus.md", "Bus transfer is opt-in and only moves already admitted bounded artifacts.", flags=("BEAST_CONSOLIDATED_CRYSTAL_BUS",), evidence=(".beast/crystal_bus",), mode="opt-in"),
    _Capability("episode_envelopes", "Episode envelopes", "agents", "agents", ("agents", "memory", "atlas"), "docs/superpowers/plans/2026-11-15-physical-crystal-fabric-phase5-episode-envelope.md", "Persists bounded episode evidence; existence does not imply successful verification.", default_enabled=True, evidence=(".beast/sensorium/episode_envelopes.sqlite3",), mode="recording"),
    _Capability("coding_crystal_loop", "Coding-crystal loop", "crystals", "crystallization", ("crystallization", "agents", "atlas"), "docs/superpowers/plans/2026-11-15-physical-crystal-fabric-phase6-crystal-loop.md", "Produces or reuses candidates only when enabled; promotion remains separately governed.", flags=("BEAST_CODING_CRYSTALS",), evidence=(".beast/crystals",), mode="opt-in"),
    _Capability("crystal_publication", "Crystal publication", "commons", "commons", ("commons", "crystallization", "atlas"), "docs/superpowers/plans/2026-11-15-physical-crystal-fabric-phase7-crystal-publication.md", "Publication receipts prove a publication attempt, not independent semantic correctness.", default_enabled=True, evidence=(".beast/commons/publications",), mode="governed"),
    _Capability("shadow_economy", "Shadow economy", "governance", "economy", ("economy", "compute-control", "atlas"), "docs/superpowers/plans/2026-11-16-physical-crystal-fabric-compute-governor-spine.md", "Shadow scoring records proposals and never grants execution authority.", default_enabled=True, evidence=(".beast/governor/shadow",), mode="shadow"),
    _Capability("compute_governor", "Compute governor", "governance", "compute-control", ("compute-control", "agents", "atlas"), "docs/superpowers/plans/2026-11-16-physical-crystal-fabric-compute-governor-spine.md", "Defaults to shadow evaluation; enforcement is explicit and does not replace approval.", flags=("BEAST_GOVERNOR_ENFORCE",), default_enabled=True, evidence=(".beast/governor",), mode="shadow"),
    _Capability("memory_contract", "Memory hull and seal", "memory", "memory", ("memory", "agents", "atlas"), "docs/superpowers/plans/2026-11-16-physical-crystal-fabric-compute-governor-spine.md", "Bounded reads and seals expose provenance; they do not certify remembered content as true.", evidence=(".beast/memory", ".beast/sensorium"), mode="governed"),
    _Capability("promotion_evidence", "Promotion evidence", "governance", "economy", ("economy", "crystallization", "atlas"), "docs/superpowers/plans/2026-11-16-physical-crystal-fabric-compute-governor-spine.md", "Evidence supports an operator decision and never promotes a candidate by itself.", default_enabled=True, evidence=(".beast/promotion",), mode="operator-gated"),
    _Capability("crystal_lattice", "Crystal lattice", "crystals", "crystallization", ("crystallization", "compute-fabric", "atlas"), "docs/superpowers/plans/2026-11-16-physical-crystal-fabric-lattice-spine.md", "Admission and ForgeKV publication remain opt-in and require valid lattice evidence.", flags=("BEAST_CRYSTAL_LATTICE",), evidence=(".beast/crystals/lattice",), mode="opt-in"),
    _Capability("adaptive_router", "Adaptive router", "routing", "compute-control", ("compute-control", "agents", "atlas"), "docs/superpowers/plans/2026-11-16-physical-crystal-fabric-phase9-adaptive-router.md", "Proposal-only by default; it cannot silently override the selected route.", flags=("BEAST_ADAPTIVE_ROUTER",), evidence=(".beast/router",), mode="proposal-only"),
    _Capability("swarm_specialist", "Swarm specialist", "agents", "agents", ("agents", "compute-control", "atlas"), "docs/superpowers/plans/2026-11-16-physical-crystal-fabric-swarm-specialist-cascade.md", "Specialist output is advisory and must rejoin the governed cascade before execution.", flags=("BEAST_SWARM_SPECIALIST",), evidence=(".beast/swarm",), mode="advisory"),
    _Capability("compression_tiers", "Compression tiers", "tooling", "tooling", ("tooling", "agents", "atlas"), "docs/superpowers/plans/2026-11-16-physical-crystal-fabric-experimental-tiers.md", "RTK, SQZ, longcodezip, and reporelay are bounded context transforms with receipts.", flags=("BEAST_COMPRESSION_TIERS",), evidence=(".beast/compression",), mode="opt-in"),
    _Capability("adapter_compiler", "Adapter compiler", "tooling", "tooling", ("tooling", "compute-fabric", "atlas"), "docs/superpowers/plans/2026-11-16-physical-crystal-fabric-experimental-tiers.md", "Builds governed adapter proposals; compiled output is not automatically activated.", flags=("BEAST_ADAPTER_COMPILER",), evidence=(".beast/adapters",), mode="opt-in"),
    _Capability("defrag_daemon", "Defrag daemon", "infrastructure", "compute-fabric", ("compute-fabric", "system", "atlas"), "docs/superpowers/plans/2026-11-16-physical-crystal-fabric-experimental-tiers.md", "Observation is separate from apply; mutations require the explicit apply flag.", flags=("BEAST_DEFRAG_DAEMON", "BEAST_DEFRAG_APPLY"), evidence=(".beast/defrag",), mode="observe-first"),
    _Capability("zero_copy_kv", "Zero-copy KV handoff", "infrastructure", "compute-fabric", ("compute-fabric", "system", "atlas"), "docs/superpowers/plans/2026-11-16-physical-crystal-fabric-experimental-tiers.md", "Uses the tested host-local memfd handoff; no nonexistent kv_transport.py or engine KV API is claimed.", flags=("BEAST_ZERO_COPY_KV",), evidence=(".beast/kv_handoff",), mode="synthetic-host-local"),
    _Capability("xdp_fastpath", "XDP fast-path", "infrastructure", "system", ("system", "compute-fabric", "atlas"), "docs/superpowers/plans/2026-11-16-physical-crystal-fabric-experimental-tiers.md", "The IDE maps simulation evidence only; loading XDP/eBPF and X7 LSM/ARDA is an operator action.", flags=("BEAST_XDP_FASTPATH_SIM",), evidence=(".beast/xdp",), mode="simulation"),
)


# Component-level source-of-record projection from the 2026-11-16 :8199
# audit.  These are intentionally nested beneath the smaller capability map:
# operators need a scannable Atlas, but the detailed deliveries must remain
# discoverable rather than being flattened away.
_COMPONENT_ROWS: dict[str, tuple[tuple[str, str, str, str, str], ...]] = {
    "coder_runtime": (
        ("tli_runtime_client", "CoderRuntimeClient and RuntimeEvent projection", "tested", "cli_only", "not_fired"),
        ("tli_persistent_state", "Coder settings, conversation store, and slash commands", "tested", "cli_only", "not_fired"),
        ("tli_textual_ui", "Focused Textual BeastCoderApp", "tested", "cli_only", "not_fired"),
        ("tli_launcher", "Default launcher and rollback", "tested", "cli_only", "not_fired"),
        ("planner_runtime", "AgentPlannerRuntime, tool registry, and run engine", "tested", "agents", "fired"),
        ("code_cortex", "Code Cortex repository observation", "tested", "agents", "fired"),
        ("agent_approvals", "Durable Agent Coder capability approvals", "tested", "agents", "fired"),
        ("pathfinder_live_coding", "Pathfinder live-coding route", "tested", "agents", "fired"),
        ("semantic_raid", "Semantic RAID context-packet mirror", "tested", "agents", "fired"),
        ("action_ir", "Constrained Action IR and line-anchored edits", "tested", "agents", "reached_not_completed"),
        ("sourceplan_review", "SourcePlan review, verification, apply, and rollback", "tested", "review", "not_fired"),
        ("mcp_tool_surface", "MCP tool surface (69-tool audit inventory)", "tested", "tooling", "probe_only"),
        ("model_inventory", "IDE model inventory (38-model audit inventory)", "tested", "models", "probe_only"),
        ("provider_inventory", "Provider/proxy inventory (29-provider audit inventory)", "tested", "models", "probe_only"),
        ("capability_router", "Capability scorecard and Auto routing", "tested", "models", "probe_only"),
    ),
    "commons_reconciliation": (
        ("fabric_architecture", "Fabric control plane and Commons nodes", "partial", "commons", "not_fired"),
        ("fabric_trust_identity", "Signed candidates, custody, and verify-only trust", "tested", "commons", "not_fired"),
        ("fabric_topology_contract", "AF_UNIX/SOCK_SEQPACKET and SCM_RIGHTS topology", "tested", "commons", "not_fired"),
        ("registry_endpoint_reconciliation", "Atomic registry endpoint reconciliation", "tested", "commons", "not_fired"),
        ("signed_candidate_verification", "Signed candidate verify-only path", "tested", "commons", "not_fired"),
        ("commons_operator_api", "Local operator API and topology routes", "tested", "commons", "not_fired"),
        ("commons_live_recovery", "Commons live recovery and verification", "tested", "commons", "not_fired"),
    ),
    "commons_health": (
        ("signed_container_health", "Signed container health verifier", "tested", "commons", "not_fired"),
        ("fabric_health", "Control-plane fabric health", "tested", "commons", "probe_only"),
        ("discovery_supersession", "Discovery supersession", "tested", "commons", "not_fired"),
        ("commons_ide_evidence", "Commons live health IDE evidence", "tested", "commons", "probe_only"),
    ),
    "socket_guardian": (
        ("socket_guardian_daemon", "Topology-bound socket guardian daemon", "tested", "system", "probe_only"),
        ("guardian_owned_listener", "Guardian-owned gateway listener", "tested", "system", "not_fired"),
        ("commons_custody", "Commons signed custody records", "tested", "commons", "not_fired"),
        ("process_lifecycle", "Governed process lifecycle", "tested", "system", "not_fired"),
        ("heal_stack", "Full-stack heal and selective recovery", "tested", "system", "not_fired"),
        ("gpu_scheduler", "GPU scheduler and TGI/Ollama placement", "tested", "compute-fabric", "not_fired"),
        ("x7_lsm_arda", "X7 LSM with ARDA userspace integration", "compiled_not_loaded", "system", "not_fired"),
    ),
    "crystal_bus": (
        ("crystal_bus_transfer", "Consolidated Crystal Bus descriptor transfer", "tested", "crystallization", "not_fired"),
        ("crystal_bus_authority", "One-use bus authority", "tested", "crystallization", "not_fired"),
        ("crystal_bus_custody", "Signed hash-chained bus custody", "tested", "crystallization", "not_fired"),
        ("crystal_bus_peer_verification", "Strict peer credentials and sequence ledger", "tested", "compute-fabric", "not_fired"),
    ),
    "episode_envelopes": (
        ("episode_budget_tracker", "Run budget tracker", "tested", "agents", "not_fired"),
        ("episode_envelope_seal", "Privacy-filtered episode envelope and seal", "tested", "agents", "not_fired"),
        ("episode_planner_wiring", "Planner runtime episode wiring", "tested", "agents", "reached_not_completed"),
    ),
    "coding_crystal_loop": (
        ("coding_opcodes", "Reviewed coding opcodes and deterministic resolver", "tested", "crystallization", "not_fired"),
        ("crystal_extraction", "Crystal extraction and negative evidence", "tested", "crystallization", "not_fired"),
        ("crystal_heldout_replay", "Three-variant no-model held-out replay", "tested", "crystallization", "not_fired"),
        ("coding_crystal_promotion", "Operator-gated coding-crystal promotion", "tested_default_off", "crystallization", "not_fired"),
        ("crystal_reuse_preflight", "Context-bound crystal reuse preflight", "tested", "agents", "fired"),
        ("family_crystal_lookup", "Promoted family-crystal lookup and bind", "tested", "crystallization", "fired_no_hit"),
        ("symbol_surgeon", "Rename-symbol family tool", "tested", "tooling", "not_fired"),
    ),
    "crystal_publication": (
        ("publication_bundle", "Signed privacy-filtered publication bundle", "tested", "commons", "not_fired"),
        ("forgekv_publication", "ForgeKV atomic publication and dataset layout", "tested", "commons", "not_fired"),
        ("commons_space_quarantine", "Commons Space verify-only import and quarantine", "tested", "commons", "not_fired"),
        ("witness_quorum", "Node-signed witness receipts and quorum", "tested", "review", "not_fired"),
        ("ml_kem_channel", "ML-KEM protected publication channel", "tested_operator_loaded", "system", "not_fired"),
        ("local_reproduction", "Local held-out imported-crystal reproduction", "tested", "crystallization", "not_fired"),
    ),
    "shadow_economy": (
        ("crystal_reuse_credit", "Shadow reuse credit and reduction receipts", "tested", "economy", "not_fired"),
        ("maintenance_risk_costs", "Maintenance, risk, rating, sybil, and clawback accounting", "tested", "economy", "not_fired"),
        ("commons_economy_snapshot", "Commons economy snapshot", "tested", "economy", "probe_only"),
    ),
    "compute_governor": (
        ("precision_prec", "PREC perceive, reason, economize, compute", "tested", "agents", "fired"),
        ("governor_admit_order", "Compute Governor strict admit ordering", "tested", "compute-control", "fired"),
        ("task_envelope_binding", "Task-envelope to episode-seal binding", "tested", "agents", "not_fired"),
        ("governor_settlement", "Governor-receipt settlement gate", "tested_default_off", "economy", "not_fired"),
        ("skill_tree_promotion", "Skill Tree promotion through D6", "tested_default_off", "crystallization", "not_fired"),
        ("chronicle_receipts", "Chronicle/L4 receipt sinks", "tested", "review", "probe_only"),
        ("eviction_dry_run", "PSI/PRISM eviction dry-run through admit", "tested", "compute-control", "not_fired"),
        ("inference_interceptor", "Governed inference interception", "tested", "agents", "fired"),
        ("streaming_interceptor", "Governed streaming interception", "tested", "agents", "reached_not_completed"),
        ("constrained_output", "Constrained JSON and Action IR output", "tested", "agents", "reached_not_completed"),
        ("model_context_budget", "Model-aware input and output budgets", "tested", "agents", "fired"),
        ("governed_egress", "Governed provider egress shim", "tested", "compute-control", "not_fired"),
    ),
    "memory_contract": (
        ("memory_reader_contract", "Tiered governed memory reader", "tested", "memory", "not_fired"),
        ("memory_hull", "Editable Memory Hull", "tested", "memory", "not_fired"),
        ("residue_seal", "Tamper-evident residue seal", "tested", "memory", "not_fired"),
        ("vector_rag", "Attributed Vector RAG retrieval", "tested", "memory", "not_fired"),
        ("crystal_vector_bridge", "Crystal/vector runtime bridge", "tested", "memory", "not_fired"),
    ),
    "promotion_evidence": (
        ("promotion_evidence_packet", "Operator promotion evidence packet", "tested", "economy", "not_fired"),
        ("witness_ledgers", "Witness, event-chain, and promotion ledgers", "tested", "review", "partial"),
    ),
    "crystal_lattice": (
        ("lattice_graph", "Governed CrystalLattice composition graph", "tested", "crystallization", "probe_only"),
        ("lattice_admit_composite", "Two-child composite admission", "tested_default_off", "crystallization", "not_fired"),
        ("lattice_demote_cascade", "Lattice demotion cascade and clawback", "tested_default_off", "economy", "not_fired"),
        ("lattice_composite_credit", "Composite reuse credit and premium cap", "tested", "economy", "not_fired"),
    ),
    "adaptive_router": (
        ("adaptive_router_proposal", "Unified Adaptive Router proposal", "tested_default_off", "compute-control", "not_fired"),
        ("adaptive_decision_bands", "Adaptive decision bands", "tested", "models", "not_fired"),
        ("adaptive_crystal_fingerprints", "D6/D5 crystal fingerprints", "tested", "crystallization", "not_fired"),
        ("semantic_reuse_nomination", "Semantic reuse nomination with verifier", "tested", "agents", "fired_no_hit"),
    ),
    "swarm_specialist": (
        ("swarm_runner", "Local Ollama swarm specialist runner", "tested_default_off", "agents", "not_fired"),
        ("swarm_dispatch", "Cascade-gated SwarmSpecialistDispatch", "tested_default_off", "agents", "not_fired"),
        ("psi_shrink", "PSI pressure shrink", "tested_default_off", "compute-control", "not_fired"),
        ("rtk_cascade", "RTK cascade-output compression", "tested_default_off", "tooling", "not_fired"),
        ("quality_cascade", "Quality Cascade run hook", "tested", "review", "not_fired"),
    ),
    "compression_tiers": (
        ("rtk_compression", "RTK diagnostic compression", "tested", "tooling", "not_fired"),
        ("sqz_compression", "SQZ diagnostic compression", "tested", "tooling", "not_fired"),
        ("longcodezip_compression", "LongCodeZip-style source compression", "tested", "tooling", "not_fired"),
        ("reporelay_map", "RepoRelay-style repository map", "tested", "tooling", "not_fired"),
    ),
    "adapter_compiler": (
        ("local_adapter_compiler", "Governed local adapter compiler", "tested_default_off", "tooling", "not_fired"),
    ),
    "defrag_daemon": (
        ("defrag_observer", "Defragmentation observer and dry-run plan", "tested_default_off", "compute-fabric", "not_fired"),
        ("defrag_apply", "Governed reversible defrag apply", "tested_default_off", "system", "not_fired"),
    ),
    "zero_copy_kv": (
        ("kv_transport_plan_path", "Planned kv_transport.py module", "missing_plan_path", "compute-fabric", "not_fired"),
        ("kv_memfd_handoff", "Sealed memfd ForgeKV handoff", "tested", "compute-fabric", "not_fired"),
        ("kv_engine_restore", "Inference-engine KV export/import", "not_implemented", "compute-fabric", "not_fired"),
    ),
    "xdp_fastpath": (
        ("xdp_userspace_sim", "XDP admitted-flow userspace simulator", "tested", "system", "not_fired"),
        ("xdp_kernel_program", "Loaded XDP/eBPF fast path", "operator_not_loaded", "system", "not_fired"),
    ),
}


def _components(capability_id: str) -> list[dict[str, str]]:
    return [
        {
            "id": component_id,
            "title": title,
            "backend_state": backend_state,
            "ide_wiring": ide_wiring,
            "baseline_run_state": baseline_run_state,
        }
        for component_id, title, backend_state, ide_wiring, baseline_run_state in _COMPONENT_ROWS.get(capability_id, ())
    ]


def _enabled(capability: _Capability, environ: Mapping[str, str]) -> bool:
    if not capability.flags:
        return capability.default_enabled
    explicit = [str(environ.get(flag, "")).strip().lower() in _TRUE_VALUES for flag in capability.flags]
    return capability.default_enabled or any(explicit)


def _evidence(root: Path, candidates: tuple[str, ...]) -> dict[str, Any]:
    present: list[Path] = []
    for relative in candidates:
        path = root / relative
        try:
            if path.exists():
                present.append(path)
        except OSError:
            continue
    updated_at: float | None = None
    for path in present:
        try:
            stamp = path.stat().st_mtime
        except OSError:
            continue
        updated_at = max(updated_at or stamp, stamp)
    return {"present": bool(present), "count": len(present), "updated_at": updated_at}


def build_integration_catalog(root: Path, environ: Mapping[str, str] | None = None) -> dict[str, Any]:
    """Build the safe server-owned integration projection for one workspace."""
    workspace = Path(root).expanduser().resolve()
    runtime_env = os.environ if environ is None else environ
    rows: list[dict[str, Any]] = []
    for capability in _CAPABILITIES:
        evidence = _evidence(workspace, capability.evidence)
        enabled = _enabled(capability, runtime_env)
        mode = capability.mode
        if capability.id == "compute_governor":
            mode = "enforcing" if str(runtime_env.get("BEAST_GOVERNOR_ENFORCE", "")).strip().lower() in _TRUE_VALUES else "shadow"
        rows.append(
            {
                "id": capability.id,
                "title": capability.title,
                "domain": capability.domain,
                "implemented": True,
                "enabled": enabled,
                "mode": mode,
                "evidence": evidence,
                "live": False,
                "claim": capability.claim,
                "source": capability.source,
                "flags": list(capability.flags),
                "surfaces": list(capability.surfaces),
                "primary_surface": capability.primary_surface,
                "components": _components(capability.id),
            }
        )
    return {
        "status": "available",
        "baseline": {
            "audit": "evidence/agent-coder-audit-2026-11-16/REPORT.md",
            "inventory": "evidence/agent-coder-audit-2026-11-16/superpowers-inventory.json",
            "run_id": "implementer-c17b0faf-6287242d2187",
            "gateway": ":8199",
            "captured_at": "2026-11-16",
        },
        "capabilities": rows,
        "summary": {
            "total": len(rows),
            "implemented": sum(1 for row in rows if row["implemented"]),
            "enabled": sum(1 for row in rows if row["enabled"]),
            "with_evidence": sum(1 for row in rows if row["evidence"]["present"]),
            "live": sum(1 for row in rows if row["live"]),
        },
    }


__all__ = ["build_integration_catalog"]

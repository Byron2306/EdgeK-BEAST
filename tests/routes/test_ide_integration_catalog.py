from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter

from app.routes.ide_routes.integrations import register_integration_routes
from app.routes.ide_support.integration_catalog import build_integration_catalog

EXPECTED_CAPABILITIES = {
    "coder_runtime",
    "commons_reconciliation",
    "commons_health",
    "socket_guardian",
    "crystal_bus",
    "episode_envelopes",
    "coding_crystal_loop",
    "crystal_publication",
    "shadow_economy",
    "compute_governor",
    "memory_contract",
    "promotion_evidence",
    "crystal_lattice",
    "adaptive_router",
    "swarm_specialist",
    "compression_tiers",
    "adapter_compiler",
    "defrag_daemon",
    "zero_copy_kv",
    "xdp_fastpath",
}


def test_catalog_maps_every_completed_superpowers_integration_to_an_ide_surface(tmp_path: Path) -> None:
    payload = build_integration_catalog(tmp_path, environ={})
    capabilities = {item["id"]: item for item in payload["capabilities"]}

    assert set(capabilities) == EXPECTED_CAPABILITIES
    assert payload["summary"] == {
        "total": 20,
        "implemented": 20,
        "enabled": 8,
        "with_evidence": 0,
        "live": 0,
    }
    assert all(item["implemented"] is True for item in capabilities.values())
    assert all(item["surfaces"] for item in capabilities.values())
    assert all(item["primary_surface"] in item["surfaces"] for item in capabilities.values())
    assert capabilities["episode_envelopes"]["primary_surface"] == "agents"
    assert capabilities["coding_crystal_loop"]["primary_surface"] == "crystallization"
    assert capabilities["crystal_publication"]["primary_surface"] == "commons"
    assert capabilities["compute_governor"]["primary_surface"] == "compute-control"
    assert capabilities["compression_tiers"]["primary_surface"] == "tooling"


def test_catalog_separates_enabled_evidence_and_live_without_leaking_secrets(tmp_path: Path) -> None:
    secret = "do-not-return-this-key-value"
    environment = {
        "BEAST_CODING_CRYSTALS": "1",
        "BEAST_ADAPTIVE_ROUTER": "true",
        "BEAST_GOVERNOR_ENFORCE": "0",
        "BEAST_CODING_CRYSTAL_KEY": secret,
        "BEAST_COMMONS_CUSTODY_SIGNING_KEY": secret,
        "GITHUB_TOKEN": secret,
    }
    (tmp_path / ".beast" / "sensorium").mkdir(parents=True)
    (tmp_path / ".beast" / "sensorium" / "episode_envelopes.sqlite3").write_bytes(b"not-a-database")

    payload = build_integration_catalog(tmp_path, environ=environment)
    capabilities = {item["id"]: item for item in payload["capabilities"]}
    rendered = repr(payload)

    assert capabilities["coding_crystal_loop"]["enabled"] is True
    assert capabilities["adaptive_router"]["enabled"] is True
    assert capabilities["compute_governor"]["enabled"] is True
    assert capabilities["compute_governor"]["mode"] == "shadow"
    assert capabilities["episode_envelopes"]["evidence"]["present"] is True
    assert capabilities["episode_envelopes"]["live"] is False
    assert secret not in rendered
    assert "BEAST_CODING_CRYSTAL_KEY" not in rendered
    assert "GITHUB_TOKEN" not in rendered


def test_catalog_tolerates_missing_optional_artifacts_and_names_claim_boundaries(tmp_path: Path) -> None:
    payload = build_integration_catalog(tmp_path, environ={})

    assert payload["status"] == "available"
    for capability in payload["capabilities"]:
        assert capability["evidence"]["present"] is False
        assert capability["live"] is False
        assert capability["claim"]
        assert capability["source"].startswith(("docs/superpowers/", ".superpowers/sdd/"))
        assert set(capability["flags"]).issubset(
            {
                "BEAST_CODING_CRYSTALS",
                "BEAST_COMMONS_CUSTODY_SIGNING_KEY",
                "BEAST_CONSOLIDATED_CRYSTAL_BUS",
                "BEAST_GOVERNOR_ENFORCE",
                "BEAST_CRYSTAL_LATTICE",
                "BEAST_ADAPTIVE_ROUTER",
                "BEAST_SWARM_SPECIALIST",
                "BEAST_COMPRESSION_TIERS",
                "BEAST_ADAPTER_COMPILER",
                "BEAST_DEFRAG_DAEMON",
                "BEAST_DEFRAG_APPLY",
                "BEAST_ZERO_COPY_KV",
                "BEAST_XDP_FASTPATH_SIM",
            }
        )


def test_integration_route_registrar_exposes_the_read_only_catalog(tmp_path: Path) -> None:
    router = APIRouter()
    register_integration_routes(router, resolve_root=lambda value=None: Path(value or tmp_path).resolve())

    routes = {(route.path, tuple(sorted(route.methods or []))) for route in router.routes}
    assert ("/edgek/ide/integrations", ("GET",)) in routes


def test_catalog_preserves_the_complete_audit_component_map_and_baseline_provenance(tmp_path: Path) -> None:
    payload = build_integration_catalog(tmp_path, environ={})
    components = {
        component["id"]: component
        for capability in payload["capabilities"]
        for component in capability["components"]
    }

    assert payload["baseline"] == {
        "audit": "evidence/agent-coder-audit-2026-11-16/REPORT.md",
        "inventory": "evidence/agent-coder-audit-2026-11-16/superpowers-inventory.json",
        "run_id": "implementer-c17b0faf-6287242d2187",
        "gateway": ":8199",
        "captured_at": "2026-11-16",
    }
    assert len(components) >= 70
    assert {
        "tli_runtime_client",
        "code_cortex",
        "pathfinder_live_coding",
        "semantic_raid",
        "mcp_tool_surface",
        "model_inventory",
        "provider_inventory",
        "socket_guardian_daemon",
        "crystal_bus_transfer",
        "family_crystal_lookup",
        "forgekv_publication",
        "ml_kem_channel",
        "precision_prec",
        "rtk_compression",
        "sqz_compression",
        "longcodezip_compression",
        "reporelay_map",
        "vector_rag",
        "memory_hull",
        "swarm_dispatch",
        "psi_shrink",
        "gpu_scheduler",
        "process_lifecycle",
        "adaptive_router_proposal",
        "kv_memfd_handoff",
        "kv_transport_plan_path",
        "xdp_userspace_sim",
        "x7_lsm_arda",
    } <= set(components)
    assert components["code_cortex"]["baseline_run_state"] == "fired"
    assert components["mcp_tool_surface"]["baseline_run_state"] == "probe_only"
    assert components["crystal_bus_transfer"]["baseline_run_state"] == "not_fired"
    assert components["kv_transport_plan_path"]["backend_state"] == "missing_plan_path"
    assert components["kv_memfd_handoff"]["backend_state"] == "tested"

import pytest
from pathlib import Path

from rich.console import Console
from rich.table import Table
from fastapi.testclient import TestClient

from app.cli.api import BackendSnapshot, BeastApiClient, load_master_mega_evidence, load_provider_model_fitness, normalize_litellm_models
from app.main import app
from app.cli.ui import (
    ApprovalQueueScreen,
    BeastHeader,
    BeastMissionConsole,
    CommandPaletteScreen,
    ContextPickerScreen,
    DiffPreviewScreen,
    HEADER_TILE_HEIGHT,
    METRIC_CARD_HEIGHT,
    PAGES,
    PageHost,
    crystal_kv_prefill_counts,
    economy_action_rows,
    intelligence_summary,
    master_evidence_summary,
    metric,
    provider_secrets_operational,
    structured_payload,
)


def test_intelligence_summary_surfaces_governed_runtime_state():
    snap = BackendSnapshot(
        base_url="http://gateway",
        session_handshake={
            "beast_object_type": "beast_session_handshake",
            "session_id": "ses_test",
            "handshake_hash": "sha256:aware",
            "latency_budget": {"preflight_budget_ms": 500, "scout_budget_ms": 300},
        },
        commons_state={"evidence_count": 12, "candidate_count": 3, "adopted_count": 1},
        commons_ranking={"count": 2},
        tool_laziness={"summary": {"skip_count": 2, "learn_more_count": 1, "estimated_latency_avoided_ms": 44}},
        provider_economist={
            "decision": "route_selected", "requested_role": "primary_patch_provider",
            "selected": {"provider": "ovhcloud"},
        },
        capability_exchange_state={"enabled": True},
        otel_state={"configured": True},
        plugins_state={"count": 4},
        compute_state={"mode": "shadow", "enforcing": False},
        compute_metrics={"sample_size": 7, "observed_total_tokens": 1000, "estimated_avoidable_total_tokens": 250},
    )

    summary = intelligence_summary(snap)

    assert summary["aware"] is True
    assert summary["preflight_budget_ms"] == 500
    assert summary["commons_evidence"] == 12
    assert summary["tools_skipped"] == 2
    assert summary["economist_provider"] == "ovhcloud"
    assert summary["exchange_enabled"] is True
    assert summary["compute_mode"] == "shadow"
    assert summary["compute_samples"] == 7
    assert summary["avoidable_compute_tokens"] == 250


def test_intelligence_summary_explains_offline_waits():
    snap = BackendSnapshot(base_url="http://offline", online=False, errors={"session_handshake": "connection refused"})

    summary = intelligence_summary(snap)

    assert summary["aware"] is False
    assert summary["online"] is False
    assert "gateway offline" in summary["blocker"]
    assert summary["endpoint_errors"] == 1
    assert summary["economist_reason"] == "no provider Chronicle samples"


def test_provider_secrets_local_routes_are_operational_not_warn():
    snap = BackendSnapshot(
        base_url="offline",
        provider_adapters=[
            {"provider_id": "litellm", "backend": "litellm"},
            {"provider_id": "ollama", "backend": "ollama"},
        ],
        provider_secrets={"providers": {}},
    )

    summary = provider_secrets_operational(snap)

    assert summary["status"] == "OK"
    assert "local" in summary["detail"]


def test_crystal_kv_prefill_counts_include_durable_prefill_credits():
    snap = BackendSnapshot(
        base_url="offline",
        kv_cache_state={"total_blocks": 0, "operations_logged": 0},
        crystal_reuse={
            "storage": {
                "active_credits": 3,
                "stored_by_type": {"kv_prefill": 2, "cached_answer": 1},
                "kv_prefill_credits": 2,
            },
            "kv_transport": {"total_blocks": 0, "operations_logged": 0},
        },
    )

    counts = crystal_kv_prefill_counts(snap)
    summary = intelligence_summary(snap)

    assert counts["durable_prefills"] == 2
    assert counts["display_blocks"] == 2
    assert summary["crystal_kv_blocks"] == 2


def test_intelligence_summary_and_page_show_crystal_reuse_and_memory_security():
    snap = BackendSnapshot(
        base_url="http://gateway",
        online=True,
        crystal_reuse={
            "storage": {"active_credits": 2, "total_credits": 3, "total_reuse_count": 1, "measured_reuse_tokens_saved": 42},
            "kv_transport": {"total_blocks": 1},
            "integration_health": {
                "integration_count": 7,
                "configured_count": 2,
                "integrations": [
                    {"project": "LMCache", "configured": True, "role": "kv", "env_vars": ["LMCACHE_ENDPOINT"], "capabilities": {"kv_cache": True}},
                    {"project": "GPTCache", "configured": False, "role": "semantic", "env_vars": ["GPTCACHE_ENDPOINT"], "capabilities": {"semantic_cache": True}},
                ],
            },
        },
        memory_security={
            "memory_hull": {"root": "/tmp/vault", "verified_sidecars": 1, "failed_sidecars": 0},
            "residue_seal": {"key_exists": True, "key_mode": "0o600"},
            "agent_passport": {
                "policy_lint": {"valid": True, "policy_count": 4},
                "sample_decisions": {"scout_memory_append": {"allowed": True, "reason": "explicit_allow"}},
            },
        },
    )

    summary = intelligence_summary(snap)
    renderable = PageHost().intelligence(snap, 0)

    assert summary["crystal_reuse_credits"] == 2
    assert summary["crystal_integration_configured"] == 2
    assert summary["memory_hull_verified"] == 1
    assert summary["passport_policy_valid"] is True
    assert renderable is not None


def test_intelligence_page_renders_without_active_textual_app():
    snap = BackendSnapshot(
        base_url="offline",
        commons_ranking={
            "count": 1,
            "rankings": [{
                "capability_id": "beast_sourceplan_prepare", "role": "tool_selector",
                "score": 0.82, "confidence": 0.7, "sample_size": 8,
                "local_samples": 5, "global_samples": 3,
            }],
        },
    )

    rendered = PageHost().intelligence(snap, 0)

    assert isinstance(rendered, Table)
    assert rendered.row_count >= 4
    assert "Intelligence" in PAGES


def test_economy_page_renders_first_class_operations():
    snap = BackendSnapshot(
        base_url="offline",
        compute_state={"modes": {"shadow": 3}},
        compute_metrics={"sample_size": 7, "observed_total_tokens": 1000, "stream_tokens_saved": 40},
        compute_savings={"potential_weekly_savings_usd": 0.01},
    )

    rendered = PageHost().economy(snap, 0)
    rows = economy_action_rows({})

    assert isinstance(rendered, Table)
    assert rendered.row_count >= 3
    assert [row["action"] for row in rows] == [
        "rollout_monitor",
        "economy_dashboard",
        "start_forge_node",
        "promote_fleet",
        "refresh_economy",
    ]


def test_spaces_page_renders_registry_scoreboard_and_shadow_policy():
    snap = BackendSnapshot(
        base_url="offline",
        commons_spaces={
            "count": 1,
            "scoreboard": {
                "spaces": 1, "valid_spaces": 1, "verified_spaces": 1,
                "provider_calls_avoided": 1, "gpu_avoided_spaces": 1, "adoptions": 0,
            },
            "artifact_sources": {
                "artifact_types": {"orchestration_plan": 1},
                "source_classes": {"tiny_llama_case": 1},
            },
            "spaces": [{
                "space_id": "tiny_llama", "name": "Tiny Llama Repair",
                "task_class": "hard_gateway_repair", "artifact_count": 3,
                "artifact_types": ["orchestration_plan"], "verifier_passed": True,
                "provider_calls_avoided": 1, "gpu_avoided": True,
                "evidence_class": "mixed", "approval_required": True,
            }],
        },
        commons_policy={
            "mode": "shadow",
            "recommendation": {"route": "tiny_local", "expected_compute_reduction": 0.8, "tools": ["pytest"]},
            "verification_projection": {"would_preserve_verification": True, "verified_support": 1},
        },
        commons_policy_evaluation={"sample_size": 1, "protocol": "in_sample_insufficient_for_holdout", "top1_route_accuracy": 1.0},
    )
    console = Console(record=True, width=160)

    console.print(PageHost().spaces(snap, 0))
    output = console.export_text()

    assert "BEAST COMPUTE SPACES" in output
    assert "Tiny Llama Repair" in output
    assert "SHADOW ONLY" in output
    assert "orchestration_plan" in output
    assert "Spaces" in PAGES


def test_provider_model_fitness_artifact_loads_for_tui(tmp_path: Path):
    artifact = tmp_path / "fitness.json"
    artifact.write_text(
        '{"beast_object_type":"provider_model_fitness_snapshot","models":'
        '[{"provider":"groq","model":"demo","fitness_score":0.875}]}',
        encoding="utf-8",
    )

    loaded = load_provider_model_fitness(artifact)

    assert loaded["models"][0]["provider"] == "groq"
    assert loaded["models"][0]["fitness_score"] == 0.875
    assert loaded["artifact_path"] == str(artifact)


def test_litellm_model_normalization_handles_nested_and_missing_names():
    loaded = normalize_litellm_models({
        "config": {
            "model_list": [
                {"model_name": "llama-local", "litellm_params": {"model": "ollama/qwen2.5:0.5b"}},
                {"litellm_params": {"model": "openai/gpt-5-codex"}},
            ]
        }
    })

    assert loaded[0]["model_name"] == "llama-local"
    assert loaded[0]["provider_model"] == "ollama/qwen2.5:0.5b"
    assert loaded[1]["model_name"] == "openai/gpt-5-codex"


def test_frozen_master_evidence_loads_for_tui(tmp_path: Path):
    bundle = tmp_path / "master_v0_1"
    bundle.mkdir()
    (bundle / "release_manifest.json").write_text(
        '{"release_name":"BEAST Definitive Mega-Test Master Evidence",'
        '"release_version":"0.1","release_status":"frozen",'
        '"controlled_design":{"observed_cells":180,"target_cells":450,"remaining_cells":270,"progress_rate":0.4},'
        '"credibility_layers":[{"id":"natural_no_harness_sessions","status":"pending"}]}',
        encoding="utf-8",
    )
    (bundle / "analysis_metrics.json").write_text(
        '{"mature_deterministic_reuse":12,"mature_qpccd":{"numerator":12,"denominator":24,"rate":0.5},'
        '"mutation_case_count":6,"mutation_recovered":6,"primary_cross_provider_cases":12,'
        '"groq_scout_cases":6,"primary_avoided_tokens_estimate":18768,"groq_scout_avoided_tokens_estimate":9384}',
        encoding="utf-8",
    )
    (bundle / "coverage_matrix.json").write_text('{"natural_observations":{"count":0}}', encoding="utf-8")
    (bundle / "integrity_manifest.json").write_text('{"manifest_hash":"sha256:frozen"}', encoding="utf-8")
    (bundle / "secret_scan.json").write_text('{"passed":true}', encoding="utf-8")

    loaded = load_master_mega_evidence(bundle)
    summary = master_evidence_summary(BackendSnapshot(base_url="offline", master_mega_evidence=loaded))

    assert loaded["release_status"] == "frozen"
    assert summary["release"] == "v0.1"
    assert summary["observed_cells"] == 180
    assert summary["qpccd_rate"] == 0.5
    assert summary["avoided_tokens_estimate"] == 28152
    assert summary["pending_layers"] == 1


def test_mission_and_economy_render_frozen_evidence_release():
    evidence = {
        "release_version": "0.1",
        "release_status": "frozen",
        "secret_scan_passed": True,
        "controlled_design": {"observed_cells": 180, "target_cells": 450, "remaining_cells": 270, "progress_rate": 0.4},
        "credibility_layers": [{"id": "natural", "status": "pending"}],
        "metrics": {
            "mature_deterministic_reuse": 12,
            "mature_qpccd": {"numerator": 12, "denominator": 24, "rate": 0.5},
            "mutation_case_count": 6,
            "mutation_recovered": 6,
            "primary_cross_provider_cases": 12,
            "groq_scout_cases": 6,
            "primary_avoided_tokens_estimate": 18768,
            "groq_scout_avoided_tokens_estimate": 9384,
        },
    }
    snap = BackendSnapshot(base_url="offline", master_mega_evidence=evidence)
    console = Console(record=True, width=160)

    console.print(PageHost().mission_control(snap))
    console.print(PageHost().economy(snap, 0))
    output = console.export_text()

    assert "EVIDENCE RELEASE" in output
    assert "180/450" in output
    assert "DEFINITIVE EVIDENCE" in output
    assert "28,152 estimated" in output


def test_common_tui_cards_have_normalized_heights():
    card = metric("Providers", 3, "routes")

    assert card.height == METRIC_CARD_HEIGHT
    header_tile = BeastHeader()._tile("Gateway", "G", "OK", "OK")
    assert header_tile.height == HEADER_TILE_HEIGHT


def test_litellm_models_table_shows_names_and_headers():
    table = PageHost().deployment(
        BackendSnapshot(
            base_url="offline",
            litellm_models=[
                {"model_name": "qwen-tiny", "litellm_params": {"model": "ollama/qwen2.5:0.5b", "api_base": "http://127.0.0.1:11434"}},
            ],
        ),
        0,
    )
    console = Console(record=True, width=150)
    console.print(table)
    output = console.export_text()

    assert "Model" in output
    assert "Provider route" in output
    assert "qwen-tiny" in output
    assert "ollama/qwen2.5:0.5b" in output


def test_structured_payload_renders_tables_instead_of_json():
    renderable = structured_payload({
        "status": "ready",
        "provider": "groq",
        "metrics": {"samples": 2, "clean_rate": 0.5},
        "models": [{"model": "llama", "score": 0.75}],
    })
    console = Console(record=True, width=100)
    console.print(renderable)
    output = console.export_text()

    assert "Summary" in output
    assert "Metrics" in output
    assert "Models" in output
    assert '"provider": "groq"' not in output


@pytest.mark.asyncio
async def test_snapshot_fetches_intelligence_and_economist_state(monkeypatch):
    client = BeastApiClient("http://localhost:8000")

    async def health(path):
        return "OK", {"status": "healthy"}

    async def get_json(path, params=None):
        responses = {
            "/edgek/providers/registry": {"providers": [{"provider_id": "demo", "backend": "openai_compatible"}]},
            "/edgek/chronicle": {"chronicles": [{
                "provider": "demo", "status": "completed", "recommended_role": "candidate_patch_provider",
                "latency_ms": 50, "hidden_clean": True, "route_confidence": "high",
            }]},
            "/edgek/meta-tool-commons": {"evidence_count": 4, "candidate_count": 1, "adopted_count": 0},
            "/edgek/capability-exchange": {"enabled": False},
            "/edgek/connectors/otel": {"configured": True},
            "/edgek/plugins": {"count": 2, "plugins": []},
            "/edgek/compute": {"mode": "shadow", "enforcing": False},
            "/edgek/compute/metrics": {"sample_size": 2, "observed_total_tokens": 50},
        }
        return responses.get(path, {})

    async def post_json(path, payload=None):
        responses = {
            "/edgek/session/handshake": {
                "beast_object_type": "beast_session_handshake",
                "latency_budget": {"preflight_budget_ms": 500, "scout_budget_ms": 300},
            },
            "/edgek/meta-tool-commons/rank": {"count": 1, "rankings": [{"capability_id": "demo_tool"}]},
            "/edgek/tool-laziness/recommend-tools": {"summary": {"skip_count": 1, "learn_more_count": 0}},
            "/edgek/provider-economist/select": {
                "decision": "route_selected", "requested_role": "primary_patch_provider",
                "selected": {"provider": "demo"},
            },
        }
        return responses.get(path, {})

    async def get_text(path, params=None):
        return ""

    def local_commons():
        return {
            "state": {"evidence_count": 518, "candidate_count": 20, "adopted_count": 0},
            "evidence_plane": {
                "beast_object_type": "meta_tool_commons_evidence_plane",
                "plane_count": 2,
                "evidence_count": 518,
                "plane_hash": "sha256:local",
                "planes": [
                    {"plane": "swarm", "evidence_count": 500, "verified_rate": 1.0, "useful_rate": 1.0, "safe_rate": 1.0},
                    {"plane": "other", "evidence_count": 18, "verified_rate": 1.0, "useful_rate": 1.0, "safe_rate": 1.0},
                ],
            },
            "latest_artifact_plane": {
                "beast_object_type": "meta_tool_commons_evidence_plane",
                "plane_count": 1,
                "evidence_count": 1,
                "artifact_path": "benchmarks/results/latest/reuse_evidence_plane.json",
                "planes": [
                    {"plane": "kv_cache", "evidence_count": 1, "verified_rate": 1.0, "useful_rate": 1.0, "safe_rate": 1.0},
                ],
            },
            "candidates": {
                "candidates": [
                    {"candidate_id": "commons_swarm", "name": "swarm_hermes_route_role_briefs", "source": "local_swarm_commons"},
                ],
            },
            "swarm_state": {"runs": 278, "statuses": {"ready": 277}, "role_events": {"hermes": 216}},
            "swarm_runs": {"runs": [{"run_id": "run_1", "status": "ready"}]},
        }

    monkeypatch.setattr(client, "_health_json", health)
    monkeypatch.setattr(client, "get_json", get_json)
    monkeypatch.setattr(client, "post_json", post_json)
    monkeypatch.setattr(client, "get_text", get_text)
    monkeypatch.setattr("app.cli.api.load_local_commons_snapshot", local_commons)
    monkeypatch.setattr("app.cli.api.load_local_compute_snapshot", lambda: {})

    snap = await client.snapshot()

    assert snap.session_handshake["beast_object_type"] == "beast_session_handshake"
    assert snap.commons_state["evidence_count"] == 518
    assert snap.commons_ranking["count"] == 1
    assert snap.tool_laziness["summary"]["skip_count"] == 1
    assert snap.provider_economist["selected"]["provider"] == "demo"
    assert snap.otel_state["configured"] is True
    assert snap.plugins_state["count"] == 2
    assert snap.compute_state["mode"] == "shadow"
    assert snap.compute_metrics["sample_size"] == 2
    swarm = snap.swarm_summary()
    assert swarm["runs"] == 278
    assert swarm["commons_prepared"] == 500
    assert swarm["commons_candidate_queue"] == 1
    assert swarm["evidence_plane_total"] == 519
    assert swarm["kv_cache_blocks"] == 1


@pytest.mark.asyncio
async def test_snapshot_suppresses_commons_404_when_local_fallback_exists(monkeypatch):
    client = BeastApiClient("http://localhost:8000")

    async def health(path):
        return "OK", {"status": "healthy"}

    async def get_json(path, params=None):
        if path == "/edgek/meta-tool-commons/evidence-plane":
            raise RuntimeError("404 Not Found")
        return {}

    async def post_json(path, payload=None):
        if path == "/edgek/meta-tool-commons/swarm-ingest":
            raise RuntimeError("404 Not Found")
        return {}

    async def get_text(path, params=None):
        return ""

    def local_commons():
        return {
            "state": {"evidence_count": 12, "candidate_count": 1, "adopted_count": 0},
            "evidence_plane": {
                "beast_object_type": "meta_tool_commons_evidence_plane",
                "plane_count": 1,
                "evidence_count": 12,
                "plane_hash": "sha256:local",
                "planes": [{"plane": "swarm", "evidence_count": 12, "verified_rate": 1.0}],
            },
        }

    monkeypatch.setattr(client, "_health_json", health)
    monkeypatch.setattr(client, "get_json", get_json)
    monkeypatch.setattr(client, "post_json", post_json)
    monkeypatch.setattr(client, "get_text", get_text)
    monkeypatch.setattr("app.cli.api.load_local_commons_snapshot", local_commons)
    monkeypatch.setattr("app.cli.api.load_local_compute_snapshot", lambda: {})
    monkeypatch.setattr("app.cli.api.load_local_litellm_config", lambda: {})

    snap = await client.snapshot()

    assert snap.commons_evidence_plane["evidence_count"] == 12
    assert snap.commons_swarm_ingest["prepared"] == 12
    assert "commons_evidence_plane" not in snap.errors
    assert "commons_swarm_ingest" not in snap.errors


@pytest.mark.asyncio
async def test_snapshot_suppresses_commons_405s_and_reports_full_local_ingestion(monkeypatch):
    client = BeastApiClient("http://localhost:8000")

    async def health(path):
        return "OK", {"status": "healthy"}

    async def get_json(path, params=None):
        if path in {"/edgek/kv-cache/state", "/edgek/meta-tool-commons/candidates"}:
            raise RuntimeError("405 Method Not Allowed")
        return {}

    async def post_json(path, payload=None):
        if path in {"/edgek/meta-tool-commons/swarm-candidates", "/edgek/meta-tool-commons/kv-cache-ingest"}:
            raise RuntimeError("405 Method Not Allowed")
        return {}

    async def get_text(path, params=None):
        return ""

    def local_commons():
        return {
            "state": {"evidence_count": 40, "candidate_count": 3, "adopted_count": 1},
            "evidence_plane": {
                "beast_object_type": "meta_tool_commons_evidence_plane",
                "plane_count": 2,
                "evidence_count": 40,
                "plane_hash": "sha256:local",
                "candidate_summary": {
                    "local_swarm_commons": {"proposed": 1},
                    "discovery_mcp_tool_catalog": {"proposed": 2},
                },
                "planes": [
                    {"plane": "swarm", "evidence_count": 12, "verified_rate": 1.0},
                    {"plane": "kv_cache", "evidence_count": 4, "verified_rate": 1.0},
                ],
            },
            "candidates": {
                "candidates": [
                    {"candidate_id": "swarm_recipe", "name": "swarm_recipe", "source": "local_swarm_commons", "kind": "skill_recipe", "status": "proposed"},
                    {"candidate_id": "mcp_tool", "name": "repo_symbol_search", "source": "discovery_mcp_tool_catalog", "kind": "meta_tool", "status": "proposed"},
                    {"candidate_id": "skill_manifest", "name": "review_skill", "source": "discovery_skill_manifest", "kind": "skill_recipe", "status": "proposed"},
                ],
            },
            "swarm_candidates": {"proposed_count": 1, "skipped_count": 0},
            "kv_cache_state": {"beast_object_type": "kv_cache_transport_stats", "total_blocks": 2, "operations_logged": 7},
            "kv_cache_ingest": {"beast_object_type": "meta_tool_commons_kv_cache_ingest", "prepared": 1, "accepted": 1},
        }

    monkeypatch.setattr(client, "_health_json", health)
    monkeypatch.setattr(client, "get_json", get_json)
    monkeypatch.setattr(client, "post_json", post_json)
    monkeypatch.setattr(client, "get_text", get_text)
    monkeypatch.setattr("app.cli.api.load_local_commons_snapshot", local_commons)
    monkeypatch.setattr("app.cli.api.load_local_compute_snapshot", lambda: {})
    monkeypatch.setattr("app.cli.api.load_local_litellm_config", lambda: {})

    snap = await client.snapshot()
    summary = snap.swarm_summary()

    assert summary["commons_candidate_queue"] == 3
    assert summary["commons_candidate_sources"]["discovery_mcp_tool_catalog"] == 2
    assert summary["kv_cache_blocks"] == 4
    assert summary["kv_cache_prepared"] == 4
    assert "commons_swarm_candidates" not in snap.errors
    assert "commons_kv_cache_ingest" not in snap.errors
    assert "commons_candidates" not in snap.errors
    assert "kv_cache_state" not in snap.errors


def test_swarm_page_shows_all_commons_candidate_sources():
    snap = BackendSnapshot(
        base_url="offline",
        commons_evidence_plane={
            "plane_count": 1,
            "evidence_count": 3,
            "candidate_summary": {"discovery_mcp_tool_catalog": {"proposed": 2}},
            "planes": [{"plane": "discovery", "evidence_count": 3, "verified_rate": 1.0, "useful_rate": 1.0, "safe_rate": 1.0}],
        },
        commons_candidates=[
            {"candidate_id": "tool1", "name": "repo_symbol_search", "source": "discovery_mcp_tool_catalog", "kind": "meta_tool", "task_class": "code_navigation", "role": "tool_selector", "risk_class": "low", "status": "proposed"},
        ],
    )
    table = PageHost().swarm(snap, 0)
    console = Console(record=True, width=150)
    console.print(table)
    output = console.export_text()

    assert "COMMONS PROMOTION QUEUE" in output
    assert "repo_symbol_search" in output
    assert "discovery_mcp_tool_catalog" in output


def test_commons_and_kv_tui_routes_accept_get_and_post_aliases():
    client = TestClient(app)

    for path in [
        "/edgek/meta-tool-commons/swarm-ingest",
        "/edgek/meta-tool-commons/swarm-candidates",
        "/edgek/meta-tool-commons/kv-cache-ingest",
        "/edgek/kv-cache/state",
    ]:
        assert client.get(path).status_code != 405
        assert client.post(path, json={}).status_code != 405


@pytest.mark.asyncio
@pytest.mark.parametrize("size", [(82, 28), (150, 42)])
async def test_intelligence_navigation_works_at_narrow_and_wide_sizes(monkeypatch, size):
    async def load_snapshot(self):
        self.snapshot = BackendSnapshot(
            base_url=self.base_url,
            online=True,
            session_handshake={
                "beast_object_type": "beast_session_handshake",
                "latency_budget": {"preflight_budget_ms": 500, "scout_budget_ms": 300},
            },
            commons_state={"evidence_count": 3, "candidate_count": 1, "adopted_count": 0},
            commons_ranking={"count": 1, "rankings": [{"capability_id": "demo", "score": 0.8}]},
        )
        self._sync()

    monkeypatch.setattr(BeastMissionConsole, "fetch_backend", load_snapshot)
    app = BeastMissionConsole(base_url="http://offline")

    async with app.run_test(size=size) as pilot:
        await pilot.press("j")
        await pilot.pause()
        assert app.selected_page == "Intelligence"
        assert app.query_one("#page-host").page == "Intelligence"


@pytest.mark.asyncio
async def test_economy_navigation_and_enter_are_first_class(monkeypatch):
    async def load_snapshot(self):
        self.snapshot = BackendSnapshot(base_url=self.base_url, online=False)
        self._sync()

    calls = []

    async def fake_run_economy_action(self, action=None):
        calls.append(action or self.selected_item().get("action"))

    monkeypatch.setattr(BeastMissionConsole, "fetch_backend", load_snapshot)
    monkeypatch.setattr(BeastMissionConsole, "_run_economy_action", fake_run_economy_action)
    app = BeastMissionConsole(base_url="http://offline")

    async with app.run_test(size=(120, 36)) as pilot:
        await pilot.press("e")
        await pilot.pause()
        assert app.selected_page == "Economy"
        await pilot.press("down")
        await pilot.pause()
        assert app.selected_indices["Economy"] == 1
        await pilot.press("enter")
        await pilot.pause()
        assert calls == ["economy_dashboard"]


def test_inner_menu_arrow_actions_are_clamped_and_predictable():
    palette = CommandPaletteScreen([
        {"id": "one", "label": "One"},
        {"id": "two", "label": "Two"},
    ])
    palette.action_move_down()
    assert palette.index == 1
    palette.action_move_up()
    assert palette.index == 0

    picker = ContextPickerScreen(
        [{"path": "a.py", "size": 1, "ext": ".py"}, {"path": "b.py", "size": 2, "ext": ".py"}],
        [],
    )
    picker.action_move_down()
    assert picker.index == 1
    picker.action_toggle_file()
    assert "b.py" in picker.selected_files
    picker.action_move_down()
    assert picker.index == 1

    diff = DiffPreviewScreen({"operations": [{"op_id": "a"}, {"op_id": "b"}]})
    diff.action_move_down()
    assert diff.index == 1
    diff.action_move_down()
    assert diff.index == 1

    approvals = ApprovalQueueScreen([
        {"plan_id": "p1", "status": "draft", "objective": "one"},
        {"plan_id": "p2", "status": "draft", "objective": "two"},
    ])
    approvals.action_move_up()
    assert approvals.index == 0


def test_tiny_llama_demo_prepares_previewable_case_plan():
    app = BeastMissionConsole(base_url="http://offline")

    demo = app.prepare_tiny_llama_demo()
    result = app._build_tiny_demo_patch_plan()
    diff = BeastApiClient("http://offline").render_patch_diff(result.data)

    assert demo["active"] is True
    assert demo["baseline_failed"] is True
    assert result.ok is True
    assert result.data["kind"] == "tiny_llama_opus_case_study_tui_plan"
    assert len(result.data["operations"]) == 4
    assert result.data["apply_policy"]["run_tests"] is True
    assert result.data["apply_policy"]["test_args"] == ["tests", "-q"]
    assert diff.ok is True
    assert "gateway/config.py" in diff.data["diff"]


def test_tiny_llama_demo_apply_runs_pytest_in_case_root(monkeypatch):
    app = BeastMissionConsole(base_url="http://offline")
    app.prepare_tiny_llama_demo()
    plan = app._build_tiny_demo_patch_plan().data
    client = BeastApiClient("http://offline")

    monkeypatch.setenv("BEAST_PATCH_RUN_TESTS", "1")
    result = client.apply_patch_plan(plan, approved=True)
    rollback = client.rollback_last_patch()

    pytest_checks = [
        item for item in result.data.get("verification", {}).get("checks", [])
        if isinstance(item, dict) and item.get("kind") == "pytest"
    ]
    assert result.ok is True
    assert pytest_checks
    assert pytest_checks[-1]["ok"] is True
    assert pytest_checks[-1]["cwd"] == plan["case_root"]
    assert rollback.ok is True


@pytest.mark.asyncio
async def test_tiny_llama_demo_binding_arms_session(monkeypatch):
    async def load_snapshot(self):
        self.snapshot = BackendSnapshot(base_url=self.base_url, online=False)
        self._sync()

    monkeypatch.setattr(BeastMissionConsole, "fetch_backend", load_snapshot)
    app = BeastMissionConsole(base_url="http://offline")

    async with app.run_test(size=(130, 38)) as pilot:
        await pilot.press("ctrl+t")
        await pilot.pause()

        assert app.tiny_demo["active"] is True
        assert app.selected_page == "Session"
        assert app.session_meta["provider"] == "ollama"


@pytest.mark.asyncio
async def test_lowercase_d_no_longer_triggers_doctor_or_demo(monkeypatch):
    async def load_snapshot(self):
        self.snapshot = BackendSnapshot(base_url=self.base_url, online=False)
        self._sync()

    calls = []

    def fake_doctor(self):
        calls.append("doctor")

    monkeypatch.setattr(BeastMissionConsole, "fetch_backend", load_snapshot)
    monkeypatch.setattr(BeastMissionConsole, "action_doctor", fake_doctor)
    app = BeastMissionConsole(base_url="http://offline")

    async with app.run_test(size=(130, 38)) as pilot:
        await pilot.press("d")
        await pilot.pause()

        assert calls == []
        assert app.tiny_demo["active"] is False


@pytest.mark.asyncio
async def test_session_number_key_navigates_without_stealing_start_key(monkeypatch):
    async def load_snapshot(self):
        self.snapshot = BackendSnapshot(base_url=self.base_url, online=False)
        self._sync()

    started = []

    async def fake_start(self):
        started.append(True)
        self.session_meta["state"] = "active"

    monkeypatch.setattr(BeastMissionConsole, "fetch_backend", load_snapshot)
    monkeypatch.setattr(BeastMissionConsole, "_start_live_session", fake_start)
    app = BeastMissionConsole(base_url="http://offline")

    async with app.run_test(size=(130, 38)) as pilot:
        await pilot.press("2")
        await pilot.pause()
        assert app.selected_page == "Session"
        assert app.input_mode is False

        await pilot.press("s")
        await pilot.pause()
        assert started == [True]


@pytest.mark.asyncio
async def test_header_has_enough_height_for_bottom_borders(monkeypatch):
    async def load_snapshot(self):
        self.snapshot = BackendSnapshot(base_url=self.base_url, online=False)
        self._sync()

    monkeypatch.setattr(BeastMissionConsole, "fetch_backend", load_snapshot)
    app = BeastMissionConsole(base_url="http://offline")

    async with app.run_test(size=(190, 42)) as pilot:
        await pilot.pause()
        header = app.query_one("#beast-header")
        assert int(header.styles.height.value) >= 16


@pytest.mark.asyncio
async def test_context_picker_key_events_move_and_toggle():
    class FakeKey:
        def __init__(self, key, character=None):
            self.key = key
            self.character = character
            self.stopped = False

        def stop(self):
            self.stopped = True

    picker = ContextPickerScreen(
        [{"path": "a.py", "size": 1, "ext": ".py"}, {"path": "b.py", "size": 2, "ext": ".py"}],
        [],
    )

    down = FakeKey("down")
    await picker.on_key(down)
    assert down.stopped is True
    assert picker.index == 1

    enter = FakeKey("enter")
    await picker.on_key(enter)
    assert enter.stopped is True
    assert "b.py" in picker.selected_files

    up = FakeKey("up")
    await picker.on_key(up)
    assert up.stopped is True
    assert picker.index == 0

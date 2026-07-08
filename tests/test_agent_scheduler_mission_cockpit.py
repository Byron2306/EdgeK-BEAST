import pytest
from httpx import ASGITransport, AsyncClient

from app.cli.api import BeastApiClient
from app.main import app
from app.kernel.compute.agent_scheduler import AgentScheduler
from app.kernel.workspaces.mission_cockpit import MissionCockpit
from app.mcp.runtime import BeastToolRuntime


def test_agent_scheduler_prefers_local_lanes_and_records_summary(tmp_path):
    scheduler = AgentScheduler(tmp_path)

    plan = scheduler.plan(
        objective="Investigate route handling",
        phase="scout",
        risk="low",
    )
    summary = scheduler.summary()

    lane_ids = [lane["lane_id"] for lane in plan["selected_lanes"]]
    assert "local_cpu_scout" in lane_ids
    assert "code_cortex_retriever" in lane_ids
    assert plan["receipt"]["local_first"] is True
    assert summary["recent_count"] == 1
    assert summary["local_lane_total"] >= 1
    assert plan["route_inputs"]["beast_object_type"] == "beast_agent_scheduler_route_inputs"
    assert "adaptive_dispatcher" in plan["route_inputs"]
    assert "inference_engine_fabric" in plan["route_inputs"]
    assert "capability_plane" in plan["route_inputs"]
    assert plan["route_inputs"]["capability_plane"]["source"] == "capability_plane"


def test_agent_scheduler_escalates_for_low_confidence_implementation(tmp_path):
    scheduler = AgentScheduler(tmp_path)

    plan = scheduler.plan(
        objective="Implement risky edit",
        phase="implementer",
        risk="medium",
        graph_confidence=0.1,
        provider_fitness=0.7,
    )

    lane_ids = [lane["lane_id"] for lane in plan["selected_lanes"]]
    assert "provider_implementer" in lane_ids
    assert plan["receipt"]["cloud_lane_count"] >= 1


def test_agent_scheduler_uses_legacy_route_inputs_as_advisory_signals(tmp_path):
    scheduler = AgentScheduler(tmp_path)
    route_inputs = scheduler.collect_route_inputs(
        objective="Implement with local route signal",
        phase="implementer",
        risk="medium",
        provider_fitness=0.7,
        crystal_match=True,
    )

    plan = scheduler.plan(
        objective="Implement with local route signal",
        phase="implementer",
        risk="medium",
        graph_confidence=0.9,
        provider_fitness=0.7,
        crystal_match=True,
        route_inputs={
            **route_inputs,
            "local_route_optimizer": {
                **route_inputs["local_route_optimizer"],
                "recommended_engine": "ollama",
            },
        },
    )

    lane_ids = [lane["lane_id"] for lane in plan["selected_lanes"]]
    assert "crystal_replay" in lane_ids
    assert "local_verifier" in lane_ids
    assert plan["receipt"]["route_inputs"]["provider_economist"]["escalation_signal"] is True


def test_sourceplan_scorecard_carries_agent_scheduler_plan(tmp_path):
    (tmp_path / "app.py").write_text("value = 'old'\n", encoding="utf-8")
    client = BeastApiClient("http://offline", workspace=tmp_path)
    plan = {
        "kind": "beast_source_patch_plan",
        "objective": "Update value",
        "operations": [{
            "id": "op1",
            "path": "app.py",
            "op": "replace_exact",
            "old_text": "old",
            "new_text": "new",
            "selected": True,
        }],
    }

    scorecard = client.sourceplan_scorecard(plan).data

    assert scorecard["agent_scheduler"]["beast_object_type"] == "beast_agent_schedule_plan"
    assert scorecard["agent_scheduler"]["receipt"]["selected_lanes"]


def test_mission_cockpit_summary_aggregates_cards(tmp_path):
    (tmp_path / "AGENTS.md").write_text("- Always run pytest.\n", encoding="utf-8")
    patch_dir = tmp_path / ".beast" / "patch_plans"
    evidence_dir = tmp_path / ".beast" / "evidence" / "sourceplan"
    patch_dir.mkdir(parents=True)
    evidence_dir.mkdir(parents=True)
    (patch_dir / "plan_demo.json").write_text('{"plan_id": "plan_demo", "status": "draft_requires_approval"}', encoding="utf-8")
    (evidence_dir / "plan_demo.json").write_text('{"beast_object_type": "sourceplan_unified_evidence_packet", "plan_id": "plan_demo", "evidence_hash": "sha256:x"}', encoding="utf-8")
    lattice_dir = tmp_path / ".beast" / "compute" / "mission_lattice"
    lattice_dir.mkdir(parents=True)
    (lattice_dir / "cells.json").write_text('[{"cell_id": "mcl_demo", "verification_ok": true, "promotion_candidate": false}]', encoding="utf-8")
    summary = MissionCockpit(tmp_path).summary(objective="Review mission", phase="reviewer", risk="high")

    card_ids = {card["card_id"] for card in summary["cards"]}
    assert summary["beast_object_type"] == "beast_mission_cockpit_summary"
    assert {"mode", "worktrees", "safety", "spec", "compute", "mission_lattice", "code_cortex", "sourceplans", "evidence", "reintegration"}.issubset(card_ids)
    assert "capability_plane" in card_ids
    assert summary["mode_route"]["selected_mode"] == "reviewer"
    assert summary["mission_lattice"]["cell_count"] == 1
    assert summary["reintegration_health"]["beast_object_type"] == "beast_reintegration_health"
    assert "missing_types" in summary["reintegration_health"]["evidence_coverage"]
    assert summary["sourceplan_queue"][0]["plan_id"] == "plan_demo"
    assert summary["evidence_stream"][0]["plan_id"] == "plan_demo"


def test_mcp_exposes_scheduler_and_cockpit_in_readonly(monkeypatch, tmp_path):
    monkeypatch.setenv("BEAST_MCP_TOOLS", "readonly")
    runtime = BeastToolRuntime()
    names = {tool["name"] for tool in runtime.tool_definitions()}

    result = runtime.call_tool(
        "beast_agent_scheduler_plan",
        {"objective": "Scout repo", "workspace_root": str(tmp_path), "phase": "scout"},
    )
    cockpit = runtime.call_tool(
        "beast_mission_cockpit_summary",
        {"workspace_root": str(tmp_path), "objective": "Scout repo", "phase": "scout"},
    )
    lattice = runtime.call_tool(
        "beast_mission_lattice_summary",
        {"workspace_root": str(tmp_path), "limit": 3},
    )

    assert "beast_agent_scheduler_plan" in names
    assert "beast_agent_scheduler_summary" in names
    assert "beast_mission_cockpit_summary" in names
    assert "beast_mission_lattice_summary" in names
    assert "beast_mission_lattice_lookup" in names
    assert "beast_mission_lattice_replay_scaffold" in names
    assert result["receipt"]["local_first"] is True
    assert cockpit["beast_object_type"] == "beast_mission_cockpit_summary"
    assert lattice["beast_object_type"] == "mission_crystal_lattice_summary"


@pytest.mark.asyncio
async def test_modular_cockpit_router_serves_mission_lattice_replay_endpoint(tmp_path):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/edgek/mission-lattice/replay-scaffold",
            json={
                "root_path": str(tmp_path),
                "plan": {
                    "plan_id": "route_replay_probe",
                    "objective": "Probe modular cockpit route",
                    "operations": [],
                },
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["beast_object_type"] == "mission_lattice_replay_closure"
    assert payload["no_auto_apply"] is True


@pytest.mark.asyncio
async def test_modular_sourceplan_compute_workspace_commons_routes_are_mounted(tmp_path):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        sourceplan = await client.post(
            "/edgek/sourceplan/scorecard",
            json={"root_path": str(tmp_path), "plan": {"plan_id": "empty", "operations": []}},
        )
        compute = await client.get("/edgek/compute/metrics")
        workspace = await client.get("/edgek/code-cortex/status", params={"root_path": str(tmp_path)})
        context = await client.post("/edgek/workspace/context", json={"root_path": str(tmp_path), "objective": "inspect routes"})
        commons = await client.get("/edgek/meta-tool-commons")

    assert sourceplan.status_code == 200
    assert sourceplan.json()["beast_object_type"] == "sourceplan_preapply_scorecard"
    assert compute.status_code == 200
    assert workspace.status_code == 200
    assert context.status_code == 200
    assert context.json()["context_front_door"] == "code_cortex"
    assert commons.status_code == 200


def test_modularized_routes_are_not_active_duplicates():
    seen = {}
    duplicates = []
    for route in app.router.routes:
        methods = tuple(sorted(getattr(route, "methods", []) or []))
        key = (getattr(route, "path", ""), methods)
        if key in seen:
            duplicates.append(key)
        seen[key] = route
    watched = {
        "/edgek/sourceplan/scorecard",
        "/edgek/compute/metrics",
        "/edgek/workspace/context",
        "/edgek/meta-tool-commons",
        "/edgek/mission-lattice/replay-scaffold",
    }
    assert not [key for key in duplicates if key[0] in watched]


def test_modularized_route_families_own_active_paths():
    expected_modules = {
        "/edgek/sourceplan/scorecard": "app.routes.sourceplan",
        "/edgek/compute/metrics": "app.routes.compute",
        "/edgek/workspace/context": "app.routes.workspace",
        "/edgek/meta-tool-commons": "app.routes.commons",
        "/edgek/mission-lattice/replay-scaffold": "app.routes.cockpit",
        "/edgek/mode-router/catalog": "app.routes.policy",
    }
    active = {
        getattr(route, "path", ""): getattr(getattr(route, "endpoint", None), "__module__", "")
        for route in app.router.routes
    }
    for path, module_name in expected_modules.items():
        assert active[path] == module_name

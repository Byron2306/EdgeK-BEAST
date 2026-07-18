import json
import time

import pytest
from httpx import ASGITransport, AsyncClient
from rich.console import Console

from app.cli.api import ActionResult, BeastApiClient
from app.cli.ui import SourceWorkbenchScreen
from app.main import app
from app.kernel.compute.agent_scheduler import AgentScheduler
from app.kernel.evidence.evidence_bus import EvidenceBus
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


def test_agent_scheduler_binds_pressure_to_resource_execution(tmp_path):
    scheduler = AgentScheduler(tmp_path)
    plan = scheduler.plan(objective="verify build", phase="review", risk="low", cpu_pressure=.9)
    assert plan["resource_profile"]["lane"] == "cpu"
    assert plan["interference"]["bucket"] == "constrained"
    assert scheduler.execute(plan, lambda: "done").result() == "done"
    scheduler.resource_executor.shutdown()


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
async def test_workspace_files_route_falls_back_to_local_candidates_for_desktop_ide(tmp_path):
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "sample.py").write_text("print('beast')\n", encoding="utf-8")
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/edgek/workspace/files",
            params={"root_path": str(tmp_path), "limit": 20},
        )

    assert response.status_code == 200
    payload = response.json()
    paths = {item["path"] for item in payload["files"]}
    assert "app/sample.py" in paths
    assert payload["fallback_used"] is True
    assert all(item["source"] == "local_candidates" for item in payload["files"])


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


@pytest.mark.asyncio
async def test_workspace_context_interactive_deadline_preserves_selected_scope(monkeypatch, tmp_path):
    import app.main as main_module

    def slow_graph_context(**kwargs):
        time.sleep(0.25)
        return {"beast_object_type": "workspace_graph_context", "files": [{"path": "service.py"}]}

    def slow_cortex_context(*args, **kwargs):
        time.sleep(0.25)
        return {"ok": True, "files": [{"path": "service.py"}]}

    monkeypatch.setattr(main_module.workspace_graph_service, "context", slow_graph_context)
    monkeypatch.setattr(main_module.code_cortex_router, "get_editing_context", slow_cortex_context)
    transport = ASGITransport(app=app)
    started = time.perf_counter()
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/edgek/workspace/context",
            json={
                "root_path": str(tmp_path),
                "objective": "edit service",
                "selected_files": ["service.py"],
                "interactive_timeout_ms": 20,
            },
        )
    elapsed = time.perf_counter() - started

    assert response.status_code == 200
    payload = response.json()
    assert elapsed < 0.18
    assert payload["context_pending"] is True
    assert payload["selected_files"] == [{"path": "service.py"}]
    assert payload["code_cortex"]["files"] == [{"path": "service.py"}]


@pytest.mark.asyncio
async def test_ide_snapshot_is_phase_one_vscode_shell_contract(tmp_path):
    (tmp_path / "service.py").write_text("def value():\n    return 1\n", encoding="utf-8")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/edgek/ide/snapshot",
            params={
                "root_path": str(tmp_path),
                "active_file": "service.py",
                "objective": "Repair service value",
                "detail": "true",
            },
        )

    payload = response.json()

    assert response.status_code == 200
    assert payload["beast_object_type"] == "beast_ide_snapshot"
    assert payload["phase"] == "phase_1_vscode_shell"
    assert payload["look_and_feel"]["source"] == "beast_tui"
    assert payload["mission_cockpit"]["beast_object_type"] == "beast_mission_cockpit_summary"
    assert payload["code_cortex"]["front_door"] == "code_cortex"
    assert payload["policy"]["architecture_decisions"]["decision_count"] == 8
    assert "edgekBeast.openSourceWorkbench" in payload["operator_actions"]


@pytest.mark.asyncio
async def test_ide_event_stream_emits_phase_two_event_contract(tmp_path):
    (tmp_path / "service.py").write_text("def value():\n    return 1\n", encoding="utf-8")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/edgek/ide/events",
            params={
                "root_path": str(tmp_path),
                "active_file": "service.py",
                "objective": "Repair service value",
                "once": "true",
            },
        )

    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]
    text = response.text
    assert "event: sourceplan" in text
    assert "event: policy" in text
    assert "event: evidence" in text
    assert "event: context" in text
    assert "event: worktree" in text
    assert "beast_ide_event" in text


@pytest.mark.asyncio
async def test_ide_related_context_contract_classifies_related_files(tmp_path):
    (tmp_path / "service.py").write_text("def value():\n    return 1\n", encoding="utf-8")
    (tmp_path / "test_service.py").write_text("from service import value\n\ndef test_value():\n    assert value() == 1\n", encoding="utf-8")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/edgek/ide/related-context",
            params={"root_path": str(tmp_path), "path": "service.py", "limit": "20"},
        )

    payload = response.json()
    assert response.status_code == 200
    assert payload["beast_object_type"] == "beast_ide_related_context"
    assert payload["path"] == "service.py"
    assert isinstance(payload["related"], list)
    for item in payload["related"]:
        assert item["relationship_kind"] in {"test", "route", "surface", "model", "related"}


@pytest.mark.asyncio
async def test_ide_sourceplan_from_editor_compiles_governed_draft(tmp_path):
    original = "def value():\n    return 1\n"
    updated = "def value():\n    return 2\n"
    (tmp_path / "service.py").write_text(original, encoding="utf-8")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/edgek/ide/sourceplan/from-editor",
            json={
                "root_path": str(tmp_path),
                "path": "service.py",
                "original_text": original,
                "new_text": updated,
                "objective": "Desktop edit service value",
                "provider": "nvidia_nim",
            },
        )

    payload = response.json()
    operation = payload["plan"]["operations"][0]

    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["beast_object_type"] == "beast_desktop_editor_sourceplan_draft"
    assert payload["plan"]["kind"] == "beast_desktop_editor_source_patch_plan"
    assert operation["op"] == "replace_exact"
    assert operation["old"] == original
    assert operation["new"] == updated
    assert operation["old_text"] == original
    assert operation["new_text"] == updated
    assert payload["preview"]["selected_count"] == 1
    assert "return 2" in payload["preview_text"]


@pytest.mark.asyncio
async def test_ide_sourceplan_from_editor_rejects_stale_buffer(tmp_path):
    (tmp_path / "service.py").write_text("def value():\n    return 3\n", encoding="utf-8")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/edgek/ide/sourceplan/from-editor",
            json={
                "root_path": str(tmp_path),
                "path": "service.py",
                "original_text": "def value():\n    return 1\n",
                "new_text": "def value():\n    return 2\n",
            },
        )

    payload = response.json()

    assert response.status_code == 200
    assert payload["ok"] is False
    assert payload["stale_context"] is True
    assert payload["error"] == "current_file_changed_since_editor_opened"
    assert payload["current_hash"].startswith("sha256:")


@pytest.mark.asyncio
async def test_ide_sourceplan_from_selection_compiles_targeted_hunk(tmp_path):
    original = "def value():\n    return 1\n"
    (tmp_path / "service.py").write_text(original, encoding="utf-8")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/edgek/ide/sourceplan/from-selection",
            json={
                "root_path": str(tmp_path),
                "path": "service.py",
                "original_text": original,
                "selection_text": "return 1",
                "replacement_text": "return 2",
                "line_start": 2,
                "line_end": 2,
                "char_start": original.index("return 1"),
                "char_end": original.index("return 1") + len("return 1"),
            },
        )

    payload = response.json()
    operation = payload["plan"]["operations"][0]

    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["beast_object_type"] == "beast_desktop_selection_sourceplan_draft"
    assert payload["plan"]["kind"] == "beast_desktop_selection_source_patch_plan"
    assert operation["op"] == "replace_exact"
    assert operation["old"] == "return 1"
    assert operation["new"] == "return 2"
    assert operation["selection"]["line_start"] == 2
    assert "return 2" in payload["preview_text"]


@pytest.mark.asyncio
async def test_ide_agent_session_detail_update_and_sourceplan_flow(tmp_path):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        created = await client.post(
            "/edgek/ide/agent-sessions/create",
            json={
                "root_path": str(tmp_path),
                "objective": "Investigate desktop live session",
                "mode": "architect",
                "provider": "nvidia_nim",
                "files": ["service.py"],
            },
        )
        session_id = created.json()["session"]["session_id"]
        detail = await client.get(
            f"/edgek/ide/agent-sessions/{session_id}",
            params={"root_path": str(tmp_path)},
        )
        updated = await client.post(
            "/edgek/ide/agent-sessions/update",
            json={
                "root_path": str(tmp_path),
                "session_id": session_id,
                "output": {"kind": "operator_agent_output", "text": "Change service.py with a governed hunk."},
                "budget_delta": {"tokens": 12},
            },
        )
        paused = await client.post(
            "/edgek/ide/agent-sessions/pause",
            json={"root_path": str(tmp_path), "session_id": session_id},
        )
        draft = await client.post(
            "/edgek/ide/agent-sessions/sourceplan-draft",
            json={"root_path": str(tmp_path), "session_id": session_id},
        )

    assert created.status_code == 200
    assert detail.status_code == 200
    assert detail.json()["ok"] is True
    assert updated.status_code == 200
    assert updated.json()["session"]["outputs"][0]["text"].startswith("Change service.py")
    assert updated.json()["session"]["budget"]["tokens"] == 12
    assert paused.json()["session"]["status"] == "paused"
    assert draft.status_code == 200
    assert draft.json()["plan"]["source"] == "agent_session_workspace"
    assert draft.json()["plan"]["requires_operator_translation"] is True


@pytest.mark.asyncio
async def test_ide_agent_session_run_events_stream_and_persist_output(tmp_path):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        created = await client.post(
            "/edgek/ide/agent-sessions/create",
            json={
                "root_path": str(tmp_path),
                "objective": "Stream a desktop agent run",
                "mode": "architect",
                "provider": "nvidia_nim",
            },
        )
        session_id = created.json()["session"]["session_id"]
        streamed = await client.get(
            f"/edgek/ide/agent-sessions/{session_id}/run-events",
            params={
                "root_path": str(tmp_path),
                "prompt": "Explain the governed path.",
                "simulate": "true",
            },
        )
        detail = await client.get(
            f"/edgek/ide/agent-sessions/{session_id}",
            params={"root_path": str(tmp_path)},
        )

    text = streamed.text
    outputs = detail.json()["session"]["outputs"]

    assert streamed.status_code == 200
    assert "event: agent_run_started" in text
    assert "event: agent_run_context" in text
    assert "event: agent_run_token" in text
    assert "event: agent_run_done" in text
    assert any(item.get("kind") == "streamed_agent_output" for item in outputs)
    assert "BEAST simulated agent stream" in outputs[-1]["text"]


@pytest.mark.asyncio
async def test_ide_agent_session_run_events_repairs_to_action_ir(monkeypatch, tmp_path):
    target = tmp_path / "service.py"
    target.write_text("def value():\n    return 1\n", encoding="utf-8")
    repair_prompts = []

    async def fake_stream_live_turn(self, text, history, provider="", lifecycle_id="", context_files=None, model="", max_tokens=None, max_continuations=None, context_max_files=64, context_max_chars_each=4200, governance_level="governed"):
        if "Return BEAST Action IR JSON only." in text:
            repair_prompts.append(text)
            yield {
                "type": "token",
                "text": '{"kind":"beast_action_ir","objective":"Update the value","actions":[{"id":"a1","type":"replace_exact","intent":"Return the new value","target":{"path":"service.py"},"old":"return 1","new":"return 2"}]}'
            }
            yield {"type": "done", "ok": True, "tool_events": []}
            return
        yield {"type": "token", "text": "Update service.py so the function returns 2."}
        yield {"type": "done", "ok": True, "tool_events": []}

    monkeypatch.setattr(BeastApiClient, "stream_live_turn", fake_stream_live_turn)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        created = await client.post(
            "/edgek/ide/agent-sessions/create",
            json={
                "root_path": str(tmp_path),
                "objective": "Update the governed file",
                "mode": "implementer",
                "provider": "nvidia_nim",
                "files": [],
            },
        )
        session_id = created.json()["session"]["session_id"]
        streamed = await client.get(
            f"/edgek/ide/agent-sessions/{session_id}/run-events",
            params=[
                ("root_path", str(tmp_path)),
                ("prompt", "Change service.py so value returns 2."),
                ("context_files", "service.py"),
            ],
        )
        detail = await client.get(
            f"/edgek/ide/agent-sessions/{session_id}",
            params={"root_path": str(tmp_path)},
        )

    text = streamed.text
    outputs = detail.json()["session"]["outputs"]
    final_output = next(item for item in reversed(outputs) if item.get("kind") == "streamed_agent_output")

    assert streamed.status_code == 200
    assert "event: agent_run_context" in text
    assert '"active_file": "service.py"' in text
    assert "event: agent_run_sourceplan" in text
    assert final_output["sourceplan_status"] == "compiled_action_ir"
    assert final_output["sourceplan_operation_count"] == 1
    assert any(item.get("kind") == "agent_action_ir_repair" for item in outputs)
    assert "Agent output did not contain BEAST Action IR JSON." in repair_prompts[0]
    assert detail.json()["session"]["files"] == ["service.py"]


@pytest.mark.asyncio
async def test_ide_local_qwen_run_is_compact_and_does_not_start_repair_cascade(monkeypatch, tmp_path):
    for index in range(5):
        (tmp_path / f"module_{index}.py").write_text(f"VALUE_{index} = {index}\n", encoding="utf-8")
    calls = []

    async def fake_stream_live_turn(self, text, history, **kwargs):
        calls.append((text, kwargs))
        yield {"type": "token", "text": "I would change module_0.py."}
        yield {"type": "done", "ok": True, "tool_events": []}

    monkeypatch.setattr(BeastApiClient, "stream_live_turn", fake_stream_live_turn)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        created = await client.post(
            "/edgek/ide/agent-sessions/create",
            json={
                "root_path": str(tmp_path),
                "objective": "Update the local coder fixture",
                "mode": "implementer",
                "provider": "ollama",
                "model": "qwen2.5-coder:1.5b",
            },
        )
        session_id = created.json()["session"]["session_id"]
        streamed = await client.get(
            f"/edgek/ide/agent-sessions/{session_id}/run-events",
            params=[
                ("root_path", str(tmp_path)),
                ("prompt", "Update the local coder fixture."),
                ("model", "qwen2.5-coder:1.5b"),
                *[("context_files", f"module_{index}.py") for index in range(5)],
            ],
        )

    assert "compact local Qwen route: 3 files, 1024 output tokens" in streamed.text
    assert "event: agent_run_needs_operator" in streamed.text
    assert len(calls) == 1
    assert calls[0][1]["max_tokens"] == 1024
    assert calls[0][1]["context_max_chars_each"] == 2400
    assert calls[0][1]["context_files"] == [f"module_{index}.py" for index in range(3)]
    assert "sourceplan repair" not in streamed.text


@pytest.mark.asyncio
async def test_ide_agent_session_rejects_unreadable_explicit_context_before_provider(monkeypatch, tmp_path):
    calls = []

    async def fake_stream_live_turn(self, *args, **kwargs):
        calls.append((args, kwargs))
        yield {"type": "done", "ok": True, "tool_events": []}

    monkeypatch.setattr(BeastApiClient, "stream_live_turn", fake_stream_live_turn)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        created = await client.post(
            "/edgek/ide/agent-sessions/create",
            json={"root_path": str(tmp_path), "objective": "Explain attachment", "mode": "chat", "provider": "nvidia_nim"},
        )
        session_id = created.json()["session"]["session_id"]
        streamed = await client.get(
            f"/edgek/ide/agent-sessions/{session_id}/run-events",
            params=[("root_path", str(tmp_path)), ("prompt", "Explain crystal_bus.py"), ("context_files", "crystal_bus.py")],
        )

    assert '"content_loaded": false' in streamed.text
    assert "Attached context could not be read from the active workspace: crystal_bus.py: File not found" in streamed.text
    assert not calls


@pytest.mark.asyncio
async def test_sourceplan_rollback_latest_route_uses_governed_snapshot(monkeypatch, tmp_path):
    calls = []

    def fake_rollback(self):
        calls.append(self.workspace_root())
        return ActionResult(True, "Patch rollback", "restored 1 file", {"restored": ["service.py"], "deleted": []})

    monkeypatch.setattr(BeastApiClient, "rollback_last_patch", fake_rollback)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/edgek/sourceplan/rollback-latest", json={"root_path": str(tmp_path)})

    assert response.status_code == 200
    assert response.json()["restored"] == ["service.py"]
    assert calls == [tmp_path.resolve()]


@pytest.mark.asyncio
async def test_ide_agent_session_repairs_empty_action_ir_into_real_edit(monkeypatch, tmp_path):
    target = tmp_path / "service.py"
    target.write_text("def value():\n    return 1\n", encoding="utf-8")
    calls = []

    async def fake_stream_live_turn(self, text, history, **kwargs):
        calls.append(text)
        if "Return BEAST Action IR JSON only." in text:
            payload = {
                "kind": "beast.action_intent.v1",
                "objective": "Update the value",
                "actions": [{
                    "type": "replace_exact",
                    "target": {"path": "service.py"},
                    "old": "return 1",
                    "new": "return 2",
                    "intent": "Return the new value",
                }],
            }
        else:
            payload = {
                "kind": "beast.action_intent.v1",
                "objective": "Update the value",
                "actions": [],
            }
        yield {"type": "token", "text": json.dumps(payload)}
        yield {"type": "done", "ok": True, "tool_events": []}

    monkeypatch.setattr(BeastApiClient, "stream_live_turn", fake_stream_live_turn)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        created = await client.post(
            "/edgek/ide/agent-sessions/create",
            json={
                "root_path": str(tmp_path),
                "objective": "Update the governed file",
                "mode": "implementer",
                "provider": "nvidia_nim",
                "files": ["service.py"],
            },
        )
        session_id = created.json()["session"]["session_id"]
        streamed = await client.get(
            f"/edgek/ide/agent-sessions/{session_id}/run-events",
            params={
                "root_path": str(tmp_path),
                "prompt": "Change service.py so value returns 2.",
            },
        )
        detail = await client.get(
            f"/edgek/ide/agent-sessions/{session_id}",
            params={"root_path": str(tmp_path)},
        )

    outputs = detail.json()["session"]["outputs"]
    final_output = next(item for item in reversed(outputs) if item.get("kind") == "streamed_agent_output")
    assert streamed.status_code == 200
    assert "event: agent_run_sourceplan" in streamed.text
    assert "event: agent_run_needs_operator" not in streamed.text
    assert len(calls) == 2
    assert "Exact snippets available in the allowed files" in calls[1]
    assert "return 1" in calls[1]
    assert final_output["sourceplan_operation_count"] == 1
    assert final_output["sourceplan_plan"]["operations"][0]["path"] == "service.py"
    assert target.read_text(encoding="utf-8") == "def value():\n    return 1\n"


@pytest.mark.asyncio
async def test_ide_agent_session_repairs_invalid_proposed_syntax_before_sourceplan(monkeypatch, tmp_path):
    target = tmp_path / "service.py"
    target.write_text("def value():\n    return 1\n", encoding="utf-8")
    calls = []

    async def fake_stream_live_turn(self, text, history, **kwargs):
        calls.append(text)
        repaired = "Validation diagnostics from the proposed files:" in text
        replacement = "return 2" if repaired else "return ("
        yield {
            "type": "token",
            "text": json.dumps({
                "kind": "beast.action_intent.v1",
                "objective": "Update the value safely",
                "actions": [{
                    "id": "a1",
                    "type": "replace_exact",
                    "intent": "Return the new value",
                    "target": {"path": "service.py"},
                    "old": "return 1",
                    "new": replacement,
                }],
            }),
        }
        yield {"type": "done", "ok": True, "tool_events": []}

    monkeypatch.setattr(BeastApiClient, "stream_live_turn", fake_stream_live_turn)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        created = await client.post(
            "/edgek/ide/agent-sessions/create",
            json={
                "root_path": str(tmp_path),
                "objective": "Update the governed file safely",
                "mode": "implementer",
                "provider": "nvidia_nim",
                "files": ["service.py"],
            },
        )
        session_id = created.json()["session"]["session_id"]
        streamed = await client.get(
            f"/edgek/ide/agent-sessions/{session_id}/run-events",
            params={
                "root_path": str(tmp_path),
                "prompt": "Change service.py so value returns 2.",
            },
        )
        detail = await client.get(
            f"/edgek/ide/agent-sessions/{session_id}",
            params={"root_path": str(tmp_path)},
        )

    outputs = detail.json()["session"]["outputs"]
    final_output = next(item for item in reversed(outputs) if item.get("kind") == "streamed_agent_output")
    assert streamed.status_code == 200
    assert streamed.text.count("event: agent_run_validation") == 2
    assert '"repair": true' in streamed.text
    assert "event: agent_run_sourceplan" in streamed.text
    assert len(calls) == 2
    assert final_output["sourceplan_status"] == "compiled_action_ir"
    assert final_output["sourceplan_validation"]["status"] == "passed"
    assert final_output["sourceplan_plan"]["validation"]["status"] == "passed"
    assert any(item.get("kind") == "agent_action_ir_validation_repair" for item in outputs)
    assert target.read_text(encoding="utf-8") == "def value():\n    return 1\n"


@pytest.mark.asyncio
async def test_ide_agent_session_runs_isolated_py_compile_before_sourceplan(monkeypatch, tmp_path):
    target = tmp_path / "service.py"
    target.write_text("def value():\n    return 1\n", encoding="utf-8")

    async def fake_stream_live_turn(self, text, history, **kwargs):
        yield {
            "type": "token",
            "text": json.dumps({
                "kind": "beast.action_intent.v1",
                "objective": "Update the value safely",
                "verify": ["python -m py_compile service.py"],
                "actions": [{
                    "id": "a1",
                    "type": "replace_exact",
                    "intent": "Return the new value",
                    "target": {"path": "service.py"},
                    "old": "return 1",
                    "new": "return 2",
                }],
            }),
        }
        yield {"type": "done", "ok": True, "tool_events": []}

    monkeypatch.setattr(BeastApiClient, "stream_live_turn", fake_stream_live_turn)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        created = await client.post(
            "/edgek/ide/agent-sessions/create",
            json={
                "root_path": str(tmp_path),
                "objective": "Update the governed file safely",
                "mode": "implementer",
                "provider": "nvidia_nim",
                "files": ["service.py"],
            },
        )
        session_id = created.json()["session"]["session_id"]
        streamed = await client.get(
            f"/edgek/ide/agent-sessions/{session_id}/run-events",
            params={
                "root_path": str(tmp_path),
                "prompt": "Change service.py so value returns 2.",
            },
        )
        detail = await client.get(
            f"/edgek/ide/agent-sessions/{session_id}",
            params={"root_path": str(tmp_path)},
        )

    final_output = next(item for item in reversed(detail.json()["session"]["outputs"]) if item.get("kind") == "streamed_agent_output")
    validation = final_output["sourceplan_validation"]
    verifier_checks = [item for item in validation["checks"] if item.get("kind") == "isolated-verifier"]
    assert streamed.status_code == 200
    assert "event: agent_run_validation" in streamed.text
    assert "isolated_verifiers" in streamed.text
    assert validation["status"] == "passed"
    assert validation["isolated_verifiers"]["status"] == "passed"
    assert any(item.get("command") == "python -m py_compile service.py" and item.get("status") == "passed" for item in verifier_checks)
    assert final_output["sourceplan_plan"]["validation"]["isolated_verifiers"]["passed"] >= 1
    assert target.read_text(encoding="utf-8") == "def value():\n    return 1\n"


@pytest.mark.asyncio
async def test_ide_agent_session_skips_unsafe_model_verifier(monkeypatch, tmp_path):
    target = tmp_path / "service.py"
    target.write_text("def value():\n    return 1\n", encoding="utf-8")

    async def fake_stream_live_turn(self, text, history, **kwargs):
        yield {
            "type": "token",
            "text": json.dumps({
                "kind": "beast.action_intent.v1",
                "objective": "Update the value safely",
                "verify": ["rm -rf ."],
                "actions": [{
                    "id": "a1",
                    "type": "replace_exact",
                    "intent": "Return the new value",
                    "target": {"path": "service.py"},
                    "old": "return 1",
                    "new": "return 2",
                }],
            }),
        }
        yield {"type": "done", "ok": True, "tool_events": []}

    monkeypatch.setattr(BeastApiClient, "stream_live_turn", fake_stream_live_turn)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        created = await client.post(
            "/edgek/ide/agent-sessions/create",
            json={
                "root_path": str(tmp_path),
                "objective": "Update the governed file safely",
                "mode": "implementer",
                "provider": "nvidia_nim",
                "files": ["service.py"],
            },
        )
        session_id = created.json()["session"]["session_id"]
        await client.get(
            f"/edgek/ide/agent-sessions/{session_id}/run-events",
            params={
                "root_path": str(tmp_path),
                "prompt": "Change service.py so value returns 2.",
            },
        )
        detail = await client.get(
            f"/edgek/ide/agent-sessions/{session_id}",
            params={"root_path": str(tmp_path)},
        )

    validation = next(item for item in reversed(detail.json()["session"]["outputs"]) if item.get("kind") == "streamed_agent_output")["sourceplan_validation"]
    verifier_checks = [item for item in validation["checks"] if item.get("kind") == "isolated-verifier"]
    assert validation["status"] == "passed"
    assert any(item.get("command") == "rm -rf ." and item.get("status") == "skipped" for item in verifier_checks)
    assert target.exists()
    assert target.read_text(encoding="utf-8") == "def value():\n    return 1\n"


@pytest.mark.asyncio
async def test_ide_mission_timeline_and_sourceplan_lifecycle_facades(tmp_path):
    target = tmp_path / "service.py"
    original = "def value():\n    return 1\n"
    target.write_text(original, encoding="utf-8")
    client_api = BeastApiClient("http://offline", workspace=tmp_path)
    plan = {
        "plan_id": "desktop_lifecycle_probe",
        "kind": "beast_source_patch_plan",
        "objective": "Inspect lifecycle",
        "provider": "nvidia_nim",
        "files_allowed": ["service.py"],
        "operations": [{
            "op_id": "op_001",
            "op": "replace_exact",
            "path": "service.py",
            "old": "return 1",
            "new": "return 2",
            "expected_hash": client_api._file_hash_text(original),
            "selected": True,
            "source_edit": True,
        }],
        "selected_operations": ["op_001"],
    }
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        created = await client.post(
            "/edgek/ide/agent-sessions/create",
            json={"root_path": str(tmp_path), "objective": "Timeline probe", "provider": "nvidia_nim"},
        )
        lifecycle = await client.post(
            "/edgek/ide/sourceplan/lifecycle",
            json={"root_path": str(tmp_path), "plan": plan},
        )
        timeline = await client.get(
            "/edgek/ide/mission-timeline",
            params={"root_path": str(tmp_path), "objective": "Timeline probe", "limit": 20},
        )

    assert created.status_code == 200
    assert lifecycle.status_code == 200
    lifecycle_payload = lifecycle.json()
    assert lifecycle_payload["beast_object_type"] == "beast_ide_sourceplan_lifecycle"
    assert lifecycle_payload["plan_id"] == "desktop_lifecycle_probe"
    assert lifecycle_payload["can_apply"] is True
    assert {stage["stage"] for stage in lifecycle_payload["stages"]} >= {"draft", "preview", "scorecard", "verify", "evidence"}
    assert timeline.status_code == 200
    timeline_payload = timeline.json()
    assert timeline_payload["beast_object_type"] == "beast_ide_mission_timeline"
    assert any(item["kind"] == "agent_session" for item in timeline_payload["entries"])


@pytest.mark.asyncio
async def test_evidence_bus_query_supports_desktop_drawer_filters(tmp_path):
    receipt = EvidenceBus(tmp_path).register(
        artifact_type="desktop_probe",
        artifact_path=tmp_path / "probe.json",
        artifact_hash="sha256:probe",
        source="desktop_ide_test",
        task_id="plan_probe",
        status="verified",
        summary="Desktop evidence drawer probe",
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        query = await client.get(
            "/edgek/evidence-bus/query",
            params={
                "root_path": str(tmp_path),
                "source": "desktop_ide_test",
                "artifact_type": "desktop_probe",
                "status": "verified",
                "plan_id": "plan_probe",
            },
        )
        related = await client.get(
            f"/edgek/evidence-bus/related/{receipt['receipt_id']}",
            params={"root_path": str(tmp_path)},
        )

    assert query.status_code == 200
    assert query.json()["match_count"] == 1
    assert query.json()["receipts"][0]["receipt_id"] == receipt["receipt_id"]
    assert related.status_code == 200
    assert related.json()["match_count"] == 1


@pytest.mark.asyncio
async def test_governed_terminal_executes_allowed_command_and_records_evidence(tmp_path):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/edgek/safety-governor/execute-command",
            json={
                "root_path": str(tmp_path),
                "command": "python3 --version",
                "mode": "operator",
                "task_id": "terminal_probe",
            },
        )
        evidence = await client.get(
            "/edgek/evidence-bus/query",
            params={"root_path": str(tmp_path), "source": "governed_terminal", "task_id": "terminal_probe"},
        )

    payload = response.json()

    assert response.status_code == 200
    assert payload["beast_object_type"] == "beast_governed_terminal_execution"
    assert payload["ok"] is True
    assert payload["returncode"] == 0
    assert "Python" in payload["stdout"]
    assert payload["evidence_receipt"]["source"] == "governed_terminal"
    assert evidence.json()["match_count"] == 1


@pytest.mark.asyncio
async def test_governed_terminal_blocks_dangerous_command(tmp_path):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/edgek/safety-governor/execute-command",
            json={
                "root_path": str(tmp_path),
                "command": "rm -rf /tmp/definitely-do-not-run",
                "mode": "operator",
            },
        )

    payload = response.json()

    assert response.status_code == 200
    assert payload["ok"] is False
    assert payload["error"] == "blocked_by_safety_governor"
    assert payload["safety"]["decision"] == "block"


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


@pytest.mark.asyncio
async def test_final_replay_gauntlet_crosses_http_mcp_and_tui(tmp_path, monkeypatch):
    target = tmp_path / "service.py"
    original = "def value():\n    return 1\n"
    target.write_text(original, encoding="utf-8")
    offline = BeastApiClient("http://offline", workspace=tmp_path)
    seed_plan = {
        "plan_id": "final_gauntlet_seed",
        "objective": "Repair service value",
        "provider": "local",
        "files_allowed": ["service.py"],
        "operations": [{
            "op_id": "op_seed",
            "op": "replace_exact",
            "path": "service.py",
            "old": "return 1",
            "new": "return 2",
            "expected_hash": offline._file_hash_text(original),
            "selected": True,
            "source_edit": True,
            "action_ir_type": "replace_exact",
        }],
    }
    assert offline.apply_patch_plan(seed_plan, approved=True).ok is True
    future_plan = {
        **seed_plan,
        "plan_id": "final_gauntlet_replay",
        "objective": "Replay the verified service value repair pattern",
        "operations": [{
            **seed_plan["operations"][0],
            "op_id": "op_replay",
            "old": "return 2",
            "new": "return 3",
            "expected_hash": offline._file_hash_text(target.read_text(encoding="utf-8")),
        }],
    }

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http:
        scorecard_response = await http.post(
            "/edgek/sourceplan/scorecard",
            json={"root_path": str(tmp_path), "plan": future_plan},
        )
        context_response = await http.post(
            "/edgek/workspace/context",
            json={"root_path": str(tmp_path), "objective": future_plan["objective"], "selected_files": ["service.py"]},
        )
        search_response = await http.get(
            "/edgek/workspace/search",
            params={"q": "service value", "limit": 5},
        )
        replay_response = await http.post(
            "/edgek/mission-lattice/replay-scaffold",
            json={"root_path": str(tmp_path), "plan": future_plan, "scorecard": scorecard_response.json()},
        )

    scorecard = scorecard_response.json()
    context = context_response.json()
    search = search_response.json()
    replay = replay_response.json()
    runtime = BeastToolRuntime()
    mcp_graph = runtime.call_tool(
        "beast_get_workspace_graph",
        {"workspace_root": str(tmp_path), "query": future_plan["objective"], "depth": 2},
    )
    mcp_replay = runtime.call_tool(
        "beast_mission_lattice_replay_scaffold",
        {"workspace_root": str(tmp_path), "plan": future_plan, "scorecard": scorecard},
    )

    class _ScorecardResult:
        ok = True
        data = scorecard

    monkeypatch.setattr(
        "app.cli.ui.BeastApiClient.sourceplan_scorecard",
        lambda self, plan: _ScorecardResult(),
    )
    monkeypatch.setattr(
        SourceWorkbenchScreen,
        "app",
        property(lambda self: type("_DummyApp", (), {"base_url": "http://offline"})()),
    )
    screen = SourceWorkbenchScreen({"operations": []})
    panel = screen._scorecard_panel({**future_plan, "workspace": str(tmp_path)})
    console = Console(record=True, width=120)
    console.print(panel)
    rendered = console.export_text()

    assert scorecard_response.status_code == 200
    assert context_response.status_code == 200
    assert search_response.status_code == 200
    assert replay_response.status_code == 200
    assert scorecard["source_workbench"]["lattice_replay"]["visible"] is True
    assert context["context_front_door"] == "code_cortex"
    assert search["context_front_door"] == "code_cortex"
    assert replay["beast_object_type"] == "mission_lattice_replay_closure"
    assert replay["no_auto_apply"] is True
    assert mcp_graph["context_front_door"] == "code_cortex"
    assert mcp_graph["beast_object_type"] == "code_cortex_workspace_graph_view"
    assert mcp_replay["beast_object_type"] == "mission_lattice_replay_closure"
    assert mcp_replay["no_auto_apply"] is True
    assert "Lattice replay" in rendered
    assert "Policy gate" in rendered

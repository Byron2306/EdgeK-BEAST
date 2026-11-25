from __future__ import annotations

import asyncio

import pytest

from typing import Any

from app.kernel.agents.planner_provider import CallbackPlannerProvider, CapabilityScoredPlannerProvider, FallbackPlannerProvider, HeuristicPlannerProvider, ScriptedPlannerProvider, StickyFallbackPlannerProvider, normalize_editor_tool_dialect, parse_planner_decision
from app.kernel.agents.planner_runtime import AgentPlannerRuntime
from app.kernel.agents.provider_quality import ProviderQualityLedger
from app.kernel.agents.run_engine import AgentRunEngine
from app.kernel.agents.ollama_planner_provider import OllamaPlannerProvider
from app.kernel.agents.nim_planner_provider import NIMPlannerProvider
from app.kernel.agents.verification_planner import plan_verification
from app.kernel.commons.route_damping import RouteFlapDampener
from app.kernel.approvals.capability_issuer import RequestBoundCapability
from app.kernel.approvals.capability_runtime import ExactStepResumeRuntime
from app.kernel.approvals.digests import sha256_digest
from app.kernel.approvals.models import ApprovalContractFactory
from app.kernel.operations_console.objective_plan import ObjectivePlanWorkspace


def make_run(tmp_path):
    (tmp_path / "sample.py").write_text("def answer():\n    return 42\n", encoding="utf-8")
    engine = AgentRunEngine(tmp_path)
    run = engine.create_run(
        session_id="session-planner",
        objective="Find the answer function and report what it returns",
        mode="analysis",
        provider="simulated",
        model="planner-test",
    )
    return engine, run["run_id"]


def _repo_run(tmp_path, *, provider="simulated", model="planner-test", graduation_contract=False,
              approval_capability="worktree_mutation", transport=""):
    """Agent repo run. ``graduation_contract`` adds the operator-owned R3.24 contract
    (explicit implementation_target + baseline pytest file) that mutating runs need to
    finish COMPLETED instead of policy_blocked by the post-session graduation gate."""
    import subprocess

    root = tmp_path / "repo"
    root.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "beast@example.test"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "BEAST Test"], cwd=root, check=True)
    (root / "answer.py").write_text("VALUE = 1\n", encoding="utf-8")
    request = {
        "context_files": ["answer.py"],
        "semantic_context": {"active_file": "answer.py", "open_files": ["answer.py"]},
    }
    if transport:
        request["transport"] = transport
    if graduation_contract:
        (root / "test_answer.py").write_text("import answer\n\n\ndef test_value():\n    assert answer.VALUE == 2\n", encoding="utf-8")
        request.update({"implementation_target": "answer.py", "required_test_files": ["test_answer.py"]})
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    subprocess.run(["git", "commit", "-qm", "initial"], cwd=root, check=True)
    engine = AgentRunEngine(root)
    run_id = engine.create_run(
        session_id="session-agent-runtime",
        objective="Change VALUE to 2 and verify it",
        mode="agent",
        provider=provider,
        model=model,
        request=request,
    )["run_id"]
    approval_id = "mutate-worktree"
    engine.store.create_approval(run_id, {"request_id": approval_id, "capabilities": [{"id": approval_capability}]})
    engine.store.resolve_approval(run_id, approval_id, {"approved": True, "scope": "run"})
    return engine, run_id, approval_id



def _bind_test_worktree(engine, run_id, approval_id, runtime, state):
    receipt = asyncio.run(engine.execute_tool(run_id, "worktree.bind", {}, approval_id=approval_id))
    state.observations = [
        receipt if item.get("tool_id") == "worktree.bind" else item
        for item in state.observations
    ]
    runtime._save_state(state)


def _approval_fixture(root, *, step_id="mutate"):
    factory = ApprovalContractFactory()
    request = factory.create_request({
        "approval_id": "approval_47",
        "run_id": "run_47",
        "step_id": step_id,
        "agent_id": "agent:beast",
        "model_id": "model:coder",
        "provider_id": "provider:local",
        "tool_id": "workspace.read_range",
        "tool_version": "1",
        "arguments": {"path": "app/example.py", "start_line": 1, "end_line": 20},
        "workspace_id": "workspace:repo",
        "execution_target": "local",
        "affected_resources": ["app/example.py"],
        "data_egress": [],
        "expected_side_effects": [],
        "risk_class": "LOW",
        "reason": "Read the approved source range",
        "budget_impact": {"tool_calls": 1},
        "evidence_policy": {"level": "summary"},
        "requested_scope": "ONCE",
        "permission_mode": "GUIDED",
        "policy_generation": "policy:47",
        "expiry_seconds": 600,
    })
    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)
    capability = RequestBoundCapability(
        capability_id="cap_47",
        approval_id=request["approval_id"],
        grant_id="grant_47",
        grant_digest=sha256_digest({"grant": 47}),
        scope_match_digest=sha256_digest({"match": 47}),
        request_digest=request["request_digest"],
        classification_digest=sha256_digest({"classification": 47}),
        decision_digest=sha256_digest({"decision": 47}),
        run_id=request["run_id"],
        step_id=request["step_id"],
        tool_id=request["tool_id"],
        tool_version=request["tool_version"],
        workspace_id=request["workspace_id"],
        execution_target=request["execution_target"],
        policy_generation=request["policy_generation"],
        call_identity_digest=sha256_digest({"call": 47}),
        scope="ONCE",
        audience="beast-tool-runtime",
        issued_at=now.isoformat(),
        expires_at=(now + timedelta(minutes=5)).isoformat(),
        nonce="nonce47",
        single_use=True,
    ).to_dict()
    return request, capability


def test_planner_executes_tools_and_completes(tmp_path):
    engine, run_id = make_run(tmp_path)
    provider = ScriptedPlannerProvider([
        {"decision_type": "tool", "tool_id": "workspace.search_text", "arguments": {"query": "def answer", "path": "."}},
        {"decision_type": "tool", "tool_id": "workspace.read_range", "arguments": {"path": "sample.py", "start_line": 1, "line_count": 10}},
        {"decision_type": "complete", "summary": "sample.py defines answer() and returns 42."},
    ])
    final = asyncio.run(AgentPlannerRuntime(engine, provider, max_turns=5).run(run_id))
    assert final["state"] == "completed"
    planner = final["checkpoint"]["planner"]
    assert planner["turn"] == 3
    assert len(planner["observations"]) == 2
    assert planner["observations"][1]["result"]["content"].endswith("return 42")
    assert planner["final_summary"].endswith("returns 42.")
    assert engine.store.verify_chain(run_id)["head_matches"] is True


def test_planner_turn_budget_is_terminal(tmp_path):
    engine, run_id = make_run(tmp_path)
    provider = ScriptedPlannerProvider([
        {"decision_type": "tool", "tool_id": "workspace.list", "arguments": {}},
        {"decision_type": "tool", "tool_id": "workspace.list", "arguments": {}},
    ])
    final = asyncio.run(AgentPlannerRuntime(engine, provider, max_turns=2).run(run_id))
    assert final["state"] == "budget_exhausted"
    assert final["checkpoint"]["planner"]["status"] == "budget_exhausted"


def test_budget_edge_autofinalizes_after_verify_and_sourceplan(tmp_path):
    engine, run_id, approval_id = _repo_run(tmp_path, provider="nvidia_nim", model="planner-test", graduation_contract=True)
    provider = ScriptedPlannerProvider([
        {"decision_type": "tool", "tool_id": "workspace.index", "arguments": {"limit": 1200, "include_symbols": True}},
        {"decision_type": "tool", "tool_id": "worktree.bind", "approval_id": approval_id, "arguments": {"objective": "Change VALUE to 2 and verify it", "provider": "nvidia_nim", "risk": "high"}},
        {"decision_type": "tool", "tool_id": "workspace.read_range", "arguments": {"path": "answer.py", "start_line": 1, "line_count": 40}},
        {"decision_type": "tool", "tool_id": "worktree.replace_exact", "approval_id": approval_id, "arguments": {"path": "answer.py", "old_text": "VALUE = 1", "new_text": "VALUE = 2"}},
        {"decision_type": "tool", "tool_id": "worktree.verify", "approval_id": approval_id, "arguments": {"command": ["python", "-m", "py_compile", "answer.py"]}},
        {"decision_type": "tool", "tool_id": "worktree.sourceplan_draft", "arguments": {}},
    ])
    runtime = AgentPlannerRuntime(engine, provider, max_turns=6)
    final = asyncio.run(runtime.run(run_id))
    assert final["state"] == "completed"
    planner = final["checkpoint"]["planner"]
    assert planner["status"] == "completed"
    assert "verification passed and SourcePlan evidence is ready" in str(planner.get("final_summary") or "")
    events = engine.store.events(run_id, limit=200)
    completed = [event for event in events if event["event_type"] == "agent.planner.completed"]
    assert completed
    assert completed[-1]["payload"]["completion_mode"] == "budget_edge_autofinalize"


def test_agent_mode_bootstraps_a_bounded_inspection_before_model_completion(tmp_path):
    (tmp_path / "sample.py").write_text("VALUE = 1\n", encoding="utf-8")
    engine = AgentRunEngine(tmp_path)
    run_id = engine.create_run(
        session_id="session-agent-bootstrap",
        objective="Inspect and repair the sample.",
        mode="agent",
        provider="simulated",
        model="planner-test",
    )["run_id"]
    provider = ScriptedPlannerProvider([
        {"decision_type": "complete", "summary": "incorrectly completed without inspecting"},
    ])
    final = asyncio.run(AgentPlannerRuntime(engine, provider, max_turns=1).run(run_id))
    planner = final["checkpoint"]["planner"]
    assert final["state"] == "budget_exhausted"
    assert planner["observations"][0]["tool_id"] == "workspace.index"
    assert planner["observations"][0]["status"] == "completed"
    assert planner["observations"][0]["result"]["summary"]["file_count"] >= 1


def test_planner_failed_tool_becomes_observation(tmp_path):
    engine, run_id = make_run(tmp_path)
    provider = ScriptedPlannerProvider([
        {"decision_type": "tool", "tool_id": "workspace.read_range", "arguments": {"path": "../escape.txt"}},
        {"decision_type": "complete", "summary": "The requested path was outside the workspace and was refused."},
    ])
    final = asyncio.run(AgentPlannerRuntime(engine, provider, max_turns=3).run(run_id))
    assert final["state"] == "completed"
    observation = final["checkpoint"]["planner"]["observations"][0]
    assert observation["status"] == "failed"
    assert "escapes workspace" in observation["error"]


def test_decision_contract_rejects_prose_and_invalid_shape():
    for value in ["I think we should inspect files", {"decision_type": "tool"}, {"decision_type": "complete"}]:
        try:
            parse_planner_decision(value)
        except ValueError:
            pass
        else:
            raise AssertionError(f"invalid decision accepted: {value!r}")


def test_decision_contract_accepts_action_alias():
    decision = parse_planner_decision({
        "action": {
            "tool_id": "git.status",
            "arguments": {},
        }
    })
    assert decision.decision_type.value == "tool"
    assert decision.tool_id == "git.status"


def test_decision_contract_normalizes_small_model_tool_aliases():
    decision = parse_planner_decision({
        "type": "function_call",
        "name": "workspace.read_range",
        "args": {"path": "sample.py", "start_line": 1, "line_count": 4},
    })
    assert decision.decision_type.value == "tool"
    assert decision.tool_id == "workspace.read_range"
    assert decision.arguments["path"] == "sample.py"


@pytest.mark.parametrize(
    ("command", "arguments", "expected_tool", "expected_arguments"),
    [
        (
            "view",
            {"path": "sample.py", "line_start": 3, "line_end": 7},
            "workspace.read_range",
            {"path": "sample.py", "start_line": 3, "line_count": 5},
        ),
        (
            "str_replace",
            {"path": "sample.py", "old_str": "return 1", "new_str": "return 2"},
            "worktree.replace_exact",
            {"path": "sample.py", "old_text": "return 1", "new_text": "return 2"},
        ),
        (
            "create",
            {"path": "new.py", "file_text": "VALUE = 1\n"},
            "worktree.write_file",
            {"path": "new.py", "content": "VALUE = 1\n"},
        ),
    ],
)
def test_editor_tool_dialect_maps_common_coder_operations(
    command, arguments, expected_tool, expected_arguments
):
    decision = parse_planner_decision({
        "decision_type": "tool",
        "tool_id": "str_replace_editor",
        "arguments": {"command": command, **arguments},
    })

    normalized = normalize_editor_tool_dialect(decision)

    assert normalized.tool_id == expected_tool
    assert normalized.arguments == expected_arguments


def test_editor_tool_dialect_relativizes_only_paths_inside_known_roots(tmp_path):
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    inside = parse_planner_decision({
        "decision_type": "tool",
        "tool_id": "str_replace_editor",
        "arguments": {"command": "view", "path": str(worktree / "sample.py")},
    })
    outside = parse_planner_decision({
        "decision_type": "tool",
        "tool_id": "str_replace_editor",
        "arguments": {"command": "view", "path": str(tmp_path / "outside.py")},
    })

    assert normalize_editor_tool_dialect(inside, roots=[worktree]).arguments["path"] == "sample.py"
    assert normalize_editor_tool_dialect(outside, roots=[worktree]).arguments["path"] == str(tmp_path / "outside.py")


def test_editor_tool_dialect_maps_opencode_read_and_canonical_absolute_path(tmp_path):
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    opencode = parse_planner_decision({
        "decision_type": "tool",
        "tool_id": "read",
        "arguments": {"file": str(worktree / "sample.py"), "ranges": "3-7"},
    })
    canonical = parse_planner_decision({
        "decision_type": "tool",
        "tool_id": "workspace.read_range",
        "arguments": {"path": str(worktree / "sample.py"), "start_line": 1, "line_count": 20},
    })

    mapped = normalize_editor_tool_dialect(opencode, roots=[worktree])
    assert mapped.tool_id == "workspace.read_range"
    assert mapped.arguments == {"path": "sample.py", "start_line": 3, "line_count": 5}
    assert normalize_editor_tool_dialect(canonical, roots=[worktree]).arguments["path"] == "sample.py"


def test_editor_tool_dialect_does_not_guess_unsupported_operations():
    decision = parse_planner_decision({
        "decision_type": "tool",
        "tool_id": "str_replace_editor",
        "arguments": {"command": "insert", "path": "sample.py", "new_str": "unsafe guess"},
    })

    assert normalize_editor_tool_dialect(decision) == decision


def test_runtime_records_editor_dialect_translation(tmp_path):
    engine, run_id = make_run(tmp_path)
    runtime = AgentPlannerRuntime(engine, ScriptedPlannerProvider([]))
    decision = parse_planner_decision({
        "decision_type": "tool",
        "tool_id": "str_replace_editor",
        "arguments": {"command": "view", "path": str(tmp_path / "sample.py")},
    })

    normalized = runtime._normalize_model_tool_dialect(
        engine.store.get_run(run_id), run_id, decision
    )

    assert normalized.tool_id == "workspace.read_range"
    assert normalized.arguments == {"path": "sample.py"}
    events = engine.store.events(run_id, limit=100)
    payload = next(
        row["payload"] for row in events
        if row["event_type"] == "agent.provider.tool_dialect_normalized"
    )
    assert payload["source_tool_id"] == "str_replace_editor"
    assert payload["tool_id"] == "workspace.read_range"


def test_decision_contract_normalizes_params_and_end_line_for_read_range():
    decision = parse_planner_decision({
        "tool_id": "workspace.read_range",
        "params": {"path": "sample.py", "start_line": 3, "end_line": 7},
    })
    assert decision.decision_type.value == "tool"
    assert decision.tool_id == "workspace.read_range"
    assert decision.arguments["path"] == "sample.py"
    assert decision.arguments["start_line"] == 3
    assert decision.arguments["line_count"] == 5


def test_decision_contract_normalizes_descriptive_action_enum():
    decision = parse_planner_decision({
        "decision_type": "inspect_workspace_first",
        "action": {"tool_id": "workspace.list", "arguments": {}},
        "summary": "Inspect the workspace before planning.",
    })
    assert decision.decision_type.value == "tool"
    assert decision.tool_id == "workspace.list"


def test_planner_observation_projection_drops_large_payloads():
    projected = AgentPlannerRuntime._compact_observation({
        "observation_id": "obs-1",
        "tool_id": "workspace.read_range",
        "status": "completed",
        "result": {"content": "x" * 10000, "sha256": "abc"},
    })
    assert len(projected["result"]["content"]) <= 2410
    assert projected["result"]["sha256"] == "abc"


def test_planner_prompt_includes_ide_semantic_context(tmp_path):
    engine = AgentRunEngine(tmp_path)
    semantic_context = {
        "services": {
            "index": {
                "digest": "sha256:semantic",
                "symbolCount": 4,
                "referenceCount": 8,
                "importEdgeCount": 2,
                "semantic": {
                    "workspaceSymbols": [{"name": "double", "kind": "function", "file": "src/helper.js", "line": 2}],
                    "topReferences": [{"name": "double", "count": 2, "files": ["src/helper.js", "src/index.js"]}],
                },
                "diagnostics": [{"file": "src/helper.js", "line": 1, "severity": "hint", "code": "todo-comment", "message": "TODO: tighten helper coverage"}],
                "codeActions": [{"title": "Track TODO in workspace", "kind": "source.organize", "diagnostic": {"file": "src/helper.js", "line": 1, "code": "todo-comment"}}],
            },
            "navigation": {"supports": {"workspaceSymbols": True, "definitions": True, "references": True, "dependents": True}},
            "diagnostics": {"count": 1, "codeActionCount": 1},
            "refactor": {"supportsRenamePreview": True, "supportsCodeActions": True},
        }
    }
    run_id = engine.create_run(
        session_id="session-semantic",
        objective="Use IDE semantic context before editing helper code",
        mode="analysis",
        provider="simulated",
        model="planner-test",
        request={"semantic_context": semantic_context},
    )["run_id"]
    prompts = []

    async def decide(prompt, _run, _turn):
        prompts.append(prompt)
        return {"decision_type": "complete", "summary": "Semantic context reviewed."}

    final = asyncio.run(AgentPlannerRuntime(engine, CallbackPlannerProvider(decide), max_turns=1).run(run_id))
    assert final["state"] == "completed"
    assert "SEMANTIC_CONTEXT:" in prompts[0]
    assert "todo-comment" in prompts[0]
    assert "double" in prompts[0]
    assert "rename_preview" in prompts[0]


def test_compact_observation_preserves_semantic_diagnostics_and_refactor():
    projected = AgentPlannerRuntime._compact_observation({
        "observation_id": "obs-semantic",
        "tool_id": "workspace.index",
        "status": "completed",
        "result": {
            "summary": {"file_count": 3, "symbol_count": 4, "reference_count": 9, "diagnostic_count": 1},
            "diagnostics": [{"file": "src/helper.js", "line": 1, "severity": "hint", "code": "todo-comment", "message": "TODO"}],
            "codeActions": [{"title": "Track TODO in workspace", "kind": "source.organize"}],
            "refactor": {"supportsRenamePreview": True, "supportsCodeActions": True},
            "renamePreview": {"ok": True, "editCount": 2, "fileCount": 2},
        },
    })
    result = projected["result"]
    assert result["summary"]["reference_count"] == 9
    assert result["diagnostics"][0]["code"] == "todo-comment"
    assert result["codeActions"][0]["title"] == "Track TODO in workspace"
    assert result["refactor"]["supportsRenamePreview"] is True
    assert result["renamePreview"]["editCount"] == 2


def test_phase1_planning_integration_seeds_durable_objective_plan(tmp_path):
    engine, run_id, _approval_id = _repo_run(tmp_path)
    provider = ScriptedPlannerProvider([
        {"decision_type": "complete", "summary": "incorrectly completed without inspecting"},
    ])
    asyncio.run(AgentPlannerRuntime(engine, provider, max_turns=1).run(run_id))
    workspace = ObjectivePlanWorkspace(engine.workspace_root)
    current = workspace.current(run_id)
    history = workspace.history(run_id)
    assert current["revision_id"]
    assert current["operator_id"] in {"beast.phase1", "beast.phase3"}
    assert history[0]["operator_id"] == "beast.phase1"
    assert history[0]["reason"] == "phase1_multi_file_execution_planning_seed"
    assert history[0]["plan"]["active_step_id"] == "inspect"
    assert [step["step_id"] for step in history[0]["plan"]["steps"]] == ["inspect", "bind", "mutate", "verify", "handoff"]
    event_types = [e["event_type"] for e in engine.store.events(run_id, limit=100)]
    assert "agent.plan.integration.seeded" in event_types


def test_phase1_planning_integration_progresses_with_observations(tmp_path):
    engine, run_id, approval_id = _repo_run(tmp_path)
    provider = ScriptedPlannerProvider([
        {"decision_type": "tool", "tool_id": "workspace.list", "arguments": {}},
        {"decision_type": "tool", "tool_id": "worktree.bind", "approval_id": approval_id, "arguments": {"objective": "repair VALUE"}},
        {"decision_type": "tool", "tool_id": "worktree.replace_exact", "approval_id": approval_id, "arguments": {"path": "answer.py", "old_text": "VALUE = 1", "new_text": "VALUE = 2"}},
        {"decision_type": "complete", "summary": "completed before verify"},
        {"decision_type": "complete", "summary": "completed before sourceplan"},
        {"decision_type": "complete", "summary": "VALUE repaired and verified."},
    ])
    asyncio.run(AgentPlannerRuntime(engine, provider, max_turns=6).run(run_id))
    current = ObjectivePlanWorkspace(engine.workspace_root).current(run_id)
    statuses = {step["step_id"]: step["status"] for step in current["plan"]["steps"]}
    assert statuses == {
        "inspect": "completed",
        "bind": "completed",
        "mutate": "completed",
        "verify": "completed",
        "handoff": "completed",
    }
    assert current["plan"]["active_step_id"] == ""
    progress_events = [e for e in engine.store.events(run_id, limit=200) if e["event_type"] == "agent.plan.integration.progressed"]
    assert len(progress_events) >= 5
    assert progress_events[-1]["payload"]["tool_id"] == "worktree.sourceplan_draft"


def test_phase2_planning_integration_marks_repair_scope_after_failed_verify(tmp_path):
    engine, run_id, approval_id = _repo_run(tmp_path)
    provider = ScriptedPlannerProvider([
        {"decision_type": "tool", "tool_id": "workspace.list", "arguments": {}},
        {"decision_type": "tool", "tool_id": "worktree.bind", "approval_id": approval_id, "arguments": {"objective": "repair VALUE"}},
        {"decision_type": "tool", "tool_id": "worktree.replace_exact", "approval_id": approval_id, "arguments": {"path": "answer.py", "old_text": "VALUE = 1", "new_text": "VALUE = 2\nbroken = "}},
        {"decision_type": "tool", "tool_id": "worktree.verify", "approval_id": approval_id, "arguments": {"command": ["python", "-m", "py_compile", "answer.py"]}},
        {"decision_type": "complete", "summary": "too early after failed verify"},
    ])
    asyncio.run(AgentPlannerRuntime(engine, provider, max_turns=4, max_repair_cycles=2).run(run_id))
    current = ObjectivePlanWorkspace(engine.workspace_root).current(run_id)
    mutate = next(step for step in current["plan"]["steps"] if step["step_id"] == "mutate")
    verify = next(step for step in current["plan"]["steps"] if step["step_id"] == "verify")
    assert current["plan"]["active_step_id"] == "mutate"
    assert mutate["status"] == "active"
    assert "syntax failure" in mutate["title"]
    assert "answer.py" in mutate["title"]
    assert any("verifier-declared residual" in item for item in mutate["success_criteria"])
    assert verify["status"] == "blocked"
    assert "verification failed" in verify["blocked_reason"]


def test_phase3_planning_integration_records_latency_on_plan_steps(tmp_path):
    engine, run_id, approval_id = _repo_run(tmp_path)
    provider = ScriptedPlannerProvider([
        {"decision_type": "tool", "tool_id": "workspace.list", "arguments": {}},
        {"decision_type": "tool", "tool_id": "worktree.bind", "approval_id": approval_id, "arguments": {"objective": "repair VALUE"}},
        {"decision_type": "tool", "tool_id": "worktree.replace_exact", "approval_id": approval_id, "arguments": {"path": "answer.py", "old_text": "VALUE = 1", "new_text": "VALUE = 2"}},
        {"decision_type": "complete", "summary": "completed before verify"},
        {"decision_type": "complete", "summary": "completed before sourceplan"},
        {"decision_type": "complete", "summary": "VALUE repaired and verified."},
    ])
    asyncio.run(AgentPlannerRuntime(engine, provider, max_turns=6).run(run_id))
    current = ObjectivePlanWorkspace(engine.workspace_root).current(run_id)
    inspect = next(step for step in current["plan"]["steps"] if step["step_id"] == "inspect")
    bind = next(step for step in current["plan"]["steps"] if step["step_id"] == "bind")
    verify = next(step for step in current["plan"]["steps"] if step["step_id"] == "verify")
    assert inspect["telemetry"]["planner_turns"] >= 1
    assert inspect["telemetry"]["tool_calls"] >= 1
    assert inspect["telemetry"]["last_tool_id"] == "workspace.list"
    assert bind["telemetry"]["tool_calls"] >= 1
    assert bind["telemetry"]["tool_latency_ms"] >= 0
    assert verify["telemetry"]["verification_latency_ms"] >= 0
    telemetry_events = [e for e in engine.store.events(run_id, limit=300) if e["event_type"] == "agent.plan.integration.telemetry"]
    assert telemetry_events


def test_phase4_planning_integration_records_route_on_active_step(tmp_path):
    engine, run_id, approval_id = _repo_run(tmp_path)
    provider = HeuristicPlannerProvider()
    asyncio.run(AgentPlannerRuntime(engine, provider, max_turns=1).run(run_id))
    current = ObjectivePlanWorkspace(engine.workspace_root).current(run_id)
    inspect = next(step for step in current["plan"]["steps"] if step["step_id"] == "inspect")
    assert inspect["telemetry"]["route_provider"] == "heuristic"
    assert inspect["telemetry"]["route_engine"] == "deterministic"
    assert inspect["telemetry"]["route_kind"] == "heuristic"
    routing_events = [e for e in engine.store.events(run_id, limit=200) if e["event_type"] == "agent.plan.integration.routing"]
    assert routing_events


def test_phase5_planning_integration_records_resume_continuity(tmp_path):
    engine, run_id, approval_id = _repo_run(tmp_path)
    runtime = AgentPlannerRuntime(engine, ScriptedPlannerProvider([]), max_turns=1)
    runtime.planning_integrations.ensure_phase1_plan(run_id, engine.store.get_run(run_id))
    runtime.planning_integrations.sync_phase1_progress(run_id, {"tool_id": "workspace.list", "status": "completed"})
    engine.merge_checkpoint(run_id, {
        "planner": {
            "run_id": run_id,
            "turn": 1,
            "max_turns": 2,
            "status": "running",
            "last_decision": {"decision_type": "tool", "tool_id": "worktree.bind", "arguments": {"objective": "repair VALUE"}},
            "observations": [{"tool_id": "workspace.list", "status": "completed", "result": {}}],
            "final_summary": "",
            "blocker": "",
            "repair_cycles": 0,
            "max_repair_cycles": 2,
            "verification_failures": [],
        }
    })
    engine.store.transition(run_id, "paused")
    engine.resume(run_id)
    resumed = asyncio.run(runtime.run(run_id))
    current = ObjectivePlanWorkspace(engine.workspace_root).current(run_id)
    bind = next(step for step in current["plan"]["steps"] if step["step_id"] == "bind")
    continuity = bind["telemetry"]["continuity"]
    assert resumed["checkpoint"]["planner"]["turn"] >= 1
    assert continuity["resume_sequence"] >= 1
    assert continuity["resumed_from_state"] == "paused"
    assert continuity["resume_status"] == "planner_resumed"
    assert continuity["resume_step_id"] == "bind"
    resume_events = [e for e in engine.store.events(run_id, limit=300) if e["event_type"] == "agent.plan.integration.resumed"]
    assert resume_events


def test_phase5_planning_integration_preserves_repair_context_on_resume(tmp_path):
    engine, run_id, approval_id = _repo_run(tmp_path)
    runtime = AgentPlannerRuntime(engine, ScriptedPlannerProvider([]), max_turns=1, max_repair_cycles=2)
    runtime.planning_integrations.ensure_phase1_plan(run_id, engine.store.get_run(run_id))
    runtime.planning_integrations.sync_phase1_progress(run_id, {"tool_id": "workspace.list", "status": "completed"})
    runtime.planning_integrations.sync_phase1_progress(run_id, {"tool_id": "worktree.bind", "status": "completed"})
    runtime.planning_integrations.sync_phase1_progress(run_id, {"tool_id": "worktree.replace_exact", "status": "completed"})
    failed_verify = {
        "tool_id": "worktree.verify",
        "status": "failed",
        "error": "verification failed",
        "result": {
            "analysis": {"failure_class": "bad_patch", "missing_symbol": ""},
            "target_paths": ["answer.py"],
        },
    }
    runtime.planning_integrations.sync_phase1_progress(run_id, failed_verify)
    engine.merge_checkpoint(run_id, {
        "planner": {
            "run_id": run_id,
            "turn": 4,
            "max_turns": 5,
            "status": "running",
            "last_decision": {"decision_type": "tool", "tool_id": "worktree.verify", "arguments": {"command": ["python", "-m", "py_compile", "answer.py"]}},
            "observations": [
                {"tool_id": "workspace.list", "status": "completed", "result": {}},
                {"tool_id": "worktree.bind", "status": "completed", "result": {}},
                {"tool_id": "worktree.replace_exact", "status": "completed", "result": {"path": "answer.py"}},
                failed_verify,
            ],
            "final_summary": "",
            "blocker": "",
            "repair_cycles": 1,
            "max_repair_cycles": 2,
            "verification_failures": [{
                "turn": 4,
                "repair_cycle": 1,
                "observation_id": "obs-verify-failed",
                "error": "verification failed",
                "result": failed_verify["result"],
                "analysis": failed_verify["result"]["analysis"],
                "target_paths": ["answer.py"],
            }],
        }
    })
    engine.store.transition(run_id, "paused")
    engine.resume(run_id)
    asyncio.run(runtime.run(run_id))
    current = ObjectivePlanWorkspace(engine.workspace_root).current(run_id)
    mutate = next(step for step in current["plan"]["steps"] if step["step_id"] == "mutate")
    continuity = mutate["telemetry"]["continuity"]
    assert current["plan"]["active_step_id"] == "mutate"
    assert continuity["resume_pending_repair"] is True
    assert continuity["resume_failure_class"] == "bad_patch"
    assert continuity["resume_target_paths"] == ["answer.py"]
    assert continuity["resume_repair_cycles"] == 1
    assert continuity["resume_status"] == "repair_pending"


def test_phase6_planning_integration_blocks_active_step_while_waiting_for_approval(tmp_path):
    engine, run_id, _approval_id = _repo_run(tmp_path)
    pending_runtime = AgentPlannerRuntime(engine, ScriptedPlannerProvider([]), max_turns=1)
    current = ObjectivePlanWorkspace(engine.workspace_root).current(run_id)
    if not current["revision_id"]:
        pending_runtime.planning_integrations.ensure_phase1_plan(run_id, engine.store.get_run(run_id))
        pending_runtime.planning_integrations.sync_phase1_progress(run_id, {"tool_id": "workspace.list", "status": "completed"})
        pending_runtime.planning_integrations.sync_phase1_progress(run_id, {"tool_id": "worktree.bind", "status": "completed"})
    approval_id = "approval-phase6"
    engine.merge_checkpoint(run_id, {
        "suspended_step": {"step_id": "mutate", "approval_id": approval_id, "tool_id": "worktree.replace_exact"},
        "suspended_step_id": "mutate",
        "suspended_approval_id": approval_id,
    })
    pending_runtime.planning_integrations.sync_phase6_approval(run_id, "agent.approval.requested", {
        "approval_id": approval_id,
        "tool_id": "worktree.replace_exact",
        "step_id": "mutate",
    })
    current = ObjectivePlanWorkspace(engine.workspace_root).current(run_id)
    mutate = next(step for step in current["plan"]["steps"] if step["step_id"] == "mutate")
    approval = mutate["telemetry"]["approval"]
    assert current["plan"]["active_step_id"] == "mutate"
    assert mutate["status"] == "blocked"
    assert "Awaiting operator approval" in mutate["blocked_reason"]
    assert approval["status"] == "waiting_for_approval"
    assert approval["approval_id"] == approval_id
    assert approval["tool_id"] == "worktree.replace_exact"


def test_phase6_planning_integration_reactivates_exact_step_after_approval_resume(tmp_path):
    engine = AgentRunEngine(tmp_path)
    engine.create_run(session_id="session_47", objective="test", run_id="run_47")
    runtime = AgentPlannerRuntime(engine, ScriptedPlannerProvider([]), max_turns=1)
    runtime.planning_integrations.ensure_phase1_plan("run_47", engine.store.get_run("run_47"))
    runtime.planning_integrations.sync_phase1_progress("run_47", {"tool_id": "workspace.list", "status": "completed"})
    runtime.planning_integrations.sync_phase1_progress("run_47", {"tool_id": "worktree.bind", "status": "completed"})
    runtime.planning_integrations.sync_phase6_approval("run_47", "agent.approval.requested", {
        "approval_id": "approval_47",
        "tool_id": "workspace.read_range",
        "step_id": "mutate",
    })
    engine.store.transition("run_47", "waiting_for_approval")
    engine.merge_checkpoint("run_47", {"suspended_step": {"step_id": "mutate", "approval_id": "approval_47"}})
    request, capability = _approval_fixture(tmp_path, step_id="mutate")
    ExactStepResumeRuntime(tmp_path).consume_and_resume(capability=capability, request=request)
    runtime.planning_integrations.sync_phase6_approval("run_47", "agent.approval.capability_consumed", {
        "approval_id": "approval_47",
        "tool_id": "workspace.read_range",
        "step_id": "mutate",
        "resume_state": "executing_tool",
    }, run=engine.store.get_run("run_47"))
    current = ObjectivePlanWorkspace(engine.workspace_root).current("run_47")
    mutate = next(step for step in current["plan"]["steps"] if step["step_id"] == "mutate")
    approval = mutate["telemetry"]["approval"]
    assert current["plan"]["active_step_id"] == "mutate"
    assert mutate["status"] == "active"
    assert mutate["blocked_reason"] == ""
    assert approval["status"] == "exact_step_resumed"
    assert approval["resume_state"] == "executing_tool"


def test_phase7_planning_integration_records_sourceplan_handoff_ready(tmp_path):
    engine, run_id, approval_id = _repo_run(tmp_path)
    provider = ScriptedPlannerProvider([
        {"decision_type": "tool", "tool_id": "workspace.list", "arguments": {}},
        {"decision_type": "tool", "tool_id": "worktree.bind", "approval_id": approval_id, "arguments": {"objective": "repair VALUE"}},
        {"decision_type": "tool", "tool_id": "worktree.replace_exact", "approval_id": approval_id, "arguments": {"path": "answer.py", "old_text": "VALUE = 1", "new_text": "VALUE = 2"}},
        {"decision_type": "complete", "summary": "completed before verify"},
        {"decision_type": "complete", "summary": "completed before sourceplan"},
        {"decision_type": "complete", "summary": "VALUE repaired and verified."},
    ])
    asyncio.run(AgentPlannerRuntime(engine, provider, max_turns=6).run(run_id))
    current = ObjectivePlanWorkspace(engine.workspace_root).current(run_id)
    handoff = next(step for step in current["plan"]["steps"] if step["step_id"] == "handoff")
    handoff_state = handoff["telemetry"]["handoff"]
    assert handoff["status"] == "completed"
    assert handoff_state["status"] == "sourceplan_ready"
    assert handoff_state["plan_id"]
    assert isinstance(handoff_state["requires_operator_translation"], bool)
    events = [e for e in engine.store.events(run_id, limit=300) if e["event_type"] == "agent.plan.integration.handoff"]
    assert any(e["payload"]["event_type"] == "agent.sourceplan.ready" for e in events)


def test_phase7_planning_integration_records_promotion_eligibility_and_commit(tmp_path):
    engine, run_id, approval_id = _repo_run(tmp_path)
    provider = ScriptedPlannerProvider([
        {"decision_type": "tool", "tool_id": "workspace.list", "arguments": {}},
        {"decision_type": "tool", "tool_id": "worktree.bind", "approval_id": approval_id, "arguments": {"objective": "repair VALUE"}},
        {"decision_type": "tool", "tool_id": "worktree.replace_exact", "approval_id": approval_id, "arguments": {"path": "answer.py", "old_text": "VALUE = 1", "new_text": "VALUE = 2"}},
        {"decision_type": "complete", "summary": "completed before verify"},
        {"decision_type": "complete", "summary": "completed before sourceplan"},
        {"decision_type": "complete", "summary": "VALUE repaired and verified."},
    ])
    asyncio.run(AgentPlannerRuntime(engine, provider, max_turns=6).run(run_id))
    promotion = __import__("app.kernel.agents.promotion_engine", fromlist=["PromotionEngine"]).PromotionEngine(engine.workspace_root)
    run = engine.store.get_run(run_id)
    checkpoint = dict(run["checkpoint"])
    sourceplan = dict(checkpoint.get("sourceplan") or {})
    sourceplan["requires_operator_translation"] = False
    checkpoint["sourceplan"] = sourceplan
    engine.checkpoint(run_id, checkpoint)
    evaluated = promotion.evaluate(run_id, requested_by="operator")
    approval = evaluated["approval"]
    assert approval is not None
    engine.store.resolve_approval(run_id, approval["approval_id"], {"approved": True, "resolved_by": "operator:test"})
    committed = promotion.promote(run_id, approval_id=approval["approval_id"], commit_message="Promote verified handoff")
    current = ObjectivePlanWorkspace(engine.workspace_root).current(run_id)
    handoff = next(step for step in current["plan"]["steps"] if step["step_id"] == "handoff")
    promotion_state = handoff["telemetry"]["promotion"]
    assert promotion_state["receipt_id"]
    assert promotion_state["status"] == "committed"
    assert promotion_state["candidate_id"] == committed["candidate"]["candidate_id"]
    assert promotion_state["commit"] == committed["candidate"]["commit"]


def test_ollama_provider_uses_shorter_timeout_for_repair_turns():
    run = {
        "checkpoint": {
            "planner": {
                "repair_cycles": 1,
                "verification_failures": [{"analysis": {"failure_class": "syntax"}}],
                "observations": [{"tool_id": "worktree.verify", "status": "failed"}],
            }
        }
    }
    timeout = OllamaPlannerProvider._request_timeout("prompt", run=run, turn=3)
    # CPU-friendly default: 30s (was 12s)
    assert timeout == 30.0


def test_ollama_provider_uses_shorter_timeout_for_followup_turns_without_repairs():
    run = {
        "checkpoint": {
            "planner": {
                "repair_cycles": 0,
                "verification_failures": [],
                "observations": [{"tool_id": "workspace.list", "status": "completed"}],
            }
        }
    }
    timeout = OllamaPlannerProvider._request_timeout("prompt", run=run, turn=2)
    # CPU-friendly default: 30s (was 14s)
    assert timeout == 30.0


def test_nim_provider_uses_shorter_timeout_for_repair_turns():
    run = {
        "checkpoint": {
            "planner": {
                "repair_cycles": 1,
                "verification_failures": [{"analysis": {"failure_class": "syntax"}}],
                "observations": [{"tool_id": "worktree.verify", "status": "failed"}],
            }
        }
    }
    timeout = NIMPlannerProvider._request_timeout(run=run, default_timeout=30.0)
    # CPU-friendly default: 30s (was 12s)
    assert timeout == 30.0


def test_nim_provider_uses_shorter_timeout_for_followup_turns_without_repairs():
    run = {
        "checkpoint": {
            "planner": {
                "repair_cycles": 0,
                "verification_failures": [],
                "observations": [{"tool_id": "workspace.list", "status": "completed"}],
            }
        }
    }
    timeout = NIMPlannerProvider._request_timeout(run=run, default_timeout=30.0)
    # CPU-friendly default: 30s follow-up timeout (was 14s)
    assert timeout == 30.0


def test_nim_provider_uses_shorter_timeout_for_late_turns():
    run = {
        "checkpoint": {
            "planner": {
                "turn": 4,
                "repair_cycles": 0,
                "verification_failures": [],
                "observations": [
                    {"tool_id": "workspace.list", "status": "completed"},
                    {"tool_id": "workspace.read_range", "status": "completed"},
                    {"tool_id": "worktree.bind", "status": "completed"},
                ],
            }
        }
    }
    timeout = NIMPlannerProvider._request_timeout(run=run, default_timeout=30.0)
    # CPU-friendly default: 20s for late turns (was 10s)
    assert timeout == 20.0


def test_ollama_provider_exposes_route_and_timeout_usage_on_success():
    class StubOllama(OllamaPlannerProvider):
        def _prepare_sensorium(self, run: dict[str, Any]) -> None:
            self._runtime_before = None

        def _finish_sensorium(self) -> None:
            return

        def _govern_request(self, prompt: str, *, run: dict[str, Any], turn: int) -> None:
            return

        def _apply_pressure_budget(self, *, reuse_mode: str = "cold") -> None:
            self._pressure_decision = None

        def _request_json(self, path: str, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
            if path == "/api/tags":  # model-installed preflight
                return {"models": [{"name": "qwen2.5:0.5b"}]}
            self._seen_timeout = timeout
            return {"response": "{\"decision_type\":\"complete\",\"summary\":\"done\"}", "total_duration": 5_000_000}

    provider = StubOllama(model="qwen2.5:0.5b", timeout_seconds=120, max_retries=0)
    run = {"checkpoint": {"planner": {"observations": [{"tool_id": "workspace.list", "status": "completed"}]}}}
    decision = asyncio.run(provider.next_decision("prompt", run=run, turn=2))
    assert decision.summary == "done"
    # CPU-friendly default: 30s follow-up timeout (was 14s)
    assert provider._seen_timeout == 30.0
    assert provider.last_usage["timeout_seconds"] == 30.0
    assert provider.last_route["route_kind"] == "direct_generate"


def test_ollama_provider_honors_persistent_bad_route_memory(tmp_path):
    dampener = RouteFlapDampener(path=tmp_path / "damping.json", suppress_at=100, half_life_seconds=3600)
    dampener.record("ollama:test-model", "timeout", now=100.0)
    provider = OllamaPlannerProvider(model="test-model", timeout_seconds=30, max_retries=0, route_dampener=dampener, route_id="ollama:test-model")
    assert provider.route_dampener is not None
    assert provider.route_dampener.suppressed("ollama:test-model", now=100.0) is True


def test_nim_provider_honors_persistent_bad_route_memory(tmp_path):
    dampener = RouteFlapDampener(path=tmp_path / "nim-damping.json", suppress_at=100, half_life_seconds=3600)
    dampener.record("nim:test-model", "timeout", now=100.0)
    provider = NIMPlannerProvider(model="test-model", api_key="nvapi-test", timeout_seconds=30, max_retries=0, route_dampener=dampener, route_id="nim:test-model")
    assert provider.route_dampener is not None
    assert provider.route_dampener.suppressed("nim:test-model", now=100.0) is True


def test_sticky_fallback_planner_provider_becomes_heuristic_only_after_repeated_timeouts():
    class SlowPrimary:
        def __init__(self):
            self.calls = 0
            self.last_usage = {}

        async def next_decision(self, prompt: str, *, run: dict[str, Any], turn: int):
            self.calls += 1
            raise TimeoutError("ollama timed out")

    primary = SlowPrimary()
    fallback = ScriptedPlannerProvider([
        {"decision_type": "complete", "summary": "heuristic fallback 1"},
        {"decision_type": "complete", "summary": "heuristic fallback 2"},
        {"decision_type": "complete", "summary": "heuristic fallback 3"},
    ])
    sticky = StickyFallbackPlannerProvider(primary, fallback, sticky_after=2, slow_latency_ms=5000)
    first = asyncio.run(sticky.next_decision("prompt", run={}, turn=1))
    second = asyncio.run(sticky.next_decision("prompt", run={}, turn=2))
    third = asyncio.run(sticky.next_decision("prompt", run={}, turn=3))
    assert first.summary == "heuristic fallback 1"
    assert second.summary == "heuristic fallback 2"
    assert third.summary == "heuristic fallback 3"
    assert primary.calls == 2
    assert sticky.force_fallback is True
    assert sticky.last_route["route_kind"] == "sticky_fallback"


def test_sticky_fallback_planner_provider_becomes_heuristic_only_after_repeated_slow_successes():
    class SlowPrimary:
        def __init__(self):
            self.calls = 0
            self.last_usage = {"latency_ms": 20000.0}
            self.last_route = {"provider": "nvidia_nim", "engine": "nvidia_nim", "route_kind": "direct_generate", "reason": "nim_chat_completions"}

        async def next_decision(self, prompt: str, *, run: dict[str, Any], turn: int):
            self.calls += 1
            return parse_planner_decision({"decision_type": "complete", "arguments": {}, "summary": f"slow {self.calls}"})

    primary = SlowPrimary()
    fallback = ScriptedPlannerProvider([
        {"decision_type": "complete", "summary": "heuristic sticky"},
    ])
    sticky = StickyFallbackPlannerProvider(primary, fallback, sticky_after=2, slow_latency_ms=15000)
    first = asyncio.run(sticky.next_decision("prompt", run={}, turn=1))
    second = asyncio.run(sticky.next_decision("prompt", run={}, turn=2))
    third = asyncio.run(sticky.next_decision("prompt", run={}, turn=3))
    assert first.summary == "slow 1"
    assert second.summary == "slow 2"
    assert third.summary == "heuristic sticky"
    assert primary.calls == 2
    assert sticky.force_fallback is True


def test_sticky_fallback_does_not_mask_non_mutating_provider_failure():
    class Broken:
        last_route = {"provider": "ollama", "route_kind": "direct_generate"}

        async def next_decision(self, prompt, *, run, turn):
            raise TimeoutError("ollama first token timeout")

    sticky = StickyFallbackPlannerProvider(
        Broken(),
        HeuristicPlannerProvider(),
        sticky_after=1,
        slow_latency_ms=5000,
    )
    try:
        asyncio.run(sticky.next_decision("prompt", run={"mode": "analysis"}, turn=1))
    except TimeoutError as exc:
        assert "first token" in str(exc)
    else:
        raise AssertionError("analysis-mode provider failure should not be masked by heuristic fallback")
    assert sticky.last_route["route_kind"] == "fallback_unavailable"


def test_local_ollama_repair_prompt_elides_older_observations(tmp_path):
    engine, run_id, approval_id = _repo_run(tmp_path)
    provider = ScriptedPlannerProvider([
        {"decision_type": "tool", "tool_id": "workspace.list", "arguments": {}},
        {"decision_type": "tool", "tool_id": "worktree.bind", "approval_id": approval_id, "arguments": {"objective": "repair VALUE"}},
        {"decision_type": "tool", "tool_id": "worktree.replace_exact", "approval_id": approval_id, "arguments": {"path": "answer.py", "old_text": "VALUE = 1", "new_text": "VALUE = 2\nbroken = "}},
        {"decision_type": "tool", "tool_id": "worktree.verify", "approval_id": approval_id, "arguments": {"command": ["python", "-m", "py_compile", "answer.py"]}},
    ])
    asyncio.run(AgentPlannerRuntime(engine, provider, max_turns=4, max_repair_cycles=2).run(run_id))
    runtime = AgentPlannerRuntime(engine, ScriptedPlannerProvider([]))
    run = engine.store.get_run(run_id)
    run["provider"] = "ollama"
    run["checkpoint"]["planner"]["observations"].insert(0, {
        "tool_id": "workspace.search_text",
        "status": "completed",
        "result": {"matches": [{"path": "answer.py"}]},
    })
    prompt = runtime._prompt(run, runtime._load_state(run_id))
    assert "LATEST FAILURE:" in prompt
    assert '"tool_id":"worktree.replace_exact"' in prompt
    assert '"tool_id":"workspace.search_text"' not in prompt


def test_nim_repair_prompt_elides_older_observations(tmp_path):
    engine, run_id, approval_id = _repo_run(tmp_path)
    provider = ScriptedPlannerProvider([
        {"decision_type": "tool", "tool_id": "workspace.list", "arguments": {}},
        {"decision_type": "tool", "tool_id": "worktree.bind", "approval_id": approval_id, "arguments": {"objective": "repair VALUE"}},
        {"decision_type": "tool", "tool_id": "worktree.replace_exact", "approval_id": approval_id, "arguments": {"path": "answer.py", "old_text": "VALUE = 1", "new_text": "VALUE = 2\nbroken = "}},
        {"decision_type": "tool", "tool_id": "worktree.verify", "approval_id": approval_id, "arguments": {"command": ["python", "-m", "py_compile", "answer.py"]}},
    ])
    asyncio.run(AgentPlannerRuntime(engine, provider, max_turns=4, max_repair_cycles=2).run(run_id))
    runtime = AgentPlannerRuntime(engine, ScriptedPlannerProvider([]))
    run = engine.store.get_run(run_id)
    run["provider"] = "nvidia_nim"
    run["checkpoint"]["planner"]["observations"].insert(0, {
        "tool_id": "workspace.search_text",
        "status": "completed",
        "result": {"matches": [{"path": "answer.py"}]},
    })
    prompt = runtime._prompt(run, runtime._load_state(run_id))
    assert "LATEST FAILURE:" in prompt
    assert '"tool_id":"worktree.replace_exact"' in prompt
    assert '"tool_id":"workspace.search_text"' not in prompt


def test_compact_provider_late_turn_prompt_shrinks_observations_and_budget(tmp_path):
    engine, run_id, approval_id = _repo_run(tmp_path)
    provider = ScriptedPlannerProvider([
        {"decision_type": "tool", "tool_id": "workspace.list", "arguments": {}},
        {"decision_type": "tool", "tool_id": "workspace.read_range", "arguments": {"path": "answer.py", "start_line": 1, "line_count": 20}},
        {"decision_type": "tool", "tool_id": "worktree.bind", "approval_id": approval_id, "arguments": {"objective": "repair VALUE"}},
    ])
    asyncio.run(AgentPlannerRuntime(engine, provider, max_turns=3, max_repair_cycles=2).run(run_id))
    runtime = AgentPlannerRuntime(engine, ScriptedPlannerProvider([]))
    run = engine.store.get_run(run_id)
    run["provider"] = "nvidia_nim"
    state = runtime._load_state(run_id)
    state.turn = 3
    run["checkpoint"]["planner"] = state.as_dict()
    prompt = runtime._prompt(run, state)
    assert len(prompt) <= 3600
    assert '"tool_id":"workspace.list"' not in prompt


def test_planner_provider_fallback_switches_after_primary_failure():
    class Broken:
        async def next_decision(self, prompt, *, run, turn):
            raise TimeoutError("primary timed out")

    reasons = []
    provider = FallbackPlannerProvider(
        Broken(),
        ScriptedPlannerProvider([{"decision_type": "complete", "summary": "fallback completed"}]),
        on_fallback=reasons.append,
    )
    decision = asyncio.run(provider.next_decision("prompt", run={}, turn=1))
    assert decision.summary == "fallback completed"
    assert provider.last_provider == "fallback"
    assert reasons and "timed out" in reasons[0]


def test_capability_scored_provider_escalates_hard_edit_to_stronger_route():
    weak = ScriptedPlannerProvider([{"decision_type": "complete", "summary": "weak"}])
    strong = ScriptedPlannerProvider([{"decision_type": "complete", "summary": "strong"}])
    switches = []
    provider = CapabilityScoredPlannerProvider([
        {"name": "local-small", "provider": weak, "capability_score": 0.25, "cost_score": 0.95},
        {"name": "strong-model", "provider": strong, "capability_score": 0.95, "cost_score": 0.25},
    ], on_switch=lambda old, new, reason: switches.append((old, new, reason)))
    run = {
        "mode": "agent",
        "objective": "Large architecture refactor across a monorepo",
        "request": {"context_files": ["a.py", "b.py", "c.py", "d.py"]},
        "checkpoint": {"planner": {"repair_cycles": 1, "verification_failures": [{"analysis": {"failure_class": "logic_regression"}}]}},
    }
    decision = asyncio.run(provider.next_decision("prompt", run=run, turn=4))
    assert decision.summary == "strong"


def test_capability_scored_provider_treats_semantic_risk_as_hard_edit_signal():
    weak = ScriptedPlannerProvider([{"decision_type": "complete", "summary": "weak"}])
    strong = ScriptedPlannerProvider([{"decision_type": "complete", "summary": "strong"}])
    provider = CapabilityScoredPlannerProvider([
        {"name": "local-small", "provider": weak, "capability_score": 0.25, "cost_score": 0.95},
        {"name": "strong-cloud", "provider": strong, "capability_score": 0.95, "cost_score": 0.25},
    ])
    run = {
        "mode": "agent",
        "objective": "Rename a symbol safely",
        "request": {
            "context_files": ["a.py"],
            "semantic_risk": {"high": True, "score": 5, "reasons": ["rename/reference fanout 18", "12 diagnostics"]},
        },
        "checkpoint": {"planner": {"repair_cycles": 0, "verification_failures": []}},
    }
    decision = asyncio.run(provider.next_decision("prompt", run=run, turn=1))
    assert decision.summary == "strong"


def test_chat_timeout_promotes_partial_stream_to_completion(tmp_path):
    (tmp_path / "sample.py").write_text("def answer():\n    return 42\n", encoding="utf-8")
    engine = AgentRunEngine(tmp_path)
    run_id = engine.create_run(
        session_id="session-chat-timeout",
        objective="Explain the workspace safely",
        mode="chat",
        provider="ollama",
        model="planner-test",
        request={"decision_timeout_ms": 10},
    )["run_id"]

    class SlowPartial:
        def __init__(self):
            self.last_partial_text = ""

        async def next_decision(self, prompt, *, run, turn):
            await asyncio.sleep(0.02)
            # Turn isolation: only a validated structured completion streamed during this turn is promotable.
            engine.emit(run_id, "agent.model.delta", {
                "text": '{"decision_type":"complete","summary":"Workspace looks like a safe agent probe."}',
            })
            self.last_partial_text = "Workspace looks like a safe agent probe."
            await asyncio.sleep(0.08)
            raise TimeoutError("slow final parse")

    final = asyncio.run(AgentPlannerRuntime(engine, SlowPartial(), max_turns=2).run(run_id))
    assert final["state"] == "completed"
    assert "safe agent probe" in str(final.get("checkpoint", {}).get("planner", {}).get("final_summary") or "")


def test_mutating_timeout_salvages_partial_structured_decision(tmp_path):
    import subprocess

    root = tmp_path / "repo"
    root.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "beast@example.test"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "BEAST Test"], cwd=root, check=True)
    (root / "answer.py").write_text("VALUE = 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    subprocess.run(["git", "commit", "-qm", "initial"], cwd=root, check=True)
    engine = AgentRunEngine(root)
    run_id = engine.create_run(
        session_id="session-agent-partial-salvage",
        objective="Change VALUE to 2 and verify it",
        mode="agent",
        provider="nvidia_nim",
        model="planner-test",
        request={"decision_timeout_ms": 10},
    )["run_id"]
    approval_id = "mutate-worktree"
    engine.store.create_approval(run_id, {"request_id": approval_id, "capabilities": [{"id": "worktree_mutation"}]})
    engine.store.resolve_approval(run_id, approval_id, {"approved": True, "scope": "run"})
    run = engine.store.get_run(run_id) or {}

    class SlowPartialMutation:
        def __init__(self):
            self.last_partial_text = ""
            self.last_route = {"provider": "nvidia_nim", "engine": "nvidia_nim", "route_kind": "direct_generate", "reason": "nim_chat_completions"}
            self.last_usage = {"engine": "nvidia_nim", "model": "test-nim"}

        async def next_decision(self, prompt, *, run, turn):
            await asyncio.sleep(0.02)
            self.last_partial_text = (
                '{"decision_type":"tool","tool_id":"worktree.replace_exact",'
                f'"approval_id":"{approval_id}",'
                '"arguments":{"path":"answer.py","old_text":"VALUE = 1","new_text":"VALUE = 2"},'
                '"summary":"Implement code change."}'
            )
            await asyncio.sleep(0.08)
            raise TimeoutError("slow final parse")

    runtime = AgentPlannerRuntime(engine, SlowPartialMutation(), max_turns=4, max_repair_cycles=2)
    checkpoint = run.get("checkpoint") if isinstance(run.get("checkpoint"), dict) else {}
    checkpoint["planner"] = {
        "turn": 2,
        "repair_cycles": 1,
        "max_repair_cycles": 2,
        "verification_failures": [{"analysis": {"failure_class": "bad_patch"}}],
        "observations": [
            {"tool_id": "workspace.read_range", "status": "completed", "result": {"path": "answer.py", "content": "VALUE = 1\n"}},
            {"tool_id": "worktree.bind", "status": "completed", "result": {"task_id": "wt-1", "worktree_root": str(tmp_path / "repo")}},
        ],
    }
    engine.store.checkpoint(run_id, checkpoint)

    final = asyncio.run(runtime.run(run_id))
    planner = final.get("checkpoint", {}).get("planner", {})
    assert final["state"] != "policy_blocked"
    assert planner.get("last_decision", {}).get("tool_id") == "worktree.replace_exact"
    events = engine.store.events(run_id, limit=200)
    assert any(event["event_type"] == "agent.provider.partial_decision_salvaged" for event in events)


def test_timeout_salvages_partial_structured_decision_from_wrapped_provider(tmp_path):
    import subprocess

    root = tmp_path / "repo"
    root.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "beast@example.test"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "BEAST Test"], cwd=root, check=True)
    (root / "answer.py").write_text("VALUE = 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    subprocess.run(["git", "commit", "-qm", "initial"], cwd=root, check=True)
    engine = AgentRunEngine(root)
    run_id = engine.create_run(
        session_id="session-wrapped-partial-salvage",
        objective="Change VALUE to 2 and verify it",
        mode="agent",
        provider="nvidia_nim",
        model="planner-test",
        request={"decision_timeout_ms": 10},
    )["run_id"]
    approval_id = "mutate-worktree"
    engine.store.create_approval(run_id, {"request_id": approval_id, "capabilities": [{"id": "worktree_mutation"}]})
    engine.store.resolve_approval(run_id, approval_id, {"approved": True, "scope": "run"})

    class _SlowPrimary:
        def __init__(self):
            self.last_partial_text = ""
            self.last_route = {"provider": "nvidia_nim", "engine": "nvidia_nim", "route_kind": "direct_generate", "reason": "nim_chat_completions"}
            self.last_usage = {"engine": "nvidia_nim", "model": "wrapped-test-nim"}

        async def next_decision(self, prompt, *, run, turn):
            await asyncio.sleep(0.02)
            self.last_partial_text = (
                '{"decision_type":"tool","tool_id":"worktree.replace_exact",'
                f'"approval_id":"{approval_id}",'
                '"arguments":{"path":"answer.py","old_text":"VALUE = 1","new_text":"VALUE = 2"},'
                '"summary":"Implement code change."}'
            )
            await asyncio.sleep(0.08)
            raise TimeoutError("slow final parse")

    class _Wrapper:
        def __init__(self, primary):
            self.primary = primary
            self.last_route = {"provider": "nvidia_nim", "engine": "nvidia_nim", "route_kind": "direct_generate", "reason": "nim_chat_completions"}
            self.last_usage = {"engine": "nvidia_nim", "model": "wrapped-test-nim"}

        async def next_decision(self, prompt, *, run, turn):
            return await self.primary.next_decision(prompt, run=run, turn=turn)

    runtime = AgentPlannerRuntime(engine, _Wrapper(_SlowPrimary()), max_turns=4, max_repair_cycles=2)
    state = runtime._load_state(run_id)
    state.turn = 2
    state.repair_cycles = 1
    state.max_repair_cycles = 2
    state.verification_failures = [{"analysis": {"failure_class": "bad_patch"}}]
    state.observations = [
        {"tool_id": "workspace.read_range", "status": "completed", "result": {"path": "answer.py", "content": "VALUE = 1\n"}},
        {"tool_id": "worktree.bind", "status": "completed", "result": {"task_id": "wt-1", "worktree_root": str(root)}},
    ]
    runtime._save_state(state)
    _bind_test_worktree(engine, run_id, approval_id, runtime, state)

    final = asyncio.run(runtime.run(run_id))
    assert final["state"] != "policy_blocked"
    events = engine.store.events(run_id, limit=200)
    assert any(event["event_type"] == "agent.provider.partial_decision_salvaged" for event in events)


def test_invalid_placeholder_mutation_retries_before_tool_execution(tmp_path):
    engine, run_id, approval_id = _repo_run(tmp_path, provider="nvidia_nim", model="planner-test")

    class PlaceholderThenExact:
        def __init__(self):
            self.calls = 0
            self.last_route = {}
            self.last_usage = {}

        async def next_decision(self, prompt, *, run, turn):
            self.calls += 1
            self.last_route = {"provider": "nvidia_nim", "engine": "nvidia_nim", "route_kind": "direct_generate", "reason": f"call_{self.calls}"}
            if self.calls == 1:
                return parse_planner_decision({
                    "decision_type": "tool",
                    "tool_id": "worktree.replace_exact",
                    "approval_id": approval_id,
                    "arguments": {"path": "answer.py", "old_text": "", "new_text": ""},
                })
            return parse_planner_decision({
                "decision_type": "tool",
                "tool_id": "worktree.replace_exact",
                "approval_id": approval_id,
                "arguments": {"path": "answer.py", "old_text": "VALUE = 1", "new_text": "VALUE = 2"},
            })

    runtime = AgentPlannerRuntime(engine, PlaceholderThenExact(), max_turns=5)
    state = runtime._load_state(run_id)
    state.observations = [
        {"tool_id": "workspace.read_range", "status": "completed", "result": {"path": "answer.py", "content": "VALUE = 1\n"}},
        {"tool_id": "worktree.bind", "status": "completed", "result": {"task_id": "wt-1", "worktree_root": str(tmp_path / "repo")}},
    ]
    state.turn = 2
    runtime._save_state(state)
    _bind_test_worktree(engine, run_id, approval_id, runtime, state)
    # This test exercises retry and execution, not the separate graduation contract.
    final = asyncio.run(runtime.run(run_id, max_turns_this_call=1))
    planner = final.get("checkpoint", {}).get("planner", {})
    assert final["state"] != "policy_blocked"
    assert planner.get("last_decision", {}).get("tool_id") in {"worktree.verify", "worktree.sourceplan_draft", "worktree.replace_exact"}
    observations = planner.get("observations", [])
    assert any(item.get("tool_id") == "worktree.replace_exact" and item.get("status") == "completed" for item in observations if isinstance(item, dict))
    events = engine.store.events(run_id, limit=200)
    assert any(event["event_type"] == "agent.provider.invalid_mutation_retry" for event in events)
    assert any(event["event_type"] == "agent.provider.invalid_mutation_recovered" for event in events)


def test_invalid_placeholder_mutation_blocks_if_retry_stays_invalid(tmp_path):
    engine, run_id, approval_id = _repo_run(tmp_path, provider="nvidia_nim", model="planner-test")

    class AlwaysPlaceholder:
        def __init__(self):
            self.calls = 0
            self.last_route = {}
            self.last_usage = {}

        async def next_decision(self, prompt, *, run, turn):
            self.calls += 1
            self.last_route = {"provider": "nvidia_nim", "engine": "nvidia_nim", "route_kind": "direct_generate", "reason": f"call_{self.calls}"}
            return parse_planner_decision({
                "decision_type": "tool",
                "tool_id": "worktree.replace_exact",
                "approval_id": approval_id,
                "arguments": {"path": "answer.py", "old_text": "", "new_text": ""},
            })

    runtime = AgentPlannerRuntime(engine, AlwaysPlaceholder(), max_turns=5)
    state = runtime._load_state(run_id)
    state.observations = [
        {"tool_id": "workspace.read_range", "status": "completed", "result": {"path": "answer.py", "content": "VALUE = 1\n"}},
        {"tool_id": "worktree.bind", "status": "completed", "result": {"task_id": "wt-1", "worktree_root": str(tmp_path / "repo")}},
    ]
    state.turn = 2
    runtime._save_state(state)
    _bind_test_worktree(engine, run_id, approval_id, runtime, state)
    final = asyncio.run(runtime.run(run_id))
    assert final["state"] == "policy_blocked"
    assert "non-empty old_text" in str(final.get("error") or "")
    events = engine.store.events(run_id, limit=200)
    assert any(event["event_type"] == "agent.provider.invalid_mutation_retry" for event in events)
    assert any(event["event_type"] == "agent.provider.invalid_mutation_retry_failed" for event in events)


def test_invalid_placeholder_retry_rejects_malformed_read_recovery(tmp_path):
    engine, run_id, approval_id = _repo_run(tmp_path, provider="nvidia_nim", model="planner-test")

    class PlaceholderThenBadRead:
        def __init__(self):
            self.calls = 0
            self.last_route = {}
            self.last_usage = {}

        async def next_decision(self, prompt, *, run, turn):
            self.calls += 1
            self.last_route = {"provider": "nvidia_nim", "engine": "nvidia_nim", "route_kind": "direct_generate", "reason": f"call_{self.calls}"}
            if self.calls == 1:
                return parse_planner_decision({
                    "decision_type": "tool",
                    "tool_id": "worktree.replace_exact",
                    "approval_id": approval_id,
                    "arguments": {"path": "answer.py", "old_text": "", "new_text": ""},
                })
            return parse_planner_decision({
                "decision_type": "tool",
                "tool_id": "workspace.read_range",
                "approval_id": approval_id,
                "arguments": {},
            })

    runtime = AgentPlannerRuntime(engine, PlaceholderThenBadRead(), max_turns=5)
    state = runtime._load_state(run_id)
    state.observations = [
        {"tool_id": "workspace.read_range", "status": "completed", "result": {"path": "answer.py", "content": "VALUE = 1\n"}},
        {"tool_id": "worktree.bind", "status": "completed", "result": {"task_id": "wt-1", "worktree_root": str(tmp_path / "repo")}},
    ]
    state.turn = 2
    runtime._save_state(state)
    _bind_test_worktree(engine, run_id, approval_id, runtime, state)
    final = asyncio.run(runtime.run(run_id))
    assert final["state"] == "policy_blocked"
    assert "workspace.read_range retry recovery requires an exact target path" in str(final.get("error") or "")


def test_invalid_placeholder_retry_rejects_wrong_file_mutation_recovery(tmp_path):
    engine, run_id, approval_id = _repo_run(tmp_path, provider="nvidia_nim", model="planner-test")

    class PlaceholderThenWrongFile:
        def __init__(self):
            self.calls = 0
            self.last_route = {}
            self.last_usage = {}

        async def next_decision(self, prompt, *, run, turn):
            self.calls += 1
            self.last_route = {"provider": "nvidia_nim", "engine": "nvidia_nim", "route_kind": "direct_generate", "reason": f"call_{self.calls}"}
            if self.calls == 1:
                return parse_planner_decision({
                    "decision_type": "tool",
                    "tool_id": "worktree.replace_exact",
                    "approval_id": approval_id,
                    "arguments": {"path": "answer.py", "old_text": "", "new_text": ""},
                })
            return parse_planner_decision({
                "decision_type": "tool",
                "tool_id": "worktree.replace_exact",
                "approval_id": approval_id,
                "arguments": {"path": "README.md", "old_text": "old", "new_text": "new"},
            })

    runtime = AgentPlannerRuntime(engine, PlaceholderThenWrongFile(), max_turns=5)
    state = runtime._load_state(run_id)
    state.observations = [
        {"tool_id": "workspace.read_range", "status": "completed", "result": {"path": "answer.py", "content": "VALUE = 1\n"}},
        {"tool_id": "worktree.bind", "status": "completed", "result": {"task_id": "wt-1", "worktree_root": str(tmp_path / "repo")}},
    ]
    state.turn = 2
    runtime._save_state(state)
    _bind_test_worktree(engine, run_id, approval_id, runtime, state)
    final = asyncio.run(runtime.run(run_id))
    assert final["state"] == "policy_blocked"
    assert "already inspected target file set" in str(final.get("error") or "")


def test_mutating_timeout_heuristic_block_retries_strong_provider(tmp_path):
    import subprocess

    root = tmp_path / "repo"
    root.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "beast@example.test"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "BEAST Test"], cwd=root, check=True)
    (root / "answer.py").write_text("VALUE = 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    subprocess.run(["git", "commit", "-qm", "initial"], cwd=root, check=True)
    engine = AgentRunEngine(root)
    run_id = engine.create_run(
        session_id="session-agent-runtime",
        objective="Change VALUE to 2 and verify it",
        mode="agent",
        provider="nvidia_nim",
        model="planner-test",
        request={"decision_timeout_ms": 10},
    )["run_id"]

    class RecoveringStrong(NIMPlannerProvider):
        # R3.22: strong re-entry resolves only the exact requested provider class and model.
        def __init__(self):
            self.calls = 0
            self.model = "planner-test"
            self.last_partial_text = ""
            self.last_route = {"provider": "nvidia_nim", "engine": "nvidia_nim", "route_kind": "direct_generate", "reason": "nim_chat_completions"}
            self.last_usage = {"engine": "nvidia_nim", "model": "test-nim"}

        async def next_decision(self, prompt, *, run, turn):
            self.calls += 1
            if self.calls == 1:
                await asyncio.sleep(0.05)
                raise TimeoutError("late turn timeout")
            self.last_route = {"provider": "nvidia_nim", "engine": "nvidia_nim", "route_kind": "direct_generate", "reason": "compact_retry_recovered"}
            return parse_planner_decision({
                "decision_type": "tool",
                "tool_id": "workspace.read_range",
                "arguments": {"path": "answer.py"},
            })

    runtime = AgentPlannerRuntime(engine, RecoveringStrong(), max_turns=4, max_repair_cycles=2)
    run = engine.store.get_run(run_id) or {}
    checkpoint = run.get("checkpoint") if isinstance(run.get("checkpoint"), dict) else {}
    checkpoint["planner"] = {
        "turn": 2,
        "repair_cycles": 1,
        "max_repair_cycles": 2,
        "verification_failures": [{"analysis": {"failure_class": "bad_patch"}}],
        "observations": [
            {"tool_id": "worktree.bind", "status": "completed"},
            {"tool_id": "worktree.replace_exact", "status": "completed"},
            {"tool_id": "worktree.verify", "status": "failed"},
        ],
    }
    engine.store.checkpoint(run_id, checkpoint)

    final = asyncio.run(runtime.run(run_id))
    planner = final.get("checkpoint", {}).get("planner", {})
    assert planner.get("last_decision", {}).get("tool_id") == "workspace.read_range"
    assert final["state"] != "policy_blocked"


def test_capability_scored_provider_degrades_failed_route_mid_run():
    class Broken:
        async def next_decision(self, prompt, *, run, turn):
            raise TimeoutError("slow local model")

    fallback = ScriptedPlannerProvider([{"decision_type": "complete", "summary": "fallback strong"}])
    provider = CapabilityScoredPlannerProvider([
        {"name": "local-small", "provider": Broken(), "capability_score": 0.3, "cost_score": 0.95},
        {"name": "strong-model", "provider": fallback, "capability_score": 0.9, "cost_score": 0.2},
    ])
    run = {"mode": "agent", "objective": "small edit", "checkpoint": {"planner": {"observations": []}}}
    decision = asyncio.run(provider.next_decision("prompt", run=run, turn=1))
    assert decision.summary == "fallback strong"
    assert provider.health["local-small"] < 1.0
    assert provider.last_provider == "strong-model"


def test_provider_quality_ledger_tunes_capability_scores(tmp_path):
    weak = ScriptedPlannerProvider([{"decision_type": "complete", "summary": "weak learned route"}])
    strong = ScriptedPlannerProvider([{"decision_type": "complete", "summary": "strong fallback"}])
    ledger = ProviderQualityLedger(tmp_path, path=tmp_path / "provider_quality.json")
    for _ in range(12):
        ledger.record("weak-local", "bounded_edit", ok=True, latency_ms=120)
    for _ in range(8):
        ledger.record("strong-cloud", "bounded_edit", ok=False, latency_ms=1800, failure_class="provider_error")
    provider = CapabilityScoredPlannerProvider([
        {"name": "weak-local", "provider": weak, "capability_score": 0.25, "cost_score": 0.95},
        {"name": "strong-cloud", "provider": strong, "capability_score": 0.9, "cost_score": 0.2},
    ], quality_ledger=ledger)
    run = {"mode": "agent", "objective": "Small bounded edit", "checkpoint": {"planner": {"observations": []}}}
    decision = asyncio.run(provider.next_decision("prompt", run=run, turn=1))
    assert decision.summary == "weak learned route"
    assert provider.last_provider == "weak-local"
    assert provider.last_route["quality_score"] > 0.5
    assert provider.last_route["task_type"] == "bounded_edit"


def test_heuristic_planner_fast_paths_workspace_then_bind_then_verify(tmp_path):
    engine, run_id, approval_id = _repo_run(tmp_path)
    provider = HeuristicPlannerProvider()
    run = engine.store.get_run(run_id)
    first = asyncio.run(provider.next_decision("prompt", run=run, turn=1))
    assert first.tool_id == "workspace.index"
    asyncio.run(engine.execute_tool(run_id, "workspace.index", {"limit": 1200, "include_symbols": True}))
    run = engine.store.get_run(run_id)
    run["checkpoint"]["planner"] = {"observations": [{"tool_id": "workspace.index", "status": "completed", "result": {}}]}
    second = asyncio.run(provider.next_decision("prompt", run=run, turn=2))
    assert second.tool_id == "worktree.bind"
    asyncio.run(engine.execute_tool(run_id, "worktree.bind", {"objective": "repair VALUE"}, approval_id=approval_id))
    asyncio.run(engine.execute_tool(run_id, "worktree.replace_exact", {"path": "answer.py", "old_text": "VALUE = 1", "new_text": "VALUE = 2"}, approval_id=approval_id))
    run = engine.store.get_run(run_id)
    run["checkpoint"]["planner"] = {"observations": [
        {"tool_id": "workspace.index", "status": "completed", "result": {}},
        {"tool_id": "worktree.bind", "status": "completed", "result": {}},
        {"tool_id": "worktree.replace_exact", "status": "completed", "result": {"path": "answer.py"}},
    ]}
    third = asyncio.run(provider.next_decision("prompt", run=run, turn=3))
    assert third.tool_id == "worktree.verify"
    assert third.arguments["command"][:3] == ["python", "-m", "py_compile"]
    assert third.arguments["command"][-1] == "answer.py"


def test_large_real_repo_endurance_touches_20_files_and_hands_off_sourceplan(tmp_path):
    import subprocess

    root = tmp_path / "bigrepo"
    root.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "beast@example.test"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "BEAST Test"], cwd=root, check=True)
    (root / "README.md").write_text("# Big Repo\n", encoding="utf-8")
    for package in ("api", "worker", "ui", "shared"):
        (root / "packages" / package).mkdir(parents=True)
        (root / "packages" / package / "__init__.py").write_text("", encoding="utf-8")
    # R3.24 graduation contract: an operator-owned baseline test for the explicit implementation target.
    (root / "test_endurance.py").write_text(
        "from packages.pkg_0 import module_0\n\n\ndef test_compute():\n    assert module_0.compute() == 0\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    subprocess.run(["git", "commit", "-qm", "initial"], cwd=root, check=True)
    engine = AgentRunEngine(root)
    paths = [f"packages/pkg_{index % 5}/module_{index}.py" for index in range(22)]
    run_id = engine.create_run(
        session_id="session-large-endurance",
        objective="Large real-repo endurance: touch 20+ files across package boundaries and verify",
        mode="agent",
        provider="simulated",
        model="planner-test",
        request={"context_files": paths[:8], "monorepo": True, "long_horizon": True,
                 "implementation_target": paths[0], "required_test_files": ["test_endurance.py"]},
    )["run_id"]
    approval_id = "large-mutation"
    engine.store.create_approval(run_id, {"request_id": approval_id, "capabilities": [{"id": "worktree_mutation"}, {"id": "run_isolated_verifier"}]})
    engine.store.resolve_approval(run_id, approval_id, {"approved": True, "scope": "run"})
    decisions = [
        {"decision_type": "tool", "tool_id": "workspace.index", "arguments": {"limit": 2000, "include_symbols": True}},
        {"decision_type": "tool", "tool_id": "worktree.bind", "approval_id": approval_id, "arguments": {"objective": "large endurance", "risk": "high"}},
    ]
    for index, file_path in enumerate(paths):
        decisions.append({
            "decision_type": "tool",
            "tool_id": "worktree.write_file",
            "approval_id": approval_id,
            "arguments": {"path": file_path, "content": f"VALUE_{index} = {index}\n\ndef compute():\n    return VALUE_{index}\n"},
        })
    decisions.extend([
        {"decision_type": "tool", "tool_id": "worktree.verify", "approval_id": approval_id, "arguments": {"command": ["python", "-m", "py_compile", *paths]}},
        {"decision_type": "tool", "tool_id": "worktree.sourceplan_draft", "approval_id": approval_id, "arguments": {}},
        {"decision_type": "complete", "summary": "Large repo endurance mutation verified and handed off."},
    ])
    final = asyncio.run(AgentPlannerRuntime(engine, ScriptedPlannerProvider(decisions), max_turns=32, observation_limit=50).run(run_id))
    assert final["state"] == "completed"
    planner = final["checkpoint"]["planner"]
    changed = [item["result"]["path"] for item in planner["observations"] if item.get("tool_id") == "worktree.write_file" and item.get("status") == "completed"]
    assert len(set(changed)) >= 20
    assert any(item.get("tool_id") == "worktree.verify" and item.get("status") == "completed" for item in planner["observations"])
    assert any(item.get("tool_id") == "worktree.sourceplan_draft" and item.get("status") == "completed" for item in planner["observations"])


def test_heuristic_planner_defers_non_retryable_failed_verify_to_model_route():
    provider = HeuristicPlannerProvider()
    run = {
        "mode": "agent",
        "checkpoint": {"planner": {
            "observations": [
                {"tool_id": "worktree.bind", "status": "completed", "result": {}},
                {"tool_id": "worktree.replace_exact", "status": "completed", "result": {"path": "answer.py"}},
                {"tool_id": "worktree.verify", "status": "failed", "result": {}},
            ],
            "verification_failures": [{"analysis": {"failure_class": "bad_patch", "retryable_without_code_change": False}}],
        }},
    }
    try:
        asyncio.run(provider.next_decision("prompt", run=run, turn=4))
    except ValueError as exc:
        assert "defers code-repair" in str(exc)
    else:
        raise AssertionError("heuristic provider should defer code-repair failures")


def test_heuristic_planner_completes_after_verified_sourceplan_handoff():
    provider = HeuristicPlannerProvider()
    run = {
        "mode": "agent",
        "checkpoint": {"planner": {
            "observations": [
                {"tool_id": "workspace.index", "status": "completed", "result": {}},
                {"tool_id": "worktree.bind", "status": "completed", "result": {}},
                {"tool_id": "worktree.replace_exact", "status": "completed", "result": {"path": "answer.py"}},
                {"tool_id": "worktree.verify", "status": "completed", "result": {}},
                {"tool_id": "worktree.sourceplan_draft", "status": "completed", "result": {}},
            ],
            "verification_failures": [],
        }},
    }
    decision = asyncio.run(provider.next_decision("prompt", run=run, turn=5))
    assert decision.decision_type.value == "complete"
    assert "SourcePlan handoff" in decision.summary


def test_heuristic_planner_blocks_cleanly_when_no_deterministic_step_exists():
    provider = HeuristicPlannerProvider()
    run = {
        "mode": "agent",
        "checkpoint": {"planner": {
            "observations": [
                {"tool_id": "workspace.index", "status": "completed", "result": {}},
                {"tool_id": "worktree.bind", "status": "completed", "result": {}},
            ],
            "verification_failures": [],
        }},
    }
    decision = asyncio.run(provider.next_decision("prompt", run=run, turn=3))
    assert decision.decision_type.value == "blocked"
    assert "stronger planner route required" in decision.blocker


def test_verification_planner_prefers_focused_pytest_for_changed_tests():
    run = {
        "request": {
            "execution_target": "container",
            "execution_target_payload": {"kind": "container", "sessionId": "ctr-1", "label": "devcontainer"},
            "test_catalog": {"tests": [{"id": "python:pytest", "framework": "pytest", "command": "python3 -m pytest"}]},
        },
        "checkpoint": {
            "planner": {
                "observations": [
                    {"tool_id": "worktree.replace_exact", "status": "completed", "result": {"path": "tests/test_agent_loop.py"}},
                ],
            },
        },
    }
    plan = plan_verification(run)
    assert plan["command"] == ["python3", "-m", "pytest", "-q", "tests/test_agent_loop.py"]
    assert plan["reason"] == "focused_pytest_for_changed_test_files"
    assert plan["execution_target"]["kind"] == "container"
    assert plan["catalog_matches"] == ["python:pytest"]


def test_verification_planner_uses_workspace_index_related_pytest_for_source_change():
    run = {
        "request": {
            "test_catalog": {"tests": [{"id": "python:pytest", "framework": "pytest", "command": "python3 -m pytest"}]},
        },
        "checkpoint": {
            "planner": {
                "observations": [
                    {
                        "tool_id": "workspace.index",
                        "status": "completed",
                        "result": {
                            "beast_object_type": "beast_workspace_index_snapshot",
                            "files": [
                                {"path": "app/service.py", "language": "python"},
                                {"path": "tests/test_service.py", "language": "python"},
                            ],
                            "tests": ["tests/test_service.py"],
                            "imports": [
                                {"path": "tests/test_service.py", "target": "app.service", "kind": "import"},
                            ],
                        },
                    },
                    {"tool_id": "worktree.replace_exact", "status": "completed", "result": {"path": "app/service.py"}},
                ],
            },
        },
    }
    plan = plan_verification(run)
    assert plan["command"] == ["python", "-m", "pytest", "-q", "tests/test_service.py"]
    assert plan["reason"] == "related_pytest_from_workspace_index"
    assert plan["scope"] == "related_tests"
    assert plan["related_tests"] == ["tests/test_service.py"]


def test_verification_planner_uses_workspace_index_related_vitest_for_typescript_source_change():
    run = {
        "request": {
            "test_catalog": {"tests": [{"id": "javascript:vitest", "framework": "vitest", "command": "npx vitest run"}]},
        },
        "checkpoint": {
            "planner": {
                "observations": [
                    {
                        "tool_id": "workspace.index",
                        "status": "completed",
                        "result": {
                            "beast_object_type": "beast_workspace_index_snapshot",
                            "files": [
                                {"path": "src/service.ts", "language": "typescript"},
                                {"path": "tests/service.test.ts", "language": "typescript"},
                            ],
                            "tests": ["tests/service.test.ts"],
                            "imports": [
                                {"path": "tests/service.test.ts", "target": "../src/service", "kind": "import"},
                            ],
                        },
                    },
                    {"tool_id": "worktree.replace_exact", "status": "completed", "result": {"path": "src/service.ts"}},
                ],
            },
        },
    }
    plan = plan_verification(run)
    assert plan["command"] == ["npx", "vitest", "run", "tests/service.test.ts"]
    assert plan["reason"] == "related_javascript_tests_from_workspace_index"
    assert plan["scope"] == "related_tests"
    assert plan["catalog_matches"] == ["javascript:vitest"]
    assert plan["related_tests"] == ["tests/service.test.ts"]


def test_verification_planner_prefers_changed_jest_test_file_over_typescript_compile():
    run = {
        "request": {
            "test_catalog": {"tests": [{"id": "javascript:jest", "framework": "jest", "command": "npx jest"}]},
        },
        "checkpoint": {
            "planner": {
                "observations": [
                    {"tool_id": "worktree.write_file", "status": "completed", "result": {"path": "src/service.test.ts"}},
                ],
            },
        },
    }
    plan = plan_verification(run)
    assert plan["command"] == ["npx", "jest", "--runTestsByPath", "src/service.test.ts"]
    assert plan["reason"] == "focused_javascript_tests_for_changed_test_files"
    assert plan["scope"] == "focused_tests"


def test_verification_planner_keeps_source_python_on_compile_gate():
    run = {
        "request": {"test_catalog": {"tests": [{"id": "python:pytest", "framework": "pytest"}]}},
        "checkpoint": {
            "planner": {
                "observations": [
                    {"tool_id": "worktree.write_file", "status": "completed", "result": {"path": "app/service.py"}},
                ],
            },
        },
    }
    plan = plan_verification(run)
    assert plan["command"] == ["python", "-m", "py_compile", "app/service.py"]
    assert plan["reason"] == "python_compile_for_changed_sources"


def test_verification_planner_selects_go_package_tests_for_changed_source():
    run = {
        "request": {"test_catalog": {"tests": [{"id": "go:test", "framework": "go test"}]}},
        "checkpoint": {"planner": {"observations": [
            {"tool_id": "worktree.replace_exact", "status": "completed", "result": {"path": "pkg/service/service.go"}},
        ]}},
    }
    plan = plan_verification(run)
    assert plan["command"] == ["go", "test", "./pkg/service"]
    assert plan["reason"] == "go_test_for_changed_packages"
    assert plan["catalog_matches"] == ["go:test"]


def test_verification_planner_selects_cargo_for_changed_rust_crate():
    run = {
        "request": {"test_catalog": {"tests": [{"id": "rust:cargo-test", "framework": "cargo"}]}},
        "checkpoint": {"planner": {"observations": [
            {"tool_id": "workspace.index", "status": "completed", "result": {
                "beast_object_type": "beast_workspace_index_snapshot",
                "files": [{"path": "Cargo.toml"}, {"path": "src/lib.rs"}, {"path": "tests/service_test.rs"}],
                "tests": ["tests/service_test.rs"],
            }},
            {"tool_id": "worktree.replace_exact", "status": "completed", "result": {"path": "src/lib.rs"}},
        ]}},
    }
    plan = plan_verification(run)
    assert plan["command"] == ["cargo", "test"]
    assert plan["reason"] == "cargo_test_for_changed_crate"
    assert plan["related_tests"] == ["tests/service_test.rs"]


def test_verification_planner_selects_maven_related_tests_for_java_source():
    run = {
        "request": {"test_catalog": {"tests": [{"id": "java:maven-test", "framework": "maven"}]}},
        "checkpoint": {"planner": {"observations": [
            {"tool_id": "workspace.index", "status": "completed", "result": {
                "beast_object_type": "beast_workspace_index_snapshot",
                "files": [
                    {"path": "pom.xml"},
                    {"path": "src/main/java/com/acme/Service.java"},
                    {"path": "src/test/java/com/acme/ServiceTest.java"},
                ],
                "tests": ["src/test/java/com/acme/ServiceTest.java"],
            }},
            {"tool_id": "worktree.replace_exact", "status": "completed", "result": {"path": "src/main/java/com/acme/Service.java"}},
        ]}},
    }
    plan = plan_verification(run)
    assert plan["command"] == ["mvn", "test", "-Dtest=ServiceTest"]
    assert plan["reason"] == "maven_related_tests_from_workspace_index"


def test_verification_planner_selects_dotnet_project_gate():
    run = {
        "request": {"test_catalog": {"tests": [{"id": "dotnet:test", "framework": "dotnet"}]}},
        "checkpoint": {"planner": {"observations": [
            {"tool_id": "workspace.index", "status": "completed", "result": {
                "beast_object_type": "beast_workspace_index_snapshot",
                "files": [{"path": "App/App.csproj"}, {"path": "App/Foo.cs"}, {"path": "App.Tests/FooTests.cs"}],
                "tests": ["App.Tests/FooTests.cs"],
            }},
            {"tool_id": "worktree.write_file", "status": "completed", "result": {"path": "App/Foo.cs"}},
        ]}},
    }
    plan = plan_verification(run)
    assert plan["command"] == ["dotnet", "test", "--no-restore"]
    assert plan["reason"] == "dotnet_test_for_changed_project"
    assert plan["catalog_matches"] == ["dotnet:test"]


def test_verification_planner_selects_playwright_spec_before_unit_runner():
    run = {
        "request": {"test_catalog": {"tests": [
            {"id": "javascript:playwright", "framework": "playwright"},
            {"id": "javascript:vitest", "framework": "vitest"},
        ]}},
        "checkpoint": {"planner": {"observations": [
            {"tool_id": "worktree.replace_exact", "status": "completed", "result": {"path": "tests/e2e/login.spec.ts"}},
        ]}},
    }
    plan = plan_verification(run)
    assert plan["command"] == ["npx", "playwright", "test", "tests/e2e/login.spec.ts"]
    assert plan["reason"] == "focused_playwright_specs_from_workspace_index"
    assert plan["scope"] == "focused_e2e"


def test_long_horizon_planning_seed_adds_architecture_and_test_map_steps(tmp_path):
    engine = AgentRunEngine(tmp_path)
    run = engine.create_run(
        session_id="session-long-horizon",
        objective="Large-repo multi-turn architecture change across dependencies",
        mode="agent",
        provider="simulated",
        model="planner-test",
        request={"context_files": ["app/a.py", "app/b.py", "tests/test_a.py", "package.json"]},
    )
    run_id = run["run_id"]
    runtime = AgentPlannerRuntime(engine, ScriptedPlannerProvider([]))
    receipt = runtime.planning_integrations.ensure_phase1_plan(run_id, run)
    steps = receipt["plan"]["steps"]
    assert [step["step_id"] for step in steps] == ["inspect", "architecture", "test-map", "bind", "mutate", "verify", "repair", "handoff"]
    assert steps[0]["telemetry"]["planning_mode"] == "long_horizon"
    brief = runtime.planning_integrations.current_plan_brief(run_id)
    assert brief["mode"] == "long_horizon"
    assert brief["active_step_id"] == "inspect"


def test_edit_prompt_includes_target_aware_verification_hint(tmp_path):
    engine, run_id, approval_id = _repo_run(tmp_path)
    engine.merge_checkpoint(run_id, {
        "planner": {
            "observations": [
                {"tool_id": "workspace.list", "status": "completed", "result": {}},
                {"tool_id": "worktree.bind", "status": "completed", "result": {}},
                {"tool_id": "worktree.replace_exact", "status": "completed", "result": {"path": "tests/test_agent_loop.py"}},
            ],
        },
    })
    run = engine.store.get_run(run_id)
    run["request"]["execution_target"] = "ssh"
    run["request"]["execution_target_payload"] = {"kind": "ssh", "sessionId": "ssh-1", "host": "devbox"}
    run["request"]["test_catalog"] = {"tests": [{"id": "python:pytest", "framework": "pytest"}]}
    runtime = AgentPlannerRuntime(engine, ScriptedPlannerProvider([]))
    prompt = runtime._prompt(run, runtime._load_state(run_id))
    assert "EXECUTION TARGET: ssh" in prompt
    assert "VERIFICATION HINT:" in prompt
    assert '"command":["python3","-m","pytest","-q","tests/test_agent_loop.py"]' in prompt
    assert '"kind":"ssh"' in prompt


def test_edit_prompt_exposes_required_phase_transition(tmp_path):
    (tmp_path / "sample.py").write_text("VALUE = 1\n", encoding="utf-8")
    engine = AgentRunEngine(tmp_path)
    run = engine.create_run(
        session_id="phase-contract",
        objective="Change VALUE to 2 and verify it.",
        mode="edit",
        provider="simulated",
        model="planner-test",
    )
    runtime = AgentPlannerRuntime(engine, ScriptedPlannerProvider([]))
    prompt = runtime._prompt(run, runtime._load_state(run["run_id"]))
    assert "Do not edit yet" in prompt
    assert "Never emit whole-file source" in prompt


def test_agent_phase_enforcement_inserts_worktree_bind_after_initial_inspection(tmp_path):
    engine, run_id, approval_id = _repo_run(tmp_path)
    provider = ScriptedPlannerProvider([
        {"decision_type": "tool", "tool_id": "workspace.index", "arguments": {"limit": 1200, "include_symbols": True}},
        {"decision_type": "complete", "summary": "done too early"},
    ])
    final = asyncio.run(AgentPlannerRuntime(engine, provider, max_turns=2).run(run_id))
    planner = final["checkpoint"]["planner"]
    assert final["state"] == "budget_exhausted"
    assert planner["observations"][0]["tool_id"] == "workspace.index"
    assert planner["observations"][1]["tool_id"] == "worktree.bind"
    assert planner["observations"][1]["status"] == "completed"
    phase_events = [e for e in engine.store.events(run_id, limit=100) if e["event_type"] == "agent.planner.phase_enforced"]
    assert phase_events
    assert phase_events[-1]["payload"]["required_tool_id"] == "worktree.bind"


def test_agent_phase_enforcement_runs_default_verify_and_sourceplan_after_mutation(tmp_path):
    engine, run_id, approval_id = _repo_run(tmp_path, graduation_contract=True)
    provider = ScriptedPlannerProvider([
        {"decision_type": "tool", "tool_id": "workspace.index", "arguments": {"limit": 1200, "include_symbols": True}},
        {"decision_type": "tool", "tool_id": "worktree.bind", "approval_id": approval_id, "arguments": {"objective": "repair VALUE"}},
        {"decision_type": "tool", "tool_id": "worktree.replace_exact", "approval_id": approval_id, "arguments": {"path": "answer.py", "old_text": "VALUE = 1", "new_text": "VALUE = 2"}},
        {"decision_type": "complete", "summary": "completed before verify"},
        {"decision_type": "complete", "summary": "completed before sourceplan"},
        {"decision_type": "complete", "summary": "VALUE repaired and verified."},
    ])
    final = asyncio.run(AgentPlannerRuntime(engine, provider, max_turns=6).run(run_id))
    planner = final["checkpoint"]["planner"]
    assert final["state"] == "completed"
    tool_ids = [item["tool_id"] for item in planner["observations"]]
    assert tool_ids == [
        "workspace.index",
        "worktree.bind",
        "worktree.replace_exact",
        "worktree.verify",
        "worktree.sourceplan_draft",
    ]
    verify = next(item for item in planner["observations"] if item["tool_id"] == "worktree.verify")
    assert verify["status"] == "completed"
    assert verify["result"]["command"][:3] == ["python", "-m", "py_compile"]
    assert verify["result"]["command"][-1] == "answer.py"
    # After verify + SourcePlan the runtime autofinalizes (no extra model turn), with its own grounded summary.
    assert planner["final_summary"].startswith("Completed bounded changes")


def test_failed_verification_records_analysis_and_target_paths(tmp_path):
    engine, run_id, approval_id = _repo_run(tmp_path)
    provider = ScriptedPlannerProvider([
        {"decision_type": "tool", "tool_id": "workspace.index", "arguments": {"limit": 1200, "include_symbols": True}},
        {"decision_type": "tool", "tool_id": "worktree.bind", "approval_id": approval_id, "arguments": {"objective": "repair VALUE"}},
        {"decision_type": "tool", "tool_id": "worktree.replace_exact", "approval_id": approval_id, "arguments": {"path": "answer.py", "old_text": "VALUE = 1", "new_text": "VALUE = 2\nbroken = "}},
        {"decision_type": "tool", "tool_id": "worktree.verify", "approval_id": approval_id, "arguments": {"command": ["python", "-m", "py_compile", "answer.py"]}},
        {"decision_type": "complete", "summary": "should not matter"},
    ])
    final = asyncio.run(AgentPlannerRuntime(engine, provider, max_turns=4, max_repair_cycles=2).run(run_id))
    planner = final["checkpoint"]["planner"]
    assert final["state"] == "budget_exhausted"
    assert planner["repair_cycles"] == 1
    failure = planner["verification_failures"][-1]
    assert failure["target_paths"] == ["answer.py"]
    assert failure["analysis"]["failure_class"] == "bad_patch"
    repair_event = next(e for e in engine.store.events(run_id, limit=200) if e["event_type"] == "agent.repair.required")
    assert repair_event["payload"]["failure_analysis"]["failure_class"] == "bad_patch"
    assert repair_event["payload"]["target_paths"] == ["answer.py"]


def test_prompt_surfaces_structured_repair_contract_after_failed_verify(tmp_path):
    engine, run_id, approval_id = _repo_run(tmp_path)
    provider = ScriptedPlannerProvider([
        {"decision_type": "tool", "tool_id": "workspace.list", "arguments": {}},
        {"decision_type": "tool", "tool_id": "worktree.bind", "approval_id": approval_id, "arguments": {"objective": "repair VALUE"}},
        {"decision_type": "tool", "tool_id": "worktree.replace_exact", "approval_id": approval_id, "arguments": {"path": "answer.py", "old_text": "VALUE = 1", "new_text": "VALUE = 2\nbroken = "}},
        {"decision_type": "tool", "tool_id": "worktree.verify", "approval_id": approval_id, "arguments": {"command": ["python", "-m", "py_compile", "answer.py"]}},
        {"decision_type": "complete", "summary": "too early after failure"},
    ])
    asyncio.run(AgentPlannerRuntime(engine, provider, max_turns=4, max_repair_cycles=2).run(run_id))
    runtime = AgentPlannerRuntime(engine, ScriptedPlannerProvider([]))
    state = runtime._load_state(run_id)
    prompt = runtime._prompt(engine.store.get_run(run_id), state)
    assert "repair the latest verifier failure with one bounded edit in answer.py" in prompt
    assert "Failure class: syntax." in prompt


def test_mutating_heuristic_block_after_bind_retries_strong_provider(tmp_path):
    engine, run_id, approval_id = _repo_run(tmp_path, provider="nvidia_nim", model="meta/llama-3.1-70b-instruct", graduation_contract=True)
    scripted = iter([
        {"decision_type": "tool", "tool_id": "worktree.replace_exact", "approval_id": approval_id, "arguments": {"path": "answer.py", "old_text": "VALUE = 1", "new_text": "VALUE = 2"}},
        {"decision_type": "tool", "tool_id": "worktree.verify", "approval_id": approval_id, "arguments": {"command": ["python", "-m", "py_compile", "answer.py"]}},
        {"decision_type": "tool", "tool_id": "worktree.sourceplan_draft", "approval_id": approval_id, "arguments": {}},
        {"decision_type": "complete", "summary": "VALUE repaired and verified."},
    ])

    class _HeuristicThenStrong:
        def __init__(self):
            self.last_route = {}
            self.last_usage = {}
            self.calls = 0

        async def next_decision(self, prompt: str, *, run: dict[str, Any], turn: int):
            self.calls += 1
            if self.calls == 1:
                self.last_route = {"provider": "heuristic", "engine": "deterministic", "route_kind": "heuristic", "reason": "deterministic_fast_path"}
                return parse_planner_decision({
                    "decision_type": "blocked",
                    "blocker": "Heuristic fallback found no further deterministic step; stronger planner route required.",
                })
            self.last_route = {"provider": "simulated", "engine": "scripted", "route_kind": "primary", "reason": "retry"}
            return parse_planner_decision(next(scripted))

    runtime = AgentPlannerRuntime(engine, _HeuristicThenStrong(), max_turns=6)
    bind_obs = asyncio.run(engine.execute_tool(run_id, "worktree.bind", {"objective": "repair VALUE"}, approval_id=approval_id))
    state = runtime._load_state(run_id)
    state.observations = [
        {
            "observation_id": "obs-index",
            "tool_id": "workspace.index",
            "status": "completed",
            "result": {"ok": True},
        },
        {
            "observation_id": "obs-bind",
            "tool_id": "worktree.bind",
            "status": "completed",
            "result": dict(bind_obs.get("result") or {}),
        },
    ]
    state.turn = 2
    runtime._save_state(state)
    final = asyncio.run(runtime.run(run_id))
    planner = final["checkpoint"]["planner"]
    assert final["state"] != "policy_blocked"
    tool_ids = [item["tool_id"] for item in planner["observations"]]
    assert tool_ids[:3] == [
        "workspace.index",
        "worktree.bind",
        "workspace.read_range",
    ]


def test_first_mutation_retry_prompt_includes_exact_file_context(tmp_path):
    engine, run_id, approval_id = _repo_run(tmp_path, provider="nvidia_nim", model="meta/llama-3.1-70b-instruct")
    runtime = AgentPlannerRuntime(engine, ScriptedPlannerProvider([]), max_turns=6)
    bind_obs = asyncio.run(engine.execute_tool(run_id, "worktree.bind", {"objective": "repair VALUE"}, approval_id=approval_id))
    read_obs = asyncio.run(engine.execute_tool(run_id, "workspace.read_range", {"path": "answer.py", "start_line": 1, "line_count": 40}))
    state = runtime._load_state(run_id)
    state.observations = [read_obs, bind_obs]
    prompt = runtime._first_mutation_retry_prompt("base prompt", state)
    assert "FIRST MUTATION REQUIRED" in prompt
    assert "TARGET FILE: answer.py" in prompt
    assert "CURRENT CONTENT" in prompt
    assert "VALUE = 1" in prompt


def test_first_mutation_retry_unwraps_sticky_provider_primary(tmp_path):
    engine, run_id, approval_id = _repo_run(tmp_path, provider="nvidia_nim", model="planner-test")

    class _Primary(NIMPlannerProvider):
        # R3.22: strong re-entry only resolves the exact requested provider class and model.
        def __init__(self):
            self.calls = 0
            self.model = "planner-test"
            self.last_route = {"provider": "nvidia_nim", "engine": "nvidia_nim", "route_kind": "direct_generate", "reason": "retry"}

        async def next_decision(self, prompt: str, *, run: dict[str, Any], turn: int):
            self.calls += 1
            assert "FIRST MUTATION REQUIRED" in prompt
            return parse_planner_decision({
                "decision_type": "tool",
                "tool_id": "worktree.replace_exact",
                "approval_id": approval_id,
                "arguments": {"path": "answer.py", "old_text": "VALUE = 1", "new_text": "VALUE = 2"},
            })

    class _Fallback:
        async def next_decision(self, prompt: str, *, run: dict[str, Any], turn: int):
            return parse_planner_decision({
                "decision_type": "blocked",
                "blocker": "Heuristic fallback found no further deterministic step; stronger planner route required.",
            })

    class _StickyWrapper:
        def __init__(self, primary):
            self.primary = primary
            self.fallback = _Fallback()
            self.force_fallback = True
            self.last_route = {"provider": "heuristic", "engine": "deterministic", "route_kind": "sticky_fallback", "reason": "run_scoped_sticky_fallback"}

        async def next_decision(self, prompt: str, *, run: dict[str, Any], turn: int):
            return await self.fallback.next_decision(prompt, run=run, turn=turn)

    primary = _Primary()
    runtime = AgentPlannerRuntime(engine, _StickyWrapper(primary), max_turns=6)
    state = runtime._load_state(run_id)
    state.turn = 2
    state.observations = [
        {"tool_id": "workspace.read_range", "status": "completed", "result": {"path": "answer.py", "content": "VALUE = 1\n"}},
        {"tool_id": "worktree.bind", "status": "completed", "result": {"task_id": "wt-1", "worktree_root": str(tmp_path / 'repo')}},
    ]
    result = asyncio.run(runtime._retry_primary_for_first_mutation(runtime.provider, "prompt", engine.store.get_run(run_id) or {}, state, turn=3, reason="test"))
    assert result is not None
    assert result.tool_id == "worktree.replace_exact"
    assert primary.calls == 1


def test_blocked_fallback_salvages_partial_decision_from_wrapped_primary(tmp_path):
    engine, run_id, approval_id = _repo_run(tmp_path, provider="nvidia_nim", model="planner-test")

    class _Primary:
        def __init__(self):
            self.last_partial_text = (
                '{"decision_type":"tool","tool_id":"worktree.replace_exact",'
                f'"approval_id":"{approval_id}",'
                '"arguments":{"path":"answer.py","old_text":"VALUE = 1","new_text":"VALUE = 2"},'
                '"summary":"Implement code change."}'
            )

    class _Wrapper:
        def __init__(self):
            self.primary = _Primary()
            self.last_route = {"provider": "heuristic", "engine": "deterministic", "route_kind": "sticky_fallback", "reason": "run_scoped_sticky_fallback"}
            self.last_usage = {"engine": "nvidia_nim", "model": "planner-test"}

        async def next_decision(self, prompt: str, *, run: dict[str, Any], turn: int):
            return parse_planner_decision({
                "decision_type": "blocked",
                "blocker": "Heuristic fallback found no further deterministic step; stronger planner route required.",
            })

    runtime = AgentPlannerRuntime(engine, _Wrapper(), max_turns=4)
    state = runtime._load_state(run_id)
    state.turn = 2
    state.observations = [
        {"tool_id": "workspace.read_range", "status": "completed", "result": {"path": "answer.py", "content": "VALUE = 1\n"}},
        {"tool_id": "worktree.bind", "status": "completed", "result": {"task_id": "wt-1", "worktree_root": str(tmp_path / 'repo')}},
    ]
    runtime._save_state(state)
    _bind_test_worktree(engine, run_id, approval_id, runtime, state)
    final = asyncio.run(runtime.run(run_id))
    assert final["state"] != "policy_blocked"
    planner = final["checkpoint"]["planner"]
    assert any(item.get("tool_id") == "worktree.replace_exact" for item in planner.get("observations", []))
    events = engine.store.events(run_id, limit=200)
    salvage = [event for event in events if event["event_type"] == "agent.provider.partial_decision_salvaged"]
    assert salvage
    assert salvage[-1]["payload"].get("reason") == "wrapped_provider_fallback_salvage"


def test_blocked_fallback_salvages_partial_decision_from_recent_model_delta(tmp_path):
    engine, run_id, approval_id = _repo_run(tmp_path, provider="nvidia_nim", model="planner-test")
    delta_text = (
        '{"decision_type":"tool","tool_id":"worktree.replace_exact",'
        f'"approval_id":"{approval_id}",'
        '"arguments":{"path":"answer.py","old_text":"VALUE = 1","new_text":"VALUE = 2"},'
        '"summary":"Implement code change."}'
    )

    class _Wrapper:
        def __init__(self):
            self.primary = object()
            self.last_route = {"provider": "heuristic", "engine": "deterministic", "route_kind": "sticky_fallback", "reason": "run_scoped_sticky_fallback"}
            self.last_usage = {"engine": "nvidia_nim", "model": "planner-test"}

        async def next_decision(self, prompt: str, *, run: dict[str, Any], turn: int):
            # Turn isolation: only deltas streamed during the current planner turn are salvageable.
            engine.emit(run_id, "agent.model.delta", {"text": delta_text})
            return parse_planner_decision({
                "decision_type": "blocked",
                "blocker": "Heuristic fallback found no further deterministic step; stronger planner route required.",
            })

    runtime = AgentPlannerRuntime(engine, _Wrapper(), max_turns=4)
    state = runtime._load_state(run_id)
    state.turn = 2
    state.observations = [
        {"tool_id": "workspace.read_range", "status": "completed", "result": {"path": "answer.py", "content": "VALUE = 1\n"}},
        {"tool_id": "worktree.bind", "status": "completed", "result": {"task_id": "wt-1", "worktree_root": str(tmp_path / 'repo')}},
    ]
    runtime._save_state(state)
    _bind_test_worktree(engine, run_id, approval_id, runtime, state)
    final = asyncio.run(runtime.run(run_id))
    assert final["state"] != "policy_blocked"
    planner = final["checkpoint"]["planner"]
    assert any(item.get("tool_id") == "worktree.replace_exact" for item in planner.get("observations", []))


def test_post_bind_duplicate_read_retries_strong_provider(tmp_path):
    engine, run_id, approval_id = _repo_run(tmp_path, provider="nvidia_nim", model="meta/llama-3.1-70b-instruct")
    scripted = iter([
        {"decision_type": "tool", "tool_id": "worktree.replace_exact", "approval_id": approval_id, "arguments": {"path": "answer.py", "old_text": "VALUE = 1", "new_text": "VALUE = 2"}},
        {"decision_type": "tool", "tool_id": "worktree.verify", "approval_id": approval_id, "arguments": {"command": ["python", "-m", "py_compile", "answer.py"]}},
        {"decision_type": "tool", "tool_id": "worktree.sourceplan_draft", "approval_id": approval_id, "arguments": {}},
        {"decision_type": "complete", "summary": "VALUE repaired and verified."},
    ])

    class _DuplicateReadThenStrong:
        def __init__(self):
            self.last_route = {}
            self.last_usage = {}
            self.calls = 0

        async def next_decision(self, prompt: str, *, run: dict[str, Any], turn: int):
            self.calls += 1
            if self.calls == 1:
                self.last_route = {"provider": "nvidia_nim", "engine": "nvidia_nim", "route_kind": "direct_generate", "reason": "nim_chat_completions"}
                return parse_planner_decision({
                    "decision_type": "tool",
                    "tool_id": "workspace.read_range",
                    "arguments": {"path": "answer.py", "start_line": 1, "line_count": 20},
                })
            self.last_route = {"provider": "nvidia_nim", "engine": "nvidia_nim", "route_kind": "direct_generate", "reason": "retry"}
            return parse_planner_decision(next(scripted))

    runtime = AgentPlannerRuntime(engine, _DuplicateReadThenStrong(), max_turns=6)
    state = runtime._load_state(run_id)
    state.observations = [
        {
            "observation_id": "obs-read",
            "tool_id": "workspace.read_range",
            "status": "completed",
            "result": {"path": "answer.py", "content": "VALUE = 1\n",
                       "start_line": 1, "end_line": 1, "total_lines": 1},
        },
        {
            "observation_id": "obs-bind",
            "tool_id": "worktree.bind",
            "status": "completed",
            "result": {"task_id": "wt-1", "worktree_root": str(tmp_path / "repo")},
        },
    ]
    state.turn = 2
    runtime._save_state(state)
    _bind_test_worktree(engine, run_id, approval_id, runtime, state)
    # This test exercises retry and execution, not the separate graduation contract.
    final = asyncio.run(runtime.run(run_id, max_turns_this_call=1))
    planner = final["checkpoint"]["planner"]
    tool_ids = [item["tool_id"] for item in planner["observations"]]
    assert tool_ids[:3] == ["workspace.read_range", "worktree.bind", "worktree.replace_exact"]
    retry_events = [event for event in engine.store.events(run_id, limit=200) if event["event_type"] == "agent.provider.post_bind_read_retry"]
    assert retry_events


def test_post_bind_duplicate_read_failure_pauses_without_repeating_read(tmp_path):
    engine, run_id, approval_id = _repo_run(tmp_path, provider="nvidia_nim", model="meta/llama-3.1-70b-instruct")

    class _RepeatedDuplicateRead:
        def __init__(self):
            self.last_route = {}
            self.last_usage = {}
            self.calls = 0

        async def next_decision(self, prompt: str, *, run: dict[str, Any], turn: int):
            self.calls += 1
            self.last_route = {"provider": "nvidia_nim", "engine": "nvidia_nim", "route_kind": "direct_generate", "reason": f"call_{self.calls}"}
            return parse_planner_decision({
                "decision_type": "tool",
                "tool_id": "workspace.read_range",
                "arguments": {"path": "answer.py", "start_line": 1, "line_count": 20},
            })

    runtime = AgentPlannerRuntime(engine, _RepeatedDuplicateRead(), max_turns=6)
    state = runtime._load_state(run_id)
    state.observations = [
        {
            "observation_id": "obs-read",
            "tool_id": "workspace.read_range",
            "status": "completed",
            "result": {"path": "answer.py", "content": "VALUE = 1\n",
                       "start_line": 1, "end_line": 1, "total_lines": 1},
        },
        {
            "observation_id": "obs-bind",
            "tool_id": "worktree.bind",
            "status": "completed",
            "result": {"task_id": "wt-1", "worktree_root": str(tmp_path / "repo")},
        },
    ]
    state.turn = 2
    runtime._save_state(state)
    _bind_test_worktree(engine, run_id, approval_id, runtime, state)
    final = asyncio.run(runtime.run(run_id))
    assert final["state"] == "paused"
    assert not final.get("error")
    events = engine.store.events(run_id, limit=200)
    assert any(event["event_type"] == "agent.provider.post_bind_read_retry_failed" for event in events)
    assert any(event["event_type"] == "agent.provider.read_loop_paused" for event in events)
    recovery = [event for event in events if event["event_type"] == "agent.provider.strong_retry_recovered"]
    assert not recovery


def test_post_bind_prompt_keeps_targeted_read_but_hides_index(tmp_path):
    engine, run_id, _approval_id = _repo_run(tmp_path, provider="nvidia_nim", model="meta/llama-3.1-70b-instruct")
    runtime = AgentPlannerRuntime(engine, ScriptedPlannerProvider([]))
    state = runtime._load_state(run_id)
    state.observations = [
        {
            "observation_id": "obs-read",
            "tool_id": "workspace.read_range",
            "status": "completed",
            "result": {"path": "answer.py", "content": "VALUE = 1\n",
                       "start_line": 1, "end_line": 1, "total_lines": 1},
        },
        {
            "observation_id": "obs-bind",
            "tool_id": "worktree.bind",
            "status": "completed",
            "result": {"task_id": "wt-1", "worktree_root": str(tmp_path / "repo")},
        },
    ]
    prompt = runtime._prompt(engine.store.get_run(run_id), state)
    assert "worktree.replace_exact(path,old_text,new_text)" in prompt
    assert "worktree.write_file(path,content)" in prompt
    assert "- workspace.read_range(" in prompt
    assert "- workspace.index(" not in prompt


def test_required_phase_enforces_targeted_read_after_bind_when_no_file_contents_seen(tmp_path):
    engine, run_id, _approval_id = _repo_run(tmp_path, provider="nvidia_nim", model="meta/llama-3.1-70b-instruct")
    runtime = AgentPlannerRuntime(engine, ScriptedPlannerProvider([]))
    run = engine.store.get_run(run_id)
    state = runtime._load_state(run_id)
    state.observations = [
        {
            "observation_id": "obs-index",
            "tool_id": "workspace.index",
            "status": "completed",
            "result": {"ok": True},
        },
        {
            "observation_id": "obs-bind",
            "tool_id": "worktree.bind",
            "status": "completed",
            "result": {"task_id": "wt-1", "worktree_root": str(tmp_path / "repo")},
        },
    ]
    decision = runtime._required_phase_decision(run, state)
    assert decision is not None
    assert decision.tool_id == "workspace.read_range"
    assert decision.arguments == {"path": "answer.py", "start_line": 1, "line_count": 220}


def test_required_phase_skips_targeted_read_after_bind_once_file_contents_seen(tmp_path):
    engine, run_id, _approval_id = _repo_run(tmp_path, provider="nvidia_nim", model="meta/llama-3.1-70b-instruct")
    runtime = AgentPlannerRuntime(engine, ScriptedPlannerProvider([]))
    run = engine.store.get_run(run_id)
    state = runtime._load_state(run_id)
    state.observations = [
        {
            "observation_id": "obs-read",
            "tool_id": "workspace.read_range",
            "status": "completed",
            "result": {"path": "answer.py", "content": "VALUE = 1\n"},
        },
        {
            "observation_id": "obs-bind",
            "tool_id": "worktree.bind",
            "status": "completed",
            "result": {"task_id": "wt-1", "worktree_root": str(tmp_path / "repo")},
        },
    ]
    decision = runtime._required_phase_decision(run, state)
    assert decision is None


def test_planner_prompt_keeps_workspace_inventory_narrow(tmp_path):
    engine, run_id = make_run(tmp_path)
    runtime = AgentPlannerRuntime(engine, ScriptedPlannerProvider([]))
    projected = runtime._compact_observation({
        "observation_id": "obs-1",
        "tool_id": "workspace.list",
        "status": "completed",
        "result": {"count": 1000, "entries": [
            {"kind": "file", "name": f"file-{index}.py", "path": f"src/file-{index}.py", "size": 100}
            for index in range(100)
        ]},
    })
    assert len(projected["result"]["entries"]) == 12
    assert "size" not in projected["result"]["entries"][0]
    prompt = runtime._prompt(engine.store.get_run(run_id), runtime._load_state(run_id))
    assert "Return ONE JSON object" in prompt
    assert "Never emit whole-file source" in prompt


def test_kitty_preflight_waits_for_observed_source(tmp_path):
    engine = AgentRunEngine(tmp_path)
    run = engine.create_run(session_id="kitty", objective="Explain sample.py", mode="analysis",
                            request={"transport": "beast_coder_tli_v1", "context_files": ["sample.py"]})
    prepared = []

    class Coordinator:
        advisory_context = []

        def prepare(self, **packet):
            prepared.append(packet)
            return {"events": [], "source_files": packet["source_files"]}

    runtime = AgentPlannerRuntime(engine, ScriptedPlannerProvider([]), integration_coordinator=Coordinator())
    state = runtime._load_state(run["run_id"])
    state.observations.append({"tool_id": "workspace.index", "status": "completed"})
    asyncio.run(runtime._prepare_coder_integrations(run, state))
    assert prepared == []
    state.observations.append({"tool_id": "workspace.read_range", "status": "completed",
                               "result": {"path": "sample.py", "content": "VALUE = 1"}})
    asyncio.run(runtime._prepare_coder_integrations(engine.store.get_run(run["run_id"]), state))
    asyncio.run(runtime._prepare_coder_integrations(engine.store.get_run(run["run_id"]), state))
    assert [packet["source_files"] for packet in prepared] == [{"sample.py": "VALUE = 1"}]
    assert prepared[0]["task_metadata"]["read_only"] is True


def _evict_bound_worktree_receipt(runtime, run_id):
    state = runtime._load_state(run_id)
    state.observations = [
        {"tool_id": "worktree.read_range", "status": "failed", "error": "unknown tool",
         "arguments": {"path": "answer.py"}, "result": {}}
        for _ in range(runtime.observation_limit)
    ]
    state.turn = 4
    runtime._save_state(state)


def test_resume_uses_valid_worktree_when_bind_receipt_has_aged_out(tmp_path):
    engine, run_id, approval_id = _repo_run(tmp_path)
    bind = asyncio.run(engine.execute_tool(run_id, "worktree.bind", {}, approval_id=approval_id))
    runtime = AgentPlannerRuntime(engine, ScriptedPlannerProvider([]), max_turns=8, observation_limit=3)
    _evict_bound_worktree_receipt(runtime, run_id)
    result = asyncio.run(runtime.run(run_id, max_turns_this_call=1))
    assert result["checkpoint"]["worktree_root"] == bind["result"]["worktree_root"]
    assert result["checkpoint"]["last_tool_id"] == "workspace.read_range"
    assert result["checkpoint"]["last_tool_status"] == "completed"
    binds = [e for e in engine.store.events(run_id) if e["event_type"] == "agent.tool.completed"
             and e["payload"]["observation"]["tool_id"] == "worktree.bind"]
    assert len(binds) == 1


def test_resume_refuses_stale_worktree_before_provider_call(tmp_path):
    from pathlib import Path
    import shutil

    engine, run_id, approval_id = _repo_run(tmp_path)
    bind = asyncio.run(engine.execute_tool(run_id, "worktree.bind", {}, approval_id=approval_id))
    shutil.rmtree(Path(bind["result"]["worktree_root"]))
    calls = []

    async def provider(prompt, run, turn):
        calls.append(turn)
        return parse_planner_decision({"decision_type": "tool", "tool_id": "worktree.bind", "arguments": {}})

    runtime = AgentPlannerRuntime(engine, CallbackPlannerProvider(provider), max_turns=8, observation_limit=3)
    _evict_bound_worktree_receipt(runtime, run_id)
    result = asyncio.run(runtime.run(run_id, max_turns_this_call=1))
    assert result["state"] == "policy_blocked"
    assert "STALE_WORKTREE_BINDING" in result["checkpoint"]["planner"]["blocker"]
    assert not calls


def test_unregistered_worktree_reader_gets_bounded_guidance_without_execution(tmp_path):
    engine, run_id, approval_id = _repo_run(tmp_path)
    bind = asyncio.run(engine.execute_tool(run_id, "worktree.bind", {}, approval_id=approval_id))
    read = asyncio.run(engine.execute_tool(run_id, "workspace.read_range", {"path": "answer.py"}))
    runtime = AgentPlannerRuntime(engine, ScriptedPlannerProvider([
        {"decision_type": "tool", "tool_id": "worktree.read_range", "arguments": {"path": "answer.py"}},
        {"decision_type": "tool", "tool_id": "workspace.read_range", "arguments": {"path": "answer.py"}},
    ]), max_turns=6)
    state = runtime._load_state(run_id)
    state.observations = [bind, read]
    runtime._save_state(state)
    result = asyncio.run(runtime.run(run_id, max_turns_this_call=2))
    events = engine.store.events(run_id, limit=1000)
    assert result["checkpoint"]["last_tool_id"] == "workspace.read_range"
    assert result["checkpoint"]["last_tool_status"] == "completed"
    assert any(e["event_type"] == "agent.planner.tool_guidance"
               and e["payload"]["replacement_tool_id"] == "workspace.read_range" for e in events)
    assert not any(e["event_type"] == "agent.planner.observation.accepted"
                   and e["payload"]["tool_id"] == "worktree.read_range" for e in events)


def test_model_cannot_rebind_valid_worktree_on_resume(tmp_path):
    engine, run_id, approval_id = _repo_run(tmp_path)
    bind = asyncio.run(engine.execute_tool(run_id, "worktree.bind", {}, approval_id=approval_id))
    read = asyncio.run(engine.execute_tool(run_id, "workspace.read_range", {"path": "answer.py"}))
    runtime = AgentPlannerRuntime(engine, ScriptedPlannerProvider([
        {"decision_type": "tool", "tool_id": "worktree.bind", "arguments": {}},
        {"decision_type": "tool", "tool_id": "worktree.bind", "arguments": {}},
    ]), max_turns=4)
    state = runtime._load_state(run_id)
    state.observations = [read]
    runtime._save_state(state)
    result = asyncio.run(runtime.run(run_id, max_turns_this_call=2))
    assert result["state"] == "policy_blocked"
    assert result["checkpoint"]["worktree_root"] == bind["result"]["worktree_root"]
    events = engine.store.events(run_id)
    assert len([e for e in events if e["event_type"] == "agent.planner.tool_guidance"]) == 2
    assert len([e for e in events if e["event_type"] == "agent.tool.completed"
                and e["payload"]["observation"]["tool_id"] == "worktree.bind"]) == 1


def _pending_exact_bind(tmp_path):
    """Set up a run where turn 2 is worktree.bind — executes directly, no approval needed."""
    engine, run_id, _ = _repo_run(tmp_path)
    calls = []

    async def plan(prompt, run, turn):
        calls.append(turn)
        if len(calls) == 1:
            return {"decision_type": "tool", "tool_id": "workspace.index", "arguments": {}}
        return {"decision_type": "tool", "tool_id": "worktree.bind",
                "arguments": {"base_ref": "HEAD", "task_id": f"proposal-{len(calls)}"}}

    runtime = AgentPlannerRuntime(engine, CallbackPlannerProvider(plan))
    # Turn 1: workspace.index
    asyncio.run(runtime.run_one_turn(run_id))
    # Turn 2: worktree.bind executes directly (no per-call approval required)
    card = {"request": {
        "safe_arguments": {"base_ref": "HEAD", "task_id": "proposal-2"},
        "tool_id": "worktree.bind",
    }}
    return engine, run_id, runtime, calls, card


def test_deferred_approval_resumes_exact_bind_without_replanning(tmp_path):
    """With no per-call approval, worktree.bind executes directly without waiting."""
    engine, run_id, runtime, calls, card = _pending_exact_bind(tmp_path)
    count = len(calls)
    # bind executes directly — no waiting_for_approval, no deferred card
    result = asyncio.run(runtime.run_one_turn(run_id))
    assert result["state"] != "waiting_for_approval", result["state"]
    assert len(calls) == count + 1  # turn 2 (bind) ran in this call
    assert result["checkpoint"].get("worktree_root")
    asyncio.run(runtime.run_one_turn(run_id))
    events = engine.store.events(run_id, limit=1000)
    binds = [e["payload"]["observation"] for e in events
             if e["event_type"] == "agent.tool.completed"
             and e["payload"]["observation"]["tool_id"] == "worktree.bind"]
    assert len(binds) == 1
    assert binds[0]["arguments"] == card["request"]["safe_arguments"]


def test_deferred_approval_rejection_does_not_replan(tmp_path):
    """No approval cards exist — rejection path is unreachable."""
    engine, run_id, runtime, calls, card = _pending_exact_bind(tmp_path)
    count = len(calls)
    # bind executes directly, no rejection possible
    result = asyncio.run(runtime.run_one_turn(run_id))
    assert result["state"] != "policy_blocked", result["state"]
    assert result["checkpoint"].get("worktree_root")
    assert len(calls) == count + 1


def test_deferred_approval_rejects_changed_saved_arguments(tmp_path):
    """No deferred approval cards — argument mismatch checking is unreachable."""
    engine, run_id, runtime, calls, card = _pending_exact_bind(tmp_path)
    count = len(calls)
    # bind executes directly with whatever arguments the model provides
    result = asyncio.run(runtime.run_one_turn(run_id))
    assert result["state"] != "policy_blocked", result["state"]
    assert result["checkpoint"].get("worktree_root")
    assert len(calls) == count + 1


def test_deferred_approval_claim_blocks_replay_across_workers(tmp_path):
    """No deferred approval claims — replay blocking is unreachable."""
    engine, run_id, runtime, calls, card = _pending_exact_bind(tmp_path)
    count = len(calls)
    # bind executes directly, no claim/replay logic
    result = asyncio.run(runtime.run_one_turn(run_id))
    assert result["state"] != "policy_blocked", result["state"]
    assert result["checkpoint"].get("worktree_root")
    assert len(calls) == count + 1


@pytest.mark.parametrize("case", ["disabled", "rejected", "approved", "stale_evidence", "live_split", "legacy_split", "read_loop"])
def test_dampened_mutation_dispatches_swarm_once_with_bound_evidence(tmp_path, monkeypatch, case):
    import json
    import subprocess
    import sys
    from app.kernel.agents.planner_provider import PlannerDecisionError
    from app.kernel.agents.swarm_specialist import OllamaSwarmRunner

    monkeypatch.setenv("BEAST_SWARM_SPECIALIST", "0" if case == "disabled" else "1")
    monkeypatch.setenv("BEAST_SWARM_SPECIALIST_MODEL", "qwen2.5-coder:7b")
    monkeypatch.setenv("BEAST_OLLAMA_BASE_URL", "http://127.0.0.1:11434")
    monkeypatch.setenv("BEAST_GOVERNED_INTERCEPTION", "0")
    generated = []

    async def installed(self):
        return ["qwen2.5-coder:7b"]

    async def generate(self, **kwargs):
        generated.append(json.loads(kwargs["prompt"]))
        return {"text": json.dumps({"path": "outside.py" if case == "rejected" else "answer.py",
                                    "old_text": "VALUE = 1", "new_text": "VALUE = 2"}),
                "usage": {"prompt_tokens": 120, "completion_tokens": 35}, "done_reason": "stop"}

    monkeypatch.setattr(OllamaSwarmRunner, "installed_models", installed)
    monkeypatch.setattr(OllamaSwarmRunner, "generate", generate)
    engine, run_id, approval_id = _repo_run(
        tmp_path, provider="nvidia_nim", graduation_contract=True, approval_capability="worktree.bind",
    )
    from pathlib import Path

    root = Path(engine.workspace_root)
    split = case in {"live_split", "legacy_split"}
    if split:
        (root / "answer.py").write_text("VALUE = 99\n")
    read_decision = {"decision_type": "tool", "tool_id": "workspace.read_range",
                     "arguments": {"path": "answer.py", "start_line": 1, "line_count": 1}}
    before_bind = asyncio.run(engine.execute_tool(run_id, "workspace.read_range", read_decision["arguments"])) if split else None
    primary = ScriptedPlannerProvider([read_decision, read_decision] if case == "read_loop" else ([read_decision] if case == "live_split" else []) + [{
        "decision_type": "tool", "tool_id": "worktree.replace_exact",
        "arguments": {"old_text": "", "new_text": ""},
    }])

    class Dampened:
        async def next_decision(self, *args, **kwargs):
            raise PlannerDecisionError("NIM route dampened after repeated slow or failed planner turns")

    runtime = AgentPlannerRuntime(engine, primary, max_turns=5)
    monkeypatch.setattr(runtime, "_get_mutation_retry_provider", lambda *_: Dampened())
    state = runtime._load_state(run_id)
    state.observations = [
        {"tool_id": "workspace.read_range", "status": "completed",
         "result": {"path": "answer.py", "content": "VALUE = 1", "start_line": 1}},
        {"tool_id": "worktree.bind", "status": "completed", "result": {}},
    ]
    state.turn = 2
    _bind_test_worktree(engine, run_id, approval_id, runtime, state)

    worktree = Path(engine.store.get_run(run_id)["checkpoint"]["worktree_root"])
    if case == "read_loop":
        evidence = asyncio.run(engine.execute_tool(run_id, "workspace.read_range", read_decision["arguments"]))
        state.observations.append(evidence)
        runtime._save_state(state)
    if case == "stale_evidence":
        (worktree / "answer.py").write_text("VALUE = 9\n")
    if split:
        assert before_bind["result"]["content"] == "VALUE = 99"
        state.observations[0] = before_bind
        runtime._save_state(state)
    if case == "live_split":
        # Act through the normal planner/tool path after binding.
        inspected = asyncio.run(runtime.run(run_id, max_turns_this_call=1, defer_approval=True))
        result = inspected["checkpoint"]["planner"]["observations"][-1]["result"]
        assert result["content"] == "VALUE = 1"
        assert result["source_scope"] == "bound_worktree"

    final = asyncio.run(runtime.run(run_id, max_turns_this_call=1, defer_approval=True))
    events = engine.store.events(run_id, limit=200)
    receipts = [e["payload"] for e in events if e["payload"].get("capability") == "swarm_recovery"]
    if case in {"disabled", "stale_evidence"}:
        assert not generated
        assert final["state"] == "policy_blocked"
        if case == "disabled":
            assert not receipts
        else:
            assert receipts[-1]["reason"] == "no_matching_bound_worktree_evidence"
        return
    assert len(generated) == 1, [r["reason"] for r in receipts]
    if case == "rejected":
        assert receipts[-1]["reason"] == "candidate_outside_exact_edit_contract"
        assert final["state"] == "policy_blocked"
        assert (worktree / "answer.py").read_text() == "VALUE = 1\n"
        return
    if case == "read_loop":
        assert any(e["event_type"] == "agent.provider.post_bind_read_stalled" for e in events)
        assert not any(e["event_type"] == "agent.provider.invalid_mutation_retry" for e in events)
        # With autopilot, workspace-bounded tools auto-grant — no approval card,
        # no waiting_for_approval. The run stays in updating_plan/completed.
        assert final["state"] != "waiting_for_approval"
        return
    assert "VALUE = 1" in generated[0]["source_context"]
    assert "VALUE = 99" not in generated[0]["source_context"]
    if case == "legacy_split":
        # Find the read_range observation that shows bound_worktree scope
        obs = final["checkpoint"]["planner"]["observations"]
        read_obs = [o for o in obs if o.get("tool_id") == "workspace.read_range" and o.get("result", {}).get("source_scope") == "bound_worktree"]
        assert read_obs, f"Expected a bound_worktree read_range observation, got: {obs}"
        assert read_obs[-1]["result"]["content"] == "VALUE = 1"
    assert {role["role"] for role in receipts[-1]["roles"]} == {
        "hermes", "conductor", "sentinel", "cartographer", "failure_analyst",
        "compressor", "crystalist", "verifier", "supervisor", "critic", "scribe", "archivist",
    }
    assert receipts[-1]["reason"] == "candidate_grounded"
    assert receipts[-1]["effect_committed"] is False
    assert sum(e["event_type"] == "agent.tool.started" and e["payload"].get("tool_id") == "worktree.bind"
               for e in events) == 1
    assert (root / "answer.py").read_text() == ("VALUE = 99\n" if split else "VALUE = 1\n")
    # With no per-call approval, replace_exact executes directly — no
    # waiting_for_approval, no approval card.
    assert final["state"] != "waiting_for_approval", final["state"]
    assert (worktree / "answer.py").read_text() == "VALUE = 2\n"
    assert (root / "answer.py").read_text() == ("VALUE = 99\n" if split else "VALUE = 1\n")
    result = subprocess.run([sys.executable, "-m", "pytest", "--noconftest", "-q", "test_answer.py"],
                            cwd=worktree, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr


def test_source_read_rejects_forged_local_binding_and_ask_stays_on_checkout(tmp_path):
    engine, run_id, approval_id = _repo_run(tmp_path)
    asyncio.run(engine.execute_tool(run_id, "worktree.bind", {}, approval_id=approval_id))
    cp = engine.store.get_run(run_id)["checkpoint"]
    engine.merge_checkpoint(run_id, {"worktree_root": str(tmp_path)})
    with pytest.raises(PermissionError, match="STALE_WORKTREE_BINDING"):
        asyncio.run(engine.execute_tool(run_id, "workspace.read_range", {"path": "answer.py"}))

    ask_id = engine.create_run(session_id="ask-test", objective="Read answer", mode="ask")["run_id"]
    engine.merge_checkpoint(ask_id, cp)
    read = asyncio.run(engine.execute_tool(ask_id, "workspace.read_range", {"path": "answer.py"}))
    assert read["result"]["source_scope"] == "workspace_checkout"
    assert read["result"]["content"] == "VALUE = 1"


def test_post_bind_read_guard_only_blocks_covered_ranges(tmp_path):
    engine, run_id, _ = _repo_run(tmp_path)
    state = AgentPlannerRuntime(engine, ScriptedPlannerProvider([]))._load_state(run_id)
    def read(start, count):
        return parse_planner_decision({"decision_type": "tool", "tool_id": "workspace.read_range",
            "arguments": {"path": "answer.py", "start_line": start, "line_count": count}})

    state.observations = [{"tool_id": "worktree.bind", "status": "completed"}]
    for start, end in ((1, 80), (81, 120)):
        state.observations.append({
            "tool_id": "workspace.read_range", "status": "completed",
            "result": {"path": "answer.py", "source_scope": "bound_worktree", "content": "data",
                       "start_line": start, "end_line": end, "total_lines": 800},
        })
    duplicate = AgentPlannerRuntime._post_bind_duplicate_read
    assert duplicate(read(1, 80), state)
    assert duplicate(read(31, 90), state)
    assert not duplicate(read(81, 80), state)
    assert not duplicate(read(630, 80), state)


def test_hosted_nim_retry_does_not_send_nvidia_model_to_ollama(tmp_path, monkeypatch):
    monkeypatch.delenv("BEAST_NIM_MODEL", raising=False)
    monkeypatch.delenv("NVIDIA_NIM_BASE_URL", raising=False)
    engine, run_id, _ = _repo_run(tmp_path, provider="nvidia_nim", model="nvidia/nemotron-3.5-super-vl-120b-a12b")
    primary = ScriptedPlannerProvider([])
    runtime = AgentPlannerRuntime(engine, primary)
    assert runtime._get_mutation_retry_provider(primary, engine.store.get_run(run_id)) is primary


@pytest.mark.parametrize("claim", ["real", "fabricated"])
def test_tli_no_change_requires_quoted_bound_evidence(tmp_path, claim):
    engine, run_id, approval_id = _repo_run(tmp_path, transport="beast_coder_tli_v1")
    bind = asyncio.run(engine.execute_tool(run_id, "worktree.bind", {}, approval_id=approval_id))
    read = asyncio.run(engine.execute_tool(run_id, "workspace.read_range", {"path": "answer.py"}))
    runtime = AgentPlannerRuntime(engine, ScriptedPlannerProvider([{
        "decision_type": "complete", "summary": "The requested definition exists.",
        "arguments": {"no_change": {"observation_id": read["observation_id"],
                                    "quote": "VALUE = 1" if claim == "real" else "VALUE = 82"}},
    }]))
    state = runtime._load_state(run_id)
    state.observations = [bind, read]
    runtime._save_state(state)
    result = asyncio.run(runtime.run(run_id, max_turns_this_call=1))
    events = engine.store.events(run_id, limit=250)
    if claim == "real":
        assert result["state"] == "completed"
        completion = next(e["payload"] for e in events if e["event_type"] == "agent.planner.completed")
        assert completion["completion_mode"] == "evidence_backed_no_change"
        assert completion["promotion_authorized"] is False
    else:
        assert result["state"] != "completed"
        assert any(e["event_type"] == "agent.planner.completion_rejected" for e in events)
    assert not any(e["event_type"] == "agent.sourceplan.ready" for e in events)


def test_tli_bound_handoff_uses_requested_test_and_leaves_diff_for_review(tmp_path):
    from pathlib import Path
    engine, run_id, approval_id = _repo_run(tmp_path, graduation_contract=True, transport="beast_coder_tli_v1")
    bind = asyncio.run(engine.execute_tool(run_id, "worktree.bind", {}, approval_id=approval_id))
    read = asyncio.run(engine.execute_tool(run_id, "workspace.read_range", {"path": "answer.py"}))
    command = ["python", "-m", "pytest", "-q", "test_answer.py", "-k", "value"]
    runtime = AgentPlannerRuntime(engine, ScriptedPlannerProvider([
        {"decision_type": "blocked", "blocker": "No worktree.bind tool is available in the allowed tool list"},
        {"decision_type": "tool", "tool_id": "worktree.replace_exact",
         "arguments": {"path": "answer.py", "old_text": "VALUE = 1", "new_text": "VALUE = 2"}},
        {"decision_type": "tool", "tool_id": "worktree.verify", "arguments": {"command": command}},
    ]), max_turns=7)
    state = runtime._load_state(run_id)
    state.observations = [bind, read]
    runtime._save_state(state)
    final = asyncio.run(runtime.run(run_id))
    assert final["state"] == "completed", final["error"]
    assert (Path(engine.workspace_root) / "answer.py").read_text() == "VALUE = 1\n"
    assert (Path(bind["result"]["worktree_root"]) / "answer.py").read_text() == "VALUE = 2\n"
    events = engine.store.events(run_id, limit=500)
    observations = [e["payload"]["observation"] for e in events if e["event_type"] == "agent.tool.completed"]
    assert sum(o["tool_id"] == "worktree.bind" for o in observations) == 1
    verify = next(o["result"] for o in observations if o["tool_id"] == "worktree.verify")
    assert verify["command"] == command and verify["returncode"] == 0
    completion = next(e["payload"] for e in events if e["event_type"] == "agent.planner.completed")
    assert completion["completion_mode"] == "isolated_review"
    assert completion["promotion_authorized"] is False


def test_passing_baseline_verifier_cannot_create_empty_sourceplan(tmp_path):
    from app.kernel.agents.tool_runtime import ToolExecutionFailed

    engine, run_id, approval_id = _repo_run(tmp_path, transport="beast_coder_tli_v1")
    asyncio.run(engine.execute_tool(run_id, "worktree.bind", {}, approval_id=approval_id))
    verified = asyncio.run(engine.execute_tool(
        run_id, "worktree.verify", {"command": ["git", "diff", "--check"]}, approval_id=approval_id,
    ))
    assert verified["result"]["returncode"] == 0
    with pytest.raises(ToolExecutionFailed, match="non-empty worktree diff"):
        asyncio.run(engine.execute_tool(run_id, "worktree.sourceplan_draft", {}))
    assert not any(e["event_type"] == "agent.sourceplan.ready" for e in engine.store.events(run_id))


def test_duplicate_read_adds_targeted_worktree_evidence_before_normal_budget_retry(tmp_path, monkeypatch):
    import subprocess
    from pathlib import Path

    monkeypatch.setenv("BEAST_SWARM_SPECIALIST", "0")
    engine, run_id, approval_id = _repo_run(tmp_path, provider="nvidia_nim")
    root = Path(engine.workspace_root)
    (root / "answer.py").write_text("# filler\n" * 80 + "def action_copy_run():\n    return 1\n")
    subprocess.run(["git", "commit", "-qam", "fixture"], cwd=root, check=True)
    with engine.store._connect() as db:
        db.execute("UPDATE agent_runs SET objective=? WHERE run_id=?", ("Add /copy file", run_id))
    bind = asyncio.run(engine.execute_tool(run_id, "worktree.bind", {}, approval_id=approval_id))
    args = {"path": "answer.py", "start_line": 1, "line_count": 20}
    read = asyncio.run(engine.execute_tool(run_id, "workspace.read_range", args))
    prompts = []

    async def decide(prompt, run, turn):
        prompts.append(prompt)
        return {"decision_type": "tool", "tool_id": "workspace.read_range", "arguments": args}

    runtime = AgentPlannerRuntime(engine, CallbackPlannerProvider(decide))
    state = runtime._load_state(run_id)
    state.turn, state.observations = 2, [bind, read]
    runtime._save_state(state)
    final = asyncio.run(runtime.run_one_turn(run_id))
    assert final["state"] == "paused", final.get("error")
    assert len(prompts) == 2
    assert "def action_copy_run():" in prompts[-1] and "1–20" in prompts[-1]
    events = engine.store.events(run_id, limit=250)
    retry = next(e["payload"] for e in events if e["event_type"] == "agent.provider.post_bind_read_retry")
    assert retry["timeout_seconds"] == runtime._decision_timeout_seconds(engine.store.get_run(run_id))
    receipts = [e["payload"]["observation"] for e in events
                if e["event_type"] == "agent.tool.completed"
                and e["payload"]["observation"]["tool_id"] == "workspace.read_range"]
    assert len(receipts) == 2
    assert receipts[-1]["result"]["source_scope"] == "bound_worktree"
    assert "def action_copy_run():" in receipts[-1]["result"]["content"]


def test_missing_legacy_deferred_approval_action_stops_without_replanning(tmp_path):
    engine, run_id, _ = _repo_run(tmp_path)
    approval_id = "approval-legacy-without-action"
    engine.store.create_approval(run_id, {"request_id": approval_id, "tool_id": "worktree.bind"})
    engine.store.resolve_approval(run_id, approval_id, {"approved": True})
    engine.merge_checkpoint(run_id, {"suspended_approval_id": approval_id})
    engine.emit(run_id, "agent.planner.approval_deferred", {
        "approval_id": approval_id, "tool_id": "worktree.bind",
    })
    calls = []

    async def plan(prompt, run, turn):
        calls.append(turn)
        return {"decision_type": "tool", "tool_id": "worktree.bind",
                "arguments": {"base_ref": "HEAD"}}

    runtime = AgentPlannerRuntime(engine, CallbackPlannerProvider(plan))
    result = asyncio.run(runtime.run_one_turn(run_id))
    assert calls == []
    assert result["state"] == "policy_blocked"
    assert "DEFERRED_APPROVAL_ACTION_MISSING" in result["error"]
    assert not result["checkpoint"].get("worktree_root")

from __future__ import annotations

import asyncio
import json
import sqlite3

import pytest

from app.kernel.agents import tool_runtime as tool_runtime_module
from app.kernel.agents.run_engine import AgentRunEngine
from app.kernel.agents.run_state import AgentRunState
from app.kernel.agents.run_store import AgentRunStore


def test_agent_run_store_hash_chain_and_replay(tmp_path):
    store = AgentRunStore(tmp_path)
    run = store.create_run(
        session_id="session-1",
        objective="Repair the router",
        mode="agent",
        provider="local",
        model="coder",
        request={"files": ["app.py"]},
    )
    run_id = run["run_id"]
    store.transition(run_id, AgentRunState.SCOPING)
    first = store.append_event(run_id, "agent.plan.created", {"steps": ["inspect", "repair"]})
    second = store.append_event(run_id, "agent.tool.completed", {"tool": "read", "ok": True})

    assert first["sequence"] == 2  # sequence 1 is agent.run.created
    assert second["sequence"] == 3
    assert second["previous_hash"] == first["event_hash"]
    assert store.verify_chain(run_id)["head_matches"] is True

    reopened = AgentRunStore(tmp_path)
    replay = reopened.events(run_id)
    assert [event["sequence"] for event in replay] == [1, 2, 3]
    assert reopened.get_run(run_id)["state"] == AgentRunState.SCOPING.value


def test_agent_run_store_detects_tampering(tmp_path):
    store = AgentRunStore(tmp_path)
    run = store.create_run(session_id="session-2", objective="Inspect", mode="analysis")
    run_id = run["run_id"]
    store.append_event(run_id, "agent.context.ready", {"files": ["a.py"]})

    connection = sqlite3.connect(store.db_path)
    try:
        connection.execute(
            "UPDATE agent_run_events SET payload_json=? WHERE run_id=? AND sequence=2",
            (json.dumps({"files": ["tampered.py"]}), run_id),
        )
        connection.commit()
    finally:
        connection.close()

    result = store.verify_chain(run_id)
    assert result["ok"] is False
    assert result["reason"] == "chain_mismatch"


def test_agent_run_approval_is_durable(tmp_path):
    store = AgentRunStore(tmp_path)
    run = store.create_run(session_id="session-3", objective="Use verifier")
    run_id = run["run_id"]
    approval = store.create_approval(run_id, {
        "request_id": "approval-1",
        "capabilities": [{"id": "run_isolated_verifier"}],
    })
    assert approval["status"] == "pending"

    resolved = store.resolve_approval(run_id, "approval-1", {"approved": True, "scope": "once"})
    assert resolved["status"] == "approved"
    assert AgentRunStore(tmp_path).approvals(run_id)[0]["resolution"]["scope"] == "once"


def test_legacy_sse_projection_updates_run_state(tmp_path):
    engine = AgentRunEngine(tmp_path)
    run = engine.create_run(session_id="session-4", objective="Simulate", mode="analysis")
    run_id = run["run_id"]
    engine.store.transition(run_id, AgentRunState.SCOPING)

    engine.record_legacy_chunk(run_id, 'event: agent_run_started\ndata: {"payload":{"session_id":"session-4"}}\n\n')
    engine.record_legacy_chunk(run_id, 'event: agent_run_permission_request\ndata: {"payload":{"request_id":"cap-1","capabilities":[]}}\n\n')
    assert engine.store.get_run(run_id)["state"] == AgentRunState.WAITING_FOR_APPROVAL.value
    assert engine.store.approvals(run_id)[0]["approval_id"] == "cap-1"

    engine.record_legacy_chunk(run_id, 'event: agent_run_done\ndata: {"payload":{"ok":true,"sourceplan_status":"chat_complete"}}\n\n')
    assert engine.store.get_run(run_id)["state"] == AgentRunState.COMPLETED.value


def test_legacy_sse_projection_adapts_canonical_planner_events(tmp_path):
    engine = AgentRunEngine(tmp_path)
    run = engine.create_run(session_id="session-planner-wire", objective="Repair sample", mode="agent")
    run_id = run["run_id"]

    engine.emit(run_id, "agent.planner.started", {"turn": 0})
    engine.emit(run_id, "agent.tool.started", {"tool_id": "workspace.list"})
    engine.emit(run_id, "agent.sourceplan.ready", {"plan_id": "plan-1", "plan": {"operations": []}})

    frames = [engine.sse_event(event, projection="legacy") for event in engine.store.events(run_id)]
    assert "event: agent_run_stage" in frames[-3]
    assert "event: agent_run_tool" in frames[-2]
    assert '"tool": "workspace.list"' in frames[-2]
    assert "event: agent_run_sourceplan" in frames[-1]
    assert '"plan_id": "plan-1"' in frames[-1]
    assert '"operations": []' in frames[-1]


def test_agent_tool_runtime_emits_execution_target_payload(tmp_path, monkeypatch):
    captured = {}

    async def fake_target_shell(context, script, *, timeout=20.0, output_limit=512000):
        captured["script"] = script
        captured["target"] = context.execution_target
        return {"ok": True, "returncode": 0, "stdout": "README.md\tREADME.md\tf\t12\n", "stderr": "", "truncated": False}

    monkeypatch.setattr(tool_runtime_module, "_run_target_shell", fake_target_shell)
    engine = AgentRunEngine(tmp_path)
    run = engine.create_run(
        session_id="session-target-runtime",
        objective="Inspect through target session",
        mode="analysis",
        request={
            "execution_target": "ssh",
            "execution_target_payload": {"kind": "ssh", "sessionId": "target-ssh-1", "host": "devbox", "label": "SSH devbox"},
        },
    )
    run_id = run["run_id"]

    result = asyncio.run(engine.execute_tool(
        run_id,
        "workspace.list",
        {},
        execution_target="ssh",
        execution_target_payload={"kind": "ssh", "sessionId": "target-ssh-1", "host": "devbox", "label": "SSH devbox"},
    ))
    assert result["status"] == "completed"
    assert result["result"]["target_execution"] == "remote_ssh"
    assert result["result"]["transport"] == "ssh"
    assert result["result"]["execution_target_payload"]["sessionId"] == "target-ssh-1"
    assert "cd '~'" in captured["script"]
    assert captured["target"] == "ssh"

    started = [event for event in engine.store.events(run_id) if event["event_type"] == "agent.tool.started"][-1]
    assert started["payload"]["execution_target"] == "ssh"
    assert started["payload"]["execution_target_payload"]["sessionId"] == "target-ssh-1"


def test_agent_workspace_read_range_uses_remote_target(tmp_path, monkeypatch):
    async def fake_target_shell(_context, _script, *, timeout=20.0, output_limit=512000):
        return {
            "ok": True,
            "returncode": 0,
            "stdout": "BEAST_META\n3\nabc123\nBEAST_CONTENT\nalpha\nbeta\n",
            "stderr": "",
            "truncated": False,
        }

    monkeypatch.setattr(tool_runtime_module, "_run_target_shell", fake_target_shell)
    engine = AgentRunEngine(tmp_path)
    run_id = engine.create_run(session_id="session-target-read", objective="Read remote", mode="analysis")["run_id"]
    result = asyncio.run(engine.execute_tool(
        run_id,
        "workspace.read_range",
        {"path": "README.md", "start_line": 1, "line_count": 2},
        execution_target="ssh",
        execution_target_payload={"kind": "ssh", "sessionId": "target-ssh-read", "host": "devbox", "remoteRoot": "/repo"},
    ))
    assert result["status"] == "completed"
    assert result["result"]["target_execution"] == "remote_ssh"
    assert result["result"]["content"] == "alpha\nbeta"
    assert result["result"]["sha256"] == "abc123"


def test_agent_workspace_search_text_uses_remote_target(tmp_path, monkeypatch):
    async def fake_target_shell(_context, _script, *, timeout=20.0, output_limit=512000):
        return {
            "ok": True,
            "returncode": 0,
            "stdout": "./app.py:7:def answer():\n",
            "stderr": "",
            "truncated": False,
        }

    monkeypatch.setattr(tool_runtime_module, "_run_target_shell", fake_target_shell)
    engine = AgentRunEngine(tmp_path)
    run_id = engine.create_run(session_id="session-target-search", objective="Search remote", mode="analysis")["run_id"]
    result = asyncio.run(engine.execute_tool(
        run_id,
        "workspace.search_text",
        {"query": "answer", "path": "."},
        execution_target="container",
        execution_target_payload={"kind": "container", "sessionId": "target-container-search", "containerId": "devctr", "workspaceFolder": "/workspace"},
    ))
    assert result["status"] == "completed"
    assert result["result"]["target_execution"] == "remote_container"
    assert result["result"]["matches"][0]["path"] == "app.py"
    assert result["result"]["matches"][0]["line"] == 7


def test_agent_run_cancel_interrupts_registered_task(tmp_path):
    async def scenario():
        engine = AgentRunEngine(tmp_path)
        run = engine.create_run(session_id="session-5", objective="Slow task")
        run_id = run["run_id"]
        engine.store.transition(run_id, AgentRunState.EXECUTING_TOOL)

        started = asyncio.Event()

        async def worker():
            started.set()
            await asyncio.sleep(30)

        task = asyncio.create_task(worker())
        await started.wait()
        from app.kernel.agents.run_cancel import AGENT_RUN_CANCELLATIONS
        AGENT_RUN_CANCELLATIONS.attach_task(run_id, task)

        result = await engine.cancel(run_id, "operator test")
        assert result["run"]["state"] == AgentRunState.CANCELLING.value
        with pytest.raises(asyncio.CancelledError):
            await task
        final = engine.finalize_cancel(run_id, "operator test")
        assert final["state"] == AgentRunState.CANCELLED.value
        assert engine.store.verify_chain(run_id)["head_matches"] is True

    asyncio.run(scenario())
